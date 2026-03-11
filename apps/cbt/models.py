from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.constants import ROLE_STUDENT
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from core.models import TimeStampedModel


class CBTQuestionType(models.TextChoices):
    OBJECTIVE = "OBJECTIVE", "Objective"
    MULTI_SELECT = "MULTI_SELECT", "Multi Select"
    SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"
    LABELING = "LABELING", "Diagram Labeling"
    MATCHING = "MATCHING", "Matching"
    ORDERING = "ORDERING", "Drag/Drop Ordering"


class CBTQuestionDifficulty(models.TextChoices):
    EASY = "EASY", "Easy"
    MEDIUM = "MEDIUM", "Medium"
    HARD = "HARD", "Hard"


class CBTExamType(models.TextChoices):
    CA = "CA", "CA"
    EXAM = "EXAM", "Exam"
    PRACTICAL = "PRACTICAL", "Practical"
    SIM = "SIM", "Simulation"
    FREE_TEST = "FREE_TEST", "Free Test"


class CBTExamStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_DEAN = "PENDING_DEAN", "Pending Dean"
    PENDING_IT = "PENDING_IT", "Pending IT"
    APPROVED = "APPROVED", "Approved"
    ACTIVE = "ACTIVE", "Active"
    CLOSED = "CLOSED", "Closed"


class CBTDocumentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCESS = "SUCCESS", "Success"
    FAILED = "FAILED", "Failed"


class CBTWritebackTarget(models.TextChoices):
    NONE = "NONE", "No Writeback"
    CA1 = "CA1", "CA1"
    CA2 = "CA2", "CA2"
    CA3 = "CA3", "CA3"
    CA4 = "CA4", "CA4"
    OBJECTIVE = "OBJECTIVE", "Exam Objective"
    THEORY = "THEORY", "Exam Theory"


class CBTAttemptStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    SUBMITTED = "SUBMITTED", "Submitted"
    FINALIZED = "FINALIZED", "Finalized"


class CBTSimulationToolCategory(models.TextChoices):
    SCIENCE = "SCIENCE", "Science"
    MATHEMATICS = "MATHEMATICS", "Mathematics"
    ARTS = "ARTS", "Arts"
    HUMANITIES = "HUMANITIES", "Humanities"
    BUSINESS = "BUSINESS", "Business"
    COMPUTER_SCIENCE = "COMPUTER_SCIENCE", "Computer Science"


class CBTSimulationScoreMode(models.TextChoices):
    AUTO = "AUTO", "Auto"
    VERIFY = "VERIFY", "Verify"
    RUBRIC = "RUBRIC", "Rubric"


class CBTSimulationSourceProvider(models.TextChoices):
    PHET = "PHET", "PhET"
    H5P = "H5P", "H5P"
    GEOGEBRA = "GEOGEBRA", "GeoGebra"
    DESMOS = "DESMOS", "Desmos"
    LABXCHANGE = "LABXCHANGE", "LabXchange"
    PYODIDE = "PYODIDE", "Pyodide/Skulpt"
    OTHER = "OTHER", "Other"


class CBTSimulationCallbackType(models.TextChoices):
    POST_MESSAGE = "POST_MESSAGE", "postMessage"
    XAPI_STATEMENT = "XAPI_STATEMENT", "xAPI Statement"
    H5P_XAPI = "H5P_XAPI", "H5P xAPI"
    PHET_WRAPPER = "PHET_WRAPPER", "PhET Wrapper"


class CBTSimulationWrapperStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_DEAN = "PENDING_DEAN", "Pending Dean"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class CBTSimulationAttemptStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not Started"
    AUTO_CAPTURED = "AUTO_CAPTURED", "Auto Captured"
    VERIFY_PENDING = "VERIFY_PENDING", "Verify Pending"
    VERIFIED = "VERIFIED", "Verified"
    RUBRIC_PENDING = "RUBRIC_PENDING", "Rubric Pending"
    RUBRIC_SCORED = "RUBRIC_SCORED", "Rubric Scored"
    IMPORTED = "IMPORTED", "Imported"


