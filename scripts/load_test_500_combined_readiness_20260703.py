"""Exercise the live combined readiness CBT with 500 concurrent candidates.

The script creates isolated LOADTEST accounts, starts real attempts, performs
question-page, heartbeat, and answer-save requests through nginx, then removes
all generated accounts, attempts, sessions, and enrollments.
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.sessions.models import Session
from django.test import Client
from django.utils import timezone

from apps.accounts.constants import ROLE_STUDENT
from apps.accounts.models import Role, StudentProfile, User
from apps.academics.models import StudentClassEnrollment
from apps.cbt.models import Exam, ExamAttempt
from apps.cbt.services import get_or_start_attempt


CANDIDATE_COUNT = int(os.getenv("CBT_LOAD_CANDIDATES", "500"))
MAX_WORKERS = int(os.getenv("CBT_LOAD_CONCURRENCY", "500"))
INCLUDE_INITIAL_PAGE = os.getenv("CBT_LOAD_INCLUDE_INITIAL_PAGE", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
REQUEST_TIMEOUT = int(os.getenv("CBT_LOAD_TIMEOUT_SECONDS", "45"))
PREFIX = "loadtest-ready-20260703-"
EXAM_IDS = {
    "JS1": 1187,
    "JS2": 1188,
    "SS1": 1189,
    "SS2": 1190,
}


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[position]


def https_request(*, session_key, method, path, body=None, headers=None):
    started = time.perf_counter()
    connection = http.client.HTTPSConnection(
        "nginx",
        443,
        timeout=REQUEST_TIMEOUT,
        context=ssl._create_unverified_context(),
    )
    request_headers = {
        "Host": "cbt.ndgakuje.org",
        "Cookie": f"sessionid={session_key}",
        "User-Agent": "NDGA-500-Candidate-Readiness/20260703",
        "Accept": "application/json,text/html",
    }
    request_headers.update(headers or {})
    try:
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        response.read()
        return response.status, (time.perf_counter() - started) * 1000
    except Exception:
        return 0, (time.perf_counter() - started) * 1000
    finally:
        connection.close()


def candidate_cycle(row):
    attempt_id = row["attempt_id"]
    session_key = row["session_key"]
    option_id = row["option_id"]
    tab_token = f"load-{attempt_id}"
    measurements = []

    if INCLUDE_INITIAL_PAGE:
        status, elapsed = https_request(
            session_key=session_key,
            method="GET",
            path=f"/cbt/attempts/{attempt_id}/run/?q=1",
        )
        measurements.append(("question", status, elapsed))
        if status != 200:
            return measurements

    payload = json.dumps(
        {
            "tab_token": tab_token,
            "question_index": 1,
            "visibility": "visible",
        }
    )
    status, elapsed = https_request(
        session_key=session_key,
        method="POST",
        path=f"/cbt/attempts/{attempt_id}/heartbeat/",
        body=payload,
        headers={"Content-Type": "application/json"},
    )
    measurements.append(("heartbeat", status, elapsed))

    form = f"q=1&action=save_stay&selected_options={option_id}"
    status, elapsed = https_request(
        session_key=session_key,
        method="POST",
        path=f"/cbt/attempts/{attempt_id}/run/?q=1",
        body=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    measurements.append(("answer_save", status, elapsed))
    return measurements


def run():
    User.objects.filter(username__startswith=PREFIX).delete()
    role = Role.objects.get(code=ROLE_STUDENT)
    exams = {
        code: Exam.objects.select_related("academic_class").get(pk=exam_id)
        for code, exam_id in EXAM_IDS.items()
    }
    for exam in exams.values():
        if exam.status != "ACTIVE":
            raise RuntimeError(f"Readiness exam {exam.id} is not active.")
        if not (exam.schedule_start <= timezone.now() <= exam.schedule_end):
            raise RuntimeError(f"Readiness exam {exam.id} is outside today's window.")

    users = [
        User(
            username=f"{PREFIX}{index:04d}",
            primary_role=role,
            is_active=True,
            must_change_password=False,
        )
        for index in range(1, CANDIDATE_COUNT + 1)
    ]
    User.objects.bulk_create(users, batch_size=200)
    users = list(
        User.objects.filter(username__startswith=PREFIX).order_by("username")
    )
    StudentProfile.objects.bulk_create(
        [
            StudentProfile(
                user=user,
                student_number=f"LOADTEST/{index:04d}",
            )
            for index, user in enumerate(users, start=1)
        ],
        batch_size=200,
    )
    class_codes = list(EXAM_IDS)
    enrollments = []
    assigned = []
    for index, user in enumerate(users):
        code = class_codes[index % len(class_codes)]
        exam = exams[code]
        enrollments.append(
            StudentClassEnrollment(
                student=user,
                academic_class=exam.academic_class,
                session=exam.session,
                is_active=True,
            )
        )
        assigned.append((user, exam))
    StudentClassEnrollment.objects.bulk_create(enrollments, batch_size=200)

    session_keys = []
    attempt_ids = []
    rows = []
    try:
        for user, exam in assigned:
            attempt, _ = get_or_start_attempt(student=user, exam=exam)
            first_answer = (
                attempt.answers.select_related("exam_question__question")
                .prefetch_related("exam_question__question__options")
                .order_by("exam_question__sort_order")
                .first()
            )
            option = first_answer.exam_question.question.options.order_by(
                "sort_order"
            ).first()
            client = Client(HTTP_HOST="cbt.ndgakuje.org")
            client.force_login(user)
            session_key = client.session.session_key
            session_keys.append(session_key)
            attempt_ids.append(attempt.id)
            rows.append(
                {
                    "session_key": session_key,
                    "attempt_id": attempt.id,
                    "option_id": option.id,
                }
            )

        started = time.perf_counter()
        all_measurements = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = [pool.submit(candidate_cycle, row) for row in rows]
            for future in as_completed(futures):
                all_measurements.extend(future.result())
        duration = time.perf_counter() - started

        status_counts = {}
        operation_counts = {}
        latencies = []
        failures = []
        for operation, status, elapsed in all_measurements:
            status_counts[status] = status_counts.get(status, 0) + 1
            operation_counts.setdefault(operation, {})
            operation_counts[operation][status] = (
                operation_counts[operation].get(status, 0) + 1
            )
            latencies.append(elapsed)
            if status != 200:
                failures.append((operation, status))
        result = {
            "candidates": len(rows),
            "requests": len(all_measurements),
            "success_200": status_counts.get(200, 0),
            "failures": len(failures),
            "status_counts": status_counts,
            "operations": operation_counts,
            "elapsed_seconds": round(duration, 2),
            "requests_per_second": round(len(all_measurements) / duration, 2),
            "median_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(percentile(latencies, 0.95), 2),
            "p99_ms": round(percentile(latencies, 0.99), 2),
            "max_ms": round(max(latencies), 2),
        }
        print(result)
        if failures:
            raise RuntimeError(f"Load test had {len(failures)} failed requests.")
    finally:
        Session.objects.filter(session_key__in=session_keys).delete()
        ExamAttempt.objects.filter(id__in=attempt_ids).delete()
        User.objects.filter(username__startswith=PREFIX).delete()


if __name__ == "__main__":
    run()
