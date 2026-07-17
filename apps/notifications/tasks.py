from celery import shared_task
from django.conf import settings

from apps.notifications.services import dispatch_birthday_wishes


def _cloud_birthday_jobs_enabled():
    if not getattr(settings, "BIRTHDAY_WISHES_ENABLED", False):
        return False
    return (getattr(settings, "SYNC_NODE_ROLE", "CLOUD") or "CLOUD").strip().upper() == "CLOUD"


@shared_task(name="notifications.send_daily_birthday_wishes")
def send_daily_birthday_wishes():
    if not _cloud_birthday_jobs_enabled():
        return {"skipped": True, "reason": "Birthday automation is paused or not running on cloud."}
    return dispatch_birthday_wishes()


@shared_task(name="notifications.send_birthday_catchup_wishes")
def send_birthday_catchup_wishes():
    if not _cloud_birthday_jobs_enabled():
        return {"skipped": True, "reason": "Birthday automation is paused or not running on cloud."}
    return dispatch_birthday_wishes(catchup=True)
