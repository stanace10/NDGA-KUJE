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


TITLE = "MON 8:00-9:20 JS3 Mathematics Second Term Exam"
DESCRIPTION = "J S 3 SECOND TERM EXAMINATION SUBJECT: MATHEMATICS"
BANK_NAME = "JS3 Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in Section A and any five (5) in Section B. "
    "Timer is 70 minutes. Exam window closes at 9:20 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Which of the following numbers is not a perfect square?", "options": {"A": "64", "B": "81", "C": "100", "D": "120"}, "answer": "D"},
    {"stem": "2. Find the LCM of 30, 45, 60 and 90.", "options": {"A": "5", "B": "60", "C": "180", "D": "360"}, "answer": "C"},
    {"stem": "3. Simplify ³⁄₁₀₀ + ³⁰⁄₁₀₀, correct to 1 decimal place.", "options": {"A": "0.2", "B": "0.3", "C": "0.4", "D": "0.7"}, "answer": "B"},
    {"stem": "4. Simplify √¹⁴⁴⁄₃", "options": {"A": "4", "B": "6", "C": "12", "D": "24"}, "answer": "A"},
    {"stem": "5. Express 2211₄ as denary number", "options": {"A": "48", "B": "160", "C": "165", "D": "168"}, "answer": "C"},
    {"stem": "6. Find the square root of ⁷⁵⁰⁄₁₀₈₀", "options": {"A": "²⁄₃", "B": "³⁄₄", "C": "⁴⁄₅", "D": "⁵⁄₆"}, "answer": "D"},
    {"stem": "7. Evaluate 5³ - √25", "options": {"A": "150", "B": "125", "C": "120", "D": "0"}, "answer": "C"},
    {"stem": "8. How many vertices does a cuboids have?", "options": {"A": "4", "B": "6", "C": "8", "D": "12"}, "answer": "C"},
    {"stem": "9. Find the perimeter of a square whose side is 10cm", "options": {"A": "10cm", "B": "25cm", "C": "35cm", "D": "40cm"}, "answer": "D"},
    {"stem": "10. The Volume of a cylinder is given by the formula:", "options": {"A": "πr", "B": "πr²", "C": "πr²h", "D": "2πr"}, "answer": "C"},
    {"stem": "11. Find the radius of a circle, if its circumference is 132cm. (Take π = ²²⁄₇)", "options": {"A": "14cm", "B": "16cm", "C": "18cm", "D": "21cm"}, "answer": "D"},
    {"stem": "12. Simplify 4(a+1) +5(a+2)", "options": {"A": "5a + 10", "B": "9 + 14a", "C": "9a + 14", "D": "10a + 14"}, "answer": "C"},
    {"stem": "13. Solve the equation ¹²⁄₍₃ₓ₊₁₎ = ³⁄ₓ .", "options": {"A": "5", "B": "4", "C": "3", "D": "1"}, "answer": "D"},
    {"stem": "14. Find the LCM of 9x and 4x²y", "options": {"A": "9x²y", "B": "18x²y", "C": "36x²y", "D": "45x²y"}, "answer": "C"},
    {"stem": "15. Solve the inequality 2x − 3 > 11", "options": {"A": "x >3", "B": "x > 7", "C": "x >8", "D": "x >11"}, "answer": "B"},
    {"stem": "16. Solve the equation x⁄₃ + x = 1", "options": {"A": "4", "B": "3", "C": "1", "D": "³⁄₄"}, "answer": "D"},
    {"stem": "17. Expand and simplify (2x - 3)(x - 5)", "options": {"A": "2x² − 13x − 15", "B": "2x² − 13x + 15", "C": "2x² + 13x − 15", "D": "2x² + 13x + 15"}, "answer": "B"},
    {"stem": "18. Factorize 9a + 27", "options": {"A": "9(a+3)", "B": "9(a - 27)", "C": "9(a-3)", "D": "9(3a- 7)"}, "answer": "A"},
    {"stem": "19. If the sum of the square of six and the square root of 81 is divided by 5, the result is", "options": {"A": "11", "B": "9", "C": "5", "D": "3"}, "answer": "B"},
    {"stem": "20. If -7 is added to a certain number, and the result is 45. What is the number?", "options": {"A": "42", "B": "35", "C": "52", "D": "12."}, "answer": "C"},
    {"stem": "21. Find the positive difference between 18 and 43", "options": {"A": "-25", "B": "-68", "C": "25", "D": "-18"}, "answer": "C"},
    {"stem": "22. The product of 8 and r is 480. Find r.", "options": {"A": "8", "B": "8r", "C": "480", "D": "60"}, "answer": "D"},
    {"stem": "23. Write 0.00000082 in standard form", "options": {"A": "10 × 10⁸", "B": "8.2 × 10⁷", "C": "8.2 × 10⁻⁷", "D": "8.2 × 10⁻⁸"}, "answer": "C"},
    {"stem": "24. Make t the subject from the formula c = a + kt", "options": {"A": "t = c + a − k", "B": "t = (c−a)⁄k", "C": "t = (k−a)⁄c", "D": "t = (a−k)⁄c"}, "answer": "B"},
    {"stem": "25. If y = f⁄g − h. What is y when f =13, g = 26 and h=³⁄₇ ?", "options": {"A": "¹⁄₁₄", "B": "²⁄₁₄", "C": "³⁄₁₄", "D": "⁴⁄₁₄"}, "answer": "A"},
    {"stem": "26. Evaluate d² − 2u when d = 16 and u = 56.", "options": {"A": "144", "B": "12", "C": "256", "D": "112"}, "answer": "A"},
    {"stem": "27. Calculate the simple interest on ₦4500 for 3 years at 6% per annum.", "options": {"A": "₦810", "B": "₦820", "C": "₦830", "D": "₦840"}, "answer": "A"},
    {"stem": "28. If b = ¹⁄₂ c⁄₍₃d₋₄₎ , find the value of b when c = 8, d =4.", "options": {"A": "0.2", "B": "0.3", "C": "0.4", "D": "0.5"}, "answer": "D"},
    {"stem": "29. Factorize 16xy + 14x².", "options": {"A": "2x(8y + 7x )", "B": "3y(8x + 7y )", "C": "4y(2x + 7y )", "D": "5y(3x + 3y )"}, "answer": "A"},
    {"stem": "30. Expand and Simplify 2(a − 2 ) + 3(a − 3)", "options": {"A": "5a − 14", "B": "6a − 13", "C": "4a + 13", "D": "5a − 13"}, "answer": "D"},
    {"stem": "31. What is the square of the square root of 81", "options": {"A": "9", "B": "900", "C": "81", "D": "91."}, "answer": "C"},
    {"stem": "32. Find the square root of ⁷⁵⁄₃₀₀", "options": {"A": "¹⁄₂", "B": "¹⁄₅", "C": "2", "D": "4"}, "answer": "A"},
    {"stem": "33. Simplify ⁹⁄₁₃ ÷ ³⁄₄", "options": {"A": "¹³⁄₁₂", "B": "²⁸⁄₃₉", "C": "¹²⁄₁₃", "D": "⁵²⁄₂₈"}, "answer": "C"},
    {"stem": "34. Simplify ²⁄₃ + ¹⁄₅", "options": {"A": "¹³⁄₁₅", "B": "¹⁵⁄₁₃", "C": "¹⁷⁄₁₅", "D": "¹⁰⁄₁₅"}, "answer": "A"},
    {"stem": "35. Divide 100 by the positive difference between 65 and 75.", "options": {"A": "5", "B": "10", "C": "15", "D": "20"}, "answer": "B"},
    {"stem": "36. Convert 9 ¹⁄₅ to improper fraction.", "options": {"A": "⁹⁄₅", "B": "¹⁰⁄₇", "C": "⁴⁶⁄₅", "D": "⁶³⁄₇"}, "answer": "C"},
    {"stem": "37. If 9 packets of cream cost ₦4500.00. Find the cost of 6 packets.", "options": {"A": "₦2000.00", "B": "₦2150.00", "C": "₦2250.00", "D": "₦3000.00"}, "answer": "D"},
    {"stem": "38. A die is rolled, what is the probability of getting a perfect square", "options": {"A": "¹⁄₃", "B": "¹⁄₂", "C": "²⁄₃", "D": "¹⁄₆"}, "answer": "A"},
    {"stem": "39. How many edges does a cube have?", "options": {"A": "12", "B": "10", "C": "8", "D": "6"}, "answer": "A"},
    {"stem": "40. How many vertices does a rectangular pyramid have?", "options": {"A": "4", "B": "5", "C": "6", "D": "7"}, "answer": "B"},
    {"stem": "41. Find the reciprocal of ⁵⁄₆", "options": {"A": "1.5", "B": "1.2", "C": "3.5", "D": "4.5"}, "answer": "B"},
    {"stem": "42. Express 0.35 as a fraction in the lowest terms.", "options": {"A": "²⁰⁄₇", "B": "⁷⁄₂₀", "C": "⁵⁄₇", "D": "⁷⁄₅"}, "answer": "B"},
    {"stem": "43. Find the reciprocal of 8.", "options": {"A": "0.125", "B": "1.125", "C": "2.125", "D": "3.125"}, "answer": "A"},
    {"stem": "44. Evaluate 1010₂ − 101₂", "options": {"A": "111₂", "B": "110₂", "C": "101₂", "D": "1011₂"}, "answer": "C"},
    {"stem": "45. 5 pies cost ₦730. How much will 9 pies cost?", "options": {"A": "₦1,314", "B": "₦1,214", "C": "₦1,414", "D": "₦1,514"}, "answer": "A"},
    {"stem": "46. Find the value of (1.1₂)³ in base 10.", "options": {"A": "²⁷⁄₈", "B": "⁹⁄₄", "C": "¹⁄₂₇", "D": "¹⁄₈"}, "answer": "A"},
    {"stem": "47. Convert 25₁₀ in base two.", "options": {"A": "11001₂", "B": "11010₂", "C": "10011₂", "D": "1001₂"}, "answer": "A"},
    {"stem": "48. Find the area of a square with length of sides 0.5m", "options": {"A": "25m²", "B": "0.2m²", "C": "0.25m²", "D": "0.52m²"}, "answer": "C"},
    {"stem": "49. 12 nights camp accommodation cost ₦6720. What will one night cost?", "options": {"A": "₦560", "B": "₦460", "C": "₦360", "D": "₦660"}, "answer": "A"},
    {"stem": "50. The base (b) of a triangular object is 9cm and the height (h) is 6cm. Find its area.", "options": {"A": "27cm²", "B": "54cm²", "C": "28cm²", "D": "29cm²"}, "answer": "A"},
    {"stem": "51. Find the area of a circle of radius 7cm (Take π = 22/7)", "options": {"A": "154cm²", "B": "308cm²", "C": "408cm²", "D": "254cm²"}, "answer": "A"},
    {"stem": "52. The ratio of the circumference of a circle to its diameter is known as ---", "options": {"A": "pi(π)", "B": "diameter", "C": "Radii", "D": "Non-rational"}, "answer": "A"},
    {"stem": "53. Evaluate 101₂ × 11₂", "options": {"A": "1111₂", "B": "1001₂", "C": "1100₂", "D": "10011₂"}, "answer": "A"},
    {"stem": "54. Solve the equation ²⁄₍m₋₁₎ =1", "options": {"A": "3", "B": "4", "C": "1", "D": "2"}, "answer": "A"},
    {"stem": "55. Find the HCF of 15xy² and 25x²y", "options": {"A": "5xy", "B": "10xy", "C": "15xy", "D": "25xy"}, "answer": "A"},
    {"stem": "56. Factorize 9x² − 1", "options": {"A": "9(x² − 1)", "B": "(3x² − 1)", "C": "(3x − 1)(3x + 1)", "D": "(3x + 1)(3x + 1)"}, "answer": "C"},
    {"stem": "57. Make h the subject of formula V = πh(R + r).", "options": {"A": "h = r⁄V(Rπ)", "B": "h = V⁄π(R+r)", "C": "h = R⁄V(rπ)", "D": "h = π⁄V(R−r)"}, "answer": "B"},
    {"stem": "58. Multiply out the bracket -7(2a – 3b)", "options": {"A": "7a + 2b", "B": "-7a – 21b", "C": "-14a + 21b", "D": "-7a + 21b"}, "answer": "C"},
    {"stem": "59. Find the square root of ¹⁰⁰⁄₂₅", "options": {"A": "2", "B": "5", "C": "10", "D": "15"}, "answer": "A"},
    {"stem": "60. The diameter of a circle is y + 2 . Calculate the radius of the circle?", "options": {"A": "y + 2", "B": "(y+2)⁄r", "C": "(y+2)⁄₂", "D": "y⁄r"}, "answer": "C"},
]

