from __future__ import annotations

from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.sync.models import SyncTransferBatch, SyncTransferDirection
from core.manual_updates import apply_manual_update_payload, fetch_remote_manual_update_payload


CURSOR_FILE_NAME = "MANUAL_PULL_CLOUD_ADMISSIONS"


class Command(BaseCommand):
    help = "Pull admission registrations and admission payment status from cloud into LAN."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since",
            help="Optional ISO timestamp override.",
        )
        parser.add_argument(
            "--limit-per-model",
            type=int,
            default=250,
            help="Maximum rows to request per model in this pull.",
        )
        parser.add_argument(
            "--no-cursor",
            action="store_true",
            help="Do not persist the latest pulled timestamp.",
        )

    def handle(self, *args, **options):
        updated_since = self._resolve_since(options.get("since"))
        try:
            payload = fetch_remote_manual_update_payload(
                channels=["admissions"],
                updated_since=updated_since,
                limit_per_model=options["limit_per_model"],
            )
            summary = apply_manual_update_payload(
                payload=payload,
                allowed_channels=["admissions"],
            )
        except ValidationError as exc:
            raise CommandError(str(exc)) from exc

        latest_timestamp = summary.get("latest_timestamp")
        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {summary.get('count', 0)} admission item(s); skipped {summary.get('skipped', 0)}."
            )
        )
        if summary.get("errors"):
            for message in summary["errors"][:10]:
                self.stdout.write(self.style.WARNING(message))

        if not options["no_cursor"]:
            SyncTransferBatch.objects.create(
                direction=SyncTransferDirection.IMPORT,
                file_name=CURSOR_FILE_NAME,
                item_count=int(summary.get("count", 0)),
                metadata={
                    "channels": ["admissions"],
                    "latest_timestamp": latest_timestamp.isoformat() if latest_timestamp else "",
                    "skipped": int(summary.get("skipped", 0)),
                    "errors": summary.get("errors", [])[:20],
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
                direction=SyncTransferDirection.IMPORT,
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
