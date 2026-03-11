from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import socket
from datetime import timedelta
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone

from apps.sync.models import (
    SyncConflictRule,
    SyncContentStream,
    SyncOperationType,
    SyncPullCursor,
    SyncQueue,
    SyncQueueEvent,
    SyncQueueStatus,
    SyncTransferBatch,
    SyncTransferDirection,
)

PENDING_SYNC_STATES = (SyncQueueStatus.PENDING, SyncQueueStatus.RETRY)
_CONNECTIVITY_CACHE_KEY = "sync_cloud_connectivity_v1"
_AUTO_SYNC_THROTTLE_CACHE_KEY = "sync_auto_process_lock_v1"
SYNC_DOMAIN_POLICIES = {
    SyncOperationType.CBT_EXAM_ATTEMPT: {
        "domain": "CBT",
        "policy": "LAN-authoritative during live exams. Remote writes append evidence and retry later instead of overriding active attempts.",
    },
    SyncOperationType.CBT_SIMULATION_ATTEMPT: {
        "domain": "CBT",
        "policy": "Simulation evidence is append-first. Score/writeback retries continue until cloud confirms receipt.",
    },
    SyncOperationType.CBT_CONTENT_CHANGE: {
        "domain": "CBT",
        "policy": "Teacher-authored CBT content pulls incrementally. Activated exam snapshots remain immutable after IT activation.",
    },
    SyncOperationType.STUDENT_REGISTRATION_UPSERT: {
        "domain": "Registration",
        "policy": "Directory records are upserted idempotently by source node identity with later reconciliation through model bindings.",
    },
    SyncOperationType.ELECTION_VOTE_SUBMISSION: {
        "domain": "Election",
        "policy": "Votes are strict-unique and LAN-authoritative during live polls. Duplicate vote envelopes are rejected as conflicts.",
    },
    SyncOperationType.MODEL_RECORD_UPSERT: {
        "domain": "Academic/General",
        "policy": "Model sync uses idempotent upserts. Active-session authority blocks unsafe overwrites for high-stakes workflows.",
    },
    SyncOperationType.MODEL_RECORD_DELETE: {
        "domain": "Academic/General",
        "policy": "Deletes are replayed only after binding resolution confirms the correct local record.",
    },
}


def current_local_node_id():
    configured = (getattr(settings, "SYNC_LOCAL_NODE_ID", "") or "").strip()
    if configured:
        return configured
    return socket.gethostname()


def current_sync_node_role():
    raw = (getattr(settings, "SYNC_NODE_ROLE", "CLOUD") or "CLOUD").strip().upper()
    if raw not in {"LAN", "CLOUD"}:
        return "CLOUD"
    return raw


def active_session_authority_enforced():
    return bool(getattr(settings, "SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY", True))


def _as_int(value, *, fallback=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def _connectivity_cache_ttl_seconds():
    value = _as_int(getattr(settings, "SYNC_CONNECTIVITY_CACHE_TTL_SECONDS", 2), fallback=2)
    return max(value, 1)
def sync_policy_for_operation(operation_type):
    return SYNC_DOMAIN_POLICIES.get(operation_type, {"domain": "General", "policy": "Idempotent queued sync with retry/backoff."})


def sync_policy_rows():
    rows = []
    for operation_type, _label in SyncOperationType.choices:
        policy = sync_policy_for_operation(operation_type)
        rows.append({
            "operation_type": operation_type,
            "domain": policy["domain"],
            "policy": policy["policy"],
        })
    return rows


def _record_sync_queue_event(*, queue_row, event_type, from_status="", to_status="", message="", metadata=None):
    return SyncQueueEvent.objects.create(
        queue_row=queue_row,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        message=(message or "")[:255],
        metadata=metadata or {},
    )


def compute_backoff_seconds(retry_count):
    base_seconds = int(getattr(settings, "SYNC_RETRY_BASE_SECONDS", 20))
    cap_seconds = int(getattr(settings, "SYNC_RETRY_MAX_SECONDS", 1800))
    retry_count = max(int(retry_count), 1)
    return min(cap_seconds, base_seconds * (2 ** (retry_count - 1)))


def build_idempotency_key(
    *,
    operation_type,
    payload,
    object_ref="",
    conflict_key="",
):
    canonical = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), default=str)
    seed = f"{operation_type}|{object_ref}|{conflict_key}|{canonical}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"{operation_type.lower()}-{digest[:80]}"


