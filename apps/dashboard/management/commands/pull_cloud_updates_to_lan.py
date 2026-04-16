from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Pull cloud-originated student payment deltas and admission registration/payment updates "
        "into the LAN instance."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="Optional ISO timestamp override applied to both payment and admissions pulls.",
        )
        parser.add_argument(
            "--no-cursor",
            action="store_true",
            help="Do not read or write persistent pull cursors.",
        )

    def handle(self, *args, **options):
        since = (options.get("since") or "").strip()
        no_cursor = bool(options.get("no_cursor"))
        command_options = {}
        if since:
            command_options["since"] = since
        if no_cursor:
            command_options["no_cursor"] = True

        try:
            self.stdout.write("Pulling cloud payment records into LAN...")
            call_command("pull_cloud_payments_delta", **command_options)
            self.stdout.write(self.style.SUCCESS("Cloud payment pull complete."))

            self.stdout.write("Pulling cloud admission registrations and payment status into LAN...")
            call_command("pull_cloud_admissions_delta", **command_options)
            self.stdout.write(self.style.SUCCESS("Cloud admissions pull complete."))
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Cloud-to-LAN manual update failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                "LAN is now updated with the latest cloud payment and admission records."
            )
        )
