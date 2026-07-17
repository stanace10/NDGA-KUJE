from django.contrib import admin

from apps.sync.models import (
    SyncContentChange,
    SyncPullCursor,
    SyncQueue,
    SyncTransferBatch,
)


@admin.register(SyncQueue)
class SyncQueueAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "operation_type",
        "status",
        "object_ref",
        "idempotency_key",
        "retry_count",
        "next_retry_at",
        "synced_at",
    )
    list_filter = ("operation_type", "status", "conflict_rule", "source_portal")
    search_fields = ("idempotency_key", "object_ref", "conflict_key", "remote_reference")
    readonly_fields = (
        "created_at",
        "updated_at",
        "synced_at",
        "last_attempt_at",
    )


@admin.register(SyncTransferBatch)
class SyncTransferBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "direction", "file_name", "item_count", "performed_by", "created_at")
    list_filter = ("direction",)
    search_fields = ("file_name", "checksum")


@admin.register(SyncContentChange)
class SyncContentChangeAdmin(admin.ModelAdmin):
    list_display = ("id", "stream", "object_type", "operation", "object_pk", "source_node_id", "created_at")
    list_filter = ("stream", "object_type", "operation")
    search_fields = ("object_pk", "source_node_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SyncPullCursor)
class SyncPullCursorAdmin(admin.ModelAdmin):
    list_display = ("stream", "last_remote_id", "last_pull_at", "last_success_at")
    readonly_fields = ("created_at", "updated_at")
