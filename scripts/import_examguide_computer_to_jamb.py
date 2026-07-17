import hashlib
import html
import json
import os
import re
from decimal import Decimal
from pathlib import Path

import django
from django.contrib.auth import get_user_model
from django.db import transaction

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from apps.academics.models import AcademicClass, AcademicSession, Subject, Term
from apps.cbt.models import (
    CBTQuestionDifficulty,
    CBTQuestionType,
    CorrectAnswer,
    Option,
    Question,
    QuestionBank,
)


SOURCE = "EXAMGUIDE-COMPUTER-20260619"
BANK_NAME = "JAMB Review Bank Computer 2026"
INPUT_JSON = Path(
    os.environ.get(
        "EXAMGUIDE_COMPUTER_JSON",
        "/tmp/examguide-computer-20260619/computer_raw_examguide.json",
    )
)


BAD_TOKENS = ("??", "\ufffd", "Ã", "Â", "â€", "â€™", "â€œ", "â€")
DIAGRAM_TERMS = ("diagram", "figure", "image below", "shown below", "flowchart below")
FORMAT_TERMS = ("underlined", "underline", "italic", "italics", "bold", "bolding")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "because",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
}


def clean_html(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(div|p|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return re.sub(r"\s+", " ", text).strip()


def sig(value):
    return re.sub(r"[^a-z0-9]+", " ", clean_html(value).lower()).strip()


def tokens(value):
    return [
        token
        for token in re.findall(r"[a-z0-9]+", clean_html(value).lower())
        if token not in STOPWORDS and len(token) > 1
    ]


def infer_correct_index(options, explanation):
    solution = clean_html(explanation)
    solution_sig = sig(solution)
    first_part = solution[:280]
    first_sig = sig(first_part)
    solution_tokens = set(tokens(solution))
    first_tokens = set(tokens(first_part))
    scored = []
    for index, option in enumerate(options):
        option_sig = sig(option)
        option_tokens = set(tokens(option))
        score = 0
        if option_sig and option_sig in first_sig:
            score += 12
        elif option_sig and option_sig in solution_sig:
            score += 6
        score += len(option_tokens & first_tokens) * 3
        score += len(option_tokens & solution_tokens)
        if option_sig and re.search(rf"\b{re.escape(option_sig)}\b", first_sig):
            score += 6
        scored.append((score, index))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 4:
        return None
    if len(scored) > 1 and scored[0][0] <= scored[1][0] + 1:
        return None
    return scored[0][1]


def rotate_options(options, stem, correct_index):
    seed = int(hashlib.sha256(stem.encode("utf-8")).hexdigest()[:8], 16)
    shift = seed % len(options)
    rotated = options[shift:] + options[:shift]
    correct = options[correct_index]
    correct_label = "ABCD"[rotated.index(correct)]
    return rotated, correct_label


def reject_reason(stem, options, explanation):
    if len(stem.split()) <= 5 or len(stem) < 18:
        return "too_short"
    if any(token in " ".join([stem, explanation] + options) for token in BAD_TOKENS):
        return "bad_encoding_or_placeholder"
    if len(options) != 4 or any(not option for option in options):
        return "blank_or_missing_option"
    if len({sig(option) for option in options}) != 4:
        return "duplicate_options"
    lower = " ".join([stem] + options).lower()
    if any(term in lower for term in DIAGRAM_TERMS):
        return "diagram_question_without_verified_image"
    if any(term in lower for term in FORMAT_TERMS):
        return "formatting_dependent_question"
    if "correct answer" in lower or "answer:" in lower:
        return "answer_leak"
    return ""


def collect_rows():
    payload = json.loads(INPUT_JSON.read_text(encoding="utf-8-sig"))
    rows = []
    rejected = []
    seen = set()
    for raw in payload:
        stem = clean_html(raw.get("question_html"))
        options = [
            clean_html(raw.get("option_a_html")),
            clean_html(raw.get("option_b_html")),
            clean_html(raw.get("option_c_html")),
            clean_html(raw.get("option_d_html")),
        ]
        explanation = clean_html(raw.get("explanation_html"))
        stem_sig = sig(stem)
        reason = reject_reason(stem, options, explanation)
        correct_index = infer_correct_index(options, explanation) if not reason else None
        if correct_index is None and not reason:
            reason = "ambiguous_correct_answer"
        if stem_sig in seen and not reason:
            reason = "duplicate_stem"
        if reason:
            rejected.append(
                {
                    "season": raw.get("season"),
                    "source_question_no": raw.get("source_question_no"),
                    "reason": reason,
                    "stem": stem,
                }
            )
            continue
        seen.add(stem_sig)
        shuffled_options, correct_label = rotate_options(options, stem, correct_index)
        rows.append(
            {
                "stem": stem,
                "options": shuffled_options,
                "correct_label": correct_label,
                "correct_text": options[correct_index],
                "explanation": explanation,
                "topic": clean_html(raw.get("topic"))[:100],
                "season": raw.get("season"),
                "source_question_no": raw.get("source_question_no"),
            }
        )
    return rows, rejected


def run():
    rows, rejected = collect_rows()
    if len(rows) < 100:
        raise RuntimeError(f"Only {len(rows)} clean Computer rows found; refusing to import.")

    User = get_user_model()
    admin = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.order_by("id").first()
    )
    session = AcademicSession.objects.order_by("-id").first()
    term = Term.objects.order_by("-id").first()
    ss2 = (
        AcademicClass.objects.filter(code__icontains="SS2").order_by("id").first()
        or AcademicClass.objects.order_by("id").first()
    )
    jamb, _ = Subject.objects.get_or_create(
        code="JAMB",
        defaults={"name": "JAMB UTME Practice"},
    )

    with transaction.atomic():
        QuestionBank.objects.filter(
            subject=jamb,
            name=BANK_NAME,
        ).delete()
        Question.objects.filter(
            subject=jamb,
            source_reference=SOURCE,
        ).delete()

        bank = QuestionBank.objects.create(
            name=BANK_NAME,
            description=(
                "Computer Studies rows decoded from the local ExamGuide UTME 2026 "
                "question pack, filtered for complete stems and four clean options."
            ),
            owner=admin,
            subject=jamb,
            academic_class=ss2,
            session=session,
            term=term,
            is_active=True,
        )

        created = 0
        for row in rows:
            question = Question.objects.create(
                question_bank=bank,
                created_by=admin,
                subject=jamb,
                question_type=CBTQuestionType.OBJECTIVE,
                stem=row["stem"],
                rich_stem="",
                topic=f"Computer: {row['topic']}"[:120],
                difficulty=CBTQuestionDifficulty.MEDIUM,
                marks=Decimal("1.00"),
                source_type=Question.SourceType.MANUAL,
                source_reference=SOURCE,
                is_active=True,
            )
            option_by_label = {}
            for index, option_text in enumerate(row["options"], start=1):
                label = "ABCD"[index - 1]
                option = Option.objects.create(
                    question=question,
                    label=label,
                    option_text=option_text,
                    sort_order=index,
                )
                option_by_label[label] = option
            answer = CorrectAnswer.objects.create(
                question=question,
                note=(
                    f"{row['explanation']} Source: ExamGuide UTME 2026, "
                    f"{row['season']} question {row['source_question_no']}."
                ).strip(),
                is_finalized=True,
            )
            answer.correct_options.set([option_by_label[row["correct_label"]]])
            created += 1

    return {
        "source": SOURCE,
        "bank": BANK_NAME,
        "clean_rows_imported": created,
        "rejected_rows": len(rejected),
        "rejected_preview": rejected[:20],
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
