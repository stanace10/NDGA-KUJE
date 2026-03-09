from __future__ import annotations

import base64
import binascii
import mimetypes
import uuid
from contextlib import contextmanager
from decimal import Decimal
from threading import local

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models
from django.utils.dateparse import parse_date, parse_datetime, parse_time

from apps.sync.models import SyncConflictRule, SyncModelBinding, SyncOperationType
from apps.sync.services import (
    active_session_authority_enforced,
    build_idempotency_key,
    current_local_node_id,
    current_sync_node_role,
    queue_sync_operation,
)

_THREAD_LOCAL = local()

GENERIC_MODEL_SYNC_CONFIG = {
    "accounts.role": {"lookup_fields": ["code"]},
    "accounts.user": {
        "lookup_fields": ["username"],
        "exclude_m2m_fields": ["groups", "user_permissions"],
    },
    "accounts.staffprofile": {"lookup_fields": ["staff_id"]},
    "accounts.studentprofile": {"lookup_fields": ["student_number"]},
    "academics.academicsession": {"lookup_fields": ["name"]},
    "academics.term": {"lookup_fields": ["session", "name"]},
    "academics.academicclass": {"lookup_fields": ["code"]},
    "academics.subject": {"lookup_fields": ["code"]},
    "academics.gradescale": {"lookup_fields": ["grade", "is_default"]},
    "academics.classsubject": {"lookup_fields": ["academic_class", "subject"]},
    "academics.teachersubjectassignment": {
        "lookup_fields": ["teacher", "subject", "academic_class", "session", "term"]
    },
    "academics.formteacherassignment": {"lookup_fields": ["teacher", "academic_class", "session"]},
    "academics.studentclassenrollment": {"lookup_fields": ["student", "academic_class", "session"]},
    "academics.studentsubjectenrollment": {"lookup_fields": ["student", "subject", "session"]},
    "academics.sessionpromotionrecord": {"lookup_fields": ["session", "student"]},
    "attendance.schoolcalendar": {"lookup_fields": ["term"]},
    "attendance.holiday": {"lookup_fields": ["calendar", "date"]},
    "attendance.attendancerecord": {"lookup_fields": ["calendar", "academic_class", "student", "date"]},
    "audit.auditevent": {},
    "dashboard.principalsignature": {"lookup_fields": ["user"]},
    "dashboard.schoolprofile": {"lookup_fields": ["singleton_key"]},
    "dashboard.club": {"lookup_fields": ["code"]},
    "dashboard.studentclubmembership": {"lookup_fields": ["student", "club", "session"]},
    "elections.election": {"lookup_fields": ["title", "session"]},
    "elections.position": {"lookup_fields": ["election", "name"]},
    "elections.candidate": {"lookup_fields": ["position", "user"]},
    "elections.votergroup": {"lookup_fields": ["election", "name"]},
    "elections.electionresultartifact": {},
    "finance.financeinstitutionprofile": {"lookup_fields": ["singleton_key"]},
    "finance.studentcharge": {},
    "finance.payment": {},
    "finance.receipt": {"lookup_fields": ["receipt_number"]},
    "finance.expense": {},
    "finance.salaryrecord": {"lookup_fields": ["staff", "month"]},
    "finance.paymentgatewaytransaction": {"lookup_fields": ["reference"]},
    "finance.financereminderdispatch": {
        "lookup_fields": ["student", "session", "term", "reminder_date", "reminder_type"]
    },
    "finance.inventoryasset": {"lookup_fields": ["asset_code"]},
    "finance.inventoryassetmovement": {},
    "notifications.notification": {},
    "pdfs.pdfartifact": {},
    "pdfs.transcriptsessionrecord": {"lookup_fields": ["student", "session"]},
    "results.resultsheet": {"lookup_fields": ["academic_class", "subject", "session", "term"]},
    "results.resultsubmission": {},
    "results.studentsubjectscore": {"lookup_fields": ["result_sheet", "student"]},
    "results.behaviormetricsetting": {"lookup_fields": ["code"]},
    "results.classresultcompilation": {"lookup_fields": ["academic_class", "session", "term"]},
    "results.classresultstudentrecord": {"lookup_fields": ["compilation", "student"]},
    "results.resultaccesspin": {"lookup_fields": ["student", "session", "term"]},
    "setup_wizard.systemsetupstate": {"lookup_fields": ["singleton_id"]},
    "setup_wizard.runtimefeatureflags": {"lookup_fields": ["singleton_id"]},
}


