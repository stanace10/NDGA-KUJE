"""Create the additional exam-only languages and enrol every eligible student.

Chinese and Sign Language apply to JS1, JS2, SS1, and SS2.
German Language applies to JS1 and JS2 only.

Run without ``--apply`` for a read-only preview.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django

django.setup()

from django.db import transaction

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
    Term,
)


SESSION_NAME = "2025/2026"
TERM_NAME = "THIRD"
SUBJECT_LEVELS = {
    ("CHN", "Chinese"): ("JS1", "JS2", "SS1", "SS2"),
    ("SGL", "Sign Language"): ("JS1", "JS2", "SS1", "SS2"),
    ("GER", "German Language"): ("JS1", "JS2"),
}


def run(*, apply: bool) -> None:
    session = AcademicSession.objects.get(name=SESSION_NAME)
    term = Term.objects.get(session=session, name=TERM_NAME)
    planned = []

    with transaction.atomic():
        for (code, name), level_codes in SUBJECT_LEVELS.items():
            subject = Subject.objects.filter(code=code).first() or Subject.objects.filter(name__iexact=name).first()
            if subject is None:
                subject = Subject(code=code, name=name, category=SubjectCategory.GENERAL, is_active=True)
                subject.full_clean()
                subject.save()
                planned.append(f"created subject {code} - {name}")
            else:
                changed = []
                if subject.code != code:
                    subject.code = code
                    changed.append("code")
                if subject.name != name:
                    subject.name = name
                    changed.append("name")
                if not subject.is_active:
                    subject.is_active = True
                    changed.append("is_active")
                if changed:
                    subject.full_clean()
                    subject.save(update_fields=[*changed, "updated_at"])
                    planned.append(f"updated subject {code} ({', '.join(changed)})")

            for level_code in level_codes:
                academic_class = AcademicClass.objects.get(code=level_code, base_class__isnull=True)
                mapping, mapping_created = ClassSubject.objects.get_or_create(
                    academic_class=academic_class,
                    subject=subject,
                    defaults={"is_active": True},
                )
                if mapping_created:
                    planned.append(f"mapped {subject.code} to {level_code}")
                elif not mapping.is_active:
                    mapping.is_active = True
                    mapping.save(update_fields=["is_active", "updated_at"])
                    planned.append(f"reactivated {subject.code} mapping for {level_code}")

                student_ids = StudentClassEnrollment.objects.filter(
                    session=session,
                    academic_class_id__in=academic_class.cohort_class_ids(),
                    is_active=True,
                ).values_list("student_id", flat=True)
                for student_id in student_ids:
                    enrollment, enrollment_created = StudentSubjectEnrollment.objects.get_or_create(
                        student_id=student_id,
                        subject=subject,
                        session=session,
                        defaults={"is_active": True},
                    )
                    if enrollment_created:
                        planned.append(f"enrolled student {student_id} in {subject.code}")
                    elif not enrollment.is_active:
                        enrollment.is_active = True
                        enrollment.save(update_fields=["is_active", "updated_at"])
                        planned.append(f"reactivated student {student_id} in {subject.code}")

        if not apply:
            transaction.set_rollback(True)

    mode = "APPLIED" if apply else "PREVIEW"
    print(f"{mode}: {len(planned)} changes")
    for row in planned:
        print(f"- {row}")

    for (code, name), level_codes in SUBJECT_LEVELS.items():
        subject = Subject.objects.filter(code=code).first()
        if not subject:
            print(f"{code}: would cover {', '.join(level_codes)}")
            continue
        enrolled = StudentSubjectEnrollment.objects.filter(subject=subject, session=session, is_active=True).count()
        teacher_count = TeacherSubjectAssignment.objects.filter(
            subject=subject,
            session=session,
            term=term,
            is_active=True,
        ).count()
        print(f"{code} {name}: {enrolled} active students; {teacher_count} teacher assignments")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Commit the changes.")
    args = parser.parse_args()
    run(apply=args.apply)
