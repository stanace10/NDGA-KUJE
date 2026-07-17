"""Repair deterministically recoverable Third Term papers and activate only validated rows.

Run:
    python manage.py shell -c "exec(open('/app/scripts/repair_remaining_third_term_exams_20260701.py', encoding='utf-8').read())"
"""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.cbt.models import (
    CBTExamStatus,
    CBTQuestionDifficulty,
    CBTQuestionType,
    CorrectAnswer,
    Exam,
    ExamQuestion,
    ExamReviewAction,
    Option,
    Question,
)
from apps.cbt.services import _apply_exam_row_marks
from apps.cbt.workflow import it_activate_exam
from scripts.import_ca23_third_term_20260624 import (
    load_base_importer,
    parse_answer_terminated_rows,
    parse_numbered_text_rows,
    parse_plain_option_answer_rows,
)
from scripts.finalize_third_term_exam_readiness_20260630 import (
    BROKEN_ENDINGS,
    THEORY_HEADER,
    replace_broken_endings,
)


IMPORT_TAG = "THIRD_TERM_EXAM_20260629"
REBUILD_PARSERS = {
    1046: parse_answer_terminated_rows,  # JS1 Business Studies: recover question 40.
    1058: parse_plain_option_answer_rows,  # JS2 CCA: recover question 40.
    1053: parse_numbered_text_rows,  # JS2 Computer Studies: recover question 40.
    1075: parse_answer_terminated_rows,  # SS1 Accounting: recover questions 49-50.
    1069: parse_answer_terminated_rows,  # SS1 English: recover question 50.
    1093: parse_answer_terminated_rows,  # SS2 Accounting: recover questions 49-50.
    1084: parse_answer_terminated_rows,  # SS2 Agricultural Science: recover question 50.
    1094: parse_answer_terminated_rows,  # SS2 Computer Studies: recover question 55.
    1089: parse_answer_terminated_rows,  # SS2 Fishery: recover question 50.
    1086: parse_plain_option_answer_rows,  # SS2 Government: recover question 50.
}
DIRECT_REPAIRS = {1040, 1052}
SUSPICIOUS_RE = re.compile(r"(\?\?|ï¿½|placeholder|insert\s+(?:image|diagram))", re.I)

JS1_CLOZE_PASSAGE = (
    "Read the passage and choose the best word for the numbered blank.\n\n"
    "Last Friday, our school organized a debate competition. Many students (25) ______ part "
    "in the event. The topic was very interesting and each participant spoke (26) ______ "
    "confidence. The judges listened carefully and (27) ______ the performances. At the end "
    "of the competition, the best speaker was (28) ______ a prize. The principal congratulated "
    "all the participants and advised them to continue (29) ______ hard. He also encouraged "
    "them to read widely in order to improve their communication (30) ______. The audience "
    "enjoyed the programme and (31) ______ loudly for the winners. The event was a great "
    "(32) ______ and everyone looked forward (33) ______ the next competition. It was indeed "
    "an unforgettable (34) ______."
)


def _it_actor():
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
    return actor


def _safe_text(value):
    return str(value or "").strip()


def _objective_rows(exam, parser):
    source = exam.import_sources.order_by("-created_at").first()
    if source is None or not source.extracted_text.strip():
        raise RuntimeError(f"Exam {exam.id} has no extracted source text.")
    base = load_base_importer()
    rows = [
        row
        for row in parser(base, source.extracted_text)
        if (row.get("question_type") or "").strip().upper() == "OBJECTIVE"
    ]
    if not rows:
        raise RuntimeError(f"Exam {exam.id} parser returned no objective questions.")
    for index, row in enumerate(rows, start=1):
        options = row.get("options") or {}
        correct_label = (row.get("correct_label") or "").strip().upper()
        if (
            not _safe_text(row.get("stem"))
            or set(options) != {"A", "B", "C", "D"}
            or correct_label not in {"A", "B", "C", "D"}
        ):
            raise RuntimeError(f"Exam {exam.id} source row {index} is incomplete.")
    return source, rows


