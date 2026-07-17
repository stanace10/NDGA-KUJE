from __future__ import annotations

import base64
from io import BytesIO
import json
import os
import sys
from pathlib import Path
from urllib import error, request

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
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.pdfs.services import render_pdf_bytes

from send_prefect_results_preview import _data_uri, _load_env_file


ENV_PATH = ROOT / ".env.lan"
LOGO_PATH = ROOT / "static" / "images" / "ndga" / "logo.png"
OUTPUT_PDF = ROOT / "ndga" / "NDGA-Third-Term-Planner-2025-2026.pdf"


SUBJECT = "Official Memo from the School Management Desk: Third Term Planner 2025/2026"
RECIPIENT = "szubby10@gmail.com"


def build_months() -> list[dict[str, object]]:
    return [
        {
            "name": "April",
            "items": [
                {"date_label": "16th Thursday", "description": "Staff Resumption"},
                {"date_label": "18th Saturday", "description": "Resumption of Students"},
                {
                    "date_label": "20th - 23rd Monday to Thursday",
                    "description": "Welcome Test / Scheme of Work; BECE NECO begins; World Book and Copyright Day on Thursday 23rd",
                },
                {"date_label": "24th Friday", "description": "Staff and Students Opening Mass"},
                {"date_label": "27th - 30th Monday to Thursday", "description": "Classes begin"},
            ],
        },
        {
            "name": "May",
            "items": [
                {"date_label": "1st Friday", "description": "SS2 Academic Presentation; Worker's Day"},
                {"date_label": "2nd Saturday", "description": "Entrance Examination / Visit to the Poor"},
                {
                    "date_label": "4th - 8th Monday to Friday",
                    "description": "Classes continue; World Red Cross and Red Crescent Day on Friday 8th",
                },
                {
                    "date_label": "11th - 15th Monday to Friday",
                    "description": "Feast Day of SNDdeN on Wednesday 13th; Ascension Thursday on Thursday 14th",
                },
                {"date_label": "15th Friday", "description": "International Day of Families"},
                {
                    "date_label": "18th - 22nd Monday to Friday",
                    "description": "1st CA from Monday to Wednesday; Feast of St Rita of Cascia",
                },
                {"date_label": "24th Sunday", "description": "Cultural Mass; Pentecost Sunday"},
                {"date_label": "26th Tuesday", "description": "Students General Assembly (SGA)"},
                {"date_label": "27th Wednesday", "description": "NDGA Funfair; Children's Day"},
                {"date_label": "29th Friday", "description": "Community Service / Workshop on Solar Installation"},
                {"date_label": "30th Saturday", "description": "Pick up for Midterm break"},
            ],
        },
        {
            "name": "June",
            "items": [
                {"date_label": "6th Saturday", "description": "Dropoff from Midterm break / Open Day"},
                {"date_label": "7th Sunday", "description": "Reception of First Holy Communion; Corpus Christi"},
                {
                    "date_label": "8th - 12th Monday to Friday",
                    "description": "Classes continue; Democracy Day on Friday 12th",
                },
                {"date_label": "13th Saturday", "description": "Feast of St Anthony of Padua"},
                {"date_label": "19th Friday", "description": "Solemnity of the Most Sacred Heart of Jesus"},
                {"date_label": "24th - 26th Wednesday to Friday", "description": "2nd CA"},
                {"date_label": "27th Saturday", "description": "Visiting Day"},
                {"date_label": "29th - 30th Monday to Tuesday", "description": "Revision"},
            ],
        },
        {
            "name": "July",
            "items": [
                {"date_label": "1st - 3rd Wednesday to Friday", "description": "Practical Examination"},
                {"date_label": "4th Saturday", "description": "Entrance Examination"},
                {"date_label": "6th - 13th Monday to Monday", "description": "Examination"},
                {"date_label": "14th - 16th Tuesday to Thursday", "description": "Post Exam Activities"},
                {"date_label": "17th Friday", "description": "Closing Mass"},
                {
                    "date_label": "18th Saturday",
                    "description": "Graduation (Date to be confirmed); Nelson Mandela International Day",
                },
            ],
        },
    ]


