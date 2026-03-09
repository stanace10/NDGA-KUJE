from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.accounts.constants import (
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
)
from apps.accounts.models import User

from core.models import TimeStampedModel


class TermName(models.TextChoices):
    FIRST = "FIRST", "First Term"
    SECOND = "SECOND", "Second Term"
    THIRD = "THIRD", "Third Term"


class SubjectCategory(models.TextChoices):
    GENERAL = "GENERAL", "General"
    SCIENCE = "SCIENCE", "Science"
    ARTS = "ARTS", "Arts"
    COMMERCIAL = "COMMERCIAL", "Commercial"
    VOCATIONAL = "VOCATIONAL", "Vocational"


class AcademicSession(TimeStampedModel):
    name = models.CharField(max_length=20, unique=True)
    is_closed = models.BooleanField(default=False)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_academic_sessions",
    )

    class Meta:
        ordering = ("-name",)

    def __str__(self):
        return self.name


class Term(TimeStampedModel):
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="terms",
    )
    name = models.CharField(max_length=10, choices=TermName.choices)

    class Meta:
        ordering = ("session__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "name"),
                name="unique_term_per_session",
            )
        ]

    def __str__(self):
        return f"{self.get_name_display()} - {self.session.name}"


class Campus(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return self.code


class AcademicClass(TimeStampedModel):
    code = models.CharField(max_length=20, unique=True)
    display_name = models.CharField(max_length=64, blank=True)
    base_class = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="arm_classes",
    )
    arm_name = models.CharField(max_length=32, blank=True)
    campus = models.ForeignKey(
        Campus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classes",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)

    def clean(self):
        self.code = (self.code or "").strip().upper()
        self.display_name = (self.display_name or "").strip()
        self.arm_name = (self.arm_name or "").strip().upper()

        if self.base_class_id:
            if self.base_class_id == self.id:
                raise ValidationError("A class arm cannot use itself as the base class.")
            if self.base_class and self.base_class.base_class_id:
                raise ValidationError("Class arms must point to a main class level, not another arm.")
            if not self.display_name and self.base_class:
                base_label = self.base_class.display_name or self.base_class.code
                arm_label = self.arm_name or "ARM"
                self.display_name = f"{base_label} {arm_label}".strip()
        else:
            self.arm_name = ""

        if not self.display_name:
            self.display_name = self.code

    @property
    def is_arm(self):
        return bool(self.base_class_id)

    @property
    def instructional_class(self):
        return self.base_class or self

    @property
    def level_code(self):
        return self.instructional_class.code

    @property
    def level_display_name(self):
        return self.instructional_class.display_name or self.instructional_class.code

    def cohort_class_ids(self):
        if self.base_class_id:
            return [self.id]
        arm_ids = list(self.arm_classes.values_list("id", flat=True))
        return [self.id, *arm_ids]

    def __str__(self):
        return self.code


class Subject(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True)
    category = models.CharField(
        max_length=20,
        choices=SubjectCategory.choices,
        default=SubjectCategory.GENERAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class GradeScale(TimeStampedModel):
    grade = models.CharField(max_length=2)
    min_score = models.PositiveSmallIntegerField()
    max_score = models.PositiveSmallIntegerField()
    sort_order = models.PositiveSmallIntegerField(default=1)
    is_default = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "grade")
        constraints = [
            models.UniqueConstraint(
                fields=("grade",),
                condition=Q(is_default=True),
                name="unique_default_grade_label",
            )
        ]

    def clean(self):
        if self.min_score > self.max_score:
            raise ValidationError("Minimum score cannot exceed maximum score.")
        if self.max_score > 100:
            raise ValidationError("Maximum score cannot exceed 100.")

    def __str__(self):
        return f"{self.grade} ({self.min_score}-{self.max_score})"

    @classmethod
    def ensure_default_scale(cls):
        defaults = [
            {"grade": "A", "min_score": 70, "max_score": 100, "sort_order": 1},
            {"grade": "B", "min_score": 60, "max_score": 69, "sort_order": 2},
            {"grade": "C", "min_score": 50, "max_score": 59, "sort_order": 3},
            {"grade": "D", "min_score": 40, "max_score": 49, "sort_order": 4},
            {"grade": "F", "min_score": 0, "max_score": 39, "sort_order": 5},
        ]
        for row in defaults:
            cls.objects.update_or_create(
                grade=row["grade"],
                defaults={**row, "is_default": True},
            )


class ClassSubject(TimeStampedModel):
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="class_subjects",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("academic_class__code", "subject__name")
        constraints = [
            models.UniqueConstraint(
                fields=("academic_class", "subject"),
                name="unique_subject_mapping_per_class",
            )
        ]

    def clean(self):
        if self.academic_class_id and self.academic_class.base_class_id:
            raise ValidationError("Subjects must be mapped to the main class level, not a class arm.")

    def __str__(self):
        return f"{self.academic_class.code} - {self.subject.name}"


class TeacherSubjectAssignment(TimeStampedModel):
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="subject_assignments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("subject", "academic_class", "session", "term"),
                condition=Q(is_active=True),
                name="unique_active_teacher_per_subject_class_term",
            )
        ]

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.session_id and self.session.is_closed and self.is_active:
            raise ValidationError("Closed session is read-only for teacher assignments.")
        if self.teacher_id:
            has_teaching_role = self.teacher.get_all_role_codes() & {
                ROLE_SUBJECT_TEACHER,
                ROLE_DEAN,
                ROLE_FORM_TEACHER,
            }
            if not has_teaching_role:
                raise ValidationError("Selected user is not eligible for subject teaching assignment.")
        if self.academic_class_id and self.academic_class.base_class_id:
            raise ValidationError("Subject teachers must be assigned to the main class level, not a class arm.")
        if self.academic_class_id and self.subject_id:
            mapping_class_id = self.academic_class.instructional_class.id if self.academic_class_id else None
            if not ClassSubject.objects.filter(
                academic_class_id=mapping_class_id,
                subject_id=self.subject_id,
                is_active=True,
            ).exists():
                raise ValidationError("Subject must be mapped to class before assignment.")

    def __str__(self):
        return (
            f"{self.teacher.username} -> {self.subject.name} "
            f"({self.academic_class.code}, {self.term.get_name_display()})"
        )


