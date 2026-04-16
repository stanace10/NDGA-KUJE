import uuid
from pathlib import Path

from django import forms
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.text import get_valid_filename

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
from apps.dashboard.models import (
    Club,
    LearningResource,
    LessonPlanDraft,
    LMSAssignment,
    LMSAssignmentSubmission,
    LMSClassroom,
    LMSDiscussionComment,
    LMSLesson,
    LMSLessonProgress,
    LMSModule,
    LMSSubmissionStatus,
    PortalDocument,
    PublicEventPost,
    PublicGalleryCategory,
    PublicGalleryImage,
    PublicNewsPost,
    PublicSiteSubmission,
    PublicSubmissionType,
    PublicWebsiteSettings,
    SchoolProfile,
    StudentClubMembership,
    WeeklyChallenge,
    WeeklyChallengeSubmission,
)
from apps.setup_wizard.services import get_setup_state
from core.upload_scan import validate_document_upload, validate_image_upload


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


class PublicSiteBrandingForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SchoolProfile
        fields = (
            "school_name",
            "address",
            "contact_email",
            "contact_phone",
            "website",
            "principal_name",
            "school_logo",
        )
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school_logo"].required = False
        self.fields["school_logo"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg,image/svg+xml"
        )


class PublicWebsiteSettingsForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicWebsiteSettings
        fields = (
            "hero_eyebrow",
            "hero_title",
            "hero_subtitle",
            "principal_welcome_title",
            "principal_welcome_message",
            "principal_welcome_support",
            "footer_statement",
            "chat_welcome_text",
            "chat_management_wait_text",
        )
        widgets = {
            "hero_subtitle": forms.Textarea(attrs={"rows": 3}),
            "principal_welcome_message": forms.Textarea(attrs={"rows": 4}),
            "principal_welcome_support": forms.Textarea(attrs={"rows": 4}),
            "footer_statement": forms.Textarea(attrs={"rows": 3}),
            "chat_welcome_text": forms.Textarea(attrs={"rows": 3}),
            "chat_management_wait_text": forms.Textarea(attrs={"rows": 2}),
        }


class PublicGalleryCategoryForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicGalleryCategory
        fields = ("title", "slug", "summary", "cover_image", "sort_order", "is_active")
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cover_image"].required = False
        self.fields["cover_image"].widget.attrs.setdefault("accept", "image/png,image/jpeg,image/jpg,image/webp")


class PublicGalleryImageForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicGalleryImage
        fields = ("category", "title", "caption", "image", "sort_order", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].widget.attrs.setdefault("accept", "image/png,image/jpeg,image/jpg,image/webp")


class PublicNewsPostForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicNewsPost
        fields = (
            "title",
            "slug",
            "category",
            "published_on",
            "summary",
            "body",
            "image",
            "sort_order",
            "is_published",
        )
        widgets = {
            "published_on": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = False
        self.fields["image"].widget.attrs.setdefault("accept", "image/png,image/jpeg,image/jpg,image/webp")


class PublicEventPostForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicEventPost
        fields = (
            "title",
            "slug",
            "meta",
            "event_date",
            "location",
            "summary",
            "body",
            "image",
            "sort_order",
            "is_published",
        )
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["image"].required = False
        self.fields["image"].widget.attrs.setdefault("accept", "image/png,image/jpeg,image/jpg,image/webp")


class PublicContactForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = PublicSiteSubmission
        fields = (
            "contact_name",
            "contact_email",
            "contact_phone",
            "category",
            "subject",
            "message",
        )
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.submission_type = PublicSubmissionType.CONTACT
        self.fields["contact_name"].label = "Full Name"
        self.fields["contact_email"].required = False
        self.fields["contact_phone"].required = False
        self.fields["category"].widget = forms.Select(
            choices=[
                ("General Enquiry", "General Enquiry"),
                ("Admissions", "Admissions"),
                ("Boarding", "Boarding"),
                ("Complaint", "Complaint"),
                ("Directions", "Directions"),
                ("Portal Support", "Portal Support"),
                ("Live Chat", "Live Chat"),
            ],
            attrs={"class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"},
        )

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.submission_type = PublicSubmissionType.CONTACT
        if commit:
            instance.save()
        return instance


class PublicAdmissionRegistrationForm(_StyledFormMixin, forms.ModelForm):
    surname = forms.CharField(max_length=80)
    first_name = forms.CharField(max_length=80)
    middle_name = forms.CharField(max_length=80, required=False)
    intended_class = forms.ChoiceField(
        choices=[
            ("JSS1", "JSS1"),
            ("JSS2", "JSS2"),
            ("JSS3", "JSS3"),
            ("SS1", "SS1"),
            ("SS2", "SS2"),
            ("SS3", "SS3"),
        ]
    )
    boarding_option = forms.ChoiceField(
        choices=[
            ("BOARDING", "Boarding"),
            ("DAY", "Day"),
        ]
    )
    nationality = forms.CharField(max_length=80, required=False)
    state_of_origin = forms.CharField(max_length=80, required=False)
    local_government_area = forms.CharField(max_length=80, required=False, label="L.G.A.")
    home_town = forms.CharField(max_length=80, required=False)
    has_disability_or_learning_difficulty = forms.BooleanField(
        required=False,
        label="I have a disability or learning difficulty",
    )
    religion = forms.CharField(max_length=100, required=False)
    parish_name = forms.CharField(max_length=140, required=False, label="Name of Parish")
    sibling_details = forms.CharField(
        required=False,
        label="Sibling(s) in NDGA",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    present_school = forms.CharField(max_length=180, required=False, label="Name of Present School")
    head_teacher_name = forms.CharField(max_length=180, required=False)
    head_teacher_signature_stamp = forms.CharField(
        max_length=180,
        required=False,
        label="Head Teacher Signature / Stamp",
    )
    head_teacher_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    previous_school_1_name = forms.CharField(max_length=180, required=False, label="Previous School 1")
    previous_school_1_year_of_entry = forms.CharField(max_length=20, required=False, label="Year of Entry")
    previous_school_1_year_of_leaving = forms.CharField(max_length=20, required=False, label="Year of Leaving")
    previous_school_1_reason_for_leaving = forms.CharField(max_length=180, required=False, label="Reason for Leaving")
    previous_school_2_name = forms.CharField(max_length=180, required=False, label="Previous School 2")
    previous_school_2_year_of_entry = forms.CharField(max_length=20, required=False, label="Year of Entry")
    previous_school_2_year_of_leaving = forms.CharField(max_length=20, required=False, label="Year of Leaving")
    previous_school_2_reason_for_leaving = forms.CharField(max_length=180, required=False, label="Reason for Leaving")
    previous_school_3_name = forms.CharField(max_length=180, required=False, label="Previous School 3")
    previous_school_3_year_of_entry = forms.CharField(max_length=20, required=False, label="Year of Entry")
    previous_school_3_year_of_leaving = forms.CharField(max_length=20, required=False, label="Year of Leaving")
    previous_school_3_reason_for_leaving = forms.CharField(max_length=180, required=False, label="Reason for Leaving")
    father_full_name = forms.CharField(max_length=180, required=False, label="Father's Title and Full Name")
    father_contact_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    father_occupation = forms.CharField(max_length=120, required=False)
    father_place_of_work = forms.CharField(max_length=160, required=False)
    father_phone = forms.CharField(max_length=40, required=False, label="Father's Mobile Number")
    father_email = forms.EmailField(required=False, label="Father's Email Address")
    mother_full_name = forms.CharField(max_length=180, required=False, label="Mother's Title and Full Name")
    mother_contact_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    mother_occupation = forms.CharField(max_length=120, required=False)
    mother_place_of_work = forms.CharField(max_length=160, required=False)
    mother_phone = forms.CharField(max_length=40, required=False, label="Mother's Mobile Number")
    mother_email = forms.EmailField(required=False, label="Mother's Email Address")
    emergency_contact_name = forms.CharField(max_length=180, required=False)
    emergency_contact_address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    emergency_contact_phone = forms.CharField(max_length=40, required=False)
    how_found_us = forms.ChoiceField(
        required=False,
        choices=[
            ("PARISH", "Parish"),
            ("FRIENDS", "Friends"),
            ("ADVERTISEMENT", "Advertisement"),
            ("REPUTATION", "Reputation"),
            ("PRESENT_SCHOOL", "Present School"),
            ("OTHER", "Other"),
        ],
    )
    how_found_us_other = forms.CharField(max_length=180, required=False, label="Other Details")
    personal_statement = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 6}),
    )
    parent_guardian_declaration_name = forms.CharField(max_length=180, label="Parent / Guardian")
    parent_guardian_signature = forms.CharField(max_length=180, label="Parent / Guardian Signature")
    parent_guardian_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    student_declaration_name = forms.CharField(max_length=180, label="Student")
    student_signature = forms.CharField(max_length=180, label="Student Signature")
    student_declaration_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    supporting_passport_photo = forms.FileField(required=False, label="Second Passport Photograph")
    medical_fitness_report = forms.FileField(required=False)

    class Meta:
        model = PublicSiteSubmission
        fields = (
            "applicant_date_of_birth",
            "intended_class",
            "guardian_name",
            "guardian_email",
            "guardian_phone",
            "residential_address",
            "boarding_option",
            "medical_notes",
            "passport_photo",
            "birth_certificate",
            "school_result",
        )
        widgets = {
            "applicant_date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "residential_address": forms.Textarea(attrs={"rows": 4}),
            "medical_notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.submission_type = PublicSubmissionType.ADMISSION
        self.fields["guardian_email"].required = False
        self.fields["medical_notes"].required = False
        self.fields["passport_photo"].required = False
        self.fields["birth_certificate"].required = False
        self.fields["school_result"].required = False
        self.fields["applicant_date_of_birth"].label = "Date of Birth"
        self.fields["guardian_name"].label = "Primary Parent / Guardian for Follow-up"
        self.fields["guardian_email"].label = "Primary Email for Payment / Follow-up"
        self.fields["guardian_phone"].label = "Primary Phone for Payment / Follow-up"
        self.fields["residential_address"].label = "Student Home Address"
        self.fields["boarding_option"].label = "Type of Place"
        self.fields["medical_notes"].label = "Medical Conditions / Notes"
        self.fields["passport_photo"].label = "Passport Photograph"
        self.fields["birth_certificate"].label = "Birth Certificate"
        self.fields["school_result"].label = "Last School Result"
        self.fields["passport_photo"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg"
        )
        self.fields["supporting_passport_photo"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg"
        )
        self.fields["passport_photo"].widget.attrs.setdefault(
            "accept", "image/png,image/jpeg,image/jpg"
        )
        self.fields["birth_certificate"].widget.attrs.setdefault(
            "accept", ".pdf,.jpg,.jpeg,.png"
        )
        self.fields["school_result"].widget.attrs.setdefault(
            "accept", ".pdf,.jpg,.jpeg,.png"
        )
        self.fields["medical_fitness_report"].widget.attrs.setdefault(
            "accept", ".pdf,.jpg,.jpeg,.png"
        )
        self.fields["nationality"].initial = "Nigerian"

    @staticmethod
    def _full_name(*parts):
        return " ".join([str(part).strip() for part in parts if str(part or "").strip()]).strip()

    @staticmethod
    def _clean_text(value):
        return (value or "").strip()

    @staticmethod
    def _store_uploaded_document(uploaded, folder_name):
        if not uploaded:
            return ""
        safe_name = get_valid_filename(Path(uploaded.name).name)
        target = (
            f"public_submissions/admission_supporting/{folder_name}/"
            f"{timezone.now():%Y/%m}/{uuid.uuid4().hex}-{safe_name}"
        )
        return default_storage.save(target, uploaded)

    def _education_history(self):
        rows = []
        for index in range(1, 4):
            school = self._clean_text(self.cleaned_data.get(f"previous_school_{index}_name"))
            entry = self._clean_text(self.cleaned_data.get(f"previous_school_{index}_year_of_entry"))
            leaving = self._clean_text(self.cleaned_data.get(f"previous_school_{index}_year_of_leaving"))
            reason = self._clean_text(self.cleaned_data.get(f"previous_school_{index}_reason_for_leaving"))
            if school or entry or leaving or reason:
                rows.append(
                    {
                        "name": school,
                        "year_of_entry": entry,
                        "year_of_leaving": leaving,
                        "reason_for_leaving": reason,
                    }
                )
        return rows

    def clean(self):
        cleaned = super().clean()
        self.instance.applicant_name = self._full_name(
            cleaned.get("surname"),
            cleaned.get("first_name"),
            cleaned.get("middle_name"),
        )
        self.instance.previous_school = self._clean_text(cleaned.get("present_school"))
        self.instance.contact_name = self._clean_text(cleaned.get("guardian_name"))
        self.instance.contact_email = self._clean_text(cleaned.get("guardian_email"))
        self.instance.contact_phone = self._clean_text(cleaned.get("guardian_phone"))
        if (cleaned.get("how_found_us") or "").strip().upper() == "OTHER" and not self._clean_text(
            cleaned.get("how_found_us_other")
        ):
            self.add_error("how_found_us_other", "Please provide details when selecting Other.")

        primary_name = self._clean_text(cleaned.get("guardian_name"))
        primary_phone = self._clean_text(cleaned.get("guardian_phone"))
        alternate_phone = self._clean_text(cleaned.get("father_phone")) or self._clean_text(
            cleaned.get("mother_phone")
        )
        if not primary_name:
            self.add_error("guardian_name", "Enter the primary parent or guardian name for follow-up.")
        if not primary_phone and not alternate_phone:
            self.add_error("guardian_phone", "Provide at least one reachable parent or guardian phone number.")
        return cleaned

    def clean_passport_photo(self):
        uploaded = self.cleaned_data.get("passport_photo")
        if uploaded:
            validate_image_upload(uploaded)
        return uploaded

    def clean_birth_certificate(self):
        uploaded = self.cleaned_data.get("birth_certificate")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded

    def clean_school_result(self):
        uploaded = self.cleaned_data.get("school_result")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded

    def clean_supporting_passport_photo(self):
        uploaded = self.cleaned_data.get("supporting_passport_photo")
        if uploaded:
            validate_image_upload(uploaded)
        return uploaded

    def clean_medical_fitness_report(self):
        uploaded = self.cleaned_data.get("medical_fitness_report")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded

    def save(self, commit=True):
        instance = super().save(commit=False)
        applicant_name = self._full_name(
            self.cleaned_data.get("surname"),
            self.cleaned_data.get("first_name"),
            self.cleaned_data.get("middle_name"),
        )
        instance.applicant_name = applicant_name
        instance.submission_type = PublicSubmissionType.ADMISSION
        instance.previous_school = self._clean_text(self.cleaned_data.get("present_school"))
        instance.contact_name = instance.guardian_name or self.cleaned_data.get("parent_guardian_declaration_name")
        instance.contact_email = (
            instance.guardian_email
            or self._clean_text(self.cleaned_data.get("father_email"))
            or self._clean_text(self.cleaned_data.get("mother_email"))
        )
        instance.contact_phone = (
            instance.guardian_phone
            or self._clean_text(self.cleaned_data.get("father_phone"))
            or self._clean_text(self.cleaned_data.get("mother_phone"))
            or self._clean_text(self.cleaned_data.get("emergency_contact_phone"))
        )
        instance.subject = f"Admission Registration - {instance.intended_class}"
        instance.category = "Admissions"
        instance.message = (
            "Online registration submitted through the public admissions form."
        )
        if commit:
            instance.save()
            metadata = dict(instance.metadata or {})
            stored_second_passport = self._store_uploaded_document(
                self.cleaned_data.get("supporting_passport_photo"),
                "passports",
            )
            stored_medical_report = self._store_uploaded_document(
                self.cleaned_data.get("medical_fitness_report"),
                "medical_reports",
            )
            metadata["admission_form"] = {
                "student_details": {
                    "surname": self._clean_text(self.cleaned_data.get("surname")),
                    "first_name": self._clean_text(self.cleaned_data.get("first_name")),
                    "middle_name": self._clean_text(self.cleaned_data.get("middle_name")),
                    "address": self._clean_text(self.cleaned_data.get("residential_address")),
                    "date_of_birth": (
                        self.cleaned_data.get("applicant_date_of_birth").isoformat()
                        if self.cleaned_data.get("applicant_date_of_birth")
                        else ""
                    ),
                    "nationality": self._clean_text(self.cleaned_data.get("nationality")),
                    "state_of_origin": self._clean_text(self.cleaned_data.get("state_of_origin")),
                    "local_government_area": self._clean_text(self.cleaned_data.get("local_government_area")),
                    "home_town": self._clean_text(self.cleaned_data.get("home_town")),
                    "has_disability_or_learning_difficulty": bool(
                        self.cleaned_data.get("has_disability_or_learning_difficulty")
                    ),
                    "medical_notes": self._clean_text(self.cleaned_data.get("medical_notes")),
                },
                "religious_background": {
                    "religion": self._clean_text(self.cleaned_data.get("religion")),
                    "parish_name": self._clean_text(self.cleaned_data.get("parish_name")),
                },
                "school_placement": {
                    "boarding_option": self._clean_text(self.cleaned_data.get("boarding_option")),
                    "intended_class": self._clean_text(self.cleaned_data.get("intended_class")),
                    "sibling_details": self._clean_text(self.cleaned_data.get("sibling_details")),
                    "present_school": self._clean_text(self.cleaned_data.get("present_school")),
                    "head_teacher_name": self._clean_text(self.cleaned_data.get("head_teacher_name")),
                    "head_teacher_signature_stamp": self._clean_text(
                        self.cleaned_data.get("head_teacher_signature_stamp")
                    ),
                    "head_teacher_date": (
                        self.cleaned_data.get("head_teacher_date").isoformat()
                        if self.cleaned_data.get("head_teacher_date")
                        else ""
                    ),
                    "education_history": self._education_history(),
                },
                "parents": {
                    "primary_guardian_name": self._clean_text(self.cleaned_data.get("guardian_name")),
                    "primary_guardian_email": self._clean_text(self.cleaned_data.get("guardian_email")),
                    "primary_guardian_phone": self._clean_text(self.cleaned_data.get("guardian_phone")),
                    "father_full_name": self._clean_text(self.cleaned_data.get("father_full_name")),
                    "father_contact_address": self._clean_text(self.cleaned_data.get("father_contact_address")),
                    "father_occupation": self._clean_text(self.cleaned_data.get("father_occupation")),
                    "father_place_of_work": self._clean_text(self.cleaned_data.get("father_place_of_work")),
                    "father_phone": self._clean_text(self.cleaned_data.get("father_phone")),
                    "father_email": self._clean_text(self.cleaned_data.get("father_email")),
                    "mother_full_name": self._clean_text(self.cleaned_data.get("mother_full_name")),
                    "mother_contact_address": self._clean_text(self.cleaned_data.get("mother_contact_address")),
                    "mother_occupation": self._clean_text(self.cleaned_data.get("mother_occupation")),
                    "mother_place_of_work": self._clean_text(self.cleaned_data.get("mother_place_of_work")),
                    "mother_phone": self._clean_text(self.cleaned_data.get("mother_phone")),
                    "mother_email": self._clean_text(self.cleaned_data.get("mother_email")),
                    "emergency_contact_name": self._clean_text(self.cleaned_data.get("emergency_contact_name")),
                    "emergency_contact_address": self._clean_text(
                        self.cleaned_data.get("emergency_contact_address")
                    ),
                    "emergency_contact_phone": self._clean_text(self.cleaned_data.get("emergency_contact_phone")),
                },
                "discovery_and_statement": {
                    "how_found_us": self._clean_text(self.cleaned_data.get("how_found_us")),
                    "how_found_us_other": self._clean_text(self.cleaned_data.get("how_found_us_other")),
                    "personal_statement": self._clean_text(self.cleaned_data.get("personal_statement")),
                },
                "declaration": {
                    "parent_guardian_name": self._clean_text(
                        self.cleaned_data.get("parent_guardian_declaration_name")
                    ),
                    "parent_guardian_signature": self._clean_text(
                        self.cleaned_data.get("parent_guardian_signature")
                    ),
                    "parent_guardian_date": (
                        self.cleaned_data.get("parent_guardian_date").isoformat()
                        if self.cleaned_data.get("parent_guardian_date")
                        else ""
                    ),
                    "student_name": self._clean_text(self.cleaned_data.get("student_declaration_name")),
                    "student_signature": self._clean_text(self.cleaned_data.get("student_signature")),
                    "student_date": (
                        self.cleaned_data.get("student_declaration_date").isoformat()
                        if self.cleaned_data.get("student_declaration_date")
                        else ""
                    ),
                },
                "documents": {
                    "passport_photo_name": getattr(self.cleaned_data.get("passport_photo"), "name", ""),
                    "supporting_passport_photo_path": stored_second_passport,
                    "birth_certificate_name": getattr(self.cleaned_data.get("birth_certificate"), "name", ""),
                    "school_result_name": getattr(self.cleaned_data.get("school_result"), "name", ""),
                    "medical_fitness_report_path": stored_medical_report,
                },
            }
            instance.metadata = metadata
            instance.save(update_fields=["applicant_name", "previous_school", "contact_name", "contact_email", "contact_phone", "metadata", "updated_at"])
        return instance


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


class LMSClassroomForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSClassroom
        fields = ("teacher_assignment", "title", "overview", "welcome_note", "is_published")
        widgets = {
            "overview": forms.Textarea(attrs={"rows": 3}),
            "welcome_note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        assignment_qs = TeacherSubjectAssignment.objects.filter(is_active=True).select_related(
            "academic_class", "subject", "session", "term"
        )
        if teacher is not None:
            assignment_qs = assignment_qs.filter(teacher=teacher)
        assignment_qs = assignment_qs.exclude(lms_classroom__isnull=False)
        self.fields["teacher_assignment"].queryset = assignment_qs.order_by(
            "academic_class__code", "subject__name"
        )
        self.fields["teacher_assignment"].label_from_instance = (
            lambda row: f"{row.academic_class.code} - {row.subject.name} ({row.session.name} {row.term.get_name_display()})"
        )


class LMSModuleForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSModule
        fields = ("classroom", "title", "summary", "sort_order", "is_published")
        widgets = {"summary": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)
        classroom_qs = LMSClassroom.objects.select_related(
            "teacher_assignment__academic_class",
            "teacher_assignment__subject",
        )
        if teacher is not None:
            classroom_qs = classroom_qs.filter(teacher_assignment__teacher=teacher)
        self.fields["classroom"].queryset = classroom_qs.order_by(
            "teacher_assignment__academic_class__code",
            "teacher_assignment__subject__name",
        )


class LMSLessonForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSLesson
        fields = (
            "module",
            "title",
            "summary",
            "content_text",
            "resource_file",
            "external_url",
            "estimated_minutes",
            "sort_order",
            "is_published",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 2}),
            "content_text": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, teacher=None, classroom=None, **kwargs):
        self.teacher = teacher
        self.classroom = classroom
        super().__init__(*args, **kwargs)
        module_qs = LMSModule.objects.select_related(
            "classroom__teacher_assignment__academic_class",
            "classroom__teacher_assignment__subject",
        )
        if teacher is not None:
            module_qs = module_qs.filter(classroom__teacher_assignment__teacher=teacher)
        if classroom is not None:
            module_qs = module_qs.filter(classroom=classroom)
        self.fields["module"].queryset = module_qs.order_by("classroom__teacher_assignment__academic_class__code", "sort_order")

    def clean_resource_file(self):
        uploaded = self.cleaned_data.get("resource_file")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded


class LMSAssignmentForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSAssignment
        fields = (
            "classroom",
            "module",
            "title",
            "instructions",
            "attachment_file",
            "due_at",
            "max_score",
            "allow_late_submissions",
            "is_published",
        )
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 4}),
            "due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, teacher=None, classroom=None, **kwargs):
        self.teacher = teacher
        self.classroom = classroom
        super().__init__(*args, **kwargs)
        classroom_qs = LMSClassroom.objects.select_related(
            "teacher_assignment__academic_class",
            "teacher_assignment__subject",
        )
        module_qs = LMSModule.objects.select_related("classroom")
        if teacher is not None:
            classroom_qs = classroom_qs.filter(teacher_assignment__teacher=teacher)
            module_qs = module_qs.filter(classroom__teacher_assignment__teacher=teacher)
        if classroom is not None:
            classroom_qs = classroom_qs.filter(pk=classroom.pk)
            module_qs = module_qs.filter(classroom=classroom)
            self.initial.setdefault("classroom", classroom.pk)
        self.fields["classroom"].queryset = classroom_qs.order_by("teacher_assignment__academic_class__code")
        self.fields["module"].queryset = module_qs.order_by("sort_order", "title")
        self.fields["module"].required = False

    def clean_attachment_file(self):
        uploaded = self.cleaned_data.get("attachment_file")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded


class LMSSubmissionForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSAssignmentSubmission
        fields = ("submission_text", "submission_file")
        widgets = {
            "submission_text": forms.Textarea(attrs={"rows": 4, "placeholder": "Write your response or short note here."}),
        }

    def clean_submission_file(self):
        uploaded = self.cleaned_data.get("submission_file")
        if uploaded:
            validate_document_upload(uploaded)
        return uploaded


class LMSAssignmentGradingForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSAssignmentSubmission
        fields = ("score", "feedback", "status")
        widgets = {
            "feedback": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, assignment=None, **kwargs):
        self.assignment = assignment
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            (LMSSubmissionStatus.GRADED, "Graded"),
            (LMSSubmissionStatus.REVISION_REQUIRED, "Revision Required"),
        ]
        self.fields["score"].required = False

    def clean_score(self):
        score = self.cleaned_data.get("score")
        if score is None:
            return score
        assignment = self.assignment or getattr(self.instance, "assignment", None)
        if assignment is not None and score > assignment.max_score:
            raise forms.ValidationError("Score cannot exceed assignment max score.")
        return score


class LMSDiscussionCommentForm(_StyledFormMixin, forms.ModelForm):
    class Meta:
        model = LMSDiscussionComment
        fields = ("classroom", "module", "assignment", "body")
        widgets = {"body": forms.Textarea(attrs={"rows": 3, "placeholder": "Add a class comment, question, or reply."})}

    def __init__(self, *args, teacher=None, student=None, classroom=None, **kwargs):
        self.teacher = teacher
        self.student = student
        self.classroom = classroom
        super().__init__(*args, **kwargs)
        classroom_qs = LMSClassroom.objects.select_related("teacher_assignment")
        if teacher is not None:
            classroom_qs = classroom_qs.filter(teacher_assignment__teacher=teacher)
        if classroom is not None:
            classroom_qs = classroom_qs.filter(pk=classroom.pk)
            self.initial.setdefault("classroom", classroom.pk)
        self.fields["classroom"].queryset = classroom_qs.order_by("title")
        module_qs = LMSModule.objects.all()
        assignment_qs = LMSAssignment.objects.all()
        if classroom is not None:
            module_qs = module_qs.filter(classroom=classroom)
            assignment_qs = assignment_qs.filter(classroom=classroom)
        self.fields["module"].queryset = module_qs.order_by("sort_order", "title")
        self.fields["assignment"].queryset = assignment_qs.order_by("title")
        self.fields["module"].required = False
        self.fields["assignment"].required = False


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