def planner_pdf_filename() -> str:
    return OUTPUT_PDF.name


def build_pdf_context() -> dict[str, object]:
    profile = {
        "school_name": "Notre Dame Girls' Academy",
        "address": "Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje Abuja",
        "contact_email": "office@ndgakuje.org",
        "contact_phone": "+234 902 940 5413",
        "website": "https://ndgakuje.org",
    }
    return {
        "school_profile": profile,
        "school_address": profile["address"],
        "memo_date": "23 April 2026",
        "recipient_line": "Parents and Guardians",
        "subject": "Third Term Planner 2025/2026 Academic Session",
        "salutation": "Dear Parents and Guardians,",
        "intro_paragraph": "Please find below the official Third Term Planner for the 2025/2026 Academic Session as issued from the School Management Desk.",
        "months": build_months(),
        "closing_note": "We appreciate your continued cooperation and support as we work together to ensure an orderly, purposeful, and fruitful term for our students.",
        "signoff_name": "School Management",
        "signoff_role": "Notre Dame Girls' Academy",
        "logo_data_uri": _data_uri(LOGO_PATH),
    }


def generate_pdf_bytes() -> bytes:
    context = build_pdf_context()
    try:
        pdf_bytes = render_pdf_bytes(
            template_name="pdfs/third_term_planner_pdf.html",
            context=context,
        )
    except RuntimeError:
        pdf_bytes = generate_reportlab_pdf_bytes(context)
    OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PDF.write_bytes(pdf_bytes)
    return pdf_bytes


def _paragraph_style(
    styles,
    name: str,
    *,
    parent: str = "BodyText",
    font_name: str | None = None,
    font_size: float | None = None,
    leading: float | None = None,
    text_color=None,
    alignment: int | None = None,
    space_after: float | None = None,
    space_before: float | None = None,
) -> ParagraphStyle:
    base = styles[parent]
    return ParagraphStyle(
        name=name,
        parent=base,
        fontName=font_name or base.fontName,
        fontSize=font_size or base.fontSize,
        leading=leading or base.leading,
        textColor=text_color if text_color is not None else base.textColor,
        alignment=alignment if alignment is not None else base.alignment,
        spaceAfter=space_after if space_after is not None else base.spaceAfter,
        spaceBefore=space_before if space_before is not None else base.spaceBefore,
    )


