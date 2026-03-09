from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify Stage 20 production-readiness artifacts and runtime essentials."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail the command if warnings are present.",
        )

    def handle(self, *args, **options):
        strict = options["strict"]
        root_dir = settings.ROOT_DIR
        failures: list[str] = []
        warnings: list[str] = []

        required_files = [
            root_dir / "core" / "settings" / "prod.py",
            root_dir / "deploy" / "nginx" / "ndga.conf",
            root_dir / "deploy" / "systemd" / "ndga-asgi.service",
            root_dir / "deploy" / "systemd" / "ndga-celery-worker.service",
            root_dir / "deploy" / "systemd" / "ndga-celery-beat.service",
            root_dir / "deploy" / "docker" / "docker-compose.lan.yml",
            root_dir / "deploy" / "docker" / "Dockerfile.lan",
            root_dir / "docs" / "STAGE20_DEPLOYMENT_BLUEPRINT.md",
            root_dir / "docs" / "GO_LIVE_CHECKLIST.md",
            root_dir / "docs" / "OFFLINE_LAN_AND_PORTABLE_BACKUPS.md",
            root_dir / "scripts" / "backup_ndga.ps1",
            root_dir / "scripts" / "restore_ndga.ps1",
            root_dir / "scripts" / "pg_dump_custom.ps1",
            root_dir / "scripts" / "pg_restore_custom.ps1",
            root_dir / "scripts" / "media_sync_rclone.ps1",
        ]
        for path in required_files:
            if not path.exists():
                failures.append(f"Missing required artifact: {path}")

        root_env = root_dir / ".env"
        legacy_lan_env = root_dir / "deploy" / "docker" / ".env.lan"
        if not root_env.exists() and not legacy_lan_env.exists():
            failures.append("Missing runtime environment file: create a root .env for cloud or LAN deployment.")

        if settings.DEBUG:
            failures.append("DEBUG=True is not allowed for production settings.")

        if not settings.ALLOWED_HOSTS:
            failures.append("ALLOWED_HOSTS is empty.")
        if not settings.CSRF_TRUSTED_ORIGINS:
            failures.append("CSRF_TRUSTED_ORIGINS is empty.")
        if len(getattr(settings, "SECRET_KEY", "")) < 50:
            warnings.append("SECRET_KEY appears too short for production.")

        if not getattr(settings, "NOTIFICATIONS_FROM_EMAIL", "").strip():
            warnings.append("NOTIFICATIONS_FROM_EMAIL is not configured.")

        email_provider = (
            getattr(settings, "NOTIFICATIONS_EMAIL_PROVIDER", "console").strip().lower()
        )
        brevo_key = getattr(settings, "BREVO_API_KEY", "").strip()
        if email_provider == "brevo" and not brevo_key:
            failures.append(
                "NOTIFICATIONS_EMAIL_PROVIDER=brevo but BREVO_API_KEY is empty."
            )

        media_backend = getattr(settings, "MEDIA_STORAGE_BACKEND", "filesystem")
        if media_backend == "s3":
            bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "").strip()
            region = getattr(settings, "AWS_S3_REGION_NAME", "").strip()
            if not bucket:
                failures.append("MEDIA_STORAGE_BACKEND=s3 but AWS_STORAGE_BUCKET_NAME is empty.")
            if not region:
                warnings.append("MEDIA_STORAGE_BACKEND=s3 but AWS_S3_REGION_NAME is empty.")
        elif media_backend == "cloudinary":
            cloud = getattr(settings, "CLOUDINARY_STORAGE", {}).get("CLOUD_NAME", "")
            if not cloud:
                failures.append(
                    "MEDIA_STORAGE_BACKEND=cloudinary but CLOUDINARY storage credentials are missing."
                )

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write(self.style.SUCCESS("Database connectivity: OK"))
        except Exception as exc:  # pragma: no cover - environment check
            failures.append(f"Database connectivity check failed: {exc}")

        if failures:
            for item in failures:
                self.stderr.write(self.style.ERROR(item))
            raise CommandError("Stage 20 verification failed.")

        if warnings:
            for item in warnings:
                self.stdout.write(self.style.WARNING(f"Warning: {item}"))
            if strict:
                raise CommandError("Stage 20 strict verification failed due to warnings.")

        self.stdout.write(self.style.SUCCESS("Stage 20 verification passed."))