def get_model_sync_config(model_or_label):
    label = model_or_label if isinstance(model_or_label, str) else model_or_label._meta.label_lower
    return GENERIC_MODEL_SYNC_CONFIG.get(label, {})


def is_generic_sync_model(model_or_label):
    return bool(get_model_sync_config(model_or_label))


def generic_sync_model_labels():
    return tuple(sorted(GENERIC_MODEL_SYNC_CONFIG.keys()))


def generic_sync_models():
    return [apps.get_model(label) for label in generic_sync_model_labels()]


def iter_synced_m2m_fields(model):
    config = get_model_sync_config(model)
    excluded = set(config.get("exclude_m2m_fields", []))
    for field in model._meta.many_to_many:
        if field.name in excluded:
            continue
        yield field


@contextmanager
def suppress_model_sync_capture():
    previous = bool(getattr(_THREAD_LOCAL, "suppress_model_sync_capture", False))
    _THREAD_LOCAL.suppress_model_sync_capture = True
    try:
        yield
    finally:
        _THREAD_LOCAL.suppress_model_sync_capture = previous


def is_model_sync_capture_suppressed():
    return bool(getattr(_THREAD_LOCAL, "suppress_model_sync_capture", False))


def _remote_high_stakes_sync_blocked(source_node_id):
    if not active_session_authority_enforced():
        return False
    if current_sync_node_role() != "LAN":
        return False
    normalized_source = (source_node_id or "").strip()
    if not normalized_source:
        return False
    return normalized_source != current_local_node_id()


def _identity_lookup_value(identity_payload, field_name):
    if not isinstance(identity_payload, dict):
        return None
    lookup_payload = identity_payload.get("lookup") or {}
    if not isinstance(lookup_payload, dict):
        return None
    return lookup_payload.get(field_name)


def _pk_to_string(value):
    if value is None:
        return ""
    return str(value)


def _ensure_binding(*, source_node_id, model_label, source_pk, local_pk):
    binding, _ = SyncModelBinding.objects.get_or_create(
        source_node_id=(source_node_id or "")[:80],
        model_label=(model_label or "")[:120],
        source_pk=(source_pk or "")[:120],
        defaults={"local_pk": (local_pk or "")[:120]},
    )
    local_pk_value = (local_pk or "")[:120]
    if binding.local_pk != local_pk_value:
        binding.local_pk = local_pk_value
        binding.save(update_fields=["local_pk", "updated_at"])
    return binding


def ensure_local_origin_binding(instance):
    model_label = instance._meta.label_lower
    local_pk = _pk_to_string(instance.pk)
    if not local_pk:
        raise ValidationError("Cannot bind unsaved model instance.")
    return _ensure_binding(
        source_node_id=current_local_node_id(),
        model_label=model_label,
        source_pk=local_pk,
        local_pk=local_pk,
    )


def _preferred_binding_for_instance(instance):
    model_label = instance._meta.label_lower
    local_pk = _pk_to_string(instance.pk)
    bindings = list(
        SyncModelBinding.objects.filter(model_label=model_label, local_pk=local_pk).order_by("created_at", "id")
    )
    if not bindings:
        bindings = [ensure_local_origin_binding(instance)]
    non_local = [row for row in bindings if row.source_node_id != current_local_node_id()]
    if non_local:
        return non_local[0]
    return bindings[0]