def _coerce_payload(payload):
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    raise ValidationError("Sync payload must be a JSON object.")


@transaction.atomic
def queue_sync_operation(
    *,
    operation_type,
    payload,
    object_ref="",
    source_portal="",
    idempotency_key="",
    conflict_rule=SyncConflictRule.APPEND_ONLY,
    conflict_key="",
    max_retries=None,
    is_manual_import=False,
    local_node_id="",
):
    payload = _coerce_payload(payload)
    valid_operations = {choice for choice, _ in SyncOperationType.choices}
    if operation_type not in valid_operations:
        raise ValidationError("Invalid sync operation type.")

    resolved_key = (idempotency_key or "").strip()
    if not resolved_key:
        resolved_key = build_idempotency_key(
            operation_type=operation_type,
            payload=payload,
            object_ref=object_ref,
            conflict_key=conflict_key,
        )
    resolved_key = resolved_key[:120]

    existing = SyncQueue.objects.select_for_update().filter(idempotency_key=resolved_key).first()
    if existing:
        return existing, False

    normalized_conflict_rule = conflict_rule or SyncConflictRule.APPEND_ONLY
    valid_conflict_rules = {choice for choice, _ in SyncConflictRule.choices}
    if normalized_conflict_rule not in valid_conflict_rules:
        raise ValidationError("Invalid sync conflict rule.")
    normalized_conflict_key = (conflict_key or "").strip()
    if (
        normalized_conflict_rule == SyncConflictRule.STRICT_UNIQUE
        and normalized_conflict_key
    ):
        duplicate_exists = SyncQueue.objects.select_for_update().filter(
            operation_type=operation_type,
            conflict_key=normalized_conflict_key,
        ).exclude(
            status=SyncQueueStatus.FAILED
        ).exists()
        if duplicate_exists:
            raise ValidationError("Duplicate strict-unique operation blocked.")

    queue_row = SyncQueue.objects.create(
        operation_type=operation_type,
        status=SyncQueueStatus.PENDING,
        payload=payload,
        idempotency_key=resolved_key,
        conflict_rule=normalized_conflict_rule,
        conflict_key=normalized_conflict_key,
        object_ref=(object_ref or "")[:120],
        source_portal=(source_portal or "")[:32],
        local_node_id=((local_node_id or "").strip() or current_local_node_id())[:80],
        next_retry_at=timezone.now(),
        max_retries=int(max_retries or getattr(settings, "SYNC_MAX_RETRIES", 8)),
        is_manual_import=bool(is_manual_import),
    )
    _record_sync_queue_event(
        queue_row=queue_row,
        event_type="QUEUED",
        to_status=queue_row.status,
        message="Sync item queued for outbound processing.",
        metadata={"operation_type": queue_row.operation_type, "object_ref": queue_row.object_ref},
    )
    return queue_row, True


def queue_exam_attempt_sync(*, attempt, event_type="ATTEMPT_UPSERT"):
    payload = {
        "event_type": event_type,
        "attempt_id": str(attempt.id),
        "exam_id": str(attempt.exam_id),
        "student_id": str(attempt.student_id),
        "attempt_number": int(attempt.attempt_number or 1),
        "status": attempt.status,
        "is_locked": bool(attempt.is_locked),
        "started_at": attempt.started_at.isoformat() if attempt.started_at else "",
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else "",
        "finalized_at": attempt.finalized_at.isoformat() if attempt.finalized_at else "",
        "objective_score": str(attempt.objective_score),
        "theory_score": str(attempt.theory_score),
        "total_score": str(attempt.total_score),
        "writeback_metadata": attempt.writeback_metadata or {},
        "updated_at": attempt.updated_at.isoformat() if attempt.updated_at else "",
    }
    idempotency_key = build_idempotency_key(
        operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
        payload=payload,
        object_ref=f"attempt:{attempt.id}",
    )
    return queue_sync_operation(
        operation_type=SyncOperationType.CBT_EXAM_ATTEMPT,
        payload=payload,
        object_ref=f"attempt:{attempt.id}",
        source_portal="cbt",
        idempotency_key=idempotency_key,
        conflict_rule=SyncConflictRule.APPEND_ONLY,
    )


