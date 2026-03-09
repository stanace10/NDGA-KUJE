from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditCategory, AuditEvent, AuditStatus


class AuditPruneCommandTests(TestCase):
    def test_prune_audit_events_respects_retention_cutoff(self):
        recent = AuditEvent.objects.create(
            category=AuditCategory.SYSTEM,
            event_type="RECENT_EVENT",
            status=AuditStatus.SUCCESS,
            message="recent",
        )
        old = AuditEvent.objects.create(
            category=AuditCategory.SYSTEM,
            event_type="OLD_EVENT",
            status=AuditStatus.SUCCESS,
            message="old",
        )
        AuditEvent.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=4000)
        )

        out = StringIO()
        call_command("prune_audit_events", "--days", "365", stdout=out)

        self.assertTrue(AuditEvent.objects.filter(id=recent.id).exists())
        self.assertFalse(AuditEvent.objects.filter(id=old.id).exists())

    def test_prune_audit_events_dry_run_does_not_delete(self):
        old = AuditEvent.objects.create(
            category=AuditCategory.SYSTEM,
            event_type="OLD_EVENT_DRY_RUN",
            status=AuditStatus.SUCCESS,
            message="old dry run",
        )
        AuditEvent.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(days=4000)
        )

        out = StringIO()
        call_command("prune_audit_events", "--days", "365", "--dry-run", stdout=out)

        self.assertTrue(AuditEvent.objects.filter(id=old.id).exists())
