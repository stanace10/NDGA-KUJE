from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Create or update an IT Manager account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=getattr(settings, "IT_BOOTSTRAP_USERNAME", "admin@ndgakuje.org"),
        )
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", default="")
        parser.add_argument(
            "--prune-others",
            action="store_true",
            help="Delete any other accounts currently assigned as IT_MANAGER.",
        )

    def handle(self, *args, **options):
        role = Role.objects.filter(code=ROLE_IT_MANAGER).first()
        if role is None:
            raise CommandError("IT_MANAGER role missing. Run migrations first.")

        username = options["username"]
        password = options["password"]
        email = options["email"]
        prune_others = options["prune_others"]

        user, created = User.objects.get_or_create(username=username, defaults={"email": email})
        user.email = email
        user.primary_role = role
        user.is_staff = True
        user.is_superuser = True
        user.must_change_password = False
        user.set_password(password)
        user.save()

        other_it_managers = User.objects.filter(primary_role=role).exclude(id=user.id)
        if prune_others:
            removed_count = other_it_managers.count()
            if removed_count:
                other_it_managers.delete()
                self.stdout.write(
                    self.style.WARNING(
                        f"Removed {removed_count} additional IT_MANAGER account(s)."
                    )
                )
        elif other_it_managers.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Detected {other_it_managers.count()} other IT_MANAGER account(s). "
                    "Run with --prune-others to keep only this account."
                )
            )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Created IT Manager user: {username}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated IT Manager user: {username}"))
