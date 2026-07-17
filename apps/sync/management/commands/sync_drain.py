from __future__ import annotations

from time import sleep

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from apps.sync.content_sync import pull_cbt_content_updates
from apps.sync.models import SyncQueue, SyncQueueStatus
from apps.sync.services import pull_remote_outbox_updates, process_sync_queue_batch


class Command(BaseCommand):
    help = "Drain sync queues manually in controlled batches."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--loops", type=int, default=25)
        parser.add_argument("--sleep-seconds", type=float, default=0.0)
        parser.add_argument("--reset-failed", action="store_true")
        parser.add_argument("--include-pull", action="store_true")

    def handle(self, *args, **options):
        limit = max(int(options["limit"]), 1)
        loops = max(int(options["loops"]), 1)
        sleep_seconds = max(float(options["sleep_seconds"]), 0.0)
        include_pull = bool(options["include_pull"])

        if options["reset_failed"]:
            reset_count = SyncQueue.objects.filter(status=SyncQueueStatus.FAILED).update(
                status=SyncQueueStatus.RETRY,
                next_retry_at=timezone.now(),
                last_error="",
            )
            self.stdout.write(f"RESET_FAILED {reset_count}")

        for index in range(1, loops + 1):
            push_summary = process_sync_queue_batch(limit=limit)
            pull_outbox_summary = {"triggered": False, "applied": 0, "duplicates": 0, "blocked": 0}
            pull_content_summary = {"triggered": False, "applied": 0, "blocked": 0}

            if include_pull:
                pull_outbox_summary = pull_remote_outbox_updates(limit=limit, max_pages=1)
                pull_content_summary = pull_cbt_content_updates(limit=limit, max_pages=1)

            counts = {
                row["status"]: row["count"]
                for row in SyncQueue.objects.values("status").annotate(count=Count("id"))
            }
            self.stdout.write(
                "LOOP {loop} PUSH claimed={claimed} synced={synced} retry={retry} failed={failed} conflict={conflict} "
                "PULL_OUTBOX applied={outbox_applied} blocked={outbox_blocked} "
                "PULL_CONTENT applied={content_applied} blocked={content_blocked} "
                "COUNTS pending={pending} retry_count={retry_count} failed_count={failed_count} synced_count={synced_count}".format(
                    loop=index,
                    claimed=push_summary.get("claimed", 0),
                    synced=push_summary.get("synced", 0),
                    retry=push_summary.get("retry", 0),
                    failed=push_summary.get("failed", 0),
                    conflict=push_summary.get("conflict", 0),
                    outbox_applied=pull_outbox_summary.get("applied", 0),
                    outbox_blocked=pull_outbox_summary.get("blocked", 0),
                    content_applied=pull_content_summary.get("applied", 0),
                    content_blocked=pull_content_summary.get("blocked", 0),
                    pending=counts.get(SyncQueueStatus.PENDING, 0),
                    retry_count=counts.get(SyncQueueStatus.RETRY, 0),
                    failed_count=counts.get(SyncQueueStatus.FAILED, 0),
                    synced_count=counts.get(SyncQueueStatus.SYNCED, 0),
                )
            )

            nothing_pushed = push_summary.get("claimed", 0) == 0
            nothing_pulled = (
                not include_pull
                or (
                    pull_outbox_summary.get("applied", 0) == 0
                    and pull_outbox_summary.get("blocked", 0) == 0
                    and pull_content_summary.get("applied", 0) == 0
                    and pull_content_summary.get("blocked", 0) == 0
                )
            )
            if nothing_pushed and nothing_pulled:
                self.stdout.write("SYNC_DRAIN_COMPLETE")
                return

            if sleep_seconds:
                sleep(sleep_seconds)

        self.stdout.write("SYNC_DRAIN_STOPPED_AT_LOOP_LIMIT")
