import csv
import hashlib
import html
import json
import os
import re
import shutil
from decimal import Decimal
from pathlib import Path

import django
from django.contrib.auth import get_user_model
from django.core.files import File
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


SOURCE = "EXAMGUIDE-JAMB-ALL-20260619"
INPUT_JSON = Path(os.environ.get("EXAMGUIDE_JAMB_JSON", "/tmp/examguide-jamb-all-20260619/examguide_jamb_raw_all.json"))
OUTPUT_DIR = Path(os.environ.get("EXAMGUIDE_JAMB_IMPORT_OUT", "/tmp/examguide-jamb-all-20260619-import"))
IMAGE_ROOT = Path(os.environ.get("EXAMGUIDE_OBJ_ROOT", "/tmp/examguide-obj"))
MIN_CLEAN_BY_SUBJECT = int(os.environ.get("EXAMGUIDE_MIN_CLEAN_BY_SUBJECT", "80"))

ALL_SUBJECTS = [
    "English",
    "Mathematics",
    "Physics",
    "Chemistry",
    "Biology",
    "Government",
    "Commerce",
    "Economics",
    "Accounting",
    "CRS",
    "Literature",
    "Computer",
    "Geography",
    "Agriculture",
]
_requested_subjects = [
    item.strip()
    for item in os.environ.get("EXAMGUIDE_SUBJECTS", "").split(",")
    if item.strip()
]
SUBJECTS = _requested_subjects or ALL_SUBJECTS

BAD_TOKENS = ("??", "\ufffd", "Ã", "Â", "â€")
DIAGRAM_TERMS = (
    "diagram",
    "figure",
    "image below",
    "shown below",
    "map below",
    "graph below",
    "illustration below",
    "specimen",
)
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "by", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "that",
    "the", "their", "this", "to", "with", "which", "what", "when", "where",
}
SUPERS = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
SUBS = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def normalize_path(value):
    text = html.unescape(str(value or "")).strip().strip('"').strip("'")
    text = text.replace("\\", "/")
    marker = "/app/res/data/em1/obj/"
    lower = text.lower()
    idx = lower.find(marker)
    if idx >= 0:
        return IMAGE_ROOT / text[idx + len(marker):]
    marker2 = "/res/data/em1/obj/"
    idx = lower.find(marker2)
    if idx >= 0:
        return IMAGE_ROOT / text[idx + len(marker2):]
    return Path(text)


def image_sources(*html_values):
    refs = []
    for value in html_values:
        for match in re.finditer(r"""(?is)<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>""", str(value or "")):
            refs.append(match.group(1))
    return refs


def convert_positioned_spans(value):
    text = str(value or "")

    def repl(match):
        tag = match.group(0)
        body = re.sub(r"<[^>]+>", "", match.group(2))
        if re.search(r"top\s*:\s*-\d", tag, re.I):
            return body.translate(SUPERS)
        if re.search(r"top\s*:\s*\d", tag, re.I):
            return body.translate(SUBS)
        return body

    return re.sub(r"(?is)<span\b([^>]*)>(.*?)</span>", repl, text)


