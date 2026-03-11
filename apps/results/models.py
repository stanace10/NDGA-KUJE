from django.conf import settings
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.academics.models import AcademicClass, AcademicSession, Subject, Term
from apps.attendance.services import compute_student_attendance_percentage
from apps.results.services import compute_grade_payload
from core.models import TimeStampedModel


class ResultSheetStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED_TO_DEAN = "SUBMITTED_TO_DEAN", "Submitted To Dean"
    REJECTED_BY_DEAN = "REJECTED_BY_DEAN", "Rejected By Dean"
    APPROVED_BY_DEAN = "APPROVED_BY_DEAN", "Approved By Dean"
    COMPILED_BY_FORM_TEACHER = "COMPILED_BY_FORM_TEACHER", "Compiled By Form Teacher"
    SUBMITTED_TO_VP = "SUBMITTED_TO_VP", "Submitted To VP"
    REJECTED_BY_VP = "REJECTED_BY_VP", "Rejected By VP"
    PUBLISHED = "PUBLISHED", "Published"


class ResultSheet(TimeStampedModel):
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="result_sheets",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="result_sheets",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="result_sheets",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="result_sheets",
    )
    cbt_component_policies = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=40,
        choices=ResultSheetStatus.choices,
        default=ResultSheetStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_result_sheets",
    )

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("academic_class", "subject", "session", "term"),
                name="unique_result_sheet_per_subject_class_term",
            )
        ]

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")

    def __str__(self):
        return f"{self.subject.name} - {self.academic_class.code} ({self.term.get_name_display()})"


class ResultSubmission(TimeStampedModel):
    result_sheet = models.ForeignKey(
        ResultSheet,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="result_submissions",
    )
    from_status = models.CharField(max_length=40, choices=ResultSheetStatus.choices)
    to_status = models.CharField(max_length=40, choices=ResultSheetStatus.choices)
    action = models.CharField(max_length=64, blank=True)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [
            models.Index(fields=("result_sheet", "created_at")),
        ]

    def __str__(self):
        return (
            f"{self.result_sheet_id}: {self.from_status} -> {self.to_status}"
        )


class StudentSubjectScore(TimeStampedModel):
    SCORE_COMPONENT_FIELDS = ("ca1", "ca2", "ca3", "ca4", "objective", "theory")

    result_sheet = models.ForeignKey(
        ResultSheet,
        on_delete=models.CASCADE,
        related_name="student_scores",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_subject_scores",
    )

    ca1 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ca2 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ca3 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    ca4 = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    objective = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    theory = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    total_ca = models.DecimalField(max_digits=6, decimal_places=2, default=0, editable=False)
    total_exam = models.DecimalField(max_digits=6, decimal_places=2, default=0, editable=False)
    grand_total = models.DecimalField(max_digits=6, decimal_places=2, default=0, editable=False)
    grade = models.CharField(max_length=2, blank=True, editable=False)

    has_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True)
    cbt_locked_fields = models.JSONField(default=list, blank=True)
    cbt_component_breakdown = models.JSONField(default=dict, blank=True)
    override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="score_overrides",
    )
    override_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("student__username",)
        constraints = [
            models.UniqueConstraint(
                fields=("result_sheet", "student"),
                name="unique_student_score_per_result_sheet",
            )
        ]

    def save(self, *args, **kwargs):
        self.cbt_locked_fields = self.normalized_locked_fields()
        self.cbt_component_breakdown = self.normalized_breakdown()
        payload = compute_grade_payload(
            ca1=self.ca1,
            ca2=self.ca2,
            ca3=self.ca3,
            ca4=self.ca4,
            objective=self.objective,
            theory=self.theory,
            allow_override=self.has_override,
            override_reason=self.override_reason,
            actor=None,
            require_elevated_override=False,
        )
        self.total_ca = payload.total_ca
        self.total_exam = payload.total_exam
        self.grand_total = payload.grand_total
        self.grade = payload.grade
        if self.has_override:
            if not self.override_at:
                self.override_at = timezone.now()
        else:
            self.override_reason = ""
            self.override_by = None
            self.override_at = None
        super().save(*args, **kwargs)

    def normalized_locked_fields(self):
        raw = self.cbt_locked_fields
        if not isinstance(raw, list):
            return []
        allowed = set(self.SCORE_COMPONENT_FIELDS)
        return sorted({str(field).strip() for field in raw if str(field).strip() in allowed})

    def normalized_breakdown(self):
        raw = self.cbt_component_breakdown
        if not isinstance(raw, dict):
            return {}
        normalized = {}
        for key, value in raw.items():
            name = str(key).strip()
            if not name:
                continue
            try:
                normalized[name] = str(Decimal(str(value)).quantize(Decimal("0.01")))
            except (InvalidOperation, TypeError, ValueError):
                continue
        return normalized

    def breakdown_value(self, key):
        try:
            return Decimal(str(self.normalized_breakdown().get(key, "0.00"))).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0.00")

    def set_breakdown_value(self, key, value):
        breakdown = self.normalized_breakdown()
        try:
            breakdown[str(key).strip()] = str(Decimal(str(value)).quantize(Decimal("0.01")))
        except (InvalidOperation, TypeError, ValueError):
            breakdown[str(key).strip()] = "0.00"
        self.cbt_component_breakdown = breakdown

    def is_component_locked(self, component_field):
        return component_field in set(self.normalized_locked_fields())

    def lock_components(self, *component_fields):
        locked = set(self.normalized_locked_fields())
        for field in component_fields:
            if field in self.SCORE_COMPONENT_FIELDS:
                locked.add(field)
        self.cbt_locked_fields = sorted(locked)

    def __str__(self):
        return f"{self.student.username} - {self.result_sheet.subject.name}: {self.grand_total}"


