import os
import sys
import time
import logging
from decimal import Decimal
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.prod")
django.setup()

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone
from django.utils.html import escape
from weasyprint import HTML

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.academics.models import AcademicClass
from apps.notifications.services import _school_logo_src, send_email_event
from apps.pdfs.services import school_logo_data_uri, school_profile as pdf_school_profile
from apps.results.utils import current_session_term
from apps.results.views import _class_ca_matrix, _student_label


INTERNAL_CLASSES = ("JS1", "JS2", "SS1", "SS2")
SEND_DELAY_SECONDS = 0.35
COMMON_MAIL_DOMAINS = (
    "gmail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "hotmail.com",
    "outlook.com",
)
logging.getLogger("fontTools").setLevel(logging.WARNING)
logging.getLogger("fontTools.subset").setLevel(logging.WARNING)
logging.getLogger("fontTools.ttLib").setLevel(logging.WARNING)


def fmt(value):
    try:
        return f"{Decimal(value):.2f}"
    except Exception:
        return str(value)


def recipient_emails(student):
    profile = getattr(student, "student_profile", None)
    seen = set()
    emails = []
    invalid = []
    for value in [getattr(profile, "guardian_email", ""), student.email]:
        email = (value or "").strip().lower()
        if not email or email in seen:
            continue
        try:
            validate_email(email)
        except ValidationError:
            invalid.append(email)
            continue
        domain = email.rsplit("@", 1)[-1]
        if any(domain.startswith(f"{common}.") for common in COMMON_MAIL_DOMAINS):
            invalid.append(email)
            continue
        seen.add(email)
        emails.append(email)
    return emails, invalid


