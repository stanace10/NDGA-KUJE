import secrets
import string

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from apps.accounts.constants import HIGH_TRUST_PASSWORD_ROLES, ROLE_CHOICES, ROLE_STUDENT
from core.models import TimeStampedModel


class Role(TimeStampedModel):
    code = models.CharField(max_length=32, unique=True, choices=ROLE_CHOICES)
    name = models.CharField(max_length=64)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=True)

    class Meta:
        ordering = ("code",)

    def __str__(self):
        return self.code


class User(AbstractUser):
    display_name = models.CharField(max_length=80, blank=True)
    primary_role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_users",
    )
    secondary_roles = models.ManyToManyField(
        Role,
        blank=True,
        related_name="secondary_users",
    )
    password_changed_count = models.PositiveSmallIntegerField(default=0)
    must_change_password = models.BooleanField(default=True)
    login_code_hash = models.CharField(max_length=128, blank=True)
    login_code_expires_at = models.DateTimeField(null=True, blank=True)
    permission_scopes = models.JSONField(default=list, blank=True)

    def __str__(self):
        return self.username

    def get_all_role_codes(self):
        role_codes = set()
        if self.primary_role_id:
            role_codes.add(self.primary_role.code)
        role_codes.update(self.secondary_roles.values_list("code", flat=True))
        return role_codes

    def has_role(self, role_code):
        return role_code in self.get_all_role_codes()

    def get_permission_scopes(self):
        stored_scopes = self.permission_scopes or []
        if not isinstance(stored_scopes, list):
            return []
        return [str(scope).strip() for scope in stored_scopes if str(scope).strip()]

    def password_change_limit(self):
        if self.get_all_role_codes() & HIGH_TRUST_PASSWORD_ROLES:
            return None
        return 1

    def can_self_change_password(self):
        limit = self.password_change_limit()
        if limit is None:
            return True
        return self.password_changed_count < limit

    def set_login_code(self, raw_code=None, ttl_hours=24):
        if raw_code is None:
            alphabet = string.ascii_uppercase + string.digits
            raw_code = "".join(secrets.choice(alphabet) for _ in range(10))
        self.login_code_hash = make_password(raw_code)
        self.login_code_expires_at = timezone.now() + timezone.timedelta(hours=ttl_hours)
        return raw_code

    def verify_login_code(self, raw_code):
        if not raw_code or not self.login_code_hash:
            return False
        if self.login_code_expires_at and timezone.now() > self.login_code_expires_at:
            return False
        return check_password(raw_code, self.login_code_hash)

    def clear_login_code(self):
        self.login_code_hash = ""
        self.login_code_expires_at = None

    @property
    def is_student(self):
        return self.has_role(ROLE_STUDENT)


class StaffProfile(TimeStampedModel):
    class LifecycleState(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DEACTIVATED = "DEACTIVATED", "Deactivated"
        TRANSFERRED = "TRANSFERRED", "Transferred"
        EXITED = "EXITED", "Exited"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    staff_id = models.CharField(max_length=32, unique=True)
    designation = models.CharField(max_length=128, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    employment_status = models.CharField(
        max_length=16,
        choices=LifecycleState.choices,
        default=LifecycleState.ACTIVE,
    )
    lifecycle_note = models.TextField(blank=True)
    profile_photo = models.ImageField(
        upload_to="profiles/staff/",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("staff_id",)

    def __str__(self):
        return self.staff_id


class StudentProfile(TimeStampedModel):
    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        OTHER = "O", "Other"

    class LifecycleState(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        DEACTIVATED = "DEACTIVATED", "Deactivated"
        TRANSFERRED = "TRANSFERRED", "Transferred"
        GRADUATED = "GRADUATED", "Graduated"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    student_number = models.CharField(max_length=32, unique=True)
    middle_name = models.CharField(max_length=150, blank=True)
    admission_date = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    guardian_name = models.CharField(max_length=150, blank=True)
    guardian_phone = models.CharField(max_length=30, blank=True)
    guardian_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    state_of_origin = models.CharField(max_length=80, blank=True)
    nationality = models.CharField(max_length=80, default="Nigerian", blank=True)
    lifecycle_state = models.CharField(
        max_length=16,
        choices=LifecycleState.choices,
        default=LifecycleState.ACTIVE,
    )
    lifecycle_note = models.TextField(blank=True)
    medical_notes = models.TextField(blank=True)
    disciplinary_notes = models.TextField(blank=True)
    is_graduated = models.BooleanField(default=False)
    graduation_session = models.ForeignKey(
        "academics.AcademicSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graduated_student_profiles",
    )
    graduated_at = models.DateTimeField(null=True, blank=True)
    profile_photo = models.ImageField(
        upload_to="profiles/students/",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ("student_number",)

    def __str__(self):
        return self.student_number
