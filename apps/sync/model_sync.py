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
from apps.sync.policies import (
    generic_model_sync_allowed_for_instance,
    generic_model_sync_allowed_for_payload,
)
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
    "dashboard.publicsitesubmission": {},
    "dashboard.publicadmissionpaymenttransaction": {"lookup_fields": ["reference"]},
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
        if not generic_model_sync_allowed_for_instance(instance):
            return None
        payload = serialize_generic_model_instance(instance)
    elif not generic_model_sync_allowed_for_payload(payload):
        return None
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


def _materialize_instance_from_lookup(model_label, lookup_payload):
    if model_label != "results.resultsheet":
        return None
    if not isinstance(lookup_payload, dict) or not lookup_payload:
        return None

    academic_class = _resolve_identity(
        "academics.academicclass",
        lookup_payload.get("academic_class"),
        allow_missing=True,
    )
    subject = _resolve_identity(
        "academics.subject",
        lookup_payload.get("subject"),
        allow_missing=True,
    )
    session = _resolve_identity(
        "academics.academicsession",
        lookup_payload.get("session"),
        allow_missing=True,
    )
    term = _resolve_identity(
        "academics.term",
        lookup_payload.get("term"),
        allow_missing=True,
    )
    if not all([academic_class, subject, session, term]):
        return None
    if getattr(term, "session_id", None) != getattr(session, "id", None):
        return None

    model = apps.get_model(model_label)
    with suppress_model_sync_capture():
        instance, _ = model.objects.get_or_create(
            academic_class=academic_class,
            subject=subject,
            session=session,
            term=term,
        )
    return instance


def _match_existing_student_subject_score(payload):
    if not isinstance(payload, dict):
        return None

    fields_payload = payload.get("fields") or {}
    result_sheet_identity = fields_payload.get("result_sheet")
    student_identity = fields_payload.get("student")
    if not result_sheet_identity or not student_identity:
        return None

    result_sheet = _resolve_identity(
        "results.resultsheet",
        result_sheet_identity,
        allow_missing=True,
    )
    student = _resolve_identity(
        "accounts.user",
        student_identity,
        allow_missing=True,
    )
    if result_sheet is None or student is None:
        return None

    model = apps.get_model("results.studentsubjectscore")
    return model.objects.filter(result_sheet=result_sheet, student=student).first()


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
            lookup_payload = identity_payload.get("lookup") or {}
            if lookup_payload:
                matched = _find_instance_by_lookup(model, lookup_payload)
                if matched is not None and matched.pk != instance.pk:
                    binding.local_pk = _pk_to_string(matched.pk)
                    binding.save(update_fields=["local_pk", "updated_at"])
                    return matched
            return instance
        binding.delete()

    lookup_payload = identity_payload.get("lookup") or {}
    instance = _find_instance_by_lookup(model, lookup_payload)
    if instance is None:
        instance = _materialize_instance_from_lookup(model_label, lookup_payload)
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
            if raw_value in (None, ""):
                setattr(instance, field_name, None)
            else:
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


def _sync_direction_for_source(source_node_id):
    normalized_source = (source_node_id or "").strip()
    if not normalized_source or normalized_source == current_local_node_id():
        return ""
    if current_sync_node_role() == "CLOUD":
        return "LAN_TO_CLOUD"
    if current_sync_node_role() == "LAN":
        return "CLOUD_TO_LAN"
    return ""


def _normalized_score_breakdown(raw):
    if not isinstance(raw, dict):
        return {}
    normalized = {}
    for key, value in raw.items():
        name = str(key).strip()
        if not name:
            continue
        try:
            normalized[name] = str(Decimal(str(value)).quantize(Decimal("0.01")))
        except Exception:
            continue
    return normalized


def _score_decimal_text(value):
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01")))


def _score_decimal_value(value):
    return Decimal(_score_decimal_text(value))


def _snapshot_student_subject_score(instance):
    return {
        "ca1": _score_decimal_text(instance.ca1),
        "ca2": _score_decimal_text(instance.ca2),
        "ca3": _score_decimal_text(instance.ca3),
        "ca4": _score_decimal_text(instance.ca4),
        "objective": _score_decimal_text(instance.objective),
        "theory": _score_decimal_text(instance.theory),
        "has_override": bool(instance.has_override),
        "override_reason": instance.override_reason,
        "override_by": instance.override_by,
        "override_at": instance.override_at,
        "locked": set(instance.normalized_locked_fields()),
        "breakdown": instance.normalized_breakdown(),
    }


CBT_BREAKDOWN_FIELD_MAP = {
    "ca2_objective": "ca2",
    "objective_auto": "objective",
}


def _cbt_owned_components(*, locked_fields, breakdown):
    owned = set(locked_fields or [])
    for breakdown_key, component_field in CBT_BREAKDOWN_FIELD_MAP.items():
        if breakdown_key in (breakdown or {}):
            owned.add(component_field)
    return owned


