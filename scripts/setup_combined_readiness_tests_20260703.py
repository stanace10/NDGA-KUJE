"""Create the English + Mathematics whole-school CBT readiness tests.

The tests are available on Friday 3 July and Sunday 5 July 2026 only.
They are practice-only, have unlimited attempts, and never write to results.

Run:
    python manage.py shell < scripts/setup_combined_readiness_tests_20260703.py
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
)
from apps.cbt.workflow import it_activate_exam, it_close_exam
from apps.results.utils import current_session_term


CLASS_SOURCES = {
    "JS1": {"english": 1040, "mathematics": 1038},
    "JS2": {"english": 1052, "mathematics": 1049},
    "SS1": {"english": 1069, "mathematics": 1064},
    "SS2": {"english": 1088, "mathematics": 1177},
}
WINDOWS = {
    "2026-07-03": ((2026, 7, 3, 0, 0, 0), (2026, 7, 3, 23, 59, 59)),
    "2026-07-05": ((2026, 7, 5, 0, 0, 0), (2026, 7, 5, 23, 59, 59)),
}
QUESTIONS_PER_SUBJECT = 10


THEORY_PROMPTS = {
    "JS1": "Write four complete sentences explaining how you prepare for a computer-based examination.",
    "JS2": "State three responsible computer-use rules and explain why one of them is important during an examination.",
    "SS1": "Explain two benefits of computer-based testing and one practical challenge a school should prepare for.",
    "SS2": "Describe three practical steps that make a computer-based examination secure, fair, and reliable.",
}


def aware(parts):
    return timezone.make_aware(
        timezone.datetime(*parts),
        timezone.get_current_timezone(),
    )


def safe_objective_links(source_exam):
    rows = (
        source_exam.exam_questions.select_related(
            "question",
            "question__correct_answer",
        )
        .prefetch_related(
            "question__options",
            "question__correct_answer__correct_options",
        )
        .filter(
            question__question_type__in=[
                CBTQuestionType.OBJECTIVE,
                CBTQuestionType.MULTI_SELECT,
            ],
            question__is_active=True,
            question__correct_answer__is_finalized=True,
        )
        .annotate(
            option_count=Count("question__options", distinct=True),
            correct_count=Count(
                "question__correct_answer__correct_options",
                distinct=True,
            ),
        )
        .filter(option_count__gte=2, correct_count__gte=1)
        .exclude(
            Q(question__stem__exact="")
            | Q(question__stem__contains="??")
            | Q(question__rich_stem__contains="??")
            | Q(question__options__option_text__exact="")
            | Q(question__options__option_text__contains="??")
        )
        .distinct()
        .order_by("sort_order", "id")
    )
    rows = list(rows[:QUESTIONS_PER_SUBJECT])
    if len(rows) != QUESTIONS_PER_SUBJECT:
        raise RuntimeError(
            f"{source_exam.title} has only {len(rows)} safe objective questions."
        )
    return rows


def clone_objective(*, source_question, target_exam, section, ordinal, actor):
    reference = (
        f"NDGA-COMBINED-READINESS-{target_exam.academic_class.code}-"
        f"{target_exam.schedule_start:%Y%m%d}-{section.upper()}-{ordinal:02d}"
    )
    existing = Question.objects.filter(
        subject=target_exam.subject,
        source_reference=reference,
    ).first()
    if existing:
        return existing

    question = Question.objects.create(
        question_bank=target_exam.question_bank,
        created_by=actor,
        subject=target_exam.subject,
        question_type=source_question.question_type,
        stem=source_question.stem,
        rich_stem=source_question.rich_stem,
        topic=f"{section}: Readiness",
        difficulty=source_question.difficulty,
        marks=Decimal("1.00"),
        source_type=source_question.source_type,
        source_reference=reference,
        stimulus_image=source_question.stimulus_image,
        stimulus_video=source_question.stimulus_video,
        stimulus_caption=source_question.stimulus_caption,
        shared_stimulus_key=(
            f"READY-{target_exam.id}-{section[:3].upper()}-"
            f"{source_question.shared_stimulus_key}"
            if source_question.shared_stimulus_key
            else ""
        )[:64],
        is_active=True,
    )
    option_by_source_id = {}
    for source_option in source_question.options.order_by("sort_order", "label"):
        option = Option.objects.create(
            question=question,
            label=source_option.label,
            option_text=source_option.option_text,
            sort_order=source_option.sort_order,
        )
        option_by_source_id[source_option.id] = option

    source_answer = source_question.correct_answer
    answer = CorrectAnswer.objects.create(
        question=question,
        note=source_answer.note,
        is_finalized=True,
    )
    answer.correct_options.set(
        option_by_source_id[source_option.id]
        for source_option in source_answer.correct_options.all()
    )
    answer.full_clean()
    return question


def create_theory(*, exam, actor):
    reference = (
        f"NDGA-COMBINED-READINESS-{exam.academic_class.code}-"
        f"{exam.schedule_start:%Y%m%d}-THEORY"
    )
    question, _ = Question.objects.get_or_create(
        subject=exam.subject,
        source_reference=reference,
        defaults={
            "question_bank": exam.question_bank,
            "created_by": actor,
            "question_type": CBTQuestionType.SHORT_ANSWER,
            "stem": THEORY_PROMPTS[exam.academic_class.code],
            "topic": "Theory: Readiness",
            "marks": Decimal("5.00"),
            "is_active": True,
        },
    )
    return question


def build_exam(*, class_code, sources, start_at, end_at, actor, session, term):
    english_source = Exam.objects.select_related(
        "academic_class",
        "subject",
        "assignment",
        "question_bank",
    ).get(pk=sources["english"])
    maths_source = Exam.objects.select_related(
        "academic_class",
        "subject",
    ).get(pk=sources["mathematics"])
    if english_source.academic_class.code != class_code:
        raise RuntimeError(f"English source does not belong to {class_code}.")
    if maths_source.academic_class_id != english_source.academic_class_id:
        raise RuntimeError(f"Mathematics source does not belong to {class_code}.")

    title = (
        f"NDGA English & Mathematics Readiness Test - {class_code} - "
        f"{timezone.localtime(start_at):%d %b %Y}"
    )
    existing = Exam.objects.filter(
        title=title,
        session=session,
        term=term,
        academic_class=english_source.academic_class,
    ).first()
    if existing:
        return existing, "existing"

    english_rows = safe_objective_links(english_source)
    maths_rows = safe_objective_links(maths_source)
    with transaction.atomic():
        exam = Exam.objects.create(
            title=title,
            description=(
                "A non-recording English and Mathematics live readiness test. "
                "Scores never affect CA, examination, averages, or term results."
            ),
            exam_type=CBTExamType.FREE_TEST,
            status=CBTExamStatus.PENDING_IT,
            created_by=actor,
            assignment=english_source.assignment,
            subject=english_source.subject,
            academic_class=english_source.academic_class,
            session=session,
            term=term,
            question_bank=english_source.question_bank,
            is_time_based=True,
            open_now=False,
            is_free_test=True,
            schedule_start=start_at,
            schedule_end=end_at,
        )
        ExamBlueprint.objects.create(
            exam=exam,
            duration_minutes=30,
            max_attempts=1,
            shuffle_questions=True,
            shuffle_options=True,
            instructions=(
                "Answer the English and Mathematics objective sections, then "
                "complete the short typed theory demonstration. This practice "
                "test does not affect any school result."
            ),
            section_config={
                "unlimited_attempts": True,
                "readiness_test": True,
                "combined_readiness": True,
                "sections": {
                    "English": QUESTIONS_PER_SUBJECT,
                    "Mathematics": QUESTIONS_PER_SUBJECT,
                },
                "question_count": 21,
                "objective_count": 20,
                "theory_count": 1,
                "theory_response_mode": "PAPER",
                "theory_target_max": "5.00",
                "theory_instructions": (
                    "Read the theory question on screen and answer it on the "
                    "supplied answer paper."
                ),
                "review_seconds": 30,
                "calculator_mode": "BASIC",
                "seb_required": False,
                "seb_test_mode": True,
                "ui_mode": "JAMB_LIGHT",
            },
            passing_score=Decimal("50.00"),
            objective_writeback_target=CBTWritebackTarget.NONE,
            theory_enabled=True,
            theory_writeback_target=CBTWritebackTarget.NONE,
            auto_show_result_on_submit=True,
            finalize_on_logout=False,
            allow_retake=True,
        )

        sort_order = 1
        for section, rows in (
            ("English", english_rows),
            ("Mathematics", maths_rows),
        ):
            for ordinal, link in enumerate(rows, start=1):
                question = clone_objective(
                    source_question=link.question,
                    target_exam=exam,
                    section=section,
                    ordinal=ordinal,
                    actor=actor,
                )
                ExamQuestion.objects.create(
                    exam=exam,
                    question=question,
                    sort_order=sort_order,
                    marks=Decimal("1.00"),
                )
                sort_order += 1

        theory = create_theory(exam=exam, actor=actor)
        ExamQuestion.objects.create(
            exam=exam,
            question=theory,
            sort_order=sort_order,
            marks=Decimal("5.00"),
        )
        it_activate_exam(
            exam=exam,
            actor=actor,
            open_now=False,
            is_time_based=True,
            schedule_start=start_at,
            schedule_end=end_at,
            comment=(
                "Activated for the 150+ candidate English/Mathematics "
                "whole-school concurrency test."
            ),
        )
    return exam, "created"


def main():
    session, term = current_session_term()
    if not session or not term:
        raise RuntimeError("Current session and term are not configured.")
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
        raise RuntimeError("No active IT Manager exists.")

    rows = []
    for day, (start_parts, end_parts) in WINDOWS.items():
        start_at = aware(start_parts)
        end_at = aware(end_parts)
        for class_code, sources in CLASS_SOURCES.items():
            exam, state = build_exam(
                class_code=class_code,
                sources=sources,
                start_at=start_at,
                end_at=end_at,
                actor=actor,
                session=session,
                term=term,
            )
            rows.append((day, class_code, exam.id, state, exam.status))

    old_tests = Exam.objects.filter(
        title__startswith="NDGA System Readiness Free Test - ",
        status=CBTExamStatus.ACTIVE,
    )
    for exam in old_tests:
        it_close_exam(
            exam=exam,
            actor=actor,
            comment="Replaced by the combined English and Mathematics readiness test.",
        )

    for row in rows:
        print("|".join(str(value) for value in row))


main()
