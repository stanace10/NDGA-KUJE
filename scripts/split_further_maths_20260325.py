from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)


MORNING_START = (2026, 3, 25, 10, 50)
MORNING_END = (2026, 3, 25, 12, 30)
AFTERNOON_START = (2026, 3, 25, 13, 45)
AFTERNOON_END = (2026, 3, 25, 15, 0)
MORNING_DURATION = 90
AFTERNOON_DURATION = 75

PLAN = [
    {
        "source_exam_id": 208,
        "morning_title": "WED 10:50-12:30 SS1 Further Mathematics Theory Paper",
        "afternoon_title": "WED 1:45-3:00 SS1 Further Mathematics Objective Paper",
        "morning_bank": "SS1 Further Mathematics Theory Paper 2025/2026",
        "afternoon_bank": "SS1 Further Mathematics Objective Paper 2025/2026",
        "paper_code": "SS1-FTM",
    },
    {
        "source_exam_id": 204,
        "morning_title": "WED 10:50-12:30 SS2 Further Mathematics Theory Paper",
        "afternoon_title": "WED 1:45-3:00 SS2 Further Mathematics Objective Paper",
        "morning_bank": "SS2 Further Mathematics Theory Paper 2025/2026",
        "afternoon_bank": "SS2 Further Mathematics Objective Paper 2025/2026",
        "paper_code": "SS2-FTM",
    },
    {
        "source_exam_id": 205,
        "morning_title": "WED 10:50-12:30 SS3 Further Mathematics Mock Theory Paper",
        "afternoon_title": "WED 1:45-3:00 SS3 Further Mathematics Mock Objective Paper",
        "morning_bank": "SS3 Further Mathematics Mock Theory Paper 2025/2026",
        "afternoon_bank": "SS3 Further Mathematics Mock Objective Paper 2025/2026",
        "paper_code": "SS3-FTM-MOCK",
    },
]


def clone_question(src_question, bank, teacher, subject, source_reference):
    question = Question.objects.create(
        question_bank=bank,
        created_by=teacher,
        subject=subject,
        question_type=src_question.question_type,
        stem=src_question.stem,
        rich_stem=src_question.rich_stem,
        marks=src_question.marks,
        source_reference=source_reference,
        is_active=True,
    )

    option_map = {}
    if src_question.question_type == "OBJECTIVE":
        for src_opt in src_question.options.order_by("sort_order", "id"):
            option_map[src_opt.id] = Option.objects.create(
                question=question,
                label=src_opt.label,
                option_text=src_opt.option_text,
                sort_order=src_opt.sort_order,
            )

    src_answer = CorrectAnswer.objects.filter(question=src_question).first()
    answer = CorrectAnswer.objects.create(
        question=question,
        note=(src_answer.note if src_answer else ""),
        is_finalized=(src_answer.is_finalized if src_answer else True),
    )
    if src_answer and option_map:
        for src_opt in src_answer.correct_options.all():
            mapped = option_map.get(src_opt.id)
            if mapped:
                answer.correct_options.add(mapped)

    return question


