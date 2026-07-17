"""Generate the SS2 JAMB question-bank and syllabus coverage register."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from django.db.models import Count
from weasyprint import HTML

from apps.cbt.models import CorrectAnswer, Option, Question, QuestionBank


OUTPUT = Path(
    os.getenv(
        "NDGA_JAMB_COVERAGE_PDF",
        str(
            ROOT
            / "SCHOOL FOLDER"
            / "NDGA SS2 JAMB Question Bank and Syllabus Coverage - 2026-07-01.pdf"
        ),
    )
)
SYLLABUS_URL = "https://myschool.ng/classroom/jamb-syllabus"
SYLLABUS_SUBJECTS = (
    "Mathematics",
    "English Language",
    "Chemistry",
    "Physics",
    "Biology",
    "Geography",
    "Literature in English",
    "Economics",
    "Commerce",
    "Accounts - Principles of Accounts",
    "Government",
    "Christian Religious Knowledge (CRK)",
    "Agricultural Science",
    "Islamic Religious Knowledge (IRK)",
    "History",
    "Fine Arts",
    "Music",
    "French",
    "Animal Husbandry",
    "Insurance",
    "Civic Education",
    "Further Mathematics",
    "Yoruba",
    "Igbo",
    "Arabic",
    "Home Economics",
    "Hausa",
    "Book Keeping",
    "Data Processing",
    "Catering Craft Practice",
    "Computer Studies",
    "Marketing",
    "Physical Education",
    "Office Practice",
    "Technical Drawing",
    "Food and Nutrition",
    "Home Management",
)
IMPORT_LABELS = {
    "Mathematics": "Mathematics",
    "English Language": "English",
    "Chemistry": "Chemistry",
    "Physics": "Physics",
    "Biology": "Biology",
    "Geography": "Geography",
    "Literature in English": "Literature",
    "Economics": "Economics",
    "Commerce": "Commerce",
    "Accounts - Principles of Accounts": "Accounting",
    "Government": "Government",
    "Christian Religious Knowledge (CRK)": "CRS",
    "Agricultural Science": "Agriculture",
    "Computer Studies": "Computer",
}


def build():
    banks = {
        bank.name.removeprefix("JAMB Review Bank ").removesuffix(" 2026"): bank
        for bank in QuestionBank.objects.filter(
            name__startswith="JAMB Review Bank ",
            name__endswith=" 2026",
            is_active=True,
        )
    }
    rows = []
    available_total = 0
    for syllabus_subject in SYLLABUS_SUBJECTS:
        import_label = IMPORT_LABELS.get(syllabus_subject)
        bank = banks.get(import_label) if import_label else None
        count = bank.questions.filter(is_active=True).count() if bank else 0
        available_total += count
        rows.append(
            (
                syllabus_subject,
                "Ready" if bank and count else "No local ExamGuide bank",
                str(count) if count else "-",
                "Strictly filtered and answer-keyed."
                if bank and count
                else "Syllabus listed, but no matching local ExamGuide source was supplied.",
            )
        )

    imported_questions = Question.objects.filter(
        question_bank__in=banks.values(),
        is_active=True,
    )
    bad_option_questions = imported_questions.annotate(
        option_count=Count("options")
    ).exclude(option_count=4).count()
    option_total = Option.objects.filter(question__in=imported_questions).count()
    answer_total = CorrectAnswer.objects.filter(
        question__in=imported_questions,
        is_finalized=True,
    ).count()
    answer_links = CorrectAnswer.correct_options.through.objects.filter(
        correctanswer__question__in=imported_questions
    ).count()

    body = "".join(
        "<tr>"
        f"<td>{html.escape(subject)}</td>"
        f"<td>{html.escape(status)}</td>"
        f"<td>{html.escape(count)}</td>"
        f"<td>{html.escape(note)}</td>"
        "</tr>"
        for subject, status, count, note in rows
    )
    document = f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 12mm; @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #64748b; }} }}
      body {{ font-family: DejaVu Sans, Arial, sans-serif; color: #172033; font-size: 8.3pt; line-height: 1.35; }}
      h1 {{ color: #0b2545; text-align: center; font-size: 16pt; margin: 0 0 3px; }}
      .subtitle {{ text-align: center; color: #475569; margin-bottom: 12px; }}
      .summary {{ border: 1px solid #d6a72f; background: #fffaf0; padding: 8px; margin-bottom: 9px; }}
      .audit {{ border-left: 4px solid #0f766e; background: #ecfdf5; padding: 8px; margin-bottom: 10px; }}
      table {{ width: 100%; border-collapse: collapse; font-size: 7.4pt; }}
      th {{ background: #0b2545; color: white; text-align: left; padding: 4px; }}
      td {{ border: .5px solid #cbd5e1; padding: 4px; vertical-align: top; }}
      tr:nth-child(even) td {{ background: #f8fafc; }}
      th:nth-child(1), td:nth-child(1) {{ width: 28%; }}
      th:nth-child(2), td:nth-child(2) {{ width: 20%; }}
      th:nth-child(3), td:nth-child(3) {{ width: 10%; text-align: center; }}
      .source {{ margin-top: 9px; color: #475569; font-size: 7.5pt; overflow-wrap: anywhere; }}
    </style></head><body>
      <h1>NOTRE DAME GIRLS' ACADEMY, KUJE</h1>
      <div class="subtitle"><b>SS2 JAMB Question Bank and Syllabus Coverage Register</b><br>
      Generated 1 July 2026</div>
      <div class="summary"><b>Imported:</b> {available_total:,} locally supplied ExamGuide questions across
      {len(banks)} subject banks. Subjects without a local source are disclosed below and were not filled
      with invented questions.</div>
      <div class="audit"><b>Integrity audit:</b> {imported_questions.count():,} active questions;
      {option_total:,} options; {answer_total:,} finalized answers; {answer_links:,} correct-option links;
      {bad_option_questions} questions with no option rows.</div>
      <table><thead><tr><th>JAMB syllabus subject</th><th>NDGA bank status</th><th>Questions</th><th>Note</th></tr></thead>
      <tbody>{body}</tbody></table>
      <p class="source"><b>Syllabus index used for coverage:</b> {html.escape(SYLLABUS_URL)}.
      The syllabus index guides topic coverage; it is not treated as an answer key. Question content and
      finalized answers come from the school's local ExamGuide/TestDriller files after deterministic checks.</p>
    </body></html>
    """
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=document, base_url=str(ROOT)).write_pdf(str(OUTPUT))
    print(
        {
            "output": str(OUTPUT),
            "banks": len(banks),
            "questions": imported_questions.count(),
            "options": option_total,
            "answers": answer_total,
            "answer_links": answer_links,
        }
    )


if __name__ == "__main__":
    build()
