"""Create the management PDF for all published defects and unavailable papers."""

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

from apps.academics.models import AcademicSession, TeacherSubjectAssignment, Term
from apps.cbt.models import CBTExamStatus, CBTQuestionType, Exam
from scripts.import_third_term_exams_20260629 import EXPECTED, IMPORT_TAG, SOURCES, SOURCE_ROOT


OUTPUT = Path(
    os.getenv(
        "NDGA_EXAM_ISSUE_PDF",
        str(ROOT / "SCHOOL FOLDER" / "NDGA Third Term Examination Paper Issues - 2026-07-01.pdf"),
    )
)


def _table(title, rows):
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
        "<table><thead><tr><th>Class</th><th>Subject</th><th>Paper status</th><th>Exact issue / note</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def build():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    assignments = {
        (row.academic_class.code, row.subject.code): row
        for row in TeacherSubjectAssignment.objects.filter(
            session=session,
            term=term,
            is_active=True,
        ).select_related("subject", "academic_class")
    }
    exams = list(
        Exam.objects.filter(
            description__contains=IMPORT_TAG,
            status=CBTExamStatus.ACTIVE,
        )
        .select_related("academic_class", "subject")
        .order_by("academic_class__code", "subject__name")
    )
    exam_map = {(row.academic_class.code, row.subject.code): row for row in exams}
    issues = []
    ready = []
    for exam in exams:
        objective_count = exam.exam_questions.filter(
            question__question_type=CBTQuestionType.OBJECTIVE
        ).count()
        theory_count = exam.exam_questions.exclude(
            question__question_type=CBTQuestionType.OBJECTIVE
        ).count()
        note = (exam.activation_comment or "").strip()
        row = (
            exam.academic_class.code,
            exam.subject.name,
            f"Published: {objective_count} objective, {theory_count} theory section",
            note or "No known source defect after final review.",
        )
        if "SOURCE ISSUE" in note.upper():
            issues.append(row)
        else:
            ready.append(row)

    unavailable = []
    for key in EXPECTED:
        if key in exam_map:
            continue
        assignment = assignments.get(key)
        rel_paths = SOURCES.get(key)
        subject_name = assignment.subject.name if assignment else key[1]
        if not assignment:
            reason = "No active teacher assignment exists for this timetable subject."
        elif not rel_paths:
            reason = "No examination paper was supplied."
        else:
            paths = [SOURCE_ROOT / value for value in rel_paths]
            missing = [path.name for path in paths if not path.is_file()]
            empty = [path.name for path in paths if path.is_file() and path.stat().st_size == 0]
            if missing:
                reason = "Source document not found: " + ", ".join(missing)
            elif empty:
                reason = "Source document is empty: " + ", ".join(empty)
            else:
                reason = "Non-empty paper exists but was not published; IT investigation required."
        unavailable.append((key[0], subject_name, "Not published", reason))

    document = f"""
    <!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 12mm; @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 8pt; color: #64748b; }} }}
      body {{ font-family: DejaVu Sans, Arial, sans-serif; color: #172033; font-size: 8.4pt; line-height: 1.35; }}
      h1 {{ color: #0b2545; text-align: center; font-size: 16pt; margin: 0 0 3px; }}
      .subtitle {{ text-align: center; color: #475569; margin-bottom: 12px; }}
      .summary {{ border: 1px solid #d6a72f; background: #fffaf0; padding: 8px; }}
      h2 {{ color: #0b2545; font-size: 11pt; margin: 12px 0 5px; page-break-after: avoid; }}
      table {{ width: 100%; border-collapse: collapse; font-size: 7.2pt; margin-bottom: 8px; }}
      th {{ background: #0b2545; color: white; text-align: left; padding: 4px; }}
      td {{ border: .5px solid #cbd5e1; padding: 4px; vertical-align: top; }}
      tr:nth-child(even) td {{ background: #f8fafc; }}
      th:nth-child(1), td:nth-child(1) {{ width: 11%; }}
      th:nth-child(2), td:nth-child(2) {{ width: 23%; }}
      th:nth-child(3), td:nth-child(3) {{ width: 24%; }}
      .warning {{ border-left: 4px solid #b91c1c; padding: 7px; background: #fff1f2; }}
    </style></head><body>
      <h1>NOTRE DAME GIRLS' ACADEMY, KUJE</h1>
      <div class="subtitle"><b>Third Term Examination Paper Issues and Missing Content</b><br>
      2025/2026 Session · Issued 1 July 2026</div>
      <div class="summary"><b>Summary:</b> {len(exams)} non-empty supplied papers are published:
      {len(ready)} with no known defect and {len(issues)} published with declared source issues.
      {len(unavailable)} timetable entries are not published because the paper is absent, empty, or has no assignment.</div>
      <p class="warning"><b>Management instruction applied:</b> source defects were not silently corrected
      or filled with invented content. Missing questions, answer keys, theory sections and malformed formulas
      are disclosed below exactly so the responsible teacher can send corrections.</p>
      {_table("Published papers with declared source issues", issues)}
      {_table("Unavailable, empty or unsupplied timetable papers", unavailable)}
      {_table("Published papers with no known source defect", ready)}
    </body></html>
    """
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=document, base_url=str(ROOT)).write_pdf(str(OUTPUT))
    print(
        {
            "output": str(OUTPUT),
            "published": len(exams),
            "published_with_issues": len(issues),
            "published_without_known_issue": len(ready),
            "unavailable": len(unavailable),
        }
    )


if __name__ == "__main__":
    build()
