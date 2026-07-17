from celery import shared_task

from apps.elections.services import auto_close_due_elections


@shared_task(name="elections.auto_close_due")
def auto_close_due_elections_task():
    closed_ids = auto_close_due_elections()
    return {"closed_count": len(closed_ids), "closed_ids": closed_ids}
