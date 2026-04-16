from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.sync.models import SyncTransferBatch, SyncTransferDirection
from core.manual_updates import LAN_TO_CLOUD_CHANNELS, push_local_manual_updates


CURSOR_FILE_NAME = "MANUAL_PUSH_LAN_TO_CLOUD"


class Command(BaseCommand):
    help = (
        "Push LAN-owned published results, attendance, student profile updates, "
        "and receipts to cloud using the manual update endpoint."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--channels",
            default="results,attendance,students,receipts",
            help="Comma-separated channels to push.",
        )
        parser.add_argument(
            "--since",
            help="Optional ISO timestamp override.",
        )
        parser.add_argument(
            "--limit-per-model",
            type=int,
            default=250,
            help="Maximum rows to export per model in this push.",
        )
        parser.add_argument(
            "--no-cursor",
            action="store_true",
            help="Do not persist the latest pushed timestamp.",
        )

    def handle(self, *args, **options):
        channels = [item.strip().lower() for item in str(options["channels"]).split(",") if item.strip()]
        invalid = [item for item in channels if item not in LAN_TO_CLOUD_CHANNELS]
        if invalid:
            raise CommandError(f"Unsupported channel(s): {', '.join(sorted(set(invalid)))}")

        updated_since = self._resolve_since(options.get("since"))
        try:
            result = push_local_manual_updates(
                channels=channels,
                updated_since=updated_since,
                limit_per_model=options["limit_per_model"],
            )
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc

        latest_timestamp = str(result.get("latest_timestamp") or "").strip()
        self.stdout.write(
            self.style.SUCCESS(
                f"Pushed {result.get('count', 0)} manual update item(s) to cloud; skipped {result.get('skipped', 0)}."
            )
        )
        if result.get("errors"):
            for message in result["errors"][:10]:
                self.stdout.write(self.style.WARNING(message))

        if not options["no_cursor"]:
            SyncTransferBatch.objects.create(
                direction=SyncTransferDirection.EXPORT,
                file_name=CURSOR_FILE_NAME,
                item_count=int(result.get("count", 0)),
                metadata={
                    "channels": channels,
                    "latest_timestamp": latest_timestamp,
                    "skipped": int(result.get("skipped", 0)),
                    "errors": result.get("errors", [])[:20],
                },
            )

    def _resolve_since(self, raw_since):
        if raw_since:
            try:
                parsed = datetime.fromisoformat(str(raw_since).replace("Z", "+00:00"))
            except ValueError as exc:
                raise CommandError("Invalid --since timestamp.") from exc
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed

        last_batch = (
            SyncTransferBatch.objects.filter(
                direction=SyncTransferDirection.EXPORT,
                file_name=CURSOR_FILE_NAME,
            )
            .order_by("-created_at")
            .first()
        )
        latest_raw = str((last_batch.metadata or {}).get("latest_timestamp") or "").strip() if last_batch else ""
        if not latest_raw:
            return None
        parsed = datetime.fromisoformat(latest_raw.replace("Z", "+00:00"))
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed
