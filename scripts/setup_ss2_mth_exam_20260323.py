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


TITLE = "MON 8:00-10:00 SS2 Mathematics Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: SS2 SUBJECT: MATHEMATICS"
BANK_NAME = "SS2 Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in Section A and answer question 1 and any other 3 questions in Section B. "
    "Timer is 90 minutes. Exam window closes at 10:00 AM WAT on Monday, March 23, 2026."
)

NAIRA = "\u20a6"

OBJECTIVES = [
    {
        "stem": "1. Approximate 123 466 540 to the nearest ten",
        "options": {"A": "123 466 540", "B": "123 466 500", "C": "123 466 600", "D": "123 466 700"},
        "answer": "A",
    },
    {
        "stem": "2. Approximate 123 466 540 to the nearest hundred",
        "options": {"A": "123 466 500", "B": "123 500 000", "C": "123 470 000", "D": "123 570 000"},
        "answer": "A",
    },
    {
        "stem": "3. Approximate 123 466 540 to the nearest thousand",
        "options": {"A": "123 477 000", "B": "123 577 000", "C": "123 467 000", "D": "123 578 000"},
        "answer": "C",
    },
    {
        "stem": "4. Approximate 123 466 540 to the nearest million",
        "options": {"A": "123 100 000", "B": "124 000 000", "C": "123 000 000", "D": "120 000 000"},
        "answer": "C",
    },
    {
        "stem": "5. Approximate 123 466 540 to the nearest billion",
        "options": {"A": "0.123", "B": "0.000", "C": "0.120", "D": "0.100"},
        "answer": "A",
    },
    {
        "stem": "6. Round 0.05586 to two decimal place",
        "options": {"A": "0.05", "B": "0.06", "C": "0.055", "D": "0.056"},
        "answer": "B",
    },
    {
        "stem": "7. Round 30.0638 to two decimal place",
        "options": {"A": "30.10", "B": "30.06", "C": "30.07", "D": "30.07"},
        "answer": "B",
    },
    {
        "stem": "8. The population of a village is 365 846. Express the population to 5 significant figures",
        "options": {"A": "365 850", "B": "365 800", "C": "365 900", "D": "365 950"},
        "answer": "A",
    },
    {
        "stem": "9. The seventh term of the GP 16/9, -8/3, 4, ..... is",
        "options": {"A": "81/4", "B": "1/257", "C": "1/356", "D": "1/357"},
        "answer": "A",
    },
    {
        "stem": "10. Calculate the angle at the centre of a circle, subtended by a chord 6 cm from the centre of the circle with radius 10 cm",
        "options": {"A": "106.30", "B": "107.20", "C": "107.40", "D": "108.50"},
        "answer": "A",
    },
    {
        "stem": "11. A chord 12 cm long subtends an angle of 40 degrees at the centre of the circle. Calculate the radius of the circle.",
        "options": {"A": "17.5 cm", "B": "17.8 cm", "C": "17.54 cm", "D": "17.4 cm"},
        "answer": "C",
    },
    {
        "stem": "12. Find the length of a chord which subtends an angle of 58 degrees at the centre of a circle with radius 16 cm",
        "options": {"A": "13.2 cm", "B": "15.51 cm", "C": "13.4 cm", "D": "13.5 cm"},
        "answer": "B",
    },
    {
        "stem": "13. Find the values for which 4x - 5 < 11",
        "options": {"A": "x < 5", "B": "x < 4", "C": "x > 5", "D": "x > 4"},
        "answer": "B",
    },
    {
        "stem": "14. Solve the equation x = 3/(x + 2)",
        "options": {"A": "x = 1 or x = -1", "B": "x = -1 or x = 3", "C": "x = 2 or x = 3", "D": "x = -1 or x = -3"},
        "answer": "B",
    },
    {
        "stem": "15. Find the value of x",
        "options": {"A": "80 degrees", "B": "81 degrees", "C": "82 degrees", "D": "83 degrees"},
        "answer": "B",
        "image": "15 to 17 ss2 maths.png",
    },
    {
        "stem": "16. Find the value of y",
        "options": {"A": "83 degrees", "B": "82 degrees", "C": "81 degrees", "D": "80 degrees"},
        "answer": "D",
        "image": "15 to 17 ss2 maths.png",
    },
    {
        "stem": "17. Find the value of z",
        "options": {"A": "100 degrees", "B": "99 degrees", "C": "90 degrees", "D": "88 degrees"},
        "answer": "B",
        "image": "15 to 17 ss2 maths.png",
    },
    {
        "stem": "18. The sum of squares of two consecutive even numbers is 52. Find the numbers.",
        "options": {"A": "x = 4 or x = 6", "B": "x = -4 or x = -6", "C": "x = 4 or x = -6", "D": "x = -4 or x = 6"},
        "answer": "C",
    },
    {
        "stem": "19. Find the value of A",
        "options": {"A": f"{NAIRA}25", "B": "50", "C": "40", "D": "35"},
        "answer": "A",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "20. Find the value of B",
        "options": {"A": "0.75 m", "B": "0.65 m", "C": "0.55 m", "D": "0.45 m"},
        "answer": "A",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "21. Find the value of C",
        "options": {"A": "10 cm^2", "B": "8 cm^2", "C": "11 cm^2", "D": "9 cm^2"},
        "answer": "D",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "22. Find the value of D",
        "options": {"A": "3 x 10^2", "B": "3 x 10^-2", "C": "30000", "D": "4 x 10^2"},
        "answer": "A",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "23. Find the value of E",
        "options": {"A": "400", "B": "600", "C": "500", "D": "550"},
        "answer": "C",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "24. Find the value of F",
        "options": {"A": "6.25%", "B": "6.15%", "C": "5.25%", "D": "6%"},
        "answer": "A",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "25. Find the value of G",
        "options": {"A": "10%", "B": "12%", "C": "13%", "D": "15%"},
        "answer": "B",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "26. Find the value of H",
        "options": {"A": "12%", "B": "13%", "C": "14%", "D": "12.5%"},
        "answer": "D",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "27. Find the value of I",
        "options": {"A": "6 1/4%", "B": "6%", "C": "3 1/4%", "D": "4 1/4%"},
        "answer": "A",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "28. Find the value of J",
        "options": {"A": "11/19%", "B": "2%", "C": "6.7%", "D": "1%"},
        "answer": "C",
        "image": "19 to 28 ss2 maths.png",
    },
    {
        "stem": "29. Find the value of a + b + c",
        "options": {"A": "10", "B": "20", "C": "18", "D": "15"},
        "answer": "D",
    },
    {
        "stem": "30. Find the value of 5[ac + by]",
        "options": {"A": "50", "B": "60", "C": "40", "D": "55"},
        "answer": "C",
    },
    {
        "stem": "31. Find sqrt(bc + 3a)",
        "options": {"A": "6 and -6", "B": "5 and -5", "C": "6", "D": "5"},
        "answer": "A",
    },
    {
        "stem": "32. Find the value of (cy)^2",
        "options": {"A": "1400", "B": "1500", "C": "1600", "D": "1800"},
        "answer": "C",
    },
    {
        "stem": "33. Find ab + y",
        "options": {"A": "2", "B": "8", "C": "10", "D": "14"},
        "answer": "A",
    },
    {
        "stem": "34. Solve x/3 + 5 = 2x",
        "options": {"A": "4", "B": "5", "C": "6", "D": "3"},
        "answer": "D",
    },
    {
        "stem": "35. Find the 50th term of A.P. 3, 7, 11, .....",
        "options": {"A": "200", "B": "199", "C": "240", "D": "800"},
        "answer": "B",
    },
    {
        "stem": "36. Find the 6th term of A.P. -2, -4, -6, ......",
        "options": {"A": "12", "B": "-12", "C": "13", "D": "-13"},
        "answer": "B",
    },
    {
        "stem": "37. Find the formula for the nth term of the A.P. 3, 7, 11",
        "options": {"A": "4n - 1", "B": "4n", "C": "5n - 1", "D": "6n - 1"},
        "answer": "A",
    },
    {
        "stem": "38. The sum of the first n term of an A.P. is 252. If the first term is -16 and the last term is 72, find the number of terms in the series",
        "options": {"A": "8", "B": "10", "C": "11", "D": "9"},
        "answer": "D",
    },
    {
        "stem": "39. Express, correct to three significant figures, 0.003592",
        "options": {"A": "0.359", "B": "0.004", "C": "0.00360", "D": "0.00359"},
        "answer": "D",
    },
    {
        "stem": "40. Evaluate (0.064)^-1/3",
        "options": {"A": "5/2", "B": "2/5", "C": "-2/5", "D": "-5/2"},
        "answer": "A",
    },
]

