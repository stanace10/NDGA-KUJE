import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.setup_wizard.backup_services import create_local_backup_archive, inspect_backup_archive


class Command(BaseCommand):
    help = "Create a fresh backup archive, validate it, and report restore-drill readiness without touching live data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="backups/drills",
            help="Directory where the drill archive should be written.",
        )
        parser.add_argument(
            "--keep-archive",
            action="store_true",
            help="Keep the generated archive instead of deleting it after inspection.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        started_at = timezone.now()
        payload = create_local_backup_archive(actor=None)
        archive_path = output_dir / payload.filename
        archive_path.write_bytes(payload.archive_bytes)
        inspection = inspect_backup_archive(archive_path)
        completed_at = timezone.now()

        archive_kept = bool(options["keep_archive"])
        if not archive_kept:
            archive_path.unlink(missing_ok=True)

        summary = {
            "status": "ok",
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "elapsed_seconds": round((completed_at - started_at).total_seconds(), 3),
            "archive_kept": archive_kept,
            "archive_path": str(archive_path),
            "inspection": inspection,
        }
        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
