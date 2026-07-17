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

from django.template.loader import render_to_string
from django.utils import timezone

from apps.dashboard.models import SchoolProfile
from apps.notifications.services import send_email_event
from apps.pdfs.services import (
    principal_signature_data_uri,
    render_pdf_bytes,
    school_logo_data_uri,
)


PREVIEW_RECIPIENT = os.getenv("NDGA_PREVIEW_RECIPIENT", "szubby10@gmail.com")


def build_memo_context():
    profile = SchoolProfile.load()
    memo_date = timezone.localdate().strftime("%d %B %Y")
    school_address = (profile.address or "").strip() or "Kuje, Abuja"
    principal_name = "Sr. Rita Ezekwem, SNDdeN."
    return {
        "school_profile": profile,
        "school_address": school_address,
        "memo_date": memo_date,
        "recipient_line": "Esteemed Parents/Guardians",
        "subject": "Reinforcement of School Policies, Discipline, and Key Updates",
        "salutation": "Dear Esteemed Parents,",
        "opening_paragraphs": [
            "Warm greetings to you all.",
            "I write with a deep sense of duty to reaffirm our unwavering commitment to the safety, discipline, and holistic development of every child entrusted to us at NDGA.",
        ],
        "resumption_policy": (
            "Please note that resumption time must be strictly observed, and the school gate "
            "will close daily at 4:00 PM. This is not merely a rule; it is a safeguard. "
            "Late entry creates opportunities for the smuggling of contraband items into the school "
            "and, more subtly, encourages habits of deceit and manipulation among students. "
            "In addition, given the realities of our society today, maintaining firm control over movement "
            "is essential for the security and accountability of every child in our care."
        ),
        "conduct_policy": (
            "It is disheartening that some students do not fully appreciate the presence and dedication "
            "of the Sisters, who give of themselves daily to guide and nurture them. The energy that should "
            "be directed toward meaningful and profitable learning is too often lost to noise and disorder. "
            "Silence, when required, is not a punishment but a discipline that shapes focus and character. "
            "Therefore, from this term, any student who disobeys the rule of silence will face up to two "
            "suspensions. Discipline, in this regard, remains non-negotiable."
        ),
        "body_sections": [
            {
                "title": "Fees and Resumption Compliance",
                "paragraphs": [
                    "Furthermore, all outstanding and new school fees must be fully paid before your daughter returns to school.",
                    "Our past leniency, though well-intentioned, has been abused. We will now uphold this policy with firmness and fairness.",
                ],
            },
            {
                "title": "Stability, Communication, and Readiness",
                "paragraphs": [
                    "I also wish to inform you that the school will not undergo any structural or policy changes until after the current academic cycle, allowing us to consolidate our standards and ensure stability for our students.",
                    "On a positive note, we are pleased to announce that we can now communicate with you directly via email and WhatsApp, ensuring timely and personal updates.",
                    "In addition, the introduction of our Computer-Based Testing (CBT) examination structure is a deliberate step to expose our students to the demands of the world ahead and to prepare them confidently for it.",
                    "Good news to you, our esteemed collaborators: school fees will remain unchanged for the next five years.",
                ],
            },
        ],
        "scripture_text": (
            "Train up a child in the way he should go, and when he is old, he will not depart from it"
        ),
        "scripture_reference": "Proverbs 22:6",
        "closing_paragraphs": [
            "This is the work we are committed to steadily, faithfully, and without compromise.",
            "We sincerely appreciate your trust in NDGA. Change is often uncomfortable, even painful, but its fruits are lasting and worthwhile.",
            "Be assured that we remain committed, and your child is safe with us.",
        ],
        "principal_name": principal_name,
        "principal_role": "Principal",
        "logo_data_uri": school_logo_data_uri(),
        "principal_signature_data_uri": principal_signature_data_uri(),
    }


def official_memo_filename():
    return f"ndga-official-principal-memo-{timezone.localdate().isoformat()}.pdf"


