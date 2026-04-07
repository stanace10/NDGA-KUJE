from __future__ import annotations

import json
import hashlib
import hmac
import uuid
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from decimal import Decimal
from urllib import error as url_error
from urllib import request as url_request

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import StudentClassEnrollment
from apps.accounts.models import User
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event, log_finance_transaction
from apps.finance.models import (
    ChargeTargetType,
    Expense,
    FinanceInstitutionProfile,
    FinanceReminderDispatch,
    InventoryAsset,
    Payment,
    PaymentGatewayProvider,
    PaymentGatewayStatus,
    PaymentGatewayTransaction,
    Receipt,
    ReminderStatus,
    ReminderType,
    SalaryRecord,
    SalaryStatus,
    StudentCharge,
)
from apps.notifications.models import NotificationCategory
from apps.notifications.services import create_notification, extract_whatsapp_phones, notify_payment_receipt, send_email_event
from apps.pdfs.services import (
    payload_sha256,
    qr_code_data_uri,
    render_pdf_bytes,
    school_logo_data_uri,
)
from apps.setup_wizard.services import get_setup_state
from apps.tenancy.utils import build_portal_url


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _money_to_minor_units(value):
    return int(_money(value) * 100)


def _month_bucket_date(value):
    """
    Normalize DB month bucket values to a month-start date.

    Depending on DB/backend and field type, TruncMonth may return either
    `date` or `datetime`. We support both without assuming `.date()` exists.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        value = value.date()
    elif hasattr(value, "date") and not isinstance(value, date):
        # Defensive fallback for backend-specific date wrappers.
        value = value.date()
    if not isinstance(value, date):
        return None
    return value.replace(day=1)


def finance_profile():
    return FinanceInstitutionProfile.load()


def finance_bank_details_text():
    profile = finance_profile()
    if not (
        profile.school_bank_name
        and profile.school_account_name
        and profile.school_account_number
    ):
        return ""
    return (
        f"Bank: {profile.school_bank_name}\n"
        f"Account Name: {profile.school_account_name}\n"
        f"Account Number: {profile.school_account_number}"
    )


def _system_request_for_portal(portal_key="student"):
    host = settings.PORTAL_SUBDOMAINS.get(portal_key, settings.PORTAL_SUBDOMAINS.get("landing", "ndgakuje.org"))
    return RequestFactory().get("/", secure=True, HTTP_HOST=host)


def current_academic_window():
    setup_state = get_setup_state()
    return setup_state.current_session, setup_state.current_term


def generate_receipt_number():
    date_part = timezone.localdate().strftime("%Y%m%d")
    prefix = f"NDGA-RCP-{date_part}"
    sequence = 1
    while True:
        candidate = f"{prefix}-{sequence:04d}"
        if not Receipt.objects.filter(receipt_number=candidate).exists():
            return candidate
        sequence += 1


def receipt_signature(*, receipt_number, payload_hash, payment_id):
    message = f"{receipt_number}|{payload_hash}|{payment_id}".encode("utf-8")
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def build_receipt_payload(payment):
    student_profile = getattr(payment.student, "student_profile", None)
    return {
        "payment_id": str(payment.id),
        "student_id": str(payment.student_id),
        "student_name": payment.student.get_full_name() or payment.student.username,
        "student_number": student_profile.student_number if student_profile else payment.student.username,
        "session": payment.session.name if payment.session_id else "",
        "term": payment.term.get_name_display() if payment.term_id else "",
        "amount": str(_money(payment.amount)),
        "payment_method": payment.payment_method,
        "payment_date": payment.payment_date.isoformat() if payment.payment_date else "",
        "gateway_reference": payment.gateway_reference,
        "note": payment.note,
        "created_at": payment.created_at.isoformat() if payment.created_at else "",
    }


def _record_receipt_integrity_alert(
    *,
    receipt,
    actor=None,
    request=None,
    source="",
    stored_hash="",
    current_hash="",
    stored_signature="",
    expected_signature="",
):
    metadata = dict(receipt.metadata or {})
    alert_fingerprint = hashlib.sha256(
        f"{stored_hash}|{current_hash}|{stored_signature}|{expected_signature}".encode("utf-8")
    ).hexdigest()
    if metadata.get("last_integrity_alert_fingerprint") == alert_fingerprint:
        return

    alerts = list(metadata.get("integrity_alerts") or [])
    alerts.append(
        {
            "timestamp": timezone.now().isoformat(),
            "source": source or "unknown",
            "stored_hash": stored_hash,
            "current_hash": current_hash,
            "stored_signature": stored_signature,
            "expected_signature": expected_signature,
        }
    )
    metadata["integrity_alerts"] = alerts[-20:]
    metadata["last_integrity_alert_fingerprint"] = alert_fingerprint
    receipt.metadata = metadata
    receipt.save(update_fields=["metadata", "updated_at"])

    log_event(
        category=AuditCategory.FINANCE,
        event_type="RECEIPT_INTEGRITY_ALERT",
        status=AuditStatus.FAILURE,
        actor=actor,
        request=request,
        message="Receipt integrity mismatch detected. Receipt or payment data changed after issuance.",
        metadata={
            "receipt_id": str(receipt.id),
            "payment_id": str(receipt.payment_id),
            "source": source,
            "stored_hash": stored_hash,
            "current_hash": current_hash,
            "stored_signature": stored_signature,
            "expected_signature": expected_signature,
        },
    )


def evaluate_receipt_integrity(*, receipt, actor=None, request=None, source="", persist=True):
    payload = build_receipt_payload(receipt.payment)
    current_hash = payload_sha256(payload).strip().lower()
    stored_hash = (receipt.payload_hash or "").strip().lower()
    metadata = dict(receipt.metadata or {})
    stored_signature = (metadata.get("signature") or "").strip().lower()
    expected_signature = receipt_signature(
        receipt_number=receipt.receipt_number,
        payload_hash=receipt.payload_hash,
        payment_id=receipt.payment_id,
    ).strip().lower()

    if not stored_signature and stored_hash and current_hash == stored_hash and persist:
        metadata["signature"] = expected_signature
        metadata["signature_version"] = "hmac-sha256-v1"
        metadata.setdefault("payment_payload", payload)
        receipt.metadata = metadata
        receipt.save(update_fields=["metadata", "updated_at"])
        stored_signature = expected_signature

    hash_matches = bool(stored_hash) and hmac.compare_digest(stored_hash, current_hash)
    signature_matches = bool(stored_signature) and hmac.compare_digest(
        stored_signature,
        expected_signature,
    )
    tampered = not (hash_matches and signature_matches)

    if tampered and persist:
        _record_receipt_integrity_alert(
            receipt=receipt,
            actor=actor,
            request=request,
            source=source,
            stored_hash=stored_hash,
            current_hash=current_hash,
            stored_signature=stored_signature,
            expected_signature=expected_signature,
        )

    return {
        "tampered": tampered,
        "hash_matches": hash_matches,
        "signature_matches": signature_matches,
        "stored_hash": stored_hash,
        "current_hash": current_hash,
        "stored_signature": stored_signature,
        "expected_signature": expected_signature,
    }


def build_receipt_dispatch_package(*, payment, receipt, request=None):
    request_for_links = request or _system_request_for_portal("student")
    portal_url = build_portal_url(
        request_for_links,
        "student",
        "/finance/student/overview/",
    )
    session_label = payment.session.name if payment.session_id else "-"
    term_label = payment.term.get_name_display() if payment.term_id else "-"
    student_name = payment.student.get_full_name() or payment.student.username
    profile = getattr(payment.student, "student_profile", None)
    student_number = profile.student_number if profile and profile.student_number else payment.student.username
    amount_text = str(_money(payment.amount))
    subject = f"NDGA Payment Receipt | {receipt.receipt_number}"
    body_text = (
        "Dear Parent/Guardian,\n\n"
        f"This is to confirm that payment has been received for {student_name}.\n\n"
        f"Receipt Number: {receipt.receipt_number}\n"
        f"Admission Number: {student_number}\n"
        f"Session: {session_label}\n"
        f"Term: {term_label}\n"
        f"Amount Paid: {amount_text}\n"
        f"Payment Method: {payment.get_payment_method_display()}\n"
        f"Payment Date: {payment.payment_date}\n\n"
        "The official NDGA receipt PDF is attached to this email.\n"
        f"You may also sign in to the student portal to review payment history: {portal_url}\n\n"
        "Thank you."
    )
    body_html = render_to_string(
        "notifications/email_body_finance_receipt.html",
        {
            "student_name": student_name,
            "student_number": student_number,
            "receipt_number": receipt.receipt_number,
            "amount_text": amount_text,
            "payment_method": payment.get_payment_method_display(),
            "payment_date": payment.payment_date,
            "session_label": session_label,
            "term_label": term_label,
            "portal_url": portal_url,
        },
    )
    attachments = []
    try:
        receipt_pdf = generate_receipt_pdf(
            request=request_for_links,
            receipt=receipt,
            generated_by=payment.received_by or payment.student,
        )
    except Exception:
        receipt_pdf = b""
    if receipt_pdf:
        attachments.append(
            {
                "name": f"NDGA-Receipt-{receipt.receipt_number}.pdf",
                "content": receipt_pdf,
                "mimetype": "application/pdf",
            }
        )
    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        "attachments": attachments,
    }


@transaction.atomic
def record_manual_payment(
    *,
    student,
    session,
    term,
    amount,
    payment_method,
    payment_date,
    received_by,
    gateway_reference="",
    note="",
    request=None,
):
    payment = Payment.objects.create(
        student=student,
        session=session,
        term=term,
        amount=amount,
        payment_method=payment_method,
        gateway_reference=(gateway_reference or "")[:120],
        note=note,
        payment_date=payment_date,
        received_by=received_by if getattr(received_by, "is_authenticated", False) else None,
    )
    payload = build_receipt_payload(payment)
    payload_hash = payload_sha256(payload)
    receipt_number = generate_receipt_number()
    receipt = Receipt.objects.create(
        payment=payment,
        receipt_number=receipt_number,
        payload_hash=payload_hash,
        generated_by=received_by if getattr(received_by, "is_authenticated", False) else None,
        metadata={
            "payment_payload": payload,
            "signature_version": "hmac-sha256-v1",
            "signature": receipt_signature(
                receipt_number=receipt_number,
                payload_hash=payload_hash,
                payment_id=payment.id,
            ),
        },
    )
    log_finance_transaction(
        actor=received_by,
        request=request,
        metadata={
            "action": "PAYMENT_RECORDED",
            "payment_id": str(payment.id),
            "receipt_id": str(receipt.id),
            "student_id": str(student.id),
            "amount": str(_money(amount)),
        },
    )
    profile = finance_profile()
    receipt_message = (
        f"Payment received. Receipt {receipt.receipt_number} "
        f"for amount {_money(amount)} has been issued."
    )
    if profile.include_bank_details_in_messages:
        bank_block = finance_bank_details_text()
        if bank_block:
            receipt_message = f"{receipt_message}\n\nSchool Account Details\n{bank_block}"
    email_package = build_receipt_dispatch_package(
        payment=payment,
        receipt=receipt,
        request=request,
    )

    notify_payment_receipt(
        student=student,
        receipt_number=receipt.receipt_number,
        amount=_money(amount),
        actor=received_by,
        request=request,
        message=receipt_message,
        email_subject=email_package["subject"],
        email_body_text=email_package["body_text"],
        email_body_html=email_package["body_html"],
        email_attachments=email_package["attachments"],
    )
    return payment, receipt


def _gateway_provider():
    return (getattr(settings, "PAYMENT_GATEWAY_PROVIDER", "") or PaymentGatewayProvider.PAYSTACK).strip().upper()


def gateway_provider_label(provider=None):
    selected = (provider or _gateway_provider() or PaymentGatewayProvider.PAYSTACK).strip().upper()
    labels = dict(PaymentGatewayProvider.choices)
    return labels.get(selected, selected.title())


def _payment_gateway_timeout_seconds():
    return int(getattr(settings, "PAYMENT_GATEWAY_TIMEOUT_SECONDS", 12) or 12)


def _paystack_secret_key():
    return (getattr(settings, "PAYSTACK_SECRET_KEY", "") or "").strip()


def _paystack_enabled():
    return bool(_paystack_secret_key())


def _flutterwave_public_key():
    return (getattr(settings, "FLUTTERWAVE_PUBLIC_KEY", "") or "").strip()


def _flutterwave_secret_key():
    return (getattr(settings, "FLUTTERWAVE_SECRET_KEY", "") or "").strip()


def _flutterwave_api_base_url():
    return (getattr(settings, "FLUTTERWAVE_API_BASE_URL", "") or "https://api.flutterwave.com/v3").rstrip("/")


def _flutterwave_enabled():
    return bool(_flutterwave_public_key() and _flutterwave_secret_key())


def _remitta_merchant_id():
    return (getattr(settings, "REMITTA_MERCHANT_ID", "") or "").strip()


def _remitta_service_type_id():
    return (getattr(settings, "REMITTA_SERVICE_TYPE_ID", "") or "").strip()


def _remitta_api_key():
    return (getattr(settings, "REMITTA_API_KEY", "") or "").strip()


def _remitta_checkout_url():
    return (
        getattr(settings, "REMITTA_CHECKOUT_URL", "")
        or "https://login.remita.net/remita/ecomm/finalize.reg"
    ).strip()


def _remitta_verify_url_template():
    return (getattr(settings, "REMITTA_VERIFY_URL_TEMPLATE", "") or "").strip()


def _remitta_enabled():
    return bool(_remitta_merchant_id() and _remitta_service_type_id() and _remitta_api_key() and _remitta_checkout_url())


def configured_gateway_provider_choices():
    choices = []
    if _paystack_enabled():
        choices.append((PaymentGatewayProvider.PAYSTACK, gateway_provider_label(PaymentGatewayProvider.PAYSTACK)))
    if _flutterwave_enabled():
        choices.append((PaymentGatewayProvider.FLUTTERWAVE, gateway_provider_label(PaymentGatewayProvider.FLUTTERWAVE)))
    if _remitta_enabled():
        choices.append((PaymentGatewayProvider.REMITTA, gateway_provider_label(PaymentGatewayProvider.REMITTA)))
    if choices:
        return choices
    return list(PaymentGatewayProvider.choices)


def default_gateway_provider():
    configured = _gateway_provider()
    if configured == PaymentGatewayProvider.PAYSTACK and _paystack_enabled():
        return configured
    if configured == PaymentGatewayProvider.FLUTTERWAVE and _flutterwave_enabled():
        return configured
    if configured == PaymentGatewayProvider.REMITTA and _remitta_enabled():
        return configured
    choices = configured_gateway_provider_choices()
    return choices[0][0] if choices else PaymentGatewayProvider.PAYSTACK


def gateway_is_enabled(provider=None):
    selected = (provider or default_gateway_provider() or PaymentGatewayProvider.PAYSTACK).strip().upper()
    if selected == PaymentGatewayProvider.PAYSTACK:
        return _paystack_enabled()
    if selected == PaymentGatewayProvider.FLUTTERWAVE:
        return _flutterwave_enabled()
    if selected == PaymentGatewayProvider.REMITTA:
        return _remitta_enabled()
    return False


def _paystack_api_request(*, path, method="GET", payload=None):
    secret_key = _paystack_secret_key()
    if not secret_key:
        raise ValidationError("Paystack secret key is not configured.")
    base_url = (getattr(settings, "PAYSTACK_API_BASE_URL", "") or "https://api.paystack.co").rstrip("/")
    url = f"{base_url}{path}"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(url, method=method.upper(), data=body, headers=headers)
    timeout_seconds = _payment_gateway_timeout_seconds()
    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValidationError(f"Gateway request failed ({exc.code}): {detail or exc.reason}") from exc
    except url_error.URLError as exc:
        raise ValidationError(f"Gateway network error: {exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid gateway response format.") from exc
    return parsed


def _flutterwave_api_request(*, path, method="GET", payload=None):
    secret_key = _flutterwave_secret_key()
    if not secret_key:
        raise ValidationError("Flutterwave secret key is not configured.")
    url = f"{_flutterwave_api_base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(url, method=method.upper(), data=body, headers=headers)
    timeout_seconds = _payment_gateway_timeout_seconds()
    try:
        with url_request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValidationError(f"Gateway request failed ({exc.code}): {detail or exc.reason}") from exc
    except url_error.URLError as exc:
        raise ValidationError(f"Gateway network error: {exc.reason}") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid gateway response format.") from exc
    return parsed


def _gateway_callback_url(request=None):
    configured = (getattr(settings, "PAYMENT_GATEWAY_CALLBACK_URL", "") or "").strip()
    if configured:
        return configured
    if request is not None:
        return build_portal_url(request, "landing", reverse("finance:gateway-callback"))
    return ""


def _guardian_emails_for_student(student):
    emails = []
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_email:
        emails.append(profile.guardian_email)
    if student.email:
        emails.append(student.email)
    # Many NDGA accounts use email-like usernames even when email field is blank.
    username = (student.username or "").strip()
    if "@" in username and "." in username:
        emails.append(username)
    return list(dict.fromkeys(email.strip().lower() for email in emails if email))


def _guardian_phone_for_student(student):
    profile = getattr(student, "student_profile", None)
    if profile and profile.guardian_phone:
        numbers = extract_whatsapp_phones(profile.guardian_phone)
        return numbers[0] if numbers else ""
    return ""


def _student_full_name(student):
    return (student.get_full_name() or student.username or "NDGA Student").strip()


def resolve_payment_plan_amount(*, overview, payment_plan, fee_item="", percentage=None, custom_amount=None):
    payment_plan = (payment_plan or "FULL").strip().upper()
    total_outstanding = _money((overview or {}).get("total_outstanding"))
    if total_outstanding <= Decimal("0.00"):
        raise ValidationError("There is no outstanding balance to pay.")

    if payment_plan == "FULL":
        return total_outstanding, {
            "payment_plan": "FULL",
            "label": "Full outstanding bundle",
        }

    if payment_plan == "FEE_ITEM":
        selected_item = (fee_item or "").strip()
        if not selected_item:
            raise ValidationError("Select the fee item to pay.")
        category_rows = (overview or {}).get("category_rows") or []
        match = next(
            (row for row in category_rows if (row.get("category") or "").strip().lower() == selected_item.lower()),
            None,
        )
        if not match:
            raise ValidationError("Selected fee item could not be found.")
        outstanding = _money(match.get("outstanding"))
        if outstanding <= Decimal("0.00"):
            raise ValidationError("Selected fee item has no outstanding balance.")
        return outstanding, {
            "payment_plan": "FEE_ITEM",
            "fee_item": match.get("category"),
            "label": f"{match.get('category')} only",
        }

    if payment_plan == "PERCENTAGE":
        if percentage in {None, ""}:
            raise ValidationError("Select the percentage payment to apply.")
        percentage_value = int(percentage)
        if percentage_value not in {25, 50, 75, 100}:
            raise ValidationError("Unsupported percentage payment option.")
        amount = _money(total_outstanding * Decimal(percentage_value) / Decimal("100"))
        if amount <= Decimal("0.00"):
            raise ValidationError("Computed percentage payment is too small.")
        return amount, {
            "payment_plan": "PERCENTAGE",
            "percentage": percentage_value,
            "label": f"{percentage_value}% of outstanding balance",
        }

    amount = _money(custom_amount)
    if amount <= Decimal("0.00"):
        raise ValidationError("Enter a valid payment amount.")
    if amount > total_outstanding:
        raise ValidationError("Custom amount cannot be more than the outstanding balance.")
    return amount, {
        "payment_plan": "CUSTOM",
        "label": "Custom amount",
    }


def _remitta_amount_string(value):
    return f"{_money(value):.2f}"


def _remitta_hash(*, reference, amount):
    signature = f"{_remitta_merchant_id()}{_remitta_service_type_id()}{reference}{amount}{_remitta_api_key()}"
    return hashlib.sha512(signature.encode("utf-8")).hexdigest()


def _remitta_launch_url(*, request, reference):
    launch_path = reverse("finance:gateway-remitta-launch", kwargs={"reference": reference})
    if request is not None:
        return build_portal_url(request, "landing", launch_path)
    return launch_path


def _remitta_checkout_payload(*, transaction_row, student):
    amount = _remitta_amount_string(transaction_row.amount)
    description = (
        f"NDGA fees for {_student_full_name(student)} "
        f"({transaction_row.session.name}{f' {transaction_row.term.get_name_display()}' if transaction_row.term_id else ''})"
    )
    payer_phone = _guardian_phone_for_student(student)
    payer_emails = _guardian_emails_for_student(student)
    payer_email = payer_emails[0] if payer_emails else ""
    return {
        "merchantId": _remitta_merchant_id(),
        "serviceTypeId": _remitta_service_type_id(),
        "amount": amount,
        "orderId": transaction_row.reference,
        "payerName": _student_full_name(student),
        "payerEmail": payer_email,
        "payerPhone": payer_phone,
        "description": description[:180],
        "responseurl": transaction_row.callback_url,
        "hash": _remitta_hash(reference=transaction_row.reference, amount=amount),
    }


def _flutterwave_checkout_payload(*, transaction_row, student):
    payer_phone = _guardian_phone_for_student(student)
    payer_emails = _guardian_emails_for_student(student)
    payer_email = payer_emails[0] if payer_emails else ""
    return {
        "tx_ref": transaction_row.reference,
        "amount": str(_money(transaction_row.amount)),
        "currency": "NGN",
        "redirect_url": transaction_row.callback_url,
        "customer": {
            "email": payer_email,
            "name": _student_full_name(student),
            "phonenumber": payer_phone,
        },
        "customizations": {
            "title": "Notre Dame Girls Academy",
            "description": f"NDGA fee payment for {_student_full_name(student)}",
        },
        "meta": {
            "student_id": str(transaction_row.student_id),
            "session_id": str(transaction_row.session_id),
            "term_id": str(transaction_row.term_id or ""),
            "transaction_id": str(transaction_row.id),
        },
    }


def remitta_launch_context(*, gateway_transaction):
    if gateway_transaction.provider != PaymentGatewayProvider.REMITTA:
        raise ValidationError("Remitta launch is only available for Remitta transactions.")
    fields = dict((gateway_transaction.metadata or {}).get("remitta_checkout_payload") or {})
    if not fields:
        raise ValidationError("Remitta checkout payload is missing.")
    return {
        "action_url": _remitta_checkout_url(),
        "fields": fields,
        "reference": gateway_transaction.reference,
    }


def _remitta_verify_request(*, gateway_transaction):
    template = _remitta_verify_url_template()
    if not template:
        return None
    url = template.format(
        reference=gateway_transaction.reference,
        order_id=gateway_transaction.reference,
        rrr=gateway_transaction.gateway_reference,
        merchant_id=_remitta_merchant_id(),
        api_key=_remitta_api_key(),
    )
    request = url_request.Request(url, method="GET")
    try:
        with url_request.urlopen(request, timeout=_payment_gateway_timeout_seconds()) as response:
            raw = response.read().decode("utf-8")
    except url_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise ValidationError(f"Remitta verification failed ({exc.code}): {detail or exc.reason}") from exc
    except url_error.URLError as exc:
        raise ValidationError(f"Remitta network error: {exc.reason}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _remitta_amount_matches(payload, expected_amount):
    candidates = [
        payload.get("amount"),
        (payload.get("data") or {}).get("amount") if isinstance(payload.get("data"), dict) else None,
    ]
    expected = _money(expected_amount)
    for value in candidates:
        try:
            if _money(value) == expected:
                return True
        except Exception:  # noqa: BLE001
            continue
    return not any(value is not None for value in candidates)


def _remitta_success_payload(payload):
    normalized_candidates = []
    for value in [
        payload.get("status"),
        payload.get("message"),
        payload.get("statuscode"),
        payload.get("statusCode"),
        payload.get("responseCode"),
        payload.get("responsecode"),
        (payload.get("data") or {}).get("status") if isinstance(payload.get("data"), dict) else None,
        (payload.get("data") or {}).get("statusMessage") if isinstance(payload.get("data"), dict) else None,
    ]:
        if value is None:
            continue
        normalized_candidates.append(str(value).strip().lower())
    success_codes = {"00", "01", "success", "successful", "approved", "completed", "payment successful"}
    return any(
        candidate in success_codes
        or "success" in candidate
        or "approved" in candidate
        or "completed" in candidate
        for candidate in normalized_candidates
    )


@transaction.atomic
def initialize_gateway_payment_transaction(
    *,
    student,
    session,
    term,
    amount,
    initiated_by=None,
    request=None,
    provider=None,
    auto_email_link=True,
):
    selected_provider = (provider or default_gateway_provider() or PaymentGatewayProvider.PAYSTACK).strip().upper()
    if selected_provider not in dict(PaymentGatewayProvider.choices):
        raise ValidationError("Unsupported payment gateway provider.")
    if not gateway_is_enabled(selected_provider):
        raise ValidationError(f"{gateway_provider_label(selected_provider)} is not configured.")

    reference = f"NDGA-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:10].upper()}"
    callback_url = _gateway_callback_url(request)
    customer_email = _guardian_emails_for_student(student)
    email = customer_email[0] if customer_email else None
    if selected_provider == PaymentGatewayProvider.PAYSTACK and not email:
        raise ValidationError("Student or guardian email is required for gateway initialization.")
    if selected_provider == PaymentGatewayProvider.FLUTTERWAVE and not email:
        raise ValidationError("Student or guardian email is required for gateway initialization.")

    transaction_row = PaymentGatewayTransaction.objects.create(
        reference=reference,
        provider=selected_provider,
        status=PaymentGatewayStatus.PENDING,
        student=student,
        session=session,
        term=term,
        amount=_money(amount),
        callback_url=callback_url,
        initiated_by=initiated_by if getattr(initiated_by, "is_authenticated", False) else None,
        metadata={
            "init_source": "BURSAR" if initiated_by and initiated_by.has_role("BURSAR") else "STUDENT_OR_SYSTEM",
            "auto_email_link": bool(auto_email_link),
        },
    )

    if selected_provider == PaymentGatewayProvider.PAYSTACK:
        payload = {
            "email": email,
            "amount": _money_to_minor_units(transaction_row.amount),
            "reference": reference,
            "callback_url": callback_url,
            "metadata": {
                "student_id": transaction_row.student_id,
                "session_id": transaction_row.session_id,
                "term_id": transaction_row.term_id,
                "transaction_id": transaction_row.id,
            },
        }
        gateway_response = _paystack_api_request(
            path="/transaction/initialize",
            method="POST",
            payload=payload,
        )
        if not gateway_response.get("status"):
            message = gateway_response.get("message") or "Gateway initialization failed."
            transaction_row.status = PaymentGatewayStatus.FAILED
            transaction_row.failure_reason = message
            transaction_row.metadata = {
                **transaction_row.metadata,
                "initialize_payload": payload,
                "initialize_response": gateway_response,
            }
            transaction_row.save(update_fields=["status", "failure_reason", "metadata", "updated_at"])
            raise ValidationError(message)

        data = gateway_response.get("data") or {}
        transaction_row.status = PaymentGatewayStatus.INITIALIZED
        transaction_row.initialized_at = timezone.now()
        transaction_row.authorization_url = (data.get("authorization_url") or "")[:500]
        transaction_row.gateway_reference = (data.get("reference") or reference)[:180]
        transaction_row.metadata = {
            **transaction_row.metadata,
            "initialize_payload": payload,
            "initialize_response": gateway_response,
            "access_code": data.get("access_code", ""),
        }
        transaction_row.save(
            update_fields=[
                "status",
                "initialized_at",
                "authorization_url",
                "gateway_reference",
                "metadata",
                "updated_at",
            ]
        )
    elif selected_provider == PaymentGatewayProvider.FLUTTERWAVE:
        payload = _flutterwave_checkout_payload(transaction_row=transaction_row, student=student)
        gateway_response = _flutterwave_api_request(
            path="/payments",
            method="POST",
            payload=payload,
        )
        if gateway_response.get("status") != "success":
            message = gateway_response.get("message") or "Gateway initialization failed."
            transaction_row.status = PaymentGatewayStatus.FAILED
            transaction_row.failure_reason = message
            transaction_row.metadata = {
                **transaction_row.metadata,
                "initialize_payload": payload,
                "initialize_response": gateway_response,
            }
            transaction_row.save(update_fields=["status", "failure_reason", "metadata", "updated_at"])
            raise ValidationError(message)
        data = gateway_response.get("data") or {}
        transaction_row.status = PaymentGatewayStatus.INITIALIZED
        transaction_row.initialized_at = timezone.now()
        transaction_row.authorization_url = (data.get("link") or "")[:500]
        transaction_row.gateway_reference = (data.get("flw_ref") or reference)[:180]
        transaction_row.metadata = {
            **transaction_row.metadata,
            "initialize_payload": payload,
            "initialize_response": gateway_response,
            "provider_label": gateway_provider_label(selected_provider),
        }
        transaction_row.save(
            update_fields=[
                "status",
                "initialized_at",
                "authorization_url",
                "gateway_reference",
                "metadata",
                "updated_at",
            ]
        )
    else:
        remitta_payload = _remitta_checkout_payload(transaction_row=transaction_row, student=student)
        transaction_row.status = PaymentGatewayStatus.INITIALIZED
        transaction_row.initialized_at = timezone.now()
        transaction_row.authorization_url = _remitta_launch_url(request=request, reference=transaction_row.reference)[:500]
        transaction_row.gateway_reference = reference
        transaction_row.metadata = {
            **transaction_row.metadata,
            "initialize_payload": remitta_payload,
            "remitta_checkout_payload": remitta_payload,
            "provider_label": gateway_provider_label(selected_provider),
        }
        transaction_row.save(
            update_fields=[
                "status",
                "initialized_at",
                "authorization_url",
                "gateway_reference",
                "metadata",
                "updated_at",
            ]
        )

    if auto_email_link:
        payment_link = transaction_row.authorization_url
        if payment_link:
            send_email_event(
                to_emails=_guardian_emails_for_student(student),
                subject=f"NDGA {gateway_provider_label(selected_provider)} Payment Link",
                body_text=(
                    f"Use this secure payment link to pay NDGA fees.\n\n"
                    f"Reference: {transaction_row.reference}\n"
                    f"Amount: {transaction_row.amount}\n"
                    f"Link: {payment_link}"
                ),
                actor=initiated_by,
                request=request,
                metadata={"event": "GATEWAY_PAYMENT_LINK", "reference": transaction_row.reference},
            )
            create_notification(
                recipient=student,
                category=NotificationCategory.PAYMENT,
                title="Online Payment Link Generated",
                message=(
                    f"Payment link generated for amount {transaction_row.amount}. "
                    f"Reference: {transaction_row.reference}."
                ),
                created_by=initiated_by,
                action_url="/finance/student/overview/",
                metadata={"reference": transaction_row.reference, "amount": str(transaction_row.amount)},
            )
    return transaction_row


@transaction.atomic
def verify_gateway_payment_transaction(*, gateway_transaction, actor=None, request=None):
    transaction_row = (
        PaymentGatewayTransaction.objects.select_for_update()
        .select_related("student", "session")
        .get(pk=gateway_transaction.pk)
    )

    if transaction_row.payment_id and transaction_row.status == PaymentGatewayStatus.PAID:
        return transaction_row, transaction_row.payment, getattr(transaction_row.payment, "receipt", None)

    transaction_row.verified_at = timezone.now()
    paid_ok = False
    amount_ok = False
    verification = {}

    if transaction_row.provider == PaymentGatewayProvider.PAYSTACK:
        verification = _paystack_api_request(
            path=f"/transaction/verify/{transaction_row.reference}",
            method="GET",
        )
        data = verification.get("data") or {}
        paid_ok = bool(verification.get("status")) and (data.get("status") == "success")
        amount_minor = int(data.get("amount") or 0)
        expected_minor = _money_to_minor_units(transaction_row.amount)
        amount_ok = amount_minor == expected_minor
    elif transaction_row.provider == PaymentGatewayProvider.REMITTA:
        callback_state = dict((transaction_row.metadata or {}).get("callback_params") or {})
        if callback_state.get("rrr") and not transaction_row.gateway_reference:
            transaction_row.gateway_reference = str(callback_state.get("rrr"))[:180]
        verification = _remitta_verify_request(gateway_transaction=transaction_row) or callback_state
        paid_ok = _remitta_success_payload(verification) or _remitta_success_payload(callback_state)
        amount_ok = _remitta_amount_matches(verification, transaction_row.amount)
    elif transaction_row.provider == PaymentGatewayProvider.FLUTTERWAVE:
        verification = _flutterwave_api_request(
            path=f"/transactions/verify_by_reference?tx_ref={transaction_row.reference}",
            method="GET",
        )
        data = verification.get("data") or {}
        paid_ok = (verification.get("status") == "success") and str(data.get("status", "")).lower() == "successful"
        amount_ok = _money(data.get("amount")) == _money(transaction_row.amount)
    else:
        raise ValidationError("Unsupported payment gateway provider.")

    transaction_row.metadata = {**transaction_row.metadata, "verify_response": verification}

    if not paid_ok or not amount_ok:
        transaction_row.status = PaymentGatewayStatus.FAILED
        if not paid_ok:
            transaction_row.failure_reason = (
                verification.get("gateway_response")
                or verification.get("status")
                or verification.get("message")
                or "Gateway verification failed."
            )
        else:
            transaction_row.failure_reason = "Amount mismatch during gateway verification."
        transaction_row.save(update_fields=["status", "failure_reason", "verified_at", "metadata", "updated_at"])
        raise ValidationError(transaction_row.failure_reason)

    payment = transaction_row.payment
    receipt = getattr(payment, "receipt", None) if payment else None
    if payment is None:
        payment, receipt = record_manual_payment(
            student=transaction_row.student,
            session=transaction_row.session,
            term=transaction_row.term,
            amount=transaction_row.amount,
            payment_method="GATEWAY",
            payment_date=timezone.localdate(),
            received_by=actor,
            gateway_reference=transaction_row.reference,
            note="Recorded from live gateway verification.",
            request=request,
        )
    transaction_row.status = PaymentGatewayStatus.PAID
    transaction_row.paid_at = timezone.now()
    transaction_row.payment = payment
    transaction_row.failure_reason = ""
    transaction_row.save(
        update_fields=[
            "status",
            "verified_at",
            "paid_at",
            "payment",
            "failure_reason",
            "metadata",
            "updated_at",
        ]
    )
    return transaction_row, payment, receipt


def verify_gateway_payment_by_reference(*, reference, actor=None, request=None):
    transaction_row = PaymentGatewayTransaction.objects.filter(reference=(reference or "").strip()).first()
    if not transaction_row:
        raise ValidationError("Unknown gateway reference.")
    return verify_gateway_payment_transaction(
        gateway_transaction=transaction_row,
        actor=actor,
        request=request,
    )


def dispatch_scheduled_fee_reminders(*, run_date=None, days_ahead=3, actor=None, request=None):
    run_date = run_date or timezone.localdate()
    days_ahead = max(int(days_ahead or 0), 1)
    session, term = current_academic_window()
    if session is None:
        return {"sent": 0, "skipped": 0, "failed": 0, "session_missing": True}

    student_ids = list(
        StudentClassEnrollment.objects.filter(session=session, is_active=True).values_list("student_id", flat=True)
    )
    students = (
        User.objects.filter(id__in=student_ids, primary_role__code="STUDENT")
        .select_related("student_profile")
        .order_by("username")
    )
    sent = 0
    skipped = 0
    failed = 0
    for student in students:
        overview = student_finance_overview(student=student, session=session, term=term)
        outstanding = _money(overview["total_outstanding"])
        if outstanding <= Decimal("0.00"):
            skipped += 1
            continue
        charge_rows = [
            row
            for row in overview["charge_rows"]
            if row.outstanding > Decimal("0.00") and row.due_date
        ]
        if not charge_rows:
            skipped += 1
            continue
        nearest_due = min(row.due_date for row in charge_rows)
        if nearest_due < run_date:
            reminder_type = ReminderType.OVERDUE
        elif nearest_due <= (run_date + timedelta(days=days_ahead)):
            reminder_type = ReminderType.UPCOMING
        else:
            skipped += 1
            continue

        dispatch_row, created = FinanceReminderDispatch.objects.get_or_create(
            student=student,
            session=session,
            term=term,
            reminder_date=run_date,
            reminder_type=reminder_type,
            defaults={
                "status": ReminderStatus.SENT,
                "due_date": nearest_due,
                "outstanding_amount": outstanding,
                "charge_ids": [row.charge_id for row in charge_rows],
                "sent_by": actor if getattr(actor, "is_authenticated", False) else None,
            },
        )
        if not created:
            skipped += 1
            continue

        if reminder_type == ReminderType.OVERDUE:
            title = "Overdue School Fee Reminder"
            body = (
                f"You have overdue fee items. Outstanding amount: {outstanding}. "
                f"Nearest due date was {nearest_due}."
            )
        else:
            title = "Upcoming School Fee Reminder"
            body = (
                f"You have fee items due soon. Outstanding amount: {outstanding}. "
                f"Nearest due date is {nearest_due}."
            )
        try:
            create_notification(
                recipient=student,
                category=NotificationCategory.PAYMENT,
                title=title,
                message=body,
                created_by=actor if getattr(actor, "is_authenticated", False) else None,
                action_url="/finance/student/overview/",
                metadata={
                    "event": "SCHEDULED_FEE_REMINDER",
                    "reminder_type": reminder_type,
                    "outstanding_amount": str(outstanding),
                    "due_date": nearest_due.isoformat(),
                },
            )
            send_email_event(
                to_emails=_guardian_emails_for_student(student),
                subject=f"NDGA {title}",
                body_text=body,
                actor=actor,
                request=request,
                metadata={
                    "event": "SCHEDULED_FEE_REMINDER",
                    "reminder_type": reminder_type,
                    "student_id": student.id,
                },
            )
            dispatch_row.status = ReminderStatus.SENT
            dispatch_row.save(update_fields=["status", "updated_at"])
            sent += 1
        except Exception:  # noqa: BLE001
            dispatch_row.status = ReminderStatus.FAILED
            dispatch_row.save(update_fields=["status", "updated_at"])
            failed += 1

    return {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "session_missing": False,
    }


def generate_receipt_pdf(*, request, receipt, generated_by):
    integrity = evaluate_receipt_integrity(
        receipt=receipt,
        actor=generated_by,
        request=request,
        source="RECEIPT_PDF_GENERATION",
    )
    if integrity["tampered"]:
        raise ValidationError(
            "Receipt integrity check failed. This payment record changed after receipt issuance."
        )

    payment = receipt.payment
    student_profile = getattr(payment.student, "student_profile", None)
    profile = finance_profile()
    verification_url = build_portal_url(
        request,
        "landing",
        reverse("finance:receipt-verify", kwargs={"receipt_id": receipt.id}),
        query={"hash": receipt.payload_hash},
    )
    context = {
        "receipt": receipt,
        "payment": payment,
        "student_profile": student_profile,
        "generated_at": timezone.now(),
        "logo_data_uri": school_logo_data_uri(),
        "watermark_data_uri": school_logo_data_uri(),
        "verification_url": verification_url,
        "verification_qr_data_uri": qr_code_data_uri(verification_url),
        "finance_profile": profile,
        "show_bank_on_receipt": bool(
            profile.show_on_receipt_pdf
            and profile.school_bank_name
            and profile.school_account_name
            and profile.school_account_number
        ),
    }
    pdf_bytes = render_pdf_bytes(
        template_name="finance/receipt_pdf.html",
        context=context,
    )
    log_finance_transaction(
        actor=generated_by,
        request=request,
        metadata={
            "action": "RECEIPT_PDF_GENERATED",
            "receipt_id": str(receipt.id),
            "payment_id": str(payment.id),
        },
    )
    return pdf_bytes


@dataclass
class DebtorRow:
    student_id: int
    student_username: str
    student_name: str
    student_number: str
    total_due: Decimal
    total_paid: Decimal
    outstanding: Decimal


@dataclass
class StudentChargeStatusRow:
    charge_id: int
    item_name: str
    description: str
    amount: Decimal
    paid_applied: Decimal
    outstanding: Decimal
    status: str
    due_date: object
    target_label: str


def debtor_rows(*, session, term=None):
    charges_qs = StudentCharge.objects.filter(is_active=True, session=session)
    if term is not None:
        charges_qs = charges_qs.filter(term__in=[term, None])

    payments_qs = Payment.objects.filter(is_void=False, session=session)
    if term is not None:
        payments_qs = payments_qs.filter(term__in=[term, None])

    student_charge_map = {}
    for row in charges_qs.filter(student__isnull=False).values("student_id").annotate(total=Sum("amount")):
        student_charge_map[int(row["student_id"])] = _money(row["total"])

    class_charge_rows = list(
        charges_qs.filter(academic_class__isnull=False).values("academic_class_id").annotate(total=Sum("amount"))
    )
    class_charge_map = {
        int(row["academic_class_id"]): _money(row["total"])
        for row in class_charge_rows
    }

    enrollment_qs = StudentClassEnrollment.objects.filter(session=session, is_active=True).select_related(
        "student",
        "academic_class",
    )
    student_class_map = {row.student_id: row.academic_class_id for row in enrollment_qs}

    payment_map = {}
    for row in payments_qs.values("student_id").annotate(total=Sum("amount")):
        payment_map[int(row["student_id"])] = _money(row["total"])

    student_ids = set(student_charge_map.keys()) | set(payment_map.keys()) | set(student_class_map.keys())
    students = {
        row.id: row
        for row in User.objects.filter(id__in=student_ids).select_related("student_profile")
    }
    rows = []
    for student_id in student_ids:
        user = students.get(student_id)
        if user is None:
            continue
        due_student = student_charge_map.get(student_id, Decimal("0.00"))
        class_id = student_class_map.get(student_id)
        due_class = class_charge_map.get(class_id, Decimal("0.00")) if class_id else Decimal("0.00")
        total_due = _money(due_student + due_class)
        total_paid = payment_map.get(student_id, Decimal("0.00"))
        outstanding = _money(total_due - total_paid)
        if outstanding <= 0:
            continue
        profile = getattr(user, "student_profile", None)
        rows.append(
            DebtorRow(
                student_id=user.id,
                student_username=user.username,
                student_name=user.get_full_name() or user.username,
                student_number=profile.student_number if profile else user.username,
                total_due=total_due,
                total_paid=_money(total_paid),
                outstanding=outstanding,
            )
        )
    rows.sort(key=lambda item: item.outstanding, reverse=True)
    return rows


def student_finance_overview(*, student, session, term=None):
    class_ids = list(
        StudentClassEnrollment.objects.filter(
            student=student,
            session=session,
            is_active=True,
        ).values_list("academic_class_id", flat=True)
    )

    charge_filter = (
        Q(target_type=ChargeTargetType.STUDENT, student=student)
        | Q(target_type=ChargeTargetType.CLASS, academic_class_id__in=class_ids)
    )
    charges_qs = StudentCharge.objects.filter(
        session=session,
        is_active=True,
    ).filter(charge_filter)

    if term is not None:
        charges_qs = charges_qs.filter(term__in=[term, None])

    charges = list(
        charges_qs.select_related("term", "academic_class")
        .order_by("due_date", "created_at", "id")
    )

    payments_qs = Payment.objects.filter(
        student=student,
        session=session,
        is_void=False,
    )
    if term is not None:
        payments_qs = payments_qs.filter(term__in=[term, None])

    payment_pool = _money(payments_qs.aggregate(total=Sum("amount"))["total"])

    charge_rows = []
    category_map = {}
    for charge in charges:
        charge_amount = _money(charge.amount)
        applied = _money(min(payment_pool, charge_amount))
        payment_pool = _money(payment_pool - applied)
        outstanding = _money(charge_amount - applied)
        if outstanding <= Decimal("0.00"):
            status = "PAID"
        elif applied > Decimal("0.00"):
            status = "PARTIAL"
        else:
            status = "OWING"

        target_label = "Personal"
        if charge.target_type == ChargeTargetType.CLASS:
            target_label = f"Class ({charge.academic_class.code})" if charge.academic_class_id else "Class"

        row = StudentChargeStatusRow(
            charge_id=charge.id,
            item_name=charge.item_name,
            description=charge.description,
            amount=charge_amount,
            paid_applied=applied,
            outstanding=outstanding,
            status=status,
            due_date=charge.due_date,
            target_label=target_label,
        )
        charge_rows.append(row)

        key = charge.item_name.strip() or "Other"
        category_row = category_map.setdefault(
            key,
            {
                "category": key,
                "charged": Decimal("0.00"),
                "paid": Decimal("0.00"),
                "outstanding": Decimal("0.00"),
                "items": 0,
            },
        )
        category_row["charged"] = _money(category_row["charged"] + charge_amount)
        category_row["paid"] = _money(category_row["paid"] + applied)
        category_row["outstanding"] = _money(category_row["outstanding"] + outstanding)
        category_row["items"] += 1

    total_charged = _money(sum((row.amount for row in charge_rows), Decimal("0.00")))
    total_paid_applied = _money(sum((row.paid_applied for row in charge_rows), Decimal("0.00")))
    total_outstanding = _money(sum((row.outstanding for row in charge_rows), Decimal("0.00")))
    total_payments = _money(payments_qs.aggregate(total=Sum("amount"))["total"])
    unallocated_credit = _money(max(total_payments - total_paid_applied, Decimal("0.00")))

    category_rows = sorted(
        category_map.values(),
        key=lambda row: (row["outstanding"], row["category"]),
        reverse=True,
    )

    return {
        "charge_rows": charge_rows,
        "category_rows": category_rows,
        "total_charged": total_charged,
        "total_paid_applied": total_paid_applied,
        "total_outstanding": total_outstanding,
        "total_payments": total_payments,
        "unallocated_credit": unallocated_credit,
    }


def monthly_cashflow_series(*, months=6):
    months = max(int(months or 0), 1)
    today = timezone.localdate().replace(day=1)
    month_points = []
    cursor = today
    for _ in range(months):
        month_points.append(cursor)
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    month_points = sorted(month_points)

    inflow_rows = (
        Payment.objects.filter(is_void=False, payment_date__gte=month_points[0])
        .annotate(month=TruncMonth("payment_date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    out_expense_rows = (
        Expense.objects.filter(is_active=True, expense_date__gte=month_points[0])
        .annotate(month=TruncMonth("expense_date"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )
    salary_rows = (
        SalaryRecord.objects.filter(
            is_active=True,
            status=SalaryStatus.PAID,
            month__gte=month_points[0],
        )
        .annotate(month_bucket=TruncMonth("month"))
        .values("month_bucket")
        .annotate(total=Sum("amount"))
        .order_by("month_bucket")
    )

    inflow_map = {}
    for row in inflow_rows:
        month_key = _month_bucket_date(row.get("month"))
        if month_key is not None:
            inflow_map[month_key] = _money(row.get("total"))

    expense_map = {}
    for row in out_expense_rows:
        month_key = _month_bucket_date(row.get("month"))
        if month_key is not None:
            expense_map[month_key] = _money(row.get("total"))

    salary_map = {}
    for row in salary_rows:
        month_key = _month_bucket_date(row.get("month_bucket"))
        if month_key is not None:
            salary_map[month_key] = _money(row.get("total"))

    data = []
    for point in month_points:
        inflow = inflow_map.get(point, Decimal("0.00"))
        outflow = _money(expense_map.get(point, Decimal("0.00")) + salary_map.get(point, Decimal("0.00")))
        data.append(
            {
                "month": point,
                "label": point.strftime("%b %Y"),
                "inflow": inflow,
                "outflow": outflow,
            }
        )
    return data


def finance_summary_metrics(*, session, term=None):
    charges_qs = StudentCharge.objects.filter(is_active=True, session=session)
    payments_qs = Payment.objects.filter(is_void=False, session=session)
    if term is not None:
        charges_qs = charges_qs.filter(term__in=[term, None])
        payments_qs = payments_qs.filter(term__in=[term, None])

    total_charges = _money(charges_qs.aggregate(total=Sum("amount"))["total"])
    total_payments = _money(payments_qs.aggregate(total=Sum("amount"))["total"])
    total_expenses = _money(Expense.objects.filter(is_active=True).aggregate(total=Sum("amount"))["total"])
    total_salaries_paid = _money(
        SalaryRecord.objects.filter(is_active=True, status=SalaryStatus.PAID).aggregate(total=Sum("amount"))["total"]
    )
    active_assets = list(InventoryAsset.objects.filter(is_active=True))
    total_assets = len(active_assets)
    total_asset_value = _money(sum((row.total_value for row in active_assets), Decimal("0.00")))
    total_outflow = _money(total_expenses + total_salaries_paid)
    balance = _money(total_payments - total_outflow)

    debtors = debtor_rows(session=session, term=term)
    total_outstanding = _money(sum((row.outstanding for row in debtors), Decimal("0.00")))
    return {
        "total_charges": total_charges,
        "total_payments": total_payments,
        "total_expenses": total_expenses,
        "total_salaries_paid": total_salaries_paid,
        "total_assets": total_assets,
        "total_asset_value": total_asset_value,
        "total_outflow": total_outflow,
        "balance": balance,
        "total_outstanding": total_outstanding,
        "debtors_count": len(debtors),
        "debtors": debtors,
    }
