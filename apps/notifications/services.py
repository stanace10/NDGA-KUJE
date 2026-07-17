from __future__ import annotations

import base64
import mimetypes
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db import transaction
from django.templatetags.static import static
from django.template.loader import render_to_string
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils import timezone

from apps.audit.services import log_event
from apps.audit.models import AuditCategory, AuditStatus
from apps.dashboard.models import SchoolProfile
from apps.notifications.email_adapters import EmailSendResult, get_email_provider
from apps.notifications.whatsapp_adapters import WhatsAppSendResult, get_whatsapp_provider
from apps.notifications.models import (
    BirthdayContact,
    BirthdayContactType,
    BirthdayDispatch,
    BirthdayDispatchStatus,
    Notification,
    NotificationCategory,
)

try:
    from apps.notifications.models import (
        EmailReplyMessage,
        EmailReplyMessageDirection,
        EmailReplyThread,
        EmailThreadScope,
    )
except ImportError:  # pragma: no cover - compatibility for older deployments
    EmailReplyMessage = None
    EmailReplyMessageDirection = None
    EmailReplyThread = None

    class EmailThreadScope:  # type: ignore[override]
        GENERAL = "GENERAL"
from apps.tenancy.utils import build_portal_url
def _normalized_emails(emails):
    seen = set()
    clean = []
    for email in emails:
        value = (email or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        clean.append(value)
    return clean


CBT_PARENT_CORRECTION_EVENT = "CBT_PARENT_CORRECTION"


def _cbt_parent_messaging_block_applies(*, subject="", body_text="", metadata=None):
    event = str((metadata or {}).get("event") or "").strip().upper()
    if event == CBT_PARENT_CORRECTION_EVENT:
        return False
    payload = " ".join(
        [
            event,
            str(subject or ""),
            str(body_text or ""),
        ]
    ).upper()
    return "CBT" in payload


def _without_guardian_emails_for_cbt(emails, *, subject, body_text, metadata):
    if not _cbt_parent_messaging_block_applies(subject=subject, body_text=body_text, metadata=metadata):
        return emails
    from apps.accounts.models import StudentProfile

    guardian_emails = set(
        _normalized_emails(
            StudentProfile.objects.exclude(guardian_email="")
            .values_list("guardian_email", flat=True)
        )
    )
    if not guardian_emails:
        return emails
    return [email for email in emails if email not in guardian_emails]


def _without_guardian_phones_for_cbt(numbers, *, body_text, metadata):
    if not _cbt_parent_messaging_block_applies(body_text=body_text, metadata=metadata):
        return numbers
    numbers = _normalized_phones(numbers)
    from apps.accounts.models import StudentProfile

    guardian_numbers = set(
        _normalized_phones(
            StudentProfile.objects.exclude(guardian_phone="")
            .values_list("guardian_phone", flat=True)
        )
    )
    if not guardian_numbers:
        return numbers
    return [number for number in numbers if number not in guardian_numbers]


def normalize_whatsapp_phone(raw_phone):
    digits = "".join(ch for ch in str(raw_phone or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("234"):
        return digits
    if digits.startswith("0") and len(digits) == 11:
        return f"234{digits[1:]}"
    if len(digits) == 10:
        return f"234{digits}"
    return digits


def extract_whatsapp_phones(raw_phone):
    parts = re.split(r"[;\n,/|]+", str(raw_phone or ""))
    numbers = []
    seen = set()
    for part in parts:
        value = normalize_whatsapp_phone(part)
        if not value or value in seen:
            continue
        seen.add(value)
        numbers.append(value)
    return numbers


def _normalized_phones(phones):
    seen = set()
    clean = []
    for phone in phones:
        for value in extract_whatsapp_phones(phone):
            if value in seen:
                continue
            seen.add(value)
            clean.append(value)
    return clean


def _email_paragraphs(body_text):
    paragraphs = []
    for block in (body_text or "").replace("\r\n", "\n").split("\n\n"):
        lines = [conditional_escape(line.strip()) for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        paragraphs.append(mark_safe("<br>".join(lines)))
    return paragraphs


def _public_root_url(*, request=None, profile=None):
    profile = profile or SchoolProfile.load()
    if request is not None:
        return build_portal_url(request, "landing", "/").rstrip("/")
    website = (profile.website or "ndgakuje.org").strip()
    if not website:
        return "https://ndgakuje.org"
    parsed = urlparse(website)
    if parsed.scheme and parsed.netloc:
        return website.rstrip("/")
    if website.startswith("//"):
        return f"https:{website}".rstrip("/")
    return f"https://{website.lstrip('/')}".rstrip("/")


def _school_logo_url(*, request=None, profile=None):
    profile = profile or SchoolProfile.load()
    logo_path = static("branding/school/ndga-logo.png")
    if not finders.find("branding/school/ndga-logo.png"):
        logo_path = static("images/ndga/logo.png")
    if logo_path.startswith(("http://", "https://")):
        return logo_path
    if not logo_path.startswith("/"):
        logo_path = f"/{logo_path}"
    static_logo_url = f"{_public_root_url(request=request, profile=profile)}{logo_path}"
    return static_logo_url or _fallback_presigned_email_logo_url()


def _inline_image_data_uri(file_field):
    if not file_field:
        return ""
    name = str(getattr(file_field, "name", "") or "").strip()
    if not name:
        return ""
    mime = mimetypes.guess_type(name)[0] or "image/png"
    try:
        file_field.open("rb")
        try:
            data = file_field.read()
        finally:
            file_field.close()
    except Exception:  # noqa: BLE001
        return ""
    if not data:
        return ""
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def _school_logo_src(*, request=None, profile=None):
    profile = profile or SchoolProfile.load()
    hosted_src = _school_logo_url(request=request, profile=profile)
    if hosted_src:
        return hosted_src
    inline_src = _inline_image_data_uri(getattr(profile, "school_logo", None))
    if inline_src:
        return inline_src
    fallback_path = finders.find("images/ndga/logo.png")
    if fallback_path and Path(fallback_path).exists():
        mime = mimetypes.guess_type(str(fallback_path))[0] or "image/png"
        data = Path(fallback_path).read_bytes()
        if data:
            return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return _school_logo_url(request=request, profile=profile)


def _load_cloud_aws_values():
    keys = (
        "AWS_STORAGE_BUCKET_NAME",
        "AWS_REGION",
        "AWS_S3_REGION_NAME",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    values = {
        key: str(getattr(settings, key, "") or "").strip()
        for key in keys
    }
    if values["AWS_STORAGE_BUCKET_NAME"] and values["AWS_ACCESS_KEY_ID"] and values["AWS_SECRET_ACCESS_KEY"]:
        return values
    env_file = Path(settings.ROOT_DIR) / ".env.cloud"
    if not env_file.exists():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in keys and not values.get(key):
            values[key] = value.strip()
    return values


def _fallback_presigned_email_logo_url():
    try:
        import boto3
        from botocore.config import Config
    except Exception:  # noqa: BLE001
        return ""

    values = _load_cloud_aws_values()
    bucket = values.get("AWS_STORAGE_BUCKET_NAME", "")
    access_key = values.get("AWS_ACCESS_KEY_ID", "")
    secret_key = values.get("AWS_SECRET_ACCESS_KEY", "")
    region = values.get("AWS_REGION") or values.get("AWS_S3_REGION_NAME") or ""
    if not bucket or not access_key or not secret_key or not region:
        return ""
    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": "branding/email/ndga-logo.png"},
            ExpiresIn=604800,
        )
    except Exception:  # noqa: BLE001
        return ""


def _school_email_html(*, subject, body_text, body_html="", request=None):
    profile = SchoolProfile.load()
    portal_home = build_portal_url(request, "landing", "/") if request else ""
    support_email = profile.contact_email or "office@ndgakuje.org"
    support_phone = profile.contact_phone or ""
    website = profile.website or portal_home
    resolved_logo_src = _school_logo_src(request=request, profile=profile)
    rendered_body = body_html or render_to_string(
        "notifications/email_body_default.html",
        {
            "paragraphs": _email_paragraphs(body_text),
        },
    )
    return render_to_string(
        "notifications/email_shell.html",
        {
            "school_profile": profile,
            "logo_src": resolved_logo_src,
            "subject": subject,
            "body_html_content": mark_safe(rendered_body),
            "portal_home": portal_home,
            "support_email": support_email,
            "support_phone": support_phone,
            "website": website,
            "current_year": timezone.now().year,
        },
    )


def _normalized_email(value):
    return (value or "").strip().lower()


def _email_replies_enabled():
    if EmailReplyThread is None or EmailReplyMessage is None:
        return False
    return bool(
        getattr(settings, "NOTIFICATIONS_EMAIL_REPLY_ENABLED", False)
        and str(getattr(settings, "NOTIFICATIONS_REPLY_DOMAIN", "") or "").strip()
    )


def _reply_domain():
    return str(getattr(settings, "NOTIFICATIONS_REPLY_DOMAIN", "") or "").strip().lower()


def _generate_thread_key():
    if EmailReplyThread is None:
        return secrets.token_hex(8)
    while True:
        key = secrets.token_hex(8)
        if not EmailReplyThread.objects.filter(thread_key=key).exists():
            return key


def _reply_to_email_for_thread_key(thread_key):
    return f"thread-{thread_key}@{_reply_domain()}"


def _reply_subject(subject):
    subject = (subject or "").strip()
    if not subject:
        return "NDGA Reply"
    if subject.lower().startswith("re:"):
        return subject
    return f"Re: {subject}"


def _thread_contact_metadata(email):
    from apps.accounts.models import StudentProfile, User

    normalized = _normalized_email(email)
    students = []
    for row in (
        StudentProfile.objects.filter(guardian_email__iexact=normalized)
        .select_related("user")
        .order_by("student_number")
    ):
        students.append(
            {
                "student_number": row.student_number,
                "name": row.user.get_full_name() if row.user_id else row.student_number,
            }
        )

    staff = []
    for row in (
        User.objects.filter(email__iexact=normalized, staff_profile__isnull=False)
        .select_related("staff_profile")
        .order_by("staff_profile__staff_id", "username")
    ):
        staff.append(
            {
                "staff_id": getattr(getattr(row, "staff_profile", None), "staff_id", "") or row.username,
                "name": row.get_full_name() or row.username,
            }
        )

    label_parts = [item["name"] for item in students[:2]] or [item["name"] for item in staff[:2]]
    recipient_label = ", ".join(label_parts) if label_parts else normalized
    return {
        "recipient_label": recipient_label,
        "students": students,
        "staff": staff,
    }


def _create_reply_thread(*, recipient_email, subject, actor=None, scope=EmailThreadScope.GENERAL, source_event="", metadata=None):
    if EmailReplyThread is None:
        return None
    thread_key = _generate_thread_key()
    contact_metadata = _thread_contact_metadata(recipient_email)
    return EmailReplyThread.objects.create(
        thread_key=thread_key,
        scope=scope,
        subject=(subject or "").strip() or "NDGA Email",
        recipient_email=_normalized_email(recipient_email),
        recipient_label=contact_metadata["recipient_label"],
        reply_to_email=_reply_to_email_for_thread_key(thread_key),
        source_event=(source_event or "").strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        metadata={
            **(metadata or {}),
            "students": contact_metadata["students"],
            "staff": contact_metadata["staff"],
        },
    )


def _record_email_thread_outbound_message(
    *,
    thread,
    result,
    subject,
    body_text,
    body_html,
    actor=None,
):
    if EmailReplyMessage is None or EmailReplyMessageDirection is None or thread is None:
        return
    timestamp = timezone.now()
    EmailReplyMessage.objects.create(
        thread=thread,
        direction=EmailReplyMessageDirection.OUTBOUND,
        provider=getattr(result, "provider", ""),
        external_message_id=getattr(result, "external_message_id", "") or "",
        sender_email=settings.NOTIFICATIONS_FROM_EMAIL,
        sender_name=settings.BREVO_SENDER_NAME,
        recipient_email=thread.recipient_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        sent_at=timestamp,
    )
    thread.subject = (thread.subject or "").strip() or (subject or "").strip() or "NDGA Email"
    thread.last_message_at = timestamp
    thread.is_open = True
    thread.save(update_fields=["subject", "last_message_at", "is_open", "updated_at"])


def _mailbox_address(mailbox):
    if not isinstance(mailbox, dict):
        return ""
    return _normalized_email(mailbox.get("Address") or mailbox.get("email") or "")


def _mailbox_name(mailbox):
    if not isinstance(mailbox, dict):
        return ""
    return (mailbox.get("Name") or mailbox.get("name") or "").strip()


def _candidate_inbound_addresses(item):
    rows = []
    for key in ("To", "Recipients", "Cc"):
        values = item.get(key) or []
        if isinstance(values, dict):
            values = [values]
        rows.extend(_mailbox_address(row) for row in values if _mailbox_address(row))
    return rows


def _resolve_inbound_thread(item):
    if EmailReplyThread is None or EmailReplyMessage is None:
        return None
    reply_domain = _reply_domain()
    if reply_domain:
        suffix = f"@{reply_domain}"
        for address in _candidate_inbound_addresses(item):
            if not address.endswith(suffix):
                continue
            local_part = address[: -len(suffix)]
            if local_part.startswith("thread-"):
                thread_key = local_part.removeprefix("thread-").strip()
                thread = EmailReplyThread.objects.filter(thread_key=thread_key).first()
                if thread:
                    return thread
    in_reply_to = str(item.get("InReplyTo") or "").strip()
    if in_reply_to:
        outbound_message = (
            EmailReplyMessage.objects.select_related("thread")
            .filter(external_message_id=in_reply_to)
            .order_by("-created_at")
            .first()
        )
        if outbound_message:
            return outbound_message.thread
    return None


def _coerce_received_at(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return timezone.now()
    try:
        parsed = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError, IndexError):
        return timezone.now()
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed.astimezone(timezone.get_current_timezone())


@transaction.atomic
def ingest_brevo_inbound_payload(payload):
    if EmailReplyThread is None or EmailReplyMessage is None or EmailReplyMessageDirection is None:
        return {"received": 0, "ingested": 0, "duplicates": 0, "unmatched": 0}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return {"received": 0, "ingested": 0, "duplicates": 0, "unmatched": 0}

    summary = {"received": len(items), "ingested": 0, "duplicates": 0, "unmatched": 0}
    for item in items:
        if not isinstance(item, dict):
            summary["unmatched"] += 1
            continue
        external_message_id = str(item.get("MessageId") or "").strip()
        if external_message_id and EmailReplyMessage.objects.filter(external_message_id=external_message_id).exists():
            summary["duplicates"] += 1
            continue
        thread = _resolve_inbound_thread(item)
        if thread is None:
            summary["unmatched"] += 1
            continue
        sender = item.get("From") or {}
        received_at = _coerce_received_at(str(item.get("SentAtDate") or ""))
        EmailReplyMessage.objects.create(
            thread=thread,
            direction=EmailReplyMessageDirection.INBOUND,
            provider="brevo-inbound",
            external_message_id=external_message_id,
            in_reply_to_message_id=str(item.get("InReplyTo") or "").strip(),
            sender_email=_mailbox_address(sender),
            sender_name=_mailbox_name(sender),
            recipient_email=thread.reply_to_email,
            subject=(item.get("Subject") or thread.subject or "").strip() or "Email Reply",
            body_text=(item.get("RawTextBody") or "").strip(),
            body_html=(item.get("RawHtmlBody") or "").strip(),
            extracted_text=(item.get("ExtractedMarkdownMessage") or "").strip(),
            extracted_signature=(item.get("ExtractedMarkdownSignature") or "").strip(),
            attachments=item.get("Attachments") or [],
            headers=item.get("Headers") or {},
            raw_payload=item,
            received_at=received_at,
        )
        thread.last_message_at = received_at
        thread.last_inbound_at = received_at
        thread.is_open = True
        thread.save(update_fields=["last_message_at", "last_inbound_at", "is_open", "updated_at"])
        summary["ingested"] += 1
    return summary


def fetch_brevo_inbound_attachment(download_token):
    if not settings.BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not configured.")
    request = Request(
        f"https://api.brevo.com/v3/inbound/attachments/{download_token}",
        headers={
            "accept": "application/octet-stream",
            "api-key": settings.BREVO_API_KEY,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return {
                "content": response.read(),
                "content_type": response.headers.get("Content-Type") or "application/octet-stream",
                "content_disposition": response.headers.get("Content-Disposition") or "",
            }
    except HTTPError as exc:
        raise RuntimeError(f"Brevo attachment download failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise RuntimeError(f"Brevo attachment download failed: {exc.reason}.") from exc


@dataclass
class WhatsAppBulkDispatchResult:
    success: bool
    provider: str
    sent_count: int = 0
    failed_count: int = 0
    detail: str = ""
    results: list[WhatsAppSendResult] | None = None


def create_notification(
    *,
    recipient,
    category,
    title,
    message,
    created_by=None,
    action_url="",
    metadata=None,
):
    return Notification.objects.create(
        recipient=recipient,
        category=category,
        title=title,
        message=message,
        created_by=created_by if getattr(created_by, "is_authenticated", False) else None,
        action_url=action_url,
        metadata=metadata or {},
    )


def create_bulk_notifications(
    *,
    recipients: Iterable,
    category,
    title,
    message,
    created_by=None,
    action_url="",
    metadata=None,
):
    notifications = []
    for user in recipients:
        notifications.append(
            create_notification(
                recipient=user,
                category=category,
                title=title,
                message=message,
                created_by=created_by,
                action_url=action_url,
                metadata=metadata,
            )
        )
    return notifications


def send_email_event(
    *,
    to_emails,
    subject,
    body_text,
    actor=None,
    request=None,
    metadata=None,
    body_html="",
    attachments=None,
    enable_replies=False,
    reply_thread_scope=EmailThreadScope.GENERAL,
    existing_thread=None,
):
    provider = get_email_provider()
    emails = _normalized_emails(
        [existing_thread.recipient_email] if existing_thread is not None else to_emails
    )
    emails = _without_guardian_emails_for_cbt(
        emails,
        subject=subject,
        body_text=body_text,
        metadata=metadata,
    )
    if not emails:
        return None
    branded_html = _school_email_html(
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        request=request,
    )
    replies_active = bool(existing_thread is not None or (enable_replies and _email_replies_enabled()))

    if existing_thread is not None:
        try:
            result = provider.send(
                to_emails=[existing_thread.recipient_email],
                subject=_reply_subject(subject),
                body_text=body_text,
                body_html=branded_html,
                attachments=attachments,
                reply_to={
                    "email": existing_thread.reply_to_email,
                    "name": settings.BREVO_SENDER_NAME,
                },
            )
        except Exception as exc:  # noqa: BLE001
            result = EmailSendResult(
                success=False,
                provider=getattr(provider, "provider_name", "unknown"),
                detail=f"{type(exc).__name__}: {exc}",
            )
        if result.success:
            _record_email_thread_outbound_message(
                thread=existing_thread,
                result=result,
                subject=_reply_subject(subject),
                body_text=body_text,
                body_html=branded_html,
                actor=actor,
            )
    elif replies_active:
        sent_count = 0
        failed_count = 0
        single_result = None
        source_event = str((metadata or {}).get("event") or "").strip()
        for email in emails:
            thread = _create_reply_thread(
                recipient_email=email,
                subject=subject,
                actor=actor,
                scope=reply_thread_scope,
                source_event=source_event,
                metadata=metadata,
            )
            try:
                current_result = provider.send(
                    to_emails=[email],
                    subject=subject,
                    body_text=body_text,
                    body_html=branded_html,
                    attachments=attachments,
                    reply_to={
                        "email": thread.reply_to_email,
                        "name": settings.BREVO_SENDER_NAME,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                current_result = EmailSendResult(
                    success=False,
                    provider=getattr(provider, "provider_name", "unknown"),
                    detail=f"{type(exc).__name__}: {exc}",
                )
            if current_result.success:
                sent_count += 1
                _record_email_thread_outbound_message(
                    thread=thread,
                    result=current_result,
                    subject=subject,
                    body_text=body_text,
                    body_html=branded_html,
                    actor=actor,
                )
            else:
                failed_count += 1
                thread.delete()
            single_result = current_result
        result = EmailSendResult(
            success=sent_count > 0 and failed_count == 0,
            provider=getattr(provider, "provider_name", "unknown"),
            detail=f"sent={sent_count} failed={failed_count}",
            external_message_id=(
                getattr(single_result, "external_message_id", "")
                if sent_count == 1 and failed_count == 0 and single_result is not None
                else ""
            ),
        )
    else:
        try:
            result = provider.send(
                to_emails=emails,
                subject=subject,
                body_text=body_text,
                body_html=branded_html,
                attachments=attachments,
            )
        except Exception as exc:  # noqa: BLE001
            result = EmailSendResult(
                success=False,
                provider=getattr(provider, "provider_name", "unknown"),
                detail=f"{type(exc).__name__}: {exc}",
            )
    status = AuditStatus.SUCCESS if result.success else AuditStatus.FAILURE
    log_event(
        category=AuditCategory.SYSTEM,
        event_type="EMAIL_EVENT",
        status=status,
        actor=actor,
        request=request,
        message=f"Email dispatch via {result.provider}.",
        metadata={
            "provider": result.provider,
            "detail": result.detail,
            "to_count": len(emails),
            "to_emails": emails,
            "attachment_count": len(attachments or []),
            "reply_threads_enabled": replies_active,
            "existing_thread_id": str(existing_thread.id) if existing_thread is not None else "",
            **(metadata or {}),
        },
    )
    return result


def send_whatsapp_event(
    *,
    to_numbers,
    body_text,
    actor=None,
    request=None,
    metadata=None,
    preview_url=True,
):
    provider = get_whatsapp_provider()
    numbers = _normalized_phones(to_numbers)
    numbers = _without_guardian_phones_for_cbt(numbers, body_text=body_text, metadata=metadata)
    if not numbers:
        return WhatsAppBulkDispatchResult(
            success=False,
            provider=getattr(provider, "provider_name", "unknown"),
            detail="No WhatsApp numbers available.",
            results=[],
        )

    results = []
    sent_count = 0
    failed_count = 0
    for number in numbers:
        try:
            result = provider.send(
                to_number=number,
                body_text=body_text,
                preview_url=preview_url,
            )
        except Exception as exc:  # noqa: BLE001
            result = WhatsAppSendResult(
                success=False,
                provider=getattr(provider, "provider_name", "unknown"),
                detail=f"{type(exc).__name__}: {exc}",
            )
        results.append(result)
        if result.success:
            sent_count += 1
        else:
            failed_count += 1

    dispatch_result = WhatsAppBulkDispatchResult(
        success=sent_count > 0 and failed_count == 0,
        provider=getattr(provider, "provider_name", "unknown"),
        sent_count=sent_count,
        failed_count=failed_count,
        detail=f"sent={sent_count} failed={failed_count}",
        results=results,
    )
    log_event(
        category=AuditCategory.SYSTEM,
        event_type="WHATSAPP_EVENT",
        status=AuditStatus.SUCCESS if sent_count > 0 else AuditStatus.FAILURE,
        actor=actor,
        request=request,
        message=f"WhatsApp dispatch via {dispatch_result.provider}.",
        metadata={
            "provider": dispatch_result.provider,
            "detail": dispatch_result.detail,
            "to_count": len(numbers),
            "to_numbers": numbers,
            "sent_count": sent_count,
            "failed_count": failed_count,
            **(metadata or {}),
        },
    )
    return dispatch_result


def _birthday_subject(contact):
    if contact.contact_type == BirthdayContactType.STAFF:
        return "Happy Birthday from Notre Dame Girls' Academy"
    return "Birthday Wishes from Notre Dame Girls' Academy"


def _birthday_message(contact, *, catchup=False):
    salutation = contact.full_name or "Esteemed Parent/Guardian"
    if contact.contact_type == BirthdayContactType.STAFF:
        if catchup:
            return (
                f"Dear {salutation},\n\n"
                "Notre Dame Girls' Academy warmly celebrates you, even though your birthday for this year has already passed. "
                "We are grateful for your service, commitment, and contribution to the life of the school.\n\n"
                "May God bless you with good health, peace, joy, and renewed strength in this new year of life.\n\n"
                "With best wishes,\nNotre Dame Girls' Academy, Kuje"
            )
        return (
            f"Dear {salutation},\n\n"
            "Happy birthday from Notre Dame Girls' Academy. We celebrate your life, your service, and your contribution "
            "to the formation of our students.\n\n"
            "May God bless you with joy, good health, peace, and many fruitful years ahead.\n\n"
            "With best wishes,\nNotre Dame Girls' Academy, Kuje"
        )
    if catchup:
        return (
            f"Dear {salutation},\n\n"
            "Notre Dame Girls' Academy warmly sends our birthday wishes to you, even though your birthday for this year "
            "has already passed. We appreciate your partnership, support, and trust in the school.\n\n"
            "May God bless you and your family with peace, joy, good health, and abundant grace.\n\n"
            "With warm regards,\nNotre Dame Girls' Academy, Kuje"
        )
    return (
        f"Dear {salutation},\n\n"
        "Happy birthday from Notre Dame Girls' Academy. We celebrate you today and appreciate your partnership with the school.\n\n"
        "May God bless you with joy, peace, good health, and abundant grace in this new year of life.\n\n"
        "With warm regards,\nNotre Dame Girls' Academy, Kuje"
    )


def dispatch_birthday_wishes(*, target_date=None, catchup=False, actor=None, request=None):
    target_date = target_date or timezone.localdate()
    queryset = BirthdayContact.objects.filter(is_active=True)
    if catchup:
        queryset = queryset.filter(
            birth_month__lt=target_date.month,
        ) | queryset.filter(
            is_active=True,
            birth_month=target_date.month,
            birth_day__lte=target_date.day,
        )
    else:
        queryset = queryset.filter(birth_month=target_date.month, birth_day=target_date.day)
    queryset = queryset.order_by("contact_type", "full_name")

    summary = {"sent": 0, "skipped": 0, "failed": 0, "already_done": 0, "contacts": queryset.count()}
    for contact in queryset:
        existing_dispatch = BirthdayDispatch.objects.filter(
            contact=contact,
            birthday_year=target_date.year,
        ).first()
        if existing_dispatch and existing_dispatch.status == BirthdayDispatchStatus.SENT:
            summary["already_done"] += 1
            continue
        if existing_dispatch:
            existing_dispatch.delete()

        subject = _birthday_subject(contact)
        body_text = _birthday_message(contact, catchup=catchup)
        email_result = None
        whatsapp_result = None
        sent_email = False
        sent_whatsapp = False
        detail_parts = []
        metadata = {
            "event": "BIRTHDAY_WISH",
            "contact_id": contact.id,
            "contact_type": contact.contact_type,
            "catchup": catchup,
        }

        if contact.email:
            email_result = send_email_event(
                to_emails=[contact.email],
                subject=subject,
                body_text=body_text,
                actor=actor,
                request=request,
                metadata=metadata,
            )
            sent_email = bool(email_result and email_result.success)
            detail_parts.append(f"email={getattr(email_result, 'detail', 'not sent')}")

        if contact.phone:
            whatsapp_result = send_whatsapp_event(
                to_numbers=[contact.phone],
                body_text=body_text,
                actor=actor,
                request=request,
                metadata=metadata,
                preview_url=False,
            )
            sent_whatsapp = bool(whatsapp_result and whatsapp_result.sent_count > 0)
            detail_parts.append(f"whatsapp={getattr(whatsapp_result, 'detail', 'not sent')}")

        if not contact.email and not contact.phone:
            summary["skipped"] += 1
            continue
        elif sent_email or sent_whatsapp:
            status = BirthdayDispatchStatus.SENT
            summary["sent"] += 1
        else:
            status = BirthdayDispatchStatus.FAILED
            summary["failed"] += 1

        BirthdayDispatch.objects.create(
            contact=contact,
            birthday_year=target_date.year,
            status=status,
            sent_email=sent_email,
            sent_whatsapp=sent_whatsapp,
            message_subject=subject,
            detail="; ".join(detail_parts),
            metadata=metadata,
        )

    return summary


def notify_results_published(*, compilation, actor, request=None):
    records = compilation.student_records.select_related("student", "student__student_profile").all()
    recipients = [row.student for row in records]
    action_url = "/pdfs/student/reports/"
    title = "Result Published"
    message = (
        f"Your {compilation.term.get_name_display()} result for session "
        f"{compilation.session.name} is now available."
    )
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.RESULTS,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url,
        metadata={
            "compilation_id": str(compilation.id),
            "session": compilation.session.name,
            "term": compilation.term.name,
            "class_code": compilation.academic_class.code,
            "published_at": (compilation.published_at or timezone.now()).isoformat(),
        },
    )

    guardian_emails = []
    for row in records:
        profile = getattr(row.student, "student_profile", None)
        if profile and profile.guardian_email:
            guardian_emails.append(profile.guardian_email)
        elif row.student.email:
            guardian_emails.append(row.student.email)

    if guardian_emails:
        report_url = build_portal_url(request, "student", action_url) if request else action_url
        send_email_event(
            to_emails=guardian_emails,
            subject=f"NDGA Result Published: {compilation.term.get_name_display()}",
            body_text=(
                f"The {compilation.term.get_name_display()} result for "
                f"{compilation.academic_class.code} in the {compilation.session.name} academic session "
                f"is now available.\n\n"
                f"Student portal login: https://student.ndgakuje.org/auth/login/?audience=student\n"
                f"Result link: {report_url}\n\n"
                f"Official report and performance PDFs are available in the portal.\n\n"
                f"Thank you for your continued support."
            ),
            actor=actor,
            request=request,
            metadata={
                "event": "RESULT_PUBLISHED",
                "compilation_id": str(compilation.id),
            },
        )
    return created


def notify_payment_receipt(
    *,
    student,
    receipt_number,
    amount,
    actor,
    request=None,
    message="",
    email_subject="",
    email_body_text="",
    email_body_html="",
    email_attachments=None,
):
    title = "Payment Receipt Issued"
    base_message = (
        message
        or (
            f"This is to confirm that payment has been received and receipt {receipt_number} "
            f"has been issued for the sum of {amount}.\n\n"
            f"You may log in to the student finance portal at any time to review the receipt, "
            f"outstanding balance, and payment history.\n\n"
            f"Thank you for your prompt attention to school payments."
        )
    )
    notification = create_notification(
        recipient=student,
        category=NotificationCategory.PAYMENT,
        title=title,
        message=base_message,
        created_by=actor,
        action_url="/portal/student/finance/",
        metadata={"receipt_number": receipt_number, "amount": str(amount)},
    )
    emails = []
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_email:
        emails.append(profile.guardian_email)
    if student.email:
        emails.append(student.email)
    if emails:
        send_email_event(
            to_emails=emails,
            subject=email_subject or f"NDGA Payment Receipt {receipt_number}",
            body_text=email_body_text or base_message,
            actor=actor,
            request=request,
            metadata={"event": "PAYMENT_RECEIPT", "receipt_number": receipt_number},
            body_html=email_body_html,
            attachments=email_attachments,
        )
    return notification


def notify_election_announcement(*, recipients, title, message, actor, request=None, action_url=""):
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.ELECTION,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url or "/portal/election/",
        metadata={"event": "ELECTION_ANNOUNCEMENT"},
    )
    emails = [user.email for user in recipients if user.email]
    if emails:
        send_email_event(
            to_emails=emails,
            subject=title,
            body_text=message,
            actor=actor,
            request=request,
            metadata={"event": "ELECTION_ANNOUNCEMENT"},
        )
    return created



def _guardian_emails_for_student(student):
    emails = []
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_email:
        emails.append(profile.guardian_email)
    if student.email:
        emails.append(student.email)
    return _normalized_emails(emails)



def notify_attendance_alert(*, student, attendance_date, status, actor, request=None, academic_class=None):
    if status != "ABSENT":
        return None
    title = "Attendance Alert"
    class_code = getattr(academic_class, "code", "your class")
    message = (
        f"This is a quick attendance notice to let you know that {student.get_full_name() or student.username} "
        f"was marked absent on {attendance_date} for {class_code}.\n\n"
        f"If this record needs clarification, please contact the school promptly so we can review it together."
    )
    notification = create_notification(
        recipient=student,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url="/portal/student/attendance/",
        metadata={
            "event": "ATTENDANCE_ALERT",
            "attendance_date": str(attendance_date),
            "class_code": class_code,
        },
    )
    emails = _guardian_emails_for_student(student)
    if emails:
        send_email_event(
            to_emails=emails,
            subject=f"NDGA Attendance Alert: {class_code}",
            body_text=message,
            actor=actor,
            request=request,
            metadata={
                "event": "ATTENDANCE_ALERT",
                "attendance_date": str(attendance_date),
                "student": student.username,
            },
        )
    return notification



def notify_cbt_schedule_published(*, exam, actor, request=None):
    from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment

    class_enrollment_qs = StudentClassEnrollment.objects.filter(
        academic_class_id__in=exam.academic_class.cohort_class_ids(),
        session=exam.session,
        is_active=True,
    ).select_related("student", "student__student_profile")
    student_ids = list(class_enrollment_qs.values_list("student_id", flat=True))
    subject_ids = set(
        StudentSubjectEnrollment.objects.filter(
            student_id__in=student_ids,
            session=exam.session,
            subject=exam.subject,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    recipients = [row.student for row in class_enrollment_qs if (not subject_ids or row.student_id in subject_ids)]
    if not recipients:
        return []
    action_url = "/cbt/exams/available/"
    if exam.schedule_start and exam.schedule_end:
        time_message = (
            f"Opens {exam.schedule_start:%d %b %Y %H:%M} and closes {exam.schedule_end:%d %b %Y %H:%M}."
        )
    else:
        time_message = "Check the CBT portal for the active window."
    title = f"CBT Scheduled: {exam.subject.name}"
    message = f"{exam.title} is scheduled for {exam.academic_class.code}. {time_message}"
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url=action_url,
        metadata={
            "event": "CBT_SCHEDULED",
            "exam_id": str(exam.id),
            "class_code": exam.academic_class.code,
            "subject": exam.subject.name,
        },
    )
    return created



def notify_assignment_deadline(*, academic_class, subject, topic, due_date, actor, request=None, session=None):
    from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment

    enrollment_qs = StudentClassEnrollment.objects.filter(
        academic_class_id__in=academic_class.cohort_class_ids(),
        is_active=True,
    ).select_related("student", "student__student_profile")
    if session is not None:
        enrollment_qs = enrollment_qs.filter(session=session)
    subject_enrollment_qs = StudentSubjectEnrollment.objects.filter(
        student_id__in=enrollment_qs.values_list("student_id", flat=True),
        subject=subject,
        is_active=True,
    )
    if session is not None:
        subject_enrollment_qs = subject_enrollment_qs.filter(session=session)
    subject_student_ids = set(subject_enrollment_qs.values_list("student_id", flat=True))
    recipients = [row.student for row in enrollment_qs if (not subject_student_ids or row.student_id in subject_student_ids)]
    if not recipients:
        return []
    due_label = f" due {due_date}" if due_date else ""
    title = f"Assignment Deadline: {subject.name}"
    message = f"A new assignment on {topic} has been published for {academic_class.code}{due_label}."
    created = create_bulk_notifications(
        recipients=recipients,
        category=NotificationCategory.SYSTEM,
        title=title,
        message=message,
        created_by=actor,
        action_url="/portal/student/learning-hub/",
        metadata={
            "event": "ASSIGNMENT_DEADLINE",
            "class_code": academic_class.code,
            "subject": subject.name,
            "topic": topic,
            "due_date": str(due_date) if due_date else "",
        },
    )
    emails = []
    for student in recipients:
        emails.extend(_guardian_emails_for_student(student))
    if emails:
        portal_url = build_portal_url(request, "student", "/portal/student/learning-hub/") if request else "/portal/student/learning-hub/"
        send_email_event(
            to_emails=emails,
            subject=title,
            body_text=(
                f"A new assignment has been published for {academic_class.code} in {subject.name}.\n\n"
                f"Topic: {topic}\n"
                f"{f'Due date: {due_date}' if due_date else 'Please check the portal for the submission timeline.'}\n\n"
                f"The learning hub can be opened here: {portal_url}"
            ),
            actor=actor,
            request=request,
            metadata={
                "event": "ASSIGNMENT_DEADLINE",
                "class_code": academic_class.code,
                "subject": subject.name,
                "topic": topic,
            },
        )
    return created
