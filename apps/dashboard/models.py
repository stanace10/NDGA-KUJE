from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.academics.models import AcademicClass, AcademicSession, Subject, Term
from apps.accounts.models import User
from core.models import TimeStampedModel


class PrincipalSignature(TimeStampedModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="principal_signature",
    )
    signature_image = models.ImageField(
        upload_to="signatures/principal/",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self):
        return f"Principal signature ({self.user.username})"


class SchoolProfile(TimeStampedModel):
    singleton_key = models.CharField(max_length=16, default="PRIMARY", unique=True, editable=False)
    school_name = models.CharField(max_length=180, default="Notre Dame Girls Academy")
    address = models.CharField(max_length=255, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    result_tagline = models.CharField(max_length=180, default="Termly Evaluation Report")
    principal_name = models.CharField(max_length=180, blank=True)
    report_footer = models.CharField(max_length=220, blank=True)
    ca1_label = models.CharField(max_length=40, default="1st CA")
    ca2_label = models.CharField(max_length=40, default="2nd CA")
    ca3_label = models.CharField(max_length=40, default="3rd CA")
    assignment_label = models.CharField(max_length=40, default="Project/Assignment")
    promotion_average_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=40)
    promotion_attendance_threshold = models.DecimalField(max_digits=5, decimal_places=2, default=75)
    promotion_policy_note = models.TextField(blank=True)
    auto_comment_guidance = models.TextField(blank=True)
    teacher_comment_guidance = models.TextField(blank=True)
    dean_comment_guidance = models.TextField(blank=True)
    principal_comment_guidance = models.TextField(blank=True)
    doctor_remark_guidance = models.TextField(blank=True)
    require_result_access_pin = models.BooleanField(default=False)
    school_logo = models.ImageField(upload_to="branding/school/", blank=True, null=True)
    school_stamp = models.ImageField(upload_to="branding/stamp/", blank=True, null=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_school_profiles",
    )

    class Meta:
        verbose_name = "School Profile"
        verbose_name_plural = "School Profile"

    def clean(self):
        self.singleton_key = "PRIMARY"
        self.school_name = (self.school_name or "Notre Dame Girls Academy").strip()
        self.address = (self.address or "").strip()
        self.contact_email = (self.contact_email or "").strip().lower()
        self.contact_phone = (self.contact_phone or "").strip()
        self.website = (self.website or "").strip()
        self.result_tagline = (self.result_tagline or "Termly Evaluation Report").strip()
        self.principal_name = (self.principal_name or "").strip()
        self.report_footer = (self.report_footer or "").strip()
        self.ca1_label = (self.ca1_label or "1st CA").strip()
        self.ca2_label = (self.ca2_label or "2nd CA").strip()
        self.ca3_label = (self.ca3_label or "3rd CA").strip()
        self.assignment_label = (self.assignment_label or "Project/Assignment").strip()
        self.promotion_policy_note = (self.promotion_policy_note or "").strip()
        self.auto_comment_guidance = (self.auto_comment_guidance or "").strip()
        self.teacher_comment_guidance = (self.teacher_comment_guidance or "").strip()
        self.dean_comment_guidance = (self.dean_comment_guidance or "").strip()
        self.principal_comment_guidance = (self.principal_comment_guidance or "").strip()
        self.doctor_remark_guidance = (self.doctor_remark_guidance or "").strip()

    @classmethod
    def load(cls):
        profile = cls.objects.first()
        if profile:
            return profile
        return cls.objects.create()

    def __str__(self):
        return self.school_name


class LearningResourceCategory(models.TextChoices):
    STUDY_MATERIAL = "STUDY_MATERIAL", "Study Material"
    PAST_QUESTION = "PAST_QUESTION", "Past Question"
    ASSIGNMENT = "ASSIGNMENT", "Assignment"
    PRACTICE = "PRACTICE", "Practice"


class LearningResource(TimeStampedModel):
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    category = models.CharField(
        max_length=24,
        choices=LearningResourceCategory.choices,
        default=LearningResourceCategory.STUDY_MATERIAL,
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="learning_resources",
        null=True,
        blank=True,
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_resources",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_resources",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_resources",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_learning_resources",
    )
    content_text = models.TextField(blank=True)
    resource_file = models.FileField(upload_to="learning/resources/", blank=True, null=True)
    external_url = models.URLField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "title")

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.subject_id and self.academic_class_id:
            mapping_class = self.academic_class.instructional_class
            mapping_exists = mapping_class.class_subjects.filter(
                subject_id=self.subject_id,
                is_active=True,
            ).exists()
            if not mapping_exists:
                raise ValidationError("Selected subject is not mapped to the selected class.")
        has_payload = bool((self.content_text or "").strip() or self.resource_file or (self.external_url or "").strip())
        if not has_payload:
            raise ValidationError("Provide resource text, a file, or an external URL.")

    def __str__(self):
        return self.title


class LessonPlanDraft(TimeStampedModel):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lesson_plan_drafts",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="lesson_plan_drafts",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="lesson_plan_drafts",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson_plan_drafts",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lesson_plan_drafts",
    )
    topic = models.CharField(max_length=180)
    teaching_goal = models.TextField(blank=True)
    teacher_notes = models.TextField(blank=True)
    lesson_objectives = models.TextField()
    lesson_outline = models.TextField()
    class_activity = models.TextField()
    assignment_text = models.TextField(blank=True)
    quiz_text = models.TextField(blank=True)
    publish_to_learning_hub = models.BooleanField(default=False)
    assignment_due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.assignment_due_date and not self.assignment_text.strip():
            raise ValidationError("Assignment due date requires assignment text.")

    def __str__(self):
        return f"{self.subject.name} - {self.topic}"


