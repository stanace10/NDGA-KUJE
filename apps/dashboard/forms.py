from django import forms

from apps.academics.models import AcademicClass, AcademicSession, Subject, TeacherSubjectAssignment, Term
from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import User
from apps.dashboard.models import Club, LearningResource, LessonPlanDraft, PortalDocument, SchoolProfile, StudentClubMembership, WeeklyChallenge, WeeklyChallengeSubmission
from apps.setup_wizard.services import get_setup_state
from core.upload_scan import validate_document_upload


class _StyledFormMixin:
    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "h-4 w-4 rounded border-slate-300 text-ndga-navy")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault(
                    "class",
                    "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                )
                widget.attrs.setdefault("rows", 4)
            else:
                widget.attrs.setdefault(
                    "class",
                    "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class StudentDisplaySettingsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("display_name",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["display_name"].required = False
        self.fields["display_name"].help_text = (
            "Optional nickname used on dashboard welcome cards."
        )
        self.fields["display_name"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "Example: Zee",
                "maxlength": "80",
            }
        )

    def clean_display_name(self):
        value = (self.cleaned_data.get("display_name") or "").strip()
        return value


PRIVILEGED_SECURITY_ROLE_CODES = {ROLE_IT_MANAGER, ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL}


class PrivilegedSecuritySettingsForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("two_factor_enabled", "two_factor_email")

    def __init__(self, *args, user=None, **kwargs):
        self.actor = user
        super().__init__(*args, **kwargs)
        self.fields["two_factor_enabled"].required = False
        self.fields["two_factor_enabled"].label = "Enable email verification for privileged sign-in"
        self.fields["two_factor_email"].required = False
        self.fields["two_factor_email"].help_text = (
            "Brevo will send the login code to this address. If left blank, the account email is used."
        )
        self.fields["two_factor_email"].widget.attrs.setdefault(
            "placeholder",
            "security@ndgakuje.org",
        )

    def clean_two_factor_email(self):
        return (self.cleaned_data.get("two_factor_email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        enabled = bool(cleaned.get("two_factor_enabled"))
        email = cleaned.get("two_factor_email") or (getattr(self.instance, "email", "") or "").strip()
        if enabled and not email:
            self.add_error(
                "two_factor_email",
                "Add a verification email or save a valid account email before enabling two-factor sign-in.",
            )
        return cleaned


class PrincipalSignatureForm(forms.Form):
    signature_image = forms.ImageField(required=False)
    signature_data = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["signature_image"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "accept": "image/png,image/jpeg,image/jpg",
            }
        )

    def clean_signature_data(self):
        value = (self.cleaned_data.get("signature_data") or "").strip()
        if value and (not value.startswith("data:image/") or ";base64," not in value):
            raise forms.ValidationError("Invalid signature pad payload.")
        return value


class SchoolProfileForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolProfile
        fields = (
            "school_name",
            "address",
            "contact_email",
            "contact_phone",
            "website",
            "result_tagline",
            "principal_name",
            "report_footer",
            "ca1_label",
            "ca2_label",
            "ca3_label",
            "assignment_label",
            "promotion_average_threshold",
            "promotion_attendance_threshold",
            "promotion_policy_note",
            "auto_comment_guidance",
            "teacher_comment_guidance",
            "dean_comment_guidance",
            "principal_comment_guidance",
            "doctor_remark_guidance",
            "require_result_access_pin",
            "school_logo",
            "school_stamp",
        )
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "promotion_policy_note": forms.Textarea(attrs={"rows": 3}),
            "auto_comment_guidance": forms.Textarea(attrs={"rows": 4}),
            "teacher_comment_guidance": forms.Textarea(attrs={"rows": 3}),
            "dean_comment_guidance": forms.Textarea(attrs={"rows": 3}),
            "principal_comment_guidance": forms.Textarea(attrs={"rows": 3}),
            "doctor_remark_guidance": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_logo"].required = False
        self.fields["school_stamp"].required = False
        self.fields["school_logo"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg,image/svg+xml"
        )
        self.fields["school_stamp"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg,image/svg+xml"
        )


class ClubForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Club
        fields = ("name", "code", "description", "patron", "is_active")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patron"].queryset = User.objects.filter(staff_profile__isnull=False, is_active=True).order_by("first_name", "last_name", "username")
        self.fields["patron"].required = False


class StudentClubMembershipForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = StudentClubMembership
        fields = ("student", "club", "session", "office_held", "significant_contribution", "is_active")
        widgets = {"significant_contribution": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = User.objects.filter(primary_role__code="STUDENT", is_active=True).select_related("student_profile").order_by("student_profile__student_number", "username")
        self.fields["club"].queryset = Club.objects.filter(is_active=True).order_by("name")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")



class AITutorQuestionForm(_StyledFormMixin, forms.Form):
    subject = forms.ModelChoiceField(queryset=Subject.objects.none(), required=False)
    question = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), max_length=1000)

    def __init__(self, *args, student=None, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Subject.objects.filter(is_active=True).order_by("name")
        if student and session:
            queryset = queryset.filter(student_enrollments__student=student, student_enrollments__session=session, student_enrollments__is_active=True).distinct()
        self.fields["subject"].queryset = queryset
        self.fields["subject"].empty_label = "Any Subject"
        self.fields["question"].widget.attrs.setdefault("placeholder", "Ask for an explanation, practice strategy, or revision help.")


class LessonPlannerForm(_StyledFormMixin, forms.Form):
    academic_class = forms.ModelChoiceField(queryset=AcademicClass.objects.none())
    subject = forms.ModelChoiceField(queryset=Subject.objects.none())
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    term = forms.ModelChoiceField(queryset=Term.objects.none())
    topic = forms.CharField(max_length=180)
    teaching_goal = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    teacher_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    publish_to_learning_hub = forms.BooleanField(required=False, initial=True)
    assignment_due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        assignment_qs = TeacherSubjectAssignment.objects.filter(is_active=True).select_related("academic_class", "subject", "session", "term")
        if teacher is not None:
            assignment_qs = assignment_qs.filter(teacher=teacher)
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(id__in=assignment_qs.values("academic_class_id").distinct()).order_by("code")
        self.fields["subject"].queryset = Subject.objects.filter(id__in=assignment_qs.values("subject_id").distinct()).order_by("name")
        self.fields["session"].queryset = AcademicSession.objects.filter(id__in=assignment_qs.values("session_id").distinct()).order_by("-name")
        self.fields["term"].queryset = Term.objects.filter(id__in=assignment_qs.values("term_id").distinct()).order_by("-session__name", "name")
        setup_state = get_setup_state()
        if setup_state.current_session_id and not self.initial.get("session"):
            self.initial["session"] = setup_state.current_session_id
        if setup_state.current_term_id and not self.initial.get("term"):
            self.initial["term"] = setup_state.current_term_id

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get("session")
        term = cleaned.get("term")
        academic_class = cleaned.get("academic_class")
        subject = cleaned.get("subject")
        if session and term and term.session_id != session.id:
            self.add_error("term", "Selected term does not belong to the selected session.")
        if cleaned.get("assignment_due_date") and not cleaned.get("publish_to_learning_hub"):
            self.add_error("publish_to_learning_hub", "Publishing must be enabled if assignment due date is set.")
        if self.teacher and academic_class and subject and session and term:
            assigned = TeacherSubjectAssignment.objects.filter(
                teacher=self.teacher,
                academic_class=academic_class,
                subject=subject,
                session=session,
                term=term,
                is_active=True,
            ).exists()
            if not assigned:
                self.add_error("subject", "Select a class, subject, session, and term combination assigned to you.")
        return cleaned


class LearningResourceForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LearningResource
        fields = (
            "title",
            "description",
            "category",
            "academic_class",
            "subject",
            "session",
            "term",
            "content_text",
            "resource_file",
            "external_url",
            "due_date",
            "is_published",
        )
        widgets = {
            "content_text": forms.Textarea(attrs={"rows": 4}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        assignment_qs = TeacherSubjectAssignment.objects.filter(is_active=True).select_related("academic_class", "subject", "session", "term")
        if teacher is not None:
            assignment_qs = assignment_qs.filter(teacher=teacher)
        class_ids = assignment_qs.values("academic_class_id").distinct()
        subject_ids = assignment_qs.values("subject_id").distinct()
        session_ids = assignment_qs.values("session_id").distinct()
        term_ids = assignment_qs.values("term_id").distinct()
        if teacher is not None:
            self.fields["academic_class"].queryset = AcademicClass.objects.filter(id__in=class_ids).order_by("code")
            self.fields["subject"].queryset = Subject.objects.filter(id__in=subject_ids).order_by("name")
            self.fields["session"].queryset = AcademicSession.objects.filter(id__in=session_ids).order_by("-name")
            self.fields["term"].queryset = Term.objects.filter(id__in=term_ids).order_by("-session__name", "name")
        else:
            self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True).order_by("code")
            self.fields["subject"].queryset = Subject.objects.filter(is_active=True).order_by("name")
            self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
            self.fields["term"].queryset = Term.objects.order_by("-session__name", "name")
        self.fields["resource_file"].required = False
        self.fields["external_url"].required = False
        self.fields["content_text"].required = False

    def clean_resource_file(self):
        uploaded = self.cleaned_data.get("resource_file")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get("session")
        term = cleaned.get("term")
        academic_class = cleaned.get("academic_class")
        subject = cleaned.get("subject")
        if session and term and term.session_id != session.id:
            self.add_error("term", "Selected term does not belong to the selected session.")
        if self.teacher and academic_class and subject:
            filters = {
                "teacher": self.teacher,
                "academic_class": academic_class,
                "subject": subject,
                "is_active": True,
            }
            if session:
                filters["session"] = session
            if term:
                filters["term"] = term
            assigned = TeacherSubjectAssignment.objects.filter(**filters).exists()
            if not assigned:
                self.add_error("subject", "Select a class and subject combination assigned to you.")
        return cleaned


class DocumentVaultUploadForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PortalDocument
        fields = (
            "title",
            "category",
            "student",
            "academic_class",
            "session",
            "term",
            "document_file",
            "notes",
            "is_visible_to_student",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = User.objects.filter(primary_role__code="STUDENT", is_active=True).order_by("username")
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True).order_by("code")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.order_by("-session__name", "name")

    def clean_document_file(self):
        uploaded = self.cleaned_data.get("document_file")
        validate_document_upload(uploaded)
        return uploaded

class WeeklyChallengeForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WeeklyChallenge
        fields = (
            "week_label",
            "title",
            "instructions",
            "question_text",
            "answer_guidance",
            "accepted_answer_keywords",
            "academic_class",
            "session",
            "term",
            "reward_points",
            "is_published",
        )
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "question_text": forms.Textarea(attrs={"rows": 4}),
            "answer_guidance": forms.Textarea(attrs={"rows": 3}),
            "accepted_answer_keywords": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["academic_class"].queryset = AcademicClass.objects.filter(is_active=True).select_related("base_class").order_by("code")
        self.fields["session"].queryset = AcademicSession.objects.order_by("-name")
        self.fields["term"].queryset = Term.objects.order_by("-session__name", "name")
        self.fields["academic_class"].required = False
        self.fields["session"].required = False
        self.fields["term"].required = False

    def clean(self):
        cleaned = super().clean()
        session = cleaned.get("session")
        term = cleaned.get("term")
        if session and term and term.session_id != session.id:
            self.add_error("term", "Selected term does not belong to the selected session.")
        return cleaned


class WeeklyChallengeSubmissionForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = WeeklyChallengeSubmission
        fields = ("response_text",)
        widgets = {
            "response_text": forms.Textarea(attrs={"rows": 5, "placeholder": "Type your answer or short explanation here."}),
        }

