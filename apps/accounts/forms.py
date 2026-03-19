import secrets
import string
import base64
import binascii
import re
import uuid

from django import forms
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.forms import PasswordChangeForm
from django.core.files.base import ContentFile

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_GROUP_ADMIN,
    ROLE_GROUP_ADMIN_CODES,
    ROLE_GROUP_STAFF,
    ROLE_GROUP_STAFF_CODES,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    STAFF_REGISTRATION_ROLE_CODES,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
    STAFF_ROLE_ID_PREFIX,
)
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.academics.models import (
    AcademicClass,
    ClassSubject,
    FormTeacherAssignment,
    StudentSubjectEnrollment,
    StudentClassEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
)
from apps.audit.services import log_login_failed
from apps.setup_wizard.services import get_setup_state
from core.upload_scan import validate_image_upload


ROLE_GROUP_CHOICES = (
    (ROLE_GROUP_STAFF, "Staff"),
    (ROLE_GROUP_ADMIN, "Admin"),
)

PROVISIONING_ALLOWED_ROLE_CODES = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}


def _singleton_role_account_preset(role_code):
    domain = (getattr(settings, "NDGA_BASE_DOMAIN", "ndgakuje.org") or "ndgakuje.org").strip()
    presets = {
        ROLE_VP: {
            "username": f"vp@{domain}",
            "staff_id": "NDGAK/VP",
            "password": "admin/vp",
        },
        ROLE_PRINCIPAL: {
            "username": f"principal@{domain}",
            "staff_id": "NDGAK/PRINCIPAL",
            "password": "admin",
        },
        ROLE_BURSAR: {
            "username": f"bursar@{domain}",
            "staff_id": "NDGAK/BURSAR",
            "password": "bursar1804",
        },
        ROLE_DEAN: {
            "username": "ndgak/staff/dean",
            "staff_id": "NDGAK/STAFF/DEAN",
            "password": "ndgak/dean",
        },
    }
    return presets.get(role_code)


def _actor_can_manage_users(actor):
    if actor is None:
        return False
    return any(actor.has_role(role_code) for role_code in PROVISIONING_ALLOWED_ROLE_CODES)


def _extract_numeric_suffix(value):
    try:
        return int(str(value).split("/")[-1])
    except (TypeError, ValueError):
        return None


def generate_temporary_password(serial_hint=None):
    serial = _extract_numeric_suffix(serial_hint) if serial_hint is not None else None
    if serial is not None:
        return f"NDGAK/{serial:03d}"
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


def set_user_password_from_login_id(user, login_id):
    password = generate_temporary_password(login_id)
    user.set_password(password)
    user.password_changed_count = 0
    user.must_change_password = False
    user.clear_login_code()
    return password


def _generate_username_from_name(*, first_name, last_name):
    domain = (
        getattr(settings, "NDGA_BASE_DOMAIN", "ndgakuje.org") or "ndgakuje.org"
    ).strip()
    safe_first = "".join(ch for ch in first_name.lower() if ch.isalnum()) or "staff"
    safe_last = "".join(ch for ch in last_name.lower() if ch.isalnum())
    base_local = safe_first
    candidate = f"{base_local}@{domain}"
    counter = 2
    while User.objects.filter(username__iexact=candidate).exists():
        if safe_last:
            candidate = f"{safe_first}.{safe_last}{counter}@{domain}"
        else:
            candidate = f"{base_local}{counter}@{domain}"
        counter += 1
    return candidate


def _generate_staff_id_for_role(role_code):
    prefix = "NDGAK/STAFF/"
    max_serial = 0
    existing_ids = StaffProfile.objects.filter(
        staff_id__startswith=prefix
    ).values_list("staff_id", flat=True)
    for row in existing_ids:
        try:
            serial = int(str(row).split("/")[-1])
        except (ValueError, TypeError):
            continue
        max_serial = max(max_serial, serial)
    next_serial = max_serial + 1
    return f"{prefix}{next_serial:03d}"


def _derive_student_year_code():
    setup_state = get_setup_state()
    if setup_state.current_session_id:
        session_name = setup_state.current_session.name
        first_part = session_name.split("/")[0].strip()
        if first_part.isdigit():
            return int(first_part) % 100
    return setup_state.updated_at.year % 100


_STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Z0-9]+/(\d{2})/(\d+)$")


def _extract_student_serial(value):
    raw = (value or "").strip().upper()
    match = _STUDENT_NUMBER_PATTERN.match(raw)
    if not match:
        return None
    try:
        return int(match.group(2))
    except (TypeError, ValueError):
        return None


def _generate_student_number():
    year_code = _derive_student_year_code()
    max_serial = 0
    existing_numbers = StudentProfile.objects.values_list("student_number", flat=True)
    for row in existing_numbers:
        serial = _extract_student_serial(row)
        if serial is None:
            continue
        max_serial = max(max_serial, serial)
    next_serial = max_serial + 1
    return f"NDGAK/{year_code:02d}/{next_serial:03d}"


def _generate_student_username(student_number):
    domain = (
        getattr(settings, "NDGA_BASE_DOMAIN", "ndgakuje.org") or "ndgakuje.org"
    ).strip()
    slug = student_number.lower().replace("/", "-")
    candidate = f"{slug}@{domain}"
    counter = 2
    while User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{slug}{counter}@{domain}"
        counter += 1
    return candidate


def _instructional_class_id_for_selection(selected_class):
    if not selected_class:
        return None
    if isinstance(selected_class, AcademicClass):
        academic_class = selected_class
    else:
        try:
            academic_class = AcademicClass.objects.select_related("base_class").get(
                pk=selected_class
            )
        except (AcademicClass.DoesNotExist, ValueError, TypeError):
            return None
    instructional_class = getattr(academic_class, "instructional_class", None)
    return instructional_class.id if instructional_class else None


def _decode_data_url_image(data_url):
    if not data_url:
        return None
    if ";base64," not in data_url:
        raise forms.ValidationError("Invalid webcam capture payload.")
    header, encoded = data_url.split(";base64,", 1)
    if not header.startswith("data:image/"):
        raise forms.ValidationError("Webcam capture must be an image.")
    extension = header.replace("data:image/", "").strip().lower()
    if extension not in {"png", "jpg", "jpeg", "webp"}:
        extension = "jpg"
    try:
        decoded = base64.b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        raise forms.ValidationError("Could not decode webcam capture.") from exc
    max_image_size_mb = settings.UPLOAD_SECURITY.get("MAX_IMAGE_MB", 8)
    if len(decoded) > max_image_size_mb * 1024 * 1024:
        raise forms.ValidationError(f"Captured image exceeds {max_image_size_mb}MB limit.")
    filename = f"capture-{uuid.uuid4().hex[:12]}.{extension}"
    return ContentFile(decoded, name=filename)


