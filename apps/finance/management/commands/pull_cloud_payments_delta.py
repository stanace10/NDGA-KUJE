from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.finance.services import pull_cloud_payment_deltas


class Command(BaseCommand):
    help = "Pull only new cloud payment events into the local finance ledger using the manual delta export endpoint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            type=str,
            default="",
            help="Optional ISO timestamp. When omitted, the stored cursor is used.",
        )
        parser.add_argument(
            "--no-cursor",
            action="store_true",
            help="Do not read or write the persistent finance delta cursor.",
        )

    def handle(self, *args, **options):
        since = None
        raw_since = (options.get("since") or "").strip()
        if raw_since:
            try:
                since = datetime.fromisoformat(raw_since)
            except ValueError as exc:
                raise CommandError("Invalid --since timestamp. Use ISO format.") from exc
            if timezone.is_naive(since):
                since = timezone.make_aware(since, timezone.get_current_timezone())

        result = pull_cloud_payment_deltas(
            updated_since=since,
            persist_cursor=not bool(options.get("no_cursor")),
        )
        latest = result.get("latest_timestamp")
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {result.get('count', 0)} payment delta event(s)."
                + (f" Latest timestamp: {latest.isoformat()}" if latest else "")
            )
        )