THEORY = [
    {
        "stem": (
            "1. (a) Copy and complete the table of values for the relation\n"
            "   y = x^2 - 2x - 1   for   -2 <= x <= 4\n\n"
            "   x   -2   -1    0    1    2    3    4\n"
            "   y                 -1\n\n"
            "(b) Draw the graph of the relation using a scale of 2 cm to 1 unit on both axes.\n"
            "(c) Use your graph to find the roots of the equation x^2 - 2x - 1 = 0.\n"
            "(d) Using the same axes, draw the graph of y = 2x - 3.\n"
            "(e) From your graphs, determine the roots of the equation x^2 - 2x - 1 = 2x - 3."
        ),
        "marks": Decimal("10.00"),
        "image": "ss2 maths no 1.png",
        "caption": "Value table for theory question 1(a)",
    },
    {
        "stem": (
            "2. A man leaves his house and travels 21 km on a bearing of 032 degrees and then 45 km on a bearing of 287 degrees.\n"
            "(a) Calculate the distance between the man's final position and his house.\n"
            "(b) Calculate the bearing of the man's house from his final position."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. A factory produces two products A and B. There are two constraints, namely:\n"
            "(a) A time constraint: 4a + 2b <= 100\n"
            "(b) A material constraint: 2a + 6b <= 180\n\n"
            "Where a and b are cost of products A and B respectively. If A requires "
            f"{NAIRA}800, and B = {NAIRA}600, find the most feasible cost of production."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4. The third term of a G.P. is 360 and the sixth term is 1215. Find the:\n"
            "(a) Common ratio\n"
            "(b) First term\n"
            "(c) Sum of the first four terms"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. A pair of fair dice are thrown once. What is the probability of getting?\n"
            "(a) a double number?\n"
            "(b) a number greater than 8?\n"
            "(c) a number greater than 5 or a double number?\n"
            "(d) a sum of numbers divisible by 3 or a number greater than 12?"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. (a) Evaluate\n"
            "        sqrt((17.45 x (35.2)^2) / ((3.15)^4 x 8.15))\n"
            "    correct to 3 significant figures.\n\n"
            "(b) Solve the quadratic equation using the quadratic formula:\n"
            "    3x^2 - x + 5"
        ),
        "marks": Decimal("10.00"),
        "image": "no 6 theory ss2.png",
        "caption": "Expression diagram for theory question 6(a)",
    },
]


