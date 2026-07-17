"""Generate the final management readiness/issue register for Third Term exams."""

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

from apps.academics.models import AcademicSession, Term
from apps.cbt.models import CBTExamStatus, CBTQuestionType, Exam
from scripts.finalize_third_term_all_papers_20260702 import (
    IMPORT_TAG,
    validate_exam,
)


OUTPUT = ROOT / "SCHOOL FOLDER" / (
    "NDGA Third Term Examination Final Readiness and Issues - 2026-07-02.pdf"
)


def _table(title, rows, empty_message):
    if not rows:
        body = (
            '<tr><td colspan="4" class="empty">'
            f"{html.escape(empty_message)}</td></tr>"
        )
    else:
        body = "".join(
            "<tr>"
            f"<td>{html.escape(str(row[0]))}</td>"
            f"<td>{html.escape(str(row[1]))}</td>"
            f"<td>{html.escape(str(row[2]))}</td>"
            f"<td>{html.escape(str(row[3]))}</td>"
            "</tr>"
            for row in rows
        )
    return (
        f"<h2>{html.escape(title)}</h2>"
        "<table><thead><tr><th>Class</th><th>Subject</th>"
        "<th>Paper</th><th>Audit result</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def build():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    exams = list(
        Exam.objects.filter(
            session=session,
            term=term,
            description__contains=IMPORT_TAG,
        )
        .select_related("academic_class", "subject", "blueprint")
        .order_by("academic_class__code", "subject__name")
    )

    ready = []
    issues = []
    drafts = []
    for exam in exams:
        objective_count = exam.exam_questions.filter(
            question__question_type__in=["OBJECTIVE", "MULTI_SELECT"]
        ).count()
        theory_count = exam.exam_questions.exclude(
            question__question_type__in=["OBJECTIVE", "MULTI_SELECT"]
        ).count()
        paper = f"{objective_count} objective; {theory_count} theory page(s)"
        key = (exam.academic_class.code, exam.subject.name)
        if exam.status != CBTExamStatus.ACTIVE:
            drafts.append((*key, paper, f"Status is {exam.status}."))
            continue
        try:
            validate_exam(
                exam,
                allow_theory_only=(
                    objective_count == 0 and theory_count > 0
                ),
            )
            config = exam.blueprint.section_config or {}
            if config.get("source_validation") != "FULLY_VALIDATED_20260702":
                raise RuntimeError("final source-validation marker is absent")
            if not exam.blueprint.shuffle_questions:
                raise RuntimeError("question shuffling is off")
            if objective_count and not exam.blueprint.shuffle_options:
                raise RuntimeError("option shuffling is off")
        except Exception as exc:
            issues.append((*key, paper, str(exc)))
        else:
            ready.append(
                (
                    *key,
                    paper,
                    "ACTIVE — complete content, options/keys, theory layout and shuffle checks passed.",
                )
            )

    document = f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 12mm; @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-size: 8pt; color: #64748b;
      }} }}
      body {{ font-family: DejaVu Sans, Arial, sans-serif; color: #172033;
              font-size: 8.2pt; line-height: 1.35; }}
      h1 {{ color: #0b2545; text-align: center; font-size: 16pt; margin: 0 0 3px; }}
      .subtitle {{ text-align: center; color: #475569; margin-bottom: 12px; }}
      .summary {{ border: 1px solid #16805d; background: #effcf6; padding: 9px; }}
      h2 {{ color: #0b2545; font-size: 11pt; margin: 12px 0 5px;
            page-break-after: avoid; }}
      table {{ width: 100%; border-collapse: collapse; font-size: 7.1pt;
               margin-bottom: 8px; }}
      th {{ background: #0b2545; color: white; text-align: left; padding: 4px; }}
      td {{ border: .5px solid #cbd5e1; padding: 4px; vertical-align: top; }}
      tr:nth-child(even) td {{ background: #f8fafc; }}
      th:nth-child(1), td:nth-child(1) {{ width: 10%; }}
      th:nth-child(2), td:nth-child(2) {{ width: 23%; }}
      th:nth-child(3), td:nth-child(3) {{ width: 24%; }}
      .empty {{ color: #166534; font-weight: bold; text-align: center; padding: 10px; }}
    </style></head><body>
      <h1>NOTRE DAME GIRLS' ACADEMY, KUJE</h1>
      <div class="subtitle"><b>Third Term Examination Final Readiness and Issue Register</b><br>
      2025/2026 Session · Issued 2 July 2026</div>
      <div class="summary"><b>Final summary:</b> {len(exams)} supplied examination papers audited;
      <b>{len(ready)} ready and active</b>, <b>{len(issues)} content/configuration issues</b>,
      and <b>{len(drafts)} draft/inactive papers</b>. Objective questions and answer options are
      shuffled by identity, so the keyed answer remains correct after shuffling.</div>
      {_table("Issues requiring correction", issues, "No remaining paper issues were found.")}
      {_table("Draft or inactive papers", drafts, "No supplied paper remains in draft or inactive status.")}
      {_table("Ready and active papers", ready, "No ready papers found.")}
    </body></html>
    """
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=document, base_url=str(ROOT)).write_pdf(str(OUTPUT))
    print(
        {
            "output": str(OUTPUT),
            "papers": len(exams),
            "ready": len(ready),
            "issues": len(issues),
            "draft_or_inactive": len(drafts),
        }
    )


if __name__ == "__main__":
    build()
