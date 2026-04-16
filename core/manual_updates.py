from __future__ import annotations

import hmac
import ipaddress
import json
from datetime import datetime
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from django.views import View

from apps.accounts.constants import ROLE_STUDENT
from apps.audit.services import get_client_ip, log_event
from apps.finance.services import (
    finance_sync_decode_transport,
    finance_sync_payload_signature,
    finance_sync_signing_secrets,
    finance_sync_transport_payload,
)
from apps.sync.model_sync import apply_generic_model_payload, serialize_generic_model_instance
from apps.sync.models import SyncOperationType
from apps.sync.policies import RESULT_PUBLICATION_MODEL_LABELS, generic_model_sync_allowed_for_instance


MANUAL_EXPORT_CHANNEL_MODELS = {
    "results": [
        "results.resultsheet",
        "results.studentsubjectscore",
        "results.classresultcompilation",
        "results.classresultstudentrecord",
        "results.resultaccesspin",
    ],
    "attendance": [
        "attendance.attendancerecord",
    ],
    "students": [
        "accounts.user",
        "accounts.studentprofile",
        "academics.studentclassenrollment",
        "academics.studentsubjectenrollment",
    ],
    "receipts": [
        "finance.receipt",
    ],
    "admissions": [
        "dashboard.publicsitesubmission",
        "dashboard.publicadmissionpaymenttransaction",
    ],
}

LAN_TO_CLOUD_CHANNELS = ("results", "attendance", "students", "receipts")
CLOUD_TO_LAN_CHANNELS = ("admissions",)


