from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class AuditCategory(models.TextChoices):
    AUTH = "AUTH", "Authentication"
    PERMISSION = "PERMISSION", "Permission"
    RESULTS = "RESULTS", "Results"
    CBT = "CBT", "CBT"
    ELECTION = "ELECTION", "Election"
    FINANCE = "FINANCE", "Finance"
    LOCKDOWN = "LOCKDOWN", "Lockdown"
    SYSTEM = "SYSTEM", "System"


class AuditStatus(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    FAILURE = "FAILURE", "Failure"
    DENIED = "DENIED", "Denied"


class AuditEvent(TimeStampedModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor_identifier = models.CharField(max_length=150, blank=True)
    category = models.CharField(max_length=24, choices=AuditCategory.choices)
    event_type = models.CharField(max_length=64)
    status = models.CharField(max_length=24, choices=AuditStatus.choices)
    message = models.TextField(blank=True)
    path = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    previous_event_hash = models.CharField(max_length=64, blank=True)
    event_hash = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("category", "event_type")),
            models.Index(fields=("created_at",)),
        ]

    def __str__(self):
        actor = self.actor.username if self.actor else self.actor_identifier or "unknown"
        return f"{self.category}:{self.event_type}:{actor}"