def render_pdf(*, student, student_number, class_label, session, term, matrix, student_row):
    school = pdf_school_profile()
    logo = school_logo_data_uri()
    student_name = _student_label(student)
    position = student_row.get("position") or "-"
    student_count = matrix.get("student_count") or len(matrix.get("rows") or [])
    subject_rows = []
    for cell in student_row["subjects"]:
        if not cell["offered"]:
            continue
        ca = cell["ca"]
        subject_rows.append(
            {
                "subject": cell["subject"].name,
                "objective": ca["objective"],
                "theory": ca["theory"],
                "total": ca["total"],
            }
        )
    subject_table = "".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td class=\"subject\">{escape(row['subject'])}</td>"
        f"<td>{fmt(row['objective'])}</td>"
        f"<td>{fmt(row['theory'])}</td>"
        f"<td><strong>{fmt(row['total'])}</strong></td>"
        "</tr>"
        for idx, row in enumerate(subject_rows, start=1)
    )
    max_total = Decimal(student_row["offered_count"]) * Decimal("10.00")
    html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: A4 portrait; margin: 16mm; }}
  body {{ font-family: Arial, sans-serif; color: #0f172a; font-size: 10pt; }}
  .header {{ display: table; width: 100%; border-bottom: 3px solid #295b94; padding-bottom: 8px; margin-bottom: 14px; }}
  .logo {{ display: table-cell; width: 70px; vertical-align: top; }}
  .logo img {{ width: 58px; height: 58px; object-fit: contain; }}
  .school {{ display: table-cell; vertical-align: top; }}
  .school h1 {{ margin: 0; color: #295b94; font-size: 16pt; text-transform: uppercase; }}
  .school p {{ margin: 2px 0; color: #c62828; font-weight: 700; }}
  .title {{ text-align: center; margin: 16px 0; }}
  .title h2 {{ margin: 0; font-size: 15pt; text-transform: uppercase; }}
  .title p {{ margin: 4px 0 0; color: #475569; }}
  .summary {{ display: table; width: 100%; margin: 10px 0 14px; border-spacing: 8px; }}
  .card {{ display: table-cell; border: 1px solid #cbd5e1; padding: 9px; border-radius: 6px; }}
  .label {{ font-size: 7.5pt; color: #64748b; text-transform: uppercase; letter-spacing: .08em; }}
  .value {{ margin-top: 4px; font-size: 13pt; font-weight: 700; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th, td {{ border: 1px solid #111827; padding: 6px; text-align: center; }}
  th {{ background: #eaf1f8; text-transform: uppercase; font-size: 8pt; }}
  td.subject {{ text-align: left; }}
  .note {{ margin-top: 16px; color: #475569; font-size: 9pt; line-height: 1.5; }}
  .footer {{ margin-top: 22px; border-top: 1px solid #cbd5e1; padding-top: 8px; font-size: 8pt; color: #64748b; }}
</style>
</head>
<body>
  <div class="header">
    <div class="logo">{'<img src="' + logo + '" alt="Logo">' if logo else ''}</div>
    <div class="school">
      <h1>{escape(school.school_name or "Notre Dame Girls' Academy")}</h1>
      <p>{escape(school.address or 'P.O.Box 46 Kuje Abuja')}</p>
      <div>{escape(school.contact_email or '')} {escape(school.contact_phone or '')}</div>
    </div>
  </div>
  <div class="title">
    <h2>First Continuous Assessment Score Report</h2>
    <p>{escape(session.name)} | {escape(term.get_name_display())}</p>
  </div>
  <div class="summary">
    <div class="card"><div class="label">Student</div><div class="value">{escape(student_name)}</div><div>{escape(student_number)}</div></div>
    <div class="card"><div class="label">Class</div><div class="value">{escape(class_label)}</div></div>
  </div>
  <div class="summary">
    <div class="card"><div class="label">CA1 Total</div><div class="value">{fmt(student_row['total'])}</div><div>Out of {fmt(max_total)}</div></div>
    <div class="card"><div class="label">Average</div><div class="value">{fmt(student_row['average'])}</div></div>
    <div class="card"><div class="label">Position</div><div class="value">{position} of {student_count}</div></div>
  </div>
  <table>
    <thead><tr><th>S/N</th><th>Subject</th><th>Objective</th><th>Theory</th><th>CA1 Total</th></tr></thead>
    <tbody>{subject_table}</tbody>
  </table>
  <p class="note">Please keep this report for your record and contact the school if any clarification is needed.</p>
  <div class="footer">Generated {timezone.localtime(timezone.now()).strftime('%d %B %Y, %I:%M %p')} by NDGA Result Management.</div>
</body>
</html>
"""
    return HTML(string=html, base_url="/app").write_pdf()


def build_email_payload(*, student, student_number, class_label, session, term, matrix, student_row):
    student_name = _student_label(student)
    position = student_row.get("position") or "-"
    student_count = matrix.get("student_count") or len(matrix.get("rows") or [])
    max_total = Decimal(student_row["offered_count"]) * Decimal("10.00")
    subject = f"{student_name} - First C.A. Score Report"
    body_text = (
        f"Your ward, {student_name} ({student_number}), has the following First Continuous Assessment "
        f"summary for {session.name} {term.get_name_display()}:\n\n"
        f"Total Score: {fmt(student_row['total'])} out of {fmt(max_total)}\n"
        f"Average: {fmt(student_row['average'])}\n"
        f"Position: {position} of {student_count}\n\n"
        "Please view the attached PDF for the subject-by-subject breakdown and complete CA1 score report.\n\n"
        "Thank you for your continued support."
    )
    body_html = f"""
<div style="font-size:15px; line-height:1.75; color:#475569;">
  <p style="margin:0 0 14px;">Your ward, <strong>{escape(student_name)}</strong> ({escape(student_number)}), has the following First Continuous Assessment summary for {escape(session.name)} {escape(term.get_name_display())}:</p>
  <table role="presentation" style="width:100%; border-collapse:collapse; margin:16px 0;">
    <tr>
      <td style="padding:14px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc;"><strong>Total Score</strong><br><span style="font-size:22px; color:#0f2747; font-weight:700;">{fmt(student_row['total'])}</span><br><span style="font-size:12px;color:#64748b;">out of {fmt(max_total)}</span></td>
      <td style="padding:14px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc;"><strong>Average</strong><br><span style="font-size:22px; color:#0f2747; font-weight:700;">{fmt(student_row['average'])}</span></td>
      <td style="padding:14px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc;"><strong>Position</strong><br><span style="font-size:22px; color:#0f2747; font-weight:700;">{position} of {student_count}</span></td>
    </tr>
  </table>
  <p style="margin:0 0 14px;">Please view the attached PDF for the subject-by-subject breakdown and complete CA1 score report.</p>
  <p style="margin:0;">Thank you for your continued support.</p>
</div>
"""
    return subject, body_text, body_html


def main():
    send = "--send" in sys.argv
    session, term = current_session_term()
    actor = User.objects.filter(primary_role__code=ROLE_IT_MANAGER, is_active=True).first() or User.objects.filter(is_superuser=True, is_active=True).first()
    school = pdf_school_profile()
    print("mode", "SEND" if send else "DRY_RUN")
    print("context", session.name, term.get_name_display())
    print("email_logo_src", _school_logo_src(profile=school))

    sent_student_ids = set()
    skipped = []
    failures = []
    successes = []
    total_candidates = 0
    for class_code in INTERNAL_CLASSES:
        academic_class = AcademicClass.objects.get(code=class_code, base_class__isnull=True, is_active=True)
        matrix = _class_ca_matrix(session=session, term=term, academic_class=academic_class, component_key="ca1")
        for student_row in matrix["rows"]:
            student = student_row["student"]
            if student.id in sent_student_ids:
                skipped.append((student_row["student_number"], _student_label(student), "duplicate-student-row"))
                continue
            sent_student_ids.add(student.id)
            total_candidates += 1
            emails, invalid_emails = recipient_emails(student)
            for invalid_email in invalid_emails:
                skipped.append((student_row["student_number"], _student_label(student), f"invalid-email:{invalid_email}"))
            if not emails:
                skipped.append((student_row["student_number"], _student_label(student), "no-email"))
                continue
            subject, body_text, body_html = build_email_payload(
                student=student,
                student_number=student_row["student_number"],
                class_label=class_code,
                session=session,
                term=term,
                matrix=matrix,
                student_row=student_row,
            )
            pdf_bytes = render_pdf(
                student=student,
                student_number=student_row["student_number"],
                class_label=class_code,
                session=session,
                term=term,
                matrix=matrix,
                student_row=student_row,
            )
            filename_safe = "-".join((_student_label(student) or student_row["student_number"]).replace("/", "-").split())
            if send:
                result = send_email_event(
                    to_emails=emails,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    actor=actor,
                    metadata={
                        "event": "CA1_PARENT_RESULT_REPORT",
                        "student_id": str(student.id),
                        "student_number": student_row["student_number"],
                        "single_student_report": "true",
                        "class_code": class_code,
                    },
                    attachments=[
                        {
                            "name": f"NDGA-CA1-{filename_safe}-Score-Report.pdf",
                            "content": pdf_bytes,
                            "mimetype": "application/pdf",
                        }
                    ],
                )
                if result is None or not result.success:
                    failures.append((student_row["student_number"], _student_label(student), emails, result.detail if result else "no-result"))
                else:
                    successes.append((student_row["student_number"], _student_label(student), emails, result.external_message_id))
                time.sleep(SEND_DELAY_SECONDS)
            else:
                successes.append((student_row["student_number"], _student_label(student), emails, "dry-run"))

    print("candidates", total_candidates)
    print("ready_with_email", len(successes) + len(failures))
    print("skipped", len(skipped))
    for row in skipped:
        print("SKIPPED", row)
    print("successes", len(successes))
    for row in successes:
        print("SUCCESS", row)
    print("failures", len(failures))
    for row in failures:
        print("FAILURE", row)
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
