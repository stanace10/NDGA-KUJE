from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.files import File
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


TITLE = "MON 8:00-9:20 JS2 Mathematics Second Term Exam"
DESCRIPTION = "JS2 MATHS EXAMS SECOND TERM 2025/2026"
BANK_NAME = "JS2 Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer number 1 and any other 3 questions. "
    "Timer is 65 minutes. Exam window closes at 9:20 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {
        "stem": "1. If a = 2, b = -3 and c = 4 find 4a - 3b + 2c",
        "options": {"A": "9", "B": "25", "C": "8", "D": "7"},
        "answer": "B",
    },
    {
        "stem": "2. If a = 2, b = -3 and c = 4 find (4a - 2c) / 36",
        "options": {"A": "0", "B": "1", "C": "2", "D": "3"},
        "answer": "A",
    },
    {
        "stem": "3. Find the simple interest on N3000 for 2 years at the rate of 3% per annum",
        "options": {"A": "N180", "B": "N180", "C": "N10", "D": "N30"},
        "answer": "B",
    },
    {
        "stem": "4. Mr Abubakar borrowed N120000 for 2 years to finance his building project. If the interest charge was N10000, find the amount he paid back.",
        "options": {"A": "N130000", "B": "N120000", "C": "N110000", "D": "N100000"},
        "answer": "A",
    },
    {
        "stem": "5. Simplify 5y + (7y - 2y)",
        "options": {"A": "10y", "B": "12y", "C": "2y", "D": "7y"},
        "answer": "A",
    },
    {
        "stem": "6. Simplify 2y + (4y - 12y) + (6y + y)",
        "options": {"A": "6y", "B": "5y", "C": "4y", "D": "y"},
        "answer": "D",
    },
    {
        "stem": "7. Simplify (a - b) - (d - e)",
        "options": {"A": "a + b - d - e", "B": "a - b - d + e", "C": "abde", "D": "ab - de"},
        "answer": "B",
    },
    {
        "stem": "8. Simplify 3(a + b) + 4(a + 2b)",
        "options": {"A": "7a + 11b", "B": "7a + 5b", "C": "8a - b", "D": "5a + 4b"},
        "answer": "A",
    },
    {
        "stem": "9. Simplify 8(a + 3) - 2(3a + 4)",
        "options": {"A": "a + 1", "B": "a - 1", "C": "2a + 16", "D": "2a - 16"},
        "answer": "C",
    },
    {
        "stem": "10. Find the highest common factor of 3x and 18y",
        "options": {"A": "3", "B": "6", "C": "3x", "D": "6y"},
        "answer": "A",
    },
    {
        "stem": "11. Find the highest common factor of 6xy, 3x^2 and 9xy",
        "options": {"A": "3x", "B": "6x", "C": "9x", "D": "12x"},
        "answer": "A",
    },
    {
        "stem": "12. Simplify 2u/3 - u/6",
        "options": {"A": "u/2", "B": "2u/3", "C": "2u/5", "D": "a/2"},
        "answer": "A",
    },
    {
        "stem": "13. Simplify 3a^2b x 4ab",
        "options": {"A": "12a^2b", "B": "12a^3b^2", "C": "7a^2b", "D": "7a^3b"},
        "answer": "B",
    },
    {
        "stem": "14. Solve 2x - 1 = 3x - 2",
        "options": {"A": "-1", "B": "1", "C": "-2", "D": "2"},
        "answer": "B",
    },
    {
        "stem": "15. Solve 13 - 4y = 4y - 3",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "answer": "B",
    },
    {
        "stem": "16. Solve 5x - 9 = 2x - 6",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "answer": "A",
    },
    {
        "stem": "17. Solve 7y - 15 = 4(y - 3)",
        "options": {"A": "-1", "B": "1", "C": "2", "D": "-2"},
        "answer": "B",
    },
    {
        "stem": "18. Solve 3(4x + 5) = -3",
        "options": {"A": "-3/2", "B": "-2/3", "C": "1/4", "D": "-3"},
        "answer": "A",
    },
    {
        "stem": "19. When a number is doubled and 12 is added, the result is 40. Find the number.",
        "options": {"A": "10", "B": "11", "C": "12", "D": "14"},
        "answer": "D",
    },
    {
        "stem": "20. A number is added to 7 and divided by 12 to give 4. Find the number.",
        "options": {"A": "21", "B": "31", "C": "41", "D": "51"},
        "answer": "C",
    },
    {
        "stem": "21. Solve 2x - 3 > 11",
        "options": {"A": "x > 7", "B": "x < 7", "C": "x >= -7", "D": "x <= 10"},
        "answer": "A",
    },
    {
        "stem": "22. Solve 3x - 2 >= x + 19",
        "options": {"A": "x = 7", "B": "x >= 7", "C": "x > 7", "D": "x >= 21"},
        "answer": "B",
    },
    {
        "stem": "23. Solve 1 - x < 6",
        "options": {"A": "x < -5", "B": "x > -5", "C": "x >= -10", "D": "x <= 12"},
        "answer": "B",
    },
    {
        "stem": "24. The following are examples of two dimensional shapes except",
        "options": {"A": "Circle", "B": "Square", "C": "Triangle", "D": "Cone"},
        "answer": "D",
    },
    {
        "stem": "25. The following have line of symmetry",
        "options": {"A": "Square", "B": "Rectangle", "C": "Parallelogram", "D": "Circle"},
        "answer": "D",
    },
    {
        "stem": "26. Find the value of b in the diagram.",
        "options": {"A": "59 degrees", "B": "121 degrees", "C": "35 degrees", "D": "49 degrees"},
        "answer": "A",
        "image": "no 26.png",
        "caption": "Diagram for question 26",
    },
    {
        "stem": "27. Find the value of y.",
        "options": {"A": "78", "B": "102", "C": "90", "D": "12"},
        "answer": "A",
        "image": "27 to 29.png",
        "caption": "Diagram for questions 27 to 29",
        "shared_key": "js2-mth-20260323-q27-29",
    },
    {
        "stem": "28. Find the value of x.",
        "options": {"A": "78", "B": "102", "C": "90", "D": "12"},
        "answer": "B",
        "image": "27 to 29.png",
        "caption": "Diagram for questions 27 to 29",
        "shared_key": "js2-mth-20260323-q27-29",
    },
    {
        "stem": "29. Find the value of z.",
        "options": {"A": "78", "B": "102", "C": "90", "D": "12", "E": "40"},
        "answer": "B",
        "image": "27 to 29.png",
        "caption": "Diagram for questions 27 to 29",
        "shared_key": "js2-mth-20260323-q27-29",
    },
    {
        "stem": "30. Find the value of y.",
        "options": {"A": "92", "B": "48", "C": "56", "D": "70"},
        "answer": "A",
        "image": "no 30.png",
        "caption": "Diagram for question 30",
    },
    {
        "stem": "31. Find the value of x.",
        "options": {"A": "20", "B": "30", "C": "140", "D": "70", "E": "150"},
        "answer": "C",
        "image": "no 31.png",
        "caption": "Diagram for question 31",
    },
    {
        "stem": "32. Find the value of q.",
        "options": {"A": "140", "B": "50", "C": "60", "D": "30"},
        "answer": "B",
        "image": "32 and 33.png",
        "caption": "Diagram for questions 32 and 33",
        "shared_key": "js2-mth-20260323-q32-33",
    },
    {
        "stem": "33. Find the value of p.",
        "options": {"A": "140", "B": "50", "C": "30", "D": "20"},
        "answer": "A",
        "image": "32 and 33.png",
        "caption": "Diagram for questions 32 and 33",
        "shared_key": "js2-mth-20260323-q32-33",
    },
    {
        "stem": "34. The angles of a quadrilateral are 2x, 3x, 7x and 8x. Find x.",
        "options": {"A": "10", "B": "12", "C": "13", "D": "18"},
        "answer": "D",
    },
    {
        "stem": "35. The angles of a quadrilateral are 2x, 5x, 4x and 4x. Find x.",
        "options": {"A": "20", "B": "24", "C": "46", "D": "36"},
        "answer": "A",
    },
    {
        "stem": "36. The following has four sides except",
        "options": {"A": "Rectangle", "B": "Square", "C": "Circle", "D": "Kite"},
        "answer": "C",
    },
    {
        "stem": "37. A polygon with eight sides is called",
        "options": {"A": "Triangle", "B": "Hexagon", "C": "Pentagon", "D": "Octagon"},
        "answer": "D",
    },
    {
        "stem": "38. A polygon with six sides is called",
        "options": {"A": "Square", "B": "Circle", "C": "Hexagon", "D": "Decagon"},
        "answer": "C",
    },
    {
        "stem": "39. Solve 100 = x + 27",
        "options": {"A": "50", "B": "53", "C": "60", "D": "73"},
        "answer": "D",
    },
    {
        "stem": "40. Expand (4a + 3)(a - 1)",
        "options": {"A": "4a^2 + a + 3", "B": "4a^2 + 7a - 3", "C": "4a^2 - a - 3", "D": "4a^2 + 2a - 3"},
        "answer": "D",
    },
]

