from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.setup_wizard.backup_services import create_local_backup_archive


class Command(BaseCommand):
    help = "Create NDGA local backup archive (database + media + manifest)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="backups",
            help="Directory where backup zip will be written (default: backups).",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = create_local_backup_archive(actor=None)
        except Exception as exc:
            raise CommandError(f"Backup failed: {exc}") from exc

        target_path = output_dir / payload.filename
        target_path.write_bytes(payload.archive_bytes)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {target_path}"))
        self.stdout.write(
            f"Media files: {payload.media_file_count} | Setup state: {payload.metadata.get('setup_state', '')}"
        )
