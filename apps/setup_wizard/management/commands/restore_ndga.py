from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.setup_wizard.backup_services import restore_local_backup_archive


class Command(BaseCommand):
    help = (
        "Restore NDGA local backup archive. "
        "By default, this flushes DB and clears media before restore."
    )

    def add_arguments(self, parser):
        parser.add_argument("archive", help="Path to backup zip file.")
        parser.add_argument(
            "--skip-flush",
            action="store_true",
            help="Do not flush database before restore.",
        )
        parser.add_argument(
            "--keep-media",
            action="store_true",
            help="Keep existing media files (do not clear media root before restore).",
        )

    def handle(self, *args, **options):
        archive_path = Path(options["archive"]).resolve()
        if not archive_path.exists():
            raise CommandError("Backup file does not exist.")
        try:
            summary = restore_local_backup_archive(
                archive_path=archive_path,
                flush_database=not options["skip_flush"],
                clear_media=not options["keep_media"],
            )
        except Exception as exc:
            raise CommandError(f"Restore failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Restore completed successfully."))
        self.stdout.write(f"Archive: {summary['archive']}")
        self.stdout.write(
            "Media restored: "
            f"{summary['restored_media_files']} / {summary['manifest_media_files']}"
        )
        self.stdout.write(
            "Checksum mismatches detected: "
            f"{summary['checksum_mismatches']}"
        )
