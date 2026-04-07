import base64
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicClass, AcademicSession, Subject, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)


TITLE = "MON 8:00-9:20 SS1 Mathematics Second Term Exam"
DESCRIPTION = "SS1 SECOND TERM MATHEMATICS 2026"
BANK_NAME = "SS1 Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in Section A and answer number 1 and any other 4 in Section B. "
    "Timer is 70 minutes. Exam window closes at 9:20 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. A sales girl gave a change of #95 .00 to the buyer instead of #100.00. calculate the percentage error.", "options": {"A": "# 4.00", "B": "# 5.00", "C": "#2.00", "D": "#10.00"}, "answer": "B"},
    {"stem": "2. The length of a book is 1.45m. A boy measured it as 1.90m, find the percentage error to one dp", "options": {"A": "31.03", "B": "23.68", "C": "23.7", "D": "31.0"}, "answer": "A"},
    {"stem": "3. Round off 0.045 to 2 dp", "options": {"A": "0.04", "B": "0.01", "C": "0.05", "D": "0.02"}, "answer": "C"},
    {"stem": "4. Round off 96495 to the nearest 100", "options": {"A": "96410", "B": "96500", "C": "96490", "D": "90000"}, "answer": "B"},
    {"stem": "5. Round off 18145.24 to 3sf", "options": {"A": "18200.00", "B": "18100.00", "C": "18100", "D": "18200"}, "answer": "C"},
    {"stem": "6. Round off 0.00456 to 2 sf", "options": {"A": "0.0045", "B": "45", "C": "0.0046", "D": "46"}, "answer": "A"},
    {"stem": "7. Solve 20p^2 - 320 = 0", "options": {"A": "P = -4 0r 4", "B": "P = -1 or 1", "C": "P = 2 or 3", "D": "P = 3 or 4"}, "answer": "A"},
    {"stem": "8. Solve the quadratic equation x^2 + 11x + 18 = 0", "options": {"A": "-1 or 2", "B": "-2 or -9", "C": "9 or 2", "D": "1 or 2"}, "answer": "B"},
    {"stem": "9. Factorize 2h^2 + 5h + 3", "options": {"A": "(2h + 3)(h + 1)", "B": "(2h - 3)(h -1)", "C": "(4h + 3)(2h - 2)", "D": "(h - 4)(3h-2)"}, "answer": "A"},
    {"stem": "10. What is the value of A", "options": {"A": "T", "B": "F", "C": "TF", "D": "FT"}, "answer": "B", "shared_html": "table_10_14"},
    {"stem": "11. What is the value of B", "options": {"A": "T", "B": "F", "C": "TF", "D": "FT"}, "answer": "B", "shared_html": "table_10_14"},
    {"stem": "12. What is the value of C", "options": {"A": "T", "B": "TF", "C": "FT", "D": "F"}, "answer": "D", "shared_html": "table_10_14"},
    {"stem": "13. What is the value of D", "options": {"A": "TF", "B": "FT", "C": "F", "D": "T"}, "answer": "D", "shared_html": "table_10_14"},
    {"stem": "14. What is the value of E", "options": {"A": "T", "B": "F", "C": "TF", "D": "FT"}, "answer": "A", "shared_html": "table_10_14"},
    {"stem": "15. Find area of a circle with radius 21cm", "options": {"A": "1386cm^2", "B": "345cm^2", "C": "247cm^2", "D": "1456cm^2"}, "answer": "A"},
    {"stem": "16. Find the area of a square with one side 4.5cm", "options": {"A": "16.25cm^2", "B": "18.75cm^2", "C": "20.25cm^2", "D": "21.50cm^2"}, "answer": "C"},
    {"stem": "17. Find the area of a square field with each diagonal 150m long", "options": {"A": "32,500m", "B": "11,250m^2", "C": "22,500m^2", "D": "22,500"}, "answer": "B"},
    {"stem": "18. The area of a circle is 81πcm^2. Find the diameter of the circle.", "options": {"A": "7cm", "B": "9cm", "C": "13cm", "D": "18cm"}, "answer": "D"},
    {"stem": "19. Calculate the circumference of a circle, centre o and radius 3.5cm(π = ²²⁄₇).", "options": {"A": "11cm", "B": "15cm", "C": "13cm", "D": "22cm"}, "answer": "D"},
    {"stem": "20. The perimeter of a parallelogram is 38cm. if one of the sides is 12cm, find the other side", "options": {"A": "7cm", "B": "9cm", "C": "13cm", "D": "6cm"}, "answer": "A"},
    {"stem": "21. Calculate the area of the figure below", "options": {"A": "1.5cm^2", "B": "10.5cm^2", "C": "27cm^2", "D": "54cm^2"}, "answer": "D", "image": "NO 21.png"},
    {"stem": "22. The trapezium below has an area of 456cm^2, calculate the distance between its parallel sides.", "options": {"A": "29cm", "B": "27cm", "C": "19cm", "D": "17cm"}, "answer": "C", "image": "NO 22.png"},
    {"stem": "23. Calculate the perpendicular distance between the parallel sides", "options": {"A": "3.35cm", "B": "3.72cm", "C": "4.50cm", "D": "4.62cm"}, "answer": "A", "image": "NO 23 AND 24.png"},
    {"stem": "24. Calculate correct to the nearest cm^2 the area of the trapezium", "options": {"A": "27cm^2", "B": "30cm^2", "C": "36cm^2", "D": "37cm^2"}, "answer": "A", "image": "NO 23 AND 24.png"},
    {"stem": "25. Calculate the area of a circle with diameter 8m to the nearest m^2", "options": {"A": "50m^2", "B": "40m^2", "C": "30m^2", "D": "20m^2"}, "answer": "A"},
    {"stem": "26. Factorise V^2 - 6v - 27", "options": {"A": "(v-9)(v+3)", "B": "(v-9)(v-3)", "C": "(v + 3)(v-2)", "D": "(v-2)(v-3)"}, "answer": "A"},
    {"stem": "27. Solve the 3t^2 - 12t = 0", "options": {"A": "t = 1 0r 2", "B": "t = 0 or 2", "C": "t = 0 or 4", "D": "t = -4 or 0"}, "answer": "C"},
    {"stem": "28. Solve the equation 3x^2 - 75 = 0", "options": {"A": "x = -5 or 5", "B": "x = 5 0r 5", "C": "x = 1 or 2", "D": "x = 2 or 2"}, "answer": "A"},
    {"stem": "29. Round of 6.0964 to the nearest whole number", "options": {"A": "1", "B": "6", "C": "7", "D": "5"}, "answer": "B"},
    {"stem": "30. Estimate 8.4 x 9.6 to 1sf", "options": {"A": "80", "B": "60", "C": "70", "D": "50"}, "answer": "A"},
    {"stem": "31. Estimate 99.9 x 313 to one significant", "options": {"A": "30", "B": "300", "C": "400", "D": "40"}, "answer": "B"},
    {"stem": "32. Estimate The value of (75.2 × 120)⁄(4.162 ×49.6) correct to one significant figure", "options": {"A": "20", "B": "30", "C": "40", "D": "60"}, "answer": "C"},
    {"stem": "33. What is the value of A", "options": {"A": "T", "B": "F", "C": "TT", "D": "FT"}, "answer": "A", "image": "NO 33 TO 38.png"},
    {"stem": "34. What is the value of B", "options": {"A": "F", "B": "T", "C": "FT", "D": "TF"}, "answer": "A", "image": "NO 33 TO 38.png"},
    {"stem": "35. What is the value of C", "options": {"A": "T", "B": "F", "C": "TF", "D": "FF"}, "answer": "B", "image": "NO 33 TO 38.png"},
    {"stem": "36. What is the value of D", "options": {"A": "T", "B": "F", "C": "TT", "D": "FF"}, "answer": "B", "image": "NO 33 TO 38.png"},
    {"stem": "37. The following are special angles except------------", "options": {"A": "30°", "B": "60°", "C": "90°", "D": "25°"}, "answer": "D"},
    {"stem": "38. An arc subtends an angles of 105 at the centre of a circle of radius 6cm. find the length of the arc if π = ²²⁄₇", "options": {"A": "11cm", "B": "12cm", "C": "13cm", "D": "14cm"}, "answer": "A"},
    {"stem": "39. Calculate the perimeter of a sector of a circle of radius 7cm, the angle of the sector being 108° if π is ²²⁄₇", "options": {"A": "13.2cm", "B": "40cm", "C": "5cm", "D": "27.2cm"}, "answer": "D"},
    {"stem": "40. An arc subtends an angle of 72 at the circumference of a circle of radius 5cm. calculate the length of the arc in terms of π", "options": {"A": "π", "B": "2 π", "C": "3 π", "D": "4 π"}, "answer": "D"},
]

