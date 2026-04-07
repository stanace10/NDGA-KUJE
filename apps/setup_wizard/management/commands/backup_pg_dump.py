from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.setup_wizard.backup_services import create_postgres_dump_backup


class Command(BaseCommand):
    help = "Create a PostgreSQL pg_dump backup and optionally upload it to S3."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=getattr(settings, "BACKUP_PG_OUTPUT_DIR", "backups/postgres"),
            help="Directory where the .dump file will be written.",
        )
        parser.add_argument(
            "--upload-s3",
            action="store_true",
            help="Upload the dump to S3 after creating it.",
        )
        parser.add_argument(
            "--s3-bucket",
            default=getattr(settings, "BACKUP_PG_S3_BUCKET", ""),
            help="Override the S3 bucket used for backup upload.",
        )
        parser.add_argument(
            "--s3-prefix",
            default=getattr(settings, "BACKUP_PG_S3_PREFIX", "nightly"),
            help="Override the S3 key prefix used for backup upload.",
        )
        parser.add_argument(
            "--keep-local",
            type=int,
            default=getattr(settings, "BACKUP_PG_KEEP_LOCAL_COUNT", 14),
            help="Number of local dump files to keep after pruning.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            payload = create_postgres_dump_backup(
                output_dir=output_dir,
                upload_to_s3=bool(options["upload_s3"]),
                s3_bucket=options["s3_bucket"],
                s3_prefix=options["s3_prefix"],
                keep_local_count=options["keep_local"],
            )
        except Exception as exc:
            raise CommandError(f"PostgreSQL backup failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"Backup created: {payload.file_path}"))
        self.stdout.write(f"SHA256: {payload.sha256}")
        self.stdout.write(f"Size: {payload.size_bytes} bytes")
        if payload.s3_bucket and payload.s3_key:
            self.stdout.write(
                self.style.SUCCESS(f"S3 uploaded: s3://{payload.s3_bucket}/{payload.s3_key}")
            )
