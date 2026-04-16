from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.academics.models import AcademicClass, AcademicSession, Subject, TeacherSubjectAssignment, Term
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


class PublicWebsiteSettings(TimeStampedModel):
    singleton_key = models.CharField(max_length=16, default="PRIMARY", unique=True, editable=False)
    hero_eyebrow = models.CharField(max_length=160, default="Welcome to Notre Dame Girls' Academy")
    hero_title = models.CharField(max_length=220, default="Educating Girls for Life")
    hero_subtitle = models.TextField(
        default=(
            "Notre Dame Girls' Academy, Kuje-Abuja forms confident, competent, and "
            "compassionate young women through purposeful learning, Catholic formation, "
            "full boarding, and disciplined care."
        )
    )
    principal_welcome_title = models.CharField(max_length=180, default="A welcome from the Principal")
    principal_welcome_message = models.TextField(
        default=(
            "Welcome to Notre Dame Girls' Academy, a Catholic secondary school dedicated "
            "to forming confident, competent, and compassionate young women."
        )
    )
    principal_welcome_support = models.TextField(
        default=(
            "We partner with parents to nurture Gospel values, disciplined study habits, "
            "strong character, and the full potential of every girl entrusted to our care."
        )
    )
    footer_statement = models.TextField(
        default=(
            "Educating girls for life through strong academics, boarding structure, "
            "faith formation, and disciplined student growth."
        )
    )
    chat_welcome_text = models.TextField(
        default=(
            "Hello. I am Julie. I can guide you on admissions, fees, boarding, "
            "subjects, screening, and school life."
        )
    )
    chat_management_wait_text = models.TextField(
        default="Connecting you to management. Please wait..."
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_public_website_settings",
    )

    class Meta:
        verbose_name = "Public Website Settings"
        verbose_name_plural = "Public Website Settings"

    def clean(self):
        self.singleton_key = "PRIMARY"
        self.hero_eyebrow = (self.hero_eyebrow or "").strip()
        self.hero_title = (self.hero_title or "").strip()
        self.hero_subtitle = (self.hero_subtitle or "").strip()
        self.principal_welcome_title = (self.principal_welcome_title or "").strip()
        self.principal_welcome_message = (self.principal_welcome_message or "").strip()
        self.principal_welcome_support = (self.principal_welcome_support or "").strip()
        self.footer_statement = (self.footer_statement or "").strip()
        self.chat_welcome_text = (self.chat_welcome_text or "").strip()
        self.chat_management_wait_text = (self.chat_management_wait_text or "").strip()

    @classmethod
    def load(cls):
        row = cls.objects.first()
        if row:
            return row
        return cls.objects.create()

    def __str__(self):
        return "Public Website Settings"


class PublicSubmissionType(models.TextChoices):
    CONTACT = "CONTACT", "Contact Enquiry"
    ADMISSION = "ADMISSION", "Admission Registration"


class PublicSubmissionStatus(models.TextChoices):
    NEW = "NEW", "New"
    IN_REVIEW = "IN_REVIEW", "In Review"
    CLOSED = "CLOSED", "Closed"


class PublicAdmissionWorkflowStatus(models.TextChoices):
    NEW = "NEW", "New"
    PENDING = "PENDING", "Pending Review"
    APPROVED = "APPROVED", "Approved"
    DECLINED = "DECLINED", "Declined"


class PublicAdmissionPaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PAID = "PAID", "Paid"
    WAIVED = "WAIVED", "Waived"


class PublicAdmissionPaymentMode(models.TextChoices):
    ONLINE = "ONLINE", "Online Payment"
    PHYSICAL = "PHYSICAL", "Physical at School"


class PublicAdmissionGatewayProvider(models.TextChoices):
    PAYSTACK = "PAYSTACK", "Paystack"
    FLUTTERWAVE = "FLUTTERWAVE", "Flutterwave"


class PublicAdmissionGatewayStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    INITIALIZED = "INITIALIZED", "Initialized"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class PublicSiteSubmission(TimeStampedModel):
    submission_type = models.CharField(
        max_length=16,
        choices=PublicSubmissionType.choices,
        default=PublicSubmissionType.CONTACT,
    )
    status = models.CharField(
        max_length=16,
        choices=PublicSubmissionStatus.choices,
        default=PublicSubmissionStatus.NEW,
    )
    contact_name = models.CharField(max_length=180)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=80, blank=True)
    subject = models.CharField(max_length=180, blank=True)
    message = models.TextField(blank=True)
    applicant_name = models.CharField(max_length=180, blank=True)
    applicant_date_of_birth = models.DateField(null=True, blank=True)
    intended_class = models.CharField(max_length=40, blank=True)
    guardian_name = models.CharField(max_length=180, blank=True)
    guardian_email = models.EmailField(blank=True)
    guardian_phone = models.CharField(max_length=40, blank=True)
    residential_address = models.TextField(blank=True)
    previous_school = models.CharField(max_length=180, blank=True)
    boarding_option = models.CharField(max_length=24, blank=True)
    medical_notes = models.TextField(blank=True)
    passport_photo = models.ImageField(
        upload_to="public_submissions/passports/",
        blank=True,
        null=True,
    )
    birth_certificate = models.FileField(
        upload_to="public_submissions/birth_certificates/",
        blank=True,
        null=True,
    )
    school_result = models.FileField(
        upload_to="public_submissions/school_results/",
        blank=True,
        null=True,
    )
    admissions_status = models.CharField(
        max_length=16,
        choices=PublicAdmissionWorkflowStatus.choices,
        default=PublicAdmissionWorkflowStatus.NEW,
    )
    payment_status = models.CharField(
        max_length=16,
        choices=PublicAdmissionPaymentStatus.choices,
        default=PublicAdmissionPaymentStatus.UNPAID,
    )
    application_fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    application_fee_reference = models.CharField(max_length=120, blank=True)
    application_fee_paid_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_public_site_submissions",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    linked_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="public_admission_submissions",
    )
    generated_admission_number = models.CharField(max_length=32, blank=True)
    approval_notes = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("submission_type", "status", "created_at")),
            models.Index(fields=("contact_email",)),
            models.Index(fields=("intended_class",)),
            models.Index(fields=("submission_type", "admissions_status", "payment_status")),
        ]

    def clean(self):
        self.contact_name = (self.contact_name or "").strip()
        self.contact_email = (self.contact_email or "").strip().lower()
        self.contact_phone = (self.contact_phone or "").strip()
        self.category = (self.category or "").strip()
        self.subject = (self.subject or "").strip()
        self.message = (self.message or "").strip()
        self.applicant_name = (self.applicant_name or "").strip()
        self.intended_class = (self.intended_class or "").strip().upper()
        self.guardian_name = (self.guardian_name or "").strip()
        self.guardian_email = (self.guardian_email or "").strip().lower()
        self.guardian_phone = (self.guardian_phone or "").strip()
        self.residential_address = (self.residential_address or "").strip()
        self.previous_school = (self.previous_school or "").strip()
        self.boarding_option = (self.boarding_option or "").strip()
        self.medical_notes = (self.medical_notes or "").strip()
        self.application_fee_reference = (self.application_fee_reference or "").strip()
        self.generated_admission_number = (self.generated_admission_number or "").strip().upper()
        self.approval_notes = (self.approval_notes or "").strip()

        if self.submission_type == PublicSubmissionType.CONTACT:
            if not self.subject:
                raise ValidationError("Contact enquiries require a subject.")
            if not self.message:
                raise ValidationError("Contact enquiries require a message.")

        if self.submission_type == PublicSubmissionType.ADMISSION:
            required_values = {
                "Applicant name": self.applicant_name,
                "Intended class": self.intended_class,
                "Guardian name": self.guardian_name,
                "Guardian phone": self.guardian_phone,
                "Residential address": self.residential_address,
            }
            missing = [label for label, value in required_values.items() if not value]
            if missing:
                raise ValidationError(", ".join(missing) + " required for admission registration.")
            if (
                self.admissions_status == PublicAdmissionWorkflowStatus.APPROVED
                and not self.generated_admission_number
            ):
                raise ValidationError("Approved applicants must have an admission number.")

    def __str__(self):
        title = self.applicant_name or self.contact_name or "Public submission"
        return f"{self.get_submission_type_display()}: {title}"

    def admission_form_payload(self):
        return dict((self.metadata or {}).get("admission_form") or {})

    def admission_payment_mode(self):
        raw = (
            (self.metadata or {}).get("application_payment_mode")
            or (self.metadata or {}).get("preferred_payment_mode")
            or ""
        )
        mode = str(raw).strip().upper()
        if mode in {
            PublicAdmissionPaymentMode.ONLINE,
            PublicAdmissionPaymentMode.PHYSICAL,
        }:
            return mode
        if self.payment_status == PublicAdmissionPaymentStatus.PAID:
            return PublicAdmissionPaymentMode.PHYSICAL
        return ""

    def payment_mode_badge(self):
        mode = self.admission_payment_mode()
        if mode == PublicAdmissionPaymentMode.ONLINE:
            return "Paid Online"
        if mode == PublicAdmissionPaymentMode.PHYSICAL:
            if self.payment_status == PublicAdmissionPaymentStatus.PAID:
                return "Paid at School"
            return "Pay at School"
        return "Awaiting Payment"

    def public_admission_pdf_available(self):
        return (
            self.submission_type == PublicSubmissionType.ADMISSION
            and self.payment_status == PublicAdmissionPaymentStatus.PAID
            and self.admission_payment_mode() == PublicAdmissionPaymentMode.ONLINE
        )