def _merge_score_breakdown(
    *,
    local_breakdown,
    incoming_breakdown,
    direction,
    local_locked,
    incoming_locked,
):
    local_breakdown = dict(local_breakdown or {})
    incoming_breakdown = dict(incoming_breakdown or {})
    local_cbt_owned = _cbt_owned_components(locked_fields=local_locked, breakdown=local_breakdown)
    incoming_cbt_owned = _cbt_owned_components(locked_fields=incoming_locked, breakdown=incoming_breakdown)

    if direction == "LAN_TO_CLOUD":
        merged = dict(local_breakdown)
        if "ca2" in incoming_cbt_owned and "ca2_objective" in incoming_breakdown:
            merged["ca2_objective"] = incoming_breakdown["ca2_objective"]
        if "objective" in incoming_cbt_owned and "objective_auto" in incoming_breakdown:
            merged["objective_auto"] = incoming_breakdown["objective_auto"]
        return merged

    merged = dict(incoming_breakdown)
    if "ca2" in local_cbt_owned and "ca2_objective" in local_breakdown:
        merged["ca2_objective"] = local_breakdown["ca2_objective"]
    if "objective" in local_cbt_owned and "objective_auto" in local_breakdown:
        merged["objective_auto"] = local_breakdown["objective_auto"]
    return merged


def _merge_result_score_after_apply(*, instance, previous_state, source_node_id):
    direction = _sync_direction_for_source(source_node_id)
    if not direction or previous_state is None:
        return

    incoming_locked = set(instance.normalized_locked_fields())
    incoming_breakdown = instance.normalized_breakdown()
    previous_locked = previous_state["locked"]
    merged_breakdown = _merge_score_breakdown(
        local_breakdown=previous_state["breakdown"],
        incoming_breakdown=incoming_breakdown,
        direction=direction,
        local_locked=previous_locked,
        incoming_locked=incoming_locked,
    )
    previous_cbt_owned = _cbt_owned_components(
        locked_fields=previous_locked,
        breakdown=previous_state["breakdown"],
    )
    incoming_cbt_owned = _cbt_owned_components(
        locked_fields=incoming_locked,
        breakdown=incoming_breakdown,
    )

    if direction == "LAN_TO_CLOUD":
        instance.ca1 = _score_decimal_value(previous_state["ca1"])
        if "ca2" not in incoming_cbt_owned:
            instance.ca2 = _score_decimal_value(previous_state["ca2"])
        instance.ca3 = _score_decimal_value(previous_state["ca3"])
        instance.ca4 = _score_decimal_value(previous_state["ca4"])
        if "objective" not in incoming_cbt_owned:
            instance.objective = _score_decimal_value(previous_state["objective"])
        instance.theory = _score_decimal_value(previous_state["theory"])
        instance.has_override = previous_state["has_override"]
        instance.override_reason = previous_state["override_reason"]
        instance.override_by = previous_state["override_by"]
        instance.override_at = previous_state["override_at"]
    else:
        if "ca2" in previous_cbt_owned:
            instance.ca2 = _score_decimal_value(previous_state["ca2"])
        if "objective" in previous_cbt_owned:
            instance.objective = _score_decimal_value(previous_state["objective"])

    instance.cbt_component_breakdown = merged_breakdown
    instance.cbt_locked_fields = sorted(previous_locked | incoming_locked)


def _snapshot_result_sheet(instance):
    return {
        "status": instance.status,
        "created_by": instance.created_by,
        "cbt_component_policies": dict(instance.cbt_component_policies or {}),
    }


def _merge_result_sheet_after_apply(*, instance, previous_state, source_node_id):
    direction = _sync_direction_for_source(source_node_id)
    if not direction or previous_state is None:
        return
    if direction == "LAN_TO_CLOUD":
        instance.status = previous_state["status"]
        instance.created_by = previous_state["created_by"]
    elif previous_state["cbt_component_policies"] and not instance.cbt_component_policies:
        instance.cbt_component_policies = previous_state["cbt_component_policies"]


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

        previous_score_state = None
        previous_sheet_state = None
        if instance is not None and model_label == "results.studentsubjectscore":
            previous_score_state = _snapshot_student_subject_score(instance)
        elif instance is not None and model_label == "results.resultsheet":
            previous_sheet_state = _snapshot_result_sheet(instance)

        if instance is None:
            if model_label == "results.studentsubjectscore":
                instance = _match_existing_student_subject_score(payload)
                if instance is not None:
                    previous_score_state = _snapshot_student_subject_score(instance)

        if instance is None:
            pk_field = model._meta.pk
            if isinstance(pk_field, models.UUIDField) and source_pk:
                instance = model(pk=uuid.UUID(source_pk))
            else:
                instance = model()

        _apply_field_values(instance, payload.get("fields") or {})
        if model_label == "results.studentsubjectscore":
            _merge_result_score_after_apply(
                instance=instance,
                previous_state=previous_score_state,
                source_node_id=source_node_id,
            )
        elif model_label == "results.resultsheet":
            _merge_result_sheet_after_apply(
                instance=instance,
                previous_state=previous_sheet_state,
                source_node_id=source_node_id,
            )
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
