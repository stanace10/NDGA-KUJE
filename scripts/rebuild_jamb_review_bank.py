from __future__ import annotations

import csv
import html
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.prod")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.academics.models import AcademicClass, AcademicSession, Subject, Term
from apps.cbt.models import (
    CBTQuestionDifficulty,
    CBTQuestionType,
    CorrectAnswer,
    Option,
    Question,
    QuestionBank,
)

SOURCE = "NDGA-JAMB-REVIEW-BANK-20260618"
SOURCE_ROOT = Path(os.environ.get("JAMB_LEGACY_SOURCE_DIR", "/app/tmp/jamb_source"))
if not SOURCE_ROOT.exists():
    SOURCE_ROOT = Path(r"E:\JambCBT")
AUDIT_DIR = SOURCE_ROOT / "htdocs" / "reports" / "audit"
SQL_SOURCES = [
    SOURCE_ROOT / "htdocs" / "jamb_question.sql",
    SOURCE_ROOT / "backups" / "db_recovery" / "jamb_question_mysql51.sql",
]

SUBJECT_MAP = {
    "English Language": "English",
    "Mathematics": "Mathematics",
    "Physics": "Physics",
    "Chemistry": "Chemistry",
    "Biology": "Biology",
    "Government": "Government",
    "CRS": "CRS",
    "English Literature": "Literature",
    "Commerce": "Commerce",
    "commerce": "Commerce",
    "Economics": "Economics",
    "Account": "Accounting",
    "Accounting": "Accounting",
}

MINIMUM_IMPORT = {
    "English": 300,
    "Mathematics": 250,
    "Physics": 250,
    "Chemistry": 250,
    "Biology": 250,
    "Government": 250,
    "CRS": 250,
    "Literature": 120,
    "Commerce": 180,
    "Economics": 180,
    "Accounting": 180,
}

BAD_TEXT = re.compile(
    r"(\?\?|^option\s*[a-d]$|question paper type|which of the following diagrams|"
    r"diagram above|shown above|shown below|figure above|image above|from the diagram|"
    r"select the diagram|this diagram|underlined|italics|italicized|bold|^\s*$)",
    re.I,
)
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str) -> str:
    text = html.unescape(str(value or ""))
    replacements = {
        "\xa0": " ",
        "Ã¢Ë†Â©": " intersection ",
        "Ã¢Ë†Âª": " union ",
        "ÃƒËœ": "empty set",
        "Ãâ‚¬": "pi",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "â€“": "-",
        "â€”": "-",
        " =N=": " N",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text, flags=re.I | re.S)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text, flags=re.I | re.S)
    text = text.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    text = TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def subject_name(raw: str) -> str:
    return SUBJECT_MAP.get((raw or "").strip(), "")


def clean_option(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"^option\s+", "", text, flags=re.I).strip()
    return text


def is_bad_text(value: str) -> bool:
    text = clean_text(value)
    if BAD_TEXT.search(text):
        return True
    if len(text) < 3:
        return True
    return False


def normalize_signature(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_text(text).lower()).strip()


def row_is_valid(subject: str, question: str, options: list[str], correct_text: str, image: str = "") -> tuple[bool, str]:
    if subject not in MINIMUM_IMPORT:
        return False, "unsupported_subject"
    if image and image.lower() not in {"none", "null", ""}:
        return False, "requires_image"
    if is_bad_text(question) or len(clean_text(question)) < 12:
        return False, "bad_question"
    if len(options) != 4:
        return False, "not_four_options"
    if any(is_bad_text(option) for option in options):
        return False, "bad_option"
    lowered = [normalize_signature(option) for option in options]
    if len(set(lowered)) != 4:
        return False, "duplicate_options"
    if not correct_text:
        return False, "missing_correct"
    correct_sig = normalize_signature(correct_text)
    if correct_sig not in lowered:
        return False, "correct_not_in_options"
    return True, ""


