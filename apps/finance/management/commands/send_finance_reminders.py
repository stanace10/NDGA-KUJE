from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.finance.services import dispatch_scheduled_fee_reminders


class Command(BaseCommand):
    help = "Run scheduled finance reminders immediately."

    def add_arguments(self, parser):
        parser.add_argument("--days-ahead", type=int, default=3)

    def handle(self, *args, **options):
        result = dispatch_scheduled_fee_reminders(days_ahead=options["days_ahead"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Finance reminders completed: sent={result['sent']} skipped={result['skipped']} failed={result['failed']}"
            )
        )
