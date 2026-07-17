from __future__ import annotations

from django.conf import settings

from apps.results.models import ClassCompilationStatus, ResultSheetStatus
from apps.sync.models import SyncOperationType

RESULT_PUBLICATION_MODEL_LABELS = {
    "results.resultsheet",
    "results.studentsubjectscore",
    "results.classresultcompilation",
    "results.classresultstudentrecord",
    "results.resultaccesspin",
}


def lan_results_only_mode_enabled():
    node_role = (getattr(settings, "SYNC_NODE_ROLE", "CLOUD") or "CLOUD").strip().upper()
    return bool(getattr(settings, "SYNC_LAN_RESULTS_ONLY_MODE", False) and node_role == "LAN")


def generic_model_sync_allowed_for_instance(instance):
    if not lan_results_only_mode_enabled():
        return True
    if instance is None:
        return False
    model_label = instance._meta.label_lower
    if model_label not in RESULT_PUBLICATION_MODEL_LABELS:
        return False
    if model_label == "results.resultsheet":
        return instance.status == ResultSheetStatus.PUBLISHED
    if model_label == "results.studentsubjectscore":
        return getattr(instance.result_sheet, "status", "") == ResultSheetStatus.PUBLISHED
    if model_label == "results.classresultcompilation":
        return instance.status == ClassCompilationStatus.PUBLISHED
    if model_label == "results.classresultstudentrecord":
        return getattr(instance.compilation, "status", "") == ClassCompilationStatus.PUBLISHED
    if model_label == "results.resultaccesspin":
        return True
    return False


def _payload_model_label(payload):
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("model") or "").strip().lower()


def _resolve_related_instance(model_label, identity_payload):
    if not isinstance(identity_payload, dict):
        return None
    try:
        from apps.sync.model_sync import _resolve_identity

        return _resolve_identity(model_label, identity_payload, allow_missing=True)
    except Exception:
        return None


def generic_model_sync_allowed_for_payload(payload):
    if not lan_results_only_mode_enabled():
        return True
    model_label = _payload_model_label(payload)
    if model_label not in RESULT_PUBLICATION_MODEL_LABELS:
        return False
    fields_payload = payload.get("fields") or {}
    if model_label == "results.resultsheet":
        return fields_payload.get("status") == ResultSheetStatus.PUBLISHED
    if model_label == "results.studentsubjectscore":
        result_sheet = _resolve_related_instance("results.resultsheet", fields_payload.get("result_sheet"))
        return getattr(result_sheet, "status", "") == ResultSheetStatus.PUBLISHED
    if model_label == "results.classresultcompilation":
        return fields_payload.get("status") == ClassCompilationStatus.PUBLISHED
    if model_label == "results.classresultstudentrecord":
        compilation = _resolve_related_instance(
            "results.classresultcompilation",
            fields_payload.get("compilation"),
        )
        return getattr(compilation, "status", "") == ClassCompilationStatus.PUBLISHED
    if model_label == "results.resultaccesspin":
        return True
    return False


def outbound_queue_row_allowed(queue_row):
    if not lan_results_only_mode_enabled():
        return True
    if queue_row.operation_type not in {
        SyncOperationType.MODEL_RECORD_UPSERT,
        SyncOperationType.MODEL_RECORD_DELETE,
    }:
        return False
    return generic_model_sync_allowed_for_payload(queue_row.payload or {})


def inbound_remote_outbox_allowed():
    return not lan_results_only_mode_enabled()
