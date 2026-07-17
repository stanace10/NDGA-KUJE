"""One-shot authenticated 500-request LAN readiness test; removes test sessions."""

from __future__ import annotations

import http.client
import os
import ssl
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from django.contrib.sessions.models import Session
from django.test import Client

from apps.academics.models import AcademicSession, StudentClassEnrollment


CONCURRENCY = int(os.getenv("CBT_LOAD_CONCURRENCY", "500"))


def request_once(session_key):
    started = time.perf_counter()
    connection = http.client.HTTPSConnection(
        "nginx",
        443,
        timeout=30,
        context=ssl._create_unverified_context(),
    )
    try:
        connection.request(
            "GET",
            "/cbt/exams/available/",
            headers={
                "Host": "cbt.ndgakuje.org",
                "Cookie": f"sessionid={session_key}",
                "User-Agent": "NDGA-SS2-JAMB-500-Readiness-Test/20260701",
            },
        )
        response = connection.getresponse()
        response.read()
        return response.status, (time.perf_counter() - started) * 1000
    except Exception:
        return 0, (time.perf_counter() - started) * 1000
    finally:
        connection.close()


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0
    index = min(len(ordered) - 1, max(0, int(len(ordered) * fraction) - 1))
    return ordered[index]


def run():
    session = AcademicSession.objects.get(name="2025/2026")
    students = [
        row.student
        for row in StudentClassEnrollment.objects.filter(
            academic_class__code__in=["SS2 BLUE", "SS2 GOLD"],
            session=session,
            is_active=True,
            student__is_active=True,
        )
        .select_related("student")
        .order_by("student_id")
    ]
    keys = []
    try:
        for student in students:
            client = Client(HTTP_HOST="cbt.ndgakuje.org")
            client.force_login(student)
            keys.append(client.session.session_key)
        started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            futures = [
                pool.submit(request_once, keys[index % len(keys)])
                for index in range(CONCURRENCY)
            ]
            results = [future.result() for future in as_completed(futures)]
        elapsed = time.perf_counter() - started
        statuses = {}
        for status, _milliseconds in results:
            statuses[status] = statuses.get(status, 0) + 1
        timings = [milliseconds for _status, milliseconds in results]
        print(
            {
                "concurrent_requests": CONCURRENCY,
                "candidate_sessions": len(keys),
                "success_200": statuses.get(200, 0),
                "failures": CONCURRENCY - statuses.get(200, 0),
                "status_counts": statuses,
                "elapsed_seconds": round(elapsed, 2),
                "requests_per_second": round(CONCURRENCY / elapsed, 2),
                "median_ms": round(statistics.median(timings), 2),
                "p95_ms": round(percentile(timings, 0.95), 2),
                "p99_ms": round(percentile(timings, 0.99), 2),
                "max_ms": round(max(timings), 2),
            }
        )
    finally:
        if keys:
            Session.objects.filter(session_key__in=keys).delete()


if __name__ == "__main__":
    run()
