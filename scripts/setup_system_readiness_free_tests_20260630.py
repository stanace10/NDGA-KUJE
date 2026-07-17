"""Create the four non-recording CBT system-readiness Free Tests.

Run:
    python manage.py shell < scripts/setup_system_readiness_free_tests_20260630.py
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTAttemptStatus,
    CBTQuestionType,
    CBTWritebackTarget,
    Exam,
    ExamAttempt,
    ExamAttemptAnswer,
    ExamBlueprint,
    ExamQuestion,
    Question,
)
from apps.cbt.workflow import it_activate_exam
from apps.results.utils import current_session_term


SOURCE_EXAMS = {
    "JS1": 1029,
    "JS2": 1031,
    "SS1": 988,
    "SS2": 1005,
}
QUESTION_COUNT = 20


THEORY_PROMPTS = {
    "JS1": (
        "Write a short paragraph of four complete sentences explaining how a student "
        "should prepare before starting a computer-based examination."
    ),
    "JS2": (
        "State three rules for responsible use of a school computer and explain why "
        "one of the rules is important."
    ),
    "SS1": (
        "In a well-organised paragraph, explain two benefits of computer-based testing "
        "and one challenge a school should prepare for."
    ),
    "SS2": (
        "Write a concise response describing three practical steps that make a "
        "computer-based examination secure, fair, and reliable."
    ),
}


def ensure_demo_theory(exam, actor):
    class_code = exam.academic_class.code
    source_reference = f"NDGA-READINESS-THEORY-{class_code}-2026"
    question, _ = Question.objects.get_or_create(
        subject=exam.subject,
        source_reference=source_reference,
        defaults={
            "question_bank": exam.question_bank,
            "created_by": actor,
            "question_type": CBTQuestionType.SHORT_ANSWER,
            "stem": THEORY_PROMPTS[class_code],
            "topic": "Theory Demonstration",
            "marks": Decimal("5.00"),
            "is_active": True,
        },
    )
    if not exam.exam_questions.filter(question=question).exists():
        last_order = exam.exam_questions.aggregate(value=Max("sort_order"))["value"] or 0
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=last_order + 1,
            marks=Decimal("5.00"),
        )

    blueprint = exam.blueprint
    config = dict(blueprint.section_config or {})
    config.update(
        {
            "question_count": QUESTION_COUNT + 1,
            "objective_count": QUESTION_COUNT,
            "theory_count": 1,
            "theory_response_mode": "TYPING",
            "theory_target_max": "5.00",
            "theory_instructions": (
                "Answer the theory demonstration in the text box. Use complete "
                "sentences, then submit when you are satisfied."
            ),
            "review_seconds": 30,
        }
    )
    blueprint.section_config = config
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.NONE
    blueprint.instructions = (
        "Answer the 20 objective questions, then select Finish Objective to open "
        "the typed theory demonstration. This free test never affects school results."
    )
    blueprint.save(
        update_fields=[
            "section_config",
            "theory_enabled",
            "theory_writeback_target",
            "instructions",
            "updated_at",
        ]
    )
    theory_link = exam.exam_questions.get(question=question)
    for attempt in ExamAttempt.objects.filter(
        exam=exam,
        status=CBTAttemptStatus.IN_PROGRESS,
    ).iterator(chunk_size=200):
        ExamAttemptAnswer.objects.get_or_create(
            attempt=attempt,
            exam_question=theory_link,
        )
        metadata = dict(attempt.writeback_metadata or {})
        order = [int(value) for value in (metadata.get("question_order") or [])]
        if theory_link.id not in order:
            order.append(theory_link.id)
            metadata["question_order"] = order
            attempt.writeback_metadata = metadata
            attempt.save(update_fields=["writeback_metadata", "updated_at"])
    return exam.exam_questions.count()


def main():
    session, term = current_session_term()
    if not session or not term:
        raise RuntimeError("Current academic session and term are not configured.")

    actor = (
        User.objects.filter(
            Q(primary_role__code=ROLE_IT_MANAGER)
            | Q(secondary_roles__code=ROLE_IT_MANAGER),
            is_active=True,
        )
        .distinct()
        .order_by("id")
        .first()
    )
    if actor is None:
        raise RuntimeError("No active IT Manager account exists.")

    now = timezone.now()
    local_now = timezone.localtime(now)
    friday_end_local = local_now.replace(
        year=2026,
        month=7,
        day=3,
        hour=23,
        minute=59,
        second=59,
        microsecond=0,
    )
    friday_end = friday_end_local.astimezone(timezone.get_current_timezone())
    if friday_end <= now:
        raise RuntimeError("The configured Free Test closing time has already passed.")

    created_rows = []
    for class_code, source_id in SOURCE_EXAMS.items():
        source = Exam.objects.select_related(
            "academic_class",
            "subject",
            "assignment",
            "question_bank",
        ).get(pk=source_id)
        if source.session_id != session.id:
            raise RuntimeError(f"Source exam {source_id} is outside the current session.")
        if source.academic_class.code != class_code:
            raise RuntimeError(f"Source exam {source_id} is not for {class_code}.")

        title = f"NDGA System Readiness Free Test - {class_code}"
        existing = Exam.objects.filter(
            title=title,
            session=session,
            term=term,
            academic_class=source.academic_class,
        ).first()
        if existing:
            total_questions = ensure_demo_theory(existing, actor)
            created_rows.append(
                (class_code, existing.id, total_questions, existing.status, "updated")
            )
            continue

        valid_links = list(
            source.exam_questions.select_related("question")
            .filter(
                question__question_type__in=[
                    CBTQuestionType.OBJECTIVE,
                    CBTQuestionType.MULTI_SELECT,
                ],
                question__is_active=True,
                question__correct_answer__is_finalized=True,
            )
            .annotate(correct_count=Count("question__correct_answer__correct_options"))
            .filter(correct_count__gte=1)
            .exclude(
                Q(question__stem__contains="??")
                | Q(question__rich_stem__contains="??")
                | Q(question__options__option_text__contains="??")
            )
            .distinct()
            .order_by("sort_order", "id")[:QUESTION_COUNT]
        )
        if len(valid_links) != QUESTION_COUNT:
            raise RuntimeError(
                f"{class_code} source {source_id} has only {len(valid_links)} safe finalized questions."
            )

        with transaction.atomic():
            exam = Exam.objects.create(
                title=title,
                description=(
                    "Free live capacity test. Scores are for practice only and are never written "
                    "to CA, exam, averages, or term results. Attempts are unlimited through Friday."
                ),
                exam_type=CBTExamType.FREE_TEST,
                status=CBTExamStatus.PENDING_IT,
                created_by=actor,
                assignment=source.assignment,
                subject=source.subject,
                academic_class=source.academic_class,
                session=session,
                term=term,
                question_bank=source.question_bank,
                is_time_based=True,
                open_now=False,
                is_free_test=True,
            )
            ExamBlueprint.objects.create(
                exam=exam,
                duration_minutes=20,
                max_attempts=1,
                shuffle_questions=True,
                shuffle_options=True,
                instructions=(
                    "This is a free system-readiness test. Answer all 20 questions. "
                    "Your score and answer review appear after submission. "
                    "It does not affect any school result, and you may try again without limit."
                ),
                section_config={
                    "unlimited_attempts": True,
                    "readiness_test": True,
                    "source_exam_id": source.id,
                    "question_count": QUESTION_COUNT,
                    "ui_mode": "JAMB_LIGHT",
                },
                passing_score=Decimal("50.00"),
                objective_writeback_target=CBTWritebackTarget.NONE,
                theory_enabled=False,
                auto_show_result_on_submit=True,
                finalize_on_logout=False,
                allow_retake=True,
            )
            ExamQuestion.objects.bulk_create(
                [
                    ExamQuestion(
                        exam=exam,
                        question=link.question,
                        sort_order=index,
                        marks=Decimal("5.00"),
                    )
                    for index, link in enumerate(valid_links, start=1)
                ]
            )
            ensure_demo_theory(exam, actor)
            it_activate_exam(
                exam=exam,
                actor=actor,
                open_now=False,
                is_time_based=True,
                schedule_start=now - timezone.timedelta(minutes=5),
                schedule_end=friday_end,
                comment="Activated for whole-school CBT concurrency and UI readiness testing.",
            )
        created_rows.append((class_code, exam.id, QUESTION_COUNT + 1, exam.status, "created"))

    print(f"Free Test window: {timezone.localtime(now):%Y-%m-%d %H:%M} to {timezone.localtime(friday_end):%Y-%m-%d %H:%M %Z}")
    for row in created_rows:
        print(*row)


main()
