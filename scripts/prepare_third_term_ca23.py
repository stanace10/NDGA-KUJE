"""Align Third Term offerings and student status with First CA evidence."""

from __future__ import annotations

import csv
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

from apps.accounts.models import StudentProfile
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    TeacherSubjectAssignment,
    Term,
)
from apps.cbt.models import Exam, ExamAttempt
from apps.results.models import StudentSubjectScore


LEVELS = ("JS1", "JS2", "SS1", "SS2")
EXCEPTIONS = {("SS2", "FSH")}
REPORT_DIR = ROOT / "exports" / "ca23-audit-20260622"


def first_ca_evidence(*, student_ids, academic_class, session, term):
    closed_ca = Exam.objects.filter(
        session=session,
        term=term,
        academic_class=academic_class,
        exam_type="CA",
        status="CLOSED",
    )
    attempted = set(
        ExamAttempt.objects.filter(student_id__in=student_ids, exam__in=closed_ca)
        .values_list("exam__subject_id", flat=True)
        .distinct()
    )
    scored = set(
        StudentSubjectScore.objects.filter(
            student_id__in=student_ids,
            result_sheet__session=session,
            result_sheet__term=term,
            result_sheet__academic_class=academic_class,
            ca1__gt=0,
        )
        .values_list("result_sheet__subject_id", flat=True)
        .distinct()
    )
    return attempted | scored


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    removed = []
    no_ca1 = []
    restored = []

    with transaction.atomic():
        for class_code in LEVELS:
            academic_class = AcademicClass.objects.get(code=class_code)
            enrollments = StudentClassEnrollment.objects.filter(
                session=session,
                academic_class__base_class=academic_class,
            ).select_related("student", "student__student_profile", "academic_class")
            student_ids = list(enrollments.values_list("student_id", flat=True))
            active_student_ids = list(
                enrollments.filter(is_active=True).values_list("student_id", flat=True)
            )
            evidence_subject_ids = first_ca_evidence(
                student_ids=student_ids,
                academic_class=academic_class,
                session=session,
                term=term,
            )
            subject_ids = set(
                TeacherSubjectAssignment.objects.filter(
                    session=session,
                    term=term,
                    academic_class=academic_class,
                    is_active=True,
                ).values_list("subject_id", flat=True)
            ) | set(
                StudentSubjectEnrollment.objects.filter(
                    session=session,
                    student_id__in=active_student_ids,
                    is_active=True,
                ).values_list("subject_id", flat=True)
            )
            for subject_id in subject_ids - evidence_subject_ids:
                subject_code = (
                    TeacherSubjectAssignment.objects.filter(subject_id=subject_id)
                    .values_list("subject__code", flat=True)
                    .first()
                    or StudentSubjectEnrollment.objects.filter(subject_id=subject_id)
                    .values_list("subject__code", flat=True)
                    .first()
                )
                if (class_code, subject_code) in EXCEPTIONS:
                    continue
                assignment_count = TeacherSubjectAssignment.objects.filter(
                    session=session,
                    term=term,
                    academic_class=academic_class,
                    subject_id=subject_id,
                    is_active=True,
                ).update(is_active=False)
                enrollment_count = StudentSubjectEnrollment.objects.filter(
                    session=session,
                    student_id__in=student_ids,
                    subject_id=subject_id,
                    is_active=True,
                ).update(is_active=False)
                exam_count = Exam.objects.filter(
                    session=session,
                    term=term,
                    academic_class=academic_class,
                    subject_id=subject_id,
                    status="ACTIVE",
                ).update(status="CLOSED", open_now=False)
                removed.append(
                    (class_code, subject_code, assignment_count, enrollment_count, exam_count)
                )

        closed_ca = Exam.objects.filter(
            session=session,
            term=term,
            exam_type="CA",
            status="CLOSED",
        )
        all_enrollments = StudentClassEnrollment.objects.filter(
            session=session,
            academic_class__base_class__code__in=LEVELS,
        ).select_related(
            "student", "student__student_profile", "academic_class__base_class"
        )
        for enrollment in all_enrollments:
            wrote = ExamAttempt.objects.filter(
                student=enrollment.student,
                exam__in=closed_ca,
            ).exists() or StudentSubjectScore.objects.filter(
                student=enrollment.student,
                result_sheet__session=session,
                result_sheet__term=term,
                ca1__gt=0,
            ).exists()
            profile = enrollment.student.student_profile
            row = (
                enrollment.academic_class.base_class.code,
                profile.student_number,
                enrollment.student.get_full_name(),
            )
            if not wrote:
                no_ca1.append(row)
            elif not enrollment.student.is_active or not enrollment.is_active:
                enrollment.student.is_active = True
                enrollment.student.save(update_fields=["is_active"])
                enrollment.is_active = True
                enrollment.save(update_fields=["is_active", "updated_at"])
                profile.lifecycle_state = StudentProfile.LifecycleState.ACTIVE
                profile.save(update_fields=["lifecycle_state", "updated_at"])
                restored.append(row)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with (REPORT_DIR / "students_without_ca1.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(("class", "admission_number", "student"))
        writer.writerows(no_ca1)
    print("REMOVED", removed)
    print("RESTORED", restored)
    print("NO_CA1", no_ca1)


if __name__ == "__main__":
    main()