THEORY = [
    {
        "stem": (
            "1) Copy and Complete the table of values for the relation y = x^2 -2 x -1 for -2 ≤ x ≤ 4\n\n"
            "x   -2  -1  0  1  2  3  4\n"
            "y   -4\n\n"
            "a. Using scales of 2cm to 1 units on both axis\n"
            "b. From the graph Find the minimum value of y\n"
            "c. Use the graph to find the roots of the equation x^2 -2x -1 = 0\n"
            "d. Using the axis draw graph of y = 2x -3\n"
            "e. From the graph determine the roots of the equation x^2 – 2x -1 = 2x -3"
        ),
        "marks": Decimal("10.00"),
        "image": "THEORY NO 1.png",
    },
    {
        "stem": "2) Solve x^2 = 10x + 39\nb) factorise b^2 – 12b – 13",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3) Estimate (95.4 ×149)⁄(5.2 ×49.1) correct to one significant figure.\n"
            "B) A pencil is 18cm long someone estimated it length to be 20cm. calculate the percentage error"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4) Show that ~(P^Q) v Q is tautology\nb) Show that P^(Q^P)",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5) a. The diagram shows a wooden structure in form of a cone, mounted on a hemispherical base. "
            "The vertical height of the cone is 48m and the base radius is 14m.[take π ²²⁄₇]\n"
            "b. What is the length of an arc which subtends an angle of 60 at the center of a circle of radius 7"
        ),
        "marks": Decimal("10.00"),
        "image": "THEORY NO 5.png",
    },
    {
        "stem": (
            "6) Copy and complete the table of values for the relation –x^2 + x + 2 for -3≤x≤3\n\n"
            "x   -3  -2  -1  0  1  2  3\n"
            "y   -4  -4\n\n"
            "a. Using scales of 2cm to I unit on x axis and 2cm to 2units on y axis\n"
            "b. From the graph find:\n"
            "I. Maximum value of y\n"
            "II. The roots of the equation x^2 – x – 2 = 0\n"
            "III. Gradient of curve at x = - 0.5"
        ),
        "marks": Decimal("10.00"),
        "image": "THEORY NO 6.png",
    },
    {
        "stem": "7) a) What is the total surface area of a closed cylinder of height 10cm and diameter 7cm? (take ²²⁄₇) (6marks)\nb) Find the volume of the cylinder(4marks)",
        "marks": Decimal("10.00"),
    },
]