def _rebuild_objectives(exam, parser):
    source, rows = _objective_rows(exam, parser)
    theory_link = (
        exam.exam_questions.exclude(question__question_type=CBTQuestionType.OBJECTIVE)
        .select_related("question")
        .first()
    )
    if theory_link is None or not theory_link.question.stem.strip():
        raise RuntimeError(f"Exam {exam.id} has no usable theory section.")
    theory_link.sort_order = 1000
    theory_link.save(update_fields=["sort_order", "updated_at"])

    old_links = list(
        exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE)
        .select_related("question")
    )
    old_question_ids = [link.question_id for link in old_links]
    exam.exam_questions.filter(id__in=[link.id for link in old_links]).delete()

    for sort_order, row in enumerate(rows, start=1):
        question = Question.objects.create(
            question_bank=exam.question_bank,
            created_by=exam.created_by,
            subject=exam.subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=_safe_text(row.get("stem")),
            rich_stem=_safe_text(row.get("rich_stem")),
            topic="Third Term Examination",
            difficulty=CBTQuestionDifficulty.MEDIUM,
            marks=Decimal("1.00"),
            source_type=Question.SourceType.DOCUMENT,
            source_reference=str(source.id),
        )
        options = row["options"]
        option_map = {}
        for option_order, label in enumerate(("A", "B", "C", "D"), start=1):
            option_map[label] = Option.objects.create(
                question=question,
                label=label,
                option_text=_safe_text(options[label]),
                sort_order=option_order,
            )
        answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.set([option_map[(row["correct_label"] or "").strip().upper()]])
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=Decimal("1.00"),
        )

    theory_link.sort_order = len(rows) + 1
    theory_link.save(update_fields=["sort_order", "updated_at"])
    Question.objects.filter(id__in=old_question_ids, exam_links__isnull=True).delete()
    return len(rows)


def _repair_js1_english(exam):
    for blank_number in range(25, 35):
        link = exam.exam_questions.select_related("question").get(sort_order=blank_number)
        question = link.question
        question.stem = (
            f"{JS1_CLOZE_PASSAGE}\n\n"
            f"Choose the best option for blank ({blank_number})."
        )
        question.rich_stem = ""
        question.shared_stimulus_key = "js1-eng-third-term-cloze-25-34"
        question.save(
            update_fields=[
                "stem",
                "rich_stem",
                "shared_stimulus_key",
                "updated_at",
            ]
        )


def _repair_js2_english(exam):
    instruction = (
        "For Questions 20-24, choose the option that has the same vowel sound "
        "as the word in capital focus."
    )
    for sort_order in range(20, 25):
        link = exam.exam_questions.select_related("question").get(sort_order=sort_order)
        question = link.question
        clean_stem = replace_broken_endings(question.stem)
        question.stem = f"{instruction}\n\nFocus word: {clean_stem}"
        question.rich_stem = ""
        question.save(update_fields=["stem", "rich_stem", "updated_at"])


def _normalize_exam_text(exam):
    for link in exam.exam_questions.select_related("question").prefetch_related("question__options"):
        question = link.question
        cleaned_stem = replace_broken_endings(question.stem)
        if cleaned_stem != question.stem:
            question.stem = cleaned_stem
            question.save(update_fields=["stem", "updated_at"])
        for option in question.options.all():
            cleaned_option = replace_broken_endings(option.option_text)
            if cleaned_option != option.option_text:
                option.option_text = cleaned_option
                option.save(update_fields=["option_text", "updated_at"])

    theory_link = (
        exam.exam_questions.exclude(question__question_type=CBTQuestionType.OBJECTIVE)
        .select_related("question")
        .first()
    )
    if theory_link and not theory_link.question.stem.startswith("THEORY SECTION (30 MARKS)"):
        theory_link.question.stem = THEORY_HEADER + theory_link.question.stem.strip()
        theory_link.question.save(update_fields=["stem", "updated_at"])


def _validate(exam):
    issues = []
    objective_links = list(
        exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE)
        .select_related("question", "question__correct_answer")
        .prefetch_related("question__options", "question__correct_answer__correct_options")
        .order_by("sort_order")
    )
    theory_links = list(
        exam.exam_questions.exclude(question__question_type=CBTQuestionType.OBJECTIVE)
        .select_related("question")
    )
    stems = Counter()
    for link in objective_links:
        question = link.question
        options = list(question.options.all())
        answer = getattr(question, "correct_answer", None)
        normalized = re.sub(r"\W+", "", question.stem).lower()
        stems[normalized] += 1
        if not question.stem.strip() or len(options) != 4:
            issues.append(f"question {link.sort_order} has invalid structure")
        if not answer or not answer.is_finalized or answer.correct_options.count() != 1:
            issues.append(f"question {link.sort_order} has invalid answer")
        all_text = [question.stem, question.rich_stem, *[option.option_text for option in options]]
        if any(SUSPICIOUS_RE.search(text or "") for text in all_text):
            issues.append(f"question {link.sort_order} contains placeholder text")
    duplicate_count = sum(value - 1 for key, value in stems.items() if key and value > 1)
    if duplicate_count:
        issues.append(f"{duplicate_count} duplicate objective question(s)")
    if not objective_links:
        issues.append("no objective questions")
    if len(theory_links) != 1 or not theory_links[0].question.stem.strip():
        issues.append("theory section is missing or invalid")
    objective_marks = sum((row.marks for row in objective_links), Decimal("0.00"))
    theory_marks = sum((row.marks for row in theory_links), Decimal("0.00"))
    if objective_marks != Decimal("20.00") or theory_marks != Decimal("30.00"):
        issues.append(f"invalid mark split {objective_marks}/{theory_marks}")
    return issues


