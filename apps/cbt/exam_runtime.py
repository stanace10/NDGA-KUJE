from __future__ import annotations

import json
import logging
import time
from functools import lru_cache

import redis
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

STATE_TTL_SECONDS = 60 * 60 * 24 * 2


@lru_cache(maxsize=1)
def state_client():
    return redis.Redis.from_url(
        settings.REDIS_STATE_URL,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=3,
        health_check_interval=30,
    )


def _key(attempt_id, suffix):
    return f"cbt:attempt:{int(attempt_id)}:{suffix}"


def _normalize_ids(values):
    result = []
    for value in values or []:
        try:
            normalized = int(value)
        except (TypeError, ValueError):
            continue
        if normalized > 0 and normalized not in result:
            result.append(normalized)
    return result


def live_answer_map(attempt_id):
    raw = state_client().hgetall(_key(attempt_id, "answers"))
    result = {}
    for exam_question_id, payload in raw.items():
        try:
            result[int(exam_question_id)] = set(_normalize_ids(json.loads(payload)))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return result


def overlay_live_answers(attempt, answers):
    try:
        live = live_answer_map(attempt.id)
    except redis.RedisError:
        logger.exception("Redis state unavailable while reading attempt %s", attempt.id)
        return answers
    if not live:
        return answers
    for answer in answers:
        selected = live.get(answer.exam_question_id)
        if selected is not None:
            answer._selected_option_ids = selected
    return answers


def save_live_objective_answer(*, attempt_id, exam_question_id, selected_option_ids):
    client = state_client()
    selected_ids = _normalize_ids(selected_option_ids)
    answers_key = _key(attempt_id, "answers")
    dirty_key = _key(attempt_id, "dirty")
    meta_key = _key(attempt_id, "meta")
    now = str(time.time())
    pipe = client.pipeline(transaction=True)
    pipe.hset(answers_key, str(int(exam_question_id)), json.dumps(selected_ids, separators=(",", ":")))
    pipe.sadd(dirty_key, str(int(exam_question_id)))
    pipe.hincrby(meta_key, "version", 1)
    pipe.hset(meta_key, mapping={"last_activity": now})
    for key in (answers_key, dirty_key, meta_key):
        pipe.expire(key, STATE_TTL_SECONDS)
    pipe.execute()
    _schedule_flush(attempt_id)
    return selected_ids


def _schedule_flush(attempt_id, *, countdown=8):
    schedule_key = _key(attempt_id, "flush-scheduled")
    client = state_client()
    if not client.set(schedule_key, "1", nx=True, ex=max(countdown + 20, 30)):
        return False
    try:
        from apps.cbt.tasks import flush_attempt_live_state

        flush_attempt_live_state.apply_async(args=[int(attempt_id)], countdown=countdown, queue="critical")
        return True
    except Exception:
        client.delete(schedule_key)
        logger.exception("Unable to enqueue CBT live-state flush for attempt %s", attempt_id)
        return False


def flush_attempt_live_state_to_db(attempt_id):
    from apps.cbt.models import CBTAttemptStatus, ExamAttempt, ExamAttemptAnswer, Option

    client = state_client()
    dirty_key = _key(attempt_id, "dirty")
    answers_key = _key(attempt_id, "answers")
    meta_key = _key(attempt_id, "meta")
    schedule_key = _key(attempt_id, "flush-scheduled")
    dirty_ids = _normalize_ids(client.smembers(dirty_key))
    version = int(client.hget(meta_key, "version") or 0)
    if not dirty_ids:
        client.delete(schedule_key)
        return 0

    payloads = client.hmget(answers_key, [str(value) for value in dirty_ids])
    selected_by_question = {}
    for question_id, payload in zip(dirty_ids, payloads):
        try:
            selected_by_question[question_id] = _normalize_ids(json.loads(payload or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            selected_by_question[question_id] = []

    with transaction.atomic():
        attempt = ExamAttempt.objects.select_for_update().get(pk=attempt_id)
        if attempt.status not in {CBTAttemptStatus.IN_PROGRESS, CBTAttemptStatus.SUBMITTED}:
            client.delete(dirty_key, schedule_key)
            return 0
        answers = list(
            ExamAttemptAnswer.objects.select_for_update()
            .select_related("exam_question__question")
            .filter(attempt_id=attempt_id, exam_question_id__in=dirty_ids)
        )
        question_ids = {row.exam_question.question_id for row in answers}
        valid_options = {
            row.id: row.question_id
            for row in Option.objects.filter(question_id__in=question_ids).only("id", "question_id")
        }
        through = ExamAttemptAnswer.selected_options.through
        answer_ids = [row.id for row in answers]
        through.objects.filter(examattemptanswer_id__in=answer_ids).delete()
        inserts = []
        for answer in answers:
            for option_id in selected_by_question.get(answer.exam_question_id, []):
                if valid_options.get(option_id) == answer.exam_question.question_id:
                    inserts.append(through(examattemptanswer_id=answer.id, option_id=option_id))
        if inserts:
            through.objects.bulk_create(inserts, ignore_conflicts=True)
        now = timezone.now()
        ExamAttemptAnswer.objects.filter(id__in=answer_ids).update(updated_at=now)
        ExamAttempt.objects.filter(pk=attempt_id).update(last_activity_at=now, updated_at=now)

    client.delete(schedule_key)
    if int(client.hget(meta_key, "version") or 0) == version:
        client.delete(dirty_key)
    elif client.scard(dirty_key):
        _schedule_flush(attempt_id, countdown=3)
    return len(answers)


HEARTBEAT_SCRIPT = """
redis.call('HSET', KEYS[1], 'student_id', ARGV[1], 'token', ARGV[2], 'seen', ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return 1
"""


def register_live_heartbeat(*, attempt_id, student_id, tab_token):
    token = (tab_token or "").strip()[:120]
    if not token:
        return False
    result = state_client().eval(
        HEARTBEAT_SCRIPT,
        1,
        _key(attempt_id, "presence"),
        str(int(student_id)),
        token,
        str(time.time()),
        str(60 * 60 * 4),
    )
    return bool(result)


def live_presence(attempt_id):
    row = state_client().hgetall(_key(attempt_id, "presence"))
    if not row:
        return None
    try:
        seen = float(row.get("seen") or 0)
    except (TypeError, ValueError):
        seen = 0
    return {"seen": seen, "age": max(0, int(time.time() - seen)), "token": row.get("token", "")}


def clear_live_attempt(attempt_id, *, keep_answers=True):
    suffixes = ["presence", "flush-scheduled"]
    if not keep_answers:
        suffixes.extend(["answers", "dirty", "meta"])
    state_client().delete(*[_key(attempt_id, suffix) for suffix in suffixes])


def warm_exam_manifest(exam):
    from apps.cbt.models import ExamQuestion

    rows = list(
        ExamQuestion.objects.filter(exam=exam)
        .select_related("question")
        .prefetch_related("question__options")
        .order_by("sort_order", "id")
    )
    payload = [
        {
            "exam_question_id": row.id,
            "question_id": row.question_id,
            "type": row.question.question_type,
            "marks": str(row.marks),
            "option_ids": [option.id for option in row.question.options.all()],
        }
        for row in rows
    ]
    state_client().set(
        f"cbt:exam:{exam.id}:manifest",
        json.dumps(payload, separators=(",", ":")),
        ex=STATE_TTL_SECONDS,
    )
    return len(payload)
