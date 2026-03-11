from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditCategory, AuditEvent, AuditStatus
from apps.audit.services import log_event, verify_audit_chain


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


class AuditIntegrityTests(TestCase):
    def test_verify_audit_chain_detects_tampering(self):
        first = log_event(
            category=AuditCategory.SYSTEM,
            event_type="CHAIN_START",
            status=AuditStatus.SUCCESS,
            message="first",
        )
        second = log_event(
            category=AuditCategory.SYSTEM,
            event_type="CHAIN_NEXT",
            status=AuditStatus.SUCCESS,
            message="second",
        )

        clean_summary = verify_audit_chain()
        self.assertTrue(clean_summary["ok"])
        self.assertEqual(clean_summary["verified_count"], 2)
        self.assertEqual(second.previous_event_hash, first.event_hash)

        AuditEvent.objects.filter(id=second.id).update(message="tampered")
        tampered_summary = verify_audit_chain()
        self.assertFalse(tampered_summary["ok"])
        self.assertTrue(
            any(
                row["event_id"] == second.id and row["issue"] == "event_hash_mismatch"
                for row in tampered_summary["mismatches"]
            )
        )
