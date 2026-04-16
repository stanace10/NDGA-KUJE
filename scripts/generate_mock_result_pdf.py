from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "student-result-design-preview.pdf"
LOGO_PATH = ROOT / "static" / "images" / "ndga" / "logo.png"
SIGNATURE_PATH = ROOT / "static" / "images" / "ndga" / "principal-signature.png"


SCHOOL = {
    "name": "NOTRE DAME GIRLS' ACADEMY",
    "address": "Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje-Abuja",
    "session": "2025/2026 Academic Session",
    "term": "Second Term Result",
    "tagline": "Sample design preview for presentation only",
}

STUDENT = {
    "name": "Adaeze Okafor",
    "admission_no": "NDGA/2026/0142",
    "class_name": "SS 2 Gold",
    "house": "St. Julie House",
    "gender": "Female",
    "age": "15",
    "position": "5th of 42",
}

SUBJECTS = [
    ("English Language", 16, 14, 48),
    ("Mathematics", 18, 15, 51),
    ("Biology", 15, 14, 44),
    ("Chemistry", 13, 12, 42),
    ("Physics", 14, 13, 46),
    ("Economics", 17, 15, 49),
    ("Government", 16, 14, 47),
    ("Civic Education", 18, 16, 50),
    ("Computer Studies", 19, 15, 52),
]

PSYCHOMOTOR = [
    ("Punctuality", "4/5"),
    ("Neatness", "5/5"),
    ("Class Participation", "4/5"),
    ("Leadership", "4/5"),
    ("Respect & Courtesy", "5/5"),
]


def score_grade(score: int) -> tuple[str, str]:
    if score >= 75:
        return "A1", "Excellent"
    if score >= 70:
        return "B2", "Very Good"
    if score >= 65:
        return "B3", "Good"
    if score >= 60:
        return "C4", "Credit"
    if score >= 50:
        return "C5", "Pass"
    return "F9", "Needs Support"


def build_subject_rows():
    rows = [["Subject", "CA 1", "CA 2", "Exam", "Total", "Grade", "Remark"]]
    totals = []
    for subject, ca1, ca2, exam in SUBJECTS:
        total = ca1 + ca2 + exam
        grade, remark = score_grade(total)
        totals.append(total)
        rows.append([subject, ca1, ca2, exam, total, grade, remark])
    return rows, totals


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SchoolTitle",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=19,
            textColor=colors.HexColor("#18406b"),
            alignment=TA_LEFT,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.3,
            leading=10.2,
            textColor=colors.HexColor("#4a5568"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionLabel",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10.5,
            textColor=colors.white,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.4,
            leading=10.4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodySmallBold",
            parent=styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=10.4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CenterSmall",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=8.2,
            leading=10.2,
            alignment=TA_CENTER,
        )
    )
    return styles


def safe_image(path: Path, width: float, height: float):
    if path.exists():
        return Image(str(path), width=width, height=height)
    return Paragraph(" ", getSampleStyleSheet()["BodyText"])