def queue_simulation_attempt_sync(*, record, event_type="SIMULATION_UPSERT"):
    payload = {
        "event_type": event_type,
        "record_id": str(record.id),
        "attempt_id": str(record.attempt_id),
        "exam_id": str(record.attempt.exam_id),
        "student_id": str(record.attempt.student_id),
        "attempt_number": int(record.attempt.attempt_number or 1),
        "exam_simulation_id": str(record.exam_simulation_id),
        "status": record.status,
        "raw_score": str(record.raw_score) if record.raw_score is not None else "",
        "final_score": str(record.final_score) if record.final_score is not None else "",
        "imported_target": record.imported_target,
        "imported_score": str(record.imported_score) if record.imported_score is not None else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }
    idempotency_key = build_idempotency_key(
        operation_type=SyncOperationType.CBT_SIMULATION_ATTEMPT,
        payload=payload,
        object_ref=f"simulation_record:{record.id}",
    )
    return queue_sync_operation(
        operation_type=SyncOperationType.CBT_SIMULATION_ATTEMPT,
        payload=payload,
        object_ref=f"simulation_record:{record.id}",
        source_portal="cbt",
        idempotency_key=idempotency_key,
        conflict_rule=SyncConflictRule.APPEND_ONLY,
    )


def _file_field_to_data_url(file_field):
    if not file_field:
        return ""
    try:
        file_field.open("rb")
        raw = file_field.read()
    except Exception:
        return ""
    finally:
        try:
            file_field.close()
        except Exception:
            pass
    if not raw:
        return ""
    mime_type = mimetypes.guess_type(getattr(file_field, "name", ""))[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def queue_cbt_content_change_sync(*, change):
    payload = {
        "id": int(change.id),
        "stream": change.stream,
        "object_type": change.object_type,
        "operation": change.operation,
        "object_pk": str(change.object_pk),
        "payload": change.payload or {},
        "created_at": change.created_at.isoformat() if change.created_at else "",
    }
    object_ref = f"cbt-change:{change.id}"
    idempotency_key = build_idempotency_key(
        operation_type=SyncOperationType.CBT_CONTENT_CHANGE,
        payload=payload,
        object_ref=object_ref,
    )
    return queue_sync_operation(
        operation_type=SyncOperationType.CBT_CONTENT_CHANGE,
        payload=payload,
        object_ref=object_ref,
        source_portal="cbt",
        idempotency_key=idempotency_key,
        conflict_rule=SyncConflictRule.APPEND_ONLY,
    )


def queue_student_registration_sync(*, user, raw_password=""):
    from apps.accounts.models import StudentProfile

    profile = StudentProfile.objects.select_related("user").get(user=user)
    active_enrollment = (
        user.class_enrollments.select_related("academic_class", "session")
        .filter(is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )
    subject_enrollments = user.subject_enrollments.select_related("subject", "session")
    if active_enrollment and active_enrollment.session_id:
        subject_enrollments = subject_enrollments.filter(session=active_enrollment.session)
    subject_codes = sorted(
        row.subject.code
        for row in subject_enrollments
        if row.is_active and row.subject_id and row.subject and row.subject.code
    )
    payload = {
        "event_type": "STUDENT_UPSERT",
        "student_number": profile.student_number,
        "username": user.username,
        "temporary_password": raw_password or "",
        "email": user.email or profile.guardian_email or "",
        "first_name": user.first_name,
        "last_name": user.last_name,
        "middle_name": profile.middle_name,
        "admission_date": profile.admission_date.isoformat() if profile.admission_date else "",
        "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else "",
        "gender": profile.gender,
        "guardian_name": profile.guardian_name,
        "guardian_phone": profile.guardian_phone,
        "guardian_email": profile.guardian_email,
        "address": profile.address,
        "state_of_origin": profile.state_of_origin,
        "nationality": profile.nationality,
        "is_graduated": bool(profile.is_graduated),
        "current_session_name": active_enrollment.session.name if active_enrollment and active_enrollment.session_id else "",
        "current_class_code": active_enrollment.academic_class.code if active_enrollment and active_enrollment.academic_class_id else "",
        "subject_codes": subject_codes,
        "profile_photo_data_url": _file_field_to_data_url(profile.profile_photo),
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else "",
    }
    object_ref = f"student:{profile.student_number}"
    idempotency_key = build_idempotency_key(
        operation_type=SyncOperationType.STUDENT_REGISTRATION_UPSERT,
        payload=payload,
        object_ref=object_ref,
        conflict_key=profile.student_number,
    )
    return queue_sync_operation(
        operation_type=SyncOperationType.STUDENT_REGISTRATION_UPSERT,
        payload=payload,
        object_ref=object_ref,
        source_portal="it",
        idempotency_key=idempotency_key,
        conflict_rule=SyncConflictRule.LAST_WRITE_WINS,
        conflict_key=profile.student_number,
    )


def queue_vote_submission_sync(
    *,
    election_id,
    position_id,
    voter_id,
    payload,
    idempotency_key="",
):
    normalized_payload = _coerce_payload(payload)
    conflict_key = f"{election_id}:{position_id}:{voter_id}"
    if not idempotency_key:
        idempotency_key = build_idempotency_key(
            operation_type=SyncOperationType.ELECTION_VOTE_SUBMISSION,
            payload=normalized_payload,
            object_ref=f"vote:{conflict_key}",
            conflict_key=conflict_key,
        )
    return queue_sync_operation(
        operation_type=SyncOperationType.ELECTION_VOTE_SUBMISSION,
        payload=normalized_payload,
        object_ref=f"vote:{conflict_key}",
        source_portal="election",
        idempotency_key=idempotency_key,
        conflict_rule=SyncConflictRule.STRICT_UNIQUE,
        conflict_key=conflict_key,
    )


def ready_queue_queryset():
    now = timezone.now()
    priority_order = Case(
        When(operation_type=SyncOperationType.CBT_CONTENT_CHANGE, then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return SyncQueue.objects.filter(
        status__in=PENDING_SYNC_STATES,
    ).filter(
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    ).order_by(priority_order, "created_at", "id")


def _cloud_endpoint():
    return (getattr(settings, "SYNC_CLOUD_ENDPOINT", "") or "").strip()


def _endpoint_auth_token():
    return (getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN", "") or "").strip()


def _connectivity_timeout():
    value = int(getattr(settings, "SYNC_CONNECTIVITY_TIMEOUT_SECONDS", 2))
    return max(value, 1)


def _probe_cloud_connectivity(force=False):
    endpoint = _cloud_endpoint()
    if not endpoint:
        return False
    if not force:
        try:
            cached = cache.get(_CONNECTIVITY_CACHE_KEY)
        except Exception:
            cached = None
        if cached is not None:
            return bool(cached)
    req = url_request.Request(endpoint, method="HEAD")
    token = _endpoint_auth_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with url_request.urlopen(req, timeout=_connectivity_timeout()) as response:
            ok = 200 <= int(response.status) < 500
    except Exception:
        ok = False
    try:
        cache.set(_CONNECTIVITY_CACHE_KEY, bool(ok), _connectivity_cache_ttl_seconds())
    except Exception:
        pass
    return bool(ok)


def _dispatch_to_cloud(queue_row):
    endpoint = _cloud_endpoint()
    if not endpoint:
        return {
            "ok": False,
            "deferred": True,
            "status_code": None,
            "payload": {},
            "error": "Sync cloud endpoint not configured.",
            "remote_reference": "",
        }
    target_url = endpoint.rstrip("/") + "/outbox/"
    body = json.dumps(
        {
            "idempotency_key": queue_row.idempotency_key,
            "operation_type": queue_row.operation_type,
            "payload": queue_row.payload,
            "object_ref": queue_row.object_ref,
            "conflict_rule": queue_row.conflict_rule,
            "conflict_key": queue_row.conflict_key,
            "local_node_id": queue_row.local_node_id,
            "queued_at": queue_row.created_at.isoformat() if queue_row.created_at else "",
        },
        sort_keys=True,
    ).encode("utf-8")
    req = url_request.Request(
        target_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    req.add_header("X-Idempotency-Key", queue_row.idempotency_key)
    token = _endpoint_auth_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with url_request.urlopen(req, timeout=_connectivity_timeout()) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            parsed = json.loads(raw) if raw else {}
            remote_reference = str(parsed.get("reference") or parsed.get("id") or "")
            return {
                "ok": 200 <= int(response.status) < 300,
                "deferred": False,
                "status_code": int(response.status),
                "payload": parsed,
                "error": "",
                "remote_reference": remote_reference,
            }
    except url_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        parsed = {}
        if raw:
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = {"raw": raw}
        error_message = parsed.get("detail") if isinstance(parsed, dict) else ""
        if not error_message:
            error_message = str(exc)
        return {
            "ok": False,
            "deferred": False,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "payload": parsed if isinstance(parsed, dict) else {"raw": str(parsed)},
            "error": error_message,
            "remote_reference": "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "deferred": False,
            "status_code": 0,
            "payload": {},
            "error": str(exc),
            "remote_reference": "",
        }



def _sync_pull_timeout():
    value = _as_int(getattr(settings, "SYNC_PULL_TIMEOUT_SECONDS", 5), fallback=5)
    return max(value, 1)


def _serialize_outbox_feed_row(row):
    return {
        "id": int(row.id),
        "idempotency_key": row.idempotency_key,
        "operation_type": row.operation_type,
        "payload": row.payload,
        "object_ref": row.object_ref,
        "conflict_rule": row.conflict_rule,
        "conflict_key": row.conflict_key,
        "local_node_id": row.local_node_id,
        "source_portal": row.source_portal,
        "queued_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def build_outbox_feed(*, after_id=0, limit=200, exclude_origin_node_id=""):
    safe_after_id = max(_as_int(after_id, fallback=0), 0)
    safe_limit = max(min(_as_int(limit, fallback=200), 500), 1)
    queryset = SyncQueue.objects.exclude(
        operation_type=SyncOperationType.CBT_CONTENT_CHANGE,
    ).filter(
        id__gt=safe_after_id,
    ).order_by("id")
    normalized_exclude = (exclude_origin_node_id or "").strip()
    if normalized_exclude:
        queryset = queryset.exclude(local_node_id=normalized_exclude)
    rows = list(queryset[:safe_limit])
    next_after_id = rows[-1].id if rows else safe_after_id
    has_more = queryset.filter(id__gt=next_after_id).exists()
    return {
        "stream": SyncContentStream.OUTBOX_EVENTS,
        "after_id": safe_after_id,
        "next_after_id": next_after_id,
        "has_more": has_more,
        "count": len(rows),
        "generated_at": timezone.now().isoformat(),
        "events": [_serialize_outbox_feed_row(row) for row in rows],
    }


def _fetch_remote_outbox_feed(*, after_id, limit):
    endpoint = _cloud_endpoint()
    if not endpoint:
        return {
            "ok": False,
            "status_code": 0,
            "payload": {},
            "error": "Cloud endpoint is not configured.",
        }
    query_string = url_parse.urlencode(
        {
            "after_id": max(_as_int(after_id, fallback=0), 0),
            "limit": max(min(_as_int(limit, fallback=200), 500), 1),
            "exclude_origin_node_id": current_local_node_id(),
        }
    )
    target_url = f"{endpoint.rstrip('/')}/outbox/feed/?{query_string}"
    req = url_request.Request(target_url, method="GET")
    token = _endpoint_auth_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with url_request.urlopen(req, timeout=_sync_pull_timeout()) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw) if raw else {}
            return {
                "ok": 200 <= int(response.status) < 300,
                "status_code": int(response.status),
                "payload": payload if isinstance(payload, dict) else {},
                "error": "",
            }
    except url_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        payload = {}
        if raw:
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {"raw": raw}
        error_message = payload.get("detail") if isinstance(payload, dict) else str(exc)
        return {
            "ok": False,
            "status_code": int(getattr(exc, "code", 0) or 0),
            "payload": payload if isinstance(payload, dict) else {},
            "error": error_message or str(exc),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": 0,
            "payload": {},
            "error": str(exc),
        }


def pull_remote_outbox_updates(*, limit=None, max_pages=None):
    if not bool(getattr(settings, "SYNC_PULL_ENABLED", True)):
        return {"triggered": False, "reason": "pull_disabled", "applied": 0, "duplicates": 0, "blocked": 0, "pages": 0}
    if not _cloud_endpoint():
        return {"triggered": False, "reason": "cloud_not_configured", "applied": 0, "duplicates": 0, "blocked": 0, "pages": 0}

    from apps.sync.inbound_sync import ingest_remote_outbox_event

    safe_limit = max(min(_as_int(limit or getattr(settings, "SYNC_PULL_BATCH_LIMIT", 200)), 500), 1)
    safe_pages = max(_as_int(max_pages or getattr(settings, "SYNC_PULL_MAX_PAGES_PER_RUN", 4)), 1)
    cursor, _ = SyncPullCursor.objects.get_or_create(stream=SyncContentStream.OUTBOX_EVENTS)

    total_applied = 0
    total_duplicates = 0
    total_blocked = 0
    pages = 0
    last_error = ""
    for _ in range(safe_pages):
        pages += 1
        cursor.last_pull_at = timezone.now()
        cursor.save(update_fields=["last_pull_at", "updated_at"])

        fetch_result = _fetch_remote_outbox_feed(after_id=cursor.last_remote_id, limit=safe_limit)
        if not fetch_result["ok"]:
            last_error = fetch_result["error"] or "Unable to fetch remote outbox feed."
            cursor.last_error = last_error
            cursor.save(update_fields=["last_error", "updated_at"])
            break

        payload = fetch_result.get("payload") or {}
        events = payload.get("events") or []
        if not isinstance(events, list) or not events:
            cursor.last_error = ""
            cursor.last_success_at = timezone.now()
            cursor.metadata = {
                "last_count": 0,
                "has_more": bool(payload.get("has_more", False)),
                "next_after_id": payload.get("next_after_id", cursor.last_remote_id),
            }
            cursor.save(update_fields=["last_error", "last_success_at", "metadata", "updated_at"])
            break

        page_applied = 0
        page_duplicates = 0
        page_blocked = 0
        next_after_id = cursor.last_remote_id
        for event in events:
            remote_id = max(_as_int(event.get("id"), fallback=0), 0)
            try:
                result = ingest_remote_outbox_event(envelope=event)
            except ValidationError as exc:
                page_blocked += 1
                last_error = "; ".join(exc.messages) or "Remote outbox apply blocked."
                break
            status = result.get("status")
            if status == "duplicate":
                page_duplicates += 1
            else:
                page_applied += 1
            if remote_id > next_after_id:
                next_after_id = remote_id

        total_applied += page_applied
        total_duplicates += page_duplicates
        total_blocked += page_blocked
        if next_after_id > cursor.last_remote_id:
            cursor.last_remote_id = next_after_id
        cursor.last_success_at = timezone.now()
        cursor.last_error = last_error if page_blocked else ""
        cursor.metadata = {
            "last_count": page_applied + page_duplicates,
            "duplicates": page_duplicates,
            "blocked": page_blocked,
            "has_more": bool(payload.get("has_more", False)),
            "next_after_id": payload.get("next_after_id", cursor.last_remote_id),
        }
        cursor.save(
            update_fields=[
                "last_remote_id",
                "last_success_at",
                "last_error",
                "metadata",
                "updated_at",
            ]
        )
        if page_blocked > 0 or not bool(payload.get("has_more", False)):
            break

    return {
        "triggered": True,
        "reason": "processed",
        "applied": total_applied,
        "duplicates": total_duplicates,
        "blocked": total_blocked,
        "pages": pages,
        "last_remote_id": cursor.last_remote_id,
        "error": last_error,
    }


@transaction.atomic
def process_queue_row(queue_row):
    if queue_row.status in {SyncQueueStatus.SYNCED, SyncQueueStatus.CONFLICT}:
        return {"processed": False, "status": queue_row.status}

    from_status = queue_row.status
    queue_row.last_attempt_at = timezone.now()
    outcome = _dispatch_to_cloud(queue_row)
    queue_row.response_code = outcome.get("status_code") or None
    queue_row.response_payload = outcome.get("payload") or {}
    queue_row.remote_reference = (outcome.get("remote_reference") or "")[:150]

    status_code = int(outcome.get("status_code") or 0)
    if outcome.get("ok"):
        queue_row.status = SyncQueueStatus.SYNCED
        queue_row.synced_at = timezone.now()
        queue_row.next_retry_at = None
        queue_row.last_error = ""
    elif status_code == 409:
        queue_row.status = SyncQueueStatus.CONFLICT
        queue_row.next_retry_at = None
        queue_row.last_error = outcome.get("error") or "Conflict detected."
    else:
        queue_row.retry_count = int(queue_row.retry_count or 0) + 1
        queue_row.last_error = outcome.get("error") or "Sync failed."
        if queue_row.retry_count > int(queue_row.max_retries or 0):
            queue_row.status = SyncQueueStatus.FAILED
            queue_row.next_retry_at = None
        else:
            queue_row.status = SyncQueueStatus.RETRY
            delay = compute_backoff_seconds(queue_row.retry_count)
            queue_row.next_retry_at = timezone.now() + timedelta(seconds=delay)

    queue_row.save(
        update_fields=[
            "status",
            "retry_count",
            "next_retry_at",
            "last_attempt_at",
            "synced_at",
            "response_code",
            "response_payload",
            "remote_reference",
            "last_error",
            "updated_at",
        ]
    )
    _record_sync_queue_event(
        queue_row=queue_row,
        event_type="STATUS_TRANSITION",
        from_status=from_status,
        to_status=queue_row.status,
        message=queue_row.last_error or f"Queue item moved to {queue_row.status}.",
        metadata={
            "response_code": queue_row.response_code,
            "retry_count": queue_row.retry_count,
            "remote_reference": queue_row.remote_reference,
        },
    )
    return {"processed": True, "status": queue_row.status}


def process_sync_queue_batch(limit=50):
    rows = list(ready_queue_queryset()[: max(int(limit or 0), 1)])
    summary = {
        "claimed": len(rows),
        "synced": 0,
        "retry": 0,
        "failed": 0,
        "conflict": 0,
    }
    for row in rows:
        result = process_queue_row(row)
        status = result.get("status")
        if status == SyncQueueStatus.SYNCED:
            summary["synced"] += 1
        elif status == SyncQueueStatus.RETRY:
            summary["retry"] += 1
        elif status == SyncQueueStatus.FAILED:
            summary["failed"] += 1
        elif status == SyncQueueStatus.CONFLICT:
            summary["conflict"] += 1
    return summary


def trigger_auto_sync_if_connected():
    if not bool(getattr(settings, "SYNC_AUTO_ON_REQUEST", True)):
        return {"triggered": False, "reason": "disabled"}
    if not _cloud_endpoint():
        return {"triggered": False, "reason": "cloud_not_configured"}
    if not SyncQueue.objects.filter(status__in=PENDING_SYNC_STATES).exists():
        return {"triggered": False, "reason": "no_pending"}
    if not _probe_cloud_connectivity():
        return {"triggered": False, "reason": "offline"}

    throttle_seconds = max(int(getattr(settings, "SYNC_AUTO_MIN_INTERVAL_SECONDS", 1)), 1)
    try:
        claimed_lock = cache.add(_AUTO_SYNC_THROTTLE_CACHE_KEY, "1", throttle_seconds)
    except Exception:
        claimed_lock = True
    if not claimed_lock:
        return {"triggered": False, "reason": "throttled"}

    batch_limit = max(int(getattr(settings, "SYNC_AUTO_BATCH_LIMIT", 60)), 1)
    summary = process_sync_queue_batch(limit=batch_limit)
    return {
        "triggered": True,
        "reason": "processed",
        "summary": summary,
    }


def get_runtime_status():
    endpoint = _cloud_endpoint()
    pending_count = SyncQueue.objects.filter(status__in=PENDING_SYNC_STATES).count()
    offline_mode_enabled = bool(settings.FEATURE_FLAGS.get("OFFLINE_MODE_ENABLED", False))
    local_node_enabled = bool(getattr(settings, "SYNC_LOCAL_NODE_ENABLED", True))
    cloud_configured = bool(endpoint)
    cloud_connected = _probe_cloud_connectivity() if cloud_configured else False

    if cloud_configured and cloud_connected and pending_count == 0:
        code = "CLOUD_CONNECTED"
        label = "Cloud Connected"
        tone = "green"
    elif pending_count > 0:
        code = "SYNC_PENDING"
        label = "Sync Pending"
        tone = "orange"
    elif offline_mode_enabled or local_node_enabled:
        code = "LOCAL_MODE"
        label = "Local Mode"
        tone = "blue"
    else:
        code = "DISCONNECTED"
        label = "Disconnected"
        tone = "red"

    if cloud_configured and not cloud_connected and pending_count == 0:
        code = "DISCONNECTED"
        label = "Disconnected"
        tone = "red"

    latest_synced = (
        SyncQueue.objects.filter(status=SyncQueueStatus.SYNCED)
        .order_by("-synced_at")
        .values_list("synced_at", flat=True)
        .first()
    )
    return {
        "code": code,
        "label": label,
        "tone": tone,
        "pending_count": pending_count,
        "local_node_id": current_local_node_id(),
        "node_role": current_sync_node_role(),
        "cloud_configured": cloud_configured,
        "cloud_connected": cloud_connected,
        "offline_mode_enabled": offline_mode_enabled,
        "latest_synced_at": latest_synced,
    }


def tone_css_map():
    return {
        "green": {
            "dot": "bg-emerald-500",
            "chip": "border-emerald-200 bg-emerald-50 text-emerald-800",
        },
        "blue": {
            "dot": "bg-sky-500",
            "chip": "border-sky-200 bg-sky-50 text-sky-800",
        },
        "orange": {
            "dot": "bg-amber-500",
            "chip": "border-amber-200 bg-amber-50 text-amber-800",
        },
        "red": {
            "dot": "bg-rose-500",
            "chip": "border-rose-200 bg-rose-50 text-rose-800",
        },
    }


def build_runtime_status_payload():
    auto_sync_result = trigger_auto_sync_if_connected()
    status = get_runtime_status()
    style = tone_css_map().get(status["tone"], tone_css_map()["red"])
    status["dot_class"] = style["dot"]
    status["chip_class"] = style["chip"]
    status["auto_sync"] = auto_sync_result
    return status


def _serialize_row_for_transfer(row):
    return {
        "operation_type": row.operation_type,
        "payload": row.payload,
        "idempotency_key": row.idempotency_key,
        "conflict_rule": row.conflict_rule,
        "conflict_key": row.conflict_key,
        "object_ref": row.object_ref,
        "source_portal": row.source_portal,
        "local_node_id": row.local_node_id,
        "status": row.status,
        "retry_count": row.retry_count,
        "max_retries": row.max_retries,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def export_sync_queue_snapshot(*, actor=None):
    queryset = SyncQueue.objects.order_by("created_at", "id")
    items = [_serialize_row_for_transfer(row) for row in queryset]
    payload = {
        "version": 1,
        "exported_at": timezone.now().isoformat(),
        "local_node_id": current_local_node_id(),
        "item_count": len(items),
        "queue": items,
    }
    raw_json = json.dumps(payload, indent=2, sort_keys=True)
    checksum = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    file_stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"ndga_sync_export_{file_stamp}.json"
    SyncTransferBatch.objects.create(
        direction=SyncTransferDirection.EXPORT,
        file_name=file_name,
        item_count=len(items),
        checksum=checksum,
        metadata={"node_id": current_local_node_id()},
        performed_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    return {
        "file_name": file_name,
        "checksum": checksum,
        "json_text": raw_json,
        "item_count": len(items),
    }


def import_sync_queue_snapshot(*, raw_json, actor=None):
    try:
        parsed = json.loads(raw_json)
    except Exception as exc:
        raise ValidationError("Invalid sync snapshot file.") from exc

    items = parsed.get("queue") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ValidationError("Snapshot file missing queue list.")

    imported = 0
    skipped = 0
    for item in items:
        if not isinstance(item, dict):
            skipped += 1
            continue
        try:
            _, created = queue_sync_operation(
                operation_type=item.get("operation_type", ""),
                payload=item.get("payload") or {},
                object_ref=item.get("object_ref", ""),
                source_portal=item.get("source_portal", ""),
                idempotency_key=item.get("idempotency_key", ""),
                conflict_rule=item.get("conflict_rule", SyncConflictRule.APPEND_ONLY),
                conflict_key=item.get("conflict_key", ""),
                max_retries=item.get("max_retries"),
                is_manual_import=True,
                local_node_id=item.get("local_node_id", ""),
            )
        except ValidationError:
            skipped += 1
            continue
        if created:
            imported += 1
        else:
            skipped += 1

    checksum = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    file_stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"ndga_sync_import_{file_stamp}.json"
    SyncTransferBatch.objects.create(
        direction=SyncTransferDirection.IMPORT,
        file_name=file_name,
        item_count=imported,
        checksum=checksum,
        metadata={"skipped": skipped, "snapshot_item_count": len(items)},
        performed_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    return {"imported": imported, "skipped": skipped, "total_items": len(items)}
