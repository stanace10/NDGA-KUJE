from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.constants import ROLE_BURSAR, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.forms import _singleton_role_account_preset
from apps.accounts.models import Role, StaffProfile, User


DEFAULT_ACCOUNT_DETAILS = {
    ROLE_VP: {
        "first_name": "Vice",
        "last_name": "Principal",
        "designation": "Vice Principal",
    },
    ROLE_PRINCIPAL: {
        "first_name": "School",
        "last_name": "Principal",
        "designation": "Principal",
    },
    ROLE_BURSAR: {
        "first_name": "Main",
        "last_name": "Bursar",
        "designation": "Bursar",
    },
}


class Command(BaseCommand):
    help = "Ensure the default VP, Principal, and Bursar accounts exist for production use."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sync-passwords",
            action="store_true",
            help="Reset the singleton leadership account passwords to the NDGA defaults.",
        )

    def handle(self, *args, **options):
        sync_passwords = options["sync_passwords"]
        required_codes = tuple(DEFAULT_ACCOUNT_DETAILS.keys())
        roles = {role.code: role for role in Role.objects.filter(code__in=required_codes)}
        missing = [code for code in required_codes if code not in roles]
        if missing:
            raise CommandError(
                "Missing role(s): " + ", ".join(sorted(missing)) + ". Run migrations first."
            )

        counts = {"created": 0, "updated": 0, "unchanged": 0}
        with transaction.atomic():
            for role_code in required_codes:
                outcome, user = self._ensure_account(
                    role=roles[role_code],
                    role_code=role_code,
                    sync_passwords=sync_passwords,
                )
                counts[outcome] += 1
                self.stdout.write(f"[{outcome.upper()}] {role_code}: {user.username}")

        summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Default portal accounts ready ({summary})."))

    def _ensure_account(self, *, role, role_code, sync_passwords):
        preset = _singleton_role_account_preset(role_code)
        if not preset:
            raise CommandError(f"No singleton preset configured for role {role_code}.")
        details = DEFAULT_ACCOUNT_DETAILS[role_code]

        user = self._resolve_user(role=role, preset=preset, role_code=role_code)
        created = user is None
        changed = False

        if created:
            user = User(
                username=preset["username"],
                email=self._email_for_username(preset["username"]),
                first_name=details["first_name"],
                last_name=details["last_name"],
                primary_role=role,
                is_staff=True,
                must_change_password=False,
                password_changed_count=0,
            )
            user.set_password(preset["password"])
            user.save()
            changed = True
        else:
            if user.username != preset["username"]:
                user.username = preset["username"]
                changed = True
            expected_email = self._email_for_username(preset["username"])
            if user.email != expected_email:
                user.email = expected_email
                changed = True
            if not user.first_name:
                user.first_name = details["first_name"]
                changed = True
            if not user.last_name:
                user.last_name = details["last_name"]
                changed = True
            if user.primary_role_id != role.id:
                user.primary_role = role
                changed = True
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if user.must_change_password:
                user.must_change_password = False
                changed = True
            if sync_passwords:
                user.set_password(preset["password"])
                user.password_changed_count = 0
                user.must_change_password = False
                changed = True
            if changed:
                user.save()

        duplicate_profile = StaffProfile.objects.exclude(user=user).filter(
            staff_id__iexact=preset["staff_id"]
        )
        if duplicate_profile.exists():
            raise CommandError(
                f"Cannot assign {preset['staff_id']} to {role_code}; it already belongs to "
                f"{duplicate_profile.select_related('user').first().user.username}."
            )

        profile, profile_created = StaffProfile.objects.get_or_create(
            user=user,
            defaults={
                "staff_id": preset["staff_id"],
                "designation": details["designation"],
            },
        )
        profile_changed = False
        if profile.staff_id != preset["staff_id"]:
            profile.staff_id = preset["staff_id"]
            profile_changed = True
        if not profile.designation:
            profile.designation = details["designation"]
            profile_changed = True
        if profile_created or profile_changed:
            profile.save()

        if created:
            return "created", user
        if changed or profile_created or profile_changed:
            return "updated", user
        return "unchanged", user

    def _resolve_user(self, *, role, preset, role_code):
        candidates = list(
            User.objects.select_related("primary_role")
            .filter(
                Q(primary_role=role)
                | Q(username__iexact=preset["username"])
                | Q(staff_profile__staff_id__iexact=preset["staff_id"])
            )
            .distinct()
        )
        if len(candidates) > 1:
            usernames = ", ".join(sorted(user.username for user in candidates))
            raise CommandError(
                f"Conflicting users found for {role_code}: {usernames}. Resolve duplicates first."
            )
        return candidates[0] if candidates else None

    @staticmethod
    def _email_for_username(username):
        return username if "@" in username else ""