def photo_placeholder(styles):
    table = Table(
        [[Paragraph("<b>STUDENT<br/>PHOTO</b>", styles["CenterSmall"])]],
        colWidths=[26 * mm],
        rowHeights=[30 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#a0aec0")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7fafc")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    return table


def build_header(styles):
    left = safe_image(LOGO_PATH, 22 * mm, 22 * mm)
    middle = [
        Paragraph(SCHOOL["name"], styles["SchoolTitle"]),
        Paragraph(SCHOOL["address"], styles["SmallMuted"]),
        Paragraph(f"{SCHOOL['session']} | {SCHOOL['term']}", styles["SmallMuted"]),
        Paragraph(SCHOOL["tagline"], styles["SmallMuted"]),
    ]
    right = photo_placeholder(styles)
    table = Table(
        [[left, middle, right]],
        colWidths=[28 * mm, 118 * mm, 28 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def build_notice(styles):
    text = (
        "<b>SAMPLE PREVIEW</b>: This PDF is a mock design only for layout review. "
        "It is not an official school result and should not be used for verification."
    )
    table = Table([[Paragraph(text, styles["BodySmall"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff4e5")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#dd6b20")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#9c4221")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def build_student_info(styles):
    left = [
        [Paragraph("<b>Student Name</b>", styles["BodySmallBold"]), Paragraph(STUDENT["name"], styles["BodySmall"])],
        [Paragraph("<b>Admission No.</b>", styles["BodySmallBold"]), Paragraph(STUDENT["admission_no"], styles["BodySmall"])],
        [Paragraph("<b>Class</b>", styles["BodySmallBold"]), Paragraph(STUDENT["class_name"], styles["BodySmall"])],
    ]
    right = [
        [Paragraph("<b>Term</b>", styles["BodySmallBold"]), Paragraph("Second Term", styles["BodySmall"])],
        [Paragraph("<b>Session</b>", styles["BodySmallBold"]), Paragraph("2025/2026", styles["BodySmall"])],
        [Paragraph("<b>Position</b>", styles["BodySmallBold"]), Paragraph(STUDENT["position"], styles["BodySmall"])],
    ]
    extra = [
        [Paragraph("<b>House</b>", styles["BodySmallBold"]), Paragraph(STUDENT["house"], styles["BodySmall"])],
        [Paragraph("<b>Gender</b>", styles["BodySmallBold"]), Paragraph(STUDENT["gender"], styles["BodySmall"])],
        [Paragraph("<b>Age</b>", styles["BodySmallBold"]), Paragraph(STUDENT["age"], styles["BodySmall"])],
    ]
    combined = []
    for idx in range(3):
        combined.append(left[idx] + right[idx] + extra[idx])

    table = Table(
        combined,
        colWidths=[25 * mm, 33 * mm, 18 * mm, 25 * mm, 18 * mm, 22 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_subjects_table(styles):
    rows, totals = build_subject_rows()
    table = Table(
        rows,
        colWidths=[48 * mm, 14 * mm, 14 * mm, 16 * mm, 16 * mm, 14 * mm, 34 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("ALIGN", (1, 1), (5, -1), "CENTER"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("ALIGN", (0, 1), (0, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#a0aec0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#cbd5e0")),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table, totals


def build_summary_box(styles, totals):
    average = sum(totals) / len(totals)
    summary_rows = [
        ["Subjects Offered", str(len(totals))],
        ["Total Obtainable", str(len(totals) * 100)],
        ["Total Obtained", str(sum(totals))],
        ["Student Average", f"{average:.1f}%"],
        ["Class Average", "74.2%"],
        ["Overall Remark", "Strong performance with room to improve in Chemistry."],
    ]
    table = Table(summary_rows, colWidths=[33 * mm, 52 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#e2e8f0")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_psychomotor_box(styles):
    rows = [["Psychomotor Domain", "Rating"]]
    rows.extend(PSYCHOMOTOR)
    rows.extend(
        [
            ("Times School Open", "62"),
            ("Times Present", "58"),
            ("Times Absent", "4"),
        ]
    )
    table = Table(rows, colWidths=[54 * mm, 24 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#b7791f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#e2e8f0")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
            ]
        )
    )
    return table


def build_comments(styles):
    teacher = Table(
        [[Paragraph("<b>Form Teacher Comment</b>", styles["BodySmallBold"])], [Paragraph("Adaeze is focused, respectful, and consistent. She should give extra attention to Chemistry problem-solving and maintain her excellent work ethic.", styles["BodySmall"])]],
        colWidths=[174 * mm],
    )
    teacher.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e0")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    signature = safe_image(SIGNATURE_PATH, 34 * mm, 10 * mm)
    sign_block = Table(
        [
            [
                Paragraph("<b>Principal Comment</b><br/>Promising term result. Keep building confidence and accuracy across the sciences.", styles["BodySmall"]),
                signature,
                Paragraph("<b>Principal Signature</b><br/>Sr. Mary Example", styles["CenterSmall"]),
            ]
        ],
        colWidths=[100 * mm, 34 * mm, 40 * mm],
    )
    sign_block.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return teacher, sign_block


def on_page(canvas, doc):
    width, height = A4

    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d7dee8"))
    canvas.rect(9 * mm, 9 * mm, width - 18 * mm, height - 18 * mm, stroke=1, fill=0)

    canvas.setFillColor(colors.HexColor("#1f4e79"))
    canvas.rect(9 * mm, height - 18 * mm, width - 18 * mm, 9 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 8.5)
    canvas.drawCentredString(width / 2, height - 14.4 * mm, "NDGA RESULT SHEET DESIGN PREVIEW")

    canvas.setFont("Helvetica-Bold", 52)
    canvas.setFillColor(colors.Color(0.88, 0.9, 0.94, alpha=0.55))
    canvas.translate(width / 2, height / 2)
    canvas.rotate(33)
    canvas.drawCentredString(0, 0, "SAMPLE PREVIEW")
    canvas.restoreState()


def main():
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
    )

    story = []
    story.append(build_header(styles))
    story.append(Spacer(1, 5 * mm))
    story.append(build_notice(styles))
    story.append(Spacer(1, 4 * mm))
    story.append(build_student_info(styles))
    story.append(Spacer(1, 5 * mm))

    subjects_table, totals = build_subjects_table(styles)
    story.append(subjects_table)
    story.append(Spacer(1, 5 * mm))

    lower = Table(
        [[build_summary_box(styles, totals), build_psychomotor_box(styles)]],
        colWidths=[88 * mm, 78 * mm],
    )
    lower.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(lower)
    story.append(Spacer(1, 5 * mm))

    teacher_box, signature_box = build_comments(styles)
    story.append(teacher_box)
    story.append(Spacer(1, 4 * mm))
    story.append(signature_box)
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Verification note: This is a sample PDF generated locally to preview the result-sheet design.",
            styles["SmallMuted"],
        )
    )

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"Created {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
