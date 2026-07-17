"""Generate the official Third Term examination readiness issue register."""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "core.settings"))

import django

django.setup()

from weasyprint import HTML

from apps.cbt.models import CBTExamStatus, CBTQuestionType, Exam


OUTPUT = Path(
    os.getenv(
        "NDGA_READINESS_PDF_PATH",
        str(ROOT / "NDGA-Third-Term-Exam-Readiness-Issues-2026-06-30.pdf"),
    )
)
IMPORT_TAG = "THIRD_TERM_EXAM_20260629"

MISSING_ROWS = [
    ("JS1", "Social & Citizenship Studies", "Paper not supplied"),
    ("JS1", "Intermediate Science", "Paper not supplied"),
    ("JS1", "CCA", "Paper not supplied"),
    ("JS1", "PHE", "Paper not supplied"),
    ("JS1", "Igbo Language", "Paper not supplied"),
    ("JS2", "Basic Technology", "Paper not supplied"),
    ("JS2", "PHE", "Paper not supplied"),
    ("JS2", "Yoruba Language", "Paper not supplied"),
    ("SS1", "Chemistry", "Paper not supplied"),
    ("SS2", "Mathematics", "Paper not supplied"),
    ("SS2", "Chemistry", "Paper not supplied"),
    ("SS2", "Garment Making Theory", "Paper not supplied"),
    ("SS2", "Further Mathematics", "Paper not supplied"),
]

INVALID_ROWS = [
    ("JS1", "Hausa Language", "Options are not safely labelled A-D; answer mapping is unreliable"),
    ("JS2", "Hausa Language", "Options are not safely labelled A-D; answer mapping is unreliable"),
    ("SS1", "Agricultural Science", "49 answers detected for 50 objective questions"),
    ("SS2", "Biology", "Supplied source file is empty (0 bytes)"),
    ("SS2", "Literature", "No usable theory section detected"),
]

LANGUAGE_ROWS = [
    ("JS1, JS2, SS1, SS2", "Chinese", "No paper and no teacher assignment"),
    ("JS1, JS2, SS1, SS2", "Sign Language", "No paper and no teacher assignment"),
    ("JS1, JS2", "German Language", "No paper and no teacher assignment"),
]


def table(title, rows):
    body = "".join(
        "<tr>"
        f"<td>{html.escape(str(class_name))}</td>"
        f"<td>{html.escape(str(subject_name))}</td>"
        f"<td>{html.escape(str(issue))}</td>"
        "</tr>"
        for class_name, subject_name, issue in rows
    )
    return (
        f"<h2>{html.escape(title)}</h2>"
        "<table><thead><tr><th>Class</th><th>Subject</th><th>Status / Issue</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def build_pdf():
    imported = Exam.objects.filter(description__contains=IMPORT_TAG).select_related(
        "academic_class",
        "subject",
    )
    ready = list(
        imported.filter(status=CBTExamStatus.ACTIVE)
        .order_by("academic_class__code", "subject__name")
    )
    drafts = list(
        imported.filter(status=CBTExamStatus.DRAFT)
        .order_by("academic_class__code", "subject__name")
    )
    draft_rows = [
        (
            exam.academic_class.code,
            exam.subject.name,
            exam.activation_comment or "Question/answer count or final readiness review required",
        )
        for exam in drafts
    ]
    ready_rows = [
        (
            exam.academic_class.code,
            exam.subject.name,
            f"READY - {exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE).count()} "
            f"objective + on-screen theory; {exam.schedule_start:%d %b %Y %H:%M} WAT",
        )
        for exam in ready
    ]
    document = f"""
    <!doctype html>
    <html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 13mm; @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #64748b; }} }}
      body {{ font-family: DejaVu Sans, Arial, sans-serif; color: #172033; font-size: 9pt; line-height: 1.35; }}
      h1 {{ color: #0b2545; text-align: center; font-size: 17pt; margin: 0 0 4px; }}
      .subtitle {{ text-align: center; font-size: 11pt; color: #334155; margin-bottom: 14px; }}
      h2 {{ color: #0b2545; font-size: 11pt; margin: 13px 0 5px; page-break-after: avoid; }}
      .summary {{ border: 1px solid #d6a72f; background: #fffaf0; padding: 8px; border-radius: 5px; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 7px; font-size: 7.7pt; }}
      th {{ background: #0b2545; color: white; text-align: left; padding: 4px 5px; }}
      td {{ border: 0.5px solid #cbd5e1; padding: 4px 5px; vertical-align: top; }}
      tr:nth-child(even) td {{ background: #f8fafc; }}
      th:nth-child(1), td:nth-child(1) {{ width: 17%; }}
      th:nth-child(2), td:nth-child(2) {{ width: 27%; }}
      .page-break {{ page-break-before: always; }}
      .note {{ margin-top: 12px; border-left: 4px solid #b91c1c; padding: 7px 9px; background: #fff1f2; }}
    </style></head><body>
      <h1>NOTRE DAME GIRLS' ACADEMY, KUJE</h1>
      <div class="subtitle"><b>Third Term Examination Readiness and Issue Register</b><br>
      2025/2026 Academic Session &middot; Examination: 6-14 July 2026 &middot; Updated: 30 June 2026</div>
      <div class="summary"><b>Readiness summary:</b> {len(ready)} papers passed the final deterministic gate;
      {len(drafts)} imported papers remain in Draft; {len(MISSING_ROWS)} timetable papers are missing;
      {len(INVALID_ROWS)} supplied papers are invalid or incomplete.</div>
      <h2>Final safety standard</h2>
      <p>A ready paper has complete objective structure; exactly one finalized answer per objective;
      20 objective marks and 30 theory marks; a complete on-screen theory section; no broken placeholder
      or replacement character; clean powers, superscripts and scientific units; no unexplained diagram
      reference; and a timetable-controlled start/end window.</p>
      {table("Exam-only languages excluded from all result calculations", LANGUAGE_ROWS)}
      {table("Missing timetable papers", MISSING_ROWS)}
      {table("Invalid or incomplete supplied papers", INVALID_ROWS)}
      {table("Imported papers held in Draft", draft_rows)}
      <div class="page-break"></div>
      {table("Papers cleared by the final readiness gate", ready_rows)}
      <div class="note"><b>Important:</b> Draft papers must not be activated until corrected and rechecked.
      Chinese, Sign Language and German Language must not contribute to result totals, averages, positions,
      awards, analytics or term-result PDFs.</div>
    </body></html>
    """
    HTML(string=document, base_url=str(ROOT)).write_pdf(str(OUTPUT))
    print(
        {
            "output": str(OUTPUT),
            "ready": len(ready),
            "draft": len(drafts),
            "missing": len(MISSING_ROWS),
            "invalid": len(INVALID_ROWS),
        }
    )


if __name__ == "__main__":
    build_pdf()