class QuestionBank(TimeStampedModel):
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cbt_question_banks",
    )
    assignment = models.ForeignKey(
        TeacherSubjectAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_question_banks",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="cbt_question_banks",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="cbt_question_banks",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="cbt_question_banks",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="cbt_question_banks",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "name", "subject", "academic_class", "session", "term"),
                name="unique_owner_bank_name_per_assignment_context",
            ),
        ]

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.assignment_id:
            if self.subject_id and self.assignment.subject_id != self.subject_id:
                raise ValidationError("Question bank subject must match assignment subject.")
            if self.academic_class_id and self.assignment.academic_class_id != self.academic_class_id:
                raise ValidationError("Question bank class must match assignment class.")
            if self.session_id and self.assignment.session_id != self.session_id:
                raise ValidationError("Question bank session must match assignment session.")
            if self.term_id and self.assignment.term_id != self.term_id:
                raise ValidationError("Question bank term must match assignment term.")

    def __str__(self):
        return f"{self.name} ({self.subject.code} - {self.academic_class.code})"


class Question(TimeStampedModel):
    class SourceType(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        DOCUMENT = "DOCUMENT", "Document Import"

    question_bank = models.ForeignKey(
        QuestionBank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cbt_questions",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="cbt_questions",
    )
    question_type = models.CharField(
        max_length=20,
        choices=CBTQuestionType.choices,
        default=CBTQuestionType.OBJECTIVE,
    )
    stem = models.TextField()
    topic = models.CharField(max_length=120, blank=True)
    difficulty = models.CharField(
        max_length=10,
        choices=CBTQuestionDifficulty.choices,
        default=CBTQuestionDifficulty.MEDIUM,
    )
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.MANUAL,
    )
    source_reference = models.CharField(max_length=120, blank=True)
    rich_stem = models.TextField(blank=True)
    stimulus_image = models.FileField(
        upload_to="cbt/question_media/images/%Y/%m/",
        null=True,
        blank=True,
    )
    stimulus_video = models.FileField(
        upload_to="cbt/question_media/videos/%Y/%m/",
        null=True,
        blank=True,
    )
    stimulus_caption = models.CharField(max_length=255, blank=True)
    shared_stimulus_key = models.CharField(max_length=64, blank=True, db_index=True)
    dean_comment = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-updated_at",)

    def clean(self):
        if self.question_bank_id and self.question_bank.subject_id != self.subject_id:
            raise ValidationError("Question subject must match question bank subject.")
        if self.marks <= 0:
            raise ValidationError("Question marks must be greater than zero.")

    def __str__(self):
        return f"{self.subject.code}: {self.stem[:64]}"


class Option(TimeStampedModel):
    class Label(models.TextChoices):
        A = "A", "A"
        B = "B", "B"
        C = "C", "C"
        D = "D", "D"

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options",
    )
    label = models.CharField(max_length=1, choices=Label.choices)
    option_text = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("question_id", "sort_order", "label")
        constraints = [
            models.UniqueConstraint(
                fields=("question", "label"),
                name="unique_option_label_per_question",
            ),
        ]

    def __str__(self):
        return f"{self.question_id}-{self.label}"


class CorrectAnswer(TimeStampedModel):
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        related_name="correct_answer",
    )
    correct_options = models.ManyToManyField(
        Option,
        blank=True,
        related_name="correct_for",
    )
    note = models.TextField(blank=True)
    is_finalized = models.BooleanField(default=False)

    class Meta:
        ordering = ("question_id",)

    def clean(self):
        if not self.pk:
            return
        option_ids = list(self.correct_options.values_list("id", flat=True))
        if not option_ids:
            return
        invalid = self.correct_options.exclude(question=self.question).exists()
        if invalid:
            raise ValidationError("Correct answer options must belong to the same question.")
        selected_count = len(option_ids)
        if self.question.question_type == CBTQuestionType.OBJECTIVE and selected_count != 1:
            raise ValidationError("Objective questions require exactly one correct option.")
        if self.question.question_type == CBTQuestionType.MULTI_SELECT and selected_count < 1:
            raise ValidationError("Multi-select questions require at least one correct option.")

    def __str__(self):
        return f"Answer-{self.question_id}"


