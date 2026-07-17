from __future__ import annotations

import csv
import html
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.prod")

import django

django.setup()

from apps.cbt.models import CorrectAnswer, Question, QuestionBank


OUT_DIR = Path(os.environ.get("JAMB_AUDIT_OUT", "/tmp/jamb-review-bank-20260619"))
INCLUDE_INACTIVE = os.environ.get("JAMB_AUDIT_INCLUDE_INACTIVE", "").lower() in {"1", "true", "yes"}

BAD_ENCODING_TOKENS = ("\u00c3", "\u00c2", "\u00e2", "\ufffd")
FORMAT_TERMS = (
    "word underlined",
    "words underlined",
    "underlined word",
    "underlined words",
    "in italics",
    "italicized word",
    "italicized words",
    "word in bold",
    "words in bold",
    "italics or bold",
    "opposite in meaning",
    "nearest in meaning to the underlined",
)
DIAGRAM_TERMS = (
    "diagram above",
    "diagram below",
    "figure above",
    "figure below",
    "shown below",
    "from the diagram",
    "in the diagram",
    "graph below",
    "map below",
    "image above",
)

SUBJECT_ALLOWED_KEYWORDS = {
    "Mathematics": (
        "equation",
        "triangle",
        "circle",
        "matrix",
        "probability",
        "set",
        "log",
        "angle",
        "root",
        "factor",
        "differentiate",
        "integrate",
        "mean",
        "median",
        "ratio",
        "permutation",
        "variation",
        "surd",
        "line",
        "polygon",
        "bearing",
        "vector",
        "sequence",
    ),
    "Physics": (
        "force",
        "motion",
        "velocity",
        "acceleration",
        "current",
        "voltage",
        "resistance",
        "lens",
        "mirror",
        "wave",
        "heat",
        "pressure",
        "density",
        "momentum",
        "energy",
        "power",
        "magnetic",
        "electric",
        "mass",
        "weight",
        "frequency",
    ),
    "Chemistry": (
        "atom",
        "mole",
        "acid",
        "base",
        "salt",
        "reaction",
        "element",
        "compound",
        "organic",
        "periodic",
        "bond",
        "oxidation",
        "alkane",
        "electrolysis",
        "solution",
        "gas",
        "metal",
        "carbon",
        "hydrogen",
    ),
    "Biology": (
        "cell",
        "plant",
        "animal",
        "organ",
        "tissue",
        "blood",
        "enzyme",
        "photosynthesis",
        "respiration",
        "gene",
        "ecology",
        "reproduction",
        "digestion",
        "excretion",
        "osmosis",
        "diffusion",
    ),
    "Computer": (
        "computer",
        "data",
        "algorithm",
        "hardware",
        "software",
        "cpu",
        "memory",
        "internet",
        "network",
        "database",
        "spreadsheet",
        "keyboard",
        "binary",
        "program",
        "operating system",
    ),
    "Commerce": (
        "trade",
        "business",
        "commerce",
        "retailer",
        "wholesaler",
        "consumer",
        "producer",
        "bank",
        "insurance",
        "transport",
        "warehouse",
        "advertising",
        "market",
        "partnership",
        "company",
        "cheque",
    ),
    "Economics": (
        "demand",
        "supply",
        "price",
        "market",
        "inflation",
        "capital",
        "labour",
        "production",
        "utility",
        "income",
        "tax",
        "population",
        "cost",
        "monopoly",
        "elasticity",
    ),
    "Accounting": (
        "ledger",
        "trial balance",
        "debit",
        "credit",
        "account",
        "cash book",
        "journal",
        "balance sheet",
        "profit",
        "loss",
        "asset",
        "liability",
        "capital",
    ),
    "Government": (
        "constitution",
        "democracy",
        "election",
        "legislature",
        "executive",
        "judiciary",
        "federal",
        "citizen",
        "party",
        "sovereignty",
        "law",
        "state",
        "parliament",
    ),
    "CRS": (
        "jesus",
        "god",
        "moses",
        "abraham",
        "israel",
        "disciple",
        "paul",
        "peter",
        "faith",
        "covenant",
        "sin",
        "prayer",
        "church",
        "prophet",
    ),
    "Literature": (
        "poem",
        "novel",
        "drama",
        "character",
        "plot",
        "theme",
        "metaphor",
        "simile",
        "persona",
        "stanza",
        "act",
        "scene",
        "narrator",
        "lekki",
        "headmaster",
    ),
}


def clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def signature(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def subject_from_bank(bank: QuestionBank) -> str:
    name = bank.name
    name = re.sub(r"^JAMB\s+Review\s+Bank\s+", "", name, flags=re.I)
    name = re.sub(r"^JAMB\s+Review\s+-\s*", "", name, flags=re.I)
    name = re.sub(r"^JAMB\s+Review\s*", "", name, flags=re.I)
    name = re.sub(r"\s+20\d{2}$", "", name).strip()
    return name or bank.subject.name


def rich_has_visible_formatting(value: str) -> bool:
    rich = str(value or "").lower()
    return any(
        token in rich
        for token in (
            "<u",
            "<em",
            "<strong",
            "text-decoration:underline",
            "font-style:italic",
            "font-weight:bold",
            "font-weight: bold",
        )
    )


def issue_flags(subject: str, question: str, options: list[str], correct_count: int, has_image: bool, rich_stem: str = "") -> list[str]:
    text = " ".join([question] + options)
    lower = text.lower()
    issues: list[str] = []
    if len(clean(question)) < 12:
        issues.append("short_question")
    if len(clean(question).split()) <= 5:
        issues.append("too_few_words")
    if "??" in text:
        issues.append("placeholder_question_mark")
    if any(token in text for token in BAD_ENCODING_TOKENS):
        issues.append("bad_encoding")
    if any(term in lower for term in FORMAT_TERMS) and not rich_has_visible_formatting(rich_stem):
        issues.append("formatting_dependency")
    if any(term in lower for term in DIAGRAM_TERMS) and not has_image:
        issues.append("missing_diagram")
    if "correct answer" in lower or "answer:" in lower:
        issues.append("answer_leak")
    if len(options) != 4:
        issues.append(f"option_count_{len(options)}")
    if any(not clean(option) for option in options):
        issues.append("blank_option")
    if any(re.fullmatch(r"option\s+[a-e]", clean(option), re.I) for option in options):
        issues.append("placeholder_option")
    option_sigs = [signature(option) for option in options]
    if len(option_sigs) != len(set(option_sigs)):
        issues.append("duplicate_options")
    if correct_count != 1:
        issues.append(f"correct_count_{correct_count}")
    allowed = SUBJECT_ALLOWED_KEYWORDS.get(subject, ())
    if allowed and not any(re.search(r"\b" + re.escape(word) + r"\b", lower) for word in allowed):
        issues.append("weak_subject_signal")
    return sorted(set(issues))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    banks = QuestionBank.objects.filter(name__icontains="JAMB").select_related("subject").order_by("subject__name", "name")
    summary: list[dict] = []
    issue_rows: list[dict] = []
    all_rows: list[dict] = []
    stem_seen: dict[tuple[str, str], list[int]] = defaultdict(list)

    for bank in banks:
        subject = subject_from_bank(bank)
        questions = (
            Question.objects.filter(question_bank=bank)
            .select_related("subject")
            .prefetch_related("options", "correct_answer__correct_options")
            .order_by("id")
        )
        if not INCLUDE_INACTIVE:
            questions = questions.filter(is_active=True)
        counters: Counter[str] = Counter()
        for question in questions:
            options = list(question.options.order_by("sort_order", "label"))
            try:
                correct_options = list(question.correct_answer.correct_options.all())
            except CorrectAnswer.DoesNotExist:
                correct_options = []
            option_texts = [clean(option.option_text) for option in options]
            flags = issue_flags(
                subject,
                clean(question.stem),
                option_texts,
                len(correct_options),
                bool(question.stimulus_image),
                question.rich_stem,
            )
            counters.update(flags)
            stem_seen[(subject, signature(question.stem))].append(question.id)
            row = {
                "bank_id": bank.id,
                "bank": bank.name,
                "subject": subject,
                "question_id": question.id,
                "topic": question.topic,
                "source_reference": question.source_reference,
                "stem": clean(question.stem),
                "A": option_texts[0] if len(option_texts) > 0 else "",
                "B": option_texts[1] if len(option_texts) > 1 else "",
                "C": option_texts[2] if len(option_texts) > 2 else "",
                "D": option_texts[3] if len(option_texts) > 3 else "",
                "correct_label": ",".join(option.label for option in correct_options),
                "correct_text": " | ".join(clean(option.option_text) for option in correct_options),
                "has_image": "yes" if question.stimulus_image else "no",
                "is_active": "yes" if question.is_active else "no",
                "issues": ";".join(flags),
            }
            all_rows.append(row)
            if flags:
                issue_rows.append(row.copy())
        summary.append({"bank_id": bank.id, "bank": bank.name, "subject": subject, "questions": questions.count(), **dict(counters)})

    duplicate_rows: list[dict] = []
    row_by_id = {int(row["question_id"]): row for row in all_rows}
    for (subject, sig), ids in stem_seen.items():
        if sig and len(ids) > 1:
            duplicate_rows.append({"subject": subject, "signature": sig, "count": len(ids), "question_ids": ",".join(map(str, ids))})
            for question_id in ids:
                row = row_by_id.get(question_id)
                if row and "duplicate_stem" not in row["issues"]:
                    row["issues"] = (row["issues"] + ";duplicate_stem").strip(";")
                    issue_rows.append(row.copy())

    fields = [
        "bank_id",
        "bank",
        "subject",
        "question_id",
        "topic",
        "source_reference",
        "stem",
        "A",
        "B",
        "C",
        "D",
        "correct_label",
        "correct_text",
        "has_image",
        "is_active",
        "issues",
    ]
    write_csv(OUT_DIR / "all_questions_review_pack.csv", all_rows, fields)
    write_csv(OUT_DIR / "audit_issues.csv", issue_rows, fields)
    summary_fields = sorted(set().union(*(row.keys() for row in summary))) if summary else ["bank", "subject", "questions"]
    write_csv(OUT_DIR / "audit_summary.csv", summary, summary_fields)
    write_csv(OUT_DIR / "duplicate_stems.csv", duplicate_rows, ["subject", "signature", "count", "question_ids"])

    for subject in sorted({row["subject"] for row in all_rows}):
        safe_subject = re.sub(r"[^A-Za-z0-9]+", "_", subject).strip("_")
        write_csv(OUT_DIR / f"review_pack_{safe_subject}.csv", [row for row in all_rows if row["subject"] == subject], fields)

    print(f"OUT={OUT_DIR}")
    print(f"banks={len(summary)} questions={len(all_rows)} issue_rows={len(issue_rows)} duplicate_groups={len(duplicate_rows)}")
    for row in summary:
        print(row)


if __name__ == "__main__":
    main()