class PublicAdmissionPaymentTransaction(TimeStampedModel):
    submission = models.ForeignKey(
        PublicSiteSubmission,
        on_delete=models.CASCADE,
        related_name="payment_transactions",
    )
    reference = models.CharField(max_length=80, unique=True)
    provider = models.CharField(
        max_length=16,
        choices=PublicAdmissionGatewayProvider.choices,
        default=PublicAdmissionGatewayProvider.PAYSTACK,
    )
    status = models.CharField(
        max_length=16,
        choices=PublicAdmissionGatewayStatus.choices,
        default=PublicAdmissionGatewayStatus.PENDING,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    callback_url = models.CharField(max_length=320, blank=True)
    authorization_url = models.CharField(max_length=500, blank=True)
    gateway_reference = models.CharField(max_length=180, blank=True)
    initialized_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("reference",)),
            models.Index(fields=("submission", "status", "created_at")),
            models.Index(fields=("provider", "status")),
        ]

    def clean(self):
        self.reference = (self.reference or "").strip().upper()
        self.gateway_reference = (self.gateway_reference or "").strip()
        self.callback_url = (self.callback_url or "").strip()
        self.authorization_url = (self.authorization_url or "").strip()
        self.failure_reason = (self.failure_reason or "").strip()
        if self.amount <= 0:
            raise ValidationError("Gateway transaction amount must be greater than zero.")
        if self.submission_id and self.submission.submission_type != PublicSubmissionType.ADMISSION:
            raise ValidationError("Public admission payments can only attach to admission submissions.")

    def __str__(self):
        return f"{self.reference} [{self.status}]"


class PublicGalleryCategory(TimeStampedModel):
    title = models.CharField(max_length=180)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    summary = models.TextField(blank=True)
    cover_image = models.ImageField(upload_to="public_site/gallery/categories/", blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_public_gallery_categories",
    )

    class Meta:
        ordering = ("sort_order", "title")

    def clean(self):
        self.title = (self.title or "").strip()
        self.summary = (self.summary or "").strip()
        if not self.slug:
            self.slug = slugify(self.title)

    def __str__(self):
        return self.title


class PublicGalleryImage(TimeStampedModel):
    category = models.ForeignKey(
        PublicGalleryCategory,
        on_delete=models.CASCADE,
        related_name="images",
    )
    title = models.CharField(max_length=180, blank=True)
    caption = models.CharField(max_length=220, blank=True)
    image = models.ImageField(upload_to="public_site/gallery/images/")
    sort_order = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_public_gallery_images",
    )

    class Meta:
        ordering = ("sort_order", "id")

    def clean(self):
        self.title = (self.title or "").strip()
        self.caption = (self.caption or "").strip()

    def __str__(self):
        return self.title or f"Gallery image #{self.pk or 'new'}"


