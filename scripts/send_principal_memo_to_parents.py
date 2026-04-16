from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "core.settings.local"),
)

import django

django.setup()

from django.utils import timezone

from apps.academics.models import StudentClassEnrollment
from apps.finance.services import current_academic_window
from apps.notifications.services import send_email_event
from apps.pdfs.services import render_pdf_bytes
from scripts.send_principal_memo_preview import (
    build_email_body,
    build_memo_context,
    official_memo_filename,
)


def _recipient_emails():
    session, _term = current_academic_window()
    enrollment_qs = StudentClassEnrollment.objects.select_related(
        "student",
        "student__student_profile",
    ).filter(
        is_active=True,
    )
    if session is not None:
        enrollment_qs = enrollment_qs.filter(session=session)

    emails = []
    seen_student_ids = set()
    for enrollment in enrollment_qs.order_by("student_id"):
        if enrollment.student_id in seen_student_ids:
            continue
        seen_student_ids.add(enrollment.student_id)
        profile = getattr(enrollment.student, "student_profile", None)
        email = (getattr(profile, "guardian_email", "") or "").strip().lower()
        if email and email not in emails:
            emails.append(email)
    return emails


def main():
    context = build_memo_context()
    pdf_bytes = render_pdf_bytes(
        template_name="pdfs/office_memo_pdf.html",
        context=context,
    )

    output_dir = ROOT / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / official_memo_filename()
    output_path.write_bytes(pdf_bytes)

    subject = "Official Principal Memo | Notre Dame Girls Academy"
    body_text = (
        f"FROM THE PRINCIPAL'S DESK\n\n"
        f"Date: {context['memo_date']}\n"
        f"To: {context['recipient_line']}\n"
        f"Subject: {context['subject']}\n\n"
        f"{context['salutation']}\n\n"
        + "\n\n".join(context["opening_paragraphs"])
        + "\n\n"
        + f"Gate and Resumption Control\n{context['resumption_policy']}\n\n"
        + f"Discipline and Conduct\n{context['conduct_policy']}\n\n"
        + "\n\n".join(
            f"{section['title']}\n" + "\n".join(section["paragraphs"])
            for section in context["body_sections"]
        )
        + "\n\n"
        + f"\"{context['scripture_text']}\" ({context['scripture_reference']})\n\n"
        + "\n\n".join(context["closing_paragraphs"])
        + f"\n\nYours faithfully,\n{context['principal_name']}\n{context['principal_role']}\n\n"
        + "The official memo PDF is attached for your records."
    )

    recipients = _recipient_emails()
    sent = 0
    failed = 0
    failures = []
    for email in recipients:
        result = send_email_event(
            to_emails=[email],
            subject=subject,
            body_text=body_text,
            body_html=build_email_body(context),
            metadata={
                "event": "PRINCIPAL_MEMO_PARENT_SEND",
                "preview_only": False,
                "memo_date": timezone.localdate().isoformat(),
            },
            attachments=[
                {
                    "name": output_path.name,
                    "content": pdf_bytes,
                    "mimetype": "application/pdf",
                }
            ],
        )
        if getattr(result, "success", False):
            sent += 1
        else:
            failed += 1
            failures.append(
                {
                    "email": email,
                    "provider": getattr(result, "provider", ""),
                    "detail": getattr(result, "detail", ""),
                }
            )

    print(
        {
            "recipient_count": len(recipients),
            "sent": sent,
            "failed": failed,
            "output_path": str(output_path),
            "failures": failures[:10],
        }
    )


if __name__ == "__main__":
    main()