THEORY = [
    {
        "stem": (
            "1. 1 litre of fuel costs N97.\n"
            "(a) Make a table of values showing the cost of fuel from 0 litre to 10 litres.\n"
            "(b) Using scale of 1cm to 1 litre on the horizontal axis and 1cm to N100 on the vertical axis, plot a graph to show this information.\n"
            "(c) From the graph, find the estimated cost of 8.3 litres.\n"
            "(d) From the graph, find the estimated litres of fuel that cost N800."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2.\n"
            "(a) A trader bought 12 electronic stores at the cost of N3600 each. If each store is sold for N4150, find the total profit.\n"
            "(b) Solve 5x - 2(8 - x)."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3.\n"
            "(a) Expand 3(x + 2y) + 4(2x - y).\n"
            "(b) Find common factors and HCF of 10pqr and 15pq^2."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4.\n"
            "(a) Use balance method to solve 3x + 7 = 2x + 8.\n"
            "(b) Factorise 21x^2 + 15xy."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5.\n"
            "(i) Find x if perimeter of triangle is 28cm.\n"
            "(ii) Find interior angle of a regular 15-sided polygon."
        ),
        "marks": Decimal("10.00"),
        "image": "no 5 theory.png",
        "caption": "Diagram for theory question 5",
    },
    {
        "stem": (
            "6. Interior angles of pentagon: (y + 13) degrees, (y + 15) degrees, (y + 23) degrees, "
            "(y + 29) degrees, (y + 40) degrees.\n"
            "(i) Find y.\n"
            "(ii) Find the value of each interior angle."
        ),
        "marks": Decimal("10.00"),
    },
]


