from celery import shared_task


@shared_task(
    name="cbt.flush_attempt_live_state",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
    acks_late=True,
)
def flush_attempt_live_state(self, attempt_id):
    from apps.cbt.exam_runtime import flush_attempt_live_state_to_db

    return flush_attempt_live_state_to_db(attempt_id)