class VaultDocumentCategory(models.TextChoices):
    TRANSCRIPT = "TRANSCRIPT", "Transcript"
    CERTIFICATE = "CERTIFICATE", "Certificate"
    STUDENT_RECORD = "STUDENT_RECORD", "Student Record"
    GRADUATION_RECORD = "GRADUATION_RECORD", "Graduation Record"
    GENERAL = "GENERAL", "General"


class PortalDocument(TimeStampedModel):
    title = models.CharField(max_length=180)
    category = models.CharField(
        max_length=24,
        choices=VaultDocumentCategory.choices,
        default=VaultDocumentCategory.GENERAL,
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vault_documents",
        null=True,
        blank=True,
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vault_documents",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vault_documents",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vault_documents",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_vault_documents",
    )
    document_file = models.FileField(upload_to="vault/documents/")
    notes = models.TextField(blank=True)
    is_visible_to_student = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at", "title")

    def clean(self):
        if self.student_id and not self.student.has_role("STUDENT"):
            raise ValidationError("Vault documents can only target student accounts.")
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")

    def __str__(self):
        return self.title



class Club(TimeStampedModel):
    name = models.CharField(max_length=140, unique=True)
    code = models.CharField(max_length=24, unique=True)
    description = models.TextField(blank=True)
    patron = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="patroned_clubs",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def clean(self):
        self.name = (self.name or "").strip()
        self.code = (self.code or "").strip().upper()
        if self.patron_id and hasattr(self.patron, "has_role") and self.patron.has_role("STUDENT"):
            raise ValidationError("Club patron must be a staff user.")

    def __str__(self):
        return self.name


class StudentClubMembership(TimeStampedModel):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="club_memberships",
    )
    club = models.ForeignKey(
        Club,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="club_memberships",
    )
    office_held = models.CharField(max_length=120, blank=True)
    significant_contribution = models.TextField(blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_club_memberships",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("club__name", "student__username")
        constraints = [
            models.UniqueConstraint(
                fields=("student", "club", "session"),
                name="unique_student_club_membership_per_session",
            )
        ]

    def clean(self):
        if self.student_id and hasattr(self.student, "has_role") and not self.student.has_role("STUDENT"):
            raise ValidationError("Club membership can only target student accounts.")

    def __str__(self):
        return f"{self.student} -> {self.club}"

class WeeklyChallenge(TimeStampedModel):
    week_label = models.CharField(max_length=60)
    title = models.CharField(max_length=180)
    instructions = models.TextField(blank=True)
    question_text = models.TextField()
    answer_guidance = models.TextField(blank=True)
    accepted_answer_keywords = models.TextField(blank=True)
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weekly_challenges",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weekly_challenges",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weekly_challenges",
    )
    reward_points = models.PositiveSmallIntegerField(default=5)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_weekly_challenges",
    )
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "title")

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        self.week_label = (self.week_label or "").strip()
        self.title = (self.title or "").strip()
        self.instructions = (self.instructions or "").strip()
        self.answer_guidance = (self.answer_guidance or "").strip()
        self.accepted_answer_keywords = (self.accepted_answer_keywords or "").strip()
        if not self.week_label:
            raise ValidationError("Challenge week label is required.")
        if not self.title:
            raise ValidationError("Challenge title is required.")
        if not (self.question_text or "").strip():
            raise ValidationError("Challenge question is required.")
        if self.reward_points < 0:
            raise ValidationError("Reward points cannot be negative.")

    @property
    def normalized_keywords(self):
        raw = self.accepted_answer_keywords or ""
        parts = []
        for chunk in raw.replace("\n", ",").split(","):
            token = chunk.strip().lower()
            if token:
                parts.append(token)
        return parts

    def __str__(self):
        return f"{self.week_label} - {self.title}"


class WeeklyChallengeSubmission(TimeStampedModel):
    challenge = models.ForeignKey(
        WeeklyChallenge,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weekly_challenge_submissions",
    )
    response_text = models.TextField()
    awarded_points = models.PositiveSmallIntegerField(default=0)
    is_correct = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_weekly_challenge_submissions",
    )

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("challenge", "student"),
                name="unique_weekly_challenge_submission_per_student",
            )
        ]

    def clean(self):
        if self.student_id and hasattr(self.student, "has_role") and not self.student.has_role("STUDENT"):
            raise ValidationError("Weekly challenge submissions can only target student accounts.")
        self.response_text = (self.response_text or "").strip()
        if not self.response_text:
            raise ValidationError("Challenge response is required.")

    def auto_grade(self):
        response = (self.response_text or "").strip().lower()
        keywords = self.challenge.normalized_keywords if self.challenge_id else []
        if not keywords:
            self.is_correct = False
            self.awarded_points = 0
            return
        matched = any(keyword in response for keyword in keywords)
        self.is_correct = matched
        self.awarded_points = self.challenge.reward_points if matched else 0

    def save(self, *args, **kwargs):
        self.auto_grade()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} -> {self.challenge}"

