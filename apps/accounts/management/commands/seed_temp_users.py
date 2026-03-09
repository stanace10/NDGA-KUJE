from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    FormTeacherAssignment,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
    Term,
    TermName,
)
from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.setup_wizard.models import RuntimeFeatureFlags, SetupStateCode, SystemSetupState


@dataclass(frozen=True)
class TempUserSpec:
    key: str
    username: str
    first_name: str
    last_name: str
    primary_role: str
    secondary_roles: tuple[str, ...] = ()


TEMP_USERS = (
    TempUserSpec(
        key="student",
        username="tmp.student@ndgakuje.org",
        first_name="Temp",
        last_name="Student",
        primary_role=ROLE_STUDENT,
    ),
    TempUserSpec(
        key="subject_teacher",
        username="tmp.subjectteacher@ndgakuje.org",
        first_name="Temp",
        last_name="SubjectTeacher",
        primary_role=ROLE_SUBJECT_TEACHER,
    ),
    TempUserSpec(
        key="dean",
        username="tmp.dean@ndgakuje.org",
        first_name="Temp",
        last_name="Dean",
        primary_role=ROLE_DEAN,
        secondary_roles=(ROLE_SUBJECT_TEACHER,),
    ),
    TempUserSpec(
        key="form_teacher",
        username="tmp.formteacher@ndgakuje.org",
        first_name="Temp",
        last_name="FormTeacher",
        primary_role=ROLE_FORM_TEACHER,
        secondary_roles=(ROLE_SUBJECT_TEACHER,),
    ),
    TempUserSpec(
        key="vp",
        username="tmp.vp@ndgakuje.org",
        first_name="Temp",
        last_name="VP",
        primary_role=ROLE_VP,
    ),
    TempUserSpec(
        key="bursar",
        username="tmp.bursar@ndgakuje.org",
        first_name="Temp",
        last_name="Bursar",
        primary_role=ROLE_BURSAR,
    ),
    TempUserSpec(
        key="principal",
        username="tmp.principal@ndgakuje.org",
        first_name="Temp",
        last_name="Principal",
        primary_role=ROLE_PRINCIPAL,
    ),
)


SUBJECT_ROWS = (
    ("MTH101", "Mathematics", SubjectCategory.SCIENCE),
    ("ENG101", "English Language", SubjectCategory.ARTS),
    ("BIO101", "Biology", SubjectCategory.SCIENCE),
)


