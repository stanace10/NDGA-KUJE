from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class NotificationCategory(models.TextChoices):
    RESULTS = "RESULTS", "Results"
    PAYMENT = "PAYMENT", "Payment"
    ELECTION = "ELECTION", "Election"
    SYSTEM = "SYSTEM", "System"


class Notification(UUIDPrimaryKeyModel, TimeStampedModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    category = models.CharField(
        max_length=24,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
    )
    title = models.CharField(max_length=180)
    message = models.TextField()
    action_url = models.CharField(max_length=300, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_notifications",
    )
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("recipient", "read_at", "created_at")),
            models.Index(fields=("category", "created_at")),
        ]

    @property
    def is_read(self):
        return self.read_at is not None

    def mark_read(self):
        if self.read_at is None:
            self.read_at = timezone.now()
            self.save(update_fields=["read_at", "updated_at"])

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"
