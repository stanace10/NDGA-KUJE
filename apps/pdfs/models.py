from django.conf import settings
from django.db import models

from apps.academics.models import AcademicSession, Term
from apps.results.models import ClassResultCompilation
from core.models import TimeStampedModel, UUIDPrimaryKeyModel


class PDFDocumentType(models.TextChoices):
    TERM_REPORT = "TERM_REPORT", "Term Report"
    TRANSCRIPT = "TRANSCRIPT", "Transcript"
    PERFORMANCE_ANALYSIS = "PERFORMANCE_ANALYSIS", "Performance Analysis"


class PDFArtifact(UUIDPrimaryKeyModel, TimeStampedModel):
    document_type = models.CharField(max_length=24, choices=PDFDocumentType.choices)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pdf_artifacts",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdf_artifacts",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdf_artifacts",
    )
    compilation = models.ForeignKey(
        ClassResultCompilation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pdf_artifacts",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_pdf_artifacts",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    payload_hash = models.CharField(max_length=64)
    source_label = models.CharField(max_length=180, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("document_type", "student", "created_at")),
            models.Index(fields=("payload_hash",)),
        ]

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.student.username} ({self.created_at:%Y-%m-%d})"


class TranscriptSessionRecord(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transcript_session_records",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="transcript_records",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_transcript_session_records",
    )
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    source_compilation_count = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("session__name", "student__username")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "session"),
                name="unique_transcript_session_record_per_student_session",
            )
        ]
        indexes = [
            models.Index(fields=("student", "session")),
            models.Index(fields=("payload_hash",)),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.session.name}"
