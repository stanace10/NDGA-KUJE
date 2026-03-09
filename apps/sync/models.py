from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class SyncOperationType(models.TextChoices):
    CBT_EXAM_ATTEMPT = "CBT_EXAM_ATTEMPT", "CBT Exam Attempt"
    CBT_SIMULATION_ATTEMPT = "CBT_SIMULATION_ATTEMPT", "CBT Simulation Attempt"
    CBT_CONTENT_CHANGE = "CBT_CONTENT_CHANGE", "CBT Content Change"
    STUDENT_REGISTRATION_UPSERT = "STUDENT_REGISTRATION_UPSERT", "Student Registration Upsert"
    ELECTION_VOTE_SUBMISSION = "ELECTION_VOTE_SUBMISSION", "Election Vote Submission"
    MODEL_RECORD_UPSERT = "MODEL_RECORD_UPSERT", "Model Record Upsert"
    MODEL_RECORD_DELETE = "MODEL_RECORD_DELETE", "Model Record Delete"


class SyncQueueStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RETRY = "RETRY", "Retry Scheduled"
    SYNCED = "SYNCED", "Synced"
    FAILED = "FAILED", "Failed"
    CONFLICT = "CONFLICT", "Conflict"


class SyncConflictRule(models.TextChoices):
    APPEND_ONLY = "APPEND_ONLY", "Append Only"
    LAST_WRITE_WINS = "LAST_WRITE_WINS", "Last Write Wins"
    STRICT_UNIQUE = "STRICT_UNIQUE", "Strict Unique"


class SyncTransferDirection(models.TextChoices):
    EXPORT = "EXPORT", "Export"
    IMPORT = "IMPORT", "Import"


class SyncContentStream(models.TextChoices):
    CBT_CONTENT = "CBT_CONTENT", "CBT Content"
    OUTBOX_EVENTS = "OUTBOX_EVENTS", "Outbox Events"


class SyncContentOperation(models.TextChoices):
    UPSERT = "UPSERT", "Upsert"
    DELETE = "DELETE", "Delete"


class SyncContentObjectType(models.TextChoices):
    QUESTION_BANK = "QUESTION_BANK", "Question Bank"
    QUESTION = "QUESTION", "Question"
    OPTION = "OPTION", "Option"
    CORRECT_ANSWER = "CORRECT_ANSWER", "Correct Answer"
    EXAM = "EXAM", "Exam"
    EXAM_BLUEPRINT = "EXAM_BLUEPRINT", "Exam Blueprint"
    EXAM_QUESTION = "EXAM_QUESTION", "Exam Question"
    SIMULATION_WRAPPER = "SIMULATION_WRAPPER", "Simulation Wrapper"
    EXAM_SIMULATION = "EXAM_SIMULATION", "Exam Simulation"


class SyncQueue(TimeStampedModel):
    operation_type = models.CharField(
        max_length=40,
        choices=SyncOperationType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=SyncQueueStatus.choices,
        default=SyncQueueStatus.PENDING,
    )
    payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    conflict_rule = models.CharField(
        max_length=20,
        choices=SyncConflictRule.choices,
        default=SyncConflictRule.APPEND_ONLY,
    )
    conflict_key = models.CharField(max_length=120, blank=True, db_index=True)
    object_ref = models.CharField(max_length=120, blank=True, db_index=True)
    source_portal = models.CharField(max_length=32, blank=True)
    local_node_id = models.CharField(max_length=80, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=8)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    response_code = models.PositiveIntegerField(null=True, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    remote_reference = models.CharField(max_length=150, blank=True)
    last_error = models.TextField(blank=True)
    is_manual_import = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("status", "next_retry_at")),
            models.Index(fields=("operation_type", "status")),
            models.Index(fields=("created_at",)),
        ]

    def __str__(self):
        return f"{self.operation_type}:{self.status}:{self.idempotency_key}"


class SyncContentChange(TimeStampedModel):
    stream = models.CharField(
        max_length=32,
        choices=SyncContentStream.choices,
        default=SyncContentStream.CBT_CONTENT,
    )
    object_type = models.CharField(max_length=40, choices=SyncContentObjectType.choices)
    operation = models.CharField(
        max_length=16,
        choices=SyncContentOperation.choices,
        default=SyncContentOperation.UPSERT,
    )
    object_pk = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    source_node_id = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ("id",)
        indexes = [
            models.Index(fields=("stream", "id")),
            models.Index(fields=("object_type", "object_pk")),
        ]

    def __str__(self):
        return f"{self.stream}:{self.object_type}:{self.operation}:{self.object_pk}"


class SyncPullCursor(TimeStampedModel):
    stream = models.CharField(max_length=32, choices=SyncContentStream.choices, unique=True)
    last_remote_id = models.BigIntegerField(default=0)
    last_pull_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("stream",)

    def __str__(self):
        return f"{self.stream}:#{self.last_remote_id}"


class SyncModelBinding(TimeStampedModel):
    source_node_id = models.CharField(max_length=80)
    model_label = models.CharField(max_length=120)
    source_pk = models.CharField(max_length=120)
    local_pk = models.CharField(max_length=120, db_index=True)

    class Meta:
        ordering = ("model_label", "source_node_id", "source_pk")
        constraints = [
            models.UniqueConstraint(
                fields=("source_node_id", "model_label", "source_pk"),
                name="unique_sync_model_binding_source_ref",
            )
        ]
        indexes = [
            models.Index(fields=("model_label", "local_pk")),
        ]

    def __str__(self):
        return f"{self.model_label}:{self.source_node_id}:{self.source_pk}->{self.local_pk}"


class SyncTransferBatch(TimeStampedModel):
    direction = models.CharField(max_length=12, choices=SyncTransferDirection.choices)
    file_name = models.CharField(max_length=255)
    item_count = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=128, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_transfer_batches",
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("direction", "created_at"))]

    def __str__(self):
        return f"{self.direction}:{self.file_name}"
