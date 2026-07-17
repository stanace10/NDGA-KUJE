"""Repair SS2 Second Term Garment Making historical import.

The old platform PDF row is GARMENT MAKING with a full 100-point total. During
historical import those rows landed under the legacy FAS/Fashion subject, while
old CBT theory-only rows were still published under GMT/Garment Making Theory.
For SS2 Second Term reports and cumulative calculations, GMT must carry the
full imported score and the duplicate FAS sheet must not be published.
"""

from __future__ import annotations

from django.db import transaction

from apps.academics.models import AcademicClass, AcademicSession, Subject, Term
from apps.results.models import ResultSheet, ResultSheetStatus, StudentSubjectScore


SESSION_NAME = "2025/2026"
TERM_NAMES = ("FIRST", "SECOND")
CLASS_CODES = ("SS1", "SS2")
SOURCE_SUBJECT_CODE = "FAS"
TARGET_SUBJECT_CODE = "GMT"


COPY_FIELDS = [
    "ca1",
    "ca2",
    "ca3",
    "ca4",
    "class_participation",
    "objective",
    "theory",
    "total_ca",
    "total_exam",
    "grand_total",
    "grade",
    "has_override",
    "override_reason",
    "cbt_locked_fields",
    "cbt_component_breakdown",
    "override_by",
    "override_at",
]


def run():
    session = AcademicSession.objects.get(name=SESSION_NAME)
    source_subject = Subject.objects.get(code=SOURCE_SUBJECT_CODE)
    target_subject = Subject.objects.get(code=TARGET_SUBJECT_CODE)

    for term_name in TERM_NAMES:
        term = Term.objects.get(session=session, name=term_name)
        for class_code in CLASS_CODES:
            academic_class = AcademicClass.objects.get(code=class_code).instructional_class
            source_sheet = ResultSheet.objects.filter(
                session=session,
                term=term,
                academic_class=academic_class,
                subject=source_subject,
            ).first()
            if source_sheet is None or not source_sheet.student_scores.exists():
                continue
            target_sheet, _created = ResultSheet.objects.get_or_create(
                session=session,
                term=term,
                academic_class=academic_class,
                subject=target_subject,
                defaults={
                    "status": ResultSheetStatus.PUBLISHED,
                    "created_by": source_sheet.created_by,
                    "cbt_component_policies": source_sheet.cbt_component_policies,
                },
            )
            if target_sheet.status != ResultSheetStatus.PUBLISHED:
                target_sheet.status = ResultSheetStatus.PUBLISHED
                target_sheet.save(update_fields=["status", "updated_at"])

            copied = 0
            created = 0
            with transaction.atomic():
                for source_score in StudentSubjectScore.objects.filter(result_sheet=source_sheet).select_related("student"):
                    target_score, was_created = StudentSubjectScore.objects.get_or_create(
                        result_sheet=target_sheet,
                        student=source_score.student,
                    )
                    update_payload = {field: getattr(source_score, field) for field in COPY_FIELDS}
                    # Use update() deliberately: StudentSubjectScore.save() applies
                    # the current Third-Term class-participation grading model, but
                    # this is a legacy First/Second-Term historical row where the PDF
                    # already contains the exact final totals.
                    StudentSubjectScore.objects.filter(pk=target_score.pk).update(**update_payload)
                    copied += 1
                    if was_created:
                        created += 1

                if source_sheet.status == ResultSheetStatus.PUBLISHED:
                    source_sheet.status = ResultSheetStatus.DRAFT
                    source_sheet.save(update_fields=["status", "updated_at"])
                elif source_sheet.status != ResultSheetStatus.DRAFT:
                    source_sheet.status = ResultSheetStatus.DRAFT
                    source_sheet.save(update_fields=["status", "updated_at"])

            print(
                {
                    "class": class_code,
                    "term": term_name,
                    "source_sheet": source_sheet.id,
                    "target_sheet": target_sheet.id,
                    "copied_scores": copied,
                    "created_target_scores": created,
                    "source_sheet_status": source_sheet.status,
                    "target_sheet_status": target_sheet.status,
                }
            )


if __name__ == "__main__":
    run()