class Exam(TimeStampedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    exam_type = models.CharField(max_length=20, choices=CBTExamType.choices)
    status = models.CharField(
        max_length=20,
        choices=CBTExamStatus.choices,
        default=CBTExamStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cbt_exams",
    )
    assignment = models.ForeignKey(
        TeacherSubjectAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_exams",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="cbt_exams",
    )
    academic_class = models.ForeignKey(
        AcademicClass,
        on_delete=models.CASCADE,
        related_name="cbt_exams",
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name="cbt_exams",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="cbt_exams",
    )
    question_bank = models.ForeignKey(
        QuestionBank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exams",
    )
    dean_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_dean_reviews",
    )
    dean_reviewed_at = models.DateTimeField(null=True, blank=True)
    dean_review_comment = models.TextField(blank=True)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_it_activations",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    activation_comment = models.TextField(blank=True)
    schedule_start = models.DateTimeField(null=True, blank=True)
    schedule_end = models.DateTimeField(null=True, blank=True)
    is_time_based = models.BooleanField(default=True)
    open_now = models.BooleanField(default=False)
    is_free_test = models.BooleanField(default=False)
    activation_snapshot = models.JSONField(default=dict, blank=True)
    activation_snapshot_hash = models.CharField(max_length=64, blank=True, db_index=True)
    timer_is_paused = models.BooleanField(default=False)
    timer_paused_at = models.DateTimeField(null=True, blank=True)
    timer_paused_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_exam_timer_pauses",
    )
    timer_pause_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-updated_at",)

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError("Selected term does not belong to selected session.")
        if self.assignment_id:
            if self.assignment.subject_id != self.subject_id:
                raise ValidationError("Exam subject must match assignment subject.")
            if self.assignment.academic_class_id != self.academic_class_id:
                raise ValidationError("Exam class must match assignment class.")
            if self.assignment.session_id != self.session_id:
                raise ValidationError("Exam session must match assignment session.")
            if self.assignment.term_id != self.term_id:
                raise ValidationError("Exam term must match assignment term.")
        if self.question_bank_id:
            if self.question_bank.subject_id != self.subject_id:
                raise ValidationError("Exam subject must match question bank subject.")
            if self.question_bank.academic_class_id != self.academic_class_id:
                raise ValidationError("Exam class must match question bank class.")
            if self.question_bank.session_id != self.session_id:
                raise ValidationError("Exam session must match question bank session.")
            if self.question_bank.term_id != self.term_id:
                raise ValidationError("Exam term must match question bank term.")
        if self.status == CBTExamStatus.ACTIVE:
            if not self.is_free_test and not self.dean_reviewed_by_id:
                raise ValidationError("Exam cannot be active before Dean approval.")
            if not self.activated_by_id:
                raise ValidationError("Exam cannot be active before IT activation.")
            if self.is_time_based and not self.open_now:
                if not self.schedule_start or not self.schedule_end:
                    raise ValidationError(
                        "Time-based exam requires schedule start and end."
                    )
                if self.schedule_end <= self.schedule_start:
                    raise ValidationError("Schedule end must be after start.")

    def __str__(self):
        return f"{self.title} ({self.subject.code} - {self.get_status_display()})"