def generate_reportlab_pdf_bytes(context: dict[str, object]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#002147")
    gold = colors.HexColor("#d4af37")
    soft_blue = colors.HexColor("#f4f8fc")
    slate = colors.HexColor("#334155")

    school_name_style = _paragraph_style(
        styles,
        "SchoolName",
        parent="Heading1",
        font_name="Helvetica-Bold",
        font_size=20,
        leading=22,
        text_color=colors.white,
        space_after=3,
    )
    header_line_style = _paragraph_style(
        styles,
        "HeaderLine",
        font_name="Helvetica",
        font_size=9,
        leading=11,
        text_color=colors.white,
        space_after=2,
    )
    header_tag_style = _paragraph_style(
        styles,
        "HeaderTag",
        font_name="Helvetica-Bold",
        font_size=9,
        leading=11,
        text_color=gold,
        space_after=0,
    )
    body_style = _paragraph_style(
        styles,
        "PlannerBody",
        font_name="Helvetica",
        font_size=10.2,
        leading=14,
        text_color=slate,
        space_after=6,
    )
    body_bold_style = _paragraph_style(
        styles,
        "PlannerBodyBold",
        font_name="Helvetica-Bold",
        font_size=10.2,
        leading=14,
        text_color=colors.HexColor("#0f172a"),
        space_after=6,
    )
    month_style = _paragraph_style(
        styles,
        "MonthStyle",
        font_name="Helvetica-Bold",
        font_size=11.2,
        leading=13,
        text_color=colors.white,
        alignment=TA_LEFT,
    )
    signoff_style = _paragraph_style(
        styles,
        "Signoff",
        font_name="Helvetica-Bold",
        font_size=11,
        leading=14,
        text_color=colors.HexColor("#0f172a"),
        space_after=2,
    )
    footer_style = _paragraph_style(
        styles,
        "Footer",
        font_name="Helvetica",
        font_size=8.5,
        leading=10,
        text_color=colors.HexColor("#64748b"),
        alignment=TA_CENTER,
    )

    story = []

    logo_cell = ""
    if LOGO_PATH.exists():
        logo = Image(str(LOGO_PATH))
        logo.drawWidth = 18 * mm
        logo.drawHeight = 18 * mm
        logo_cell = logo

    header_text = [
        Paragraph("OFFICIAL MEMO", header_line_style),
        Paragraph(str(context["school_profile"]["school_name"]), school_name_style),
        Paragraph(str(context["school_address"]), header_line_style),
        Paragraph("FROM THE SCHOOL MANAGEMENT DESK", header_tag_style),
    ]
    header_table = Table([[logo_cell, header_text]], colWidths=[24 * mm, 150 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), navy),
                ("BOX", (0, 0), (-1, -1), 0.5, navy),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 5 * mm))

    meta_rows = [
        [
            Paragraph("<b>DATE</b><br/>23 April 2026", body_style),
            Paragraph("<b>TO</b><br/>Parents and Guardians", body_style),
        ],
        [
            Paragraph("<b>SUBJECT</b><br/>Third Term Planner 2025/2026 Academic Session", body_style),
            "",
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[88 * mm, 88 * mm])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), soft_blue),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe4f0")),
                ("SPAN", (0, 1), (1, 1)),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(str(context["salutation"]), body_bold_style))
    story.append(Paragraph(str(context["intro_paragraph"]), body_style))
    story.append(Spacer(1, 1 * mm))

    for month in context["months"]:
        story.append(
            Table(
                [[Paragraph(str(month["name"]).upper(), month_style)]],
                colWidths=[176 * mm],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), navy),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                ),
            )
        )
        month_rows = []
        for item in month["items"]:
            month_rows.append(
                [
                    Paragraph(f"<b>{item['date_label']}</b>", body_style),
                    Paragraph(str(item["description"]), body_style),
                ]
            )
        month_table = Table(month_rows, colWidths=[56 * mm, 120 * mm])
        month_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#dbe4f0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(month_table)
        story.append(Spacer(1, 3 * mm))

    closing_table = Table(
        [[Paragraph(str(context["closing_note"]), body_style)]],
        colWidths=[176 * mm],
    )
    closing_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf0")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, gold),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(closing_table)
    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph("Yours faithfully,", body_style))
    story.append(Spacer(1, 5 * mm))
    story.append(
        Table(
            [[""]],
            colWidths=[62 * mm],
            style=TableStyle([("LINEABOVE", (0, 0), (0, 0), 1, colors.HexColor("#94a3b8"))]),
        )
    )
    story.append(Paragraph(str(context["signoff_name"]), signoff_style))
    story.append(Paragraph(str(context["signoff_role"]), body_style))
    story.append(Spacer(1, 4 * mm))
    school_profile = context["school_profile"]
    footer_text = f"{school_profile['school_name']} | {school_profile['contact_email']} | {school_profile['contact_phone']} | {school_profile['website']}"
    story.append(Paragraph(footer_text, footer_style))

    doc.build(story)
    return buffer.getvalue()


def _attachment_payload(name: str, content: bytes) -> dict[str, str]:
    return {
        "name": name,
        "content": base64.b64encode(content).decode("ascii"),
    }