def _encode_file_field(file_field):
    if not file_field:
        return None
    try:
        file_field.open("rb")
        raw = file_field.read()
    except Exception:
        raw = b""
    finally:
        try:
            file_field.close()
        except Exception:
            pass
    mime_type = mimetypes.guess_type(getattr(file_field, "name", ""))[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii") if raw else ""
    return {
        "name": getattr(file_field, "name", "") or "",
        "content_type": mime_type,
        "data_url": f"data:{mime_type};base64,{encoded}" if encoded else "",
    }


def _decode_file_payload(payload, *, fallback_name):
    if payload in (None, ""):
        return None
    if not isinstance(payload, dict):
        raise ValidationError("Invalid synced file payload.")
    raw = (payload.get("data_url") or "").strip()
    original_name = (payload.get("name") or "").strip()
    if not raw:
        return {"name": original_name, "content": None}
    if ";base64," not in raw:
        raise ValidationError("Invalid synced file payload.")
    header, encoded = raw.split(";base64,", 1)
    mime_type = header.replace("data:", "").strip()
    extension = mimetypes.guess_extension(mime_type) or ""
    try:
        decoded = base64.b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError("Invalid synced file payload.") from exc
    file_name = original_name or f"{fallback_name}{extension}"
    return {"name": file_name, "content": ContentFile(decoded, name=file_name)}


def _serialize_lookup(instance):
    config = get_model_sync_config(instance)
    lookup_fields = config.get("lookup_fields", [])
    if not lookup_fields:
        return {}
    payload = {}
    for field_name in lookup_fields:
        field = instance._meta.get_field(field_name)
        payload[field_name] = _serialize_field_value(field, getattr(instance, field_name))
    return payload


def _serialize_identity(instance):
    binding = _preferred_binding_for_instance(instance)
    return {
        "model": instance._meta.label_lower,
        "source_node_id": binding.source_node_id,
        "source_pk": binding.source_pk,
        "lookup": _serialize_lookup(instance),
    }


def _serialize_field_value(field, value):
    if value is None:
        return None
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        return _serialize_identity(value)
    if isinstance(field, models.FileField):
        return _encode_file_field(value)
    if isinstance(field, models.DateTimeField):
        return value.isoformat()
    if isinstance(field, models.DateField):
        return value.isoformat()
    if isinstance(field, models.TimeField):
        return value.isoformat()
    if isinstance(field, models.DecimalField):
        return str(value)
    if isinstance(field, models.UUIDField):
        return str(value)
    return value


def serialize_generic_model_instance(instance):
    ensure_local_origin_binding(instance)
    fields_payload = {}
    config = get_model_sync_config(instance)
    excluded_fields = set(config.get("exclude_fields", []))
    for field in instance._meta.concrete_fields:
        if field.primary_key or field.name in excluded_fields:
            continue
        fields_payload[field.name] = _serialize_field_value(field, getattr(instance, field.name))

    m2m_payload = {}
    for field in iter_synced_m2m_fields(instance._meta.model):
        rows = sorted(getattr(instance, field.name).all(), key=lambda row: str(row.pk))
        m2m_payload[field.name] = [_serialize_identity(row) for row in rows]

    return {
        "model": instance._meta.label_lower,
        "identity": _serialize_identity(instance),
        "fields": fields_payload,
        "m2m": m2m_payload,
        "created_at": instance.created_at.isoformat() if getattr(instance, "created_at", None) else "",
        "updated_at": instance.updated_at.isoformat() if getattr(instance, "updated_at", None) else "",
    }


def _build_queue_payload(*, operation_type, payload):
    object_identity = payload.get("identity") or {}
    conflict_key = (
        f"{payload.get('model', '')}:{object_identity.get('source_node_id', '')}:{object_identity.get('source_pk', '')}"
    )[:120]
    idempotency_key = build_idempotency_key(
        operation_type=operation_type,
        payload=payload,
        object_ref=conflict_key,
        conflict_key=conflict_key,
    )
    return {
        "operation_type": operation_type,
        "payload": payload,
        "object_ref": conflict_key,
        "source_portal": "platform",
        "idempotency_key": idempotency_key,
        "conflict_rule": SyncConflictRule.LAST_WRITE_WINS,
        "conflict_key": conflict_key,
    }


def queue_generic_model_change(*, instance=None, operation="UPSERT", payload_override=None):
    payload = payload_override
    if payload is None:
        if instance is None or not is_generic_sync_model(instance):
            return None
        payload = serialize_generic_model_instance(instance)
    operation_type = (
        SyncOperationType.MODEL_RECORD_DELETE
        if operation == "DELETE"
        else SyncOperationType.MODEL_RECORD_UPSERT
    )
    queue_kwargs = _build_queue_payload(operation_type=operation_type, payload=payload)
    return queue_sync_operation(**queue_kwargs)


def _parse_scalar_field(field, value):
    if value is None:
        return None
    if isinstance(field, models.DateTimeField):
        return parse_datetime(str(value).replace("Z", "+00:00"))
    if isinstance(field, models.DateField):
        return parse_date(str(value))
    if isinstance(field, models.TimeField):
        return parse_time(str(value))
    if isinstance(field, models.DecimalField):
        return Decimal(str(value))
    if isinstance(field, models.UUIDField):
        return uuid.UUID(str(value))
    return value


def _find_instance_by_lookup(model, lookup_payload):
    if not isinstance(lookup_payload, dict) or not lookup_payload:
        return None
    config = get_model_sync_config(model)
    lookup_fields = config.get("lookup_fields", [])
    if not lookup_fields:
        return None
    resolved = {}
    for field_name in lookup_fields:
        if field_name not in lookup_payload:
            return None
        field = model._meta.get_field(field_name)
        raw_value = lookup_payload[field_name]
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            related_model_label = field.related_model._meta.label_lower
            related = _resolve_identity(related_model_label, raw_value, allow_missing=True)
            if related is None:
                return None
            resolved[field_name] = related
        else:
            resolved[field_name] = _parse_scalar_field(field, raw_value)
    return model.objects.filter(**resolved).first()


def _resolve_identity(model_label, identity_payload, *, allow_missing=False):
    if not isinstance(identity_payload, dict):
        if allow_missing:
            return None
        raise ValidationError("Invalid sync identity payload.")
    model = apps.get_model(model_label)
    source_node_id = (identity_payload.get("source_node_id") or "").strip()
    source_pk = (identity_payload.get("source_pk") or "").strip()
    binding = SyncModelBinding.objects.filter(
        source_node_id=source_node_id,
        model_label=model_label,
        source_pk=source_pk,
    ).first()
    if binding:
        instance = model.objects.filter(pk=binding.local_pk).first()
        if instance is not None:
            return instance
        binding.delete()

    lookup_payload = identity_payload.get("lookup") or {}
    instance = _find_instance_by_lookup(model, lookup_payload)
    if instance is not None:
        if source_node_id and source_pk:
            _ensure_binding(
                source_node_id=source_node_id,
                model_label=model_label,
                source_pk=source_pk,
                local_pk=_pk_to_string(instance.pk),
            )
        return instance

    if allow_missing:
        return None
    raise ValidationError("Dependency unavailable for synced relation.")


def _apply_field_values(instance, payload_fields):
    model = instance._meta.model
    for field_name, raw_value in (payload_fields or {}).items():
        field = model._meta.get_field(field_name)
        if isinstance(field, (models.ForeignKey, models.OneToOneField)):
            related_model_label = field.related_model._meta.label_lower
            setattr(instance, field_name, _resolve_identity(related_model_label, raw_value))
            continue
        if isinstance(field, models.FileField):
            file_payload = _decode_file_payload(
                raw_value,
                fallback_name=f"sync-{instance._meta.model_name}-{field_name}",
            )
            if file_payload is None:
                setattr(instance, field.name, None)
            elif file_payload["content"] is not None:
                getattr(instance, field.name).save(file_payload["name"], file_payload["content"], save=False)
            continue
        setattr(instance, field_name, _parse_scalar_field(field, raw_value))


def _apply_m2m_values(instance, payload_m2m):
    model = instance._meta.model
    for field_name, raw_values in (payload_m2m or {}).items():
        field = model._meta.get_field(field_name)
        related_model_label = field.related_model._meta.label_lower
        resolved_rows = []
        for raw_value in raw_values or []:
            resolved_rows.append(_resolve_identity(related_model_label, raw_value))
        getattr(instance, field_name).set(resolved_rows)


def _apply_timestamps(instance, *, created_at_raw="", updated_at_raw=""):
    update_values = {}
    if hasattr(instance, "created_at") and created_at_raw:
        parsed = parse_datetime(str(created_at_raw).replace("Z", "+00:00"))
        if parsed is not None:
            update_values["created_at"] = parsed
    if hasattr(instance, "updated_at") and updated_at_raw:
        parsed = parse_datetime(str(updated_at_raw).replace("Z", "+00:00"))
        if parsed is not None:
            update_values["updated_at"] = parsed
    if update_values:
        instance.__class__.objects.filter(pk=instance.pk).update(**update_values)


def _local_open_election_for_payload(model_label, payload):
    from apps.elections.models import ElectionStatus

    if model_label not in {"elections.election", "elections.position", "elections.candidate", "elections.votergroup"}:
        return None

    identity_payload = payload.get("identity") or {}
    fields_payload = payload.get("fields") or {}

    if model_label == "elections.election":
        election = _resolve_identity(model_label, identity_payload, allow_missing=True)
        if election is not None and election.status == ElectionStatus.OPEN:
            return election
        return None

    election_identity = fields_payload.get("election") or _identity_lookup_value(identity_payload, "election")
    if model_label == "elections.candidate":
        position_identity = fields_payload.get("position") or _identity_lookup_value(identity_payload, "position")
        position = _resolve_identity("elections.position", position_identity, allow_missing=True)
        election = position.election if position is not None else None
    else:
        election = _resolve_identity("elections.election", election_identity, allow_missing=True)

    if election is not None and election.status == ElectionStatus.OPEN:
        return election
    return None


def apply_generic_model_payload(*, payload, operation_type):
    if not isinstance(payload, dict):
        raise ValidationError("Generic sync payload must be an object.")
    model_label = (payload.get("model") or "").strip().lower()
    if not is_generic_sync_model(model_label):
        raise ValidationError("Unsupported generic sync model.")
    model = apps.get_model(model_label)
    identity = payload.get("identity") or {}
    source_node_id = (identity.get("source_node_id") or "").strip()
    source_pk = (identity.get("source_pk") or "").strip()

    if _remote_high_stakes_sync_blocked(source_node_id):
        election = _local_open_election_for_payload(model_label, payload)
        if election is not None:
            raise ValidationError("Authority unavailable for active LAN election session. Retry later.")

    with suppress_model_sync_capture():
        instance = _resolve_identity(model_label, identity, allow_missing=True)
        if operation_type == SyncOperationType.MODEL_RECORD_DELETE:
            if instance is not None:
                instance.delete()
            return {"reference": f"{model_label}:{source_node_id}:{source_pk}", "deleted": True}

        if instance is None:
            pk_field = model._meta.pk
            if isinstance(pk_field, models.UUIDField) and source_pk:
                instance = model(pk=uuid.UUID(source_pk))
            else:
                instance = model()

        _apply_field_values(instance, payload.get("fields") or {})
        instance.save()
        if source_node_id and source_pk:
            _ensure_binding(
                source_node_id=source_node_id,
                model_label=model_label,
                source_pk=source_pk,
                local_pk=_pk_to_string(instance.pk),
            )
        _apply_m2m_values(instance, payload.get("m2m") or {})
        _apply_timestamps(
            instance,
            created_at_raw=payload.get("created_at") or "",
            updated_at_raw=payload.get("updated_at") or "",
        )
    return {"reference": f"{model_label}:{instance.pk}"}
