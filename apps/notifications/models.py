from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class NotificationCategory(models.TextChoices):
    RESULTS = "RESULTS", "Results"
    PAYMENT = "PAYMENT", "Payment"
    BIRTHDAY = "BIRTHDAY", "Birthday"
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


class EmailThreadScope(models.TextChoices):
    GENERAL = "GENERAL", "General"
    FINANCE = "FINANCE", "Finance"


class EmailReplyThread(UUIDPrimaryKeyModel, TimeStampedModel):
    thread_key = models.CharField(max_length=32, unique=True)
    scope = models.CharField(
        max_length=16,
        choices=EmailThreadScope.choices,
        default=EmailThreadScope.GENERAL,
    )
    subject = models.CharField(max_length=180)
    recipient_email = models.EmailField()
    recipient_label = models.CharField(max_length=180, blank=True)
    reply_to_email = models.EmailField(unique=True)
    source_event = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_email_reply_threads",
    )
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-last_message_at", "-created_at")
        indexes = [
            models.Index(fields=("scope", "last_message_at")),
            models.Index(fields=("recipient_email", "last_message_at")),
            models.Index(fields=("source_event", "last_message_at")),
        ]

    def __str__(self):
        return f"{self.recipient_email} - {self.subject}"


class EmailReplyMessageDirection(models.TextChoices):
    OUTBOUND = "OUTBOUND", "Outbound"
    INBOUND = "INBOUND", "Inbound"


class EmailReplyMessage(UUIDPrimaryKeyModel, TimeStampedModel):
    thread = models.ForeignKey(
        EmailReplyThread,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    direction = models.CharField(max_length=16, choices=EmailReplyMessageDirection.choices)
    provider = models.CharField(max_length=32, blank=True)
    external_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    in_reply_to_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    sender_email = models.EmailField(blank=True)
    sender_name = models.CharField(max_length=180, blank=True)
    recipient_email = models.EmailField(blank=True)
    subject = models.CharField(max_length=180)
    body_text = models.TextField(blank=True)
    body_html = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    extracted_signature = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    headers = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_email_reply_messages",
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("thread", "created_at")),
            models.Index(fields=("direction", "created_at")),
            models.Index(fields=("received_at",)),
        ]

    def __str__(self):
        return f"{self.thread.recipient_email} - {self.direction} - {self.subject}"


class BirthdayContactType(models.TextChoices):
    PARENT = "PARENT", "Parent"
    STAFF = "STAFF", "Staff"


class BirthdayDispatchStatus(models.TextChoices):
    SENT = "SENT", "Sent"
    SKIPPED = "SKIPPED", "Skipped"
    FAILED = "FAILED", "Failed"


class BirthdayContact(TimeStampedModel):
    contact_type = models.CharField(
        max_length=12,
        choices=BirthdayContactType.choices,
        default=BirthdayContactType.PARENT,
    )
    full_name = models.CharField(max_length=180)
    birth_month = models.PositiveSmallIntegerField()
    birth_day = models.PositiveSmallIntegerField()
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=80, blank=True)
    student_name = models.CharField(max_length=180, blank=True)
    student_admission_no = models.CharField(max_length=40, blank=True)
    source_label = models.CharField(max_length=180, blank=True)
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="birthday_contacts",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("birth_month", "birth_day", "full_name")
        constraints = [
            models.UniqueConstraint(
                fields=("contact_type", "full_name", "birth_month", "birth_day"),
                name="unique_birthday_contact_day",
            ),
        ]
        indexes = [
            models.Index(fields=("contact_type", "birth_month", "birth_day", "is_active"), name="notificatio_contact_927368_idx"),
            models.Index(fields=("email",), name="notificatio_email_9d18b4_idx"),
            models.Index(fields=("phone",), name="notificatio_phone_af7d17_idx"),
        ]

    def clean(self):
        self.full_name = (self.full_name or "").strip()
        self.email = (self.email or "").strip().lower()
        self.phone = (self.phone or "").strip()
        self.student_name = (self.student_name or "").strip()
        self.student_admission_no = (self.student_admission_no or "").strip().upper()
        self.source_label = (self.source_label or "").strip()

    def __str__(self):
        return f"{self.full_name} ({self.birth_month:02d}/{self.birth_day:02d})"


class BirthdayDispatch(TimeStampedModel):
    contact = models.ForeignKey(
        BirthdayContact,
        on_delete=models.CASCADE,
        related_name="dispatches",
    )
    birthday_year = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12,
        choices=BirthdayDispatchStatus.choices,
        default=BirthdayDispatchStatus.SENT,
    )
    sent_email = models.BooleanField(default=False)
    sent_whatsapp = models.BooleanField(default=False)
    message_subject = models.CharField(max_length=180, blank=True)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    dispatched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-dispatched_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("contact", "birthday_year"),
                name="unique_birthday_dispatch_year",
            ),
        ]
        indexes = [
            models.Index(fields=("birthday_year", "status"), name="notificatio_birthda_5bf61e_idx"),
            models.Index(fields=("dispatched_at",), name="notificatio_dispatc_b2f630_idx"),
        ]

    def __str__(self):
        return f"{self.contact} - {self.birthday_year} - {self.status}"
