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

from apps.dashboard.models import SchoolProfile
from apps.notifications.services import send_email_event
from apps.pdfs.services import (
    principal_signature_data_uri,
    render_pdf_bytes,
    school_logo_data_uri,
)


RECIPIENT = "szubby10@gmail.com"
SUBJECT = "Notice of Revised Billing Structure for Sisters of Notre Dame de Namur Schools in Nigeria"


def build_context():
    profile = SchoolProfile.load()
    memo_date = timezone.localdate().strftime("%d %B %Y")
    school_address = (profile.address or "").strip() or "Kuje, Abuja"
    return {
        "school_profile": profile,
        "school_address": school_address,
        "memo_date": memo_date,
        "recipient_line": "Esteemed Parents/Guardians",
        "subject": SUBJECT,
        "salutation": "Dear Esteemed Parents/Guardians,",
        "opening_paragraphs": [
            (
                "Warm greetings from the Sisters of Notre Dame de Namur Schools in Nigeria. We wish to notify all "
                "parents and guardians that a revised billing structure will be introduced across our schools "
                "with effect from the September 2026/2027 academic session."
            ),
            (
                "This arrangement is intended to make school billing clearer by separating fixed school fees "
                "from other approved school-related contributions and student support items."
            ),
        ],
        "billing_categories": [
            {
                "title": "Category 1: Official School Fees",
                "text": (
                    "The official fee from September 2026 is N380,000. This is the standard school fee for our school."
                ),
            },
            {
                "title": "Category 2: School Celebrations and Events",
                "text": (
                    "This category covers approved school celebrations and events such as Christmas activities, "
                    "inter-house sports, cultural day, graduation, school programmes, ceremonies, and any other "
                    "officially communicated events."
                ),
            },
            {
                "title": "Category 3: Student and PTA-Related Items",
                "text": (
                    "This category covers student and PTA-related items, including foreign languages, opportunity "
                    "for scholarship and IT innovation, which are compulsory fees. It also covers snacks and other "
                    "student-development needs. The PTA levy is termly and covers PTA and staff welfare."
                ),
            },
        ],
        "collaboration_note": (
            "This message is sent in the spirit of better collaboration, respect, and appreciation as we continue "
            "to work together for the good of our students. NDGA: Educating Girls for Life."
        ),
        "closing_paragraphs": [
            "We thank you for your cooperation, understanding, and continued partnership with the school.",
        ],
        "principal_name": "School Management",
        "principal_role": "",
        "logo_data_uri": school_logo_data_uri(),
        "principal_signature_data_uri": principal_signature_data_uri(),
    }


def build_email_html(context):
    category_html = "".join(
        f"""
        <div style="margin:0 0 14px; padding:16px 18px; border-radius:16px; border:1px solid #dbe5f0; background:#f8fbff;">
          <p style="margin:0 0 7px; font-size:12px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; color:#163f73;">{category['title']}</p>
          <p style="margin:0; font-size:15px; line-height:1.8; color:#334155;">{category['text']}</p>
        </div>
        """
        for category in context["billing_categories"]
    )
    opening_html = "".join(
        f"<p style='margin:0 0 12px; font-size:15px; line-height:1.85; color:#334155;'>{paragraph}</p>"
        for paragraph in context["opening_paragraphs"]
    )
    closing_html = "".join(
        f"<p style='margin:0 0 12px; font-size:15px; line-height:1.85; color:#334155;'>{paragraph}</p>"
        for paragraph in context["closing_paragraphs"]
    )
    return f"""
    <div style="font-size:15px; line-height:1.8; color:#334155;">
      <div style="margin:0 0 18px; padding:18px 20px; border-radius:18px; background:#f8fbff; border:1px solid #dbe4f0;">
        <p style="margin:0 0 6px; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#c99628;">Official School Memo</p>
        <p style="margin:0 0 10px; font-size:19px; color:#0f172a;"><strong>{context['subject']}</strong></p>
        <p style="margin:0 0 6px; font-size:14px; color:#334155;"><strong>Date:</strong> {context['memo_date']}</p>
        <p style="margin:0; font-size:14px; color:#334155;"><strong>To:</strong> {context['recipient_line']}</p>
      </div>
      <p style="margin:0 0 14px; font-size:15px; line-height:1.85; color:#334155;">{context['salutation']}</p>
      {opening_html}
      {category_html}
      <div style="margin:0 0 18px; padding:16px 18px; border-left:4px solid #c79a35; background:#fffaf0; border-radius:0 14px 14px 0;">
        <p style="margin:0; font-size:14px; line-height:1.8; color:#5b4630;">{context['collaboration_note']}</p>
      </div>
      {closing_html}
      <p style="margin:18px 0 8px; font-size:15px; color:#334155;">Yours faithfully,</p>
      <p style="margin:0; font-size:16px; font-weight:700; color:#0f172a;">{context['principal_name']}</p>
      <p style="margin:18px 0 0; font-size:13px; color:#64748b;">The official memo PDF is attached for your records.</p>
    </div>
    """


def build_body_text(context):
    categories = "\n\n".join(
        f"{item['title']}\n{item['text']}" for item in context["billing_categories"]
    )
    return (
        f"{context['subject']}\n\n"
        f"Date: {context['memo_date']}\n"
        f"To: {context['recipient_line']}\n\n"
        f"{context['salutation']}\n\n"
        + "\n\n".join(context["opening_paragraphs"])
        + "\n\n"
        + categories
        + "\n\n"
        + context["collaboration_note"]
        + "\n\n"
        + "\n\n".join(context["closing_paragraphs"])
        + f"\n\nYours faithfully,\n{context['principal_name']}\n\n"
        + "The official memo PDF is attached for your records."
    )


def main():
    context = build_context()
    pdf_bytes = render_pdf_bytes(
        template_name="pdfs/billing_system_memo_pdf.html",
        context=context,
    )
    output_dir = ROOT / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ndga-revised-billing-system-memo-{timezone.localdate().isoformat()}.pdf"
    output_path.write_bytes(pdf_bytes)

    result = send_email_event(
        to_emails=[RECIPIENT],
        subject=SUBJECT,
        body_text=build_body_text(context),
        body_html=build_email_html(context),
        metadata={
            "event": "BILLING_SYSTEM_MEMO_ADMIN_ONLY",
            "recipient_policy": "single_admin_email_only",
            "to_email": RECIPIENT,
        },
        attachments=[
            {
                "name": output_path.name,
                "content": pdf_bytes,
                "mimetype": "application/pdf",
            }
        ],
    )
    print(
        {
            "recipient": RECIPIENT,
            "output_path": str(output_path),
            "provider": getattr(result, "provider", ""),
            "detail": getattr(result, "detail", ""),
            "success": getattr(result, "success", False),
        }
    )


if __name__ == "__main__":
    main()