def build_exam(*, title, description, instructions, source_exam, bank_name, question_links, duration_minutes, theory_enabled, objective_target_max, theory_target_max, paper_code, it_user, dean_user, schedule_start, schedule_end):
    teacher = source_exam.created_by
    subject = source_exam.subject
    academic_class = source_exam.academic_class
    session = source_exam.session
    term = source_exam.term
    assignment = source_exam.assignment

    bank, _ = QuestionBank.objects.get_or_create(
        owner=teacher,
        name=bank_name,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={"description": description, "assignment": assignment, "is_active": True},
    )
    bank.description = description
    bank.assignment = assignment
    bank.is_active = True
    bank.save()

    exam, created = Exam.objects.get_or_create(
        title=title,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={
            "description": description,
            "exam_type": CBTExamType.EXAM,
            "status": CBTExamStatus.ACTIVE,
            "created_by": teacher,
            "assignment": assignment,
            "question_bank": bank,
            "dean_reviewed_by": dean_user,
            "dean_reviewed_at": timezone.now(),
            "dean_review_comment": "Approved after paper split.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": f"Scheduled after paper split: {title}",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts. Refusing to overwrite live content.")

    exam.description = description
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved after paper split."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = f"Scheduled after paper split: {title}"
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    ExamQuestion.objects.filter(exam=exam).delete()
    bank.questions.all().delete()

    for idx, src_link in enumerate(question_links, start=1):
        cloned = clone_question(
            src_link.question,
            bank,
            teacher,
            subject,
            f"{paper_code}-{idx:02d}",
        )
        ExamQuestion.objects.create(
            exam=exam,
            question=cloned,
            sort_order=idx,
            marks=src_link.marks,
        )

    objective_count = sum(1 for q in question_links if q.question.question_type == "OBJECTIVE")
    theory_count = len(question_links) - objective_count

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = duration_minutes
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = instructions
    blueprint.section_config = {
        "paper_code": paper_code,
        "flow_type": "OBJECTIVE_THEORY" if theory_enabled and objective_count else ("THEORY_ONLY" if theory_enabled else "OBJECTIVE_ONLY"),
        "objective_count": objective_count,
        "theory_count": theory_count,
        "objective_target_max": objective_target_max,
        "theory_target_max": theory_target_max,
    }
    blueprint.passing_score = Decimal("0.00")
    blueprint.objective_writeback_target = CBTWritebackTarget.OBJECTIVE
    blueprint.theory_enabled = theory_enabled
    blueprint.theory_writeback_target = CBTWritebackTarget.THEORY
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()

    return exam, blueprint, created


@transaction.atomic
def main():
    lagos = ZoneInfo("Africa/Lagos")
    morning_start = datetime(*MORNING_START, tzinfo=lagos)
    morning_end = datetime(*MORNING_END, tzinfo=lagos)
    afternoon_start = datetime(*AFTERNOON_START, tzinfo=lagos)
    afternoon_end = datetime(*AFTERNOON_END, tzinfo=lagos)

    it_user = User.objects.get(username="admin@ndgakuje.org")
    dean_user = User.objects.get(username="principal@ndgakuje.org")

    results = []

    for item in PLAN:
        source_exam = Exam.objects.select_related(
            "subject", "academic_class", "session", "term", "created_by", "assignment"
        ).get(id=item["source_exam_id"])

        if source_exam.attempts.filter(status="SUBMITTED").exists():
            raise RuntimeError(f"Source exam {source_exam.id} already has submitted attempts.")

        deleted_attempts = source_exam.attempts.exclude(status="SUBMITTED").delete()
        source_exam.status = CBTExamStatus.CLOSED
        source_exam.open_now = False
        source_exam.activation_comment = "Superseded after split into theory-only and objective-only papers."
        source_exam.save(update_fields=["status", "open_now", "activation_comment"])

        links = list(source_exam.exam_questions.select_related("question").order_by("sort_order", "id"))
        objective_links = [link for link in links if link.question.question_type == "OBJECTIVE"]
        theory_links = [link for link in links if link.question.question_type != "OBJECTIVE"]

        morning_exam, morning_blueprint, _ = build_exam(
            title=item["morning_title"],
            description=f"{source_exam.description} - THEORY PAPER",
            instructions=(
                "This sitting is theory only. Answer theory questions only. "
                "Timer is 90 minutes. Exam window closes at 12:30 PM WAT on Wednesday, March 25, 2026."
            ),
            source_exam=source_exam,
            bank_name=item["morning_bank"],
            question_links=theory_links,
            duration_minutes=MORNING_DURATION,
            theory_enabled=True,
            objective_target_max="0.00",
            theory_target_max="60.00",
            paper_code=f"{item['paper_code']}-TH",
            it_user=it_user,
            dean_user=dean_user,
            schedule_start=morning_start,
            schedule_end=morning_end,
        )

        afternoon_exam, afternoon_blueprint, _ = build_exam(
            title=item["afternoon_title"],
            description=f"{source_exam.description} - OBJECTIVE PAPER",
            instructions=(
                "This sitting is objective only. Answer all objective questions. "
                "Timer is 75 minutes. Exam window closes at 3:00 PM WAT on Wednesday, March 25, 2026."
            ),
            source_exam=source_exam,
            bank_name=item["afternoon_bank"],
            question_links=objective_links,
            duration_minutes=AFTERNOON_DURATION,
            theory_enabled=False,
            objective_target_max="40.00",
            theory_target_max="0.00",
            paper_code=f"{item['paper_code']}-OBJ",
            it_user=it_user,
            dean_user=dean_user,
            schedule_start=afternoon_start,
            schedule_end=afternoon_end,
        )

        results.append(
            {
                "source_exam_id": source_exam.id,
                "source_title": source_exam.title,
                "deleted_attempt_objects": deleted_attempts[0],
                "morning_exam_id": morning_exam.id,
                "morning_title": morning_exam.title,
                "morning_duration": morning_blueprint.duration_minutes,
                "morning_questions": morning_exam.exam_questions.count(),
                "afternoon_exam_id": afternoon_exam.id,
                "afternoon_title": afternoon_exam.title,
                "afternoon_duration": afternoon_blueprint.duration_minutes,
                "afternoon_questions": afternoon_exam.exam_questions.count(),
            }
        )

    print(results)


if __name__ == "__main__":
    main()