def _exam_assets_root():
    return Path.cwd() / "EXAM"


def _use_uploaded_stimulus():
    return str(getattr(settings, "MEDIA_STORAGE_BACKEND", "")).strip().lower() == "filesystem"


def _build_rich_stem(stem, *, image_name=None, caption=""):
    if not image_name:
        return ""
    image_url = f"/static/exam/{quote(image_name)}"
    caption_html = f"<figcaption>{caption}</figcaption>" if caption else ""
    return (
        f"<p>{stem}</p>"
        f"<figure class=\"cbt-inline-figure\">"
        f"<img src=\"{image_url}\" alt=\"Question diagram\" "
        f"style=\"max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:12px;padding:8px;background:#fff;\">"
        f"{caption_html}"
        f"</figure>"
    )


def _attach_image(question, image_name, caption="", shared_key=""):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    with image_path.open("rb") as handle:
        question.stimulus_image.save(image_path.name, File(handle), save=False)
    question.stimulus_caption = caption
    question.shared_stimulus_key = shared_key
    question.save(update_fields=["stimulus_image", "stimulus_caption", "shared_stimulus_key", "updated_at"])


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
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
        defaults={
            "description": DESCRIPTION,
            "assignment": assignment,
            "is_active": True,
        },
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
            "dean_review_comment": "Approved for resumed second term examination.",
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
    exam.dean_review_comment = "Approved for resumed second term examination."
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
    use_uploaded_stimulus = _use_uploaded_stimulus()

    for index, item in enumerate(OBJECTIVES, start=1):
        rich_stem = ""
        if item.get("image") and not use_uploaded_stimulus:
            rich_stem = _build_rich_stem(
                item["stem"],
                image_name=item.get("image"),
                caption=item.get("caption", ""),
            )
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=Decimal("1.00"),
            source_reference=f"JS2-MTH-20260323-OBJ-{index:02d}",
            is_active=True,
        )
        if "image" in item and use_uploaded_stimulus:
            _attach_image(
                question,
                item["image"],
                caption=item.get("caption", ""),
                shared_key=item.get("shared_key", ""),
            )

        option_labels = list(item["options"].keys())
        option_map = {}
        for option_index, label in enumerate(option_labels, start=1):
            option_map[label] = Option.objects.create(
                question=question,
                label=label,
                option_text=item["options"][label],
                sort_order=option_index,
            )
        answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.add(option_map[item["answer"]])
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=Decimal("1.00"),
        )
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        rich_stem = ""
        if item.get("image") and not use_uploaded_stimulus:
            rich_stem = _build_rich_stem(
                item["stem"],
                image_name=item.get("image"),
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
            source_reference=f"JS2-MTH-20260323-TH-{index:02d}",
            is_active=True,
        )
        if "image" in item and use_uploaded_stimulus:
            _attach_image(question, item["image"], caption=item.get("caption", ""))
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=item["marks"],
        )
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 65
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS2-MTH-EXAM",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
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
            "image_questions": [index for index, item in enumerate(OBJECTIVES, start=1) if "image" in item],
        }
    )


main()