def build_email_body(context):
    sections_html = []
    for section in context["body_sections"]:
        paragraphs = "".join(
            f"<p style='margin:0 0 12px; font-size:15px; line-height:1.85; color:#334155;'>{paragraph}</p>"
            for paragraph in section["paragraphs"]
        )
        sections_html.append(
            f"""
            <div style="margin:0 0 18px;">
              <p style="margin:0 0 8px; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#163f73;">{section['title']}</p>
              {paragraphs}
            </div>
            """
        )
    opening_html = "".join(
        f"<p style='margin:0 0 12px; font-size:15px; line-height:1.85; color:#334155;'>{paragraph}</p>"
        for paragraph in context["opening_paragraphs"]
    )
    closing_html = "".join(
        f"<p style='margin:0 0 12px; font-size:15px; line-height:1.85; color:#334155;'>{paragraph}</p>"
        for paragraph in context["closing_paragraphs"]
    )
    return """
    <div style="font-size:15px; line-height:1.8; color:#334155;">
      <div style="margin:0 0 18px; padding:18px 20px; border-radius:18px; background:#f8fbff; border:1px solid #dbe4f0;">
        <p style="margin:0 0 6px; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#c99628;">From the Principal's Desk</p>
        <p style="margin:0 0 10px; font-size:19px; color:#0f172a;"><strong>{subject}</strong></p>
        <p style="margin:0 0 6px; font-size:14px; color:#334155;"><strong>Date:</strong> {memo_date}</p>
        <p style="margin:0; font-size:14px; color:#334155;"><strong>To:</strong> {recipient_line}</p>
      </div>
      <p style="margin:0 0 14px; font-size:15px; line-height:1.85; color:#334155;">{salutation}</p>
      {opening_html}
      <div style="margin:0 0 18px; padding:18px 20px; border-radius:18px; background:#f8fbff; border:1px solid #dbe4f0;">
        <p style="margin:0 0 8px; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#163f73;">Gate and Resumption Control</p>
        <p style="margin:0; font-size:15px; line-height:1.85; color:#334155;">{resumption_policy}</p>
      </div>
      <div style="margin:0 0 18px; padding:18px 20px; border-radius:18px; background:#fff5f5; border:1px solid #fecaca;">
        <p style="margin:0 0 8px; font-size:12px; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:#9f1239;">Discipline and Conduct</p>
        <p style="margin:0; font-size:15px; line-height:1.85; color:#5b2333;">{conduct_policy}</p>
      </div>
      {sections_html}
      <div style="margin:0 0 18px; padding:16px 18px; border-left:4px solid #c79a35; background:#fffaf0; border-radius:0 14px 14px 0;">
        <p style="margin:0; font-size:14px; line-height:1.8; color:#5b4630;"><em>"{scripture_text}" ({scripture_reference})</em></p>
      </div>
      {closing_html}
      <p style="margin:18px 0 8px; font-size:15px; color:#334155;">Yours faithfully,</p>
      <p style="margin:0; font-size:16px; font-weight:700; color:#0f172a;">{principal_name}</p>
      <p style="margin:2px 0 0; font-size:14px; color:#475569;">{principal_role}</p>
      <p style="margin:18px 0 0; font-size:13px; color:#64748b;">A formal PDF office copy is also attached for your records.</p>
    </div>
    """.format(
        subject=context["subject"],
        memo_date=context["memo_date"],
        recipient_line=context["recipient_line"],
        salutation=context["salutation"],
        opening_html=opening_html,
        resumption_policy=context["resumption_policy"],
        conduct_policy=context["conduct_policy"],
        sections_html="".join(sections_html),
        scripture_text=context["scripture_text"],
        scripture_reference=context["scripture_reference"],
        closing_html=closing_html,
        principal_name=context["principal_name"],
        principal_role=context["principal_role"],
    )


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

    subject = "Principal Memo Preview - Updated Draft"
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
        + "A formal PDF office copy is also attached for your records."
    )

    result = send_email_event(
        to_emails=[PREVIEW_RECIPIENT],
        subject=subject,
        body_text=body_text,
        body_html=build_email_body(context),
        metadata={
            "event": "PRINCIPAL_MEMO_PREVIEW",
            "preview_only": True,
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
            "recipient": PREVIEW_RECIPIENT,
            "output_path": str(output_path),
            "provider": getattr(result, "provider", ""),
            "detail": getattr(result, "detail", ""),
            "success": getattr(result, "success", False),
        }
    )


if __name__ == "__main__":
    main()
