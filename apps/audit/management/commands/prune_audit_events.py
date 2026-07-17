from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.audit.models import AuditEvent


class Command(BaseCommand):
    help = "Prune old audit events according to retention policy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=settings.AUDIT_RETENTION_DAYS,
            help="Delete events older than N days (default from AUDIT_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            help="Delete in batches to avoid long table locks.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many events would be deleted without deleting.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if days < 1:
            raise CommandError("--days must be >= 1")
        if batch_size < 100:
            raise CommandError("--batch-size must be >= 100")

        cutoff = timezone.now() - timedelta(days=days)
        queryset = AuditEvent.objects.filter(created_at__lt=cutoff).order_by("id")
        total = queryset.count()
        self.stdout.write(
            f"Retention cutoff: {cutoff.isoformat()} | candidates: {total}"
        )

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry-run enabled. No rows were deleted.")
            )
            return

        deleted_total = 0
        while True:
            ids = list(queryset.values_list("id", flat=True)[:batch_size])
            if not ids:
                break
            deleted, _ = AuditEvent.objects.filter(id__in=ids).delete()
            deleted_total += deleted
            self.stdout.write(f"Deleted {deleted_total}/{total}...")

        self.stdout.write(
            self.style.SUCCESS(
                f"Audit prune complete. Deleted {deleted_total} event(s)."
            )
        )
