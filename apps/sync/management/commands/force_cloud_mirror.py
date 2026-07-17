from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.sync.content_sync import _fetch_cbt_content_feed, apply_cbt_content_changes
from apps.sync.inbound_sync import ingest_remote_outbox_event
from apps.sync.models import SyncContentStream, SyncOperationType, SyncPullCursor
from apps.sync.policies import lan_results_only_mode_enabled
from apps.sync.services import _cloud_endpoint, _fetch_remote_outbox_feed


class Command(BaseCommand):
    help = (
        "Force a full cloud-to-local mirror replay from the cloud outbox and CBT content feeds. "
        "This bypasses stale local duplicate markers and re-applies cloud data from the start."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=200,
            help="Page size for both outbox and CBT content feed pulls.",
        )
        parser.add_argument(
            "--max-outbox-pages",
            type=int,
            default=1000,
            help="Maximum outbox pages to replay in one run.",
        )
        parser.add_argument(
            "--max-content-pages",
            type=int,
            default=1000,
            help="Maximum CBT content pages to replay in one run.",
        )
        parser.add_argument(
            "--skip-outbox",
            action="store_true",
            help="Skip generic outbox replay and only replay CBT content.",
        )
        parser.add_argument(
            "--skip-content",
            action="store_true",
            help="Skip CBT content replay and only replay generic outbox events.",
        )
        parser.add_argument(
            "--allow-operation",
            action="append",
            default=[],
            help="Only replay the specified operation type(s). Repeat as needed.",
        )
        parser.add_argument(
            "--allow-model",
            action="append",
            default=[],
            help="For generic model events, only replay the specified model label(s). Repeat as needed.",
        )
        parser.add_argument(
            "--deny-model",
            action="append",
            default=[],
            help="For generic model events, skip the specified model label(s). Repeat as needed.",
        )

    def handle(self, *args, **options):
        if lan_results_only_mode_enabled():
            raise CommandError(
                "force_cloud_mirror is disabled while LAN results-only mode is active."
            )
        endpoint = _cloud_endpoint()
        if not endpoint:
            raise CommandError("SYNC_CLOUD_ENDPOINT is not configured.")

        limit = max(1, min(int(options["limit"]), 500))
        max_outbox_pages = max(1, int(options["max_outbox_pages"]))
        max_content_pages = max(1, int(options["max_content_pages"]))
        allowed_operations = {
            str(value or "").strip().upper()
            for value in (options.get("allow_operation") or [])
            if str(value or "").strip()
        }
        allowed_models = {
            str(value or "").strip().lower()
            for value in (options.get("allow_model") or [])
            if str(value or "").strip()
        }
        denied_models = {
            str(value or "").strip().lower()
            for value in (options.get("deny_model") or [])
            if str(value or "").strip()
        }

        self.stdout.write(f"Cloud endpoint: {endpoint}")
        if not options["skip_outbox"]:
            outbox_summary = self._replay_outbox(
                limit=limit,
                max_pages=max_outbox_pages,
                allowed_operations=allowed_operations,
                allowed_models=allowed_models,
                denied_models=denied_models,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Outbox replay complete: "
                    f"applied {outbox_summary['applied']}, "
                    f"reapplied {outbox_summary['reapplied']}, "
                    f"duplicates {outbox_summary['duplicates']}, "
                    f"blocked {outbox_summary['blocked']}, "
                    f"skipped {outbox_summary['skipped']}, "
                    f"pages {outbox_summary['pages']}."
                )
            )
            if outbox_summary["error"]:
                self.stdout.write(self.style.WARNING(f"Outbox replay warning: {outbox_summary['error']}"))

        if not options["skip_content"]:
            content_summary = self._replay_content(limit=limit, max_pages=max_content_pages)
            self.stdout.write(
                self.style.SUCCESS(
                    "CBT content replay complete: "
                    f"applied {content_summary['applied']}, "
                    f"blocked {content_summary['blocked']}, "
                    f"pages {content_summary['pages']}."
                )
            )
            if content_summary["error"]:
                self.stdout.write(self.style.WARNING(f"CBT content replay warning: {content_summary['error']}"))

    def _replay_outbox(self, *, limit, max_pages, allowed_operations, allowed_models, denied_models):
        summary = {
            "applied": 0,
            "reapplied": 0,
            "duplicates": 0,
            "blocked": 0,
            "skipped": 0,
            "pages": 0,
            "last_remote_id": 0,
            "error": "",
        }
        after_id = 0
        for _ in range(max_pages):
            summary["pages"] += 1
            fetch_result = _fetch_remote_outbox_feed(after_id=after_id, limit=limit)
            if not fetch_result["ok"]:
                summary["error"] = fetch_result["error"] or "Unable to fetch remote outbox feed."
                break

            payload = fetch_result.get("payload") or {}
            events = payload.get("events") or []
            if not events:
                break

            next_after_id = after_id
            for event in events:
                remote_id = int(event.get("id") or 0)
                operation_type = str(event.get("operation_type") or "").strip().upper()
                payload = event.get("payload") or {}
                model_label = str(payload.get("model") or "").strip().lower()
                if allowed_operations and operation_type not in allowed_operations:
                    summary["skipped"] += 1
                    if remote_id > next_after_id:
                        next_after_id = remote_id
                    continue
                if operation_type in {
                    SyncOperationType.MODEL_RECORD_UPSERT,
                    SyncOperationType.MODEL_RECORD_DELETE,
                }:
                    if allowed_models and model_label not in allowed_models:
                        summary["skipped"] += 1
                        if remote_id > next_after_id:
                            next_after_id = remote_id
                        continue
                    if model_label and model_label in denied_models:
                        summary["skipped"] += 1
                        if remote_id > next_after_id:
                            next_after_id = remote_id
                        continue
                try:
                    result = ingest_remote_outbox_event(envelope=event, force_reapply=True)
                except (ValidationError, IntegrityError) as exc:
                    summary["blocked"] += 1
                    summary["error"] = "; ".join(getattr(exc, "messages", [])) or str(exc)
                    continue
                status = result.get("status")
                if status == "duplicate":
                    summary["duplicates"] += 1
                elif status == "reapplied":
                    summary["reapplied"] += 1
                else:
                    summary["applied"] += 1
                if remote_id > next_after_id:
                    next_after_id = remote_id

            after_id = next_after_id
            summary["last_remote_id"] = after_id
            if not payload.get("has_more", False):
                break

        SyncPullCursor.objects.update_or_create(
            stream=SyncContentStream.OUTBOX_EVENTS,
            defaults={
                "last_remote_id": summary["last_remote_id"],
                "last_pull_at": timezone.now(),
                "last_success_at": timezone.now(),
                "last_error": summary["error"],
                "metadata": {
                    "forced_replay": True,
                    "applied": summary["applied"],
                    "reapplied": summary["reapplied"],
                    "duplicates": summary["duplicates"],
                    "blocked": summary["blocked"],
                    "skipped": summary["skipped"],
                    "pages": summary["pages"],
                },
            },
        )
        return summary

    def _replay_content(self, *, limit, max_pages):
        summary = {
            "applied": 0,
            "blocked": 0,
            "pages": 0,
            "last_remote_id": 0,
            "error": "",
        }
        after_id = 0
        all_changes = []
        for _ in range(max_pages):
            summary["pages"] += 1
            fetch_result = _fetch_cbt_content_feed(after_id=after_id, limit=limit)
            if not fetch_result["ok"]:
                summary["error"] = fetch_result["error"] or "Unable to fetch CBT content feed."
                break

            payload = fetch_result.get("payload") or {}
            changes = payload.get("changes") or []
            if not changes:
                break

            summary["last_remote_id"] = max(summary["last_remote_id"], int(payload.get("next_after_id") or after_id))
            all_changes.extend(changes)
            after_id = int(payload.get("next_after_id") or after_id)
            if not payload.get("has_more", False):
                break

        if all_changes:
            apply_result = apply_cbt_content_changes(changes=all_changes)
            summary["applied"] = int(apply_result.get("applied") or 0)
            summary["blocked"] = int(apply_result.get("blocked") or 0)
            if apply_result.get("errors"):
                summary["error"] = (apply_result.get("errors") or [""])[0]

        SyncPullCursor.objects.update_or_create(
            stream=SyncContentStream.CBT_CONTENT,
            defaults={
                "last_remote_id": summary["last_remote_id"],
                "last_pull_at": timezone.now(),
                "last_success_at": timezone.now(),
                "last_error": summary["error"],
                "metadata": {
                    "forced_replay": True,
                    "applied": summary["applied"],
                    "blocked": summary["blocked"],
                    "pages": summary["pages"],
                },
            },
        )
        return summary