def build_text_body() -> str:
    return (
        "OFFICIAL MEMO\n"
        "NOTRE DAME GIRLS' ACADEMY\n"
        "From the School Management Desk\n"
        "Date: 23 April 2026\n"
        "Subject: Third Term Planner 2025/2026 Academic Session\n\n"
        "Dear Parents and Guardians,\n\n"
        "Please find below the Third Term Planner for the 2025/2026 Academic Session.\n\n"
        "APRIL\n"
        "16th Thursday - Staff Resumption\n"
        "18th Saturday - Resumption of Students\n"
        "20th-23rd Monday-Thursday - Welcome Test / Scheme of Work | BECE NECO begins | World Book and Copyright Day on Thursday 23rd\n"
        "24th Friday - Staff and Students Opening Mass\n"
        "27th-30th Monday-Thursday - Classes begin\n\n"
        "MAY\n"
        "1st Friday - SS2 Academic Presentation | Worker's Day\n"
        "2nd Saturday - Entrance Examination / Visit to the Poor\n"
        "4th-8th Monday-Friday - Classes continue | World Red Cross and Red Crescent Day on Friday 8th\n"
        "11th-15th Monday-Friday - Feast Day of SNDdeN on Wednesday 13th | Ascension Thursday on Thursday 14th\n"
        "15th Friday - International Day of Families\n"
        "18th-22nd Monday-Friday - 1st CA from Monday to Wednesday | Feast of St Rita of Cascia\n"
        "24th Sunday - Cultural Mass | Pentecost Sunday\n"
        "26th Tuesday - Students General Assembly (SGA)\n"
        "27th Wednesday - NDGA Funfair | Children's Day\n"
        "29th Friday - Community Service / Workshop on Solar Installation\n"
        "30th Saturday - Pick up for Midterm break\n\n"
        "JUNE\n"
        "6th Saturday - Dropoff from Midterm break / Open Day\n"
        "7th Sunday - Reception of First Holy Communion | Corpus Christi\n"
        "8th-12th Monday-Friday - Classes continue | Democracy Day on Friday 12th\n"
        "13th Saturday - Feast of St Anthony of Padua\n"
        "19th Friday - Solemnity of the Most Sacred Heart of Jesus\n"
        "24th-26th Wednesday-Friday - 2nd CA\n"
        "27th Saturday - Visiting Day\n"
        "29th-30th Monday-Tuesday - Revision\n\n"
        "JULY\n"
        "1st-3rd Wednesday-Friday - Practical Examination\n"
        "4th Saturday - Entrance Examination\n"
        "6th-13th Monday-Monday - Examination\n"
        "14th-16th Tuesday-Thursday - Post Exam Activities\n"
        "17th Friday - Closing Mass\n"
        "18th Saturday - Graduation (Date to be confirmed) | Nelson Mandela International Day\n\n"
        "We appreciate your continued cooperation and support.\n\n"
        "Yours faithfully,\n"
        "School Management\n"
        "Notre Dame Girls' Academy\n\n"
        "The official planner PDF is attached for your records."
    )


