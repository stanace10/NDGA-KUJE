"""Apply deterministic safety corrections to the imported Third Term exams."""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django

django.setup()

from django.db import transaction

from apps.cbt.models import CBTExamStatus, CBTQuestionType, Exam


IMPORT_TAG = "THIRD_TERM_EXAM_20260629"
HOLD_EXAM_IDS = {
    1040: "Broken JS1 English cloze passage/questions 25-34.",
    1041: "Four duplicated JS1 Digital Technology objective questions.",
    1052: "JS2 English phonetics questions lost their section instruction.",
    1092: "SS2 Physics contains a duplicated electric-charge question.",
}

BROKEN_ENDINGS = {
    "fabri c)": "fabric",
    "Nigeri a)": "Nigeria",
    "fee d)": "feed",
    "sol d)": "sold",
    "metho d)": "method",
    "hea d)": "head",
    "dea d)": "dead",
    "foo d)": "food",
    "purchase d)": "purchased",
    "fin d)": "find",
    "calle d)": "called",
    "shoul d)": "should",
}

THEORY_HEADER = (
    "THEORY SECTION (30 MARKS)\n"
    "Follow the paper-specific instruction below. The completed theory work is marked/scaled to 30 marks.\n\n"
)


def replace_broken_endings(value: str) -> str:
    cleaned = value or ""
    for broken, replacement in BROKEN_ENDINGS.items():
        cleaned = re.sub(re.escape(broken) + r"$", replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+a\)\s*$", "", cleaned)
    cleaned = re.sub(r"^\s*4\s*Mark\s*=\s*20\s*Marks\)\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


@transaction.atomic
def run():
    imported = Exam.objects.filter(description__contains=IMPORT_TAG).select_related(
        "academic_class",
        "subject",
        "blueprint",
    )
    held = []
    repaired_questions = 0

    for exam_id, reason in HOLD_EXAM_IDS.items():
        exam = imported.filter(pk=exam_id).first()
        if not exam:
            continue
        exam.status = CBTExamStatus.DRAFT
        exam.open_now = False
        exam.activation_comment = f"Held in Draft after final readiness audit: {reason}"
        exam.save(update_fields=["status", "open_now", "activation_comment", "updated_at"])
        held.append((exam.academic_class.code, exam.subject.code, reason))

    active = imported.filter(status=CBTExamStatus.ACTIVE)
    for exam in active:
        for link in exam.exam_questions.select_related("question").prefetch_related("question__options"):
            question = link.question
            cleaned_stem = replace_broken_endings(question.stem)
            if cleaned_stem != question.stem:
                question.stem = cleaned_stem
                question.save(update_fields=["stem", "updated_at"])
                repaired_questions += 1

            for option in question.options.all():
                cleaned_option = replace_broken_endings(option.option_text)
                if cleaned_option != option.option_text:
                    option.option_text = cleaned_option
                    option.save(update_fields=["option_text", "updated_at"])

        theory_link = exam.exam_questions.exclude(
            question__question_type=CBTQuestionType.OBJECTIVE
        ).select_related("question").first()
        if theory_link and not theory_link.question.stem.startswith("THEORY SECTION (30 MARKS)"):
            theory_link.question.stem = THEORY_HEADER + theory_link.question.stem.strip()
            theory_link.question.save(update_fields=["stem", "updated_at"])
            repaired_questions += 1

    # Restore three TDR questions whose "third-angle" prefix moved into option D.
    tdr = imported.filter(pk=1097, status=CBTExamStatus.ACTIVE).first()
    if tdr:
        tdr_repairs = {
            11: ("In third-angle projection, the object is placed", "above the plane"),
            12: ("In third-angle projection, the plan is drawn", "on the right"),
            13: ("In third-angle projection, the right-hand end view is placed on the", "bottom"),
        }
        for sort_order, (stem, option_d) in tdr_repairs.items():
            link = tdr.exam_questions.select_related("question").get(sort_order=sort_order)
            link.question.stem = stem
            link.question.save(update_fields=["stem", "updated_at"])
            option = link.question.options.get(label="D")
            option.option_text = option_d
            option.save(update_fields=["option_text", "updated_at"])
            repaired_questions += 1

    # Make repeated Literature stems self-contained while preserving their source context.
    literature = imported.filter(pk=1074, status=CBTExamStatus.ACTIVE).first()
    if literature:
        context_by_order = {
            9: "Digging",
            11: "Digging",
            12: "Digging",
            21: "Not My Business",
            23: "Not My Business",
            24: "Not My Business",
            44: "She Walks in Beauty",
            46: "She Walks in Beauty",
            47: "She Walks in Beauty",
        }
        for sort_order, context in context_by_order.items():
            link = literature.exam_questions.select_related("question").get(sort_order=sort_order)
            if not link.question.stem.startswith(f"[{context}]"):
                link.question.stem = f"[{context}] {link.question.stem}"
                link.question.save(update_fields=["stem", "updated_at"])
                repaired_questions += 1

    # Final deterministic gate. Any unexpected defect is held in Draft.
    final_issues = []
    suspicious = re.compile(r"(\?\?|�|placeholder|insert\s+(?:image|diagram))", re.IGNORECASE)
    for exam in imported.filter(status=CBTExamStatus.ACTIVE):
        issues = []
        objective_links = list(
            exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE)
            .select_related("question", "question__correct_answer")
            .prefetch_related("question__options", "question__correct_answer__correct_options")
        )
        theory_links = list(
            exam.exam_questions.exclude(question__question_type=CBTQuestionType.OBJECTIVE)
            .select_related("question")
        )
        normalized_stems = Counter(
            re.sub(r"\W+", "", link.question.stem).lower()
            for link in objective_links
        )
        duplicate_count = sum(value - 1 for key, value in normalized_stems.items() if key and value > 1)
        if duplicate_count:
            issues.append(f"{duplicate_count} duplicate objective question(s)")
        for link in objective_links:
            question = link.question
            options = list(question.options.all())
            answer = getattr(question, "correct_answer", None)
            if not question.stem.strip() or len(options) != 4:
                issues.append(f"question {link.sort_order} has invalid structure")
            if not answer or not answer.is_finalized or answer.correct_options.count() != 1:
                issues.append(f"question {link.sort_order} has invalid answer key")
            all_text = [question.stem, question.rich_stem, *[option.option_text for option in options]]
            if any(suspicious.search(text or "") for text in all_text):
                issues.append(f"question {link.sort_order} contains a placeholder")
        objective_marks = sum((link.marks for link in objective_links), Decimal("0.00"))
        theory_marks = sum((link.marks for link in theory_links), Decimal("0.00"))
        if objective_marks != Decimal("20.00") or theory_marks != Decimal("30.00"):
            issues.append(f"invalid mark split {objective_marks}/{theory_marks}")
        if len(theory_links) != 1 or not theory_links[0].question.stem.strip():
            issues.append("theory section is missing or split incorrectly")
        if issues:
            exam.status = CBTExamStatus.DRAFT
            exam.open_now = False
            exam.activation_comment = "Held in Draft by final deterministic readiness gate: " + "; ".join(issues)
            exam.save(update_fields=["status", "open_now", "activation_comment", "updated_at"])
            final_issues.append((exam.academic_class.code, exam.subject.code, issues))

    print(
        {
            "held_known": held,
            "repaired_questions": repaired_questions,
            "held_by_final_gate": final_issues,
            "active_ready": imported.filter(status=CBTExamStatus.ACTIVE).count(),
            "draft_review": imported.filter(status=CBTExamStatus.DRAFT).count(),
        }
    )


if __name__ == "__main__":
    run()
