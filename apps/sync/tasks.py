from celery import shared_task

from apps.sync.content_sync import pull_cbt_content_updates
from apps.sync.services import process_sync_queue_batch, pull_remote_outbox_updates


@shared_task(name="sync.process_queue_batch")
def process_queue_batch_task(limit=100):
    return process_sync_queue_batch(limit=limit)


@shared_task(name="sync.pull_remote_outbox")
def pull_remote_outbox_task(limit=None, max_pages=None):
    return pull_remote_outbox_updates(limit=limit, max_pages=max_pages)


@shared_task(name="sync.pull_cbt_content")
def pull_cbt_content_task(limit=None, max_pages=None):
    return pull_cbt_content_updates(limit=limit, max_pages=max_pages)