class ExamBlueprint(TimeStampedModel):
    exam = models.OneToOneField(
        Exam,
        on_delete=models.CASCADE,
        related_name="blueprint",
    )
    duration_minutes = models.PositiveIntegerField(default=60)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    instructions = models.TextField(blank=True)
    section_config = models.JSONField(default=list, blank=True)
    passing_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    objective_writeback_target = models.CharField(
        max_length=20,
        choices=CBTWritebackTarget.choices,
        default=CBTWritebackTarget.OBJECTIVE,
    )
    theory_enabled = models.BooleanField(default=False)
    theory_writeback_target = models.CharField(
        max_length=20,
        choices=CBTWritebackTarget.choices,
        default=CBTWritebackTarget.THEORY,
    )
    auto_show_result_on_submit = models.BooleanField(default=True)
    finalize_on_logout = models.BooleanField(default=False)
    allow_retake = models.BooleanField(default=False)

    class Meta:
        ordering = ("exam_id",)

    def clean(self):
        section_config = self.section_config if isinstance(self.section_config, dict) else {}
        manual_score_split = bool(section_config.get("manual_score_split"))
        if self.duration_minutes < 1:
            raise ValidationError("Duration must be at least 1 minute.")
        if self.max_attempts < 1:
            raise ValidationError("Max attempts must be at least 1.")
        if self.passing_score < 0 or self.passing_score > 100:
            raise ValidationError("Passing score must be between 0 and 100.")
        if self.objective_writeback_target not in {
            CBTWritebackTarget.CA1,
            CBTWritebackTarget.CA2,
            CBTWritebackTarget.CA3,
            CBTWritebackTarget.CA4,
            CBTWritebackTarget.OBJECTIVE,
            CBTWritebackTarget.NONE,
        }:
            raise ValidationError("Invalid objective writeback target.")
        if self.objective_writeback_target == CBTWritebackTarget.THEORY:
            raise ValidationError("Objective writeback target cannot be theory.")
        if self.theory_enabled and self.theory_writeback_target == CBTWritebackTarget.NONE and not manual_score_split:
            raise ValidationError("Theory writeback target must be set when theory is enabled.")
        if self.theory_enabled and self.theory_writeback_target == CBTWritebackTarget.OBJECTIVE:
            raise ValidationError("Theory writeback target cannot be objective.")

    def __str__(self):
        return f"Blueprint-{self.exam_id}"


class ExamQuestion(TimeStampedModel):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_questions",
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="exam_links",
    )
    sort_order = models.PositiveIntegerField(default=1)
    marks = models.DecimalField(max_digits=5, decimal_places=2, default=1)

    class Meta:
        ordering = ("exam_id", "sort_order")
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "question"),
                name="unique_question_per_exam",
            ),
            models.UniqueConstraint(
                fields=("exam", "sort_order"),
                name="unique_question_order_per_exam",
            ),
        ]

    def clean(self):
        if self.question.subject_id != self.exam.subject_id:
            raise ValidationError("Exam question subject must match exam subject.")
        if self.marks <= 0:
            raise ValidationError("Exam question marks must be greater than zero.")

    def __str__(self):
        return f"{self.exam_id}-{self.sort_order}"


class SimulationWrapper(TimeStampedModel):
    tool_name = models.CharField(max_length=180)
    tool_type = models.CharField(max_length=80, blank=True)
    source_provider = models.CharField(
        max_length=32,
        choices=CBTSimulationSourceProvider.choices,
        default=CBTSimulationSourceProvider.OTHER,
    )
    source_reference_url = models.URLField(blank=True)
    tool_category = models.CharField(
        max_length=32,
        choices=CBTSimulationToolCategory.choices,
    )
    description = models.TextField(blank=True)
    online_url = models.URLField(blank=True)
    offline_asset_path = models.CharField(max_length=255, blank=True)
    score_mode = models.CharField(
        max_length=20,
        choices=CBTSimulationScoreMode.choices,
    )
    max_score = models.DecimalField(max_digits=7, decimal_places=2, default=10)
    scoring_callback_type = models.CharField(
        max_length=64,
        choices=CBTSimulationCallbackType.choices,
        default=CBTSimulationCallbackType.POST_MESSAGE,
    )
    evidence_required = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=CBTSimulationWrapperStatus.choices,
        default=CBTSimulationWrapperStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_simulation_wrappers_created",
    )
    dean_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_simulation_wrappers_reviewed",
    )
    dean_reviewed_at = models.DateTimeField(null=True, blank=True)
    dean_review_comment = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("tool_name", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("tool_name", "tool_category"),
                name="unique_simulation_tool_name_per_category",
            )
        ]

    def clean(self):
        if self.max_score <= 0:
            raise ValidationError("Simulation max score must be greater than zero.")
        if not (self.online_url or self.offline_asset_path):
            raise ValidationError("Provide online URL or offline asset path for simulation.")
        if self.score_mode == CBTSimulationScoreMode.AUTO and not self.scoring_callback_type:
            raise ValidationError("Auto score mode requires a callback type.")
        if self.score_mode == CBTSimulationScoreMode.AUTO and self.scoring_callback_type == "":
            raise ValidationError("Auto score mode requires callback integration.")
        if self.score_mode == CBTSimulationScoreMode.VERIFY and not self.evidence_required:
            self.evidence_required = True

    def __str__(self):
        return f"{self.tool_name} ({self.get_tool_category_display()})"


