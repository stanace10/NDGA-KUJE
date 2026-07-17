from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.cbt.models import (
    CBTExamStatus,
    CBTQuestionType,
    CBTWritebackTarget,
    Exam,
    ExamBlueprint,
    ExamQuestion,
)


SOURCE_TITLE = "MON 8:00-10:00 SS3 Mathematics Mock Examination"
THEORY_TITLE = "MON 8:00-9:30 SS3 Mathematics Theory Paper"
OBJECTIVE_TITLE = "SS3 Mathematics Objective Paper"

THEORY_DESCRIPTION = "MOCK EXAMINATION 2026/2027 CLASS: SS3 SUBJECT: MATHEMATICS THEORY PAPER"
OBJECTIVE_DESCRIPTION = "MOCK EXAMINATION 2026/2027 CLASS: SS3 SUBJECT: MATHEMATICS OBJECTIVE PAPER"

THEORY_INSTRUCTIONS = (
    "This is the SS3 Mathematics theory paper. Answer only the theory questions shown. "
    "Timer is 80 minutes. Exam window closes at 9:30 AM WAT on Monday, March 23, 2026."
)
OBJECTIVE_INSTRUCTIONS = (
    "This is the SS3 Mathematics objective paper. Activate this paper separately after the theory paper."
)

OBJECTIVE_TYPES = {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}


def _copy_exam_rows(target_exam, rows):
    ExamQuestion.objects.filter(exam=target_exam).delete()
    for sort_order, row in enumerate(rows, start=1):
        ExamQuestion.objects.create(
            exam=target_exam,
            question=row.question,
            sort_order=sort_order,
            marks=row.marks,
        )


def _configure_theory_exam(target_exam, *, row_count):
    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=target_exam)
    blueprint.duration_minutes = 80
    blueprint.max_attempts = 1
    # Preserve theory question order for a WAEC-style paper.
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = THEORY_INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-MTH-MOCK-THEORY",
        "flow_type": "THEORY_ONLY",
        "objective_count": 0,
        "theory_count": row_count,
        "theory_response_mode": "PAPER",
        "objective_target_max": "0.00",
        "theory_target_max": "60.00",
    }
    blueprint.passing_score = 0
    blueprint.objective_writeback_target = CBTWritebackTarget.NONE
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.THEORY
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()


def _configure_objective_exam(target_exam, *, row_count):
    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=target_exam)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = OBJECTIVE_INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-MTH-MOCK-OBJECTIVE",
        "flow_type": "OBJECTIVE_ONLY",
        "objective_count": row_count,
        "theory_count": 0,
        "objective_target_max": "40.00",
        "theory_target_max": "0.00",
    }
    blueprint.passing_score = 0
    blueprint.objective_writeback_target = CBTWritebackTarget.OBJECTIVE
    blueprint.theory_enabled = False
    blueprint.theory_writeback_target = CBTWritebackTarget.NONE
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()


