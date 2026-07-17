from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.cbt.models import ExamAttempt
from apps.cbt.services import _get_or_create_score_row
from apps.results.models import StudentSubjectScore


def _as_decimal(value, default="0.00"):
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default).quantize(Decimal("0.01"))


class Command(BaseCommand):
    help = "Repairs teacher result rows from CBT attempt writeback metadata."

    def add_arguments(self, parser):
        parser.add_argument(
            "--exam-id",
            type=int,
            default=0,
            help="Only repair attempts for a specific exam id.",
        )
        parser.add_argument(
            "--attempt-id",
            type=int,
            default=0,
            help="Only repair a specific attempt id.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Inspect mismatches without saving repairs.",
        )
        parser.add_argument(
            "--all-attempts",
            action="store_true",
            help="Repair every attempt instead of only the latest attempt per student and exam.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        qs = ExamAttempt.objects.select_related("exam", "exam__blueprint", "student")
        if options["exam_id"]:
            qs = qs.filter(exam_id=options["exam_id"])
        if options["attempt_id"]:
            qs = qs.filter(id=options["attempt_id"])
        if not options["all_attempts"] and not options["attempt_id"]:
            latest_attempt_ids = []
            seen_pairs = set()
            for attempt_id, exam_id, student_id in qs.order_by("exam_id", "student_id", "-attempt_number", "-id").values_list(
                "id",
                "exam_id",
                "student_id",
            ):
                pair = (exam_id, student_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                latest_attempt_ids.append(attempt_id)
            qs = qs.filter(id__in=latest_attempt_ids)

        scanned = 0
        repaired = 0
        unchanged = 0
        missing_rows_created = 0
        details = []

        for attempt in qs.iterator():
            metadata = attempt.writeback_metadata or {}
            if not isinstance(metadata, dict):
                continue

            score_preexisting = StudentSubjectScore.objects.filter(
                result_sheet__academic_class=attempt.exam.academic_class,
                result_sheet__subject=attempt.exam.subject,
                result_sheet__session=attempt.exam.session,
                result_sheet__term=attempt.exam.term,
                student=attempt.student,
            ).exists()

            sheet, score = _get_or_create_score_row(attempt)
            if not score_preexisting:
                missing_rows_created += 1

            attempt_changed = False
            scanned += 1

            for metadata_key in ("objective_writeback", "theory_writeback"):
                writeback = metadata.get(metadata_key) or {}
                if not isinstance(writeback, dict) or writeback.get("skipped"):
                    continue

                field = (writeback.get("field") or "").strip()
                if field not in StudentSubjectScore.SCORE_COMPONENT_FIELDS:
                    continue

                after_value = _as_decimal(writeback.get("after", "0.00"))
                before_value = _as_decimal(getattr(score, field))

                if before_value == after_value:
                    continue

                setattr(score, field, after_value)
                score.lock_components(field)

                if metadata_key == "objective_writeback":
                    objective_auto_score = writeback.get("objective_auto_score")
                    if field == "objective":
                        score.set_breakdown_value("objective_auto", _as_decimal(objective_auto_score or attempt.objective_score))
                    elif field == "ca2":
                        score.set_breakdown_value("ca2_objective", _as_decimal(objective_auto_score or attempt.objective_score))
                    elif field in {"ca1", "ca3", "ca4"} and objective_auto_score is not None:
                        score.set_breakdown_value(f"{field}_objective", _as_decimal(objective_auto_score))
                        manual_theory = writeback.get("manual_theory_score")
                        if manual_theory is not None:
                            score.set_breakdown_value(f"{field}_theory", _as_decimal(manual_theory))

                if not options["dry_run"]:
                    score.save()

                attempt_changed = True
                repaired += 1
                if len(details) < 20:
                    details.append(
                        {
                            "attempt_id": attempt.id,
                            "student": attempt.student.username,
                            "exam": attempt.exam.title,
                            "field": field,
                            "before": str(before_value),
                            "after": str(after_value),
                            "sheet_id": sheet.id,
                            "metadata_key": metadata_key,
                        }
                    )

            if not attempt_changed:
                unchanged += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"REPAIR_SUMMARY scanned={scanned} repaired={repaired} unchanged={unchanged} "
                f"missing_rows_created={missing_rows_created} dry_run={bool(options['dry_run'])}"
            )
        )
        if details:
            for row in details:
                self.stdout.write(str(row))
