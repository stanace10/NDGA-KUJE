from __future__ import annotations

import logging
from threading import local

from django.db import transaction
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.db.utils import OperationalError, ProgrammingError

from apps.sync.model_sync import (
    generic_sync_models,
    is_generic_sync_model,
    is_model_sync_capture_suppressed,
    iter_synced_m2m_fields,
    queue_generic_model_change,
    serialize_generic_model_instance,
)

logger = logging.getLogger(__name__)
_THREAD_LOCAL = local()
_M2M_HANDLERS = []
_CONNECTED = False


def _preclear_cache():
    cache = getattr(_THREAD_LOCAL, "preclear_cache", None)
    if cache is None:
        cache = {}
        _THREAD_LOCAL.preclear_cache = cache
    return cache


def _preclear_key(*, sender, instance, reverse, field_name):
    return f"{sender._meta.label_lower}:{field_name}:{instance.pk}:{int(bool(reverse))}"


def _safe_queue_instance(*, instance=None, operation="UPSERT", payload_override=None):
    if instance is not None and not is_generic_sync_model(instance):
        return
    try:
        queue_generic_model_change(
            instance=instance,
            operation=operation,
            payload_override=payload_override,
        )
    except (ProgrammingError, OperationalError) as exc:
        logger.warning("Skipped generic sync queue capture: %s", exc)


def capture_generic_upsert(sender, instance, raw=False, **kwargs):
    if raw or is_model_sync_capture_suppressed() or not is_generic_sync_model(sender):
        return
    transaction.on_commit(lambda: _safe_queue_instance(instance=instance, operation="UPSERT"))


def capture_generic_delete(sender, instance, **kwargs):
    if is_model_sync_capture_suppressed() or not is_generic_sync_model(sender):
        return
    try:
        payload = serialize_generic_model_instance(instance)
    except (ProgrammingError, OperationalError) as exc:
        logger.warning("Skipped generic sync delete capture: %s", exc)
        return
    transaction.on_commit(
        lambda payload=payload: _safe_queue_instance(
            operation="DELETE",
            payload_override=payload,
        )
    )


def _queue_many(instances):
    for row in instances:
        _safe_queue_instance(instance=row, operation="UPSERT")


def _make_m2m_handler(source_model, field_name):
    def handle_m2m_change(sender, instance, action, reverse, model, pk_set, **kwargs):
        if is_model_sync_capture_suppressed():
            return
        cache_key = _preclear_key(
            sender=sender,
            instance=instance,
            reverse=reverse,
            field_name=field_name,
        )
        if action == "pre_clear":
            cache = _preclear_cache()
            if reverse:
                impacted = list(
                    source_model.objects.filter(**{field_name: instance}).values_list("pk", flat=True)
                )
            else:
                impacted = [instance.pk] if instance.pk is not None else []
            cache[cache_key] = impacted
            return
        if action not in {"post_add", "post_remove", "post_clear"}:
            return
        if reverse:
            if action == "post_clear":
                impacted_pks = _preclear_cache().pop(cache_key, [])
            else:
                impacted_pks = list(pk_set or [])
            if not impacted_pks:
                return
            transaction.on_commit(
                lambda impacted_pks=tuple(impacted_pks): _queue_many(
                    source_model.objects.filter(pk__in=impacted_pks)
                )
            )
            return
        transaction.on_commit(lambda: _safe_queue_instance(instance=instance, operation="UPSERT"))

    return handle_m2m_change


def connect_generic_sync_signals():
    global _CONNECTED
    if _CONNECTED:
        return
    for model in generic_sync_models():
        label = model._meta.label_lower.replace(".", "-")
        post_save.connect(
            capture_generic_upsert,
            sender=model,
            dispatch_uid=f"sync-generic-upsert-{label}",
            weak=False,
        )
        pre_delete.connect(
            capture_generic_delete,
            sender=model,
            dispatch_uid=f"sync-generic-delete-{label}",
            weak=False,
        )
        for field in iter_synced_m2m_fields(model):
            handler = _make_m2m_handler(model, field.name)
            _M2M_HANDLERS.append(handler)
            m2m_changed.connect(
                handler,
                sender=field.remote_field.through,
                dispatch_uid=f"sync-generic-m2m-{label}-{field.name}",
                weak=False,
            )
    _CONNECTED = True


connect_generic_sync_signals()