def _exam_assets_root():
    return Path.cwd() / "EXAM"


def _image_data_uri(image_name):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _rich_stem_with_image(stem, *, image_name, caption=""):
    body = "<br>".join(stem.splitlines())
    image_url = _image_data_uri(image_name)
    caption_html = (
        f"<figcaption style=\"margin-top:8px;font-size:0.9rem;color:#475569;\">{caption}</figcaption>"
        if caption
        else ""
    )
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
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="MTH")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="emmanuel@ndgakuje.org",
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
    schedule_end = datetime(2026, 3, 23, 10, 0, tzinfo=lagos)

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
        if item.get("image"):
            rich_stem = _rich_stem_with_image(item["stem"], image_name=item["image"])
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=Decimal("1.00"),
            source_reference=f"SS2-MTH-20260323-OBJ-{index:02d}",
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
        rich_stem = ""
        if item.get("image"):
            rich_stem = _rich_stem_with_image(
                item["stem"],
                image_name=item["image"],
                caption=item.get("caption", ""),
            )
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=item["marks"],
            source_reference=f"SS2-MTH-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS2-MTH-EXAM",
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
            "rich_stem_objective_rows": [index for index, item in enumerate(OBJECTIVES, start=1) if item.get("image")],
            "rich_stem_theory_rows": [index for index, item in enumerate(THEORY, start=1) if item.get("image")],
        }
    )


main()