THEORY = [
    {
        "stem": "1. Solve the equation ³ˣ⁻²⁄₆ = (4+5x)⁄₅ .\n\na. Express 34277₈ to a number in binary.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. Calculate the 5th angle of the pentagon whose other four angles are 89°, 202°, 101°, and 132°.\n\n"
            "b. The table below shows the scores of students in a mathematics examination.\n"
            "I. How many students took part in the test?\n"
            "II. What is the probability of scoring 64\n"
            "III. What is the probability of scoring 66\n"
            "IV. What is the probability of scoring 67.\n"
            "V. Calculate the percentage of scoring 63."
        ),
        "marks": Decimal("10.00"),
        "image": "JS3 THEORY NO 2B.png",
        "caption": "Scores table for theory question 2(b)",
    },
    {
        "stem": "3. Make r the subject of formula V = πh(R + r).\n\nI. If f = (t+4u)⁄₃ₜ , find the value of f when t = 10 and u = 2.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4. Name the similar triangles, giving the letters in corresponding order. Find the missing sides.",
        "marks": Decimal("10.00"),
        "image": "JS3 THEORY NO 4.png",
        "caption": "Similar triangles diagram for theory question 4",
    },
    {
        "stem": "5. Find the compound interest and the final amount for ₦40000 for 2 years at 6% per annum.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. Sketch the isometric view of the following three dimensional shapes with at least two properties:\n"
            "(i) Cylinder\n"
            "(ii) rectangular pyramid\n"
            "(iii) Cuboid\n"
            "(iv) cone."
        ),
        "marks": Decimal("10.00"),
    },
]


def _exam_assets_root():
    return Path.cwd() / "EXAM" / "js"


def _image_data_uri(image_name):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _rich_stem(stem, *, image_name=None, caption=""):
    if not image_name:
        return ""
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


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="MTH")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="mdaniel@ndgakuje.org",
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
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            marks=Decimal("1.00"),
            source_reference=f"JS3-MTH-20260323-OBJ-{index:02d}",
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
            rich_stem=_rich_stem(item["stem"], image_name=item.get("image"), caption=item.get("caption", "")),
            marks=item["marks"],
            source_reference=f"JS3-MTH-20260323-TH-{index:02d}",
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
        "paper_code": "JS3-MTH-EXAM",
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
            "rich_stem_theory_rows": [index for index, item in enumerate(THEORY, start=1) if item.get("image")],
        }
    )


main()