def resolve_user_by_login_identifier(raw_identifier):
    identifier = (raw_identifier or "").strip()
    if not identifier:
        return None
    user = User.objects.select_related("primary_role").filter(
        username__iexact=identifier
    ).first()
    if user:
        return user
    staff_match = StaffProfile.objects.select_related("user", "user__primary_role").filter(
        staff_id__iexact=identifier
    ).first()
    if staff_match:
        return staff_match.user
    student_match = StudentProfile.objects.select_related("user", "user__primary_role").filter(
        student_number__iexact=identifier
    ).first()
    if student_match:
        return student_match.user
    return None


class NDGALoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    login_code = forms.CharField(
        required=False,
        max_length=32,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code"}),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        self.used_login_code = False
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Login ID"
        self.fields["username"].widget.attrs.update(
            {
                "class": (
                    "w-full rounded-2xl border border-white/35 bg-white/90 px-4 py-3 "
                    "text-sm text-slate-900 shadow-sm outline-none transition "
                    "placeholder:text-slate-400 focus:border-ndga-navy/60 "
                    "focus:ring-4 focus:ring-ndga-navy/10"
                ),
                "placeholder": "Enter login ID",
                "autocomplete": "username",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "class": (
                    "w-full rounded-2xl border border-white/35 bg-white/90 px-4 py-3 pr-20 "
                    "text-sm text-slate-900 shadow-sm outline-none transition "
                    "placeholder:text-slate-400 focus:border-ndga-navy/60 "
                    "focus:ring-4 focus:ring-ndga-navy/10"
                ),
                "placeholder": "Enter password",
            }
        )
        self.fields["login_code"].widget = forms.HiddenInput()

    def _resolve_login_user(self, raw_identifier):
        return resolve_user_by_login_identifier(raw_identifier)

    def clean(self):
        cleaned_data = super().clean()
        identifier = cleaned_data.get("username")
        password = cleaned_data.get("password")
        login_code = cleaned_data.get("login_code")
        user_from_identifier = self._resolve_login_user(identifier)

        if not password and not login_code:
            raise forms.ValidationError("Enter your password.")

        if login_code:
            if not user_from_identifier:
                log_login_failed(request=self.request, username=identifier)
                raise forms.ValidationError("Invalid login ID or login code.")
            user = user_from_identifier
            if not user.verify_login_code(login_code):
                log_login_failed(request=self.request, username=identifier)
                raise forms.ValidationError("Invalid login ID or login code.")
            if not user.is_active:
                raise forms.ValidationError("This account is inactive.")
            user.backend = "django.contrib.auth.backends.ModelBackend"
            self.user_cache = user
            self.used_login_code = True
            return cleaned_data

        auth_username = user_from_identifier.username if user_from_identifier else identifier
        user = authenticate(
            self.request,
            username=auth_username,
            password=password,
        )
        if user is None:
            raise forms.ValidationError("Invalid login ID or password.")
        if not user.is_active:
            raise forms.ValidationError("This account is inactive.")
        self.user_cache = user
        return cleaned_data

    def get_user(self):
        return self.user_cache


class PrivilegedTwoFactorForm(forms.Form):
    verification_code = forms.CharField(max_length=6, min_length=6, label="Verification Code")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["verification_code"].widget.attrs.update(
            {
                "class": (
                    "w-full rounded-2xl border border-white/35 bg-white/90 px-4 py-3 "
                    "text-center text-base font-semibold tracking-[0.32em] text-slate-900 shadow-sm "
                    "outline-none transition placeholder:text-slate-400 focus:border-ndga-navy/60 "
                    "focus:ring-4 focus:ring-ndga-navy/10"
                ),
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "placeholder": "000000",
            }
        )

    def clean_verification_code(self):
        return (self.cleaned_data.get("verification_code") or "").strip()

class PasswordResetRequestForm(forms.Form):
    login_id = forms.CharField(max_length=150, label="Login ID")

    def __init__(self, *args, **kwargs):
        self.user_cache = None
        super().__init__(*args, **kwargs)
        self.fields["login_id"].widget.attrs.update(
            {
                "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                "placeholder": "Staff ID, Student ID, or portal username",
                "autocomplete": "username",
            }
        )

    def clean(self):
        cleaned_data = super().clean()
        login_id = cleaned_data.get("login_id", "")
        user = resolve_user_by_login_identifier(login_id)
        if not user:
            raise forms.ValidationError("Account not found for the provided login ID.")
        if user.has_role(ROLE_STUDENT):
            raise forms.ValidationError(
                "Student password reset is managed by IT Manager only."
            )
        if not user.email:
            raise forms.ValidationError(
                "No recovery email is set for this account. Contact IT Manager."
            )
        if not user.can_self_change_password():
            raise forms.ValidationError(
                "Self-service reset limit reached. Contact IT Manager."
            )
        self.user_cache = user
        return cleaned_data

    def get_user(self):
        return self.user_cache


class PasswordResetCodeForm(forms.Form):
    reset_code = forms.CharField(max_length=32, label="Reset Code")
    new_password1 = forms.CharField(
        widget=forms.PasswordInput,
        label="New Password",
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirm New Password",
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field_name in ("reset_code", "new_password1", "new_password2"):
            self.fields[field_name].widget.attrs.update(
                {
                    "class": "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm",
                }
            )

    def clean(self):
        cleaned_data = super().clean()
        reset_code = cleaned_data.get("reset_code")
        password_1 = cleaned_data.get("new_password1")
        password_2 = cleaned_data.get("new_password2")

        if not self.user.verify_login_code(reset_code):
            raise forms.ValidationError("Invalid or expired reset code.")
        if password_1 != password_2:
            raise forms.ValidationError("Passwords do not match.")
        if len(password_1 or "") < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.password_changed_count += 1
        self.user.must_change_password = False
        self.user.clear_login_code()
        self.user.save(
            update_fields=[
                "password",
                "password_changed_count",
                "must_change_password",
                "login_code_hash",
                "login_code_expires_at",
            ]
        )
        return self.user


class PolicyPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("old_password", "new_password1", "new_password2"):
            self.fields[field_name].widget.attrs["class"] = (
                "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            )

    def clean(self):
        cleaned_data = super().clean()
        if not self.user.can_self_change_password():
            raise forms.ValidationError(
                "Password change limit reached. Contact IT Manager for reset code."
            )
        return cleaned_data


class ITCredentialResetForm(forms.Form):
    RESET_MODE_PASSWORD = "PASSWORD"
    RESET_MODE_LOGIN_CODE = "LOGIN_CODE"
    RESET_MODE_CHOICES = (
        (RESET_MODE_PASSWORD, "Set New Password"),
        (RESET_MODE_LOGIN_CODE, "Issue One-Time Login Code"),
    )

    target_user = forms.ModelChoiceField(queryset=User.objects.none())
    reset_mode = forms.ChoiceField(choices=RESET_MODE_CHOICES)
    temporary_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
    )

    def __init__(self, actor, *args, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        self.fields["target_user"].queryset = (
            User.objects.select_related("primary_role")
            .exclude(id=actor.id)
            .exclude(username=settings.ANONYMOUS_USER_NAME)
            .order_by("username")
        )
        self.fields["target_user"].widget.attrs["class"] = (
            "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        )
        self.fields["reset_mode"].widget.attrs["class"] = (
            "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        )
        self.fields["temporary_password"].widget.attrs["class"] = (
            "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        )

    def clean(self):
        cleaned_data = super().clean()
        reset_mode = cleaned_data.get("reset_mode")
        temporary_password = cleaned_data.get("temporary_password")
        if reset_mode == self.RESET_MODE_PASSWORD and not temporary_password:
            raise forms.ValidationError("Temporary password is required for this mode.")
        if not self.actor.has_role(ROLE_IT_MANAGER):
            raise forms.ValidationError("Only IT Manager can perform this action.")
        return cleaned_data


class ITStaffRegistrationForm(forms.Form):
    role_group = forms.ChoiceField(choices=ROLE_GROUP_CHOICES, initial=ROLE_GROUP_STAFF)
    primary_role = forms.ModelChoiceField(queryset=Role.objects.none())
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False, label="Personal Email (for recovery)")
    staff_id = forms.CharField(
        max_length=32,
        required=False,
        label="Staff ID (Optional)",
        help_text="Leave blank to auto-generate.",
    )
    phone_number = forms.CharField(max_length=30, required=False)
    profile_photo = forms.ImageField(required=False)
    webcam_image_data = forms.CharField(required=False, widget=forms.HiddenInput())
    form_class_assignment = forms.ModelChoiceField(
        queryset=AcademicClass.objects.none(),
        required=False,
        label="Form Class Assignment",
    )
    also_teaches = forms.BooleanField(
        required=False,
        label="This role also teaches subjects",
    )
    teaching_loads = forms.ModelMultipleChoiceField(
        queryset=ClassSubject.objects.none(),
        required=False,
        label="Subject-Class Teaching Load",
    )

    def __init__(self, actor, *args, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        role_qs = Role.objects.filter(
            code__in=STAFF_REGISTRATION_ROLE_CODES
        ).order_by("code")
        self.fields["primary_role"].queryset = role_qs
        class_qs = AcademicClass.objects.filter(is_active=True).order_by("code")
        self.fields["form_class_assignment"].queryset = class_qs
        self.fields["teaching_loads"].queryset = (
            ClassSubject.objects.select_related("academic_class", "subject")
            .filter(
                is_active=True,
                academic_class__is_active=True,
                subject__is_active=True,
            )
            .order_by("academic_class__code", "subject__name")
        )
        self.fields["teaching_loads"].label_from_instance = (
            lambda item: f"{item.academic_class.code} - {item.subject.name}"
        )
        self.fields["teaching_loads"].help_text = (
            "Select one or more class-subject loads for this staff."
        )
        self.fields["role_group"].help_text = "Choose Staff or Admin first."
        self.fields["primary_role"].help_text = (
            "Role options are filtered by Staff/Admin category."
        )

        setup_state = get_setup_state()
        self.current_session = setup_state.current_session
        self.current_term = setup_state.current_term

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 text-ndga-navy"
            else:
                field.widget.attrs["class"] = "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        self.fields["teaching_loads"].widget.attrs["class"] = (
            "w-full min-h-44 rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

    def _filter_roles_by_group(self, group):
        qs = self.fields["primary_role"].queryset
        if group == ROLE_GROUP_ADMIN:
            return qs.filter(code__in=ROLE_GROUP_ADMIN_CODES)
        return qs.filter(code__in=ROLE_GROUP_STAFF_CODES)

    def clean(self):
        cleaned_data = super().clean()
        if not _actor_can_manage_users(self.actor):
            raise forms.ValidationError("Only IT Manager, VP, or Principal can register users.")
        if not self.current_session or not self.current_term:
            raise forms.ValidationError("Set current session and term before creating staff.")

        role_group = cleaned_data.get("role_group")
        primary_role = cleaned_data.get("primary_role")
        if not primary_role:
            return cleaned_data
        if not self._filter_roles_by_group(role_group).filter(id=primary_role.id).exists():
            raise forms.ValidationError("Selected role does not match chosen Staff/Admin category.")
        if primary_role and primary_role.code == ROLE_STUDENT:
            raise forms.ValidationError("Staff registration cannot use STUDENT role.")

        if primary_role and primary_role.code == ROLE_IT_MANAGER:
            raise forms.ValidationError("Use the dedicated IT bootstrap account. Do not create extra IT managers.")

        manual_staff_id = (cleaned_data.get("staff_id") or "").strip().upper()
        preset = _singleton_role_account_preset(primary_role.code)
        resolved_staff_id = preset["staff_id"] if preset else manual_staff_id
        if resolved_staff_id:
            cleaned_data["staff_id"] = resolved_staff_id
            duplicate_staff = StaffProfile.objects.filter(staff_id__iexact=resolved_staff_id).exists()
            if duplicate_staff:
                if preset:
                    self.add_error("primary_role", "A staff account already exists for this role.")
                else:
                    self.add_error("staff_id", "Staff ID already exists.")
        if preset and User.objects.filter(username__iexact=preset["username"]).exists():
            self.add_error("primary_role", "A staff account already exists for this role.")

        form_class = cleaned_data.get("form_class_assignment")
        if primary_role.code == ROLE_FORM_TEACHER and not form_class:
            raise forms.ValidationError("Form teacher role requires class assignment.")

        teaching_loads = cleaned_data.get("teaching_loads")
        also_teaches = cleaned_data.get("also_teaches", False)
        if primary_role.code == ROLE_SUBJECT_TEACHER and not teaching_loads:
            raise forms.ValidationError("Subject teacher must have at least one subject-class load.")
        if primary_role.code in {ROLE_DEAN, ROLE_FORM_TEACHER}:
            if also_teaches and not teaching_loads:
                raise forms.ValidationError("Select teaching loads when 'also teaches' is enabled.")
        if primary_role.code in {ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL} and teaching_loads:
            raise forms.ValidationError("Admin roles cannot be assigned teaching loads.")

        webcam_data = cleaned_data.get("webcam_image_data")
        if webcam_data:
            cleaned_data["decoded_webcam_image"] = _decode_data_url_image(webcam_data)

        return cleaned_data

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        return validate_image_upload(photo)

    def save(self):
        first_name = self.cleaned_data["first_name"].strip()
        last_name = self.cleaned_data["last_name"].strip()
        primary_role = self.cleaned_data["primary_role"]
        preset = _singleton_role_account_preset(primary_role.code)
        generated_username = (
            preset["username"]
            if preset
            else _generate_username_from_name(
                first_name=first_name,
                last_name=last_name,
            )
        )
        manual_staff_id = (self.cleaned_data.get("staff_id") or "").strip().upper()
        final_staff_id = (
            preset["staff_id"]
            if preset
            else manual_staff_id or _generate_staff_id_for_role(primary_role.code)
        )
        password = preset["password"] if preset else generate_temporary_password(final_staff_id)
        user = User.objects.create_user(
            username=generated_username,
            password=password,
            email=self.cleaned_data.get("email", ""),
            first_name=first_name,
            last_name=last_name,
            primary_role=primary_role,
            must_change_password=False,
            password_changed_count=0,
        )
        auto_secondary_codes = []
        primary_code = primary_role.code
        if primary_code in {ROLE_DEAN, ROLE_FORM_TEACHER}:
            auto_secondary_codes.append(ROLE_SUBJECT_TEACHER)
        if auto_secondary_codes:
            user.secondary_roles.set(Role.objects.filter(code__in=auto_secondary_codes))
        selected_photo = self.cleaned_data.get("profile_photo")
        webcam_photo = self.cleaned_data.get("decoded_webcam_image")
        StaffProfile.objects.create(
            user=user,
            staff_id=final_staff_id,
            phone_number=self.cleaned_data.get("phone_number", "").strip(),
            profile_photo=selected_photo or webcam_photo,
        )

        form_class = self.cleaned_data.get("form_class_assignment")
        if form_class and user.has_role(ROLE_FORM_TEACHER):
            FormTeacherAssignment.objects.update_or_create(
                teacher=user,
                academic_class=form_class,
                session=self.current_session,
                defaults={"is_active": True},
            )

        teaching_loads = self.cleaned_data.get("teaching_loads")
        should_apply_teaching = (
            user.has_role(ROLE_SUBJECT_TEACHER)
            or (primary_code in {ROLE_DEAN, ROLE_FORM_TEACHER} and self.cleaned_data.get("also_teaches"))
        )
        if should_apply_teaching and teaching_loads:
            for load in teaching_loads:
                TeacherSubjectAssignment.objects.update_or_create(
                    teacher=user,
                    subject=load.subject,
                    academic_class=load.academic_class,
                    session=self.current_session,
                    term=self.current_term,
                    defaults={"is_active": True},
                )
        return user, password, final_staff_id


class ITStudentRegistrationForm(forms.Form):
    student_number = forms.CharField(
        max_length=32,
        required=False,
        label="Admission No / Student ID (Optional)",
        help_text="Leave blank to auto-generate from current session year and latest sequence.",
    )
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    middle_name = forms.CharField(max_length=150, required=False)
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    admission_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    gender = forms.ChoiceField(
        choices=[("", "Select"), *StudentProfile.Gender.choices],
        required=False,
    )
    guardian_name = forms.CharField(max_length=150, required=False)
    guardian_phone = forms.CharField(max_length=30, required=False)
    guardian_email = forms.EmailField(required=True, label="Parent/Guardian Email")
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    state_of_origin = forms.CharField(max_length=80, required=False)
    nationality = forms.CharField(max_length=80, required=False, initial="Nigerian")
    profile_photo = forms.ImageField(required=False)
    webcam_image_data = forms.CharField(required=False, widget=forms.HiddenInput())
    current_class = forms.ModelChoiceField(
        queryset=AcademicClass.objects.none(),
        required=False,
    )
    lifecycle_state = forms.ChoiceField(
        choices=StudentProfile.LifecycleState.choices,
        required=False,
    )
    lifecycle_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    medical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    disciplinary_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    subject_category = forms.ChoiceField(
        choices=[("", "All Categories"), *SubjectCategory.choices],
        required=False,
    )
    offered_subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Offered Subjects",
    )

    def __init__(self, actor, *args, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)
        self.fields["current_class"].queryset = AcademicClass.objects.filter(is_active=True).order_by("code")
        self.fields["lifecycle_state"].initial = StudentProfile.LifecycleState.ACTIVE
        selected_class = None
        if self.is_bound:
            selected_class = self.data.get("current_class")
        else:
            selected_class = self.initial.get("current_class")
        selected_category = ""
        if self.is_bound:
            selected_category = (self.data.get("subject_category") or "").strip()
        else:
            selected_category = (self.initial.get("subject_category") or "").strip()
        subject_qs = Subject.objects.filter(is_active=True)
        instructional_class_id = _instructional_class_id_for_selection(selected_class)
        if instructional_class_id:
            class_subjects = ClassSubject.objects.filter(
                academic_class_id=instructional_class_id,
                is_active=True,
                subject__is_active=True,
            ).select_related("subject")
            subject_ids = list(class_subjects.values_list("subject_id", flat=True))
            subject_qs = Subject.objects.filter(id__in=subject_ids, is_active=True)
        if selected_category:
            subject_qs = subject_qs.filter(category=selected_category)
        subject_qs = subject_qs.order_by("name")
        self.fields["offered_subjects"].queryset = subject_qs
        self.fields["offered_subjects"].help_text = (
            "Select only subjects this student offers in the selected class."
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        self.fields["offered_subjects"].widget.attrs["class"] = (
            "w-full min-h-40 rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

    def clean(self):
        cleaned_data = super().clean()
        if not _actor_can_manage_users(self.actor):
            raise forms.ValidationError("Only IT Manager, VP, or Principal can register users.")
        setup_state = get_setup_state()
        if not setup_state.current_session_id:
            raise forms.ValidationError("Set current academic session before creating students.")
        manual_student_number = (cleaned_data.get("student_number") or "").strip().upper()
        if manual_student_number:
            cleaned_data["student_number"] = manual_student_number
            duplicate_student = StudentProfile.objects.filter(student_number__iexact=manual_student_number).exists()
            if duplicate_student:
                self.add_error("student_number", "Admission number already exists.")
        webcam_data = cleaned_data.get("webcam_image_data")
        if not cleaned_data.get("profile_photo") and not webcam_data:
            raise forms.ValidationError(
                "Student profile image is required. Upload a photo or capture with webcam."
            )
        current_class = cleaned_data.get("current_class")
        offered_subjects = cleaned_data.get("offered_subjects")
        instructional_class = current_class.instructional_class if current_class else None
        if not current_class:
            raise forms.ValidationError("Current class is required for student registration.")
        if current_class and not offered_subjects:
            raise forms.ValidationError(
                "Select at least one offered subject for the selected class."
            )
        if instructional_class and offered_subjects:
            allowed_ids = set(
                ClassSubject.objects.filter(
                    academic_class=instructional_class,
                    is_active=True,
                    subject__is_active=True,
                ).values_list("subject_id", flat=True)
            )
            invalid_subjects = [
                subject.name for subject in offered_subjects if subject.id not in allowed_ids
            ]
            if invalid_subjects:
                raise forms.ValidationError(
                    "Invalid subject selection for class: " + ", ".join(invalid_subjects)
                )
        if webcam_data:
            cleaned_data["decoded_webcam_image"] = _decode_data_url_image(webcam_data)
        return cleaned_data

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        return validate_image_upload(photo)

    def save(self):
        role_student = Role.objects.get(code=ROLE_STUDENT)
        manual_student_number = (self.cleaned_data.get("student_number") or "").strip().upper()
        final_student_number = manual_student_number or _generate_student_number()
        generated_username = _generate_student_username(final_student_number)
        password = generate_temporary_password(final_student_number)
        user = User.objects.create_user(
            username=generated_username,
            password=password,
            email=self.cleaned_data.get("guardian_email", "").strip(),
            first_name=self.cleaned_data["first_name"].strip(),
            last_name=self.cleaned_data["last_name"].strip(),
            primary_role=role_student,
            must_change_password=False,
            password_changed_count=0,
        )
        selected_photo = self.cleaned_data.get("profile_photo")
        webcam_photo = self.cleaned_data.get("decoded_webcam_image")
        StudentProfile.objects.create(
            user=user,
            student_number=final_student_number,
            middle_name=self.cleaned_data.get("middle_name", "").strip(),
            admission_date=self.cleaned_data.get("admission_date"),
            date_of_birth=self.cleaned_data.get("date_of_birth"),
            gender=self.cleaned_data.get("gender", ""),
            guardian_name=self.cleaned_data.get("guardian_name", "").strip(),
            guardian_phone=self.cleaned_data.get("guardian_phone", "").strip(),
            guardian_email=self.cleaned_data.get("guardian_email", "").strip(),
            address=self.cleaned_data.get("address", "").strip(),
            state_of_origin=self.cleaned_data.get("state_of_origin", "").strip(),
            nationality=self.cleaned_data.get("nationality", "").strip() or "Nigerian",
            lifecycle_state=(self.cleaned_data.get("lifecycle_state") or StudentProfile.LifecycleState.ACTIVE),
            lifecycle_note=self.cleaned_data.get("lifecycle_note", "").strip(),
            medical_notes=self.cleaned_data.get("medical_notes", "").strip(),
            disciplinary_notes=self.cleaned_data.get("disciplinary_notes", "").strip(),
            profile_photo=selected_photo or webcam_photo,
        )

        setup_state = get_setup_state()
        current_class = self.cleaned_data.get("current_class")
        if current_class and setup_state.current_session_id:
            StudentClassEnrollment.objects.update_or_create(
                student=user,
                session=setup_state.current_session,
                defaults={
                    "academic_class": current_class,
                    "is_active": True,
                },
            )
            offered_subjects = self.cleaned_data.get("offered_subjects") or []
            selected_ids = {subject.id for subject in offered_subjects}
            existing_rows = StudentSubjectEnrollment.objects.filter(
                student=user,
                session=setup_state.current_session,
            )
            for row in existing_rows:
                should_be_active = row.subject_id in selected_ids
                if row.is_active != should_be_active:
                    row.is_active = should_be_active
                    row.save(update_fields=["is_active", "updated_at"])
            existing_subject_ids = set(existing_rows.values_list("subject_id", flat=True))
            for subject in offered_subjects:
                if subject.id not in existing_subject_ids:
                    StudentSubjectEnrollment.objects.create(
                        student=user,
                        subject=subject,
                        session=setup_state.current_session,
                        is_active=True,
                    )
        return user, password, final_student_number


class ITStaffUpdateForm(forms.Form):
    staff_id = forms.CharField(
        max_length=32,
        label="Staff ID",
        help_text="If this ID changes, the login password resets to match the new serial pattern.",
    )
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False, label="Personal Email (for recovery)")
    primary_role = forms.ModelChoiceField(queryset=Role.objects.none())
    designation = forms.CharField(max_length=128, required=False)
    phone_number = forms.CharField(max_length=30, required=False)
    employment_status = forms.ChoiceField(choices=StaffProfile.LifecycleState.choices, required=False)
    lifecycle_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    profile_photo = forms.ImageField(required=False)
    webcam_image_data = forms.CharField(required=False, widget=forms.HiddenInput())
    form_class_assignment = forms.ModelChoiceField(
        queryset=AcademicClass.objects.none(),
        required=False,
        label="Form Class Assignment",
    )
    also_teaches = forms.BooleanField(required=False, label="This role also teaches subjects")
    teaching_loads = forms.ModelMultipleChoiceField(
        queryset=ClassSubject.objects.none(),
        required=False,
        label="Subject-Class Teaching Load",
    )
    clear_form_assignments = forms.BooleanField(
        required=False,
        label="Deactivate existing form-teacher assignments",
    )
    clear_subject_assignments = forms.BooleanField(
        required=False,
        label="Deactivate existing subject-teacher assignments",
    )

    def __init__(self, actor, user_instance, *args, **kwargs):
        self.actor = actor
        self.user_instance = user_instance
        self.profile_instance = user_instance.staff_profile
        setup_state = get_setup_state()
        self.current_session = setup_state.current_session
        self.current_term = setup_state.current_term

        form_assignment_qs = FormTeacherAssignment.objects.select_related(
            "academic_class", "session"
        ).filter(teacher=user_instance, is_active=True)
        subject_assignment_qs = TeacherSubjectAssignment.objects.filter(
            teacher=user_instance,
            is_active=True,
        )

        preferred_form_assignment = form_assignment_qs.first()
        preferred_subject_load_ids = []
        if setup_state.current_session_id:
            preferred_form_assignment = (
                form_assignment_qs.filter(session=setup_state.current_session).first()
                or preferred_form_assignment
            )
            if setup_state.current_term_id:
                preferred_subject_load_ids = list(
                    subject_assignment_qs.filter(
                        session=setup_state.current_session,
                        term=setup_state.current_term,
                    ).values_list("subject_id", "academic_class_id")
                )
        if not preferred_subject_load_ids:
            preferred_subject_load_ids = list(
                subject_assignment_qs.values_list("subject_id", "academic_class_id")
            )
        self.preferred_load_ids = set(preferred_subject_load_ids)

        initial = kwargs.setdefault("initial", {})
        initial.setdefault("staff_id", self.profile_instance.staff_id)
        initial.setdefault("first_name", user_instance.first_name)
        initial.setdefault("last_name", user_instance.last_name)
        initial.setdefault("email", user_instance.email)
        initial.setdefault("designation", self.profile_instance.designation)
        initial.setdefault("phone_number", self.profile_instance.phone_number)
        initial.setdefault("employment_status", self.profile_instance.employment_status)
        initial.setdefault("lifecycle_note", self.profile_instance.lifecycle_note)
        initial.setdefault("primary_role", user_instance.primary_role_id)
        if preferred_form_assignment:
            initial.setdefault("form_class_assignment", preferred_form_assignment.academic_class_id)
        initial.setdefault(
            "also_teaches",
            bool(
                user_instance.primary_role
                and user_instance.primary_role.code in {ROLE_SUBJECT_TEACHER, ROLE_DEAN, ROLE_FORM_TEACHER}
                and self.preferred_load_ids
            ),
        )
        super().__init__(*args, **kwargs)

        self.fields["primary_role"].queryset = Role.objects.filter(
            code__in=STAFF_REGISTRATION_ROLE_CODES
        ).order_by("code")
        class_qs = AcademicClass.objects.filter(is_active=True).order_by("code")
        self.fields["form_class_assignment"].queryset = class_qs
        self.fields["teaching_loads"].queryset = (
            ClassSubject.objects.select_related("academic_class", "subject")
            .filter(
                is_active=True,
                academic_class__is_active=True,
                subject__is_active=True,
            )
            .order_by("academic_class__code", "subject__name")
        )
        self.fields["teaching_loads"].label_from_instance = (
            lambda item: f"{item.academic_class.code} - {item.subject.name}"
        )
        if self.preferred_load_ids:
            initial_ids = []
            for row in self.fields["teaching_loads"].queryset:
                if (row.subject_id, row.academic_class_id) in self.preferred_load_ids:
                    initial_ids.append(row.id)
            self.initial.setdefault("teaching_loads", initial_ids)

        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "h-4 w-4 rounded border-slate-300 text-ndga-navy"
            else:
                field.widget.attrs["class"] = "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        self.fields["teaching_loads"].widget.attrs["class"] = (
            "w-full min-h-44 rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

    def clean_staff_id(self):
        value = (self.cleaned_data.get("staff_id") or "").strip().upper()
        if not value:
            raise forms.ValidationError("Staff ID is required.")
        duplicate = StaffProfile.objects.filter(staff_id=value).exclude(user=self.user_instance)
        if duplicate.exists():
            raise forms.ValidationError("Staff ID already exists.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        if not _actor_can_manage_users(self.actor):
            raise forms.ValidationError("Only IT Manager, VP, or Principal can update staff records.")
        if not self.current_session or not self.current_term:
            raise forms.ValidationError("Set current session and term before updating staff assignments.")

        primary_role = cleaned_data.get("primary_role")
        if primary_role and primary_role.code == ROLE_IT_MANAGER:
            raise forms.ValidationError(
                "Use the dedicated IT bootstrap account. Do not create extra IT managers."
            )
        if not primary_role:
            return cleaned_data

        preset = _singleton_role_account_preset(primary_role.code)
        if preset:
            requested_staff_id = (cleaned_data.get("staff_id") or "").strip().upper()
            if requested_staff_id and requested_staff_id != preset["staff_id"]:
                self.add_error("staff_id", "This role uses a fixed staff ID.")
            cleaned_data["staff_id"] = preset["staff_id"]

        form_class = cleaned_data.get("form_class_assignment")
        if primary_role.code == ROLE_FORM_TEACHER and not form_class:
            raise forms.ValidationError("Form teacher role requires class assignment.")

        teaching_loads = cleaned_data.get("teaching_loads")
        also_teaches = cleaned_data.get("also_teaches", False)
        if primary_role.code == ROLE_SUBJECT_TEACHER and not teaching_loads:
            raise forms.ValidationError("Subject teacher must have at least one subject-class load.")
        if primary_role.code in {ROLE_DEAN, ROLE_FORM_TEACHER}:
            if also_teaches and not teaching_loads:
                raise forms.ValidationError("Select teaching loads when 'also teaches' is enabled.")
        if primary_role.code in {ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL} and teaching_loads:
            raise forms.ValidationError("Admin roles cannot have teaching loads.")
        webcam_data = cleaned_data.get("webcam_image_data")
        if webcam_data:
            cleaned_data["decoded_webcam_image"] = _decode_data_url_image(webcam_data)
        return cleaned_data

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        return validate_image_upload(photo)

    def save(self):
        previous_staff_id = self.profile_instance.staff_id
        next_staff_id = self.cleaned_data["staff_id"]
        preset = _singleton_role_account_preset(self.cleaned_data["primary_role"].code)

        self.user_instance.first_name = self.cleaned_data["first_name"].strip()
        self.user_instance.last_name = self.cleaned_data["last_name"].strip()
        self.user_instance.email = self.cleaned_data.get("email", "")
        self.user_instance.primary_role = self.cleaned_data["primary_role"]
        self.user_instance.save(update_fields=["first_name", "last_name", "email", "primary_role"])

        auto_secondary_codes = []
        if self.user_instance.primary_role.code in {ROLE_DEAN, ROLE_FORM_TEACHER}:
            auto_secondary_codes.append(ROLE_SUBJECT_TEACHER)
        self.user_instance.secondary_roles.set(Role.objects.filter(code__in=auto_secondary_codes))

        self.profile_instance.designation = self.cleaned_data.get("designation", "").strip()
        self.profile_instance.phone_number = self.cleaned_data.get("phone_number", "").strip()
        self.profile_instance.employment_status = self.cleaned_data.get("employment_status") or StaffProfile.LifecycleState.ACTIVE
        self.profile_instance.lifecycle_note = self.cleaned_data.get("lifecycle_note", "").strip()
        self.profile_instance.staff_id = next_staff_id
        new_photo = self.cleaned_data.get("profile_photo")
        webcam_photo = self.cleaned_data.get("decoded_webcam_image")
        if new_photo or webcam_photo:
            self.profile_instance.profile_photo = new_photo or webcam_photo
        self.profile_instance.save()

        self.generated_password = ""
        if next_staff_id != previous_staff_id:
            if preset:
                self.generated_password = preset["password"]
                self.user_instance.set_password(self.generated_password)
                self.user_instance.password_changed_count = 0
                self.user_instance.must_change_password = False
                self.user_instance.clear_login_code()
            else:
                self.generated_password = set_user_password_from_login_id(self.user_instance, next_staff_id)
            self.user_instance.save(
                update_fields=[
                    "password",
                    "password_changed_count",
                    "must_change_password",
                    "login_code_hash",
                    "login_code_expires_at",
                ]
            )

        if self.cleaned_data.get("clear_form_assignments") or not self.user_instance.has_role(ROLE_FORM_TEACHER):
            FormTeacherAssignment.objects.filter(
                teacher=self.user_instance,
                is_active=True,
            ).update(is_active=False)

        if self.cleaned_data.get("clear_subject_assignments"):
            TeacherSubjectAssignment.objects.filter(
                teacher=self.user_instance,
                is_active=True,
            ).update(is_active=False)

        selected_form_class = self.cleaned_data.get("form_class_assignment")
        if selected_form_class and self.user_instance.has_role(ROLE_FORM_TEACHER):
            FormTeacherAssignment.objects.update_or_create(
                teacher=self.user_instance,
                academic_class=selected_form_class,
                session=self.current_session,
                defaults={"is_active": True},
            )

        teaching_loads = self.cleaned_data.get("teaching_loads") or []
        role_code = self.user_instance.primary_role.code
        should_apply_teaching = role_code == ROLE_SUBJECT_TEACHER or (
            role_code in {ROLE_DEAN, ROLE_FORM_TEACHER}
            and self.cleaned_data.get("also_teaches")
        )
        if not should_apply_teaching:
            TeacherSubjectAssignment.objects.filter(
                teacher=self.user_instance,
                is_active=True,
            ).update(is_active=False)
            return self.user_instance

        selected_pairs = {(load.subject_id, load.academic_class_id) for load in teaching_loads}
        existing_assignments = TeacherSubjectAssignment.objects.filter(
            teacher=self.user_instance,
            session=self.current_session,
            term=self.current_term,
        )
        for row in existing_assignments:
            if (row.subject_id, row.academic_class_id) not in selected_pairs and row.is_active:
                row.is_active = False
                row.save(update_fields=["is_active", "updated_at"])

        for load in teaching_loads:
            TeacherSubjectAssignment.objects.update_or_create(
                teacher=self.user_instance,
                subject=load.subject,
                academic_class=load.academic_class,
                session=self.current_session,
                term=self.current_term,
                defaults={"is_active": True},
            )

        return self.user_instance


class ITStudentUpdateForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    middle_name = forms.CharField(max_length=150, required=False)
    student_number = forms.CharField(
        max_length=32,
        help_text="If this admission number changes, the login password resets to match the new serial pattern.",
    )
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    admission_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    gender = forms.ChoiceField(choices=[("", "Select"), *StudentProfile.Gender.choices], required=False)
    guardian_name = forms.CharField(max_length=150, required=False)
    guardian_phone = forms.CharField(max_length=30, required=False)
    guardian_email = forms.EmailField(required=True, label="Parent/Guardian Email")
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    state_of_origin = forms.CharField(max_length=80, required=False)
    nationality = forms.CharField(max_length=80, required=False, initial="Nigerian")
    lifecycle_state = forms.ChoiceField(choices=StudentProfile.LifecycleState.choices, required=False)
    lifecycle_note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    medical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    disciplinary_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    profile_photo = forms.ImageField(required=False)
    webcam_image_data = forms.CharField(required=False, widget=forms.HiddenInput())
    current_class = forms.ModelChoiceField(queryset=AcademicClass.objects.none(), required=False)
    subject_category = forms.ChoiceField(
        choices=[("", "All Categories"), *SubjectCategory.choices],
        required=False,
    )
    offered_subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Offered Subjects",
    )

    def __init__(self, actor, user_instance, *args, **kwargs):
        self.actor = actor
        self.user_instance = user_instance
        self.profile_instance = user_instance.student_profile
        setup_state = get_setup_state()
        self.current_session = setup_state.current_session
        current_enrollment = None
        if setup_state.current_session_id:
            current_enrollment = StudentClassEnrollment.objects.filter(
                student=user_instance,
                session=setup_state.current_session,
                is_active=True,
            ).first()
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("first_name", user_instance.first_name)
        initial.setdefault("last_name", user_instance.last_name)
        initial.setdefault("student_number", self.profile_instance.student_number)
        initial.setdefault("middle_name", self.profile_instance.middle_name)
        initial.setdefault("date_of_birth", self.profile_instance.date_of_birth)
        initial.setdefault("admission_date", self.profile_instance.admission_date)
        initial.setdefault("gender", self.profile_instance.gender)
        initial.setdefault("guardian_name", self.profile_instance.guardian_name)
        initial.setdefault("guardian_phone", self.profile_instance.guardian_phone)
        initial.setdefault("guardian_email", self.profile_instance.guardian_email)
        initial.setdefault("address", self.profile_instance.address)
        initial.setdefault("state_of_origin", self.profile_instance.state_of_origin)
        initial.setdefault("nationality", self.profile_instance.nationality)
        initial.setdefault("lifecycle_state", self.profile_instance.lifecycle_state)
        initial.setdefault("lifecycle_note", self.profile_instance.lifecycle_note)
        initial.setdefault("medical_notes", self.profile_instance.medical_notes)
        initial.setdefault("disciplinary_notes", self.profile_instance.disciplinary_notes)
        if current_enrollment:
            initial.setdefault("current_class", current_enrollment.academic_class_id)
            subject_ids = list(
                StudentSubjectEnrollment.objects.filter(
                    student=user_instance,
                    session=setup_state.current_session,
                    is_active=True,
                ).values_list("subject_id", flat=True)
            )
            if subject_ids:
                initial.setdefault("offered_subjects", subject_ids)
        super().__init__(*args, **kwargs)

        self.fields["current_class"].queryset = AcademicClass.objects.filter(is_active=True).order_by("code")
        selected_class = None
        if self.is_bound:
            selected_class = self.data.get("current_class")
        else:
            selected_class = self.initial.get("current_class")
        selected_category = ""
        if self.is_bound:
            selected_category = (self.data.get("subject_category") or "").strip()
        else:
            selected_category = (self.initial.get("subject_category") or "").strip()
        subject_qs = Subject.objects.filter(is_active=True)
        instructional_class_id = _instructional_class_id_for_selection(selected_class)
        if instructional_class_id:
            subject_ids = list(
                ClassSubject.objects.filter(
                    academic_class_id=instructional_class_id,
                    is_active=True,
                    subject__is_active=True,
                ).values_list("subject_id", flat=True)
            )
            subject_qs = Subject.objects.filter(id__in=subject_ids, is_active=True)
        if selected_category:
            subject_qs = subject_qs.filter(category=selected_category)
        subject_qs = subject_qs.order_by("name")
        self.fields["offered_subjects"].queryset = subject_qs
        self.fields["offered_subjects"].help_text = (
            "Select only subjects this student offers in the selected class."
        )
        for field in self.fields.values():
            field.widget.attrs["class"] = "w-full rounded-xl border border-slate-300 px-3 py-2 text-sm"
        self.fields["offered_subjects"].widget.attrs["class"] = (
            "w-full min-h-40 rounded-xl border border-slate-300 px-3 py-2 text-sm"
        )

    def clean_student_number(self):
        value = self.cleaned_data["student_number"].strip().upper()
        duplicate = StudentProfile.objects.filter(student_number=value).exclude(user=self.user_instance)
        if duplicate.exists():
            raise forms.ValidationError("Student number already exists.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        if not _actor_can_manage_users(self.actor):
            raise forms.ValidationError("Only IT Manager, VP, or Principal can update student records.")
        setup_state = get_setup_state()
        if not setup_state.current_session_id:
            raise forms.ValidationError("Set current academic session before updating students.")
        current_class = cleaned_data.get("current_class")
        offered_subjects = cleaned_data.get("offered_subjects")
        instructional_class = current_class.instructional_class if current_class else None
        if not current_class:
            raise forms.ValidationError("Current class is required for student record update.")
        if current_class and not offered_subjects:
            raise forms.ValidationError(
                "Select at least one offered subject for the selected class."
            )
        if instructional_class and offered_subjects:
            allowed_ids = set(
                ClassSubject.objects.filter(
                    academic_class=instructional_class,
                    is_active=True,
                    subject__is_active=True,
                ).values_list("subject_id", flat=True)
            )
            invalid_subjects = [
                subject.name for subject in offered_subjects if subject.id not in allowed_ids
            ]
            if invalid_subjects:
                raise forms.ValidationError(
                    "Invalid subject selection for class: " + ", ".join(invalid_subjects)
                )
        webcam_data = cleaned_data.get("webcam_image_data")
        if webcam_data:
            cleaned_data["decoded_webcam_image"] = _decode_data_url_image(webcam_data)
        return cleaned_data

    def clean_profile_photo(self):
        photo = self.cleaned_data.get("profile_photo")
        if not photo:
            return photo
        return validate_image_upload(photo)

    def save(self):
        setup_state = get_setup_state()
        previous_student_number = self.profile_instance.student_number
        self.user_instance.first_name = self.cleaned_data["first_name"].strip()
        self.user_instance.last_name = self.cleaned_data["last_name"].strip()
        self.user_instance.email = self.cleaned_data.get("guardian_email", "").strip()
        self.user_instance.save(update_fields=["first_name", "last_name", "email"])

        self.profile_instance.student_number = self.cleaned_data["student_number"]
        self.profile_instance.middle_name = self.cleaned_data.get("middle_name", "").strip()
        self.profile_instance.date_of_birth = self.cleaned_data.get("date_of_birth")
        self.profile_instance.admission_date = self.cleaned_data.get("admission_date")
        self.profile_instance.gender = self.cleaned_data.get("gender", "")
        self.profile_instance.guardian_name = self.cleaned_data.get("guardian_name", "").strip()
        self.profile_instance.guardian_phone = self.cleaned_data.get("guardian_phone", "").strip()
        self.profile_instance.guardian_email = self.cleaned_data.get("guardian_email", "").strip()
        self.profile_instance.address = self.cleaned_data.get("address", "").strip()
        self.profile_instance.state_of_origin = self.cleaned_data.get("state_of_origin", "").strip()
        self.profile_instance.nationality = self.cleaned_data.get("nationality", "").strip() or "Nigerian"
        self.profile_instance.lifecycle_state = self.cleaned_data.get("lifecycle_state") or StudentProfile.LifecycleState.ACTIVE
        self.profile_instance.lifecycle_note = self.cleaned_data.get("lifecycle_note", "").strip()
        self.profile_instance.medical_notes = self.cleaned_data.get("medical_notes", "").strip()
        self.profile_instance.disciplinary_notes = self.cleaned_data.get("disciplinary_notes", "").strip()
        new_photo = self.cleaned_data.get("profile_photo")
        webcam_photo = self.cleaned_data.get("decoded_webcam_image")
        if new_photo or webcam_photo:
            self.profile_instance.profile_photo = new_photo or webcam_photo
        self.profile_instance.save()

        self.generated_password = ""
        if self.profile_instance.student_number != previous_student_number:
            self.generated_password = set_user_password_from_login_id(
                self.user_instance,
                self.profile_instance.student_number,
            )
            self.user_instance.save(
                update_fields=[
                    "password",
                    "password_changed_count",
                    "must_change_password",
                    "login_code_hash",
                    "login_code_expires_at",
                ]
            )

        current_class = self.cleaned_data.get("current_class")
        if current_class and setup_state.current_session_id:
            StudentClassEnrollment.objects.update_or_create(
                student=self.user_instance,
                session=setup_state.current_session,
                defaults={
                    "academic_class": current_class,
                    "is_active": True,
                },
            )
            selected_subjects = self.cleaned_data.get("offered_subjects") or []
            selected_ids = {subject.id for subject in selected_subjects}
            existing = StudentSubjectEnrollment.objects.filter(
                student=self.user_instance,
                session=setup_state.current_session,
            )
            existing_map = {row.subject_id: row for row in existing}
            for subject_id, row in existing_map.items():
                should_be_active = subject_id in selected_ids
                if row.is_active != should_be_active:
                    row.is_active = should_be_active
                    row.save(update_fields=["is_active", "updated_at"])
            for subject in selected_subjects:
                if subject.id not in existing_map:
                    StudentSubjectEnrollment.objects.create(
                        student=self.user_instance,
                        subject=subject,
                        session=setup_state.current_session,
                        is_active=True,
                    )
        return self.user_instance