def latest_audit_csv() -> Path | None:
    files = sorted(AUDIT_DIR.glob("core_subjects_2026_full_audit_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def iter_audit_rows():
    path = latest_audit_csv()
    if not path:
        return
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            subject = subject_name(row.get("subject", ""))
            question = clean_text(" ".join(part for part in [row.get("instruction", ""), row.get("passage", ""), row.get("question", "")] if part))
            options = [clean_option(row.get(key, "")) for key in ("option_a", "option_b", "option_c", "option_d")]
            correct = clean_option(row.get("correct_answer", ""))
            image = clean_text(row.get("image_src", ""))
            ok, reason = row_is_valid(subject, question, options, correct, image)
            yield {
                "subject": subject,
                "year": row.get("year", ""),
                "question": question,
                "options": options,
                "correct": correct,
                "image": image,
                "ok": ok,
                "reason": reason,
                "source": str(path),
            }


def sql_tuple_chunks(text: str):
    in_insert = False
    buffer = []
    depth = 0
    quote = False
    escaped = False
    for char in text:
        if not in_insert:
            if text.startswith("INSERT INTO `jamb_question`", max(0, len(buffer))):
                pass
        # A simpler and robust enough extractor for this dump: match tuple blocks after INSERT lines.
    pattern = re.compile(r"\((\d+,\s*\d+,\s*'(?:[^'\\]|\\.|'')*'.*?)\)(?:,|;)", re.S)
    for match in pattern.finditer(text):
        yield "(" + match.group(1) + ")"


def literal_sql_tuple(chunk: str):
    text = chunk.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    fields = []
    current = []
    in_quote = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_quote:
            if char == "\\" and index + 1 < len(text):
                current.append(text[index + 1])
                index += 2
                continue
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    current.append("'")
                    index += 2
                    continue
                in_quote = False
                index += 1
                continue
            current.append(char)
            index += 1
            continue
        if char == "'":
            in_quote = True
            index += 1
            continue
        if char == ",":
            fields.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    fields.append("".join(current).strip())
    normalized = []
    for value in fields:
        if value.upper() == "NULL":
            normalized.append(None)
        elif re.fullmatch(r"-?\d+", value or ""):
            normalized.append(int(value))
        else:
            normalized.append(value)
    return normalized


def iter_sql_rows():
    seen_files = set()
    for path in SQL_SOURCES:
        if not path.exists() or path in seen_files:
            continue
        seen_files.add(path)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for chunk in sql_tuple_chunks(text):
            try:
                qid, qnumber, raw_subject, year, instruction, question, ranswer, answer1, answer2, answer3, *_rest = literal_sql_tuple(chunk)
            except Exception:
                continue
            image = ""
            if len(_rest) >= 4:
                image = clean_text(_rest[3])
            subject = subject_name(raw_subject)
            question_text = clean_text(" ".join(part for part in [instruction, question] if part))
            correct = clean_option(ranswer)
            options = [correct, clean_option(answer1), clean_option(answer2), clean_option(answer3)]
            ok, reason = row_is_valid(subject, question_text, options, correct, image)
            yield {
                "subject": subject,
                "year": year,
                "question": question_text,
                "options": options,
                "correct": correct,
                "image": image,
                "ok": ok,
                "reason": reason,
                "source": str(path),
            }


def collect_rows():
    rows_by_subject: dict[str, OrderedDict[str, dict]] = {subject: OrderedDict() for subject in MINIMUM_IMPORT}
    rejected = Counter()
    for row in list(iter_audit_rows() or []) + list(iter_sql_rows()):
        if not row.get("subject"):
            rejected["unsupported_subject"] += 1
            continue
        if not row["ok"]:
            rejected[row["reason"]] += 1
            continue
        signature = normalize_signature(row["question"])
        subject_rows = rows_by_subject[row["subject"]]
        if signature in subject_rows:
            rejected["duplicate_question"] += 1
            continue
        row["options"] = stable_options(row["options"], row["correct"], signature)
        subject_rows[signature] = row
    return {subject: list(rows.values()) for subject, rows in rows_by_subject.items()}, rejected


def stable_options(options: list[str], correct: str, signature: str) -> list[str]:
    unique = []
    for option in options:
        if normalize_signature(option) not in {normalize_signature(row) for row in unique}:
            unique.append(option)
    # Keep A-D labels stable and deterministic; do not shuffle during exams.
    if correct not in unique:
        unique.insert(0, correct)
    return unique[:4]


def bulk_create_subject_questions(*, bank, admin, jamb, subject_label: str, rows: list[dict]):
    questions = [
        Question(
            question_bank=bank,
            created_by=admin,
            subject=jamb,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=row["question"],
            rich_stem="",
            topic=f"{subject_label}: JAMB Review",
            difficulty=CBTQuestionDifficulty.MEDIUM,
            marks=Decimal("1.00"),
            source_reference=SOURCE,
            is_active=True,
        )
        for row in rows
    ]
    Question.objects.bulk_create(questions, batch_size=500)
    questions = list(
        Question.objects.filter(question_bank=bank, source_reference=SOURCE).order_by("id")
    )
    option_rows = []
    correct_labels = {}
    for question, row in zip(questions, rows):
        correct_sig = normalize_signature(row["correct"])
        for pos, option_text in enumerate(row["options"], start=1):
            label = chr(64 + pos)
            option_rows.append(
                Option(question=question, label=label, option_text=option_text, sort_order=pos)
            )
            if normalize_signature(option_text) == correct_sig:
                correct_labels[question.id] = label
    Option.objects.bulk_create(option_rows, batch_size=1000)
    answers = [
        CorrectAnswer(
            question=question,
            note=f"Verified answer: {rows[index]['correct']}. Source year: {rows[index].get('year') or 'review bank'}.",
            is_finalized=True,
        )
        for index, question in enumerate(questions)
    ]
    CorrectAnswer.objects.bulk_create(answers, batch_size=500)
    answers = list(CorrectAnswer.objects.filter(question__question_bank=bank).order_by("question_id"))
    options = Option.objects.filter(question__question_bank=bank)
    option_by_question_label = {(option.question_id, option.label): option.id for option in options}
    through = CorrectAnswer.correct_options.through
    through_rows = []
    for answer in answers:
        label = correct_labels.get(answer.question_id)
        option_id = option_by_question_label.get((answer.question_id, label))
        if option_id:
            through_rows.append(through(correctanswer_id=answer.id, option_id=option_id))
    through.objects.bulk_create(through_rows, batch_size=1000)
    return len(questions)


def run():
    rows_by_subject, rejected = collect_rows()
    insufficient = {
        subject: len(rows)
        for subject, rows in rows_by_subject.items()
        if len(rows) < MINIMUM_IMPORT[subject]
    }
    if insufficient:
        raise RuntimeError(f"Insufficient clean rows: {insufficient}")

    User = get_user_model()
    admin = User.objects.filter(is_superuser=True).order_by("id").first() or User.objects.order_by("id").first()
    session = AcademicSession.objects.order_by("-id").first()
    term = Term.objects.order_by("-id").first()
    ss2 = AcademicClass.objects.filter(code__icontains="SS2").order_by("id").first() or AcademicClass.objects.order_by("id").first()
    jamb, _ = Subject.objects.get_or_create(code="JAMB", defaults={"name": "JAMB UTME Practice"})

    with transaction.atomic():
        QuestionBank.objects.filter(subject=jamb, name__startswith="JAMB Review Bank ").delete()
        Question.objects.filter(subject=jamb, source_reference=SOURCE).delete()

    created = {}
    for subject, rows in rows_by_subject.items():
        with transaction.atomic():
            bank = QuestionBank.objects.create(
                name=f"JAMB Review Bank {subject} 2026",
                description=(
                    "Strictly filtered JAMB practice rows. No missing-image questions, no placeholders, "
                    "no duplicated options. Review before opening exams."
                ),
                owner=admin,
                subject=jamb,
                academic_class=ss2,
                session=session,
                term=term,
                is_active=True,
            )
            created[subject] = bulk_create_subject_questions(
                bank=bank,
                admin=admin,
                jamb=jamb,
                subject_label=subject,
                rows=rows,
            )

    return {
        "created_questions": created,
        "total_created": sum(created.values()),
        "rejected": dict(rejected),
        "source": SOURCE,
    }


if __name__ == "__main__":
    print(run())