@transaction.atomic
def main():
    source_exam = Exam.objects.get(title=SOURCE_TITLE)

    if source_exam.attempts.exists():
        raise RuntimeError(f"Source exam {source_exam.id} already has attempts. Refusing to split a live-attempt paper.")

    theory_rows = [
        row
        for row in source_exam.exam_questions.select_related("question").order_by("sort_order")
        if row.question.question_type not in OBJECTIVE_TYPES
    ]
    objective_rows = [
        row
        for row in source_exam.exam_questions.select_related("question").order_by("sort_order")
        if row.question.question_type in OBJECTIVE_TYPES
    ]

    if not theory_rows:
        raise RuntimeError("No theory rows found in the source exam.")
    if not objective_rows:
        raise RuntimeError("No objective rows found in the source exam.")

    lagos = ZoneInfo("Africa/Lagos")
    theory_start = datetime(2026, 3, 23, 8, 0, tzinfo=lagos)
    theory_end = datetime(2026, 3, 23, 9, 30, tzinfo=lagos)

    dean_user = source_exam.dean_reviewed_by or User.objects.get(username="principal@ndgakuje.org")
    it_user = source_exam.activated_by or User.objects.get(username="admin@ndgakuje.org")

    theory_exam, _ = Exam.objects.get_or_create(
        title=THEORY_TITLE,
        subject=source_exam.subject,
        academic_class=source_exam.academic_class,
        session=source_exam.session,
        term=source_exam.term,
        defaults={"created_by": source_exam.created_by},
    )
    if theory_exam.attempts.exists():
        raise RuntimeError(f"Theory exam {theory_exam.id} already has attempts. Refusing to overwrite it.")
    theory_exam.description = THEORY_DESCRIPTION
    theory_exam.exam_type = source_exam.exam_type
    theory_exam.status = CBTExamStatus.ACTIVE
    theory_exam.created_by = source_exam.created_by
    theory_exam.assignment = source_exam.assignment
    theory_exam.question_bank = source_exam.question_bank
    theory_exam.dean_reviewed_by = dean_user
    theory_exam.dean_reviewed_at = source_exam.dean_reviewed_at or timezone.now()
    theory_exam.dean_review_comment = "Split from the combined SS3 mathematics mock paper for theory-first delivery."
    theory_exam.activated_by = it_user
    theory_exam.activated_at = timezone.now()
    theory_exam.activation_comment = "Theory-only paper scheduled for 8:00 AM - 9:30 AM WAT on March 23, 2026."
    theory_exam.schedule_start = theory_start
    theory_exam.schedule_end = theory_end
    theory_exam.is_time_based = True
    theory_exam.open_now = False
    theory_exam.is_free_test = False
    theory_exam.timer_is_paused = False
    theory_exam.save()
    _copy_exam_rows(theory_exam, theory_rows)
    _configure_theory_exam(theory_exam, row_count=len(theory_rows))

    objective_exam, _ = Exam.objects.get_or_create(
        title=OBJECTIVE_TITLE,
        subject=source_exam.subject,
        academic_class=source_exam.academic_class,
        session=source_exam.session,
        term=source_exam.term,
        defaults={"created_by": source_exam.created_by},
    )
    if objective_exam.attempts.exists():
        raise RuntimeError(f"Objective exam {objective_exam.id} already has attempts. Refusing to overwrite it.")
    objective_exam.description = OBJECTIVE_DESCRIPTION
    objective_exam.exam_type = source_exam.exam_type
    objective_exam.status = CBTExamStatus.APPROVED
    objective_exam.created_by = source_exam.created_by
    objective_exam.assignment = source_exam.assignment
    objective_exam.question_bank = source_exam.question_bank
    objective_exam.dean_reviewed_by = dean_user
    objective_exam.dean_reviewed_at = source_exam.dean_reviewed_at or timezone.now()
    objective_exam.dean_review_comment = "Prepared from the combined SS3 mathematics mock paper for later objective activation."
    objective_exam.activated_by = None
    objective_exam.activated_at = None
    objective_exam.activation_comment = ""
    objective_exam.schedule_start = None
    objective_exam.schedule_end = None
    objective_exam.is_time_based = True
    objective_exam.open_now = False
    objective_exam.is_free_test = False
    objective_exam.timer_is_paused = False
    objective_exam.save()
    _copy_exam_rows(objective_exam, objective_rows)
    _configure_objective_exam(objective_exam, row_count=len(objective_rows))

    source_exam.status = CBTExamStatus.CLOSED
    source_exam.open_now = False
    source_exam.activation_comment = (
        (source_exam.activation_comment or "").strip() + " Split into separate theory and objective papers on March 23, 2026."
    ).strip()
    source_exam.save(update_fields=["status", "open_now", "activation_comment", "updated_at"])

    print(
        {
            "source_exam_id": source_exam.id,
            "source_status": source_exam.status,
            "theory_exam_id": theory_exam.id,
            "theory_title": theory_exam.title,
            "theory_status": theory_exam.status,
            "theory_start": theory_exam.schedule_start.isoformat() if theory_exam.schedule_start else "",
            "theory_end": theory_exam.schedule_end.isoformat() if theory_exam.schedule_end else "",
            "theory_duration": theory_exam.blueprint.duration_minutes,
            "theory_rows": len(theory_rows),
            "objective_exam_id": objective_exam.id,
            "objective_title": objective_exam.title,
            "objective_status": objective_exam.status,
            "objective_duration": objective_exam.blueprint.duration_minutes,
            "objective_rows": len(objective_rows),
        }
    )


main()
