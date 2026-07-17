"""Move source-specific theory directions into the persistent theory banner."""

from __future__ import annotations

import re
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.cbt.models import CBTQuestionType, Exam


IMPORT_TAG = "THIRD_TERM_EXAM_20260629"
DEFAULT = (
    "Answer the theory questions on paper exactly as directed in the paper. "
    "Read every sub-question carefully before answering."
)
DIRECTIVE_RE = re.compile(
    r"(?ix)\b("
    r"answer\s+number\s+one\s+and\s+any\s+other\s+(?:one|two|three|four|five|\d+)"
    r"|answer\s+any\s+(?:one|two|three|four|five|six|\d+)(?:\s*\(\d+\))?\s+questions?"
    r"|answer\s+only\s+(?:one|two|three|four|five|six|\d+)(?:\s*\(\d+\))?\s+questions?"
    r"|answer\s+(?:all|one|two|three|four|five|six)(?:\s*\(\d+\))?\s+(?:the\s+)?questions?"
    r"|answer\s+four\s+questions\s+in\s+all"
    r"|attempt\s+(?:only\s+)?(?:one|two|three|four|five|six|\d+)(?:\s*\(\d+\))?\s+questions?"
    r"|number\s+one\s+is\s+compulsory"
    r")\b"
)


def instruction_for_exam(exam):
    theory = (
        exam.exam_questions.exclude(
            question__question_type__in=[
                CBTQuestionType.OBJECTIVE,
                CBTQuestionType.MULTI_SELECT,
            ]
        )
        .select_related("question")
        .order_by("sort_order")
        .first()
    )
    stem = (theory.question.stem if theory else "") or ""
    candidates = [
        match.group(1).strip().rstrip(".") + "."
        for match in DIRECTIVE_RE.finditer(stem[:1500])
    ]
    if not candidates:
        source = exam.import_sources.order_by("-created_at").first()
        text = (source.extracted_text if source else "") or ""
        candidates = [
            match.group(1).strip().rstrip(".") + "."
            for match in DIRECTIVE_RE.finditer(text)
        ][-2:]
    unique = []
    for row in candidates:
        normalized = re.sub(r"\s+", " ", row).strip()
        if normalized and normalized.casefold() not in {item.casefold() for item in unique}:
            unique.append(normalized)
    return " ".join(unique[:3]) or DEFAULT


def run():
    updated = []
    exams = (
        Exam.objects.filter(description__contains=IMPORT_TAG)
        .select_related("blueprint", "academic_class", "subject")
        .order_by("id")
    )
    for exam in exams:
        blueprint = getattr(exam, "blueprint", None)
        if blueprint is None:
            continue
        config = dict(blueprint.section_config or {})
        instruction = instruction_for_exam(exam)
        config["theory_instructions"] = instruction
        blueprint.section_config = config
        blueprint.save(update_fields=["section_config", "updated_at"])
        updated.append(
            (exam.id, exam.academic_class.code, exam.subject.code, instruction)
        )
    print({"updated": len(updated)})
    for row in updated:
        print(" | ".join(str(value) for value in row))


run()
