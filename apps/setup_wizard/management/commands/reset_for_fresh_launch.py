from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.constants import ROLE_CHOICES, ROLE_IT_MANAGER
from apps.accounts.models import Role, StaffProfile, User
from apps.setup_wizard.models import RuntimeFeatureFlags, SetupStateCode, SystemSetupState


class Command(BaseCommand):
    help = "Reset operational data and bootstrap a single IT Manager for fresh launch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--it-username",
            default=getattr(settings, "IT_BOOTSTRAP_USERNAME", "admin@ndgakuje.org"),
            help="IT Manager username to keep after reset.",
        )
        parser.add_argument(
            "--it-password",
            default="admin",
            help="Password for the IT Manager account after reset.",
        )
        parser.add_argument(
            "--it-email",
            default="admin@ndgakuje.org",
            help="Email for the IT Manager account after reset.",
        )
        parser.add_argument(
            "--staff-id",
            default="ITM-001",
            help="Staff ID to assign to the IT Manager profile.",
        )
        parser.add_argument(
            "--yes-i-know",
            action="store_true",
            help="Required confirmation flag because this command irreversibly deletes data.",
        )

    def handle(self, *args, **options):
        if not options["yes_i_know"]:
            raise CommandError(
                "Refusing to run destructive reset without --yes-i-know."
            )

        username = (options["it_username"] or "").strip()
        password = options["it_password"] or ""
        email = (options["it_email"] or "").strip()
        staff_id = (options["staff_id"] or "").strip() or "ITM-001"

        if not username:
            raise CommandError("IT username is required.")
        if not password:
            raise CommandError("IT password is required.")

        self.stdout.write(self.style.WARNING("Flushing database tables..."))
        management.call_command("flush", "--noinput", verbosity=0)

        with transaction.atomic():
            role_map = {}
            for code, label in ROLE_CHOICES:
                role, _ = Role.objects.get_or_create(
                    code=code,
                    defaults={"name": label, "description": f"{label} role", "is_system": True},
                )
                role_map[code] = role

            it_role = role_map.get(ROLE_IT_MANAGER)
            if it_role is None:
                raise CommandError("IT_MANAGER role bootstrap failed.")

            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            user.primary_role = it_role
            user.is_staff = True
            user.is_superuser = True
            user.must_change_password = False
            user.save()

            StaffProfile.objects.update_or_create(
                user=user,
                defaults={
                    "staff_id": staff_id,
                    "designation": "IT Manager",
                },
            )

            setup_state = SystemSetupState.get_solo()
            setup_state.state = SetupStateCode.BOOT_EMPTY
            setup_state.current_session = None
            setup_state.current_term = None
            setup_state.finalized_at = None
            setup_state.finalized_by = None
            setup_state.last_updated_by = user
            setup_state.save(
                update_fields=[
                    "state",
                    "current_session",
                    "current_term",
                    "finalized_at",
                    "finalized_by",
                    "last_updated_by",
                    "updated_at",
                ]
            )

            flags = RuntimeFeatureFlags.get_solo()
            flags.last_updated_by = user
            flags.save(update_fields=["last_updated_by", "updated_at"])

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("NDGA reset complete."))
        self.stdout.write(f"IT Manager username: {username}")
        self.stdout.write(f"IT Manager password: {password}")
