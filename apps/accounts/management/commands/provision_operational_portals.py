from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.constants import ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_SUBJECT_TEACHER
from apps.accounts.forms import _form_teacher_role_account_preset, _singleton_role_account_preset
from apps.accounts.models import Role, StaffProfile, User
from apps.academics.models import FormTeacherAssignment
from apps.results.models import ClassResultCompilation


class Command(BaseCommand):
    help = "Split dean and form-teacher duties into dedicated portal accounts."

    def handle(self, *args, **options):
        role_map = {role.code: role for role in Role.objects.filter(code__in=[ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_SUBJECT_TEACHER])}
        missing_roles = {ROLE_DEAN, ROLE_FORM_TEACHER, ROLE_SUBJECT_TEACHER} - set(role_map)
        if missing_roles:
            raise CommandError(f"Missing roles: {', '.join(sorted(missing_roles))}")

        summary = {
            "dean_accounts_created": 0,
            "dean_accounts_updated": 0,
            "form_accounts_created": 0,
            "form_accounts_updated": 0,
            "source_accounts_cleaned": 0,
            "form_assignments_reassigned": 0,
        }

        with transaction.atomic():
            dean_sources = list(
                User.objects.filter(primary_role__code=ROLE_DEAN)
                .select_related("staff_profile", "primary_role")
                .prefetch_related("secondary_roles")
            )
            for source_user in dean_sources:
                outcome, portal_user = self._ensure_dean_account(source_user, role_map[ROLE_DEAN])
                summary[f"dean_accounts_{outcome}"] += 1
                self.stdout.write(f"[{outcome.upper()}] dean portal -> {portal_user.staff_profile.staff_id}")
                if source_user.id != portal_user.id:
                    if self._clean_source_account(source_user, role_map[ROLE_SUBJECT_TEACHER], remove_roles={ROLE_DEAN}):
                        summary["source_accounts_cleaned"] += 1

            active_form_assignments = list(
                FormTeacherAssignment.objects.filter(is_active=True)
                .select_related("teacher", "teacher__staff_profile", "teacher__primary_role", "academic_class", "session")
                .prefetch_related("teacher__secondary_roles")
                .order_by("academic_class__code")
            )
            for assignment in active_form_assignments:
                source_user = assignment.teacher
                source_user_id = assignment.teacher_id
                outcome, portal_user = self._ensure_form_teacher_account(
                    source_user=source_user,
                    assignment=assignment,
                    form_role=role_map[ROLE_FORM_TEACHER],
                )
                summary[f"form_accounts_{outcome}"] += 1
                if source_user_id != portal_user.id:
                    assignment.teacher = portal_user
                    assignment.save(update_fields=["teacher", "updated_at"])
                    ClassResultCompilation.objects.filter(
                        academic_class=assignment.academic_class,
                        session=assignment.session,
                        form_teacher_id=source_user_id,
                    ).update(form_teacher=portal_user)
                    summary["form_assignments_reassigned"] += 1
                if source_user_id != portal_user.id:
                    if self._clean_source_account(source_user, role_map[ROLE_SUBJECT_TEACHER], remove_roles={ROLE_FORM_TEACHER}):
                        summary["source_accounts_cleaned"] += 1

        summary_line = ", ".join(f"{key}={value}" for key, value in summary.items())
        self.stdout.write(self.style.SUCCESS(f"Operational portals provisioned ({summary_line})."))

    def _ensure_dean_account(self, source_user, role):
        preset = _singleton_role_account_preset(ROLE_DEAN)
        if not preset:
            raise CommandError("Dean preset is not configured.")
        designation = "Dean"
        return self._ensure_staff_account(
            source_user=source_user,
            role=role,
            preset=preset,
            designation=designation,
        )

    def _ensure_form_teacher_account(self, *, source_user, assignment, form_role):
        preset = _form_teacher_role_account_preset(assignment.academic_class)
        if not preset:
            raise CommandError(f"Unable to generate form-teacher preset for {assignment.academic_class.code}.")
        designation = f"Form Teacher - {(assignment.academic_class.display_name or assignment.academic_class.code).strip()}"
        return self._ensure_staff_account(
            source_user=source_user,
            role=form_role,
            preset=preset,
            designation=designation,
        )

    def _ensure_staff_account(self, *, source_user, role, preset, designation):
        existing = (
            User.objects.filter(
                staff_profile__staff_id__iexact=preset["staff_id"]
            )
            .select_related("staff_profile", "primary_role")
            .prefetch_related("secondary_roles")
            .first()
        )
        if existing is None:
            existing = (
                User.objects.filter(username__iexact=preset["username"])
                .select_related("staff_profile", "primary_role")
                .prefetch_related("secondary_roles")
                .first()
            )
        created = existing is None
        if created:
            existing = User(
                username=preset["username"],
                email=source_user.email,
                first_name=source_user.first_name,
                last_name=source_user.last_name,
                display_name=source_user.display_name,
                primary_role=role,
                is_staff=True,
                must_change_password=False,
                password_changed_count=0,
                two_factor_enabled=source_user.two_factor_enabled,
                two_factor_email=source_user.two_factor_email,
            )
        else:
            existing.username = preset["username"]
            existing.email = source_user.email
            existing.first_name = source_user.first_name
            existing.last_name = source_user.last_name
            existing.display_name = source_user.display_name
            existing.primary_role = role
            existing.is_staff = True
            existing.must_change_password = False
            existing.password_changed_count = 0
        existing.set_password(preset["password"])
        existing.clear_login_code()
        existing.save()
        existing.secondary_roles.clear()

        source_profile = getattr(source_user, "staff_profile", None)
        profile_defaults = {
            "staff_id": preset["staff_id"],
            "designation": designation,
            "phone_number": getattr(source_profile, "phone_number", ""),
        }
        profile, _ = StaffProfile.objects.get_or_create(user=existing, defaults=profile_defaults)
        profile.staff_id = preset["staff_id"]
        profile.designation = designation
        if source_profile is not None:
            profile.phone_number = source_profile.phone_number
            if getattr(source_profile, "profile_photo", None) and not profile.profile_photo:
                profile.profile_photo = source_profile.profile_photo
        profile.save()
        existing.refresh_from_db()
        return ("created" if created else "updated"), existing

    def _clean_source_account(self, source_user, subject_role, *, remove_roles):
        changed = False
        primary_role = getattr(source_user, "primary_role", None)
        if primary_role and primary_role.code in remove_roles:
            source_user.primary_role = subject_role
            changed = True
        removable_secondary_ids = list(
            source_user.secondary_roles.filter(code__in=remove_roles).values_list("id", flat=True)
        )
        if removable_secondary_ids:
            source_user.secondary_roles.remove(*removable_secondary_ids)
            changed = True
        duplicate_subject_secondary = source_user.secondary_roles.filter(code=ROLE_SUBJECT_TEACHER).exists()
        if source_user.primary_role_id == subject_role.id and duplicate_subject_secondary:
            source_user.secondary_roles.remove(*source_user.secondary_roles.filter(code=ROLE_SUBJECT_TEACHER).values_list("id", flat=True))
            changed = True
        if changed:
            source_user.save(update_fields=["primary_role"])
        return changed