class PublicNewsPost(TimeStampedModel):
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.CharField(max_length=120, default="School News")
    published_on = models.DateField(default=timezone.localdate)
    summary = models.TextField()
    body = models.TextField()
    image = models.ImageField(upload_to="public_site/news/", blank=True, null=True)
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=10)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_public_news_posts",
    )

    class Meta:
        ordering = ("sort_order", "-published_on", "-created_at")

    def clean(self):
        self.title = (self.title or "").strip()
        self.category = (self.category or "").strip()
        self.summary = (self.summary or "").strip()
        self.body = (self.body or "").strip()
        if not self.slug:
            self.slug = slugify(self.title)

    def body_paragraphs(self):
        return [line.strip() for line in (self.body or "").splitlines() if line.strip()]

    def __str__(self):
        return self.title


class PublicEventPost(TimeStampedModel):
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    meta = models.CharField(max_length=120, default="School Event")
    event_date = models.DateField(default=timezone.localdate)
    location = models.CharField(max_length=220, blank=True)
    summary = models.TextField()
    body = models.TextField(blank=True)
    image = models.ImageField(upload_to="public_site/events/", blank=True, null=True)
    is_published = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=10)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_public_event_posts",
    )

    class Meta:
        ordering = ("sort_order", "event_date", "title")

    def clean(self):
        self.title = (self.title or "").strip()
        self.meta = (self.meta or "").strip()
        self.location = (self.location or "").strip()
        self.summary = (self.summary or "").strip()
        self.body = (self.body or "").strip()
        if not self.slug:
            self.slug = slugify(self.title)

    def body_paragraphs(self):
        return [line.strip() for line in (self.body or "").splitlines() if line.strip()]

    def __str__(self):
        return self.title


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


class LMSSubmissionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    GRADED = "GRADED", "Graded"
    REVISION_REQUIRED = "REVISION_REQUIRED", "Revision Required"


class LMSClassroom(TimeStampedModel):
    teacher_assignment = models.OneToOneField(
        TeacherSubjectAssignment,
        on_delete=models.CASCADE,
        related_name="lms_classroom",
    )
    title = models.CharField(max_length=180)
    overview = models.TextField(blank=True)
    welcome_note = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("teacher_assignment__academic_class__code", "teacher_assignment__subject__name")

    def clean(self):
        self.title = (self.title or "").strip()
        self.overview = (self.overview or "").strip()
        self.welcome_note = (self.welcome_note or "").strip()
        if not self.title:
            self.title = (
                f"{self.teacher_assignment.academic_class.code} "
                f"{self.teacher_assignment.subject.name}"
            )

    def __str__(self):
        return self.title


class LMSModule(TimeStampedModel):
    classroom = models.ForeignKey(
        LMSClassroom,
        on_delete=models.CASCADE,
        related_name="modules",
    )
    title = models.CharField(max_length=180)
    summary = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "created_at")

    def clean(self):
        self.title = (self.title or "").strip()
        self.summary = (self.summary or "").strip()
        if not self.title:
            raise ValidationError("Module title is required.")

    def __str__(self):
        return f"{self.classroom.title}: {self.title}"


class LMSLesson(TimeStampedModel):
    module = models.ForeignKey(
        LMSModule,
        on_delete=models.CASCADE,
        related_name="lessons",
    )
    title = models.CharField(max_length=180)
    summary = models.TextField(blank=True)
    content_text = models.TextField(blank=True)
    resource_file = models.FileField(upload_to="learning/lms_lessons/", blank=True, null=True)
    external_url = models.URLField(blank=True)
    estimated_minutes = models.PositiveIntegerField(default=20)
    sort_order = models.PositiveIntegerField(default=1)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "created_at")

    def clean(self):
        self.title = (self.title or "").strip()
        self.summary = (self.summary or "").strip()
        self.content_text = (self.content_text or "").strip()
        if not self.title:
            raise ValidationError("Lesson title is required.")
        has_payload = bool(self.content_text or self.resource_file or (self.external_url or "").strip())
        if not has_payload:
            raise ValidationError("Provide lesson text, a file, or an external URL.")

    def __str__(self):
        return f"{self.module}: {self.title}"