class ExamSimulation(TimeStampedModel):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="exam_simulations",
    )
    simulation_wrapper = models.ForeignKey(
        SimulationWrapper,
        on_delete=models.CASCADE,
        related_name="exam_links",
    )
    sort_order = models.PositiveIntegerField(default=1)
    writeback_target = models.CharField(
        max_length=20,
        choices=CBTWritebackTarget.choices,
        default=CBTWritebackTarget.CA3,
    )
    max_score_override = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_required = models.BooleanField(default=True)

    class Meta:
        ordering = ("exam_id", "sort_order")
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "simulation_wrapper"),
                name="unique_simulation_wrapper_per_exam",
            ),
            models.UniqueConstraint(
                fields=("exam", "sort_order"),
                name="unique_simulation_order_per_exam",
            ),
        ]

    @property
    def effective_max_score(self):
        return self.max_score_override or self.simulation_wrapper.max_score

    def clean(self):
        if self.max_score_override is not None and self.max_score_override <= 0:
            raise ValidationError("Simulation max score override must be greater than zero.")
        if (
            self.simulation_wrapper_id
            and self.simulation_wrapper.status != CBTSimulationWrapperStatus.APPROVED
        ):
            raise ValidationError("Only Dean-approved simulations can be linked to exams.")

    def __str__(self):
        return f"{self.exam_id}-{self.sort_order}-{self.simulation_wrapper.tool_name}"


class ExamReviewAction(TimeStampedModel):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="review_actions",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_review_actions",
    )
    from_status = models.CharField(max_length=20, choices=CBTExamStatus.choices)
    to_status = models.CharField(max_length=20, choices=CBTExamStatus.choices)
    action = models.CharField(max_length=64)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ("created_at",)
        indexes = [models.Index(fields=("exam", "created_at"))]

    def __str__(self):
        return f"{self.exam_id}: {self.from_status}->{self.to_status}"


class ExamDocumentImport(TimeStampedModel):
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cbt_import_uploads",
    )
    assignment = models.ForeignKey(
        TeacherSubjectAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_import_uploads",
    )
    exam = models.ForeignKey(
        Exam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_sources",
    )
    source_file = models.FileField(upload_to="cbt/imports/%Y/%m/")
    source_filename = models.CharField(max_length=255)
    extraction_status = models.CharField(
        max_length=20,
        choices=CBTDocumentStatus.choices,
        default=CBTDocumentStatus.PENDING,
    )
    extracted_text = models.TextField(blank=True)
    parse_summary = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.source_filename} ({self.get_extraction_status_display()})"


class ExamAttempt(TimeStampedModel):
    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cbt_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=CBTAttemptStatus.choices,
        default=CBTAttemptStatus.IN_PROGRESS,
    )
    attempt_number = models.PositiveSmallIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    objective_raw_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    objective_max_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    objective_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    theory_raw_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    theory_max_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    theory_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    total_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    auto_marking_completed = models.BooleanField(default=False)
    theory_marking_completed = models.BooleanField(default=False)
    writeback_completed = models.BooleanField(default=False)
    writeback_metadata = models.JSONField(default=dict, blank=True)
    is_locked = models.BooleanField(default=False)
    lock_reason = models.CharField(max_length=64, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    allow_resume_by_it = models.BooleanField(default=False)
    extra_time_minutes = models.PositiveIntegerField(default=0)
    timer_pause_seconds = models.PositiveIntegerField(default=0)
    active_tab_token = models.CharField(max_length=120, blank=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    integrity_bundle = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("exam", "student", "attempt_number"),
                name="unique_attempt_number_per_exam_student",
            ),
        ]
        indexes = [
            models.Index(fields=("exam", "student")),
            models.Index(fields=("status", "updated_at")),
        ]

    def clean(self):
        if self.exam_id and self.student_id:
            if self.student.has_role(ROLE_STUDENT) is False:
                raise ValidationError("Only student users can own CBT attempts.")

    def __str__(self):
        return f"{self.student.username} -> {self.exam.title} ({self.attempt_number})"


