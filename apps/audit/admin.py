from django.contrib import admin

from apps.audit.models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "category",
        "event_type",
        "status",
        "actor",
        "actor_identifier",
    )
    list_filter = ("category", "status", "event_type")
    search_fields = ("actor__username", "actor_identifier", "event_type", "message")
    readonly_fields = (
        "created_at",
        "updated_at",
        "category",
        "event_type",
        "status",
        "actor",
        "actor_identifier",
        "message",
        "path",
        "ip_address",
        "metadata",
    )