def build_html_body() -> str:
    logo_src = _data_uri(LOGO_PATH)
    logo_block = ""
    if logo_src:
        logo_block = (
            "<div style='width:74px;height:74px;border-radius:18px;background:#ffffff;"
            "display:flex;align-items:center;justify-content:center;padding:10px;'>"
            f"<img src='{logo_src}' alt='NDGA logo' style='width:54px;height:54px;object-fit:contain;'>"
            "</div>"
        )
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;background:#f4f7fb;padding:24px 0;color:#334155;">
      <div style="max-width:780px;margin:0 auto;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 20px 48px rgba(15,23,42,0.10);">
        <div style="padding:24px 28px;background:linear-gradient(135deg,#002147 0%,#03152d 62%,#d4af37 100%);color:#ffffff;">
          <div style="display:flex;gap:18px;align-items:flex-start;">
            {logo_block}
            <div>
              <div style="display:inline-block;padding:7px 14px;border-radius:999px;background:rgba(255,255,255,0.18);font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">Official Memo</div>
              <h1 style="margin:10px 0 6px;font-size:28px;line-height:1.1;">Notre Dame Girls' Academy</h1>
              <p style="margin:0;font-size:14px;color:#e2e8f0;">Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje Abuja</p>
              <p style="margin:10px 0 0;font-size:14px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#f8d78f;">From the School Management Desk</p>
            </div>
          </div>
        </div>

        <div style="padding:28px;">
          <div style="border:1px solid #dbe4f0;border-radius:18px;background:#f8fbff;padding:18px 20px;margin:0 0 22px;">
            <p style="margin:0 0 6px;font-size:14px;color:#0f172a;"><strong>Date:</strong> 23 April 2026</p>
            <p style="margin:0 0 6px;font-size:14px;color:#0f172a;"><strong>To:</strong> Parents and Guardians</p>
            <p style="margin:0;font-size:14px;color:#0f172a;"><strong>Subject:</strong> Third Term Planner 2025/2026 Academic Session</p>
          </div>

          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">Dear Parents and Guardians,</p>
          <p style="margin:0 0 18px;font-size:15px;line-height:1.85;">Please find below the Third Term Planner for the 2025/2026 Academic Session.</p>

          <div style="margin:0 0 18px;border:1px solid #dbe4f0;border-radius:18px;overflow:hidden;">
            <div style="padding:14px 18px;background:#002147;color:#ffffff;font-size:18px;font-weight:700;">APRIL</div>
            <div style="padding:18px;background:#ffffff;">
              <p style="margin:0 0 10px;"><strong>16th Thursday:</strong> Staff Resumption</p>
              <p style="margin:0 0 10px;"><strong>18th Saturday:</strong> Resumption of Students</p>
              <p style="margin:0 0 10px;"><strong>20th - 23rd Monday to Thursday:</strong> Welcome Test / Scheme of Work</p>
              <p style="margin:0 0 10px;"><strong>International Activities:</strong> BECE NECO begins; World Book and Copyright Day on Thursday 23rd</p>
              <p style="margin:0 0 10px;"><strong>24th Friday:</strong> Staff and Students Opening Mass</p>
              <p style="margin:0;"><strong>27th - 30th Monday to Thursday:</strong> Classes begin</p>
            </div>
          </div>

          <div style="margin:0 0 18px;border:1px solid #dbe4f0;border-radius:18px;overflow:hidden;">
            <div style="padding:14px 18px;background:#002147;color:#ffffff;font-size:18px;font-weight:700;">MAY</div>
            <div style="padding:18px;background:#ffffff;">
              <p style="margin:0 0 10px;"><strong>1st Friday:</strong> SS2 Academic Presentation | Worker's Day</p>
              <p style="margin:0 0 10px;"><strong>2nd Saturday:</strong> Entrance Examination / Visit to the Poor</p>
              <p style="margin:0 0 10px;"><strong>4th - 8th Monday to Friday:</strong> Classes continue | World Red Cross and Red Crescent Day on Friday 8th</p>
              <p style="margin:0 0 10px;"><strong>11th - 15th Monday to Friday:</strong> Feast Day of SNDdeN on Wednesday 13th | Ascension Thursday on Thursday 14th</p>
              <p style="margin:0 0 10px;"><strong>15th Friday:</strong> International Day of Families</p>
              <p style="margin:0 0 10px;"><strong>18th - 22nd Monday to Friday:</strong> 1st CA (Monday to Wednesday) | Feast of St Rita of Cascia</p>
              <p style="margin:0 0 10px;"><strong>24th Sunday:</strong> Cultural Mass | Pentecost Sunday</p>
              <p style="margin:0 0 10px;"><strong>26th Tuesday:</strong> Students General Assembly (SGA)</p>
              <p style="margin:0 0 10px;"><strong>27th Wednesday:</strong> NDGA Funfair | Children's Day</p>
              <p style="margin:0 0 10px;"><strong>29th Friday:</strong> Community Service / Workshop on Solar Installation</p>
              <p style="margin:0;"><strong>30th Saturday:</strong> Pick up for Midterm break</p>
            </div>
          </div>

          <div style="margin:0 0 18px;border:1px solid #dbe4f0;border-radius:18px;overflow:hidden;">
            <div style="padding:14px 18px;background:#002147;color:#ffffff;font-size:18px;font-weight:700;">JUNE</div>
            <div style="padding:18px;background:#ffffff;">
              <p style="margin:0 0 10px;"><strong>6th Saturday:</strong> Dropoff from Midterm break / Open Day</p>
              <p style="margin:0 0 10px;"><strong>7th Sunday:</strong> Reception of First Holy Communion | Corpus Christi</p>
              <p style="margin:0 0 10px;"><strong>8th - 12th Monday to Friday:</strong> Classes continue | Democracy Day on Friday 12th</p>
              <p style="margin:0 0 10px;"><strong>13th Saturday:</strong> Feast of St Anthony of Padua</p>
              <p style="margin:0 0 10px;"><strong>19th Friday:</strong> Solemnity of the Most Sacred Heart of Jesus</p>
              <p style="margin:0 0 10px;"><strong>24th - 26th Wednesday to Friday:</strong> 2nd CA</p>
              <p style="margin:0 0 10px;"><strong>27th Saturday:</strong> Visiting Day</p>
              <p style="margin:0;"><strong>29th - 30th Monday to Tuesday:</strong> Revision</p>
            </div>
          </div>

          <div style="margin:0 0 18px;border:1px solid #dbe4f0;border-radius:18px;overflow:hidden;">
            <div style="padding:14px 18px;background:#002147;color:#ffffff;font-size:18px;font-weight:700;">JULY</div>
            <div style="padding:18px;background:#ffffff;">
              <p style="margin:0 0 10px;"><strong>1st - 3rd Wednesday to Friday:</strong> Practical Examination</p>
              <p style="margin:0 0 10px;"><strong>4th Saturday:</strong> Entrance Examination</p>
              <p style="margin:0 0 10px;"><strong>6th - 13th Monday to Monday:</strong> Examination</p>
              <p style="margin:0 0 10px;"><strong>14th - 16th Tuesday to Thursday:</strong> Post Exam Activities</p>
              <p style="margin:0 0 10px;"><strong>17th Friday:</strong> Closing Mass</p>
              <p style="margin:0;"><strong>18th Saturday:</strong> Graduation (Date to be confirmed) | Nelson Mandela International Day</p>
            </div>
          </div>

          <p style="margin:18px 0 12px;font-size:15px;line-height:1.85;">We appreciate your continued cooperation and support.</p>
          <p style="margin:18px 0 8px;font-size:15px;">Yours faithfully,</p>
          <p style="margin:0;font-size:16px;font-weight:700;color:#0f172a;">School Management</p>
          <p style="margin:2px 0 0;font-size:14px;color:#475569;">Notre Dame Girls' Academy</p>
          <p style="margin:18px 0 0;font-size:13px;color:#64748b;">The official planner PDF is attached for your records.</p>
        </div>
      </div>
    </div>
    """


def send_preview() -> dict[str, object]:
    env = _load_env_file(ENV_PATH)
    api_key = env.get("BREVO_API_KEY", "").strip()
    sender_email = env.get("NOTIFICATIONS_FROM_EMAIL", "office@ndgakuje.org").strip()
    sender_name = env.get("BREVO_SENDER_NAME", "NOTRE DAME GIRLS ACADEMY").strip()
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is missing from .env.lan")
    pdf_bytes = generate_pdf_bytes()

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": RECIPIENT}],
        "subject": SUBJECT,
        "textContent": build_text_body(),
        "htmlContent": build_html_body(),
        "attachment": [
            _attachment_payload(planner_pdf_filename(), pdf_bytes),
        ],
    }

    req = request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status": resp.status,
                "recipient": RECIPIENT,
                "response": body,
                "output_pdf": str(OUTPUT_PDF),
                "generated_at": timezone.localtime().isoformat(),
            }
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": exc.code,
            "recipient": RECIPIENT,
            "response": body,
            "output_pdf": str(OUTPUT_PDF),
        }


if __name__ == "__main__":
    print(send_preview())