class BehaviorMetricSetting(TimeStampedModel):
    code = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_behavior_metric_settings",
    )

    class Meta:
        ordering = ("sort_order", "label")
        indexes = [
            models.Index(fields=("is_active", "sort_order")),
        ]

    def clean(self):
        self.code = (self.code or "").strip().lower().replace(" ", "_")
        self.label = (self.label or "").strip()
        if not self.code:
            raise ValidationError("Behavior metric code is required.")
        if not self.label:
            raise ValidationError("Behavior metric label is required.")

    def __str__(self):
        return f"{self.label} ({self.code})"


class ClassCompilationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED_TO_VP = "SUBMITTED_TO_VP", "Submitted To VP"
    REJECTED_BY_VP = "REJECTED_BY_VP", "Rejected By VP"
    PUBLISHED = "PUBLISHED", "Published"


class ClassResultCompilation(TimeStampedModel):
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="result_compilations",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="result_compilations",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="result_compilations",
    )
    form_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="compiled_result_batches",
    )
    status = models.CharField(
        max_length=30,
        choices=ClassCompilationStatus.choices,
        default=ClassCompilationStatus.DRAFT,
    )
    submitted_to_vp_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    vp_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vp_result_compilation_actions",
    )
    principal_override_actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="principal_result_compilation_actions",
    )
    decision_comment = models.TextField(blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("academic_class", "session", "term"),
                name="unique_class_compilation_per_term",
            )
        ]

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")

    def __str__(self):
        return f"{self.academic_class.code} {self.term.get_name_display()} {self.status}"


class ClassResultStudentRecord(TimeStampedModel):
    compilation = models.ForeignKey(
        ClassResultCompilation,
        on_delete=models.CASCADE,
        related_name="student_records",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_result_records",
    )
    attendance_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    behavior_rating = models.PositiveSmallIntegerField(default=3)
    behavior_breakdown = models.JSONField(default=dict, blank=True)
    teacher_comment = models.TextField(blank=True)
    club_membership = models.CharField(max_length=160, blank=True)
    office_held = models.CharField(max_length=160, blank=True)
    notable_contribution = models.TextField(blank=True)
    doctor_remark = models.TextField(blank=True)
    height_start_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    height_end_cm = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    weight_start_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    weight_end_kg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    medical_incidents = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("student__username",)
        constraints = [
            models.UniqueConstraint(
                fields=("compilation", "student"),
                name="unique_class_record_per_student_compilation",
            )
        ]

    def clean(self):
        if self.behavior_rating < 1 or self.behavior_rating > 5:
            raise ValidationError("Behavior rating must be between 1 and 5.")

    def refresh_attendance(self, calendar, academic_class):
        self.attendance_percentage = compute_student_attendance_percentage(
            student=self.student,
            calendar=calendar,
            academic_class=academic_class,
        )


class ResultAccessPin(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="result_access_pins",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="result_access_pins",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="result_access_pins",
    )
    pin_code = models.CharField(max_length=12)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_result_access_pins",
    )
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("student", "session", "term"),
                name="unique_result_access_pin_per_student_term",
            )
        ]

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.student_id and not self.student.has_role("STUDENT"):
            raise ValidationError("Result PIN can only target student accounts.")
        self.pin_code = (self.pin_code or "").strip().upper()
        if not self.pin_code:
            raise ValidationError("PIN code is required.")

    def is_usable(self):
        if not self.is_active:
            return False
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def __str__(self):
        return f"{self.student} {self.session} {self.term} PIN"