class ExamAttemptAnswer(TimeStampedModel):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    exam_question = models.ForeignKey(
        ExamQuestion,
        on_delete=models.CASCADE,
        related_name="attempt_answers",
    )
    selected_options = models.ManyToManyField(
        Option,
        blank=True,
        related_name="attempt_answers",
    )
    response_text = models.TextField(blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    is_flagged = models.BooleanField(default=False)
    is_correct = models.BooleanField(null=True, blank=True)
    auto_score = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    teacher_score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    teacher_marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_marked_answers",
    )
    teacher_marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("exam_question__sort_order",)
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "exam_question"),
                name="unique_answer_per_exam_question_per_attempt",
            ),
        ]

    def clean(self):
        if self.attempt_id and self.exam_question_id:
            if self.exam_question.exam_id != self.attempt.exam_id:
                raise ValidationError("Attempt answer question must belong to attempt exam.")
        if self.pk and self.selected_options.exclude(question=self.exam_question.question).exists():
            raise ValidationError("Selected options must belong to the answer question.")

    def __str__(self):
        return f"{self.attempt_id}-{self.exam_question_id}"


class SimulationAttemptRecord(TimeStampedModel):
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="simulation_attempts",
    )
    exam_simulation = models.ForeignKey(
        ExamSimulation,
        on_delete=models.CASCADE,
        related_name="attempt_records",
    )
    status = models.CharField(
        max_length=20,
        choices=CBTSimulationAttemptStatus.choices,
        default=CBTSimulationAttemptStatus.NOT_STARTED,
    )
    raw_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    final_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    callback_payload = models.JSONField(default=dict, blank=True)
    evidence_file = models.FileField(
        upload_to="cbt/simulation_evidence/%Y/%m/",
        null=True,
        blank=True,
    )
    evidence_note = models.TextField(blank=True)
    verify_comment = models.TextField(blank=True)
    rubric_breakdown = models.JSONField(default=dict, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_verified_simulation_scores",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    imported_target = models.CharField(
        max_length=20,
        choices=CBTWritebackTarget.choices,
        default=CBTWritebackTarget.NONE,
    )
    imported_score = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cbt_imported_simulation_scores",
    )
    imported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("exam_simulation__sort_order",)
        constraints = [
            models.UniqueConstraint(
                fields=("attempt", "exam_simulation"),
                name="unique_simulation_record_per_attempt",
            )
        ]
        indexes = [
            models.Index(fields=("status", "updated_at")),
            models.Index(fields=("attempt", "status")),
        ]

    def clean(self):
        if self.attempt_id and self.exam_simulation_id:
            if self.exam_simulation.exam_id != self.attempt.exam_id:
                raise ValidationError("Simulation record must match attempt exam.")
        max_score = self.exam_simulation.effective_max_score if self.exam_simulation_id else None
        if self.final_score is not None and max_score is not None:
            if self.final_score < 0 or self.final_score > max_score:
                raise ValidationError("Final simulation score must be within simulation max range.")
        if self.status == CBTSimulationAttemptStatus.VERIFY_PENDING and self.exam_simulation_id:
            if self.exam_simulation.simulation_wrapper.evidence_required and not self.evidence_file:
                raise ValidationError("Evidence file is required for this simulation.")

    def __str__(self):
        return f"{self.attempt_id}-{self.exam_simulation_id}-{self.status}"