def _activate_repaired(exam, actor, reason):
    previous_status = exam.status
    exam.status = CBTExamStatus.APPROVED
    exam.open_now = False
    exam.activated_by = None
    exam.activated_at = None
    exam.activation_snapshot = {}
    exam.activation_snapshot_hash = ""
    exam.activation_comment = reason
    exam.save(
        update_fields=[
            "status",
            "open_now",
            "activated_by",
            "activated_at",
            "activation_snapshot",
            "activation_snapshot_hash",
            "activation_comment",
            "updated_at",
        ]
    )
    ExamReviewAction.objects.create(
        exam=exam,
        actor=actor,
        from_status=previous_status,
        to_status=CBTExamStatus.APPROVED,
        action="IT_DETERMINISTIC_REPAIR",
        comment=reason,
    )
    it_activate_exam(
        exam=exam,
        actor=actor,
        open_now=False,
        is_time_based=True,
        schedule_start=exam.schedule_start,
        schedule_end=exam.schedule_end,
        comment=reason,
    )


@transaction.atomic
def run():
    actor = _it_actor()
    repaired = []
    for exam_id, parser in REBUILD_PARSERS.items():
        exam = Exam.objects.select_related("blueprint", "question_bank").get(
            pk=exam_id,
            description__contains=IMPORT_TAG,
            status=CBTExamStatus.DRAFT,
        )
        objective_count = _rebuild_objectives(exam, parser)
        _normalize_exam_text(exam)
        _apply_exam_row_marks(
            exam=exam,
            objective_total=Decimal("20.00"),
            theory_total=Decimal("30.00"),
        )
        exam.blueprint.section_config = {
            **(exam.blueprint.section_config or {}),
            "objective_count": objective_count,
            "theory_count": 1,
            "objective_target_max": "20.00",
            "theory_target_max": "30.00",
            "source_repaired": True,
        }
        exam.blueprint.save(update_fields=["section_config", "updated_at"])
        issues = _validate(exam)
        if issues:
            raise RuntimeError(f"Exam {exam.id} failed post-repair validation: {issues}")
        reason = (
            "Reconstructed deterministically from supplied source; complete options and finalized "
            "answer mapping verified; 20/30 mark split verified."
        )
        _activate_repaired(exam, actor, reason)
        repaired.append((exam.id, exam.academic_class.code, exam.subject.code, objective_count))

    for exam_id in sorted(DIRECT_REPAIRS):
        exam = Exam.objects.select_related("blueprint").get(
            pk=exam_id,
            description__contains=IMPORT_TAG,
            status=CBTExamStatus.DRAFT,
        )
        if exam_id == 1040:
            _repair_js1_english(exam)
            reason = "Restored the full cloze passage and blank-specific prompts for Questions 25-34."
        else:
            _repair_js2_english(exam)
            reason = "Restored the missing phonetics instruction for Questions 20-24."
        _normalize_exam_text(exam)
        _apply_exam_row_marks(
            exam=exam,
            objective_total=Decimal("20.00"),
            theory_total=Decimal("30.00"),
        )
        issues = _validate(exam)
        if issues:
            raise RuntimeError(f"Exam {exam.id} failed post-repair validation: {issues}")
        _activate_repaired(exam, actor, reason + " Full structural and answer validation passed.")
        repaired.append(
            (
                exam.id,
                exam.academic_class.code,
                exam.subject.code,
                exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE).count(),
            )
        )

    remaining = list(
        Exam.objects.filter(
            description__contains=IMPORT_TAG,
            status=CBTExamStatus.DRAFT,
        )
        .select_related("academic_class", "subject")
        .order_by("academic_class__code", "subject__name")
        .values_list("id", "academic_class__code", "subject__code", "activation_comment")
    )
    print({"activated_repaired": repaired, "remaining_draft": remaining})


run()