class Command(BaseCommand):
    help = (
        "Seed temporary NDGA test users (student, teachers, dean, form teacher, VP, "
        "bursar, principal) with minimal academic assignments. "
        "Use --cleanup to remove them later."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="admin",
            help="Password applied to all temporary users (default: admin).",
        )
        parser.add_argument(
            "--session-name",
            default="2025/2026",
            help="Academic session name to create/use (default: 2025/2026).",
        )
        parser.add_argument(
            "--term",
            default=TermName.FIRST,
            choices=[TermName.FIRST, TermName.SECOND, TermName.THIRD],
            help="Active term to create/use for assignments.",
        )
        parser.add_argument(
            "--class-code",
            default="JS1ALPHA",
            help="Academic class code to create/use (default: JS1ALPHA).",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Delete only the temporary users created by this command.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        cleanup = options["cleanup"]
        if cleanup:
            self._cleanup_users()
            return

        role_map = {role.code: role for role in Role.objects.filter(code__in=self._required_roles())}
        missing_roles = sorted(set(self._required_roles()) - set(role_map.keys()))
        if missing_roles:
            raise CommandError(
                f"Missing role(s): {', '.join(missing_roles)}. Run migrations first."
            )

        password = options["password"]
        session_name = options["session_name"]
        term_name = options["term"]
        class_code = options["class_code"].upper().strip()

        session, _ = AcademicSession.objects.get_or_create(name=session_name)
        term_map = {}
        for name in (TermName.FIRST, TermName.SECOND, TermName.THIRD):
            term, _ = Term.objects.get_or_create(session=session, name=name)
            term_map[name] = term
        active_term = term_map[term_name]

        academic_class, _ = AcademicClass.objects.get_or_create(
            code=class_code,
            defaults={"display_name": class_code.replace("JS1", "JS1 ").title()},
        )
        if not academic_class.display_name:
            academic_class.display_name = class_code
            academic_class.save(update_fields=["display_name"])

        subjects = {}
        for code, name, category in SUBJECT_ROWS:
            subject, _ = Subject.objects.get_or_create(
                code=code,
                defaults={"name": name, "category": category, "is_active": True},
            )
            if subject.name != name or subject.category != category or not subject.is_active:
                subject.name = name
                subject.category = category
                subject.is_active = True
                subject.save(update_fields=["name", "category", "is_active"])
            ClassSubject.objects.get_or_create(
                academic_class=academic_class,
                subject=subject,
                defaults={"is_active": True},
            )
            subjects[code] = subject

        created_users = self._create_users(role_map=role_map, password=password)

        # Staff/student profiles
        self._ensure_staff_profile(created_users["subject_teacher"], "TMP-STF-001")
        self._ensure_staff_profile(created_users["dean"], "TMP-STF-002")
        self._ensure_staff_profile(created_users["form_teacher"], "TMP-STF-003")
        self._ensure_staff_profile(created_users["vp"], "TMP-STF-004")
        self._ensure_staff_profile(created_users["bursar"], "TMP-STF-005")
        self._ensure_staff_profile(created_users["principal"], "TMP-STF-006")
        self._ensure_student_profile(created_users["student"], "TMP-STU-001")

        # Teaching assignments (three different subjects to satisfy uniqueness rules).
        TeacherSubjectAssignment.objects.update_or_create(
            subject=subjects["MTH101"],
            academic_class=academic_class,
            session=session,
            term=active_term,
            defaults={"teacher": created_users["subject_teacher"], "is_active": True},
        )
        TeacherSubjectAssignment.objects.update_or_create(
            subject=subjects["BIO101"],
            academic_class=academic_class,
            session=session,
            term=active_term,
            defaults={"teacher": created_users["dean"], "is_active": True},
        )
        TeacherSubjectAssignment.objects.update_or_create(
            subject=subjects["ENG101"],
            academic_class=academic_class,
            session=session,
            term=active_term,
            defaults={"teacher": created_users["form_teacher"], "is_active": True},
        )

        FormTeacherAssignment.objects.update_or_create(
            academic_class=academic_class,
            session=session,
            defaults={"teacher": created_users["form_teacher"], "is_active": True},
        )

        student_user = created_users["student"]
        StudentClassEnrollment.objects.update_or_create(
            student=student_user,
            session=session,
            defaults={"academic_class": academic_class, "is_active": True},
        )
        for subject in subjects.values():
            StudentSubjectEnrollment.objects.update_or_create(
                student=student_user,
                subject=subject,
                session=session,
                defaults={"is_active": True},
            )

        # Keep setup state usable for portal testing.
        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = active_term
        if setup_state.finalized_at is None:
            setup_state.finalized_at = timezone.now()
        setup_state.save(
            update_fields=[
                "state",
                "current_session",
                "current_term",
                "finalized_at",
                "updated_at",
            ]
        )

        runtime_flags = RuntimeFeatureFlags.get_solo()
        runtime_flags.cbt_enabled = True
        runtime_flags.election_enabled = True
        runtime_flags.save(update_fields=["cbt_enabled", "election_enabled", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Temporary NDGA test users are ready."))
        self.stdout.write(
            self.style.WARNING(
                f"All temporary users use password: {password!r} (change if needed)."
            )
        )
        for spec in TEMP_USERS:
            self.stdout.write(f"- {spec.primary_role:<16} {spec.username}")
        self.stdout.write(
            self.style.SUCCESS("Cleanup later with: python manage.py seed_temp_users --cleanup")
        )

    @staticmethod
    def _required_roles():
        return [
            ROLE_STUDENT,
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_VP,
            ROLE_BURSAR,
            ROLE_PRINCIPAL,
        ]

    def _cleanup_users(self):
        usernames = [spec.username for spec in TEMP_USERS]
        deleted_count, _ = User.objects.filter(username__in=usernames).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Removed temporary users and related dependent rows (objects deleted: {deleted_count})."
            )
        )

    def _create_users(self, *, role_map: dict[str, Role], password: str):
        users_by_key: dict[str, User] = {}
        for spec in TEMP_USERS:
            user, _ = User.objects.get_or_create(
                username=spec.username,
                defaults={"email": spec.username},
            )
            user.email = spec.username
            user.first_name = spec.first_name
            user.last_name = spec.last_name
            user.primary_role = role_map[spec.primary_role]
            user.is_staff = spec.primary_role != ROLE_STUDENT
            user.is_superuser = False
            user.must_change_password = False
            user.set_password(password)
            user.save()

            secondary_role_objs = [role_map[code] for code in spec.secondary_roles]
            user.secondary_roles.set(secondary_role_objs)
            users_by_key[spec.key] = user
        return users_by_key

    def _ensure_staff_profile(self, user: User, staff_id_seed: str):
        profile, _ = StaffProfile.objects.get_or_create(user=user, defaults={"staff_id": staff_id_seed})
        if profile.staff_id != staff_id_seed:
            # Keep deterministic id unless already occupied by another profile.
            candidate = staff_id_seed
            suffix = 1
            while StaffProfile.objects.exclude(user=user).filter(staff_id=candidate).exists():
                suffix += 1
                candidate = f"{staff_id_seed}-{suffix}"
            profile.staff_id = candidate
            profile.save(update_fields=["staff_id", "updated_at"])

    def _ensure_student_profile(self, user: User, student_number_seed: str):
        profile, _ = StudentProfile.objects.get_or_create(
            user=user,
            defaults={
                "student_number": student_number_seed,
                "gender": StudentProfile.Gender.FEMALE,
                "admission_date": timezone.localdate(),
            },
        )
        if profile.student_number != student_number_seed:
            candidate = student_number_seed
            suffix = 1
            while StudentProfile.objects.exclude(user=user).filter(student_number=candidate).exists():
                suffix += 1
                candidate = f"{student_number_seed}-{suffix}"
            profile.student_number = candidate
            profile.save(update_fields=["student_number", "updated_at"])