def manual_update_token_values():
    values = []
    candidates = [
        getattr(settings, "MANUAL_UPDATE_TOKEN", ""),
        *list(getattr(settings, "MANUAL_UPDATE_TOKEN_FALLBACKS", []) or []),
        getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN", ""),
        *list(getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN_FALLBACKS", []) or []),
    ]
    for candidate in candidates:
        token = (candidate or "").strip()
        if token and token not in values:
            values.append(token)
    return values


def manual_update_remote_base_url():
    configured = (getattr(settings, "MANUAL_UPDATE_REMOTE_BASE_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured
    sync_endpoint = (getattr(settings, "SYNC_CLOUD_ENDPOINT", "") or "").strip()
    if not sync_endpoint:
        return ""
    parsed = url_parse.urlparse(sync_endpoint)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return url_parse.urlunparse(parsed._replace(path="", params="", query="", fragment="")).rstrip("/")


def manual_update_remote_url(path: str):
    base_url = manual_update_remote_base_url()
    if not base_url:
        return ""
    return f"{base_url}{path}"


def manual_update_request_authorized(request):
    provided = (
        request.headers.get("X-NDGA-Manual-Update-Token")
        or request.headers.get("X-NDGA-Manual-Sync-Token")
        or request.GET.get("token")
        or ""
    ).strip()
    if not provided:
        return False
    return any(hmac.compare_digest(provided, expected) for expected in manual_update_token_values())


def manual_update_request_ip_allowed(request):
    allowed = list(getattr(settings, "MANUAL_UPDATE_ALLOWED_IPS", []) or [])
    if not allowed:
        allowed = list(getattr(settings, "SYNC_ENDPOINT_ALLOWED_IPS", []) or [])
    if not allowed:
        return True
    raw_ip = (get_client_ip(request) or "").strip()
    if not raw_ip:
        return False
    try:
        request_ip = ipaddress.ip_address(raw_ip)
    except ValueError:
        return False
    for item in allowed:
        candidate = (item or "").strip()
        if not candidate:
            continue
        try:
            if "/" in candidate and request_ip in ipaddress.ip_network(candidate, strict=False):
                return True
            if request_ip == ipaddress.ip_address(candidate):
                return True
        except ValueError:
            continue
    return False


def manual_update_signed_response(payload, *, status=200):
    raw = finance_sync_transport_payload(payload)
    response = HttpResponse(raw, status=status, content_type="application/json")
    signature = finance_sync_payload_signature(raw)
    if signature:
        response["X-NDGA-Payload-Signature"] = signature
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response


def decode_manual_update_response(*, raw_body, headers):
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    signature = (headers.get("X-NDGA-Payload-Signature") or "").strip().lower()
    secrets = finance_sync_signing_secrets()
    if secrets:
        if not signature:
            raise ValidationError("Manual update signature header is missing.")
        if not any(
            hmac.compare_digest(
                hmac.new(secret.encode("utf-8"), raw_body, "sha256").hexdigest(),
                signature,
            )
            for secret in secrets
        ):
            raise ValidationError("Manual update signature verification failed.")
    return finance_sync_decode_transport(raw_body)


def normalized_manual_channels(raw_channels, *, allowed_channels=None):
    if isinstance(raw_channels, str):
        values = [item.strip().lower() for item in raw_channels.split(",")]
    else:
        values = [str(item or "").strip().lower() for item in (raw_channels or [])]
    values = [item for item in values if item]
    if not values:
        values = list(allowed_channels or LAN_TO_CLOUD_CHANNELS)
    valid_channels = set(MANUAL_EXPORT_CHANNEL_MODELS)
    if allowed_channels is not None:
        valid_channels &= set(allowed_channels)
    invalid = [item for item in values if item not in valid_channels]
    if invalid:
        raise ValidationError(f"Unsupported manual update channel(s): {', '.join(sorted(set(invalid)))}.")
    ordered = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return ordered


def manual_update_model_labels(channels):
    ordered = []
    for channel in normalized_manual_channels(channels, allowed_channels=MANUAL_EXPORT_CHANNEL_MODELS.keys()):
        for label in MANUAL_EXPORT_CHANNEL_MODELS.get(channel, []):
            if label not in ordered:
                ordered.append(label)
    return ordered


def _apply_updated_since(queryset, updated_since):
    if updated_since is None:
        return queryset
    field_names = {field.name for field in queryset.model._meta.concrete_fields}
    if "updated_at" in field_names:
        return queryset.filter(updated_at__gt=updated_since)
    if "created_at" in field_names:
        return queryset.filter(created_at__gt=updated_since)
    return queryset


def _student_role_query(prefix=""):
    return (
        models.Q(**{f"{prefix}primary_role__code": ROLE_STUDENT})
        | models.Q(**{f"{prefix}secondary_roles__code": ROLE_STUDENT})
    )


def _manual_export_queryset(model_label, *, updated_since=None):
    model = apps.get_model(model_label)
    queryset = model.objects.all()

    if model_label in RESULT_PUBLICATION_MODEL_LABELS:
        if model_label == "results.resultsheet":
            from apps.results.models import ResultSheetStatus

            queryset = queryset.filter(status=ResultSheetStatus.PUBLISHED)
        elif model_label == "results.studentsubjectscore":
            from apps.results.models import ResultSheetStatus

            queryset = queryset.filter(result_sheet__status=ResultSheetStatus.PUBLISHED)
        elif model_label == "results.classresultcompilation":
            from apps.results.models import ClassCompilationStatus

            queryset = queryset.filter(status=ClassCompilationStatus.PUBLISHED)
        elif model_label == "results.classresultstudentrecord":
            from apps.results.models import ClassCompilationStatus

            queryset = queryset.filter(compilation__status=ClassCompilationStatus.PUBLISHED)
    elif model_label == "attendance.attendancerecord":
        queryset = queryset.filter(_student_role_query("student__")).distinct()
    elif model_label == "accounts.user":
        queryset = queryset.filter(_student_role_query()).distinct()
    elif model_label == "accounts.studentprofile":
        queryset = queryset.filter(_student_role_query("user__")).distinct()
    elif model_label == "academics.studentclassenrollment":
        queryset = queryset.filter(_student_role_query("student__")).distinct()
    elif model_label == "academics.studentsubjectenrollment":
        queryset = queryset.filter(_student_role_query("student__")).distinct()
    elif model_label == "finance.receipt":
        queryset = queryset.filter(_student_role_query("payment__student__")).distinct()
    elif model_label == "dashboard.publicsitesubmission":
        from apps.dashboard.models import PublicSubmissionType

        queryset = queryset.filter(submission_type=PublicSubmissionType.ADMISSION)
    elif model_label == "dashboard.publicadmissionpaymenttransaction":
        from apps.dashboard.models import PublicSubmissionType

        queryset = queryset.filter(submission__submission_type=PublicSubmissionType.ADMISSION)

    queryset = _apply_updated_since(queryset, updated_since)
    field_names = {field.name for field in model._meta.concrete_fields}
    if "updated_at" in field_names:
        queryset = queryset.order_by("updated_at", "pk")
    elif "created_at" in field_names:
        queryset = queryset.order_by("created_at", "pk")
    else:
        queryset = queryset.order_by("pk")
    return queryset


def build_manual_update_payload(*, channels, updated_since=None, limit_per_model=250):
    items = []
    latest_timestamp = updated_since
    channel_list = normalized_manual_channels(channels, allowed_channels=MANUAL_EXPORT_CHANNEL_MODELS.keys())
    for model_label in manual_update_model_labels(channel_list):
        queryset = _manual_export_queryset(
            model_label,
            updated_since=updated_since,
        )[: max(1, min(int(limit_per_model), 1000))]
        for instance in queryset:
            if model_label in RESULT_PUBLICATION_MODEL_LABELS and not generic_model_sync_allowed_for_instance(instance):
                continue
            items.append(serialize_generic_model_instance(instance))
            instance_updated_at = getattr(instance, "updated_at", None) or getattr(instance, "created_at", None)
            if instance_updated_at and (latest_timestamp is None or instance_updated_at > latest_timestamp):
                latest_timestamp = instance_updated_at
    return {
        "channels": channel_list,
        "count": len(items),
        "latest_timestamp": latest_timestamp.isoformat() if latest_timestamp else "",
        "generated_at": timezone.now().isoformat(),
        "items": items,
    }


def apply_manual_update_payload(*, payload, allowed_channels):
    channel_list = normalized_manual_channels(allowed_channels, allowed_channels=allowed_channels)
    allowed_labels = set(manual_update_model_labels(channel_list))
    items = list(payload.get("items") or [])
    imported = 0
    skipped = 0
    errors = []
    latest_timestamp = None
    for item in items:
        model_label = str(item.get("model") or "").strip().lower()
        if model_label not in allowed_labels:
            skipped += 1
            continue
        try:
            apply_generic_model_payload(
                payload=item,
                operation_type=SyncOperationType.MODEL_RECORD_UPSERT,
            )
            imported += 1
            updated_raw = str(item.get("updated_at") or "").strip()
            if updated_raw:
                parsed = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
                if latest_timestamp is None or parsed > latest_timestamp:
                    latest_timestamp = parsed
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model_label}: {exc}")
    return {
        "channels": channel_list,
        "count": imported,
        "skipped": skipped,
        "errors": errors,
        "latest_timestamp": latest_timestamp,
    }


def fetch_remote_manual_update_payload(*, channels, updated_since=None, limit_per_model=250):
    endpoint = manual_update_remote_url("/ops/manual-export/updates/")
    if not endpoint:
        raise ValidationError("Manual update remote base URL is not configured.")
    params = {
        "channels": ",".join(normalized_manual_channels(channels, allowed_channels=MANUAL_EXPORT_CHANNEL_MODELS.keys())),
        "limit": str(max(1, min(int(limit_per_model), 1000))),
    }
    if updated_since is not None:
        params["since"] = updated_since.isoformat()
    url = f"{endpoint}?{url_parse.urlencode(params)}"
    request_obj = url_request.Request(url, method="GET")
    token = next(iter(manual_update_token_values()), "")
    if token:
        request_obj.add_header("X-NDGA-Manual-Update-Token", token)
    try:
        with url_request.urlopen(request_obj, timeout=30) as response:
            raw_body = response.read()
            return decode_manual_update_response(raw_body=raw_body, headers=response.headers)
    except (url_error.URLError, ValidationError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Unable to fetch manual update payload: {exc}") from exc


def push_local_manual_updates(*, channels, updated_since=None, limit_per_model=250):
    endpoint = manual_update_remote_url("/ops/manual-import/updates/")
    if not endpoint:
        raise ValidationError("Manual update remote base URL is not configured.")
    payload = build_manual_update_payload(
        channels=channels,
        updated_since=updated_since,
        limit_per_model=limit_per_model,
    )
    raw_body = finance_sync_transport_payload(payload)
    request_obj = url_request.Request(endpoint, method="POST", data=raw_body)
    request_obj.add_header("Content-Type", "application/json")
    token = next(iter(manual_update_token_values()), "")
    if token:
        request_obj.add_header("X-NDGA-Manual-Update-Token", token)
    signature = finance_sync_payload_signature(raw_body)
    if signature:
        request_obj.add_header("X-NDGA-Payload-Signature", signature)
    try:
        with url_request.urlopen(request_obj, timeout=60) as response:
            raw_response = response.read()
            return decode_manual_update_response(raw_body=raw_response, headers=response.headers)
    except (url_error.URLError, ValidationError, json.JSONDecodeError) as exc:
        raise ValidationError(f"Unable to push manual updates to cloud: {exc}") from exc


class ManualUpdateExportView(View):
    allowed_channels = MANUAL_EXPORT_CHANNEL_MODELS.keys()

    def get(self, request, *args, **kwargs):
        if not manual_update_request_ip_allowed(request):
            return HttpResponse(json.dumps({"detail": "Forbidden"}), status=403, content_type="application/json")
        if not manual_update_request_authorized(request):
            return HttpResponse(json.dumps({"detail": "Unauthorized"}), status=401, content_type="application/json")
        try:
            channels = normalized_manual_channels(
                request.GET.get("channels", ""),
                allowed_channels=self.allowed_channels,
            )
            since_raw = (request.GET.get("since") or "").strip()
            since = None
            if since_raw:
                since = datetime.fromisoformat(since_raw.replace("Z", "+00:00"))
                if timezone.is_naive(since):
                    since = timezone.make_aware(since, timezone.get_current_timezone())
            limit = max(1, min(int(request.GET.get("limit") or 250), 1000))
            payload = build_manual_update_payload(
                channels=channels,
                updated_since=since,
                limit_per_model=limit,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return HttpResponse(json.dumps({"detail": str(exc)}), status=400, content_type="application/json")
        return manual_update_signed_response(payload)


class ManualUpdateImportView(View):
    allowed_channels = LAN_TO_CLOUD_CHANNELS

    def post(self, request, *args, **kwargs):
        if not manual_update_request_ip_allowed(request):
            return HttpResponse(json.dumps({"detail": "Forbidden"}), status=403, content_type="application/json")
        if not manual_update_request_authorized(request):
            return HttpResponse(json.dumps({"detail": "Unauthorized"}), status=401, content_type="application/json")
        try:
            payload = decode_manual_update_response(raw_body=request.body, headers=request.headers)
            summary = apply_manual_update_payload(
                payload=payload,
                allowed_channels=self.allowed_channels,
            )
        except ValidationError as exc:
            return HttpResponse(json.dumps({"detail": str(exc)}), status=400, content_type="application/json")
        log_event(
            category="SYSTEM",
            event_type="MANUAL_UPDATE_IMPORT",
            status="SUCCESS" if not summary["errors"] else "PARTIAL",
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            request=request,
            message="Manual LAN-to-cloud update import processed.",
            metadata={
                "channels": summary["channels"],
                "count": summary["count"],
                "skipped": summary["skipped"],
                "errors": summary["errors"][:10],
            },
        )
        latest_timestamp = summary["latest_timestamp"]
        return manual_update_signed_response(
            {
                "channels": summary["channels"],
                "count": summary["count"],
                "skipped": summary["skipped"],
                "errors": summary["errors"],
                "latest_timestamp": latest_timestamp.isoformat() if latest_timestamp else "",
                "processed_at": timezone.now().isoformat(),
            }
        )