def clean_html(value):
    text = html.unescape(convert_positioned_spans(value))
    text = re.sub(r"(?is)<img\b[^>]*>", " ", text)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(div|p|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def sanitize_rich(value):
    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<img\b[^>]*>", "", text)
    text = re.sub(r"(?is)<script\b.*?</script>", "", text)
    text = re.sub(r"(?is)<style\b.*?</style>", "", text)
    text = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", text)
    text = re.sub(r"javascript:", "", text, flags=re.I)
    return text.strip()


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
    first_part = solution[:360]
    first_sig = sig(first_part)
    solution_tokens = set(tokens(solution))
    first_tokens = set(tokens(first_part))
    scored = []
    for index, option in enumerate(options):
        option_sig = sig(option)
        option_tokens = set(tokens(option))
        score = 0
        if option_sig and option_sig in first_sig:
            score += 18
        elif option_sig and option_sig in solution_sig:
            score += 9
        if option_sig and re.search(rf"\b{re.escape(option_sig)}\b", first_sig):
            score += 8
        score += len(option_tokens & first_tokens) * 3
        score += len(option_tokens & solution_tokens)
        scored.append((score, index))
    scored.sort(reverse=True)
    if not scored or scored[0][0] < 5:
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


def reject_reason(subject, stem, options, explanation, image_paths, raw_html):
    full_text = " ".join([stem, explanation] + options)
    if len(stem.split()) <= 5 or len(stem) < 18:
        return "too_short"
    if any(token in full_text for token in BAD_TOKENS):
        return "bad_encoding_or_placeholder"
    if len(options) != 4 or any(not option for option in options):
        return "blank_or_missing_option"
    if len({sig(option) for option in options}) != 4:
        return "duplicate_options"
    lower = " ".join([stem, raw_html]).lower()
    if any(term in lower for term in DIAGRAM_TERMS):
        if not image_paths:
            return "diagram_without_image_reference"
        if not all(path.exists() for path in image_paths[:1]):
            return "diagram_image_missing"
    if "correct answer" in lower or re.search(r"\banswer\s*:", lower):
        return "answer_leak"
    return ""


def collect_rows():
    payload = json.loads(INPUT_JSON.read_text(encoding="utf-8-sig"))
    rows_by_subject = {subject: [] for subject in SUBJECTS}
    rejected = []
    seen = {subject: set() for subject in SUBJECTS}
    for raw in payload:
        subject = str(raw.get("bank_subject") or "").strip()
        if subject not in rows_by_subject:
            continue
        stem = clean_html(raw.get("question_html"))
        rich_stem = sanitize_rich(raw.get("question_html"))
        option_html = list(raw.get("options_html") or [])
        options = [clean_html(option) for option in option_html[:4]]
        explanation = clean_html(raw.get("explanation_html"))
        topic = clean_html(raw.get("topic"))[:100]
        img_refs = image_sources(raw.get("question_html"), raw.get("explanation_html"))
        image_paths = [normalize_path(ref) for ref in img_refs]
        reason = reject_reason(subject, stem, options, explanation, image_paths, str(raw.get("question_html") or ""))
        correct_index = infer_correct_index(options, explanation) if not reason else None
        if correct_index is None and not reason:
            reason = "ambiguous_correct_answer"
        stem_sig = sig(stem)
        if stem_sig in seen[subject] and not reason:
            reason = "duplicate_stem"
        if reason:
            rejected.append(
                {
                    "subject": subject,
                    "source_folder": raw.get("source_folder"),
                    "season": raw.get("season"),
                    "source_question_no": raw.get("source_question_no"),
                    "reason": reason,
                    "stem": stem,
                }
            )
            continue
        seen[subject].add(stem_sig)
        shuffled_options, correct_label = rotate_options(options, stem, correct_index)
        rows_by_subject[subject].append(
            {
                "stem": stem,
                "rich_stem": rich_stem,
                "options": shuffled_options,
                "correct_label": correct_label,
                "correct_text": options[correct_index],
                "explanation": explanation,
                "topic": f"{subject}: {topic}"[:120],
                "season": raw.get("season"),
                "source_folder": raw.get("source_folder"),
                "source_question_no": raw.get("source_question_no"),
                "image_path": str(image_paths[0]) if image_paths else "",
            }
        )
    return rows_by_subject, rejected


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def attach_image(question, image_path):
    if not image_path:
        return False
    source = Path(image_path)
    if not source.exists():
        return False
    suffix = source.suffix.lower() or ".png"
    name = f"{question.id}-{hashlib.sha1(str(source).encode()).hexdigest()[:12]}{suffix}"
    with source.open("rb") as handle:
        question.stimulus_image.save(f"jamb_examguide/{name}", File(handle), save=True)
    return True


def bulk_create_subject_questions(*, bank, admin, jamb, subject, rows):
    questions = [
        Question(
            question_bank=bank,
            created_by=admin,
            subject=jamb,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=row["stem"],
            rich_stem=row["rich_stem"],
            topic=row["topic"],
            difficulty=CBTQuestionDifficulty.MEDIUM,
            marks=Decimal("1.00"),
            source_type=Question.SourceType.MANUAL,
            source_reference=f"{SOURCE}:{subject}",
            is_active=True,
        )
        for row in rows
    ]
    Question.objects.bulk_create(questions, batch_size=500)
    questions = list(
        Question.objects.filter(
            question_bank=bank,
            source_reference=f"{SOURCE}:{subject}",
        ).order_by("id")
    )
    if len(questions) != len(rows):
        raise RuntimeError(
            f"{subject}: expected {len(rows)} bulk-created questions, found {len(questions)}."
        )

    option_rows = []
    correct_labels = {}
    for question, row in zip(questions, rows):
        correct_labels[question.id] = row["correct_label"]
        for index, option_text in enumerate(row["options"], start=1):
            option_rows.append(
                Option(
                    question=question,
                    label="ABCD"[index - 1],
                    option_text=option_text,
                    sort_order=index,
                )
            )
    Option.objects.bulk_create(option_rows, batch_size=2000)

    answers = [
        CorrectAnswer(
            question=question,
            note=(
                f"{row['explanation']} Source: ExamGuide UTME 2026, "
                f"{row['source_folder']} {row['season']} question {row['source_question_no']}."
            ).strip(),
            is_finalized=True,
        )
        for question, row in zip(questions, rows)
    ]
    CorrectAnswer.objects.bulk_create(answers, batch_size=1000)
    answers = list(
        CorrectAnswer.objects.filter(question__question_bank=bank).order_by("question_id")
    )
    option_by_question_label = {
        (option.question_id, option.label): option.id
        for option in Option.objects.filter(question__question_bank=bank).only(
            "id",
            "question_id",
            "label",
        )
    }
    through = CorrectAnswer.correct_options.through
    through.objects.bulk_create(
        [
            through(
                correctanswer_id=answer.id,
                option_id=option_by_question_label[
                    (answer.question_id, correct_labels[answer.question_id])
                ],
            )
            for answer in answers
        ],
        batch_size=2000,
    )

    images = 0
    for question, row in zip(questions, rows):
        if row["image_path"] and attach_image(question, row["image_path"]):
            images += 1
    return len(questions), images


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows_by_subject, rejected = collect_rows()
    clean_summary = [
        {"subject": subject, "clean_rows": len(rows)}
        for subject, rows in rows_by_subject.items()
    ]
    insufficient = {
        subject: len(rows)
        for subject, rows in rows_by_subject.items()
        if len(rows) < MIN_CLEAN_BY_SUBJECT
    }
    if insufficient:
        write_csv(OUTPUT_DIR / "rejected_rows.csv", rejected, ["subject", "source_folder", "season", "source_question_no", "reason", "stem"])
        write_csv(OUTPUT_DIR / "clean_summary.csv", clean_summary, ["subject", "clean_rows"])
        raise RuntimeError(f"Insufficient clean rows; refusing import: {insufficient}")

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
    jamb, _ = Subject.objects.get_or_create(code="JAMB", defaults={"name": "JAMB UTME Practice"})

    created_summary = []
    with transaction.atomic():
        for subject in SUBJECTS:
            QuestionBank.objects.filter(subject=jamb, name=f"JAMB Review Bank {subject} 2026").delete()
            Question.objects.filter(subject=jamb, source_reference=f"{SOURCE}:{subject}").delete()

    for subject, rows in rows_by_subject.items():
        with transaction.atomic():
            bank = QuestionBank.objects.create(
                name=f"JAMB Review Bank {subject} 2026",
                description=(
                    "Decoded from local TestDriller/ExamGuide UTME content and strictly filtered "
                    "for complete stems, four options, verified answer explanations, and available diagrams."
                ),
                owner=admin,
                subject=jamb,
                academic_class=ss2,
                session=session,
                term=term,
                is_active=True,
            )
            created, images = bulk_create_subject_questions(
                bank=bank,
                admin=admin,
                jamb=jamb,
                subject=subject,
                rows=rows,
            )
        created_summary.append({"subject": subject, "created": created, "images": images})

    write_csv(OUTPUT_DIR / "rejected_rows.csv", rejected, ["subject", "source_folder", "season", "source_question_no", "reason", "stem"])
    write_csv(OUTPUT_DIR / "clean_summary.csv", clean_summary, ["subject", "clean_rows"])
    write_csv(OUTPUT_DIR / "created_summary.csv", created_summary, ["subject", "created", "images"])
    return {
        "source": SOURCE,
        "created_total": sum(row["created"] for row in created_summary),
        "created": created_summary,
        "rejected_rows": len(rejected),
        "output_dir": str(OUTPUT_DIR),
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