class FormTeacherAssignment(TimeStampedModel):
    teacher = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="form_teacher_assignments",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="form_teacher_assignments",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="form_teacher_assignments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("academic_class", "session"),
                condition=Q(is_active=True),
                name="unique_active_form_teacher_per_class_session",
            )
        ]

    def clean(self):
        if self.session_id and self.session.is_closed and self.is_active:
            raise ValidationError("Closed session is read-only for form teacher assignments.")
        if self.teacher_id and not self.teacher.has_role(ROLE_FORM_TEACHER):
            raise ValidationError("Selected user does not have FORM_TEACHER role.")

    def __str__(self):
        return f"{self.teacher.username} -> {self.academic_class.code} ({self.session.name})"


class StudentClassEnrollment(TimeStampedModel):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="class_enrollments",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="student_enrollments",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="student_enrollments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("academic_class__code", "student__username")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "academic_class", "session"),
                name="unique_student_class_session_enrollment",
            ),
            models.UniqueConstraint(
                fields=("student", "session"),
                condition=Q(is_active=True),
                name="unique_active_student_enrollment_per_session",
            ),
        ]

    def clean(self):
        if self.session_id and self.session.is_closed and self.is_active:
            raise ValidationError("Closed session is read-only for class enrollment.")
        if self.student_id and not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Selected user does not have STUDENT role.")

    def __str__(self):
        return f"{self.student.username} -> {self.academic_class.code} ({self.session.name})"


class StudentSubjectEnrollment(TimeStampedModel):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subject_enrollments",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="student_enrollments",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="student_subject_enrollments",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("student__username", "subject__name")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "subject", "session"),
                name="unique_student_subject_per_session",
            ),
        ]

    def clean(self):
        if self.session_id and self.session.is_closed and self.is_active:
            raise ValidationError("Closed session is read-only for subject enrollment.")
        if self.student_id and not self.student.has_role(ROLE_STUDENT):
            raise ValidationError("Selected user does not have STUDENT role.")

        if self.student_id and self.session_id and self.subject_id:
            enrollment = StudentClassEnrollment.objects.filter(
                student=self.student,
                session=self.session,
                is_active=True,
            ).select_related("academic_class").first()
            if not enrollment:
                raise ValidationError(
                    "Student must have an active class enrollment before subject enrollment."
                )
            mapping_class = enrollment.academic_class.instructional_class
            if not ClassSubject.objects.filter(
                academic_class=mapping_class,
                subject=self.subject,
                is_active=True,
            ).exists():
                raise ValidationError(
                    "Subject must be mapped to the student's class level before enrollment."
                )

    def __str__(self):
        return f"{self.student.username} -> {self.subject.code} ({self.session.name})"


class SessionPromotionOutcome(models.TextChoices):
    PROMOTED = "PROMOTED", "Promoted"
    RETAINED = "RETAINED", "Retained"
    GRADUATED = "GRADUATED", "Graduated"


class SessionPromotionRecord(TimeStampedModel):
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="promotion_records",
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="session_promotion_records",
    )
    from_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_from_records",
    )
    to_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_to_records",
    )
    outcome = models.CharField(
        max_length=16,
        choices=SessionPromotionOutcome.choices,
    )
    generated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_session_promotion_records",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ("student__username",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "student"),
                name="unique_promotion_record_per_student_session",
            )
        ]

    def __str__(self):
        from_code = self.from_class.code if self.from_class else "-"
        to_code = self.to_class.code if self.to_class else "-"
        return f"{self.student.username} {self.outcome} ({from_code} -> {to_code})"