class LMSAssignment(TimeStampedModel):
    classroom = models.ForeignKey(
        LMSClassroom,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    module = models.ForeignKey(
        LMSModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    title = models.CharField(max_length=180)
    instructions = models.TextField()
    attachment_file = models.FileField(upload_to="learning/lms_assignments/", blank=True, null=True)
    due_at = models.DateTimeField(null=True, blank=True)
    max_score = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    allow_late_submissions = models.BooleanField(default=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ("due_at", "-created_at")

    def clean(self):
        self.title = (self.title or "").strip()
        self.instructions = (self.instructions or "").strip()
        if not self.title:
            raise ValidationError("Assignment title is required.")
        if not self.instructions:
            raise ValidationError("Assignment instructions are required.")
        if self.max_score <= 0:
            raise ValidationError("Assignment max score must be greater than zero.")
        if self.module_id and self.module.classroom_id != self.classroom_id:
            raise ValidationError("Selected module does not belong to the classroom.")

    def __str__(self):
        return f"{self.classroom.title}: {self.title}"


class LMSLessonProgress(TimeStampedModel):
    lesson = models.ForeignKey(
        LMSLesson,
        on_delete=models.CASCADE,
        related_name="progress_rows",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lms_lesson_progress",
    )
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("lesson", "student"),
                name="unique_lms_lesson_progress_per_student",
            )
        ]

    def clean(self):
        if self.student_id and hasattr(self.student, "has_role") and not self.student.has_role("STUDENT"):
            raise ValidationError("Lesson progress can only target student accounts.")

    def __str__(self):
        return f"{self.student} -> {self.lesson}"


class LMSAssignmentSubmission(TimeStampedModel):
    assignment = models.ForeignKey(
        LMSAssignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lms_assignment_submissions",
    )
    submission_text = models.TextField(blank=True)
    submission_file = models.FileField(upload_to="learning/lms_submissions/", blank=True, null=True)
    status = models.CharField(
        max_length=24,
        choices=LMSSubmissionStatus.choices,
        default=LMSSubmissionStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_lms_submissions",
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("assignment", "student"),
                name="unique_lms_submission_per_assignment_student",
            )
        ]

    def clean(self):
        if self.student_id and hasattr(self.student, "has_role") and not self.student.has_role("STUDENT"):
            raise ValidationError("Assignment submissions can only target student accounts.")
        self.submission_text = (self.submission_text or "").strip()
        self.feedback = (self.feedback or "").strip()
        has_payload = bool(self.submission_text or self.submission_file)
        if self.status in {LMSSubmissionStatus.SUBMITTED, LMSSubmissionStatus.GRADED, LMSSubmissionStatus.REVISION_REQUIRED} and not has_payload:
            raise ValidationError("Provide submission text or a file before submitting.")
        if self.score is not None and self.score < 0:
            raise ValidationError("Submission score cannot be negative.")
        if self.score is not None and self.assignment_id and self.score > self.assignment.max_score:
            raise ValidationError("Submission score cannot exceed the assignment max score.")

    def save(self, *args, **kwargs):
        if self.status in {LMSSubmissionStatus.SUBMITTED, LMSSubmissionStatus.GRADED, LMSSubmissionStatus.REVISION_REQUIRED} and self.submitted_at is None:
            self.submitted_at = timezone.now()
        if self.status in {LMSSubmissionStatus.GRADED, LMSSubmissionStatus.REVISION_REQUIRED} and self.graded_at is None:
            self.graded_at = timezone.now()
        if self.status == LMSSubmissionStatus.SUBMITTED:
            self.score = None
            self.feedback = ""
            self.graded_by = None
            self.graded_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} -> {self.assignment}"


class LMSDiscussionComment(TimeStampedModel):
    classroom = models.ForeignKey(
        LMSClassroom,
        on_delete=models.CASCADE,
        related_name="discussion_comments",
    )
    module = models.ForeignKey(
        LMSModule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discussion_comments",
    )
    assignment = models.ForeignKey(
        LMSAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="discussion_comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="lms_discussion_comments",
    )
    body = models.TextField()
    is_staff_note = models.BooleanField(default=False)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        self.body = (self.body or "").strip()
        if not self.body:
            raise ValidationError("Comment body is required.")
        if self.module_id and self.module.classroom_id != self.classroom_id:
            raise ValidationError("Selected module does not belong to the classroom.")
        if self.assignment_id and self.assignment.classroom_id != self.classroom_id:
            raise ValidationError("Selected assignment does not belong to the classroom.")

    def __str__(self):
        return f"{self.author} -> {self.classroom}"


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

