from __future__ import annotations

from celery import shared_task
from django.conf import settings

from apps.setup_wizard.backup_services import create_postgres_dump_backup


@shared_task(name="setup.nightly_pg_backup")
def nightly_pg_backup_task():
    return create_postgres_dump_backup(
        output_dir=getattr(settings, "BACKUP_PG_OUTPUT_DIR", "backups/postgres"),
        upload_to_s3=bool(getattr(settings, "BACKUP_PG_S3_ENABLED", False)),
        s3_bucket=getattr(settings, "BACKUP_PG_S3_BUCKET", ""),
        s3_prefix=getattr(settings, "BACKUP_PG_S3_PREFIX", "nightly"),
        keep_local_count=getattr(settings, "BACKUP_PG_KEEP_LOCAL_COUNT", 14),
    ).__dict__
