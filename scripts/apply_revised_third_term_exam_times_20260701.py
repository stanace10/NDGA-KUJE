"""Apply the revised July 2026 examination windows without touching questions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from django.db import transaction
from django.utils import timezone

from apps.cbt.models import Exam


IMPORT_TAG = "THIRD_TERM_EXAM_20260629"
LONG_SUBJECTS = {"ENG", "MTH", "FTM"}
SLOTS = {
    7: ((7, 30), (9, 30)),
    9: ((10, 0), (11, 30)),
    12: ((12, 30), (14, 0)),
}


def run():
    rows = []
    with transaction.atomic():
        exams = (
            Exam.objects.filter(description__contains=IMPORT_TAG)
            .select_related("subject", "academic_class", "blueprint")
            .order_by("schedule_start", "academic_class__code", "subject__code")
        )
        for exam in exams:
            local_start = timezone.localtime(exam.schedule_start)
            slot = SLOTS.get(local_start.hour)
            if slot is None:
                rows.append((exam.id, "SKIPPED", local_start.isoformat()))
                continue
            start_parts, end_parts = slot
            new_start = local_start.replace(
                hour=start_parts[0],
                minute=start_parts[1],
                second=0,
                microsecond=0,
            )
            new_end = local_start.replace(
                hour=end_parts[0],
                minute=end_parts[1],
                second=0,
                microsecond=0,
            )
            exam.schedule_start = new_start
            exam.schedule_end = new_end
            exam.is_time_based = True
            exam.open_now = False
            exam.save(
                update_fields=[
                    "schedule_start",
                    "schedule_end",
                    "is_time_based",
                    "open_now",
                    "updated_at",
                ]
            )
            duration = (
                120
                if exam.academic_class.code.startswith("SS")
                and exam.subject.code in LONG_SUBJECTS
                else 90
            )
            exam.blueprint.duration_minutes = duration
            exam.blueprint.save(update_fields=["duration_minutes", "updated_at"])
            rows.append(
                (
                    exam.id,
                    exam.academic_class.code,
                    exam.subject.code,
                    f"{new_start:%Y-%m-%d %H:%M}-{new_end:%H:%M}",
                    duration,
                )
            )
    print(
        {
            "updated": sum(1 for row in rows if len(row) == 5),
            "skipped": sum(1 for row in rows if len(row) != 5),
        }
    )
    for row in rows:
        print(row)


if __name__ == "__main__":
    run()