def _exam_assets_root():
    return Path.cwd() / "EXAM" / "ss"


def _image_data_uri(image_name):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _rich_stem_with_image(stem, *, image_name, caption=""):
    body = "<br>".join(stem.splitlines())
    image_url = _image_data_uri(image_name)
    caption_html = f"<figcaption style=\"margin-top:8px;font-size:0.9rem;color:#475569;\">{caption}</figcaption>" if caption else ""
    return (
        f"<div>{body}</div>"
        f"<figure class=\"cbt-inline-figure\" style=\"margin-top:12px;\">"
        f"<img src=\"{image_url}\" alt=\"Question diagram\" "
        f"style=\"max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:12px;padding:8px;background:#fff;\">"
        f"{caption_html}"
        f"</figure>"
    )


def _shared_table_10_14(stem):
    return (
        "<div>Use the below table to answer question 10 – 14</div>"
        "<table style=\"margin-top:12px;border-collapse:collapse;width:100%;max-width:760px;\">"
        "<tr><td style=\"border:1px solid #94a3b8;padding:6px;\">P</td><td style=\"border:1px solid #94a3b8;padding:6px;\">Q</td><td style=\"border:1px solid #94a3b8;padding:6px;\">~Q</td><td style=\"border:1px solid #94a3b8;padding:6px;\">P ^~Q</td><td style=\"border:1px solid #94a3b8;padding:6px;\">~ (P^Q)</td></tr>"
        "<tr><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">A</td><td style=\"border:1px solid #94a3b8;padding:6px;\">B</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td></tr>"
        "<tr><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td></tr>"
        "<tr><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">C</td><td style=\"border:1px solid #94a3b8;padding:6px;\">D</td></tr>"
        "<tr><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">T</td><td style=\"border:1px solid #94a3b8;padding:6px;\">F</td><td style=\"border:1px solid #94a3b8;padding:6px;\">E</td></tr>"
        "</table>"
        f"<div style=\"margin-top:12px;\">{stem}</div>"
    )


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="MTH")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="susan@ndgakuje.org",
        academic_class=academic_class,
        subject=subject,
        session=session,
        term=term,
        is_active=True,
    )
    teacher = assignment.teacher
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 23, 8, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 9, 20, tzinfo=lagos)

    bank, _ = QuestionBank.objects.get_or_create(
        owner=teacher,
        name=BANK_NAME,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={"description": DESCRIPTION, "assignment": assignment, "is_active": True},
    )
    bank.description = DESCRIPTION
    bank.assignment = assignment
    bank.is_active = True
    bank.save()

    exam, created = Exam.objects.get_or_create(
        title=TITLE,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={
            "description": DESCRIPTION,
            "exam_type": CBTExamType.EXAM,
            "status": CBTExamStatus.ACTIVE,
            "created_by": teacher,
            "assignment": assignment,
            "question_bank": bank,
            "dean_reviewed_by": dean_user,
            "dean_reviewed_at": timezone.now(),
            "dean_review_comment": "Approved for Monday morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 8:00 AM WAT.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts. Refusing to overwrite live content.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for Monday morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 8:00 AM WAT."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    ExamQuestion.objects.filter(exam=exam).delete()
    bank.questions.all().delete()

    sort_order = 1
    for index, item in enumerate(OBJECTIVES, start=1):
        rich_stem = ""
        if item.get("shared_html") == "table_10_14":
            rich_stem = _shared_table_10_14(item["stem"])
        elif item.get("image"):
            rich_stem = _rich_stem_with_image(item["stem"], image_name=item["image"])
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=Decimal("1.00"),
            source_reference=f"SS1-MTH-20260323-OBJ-{index:02d}",
            is_active=True,
        )
        option_map = {}
        for option_index, label in enumerate(("A", "B", "C", "D"), start=1):
            option_map[label] = Option.objects.create(
                question=question,
                label=label,
                option_text=item["options"][label],
                sort_order=option_index,
            )
        answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.add(option_map[item["answer"]])
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=Decimal("1.00"))
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            rich_stem=_rich_stem_with_image(item["stem"], image_name=item["image"]) if item.get("image") else "",
            marks=item["marks"],
            source_reference=f"SS1-MTH-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 70
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS1-MTH-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "20.00",
        "theory_target_max": "40.00",
    }
    blueprint.passing_score = Decimal("0.00")
    blueprint.objective_writeback_target = CBTWritebackTarget.OBJECTIVE
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.THEORY
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()

    print(
        {
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
            "rich_stem_objective_rows": [
                index for index, item in enumerate(OBJECTIVES, start=1) if item.get("shared_html") or item.get("image")
            ],
            "rich_stem_theory_rows": [index for index, item in enumerate(THEORY, start=1) if item.get("image")],
        }
    )


main()
