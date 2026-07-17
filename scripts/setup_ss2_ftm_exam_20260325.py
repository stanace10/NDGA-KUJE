from datetime import datetime
from decimal import Decimal
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


TITLE = "WED 9:15-10:30 SS2 Further Mathematics Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION SUBJECT: FURTHER MATHEMATICS CLASS: SS2"
BANK_NAME = "SS2 Further Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 10:30 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {
        "stem": "Form a quadratic equation whose roots are 2 and -3.",
        "options": {
            "A": "x² + x - 6 = 0",
            "B": "x² - x - 6 = 0",
            "C": "x² + x + 6 = 0",
            "D": "x² - x + 6 = 0",
        },
        "answer": "A",
    },
    {
        "stem": "A quadratic equation has equal roots if its discriminant is:",
        "options": {
            "A": "Less than zero",
            "B": "Greater than zero",
            "C": "Equal to zero",
            "D": "Equal to one",
        },
        "answer": "C",
    },
    {
        "stem": "For which value of k will the equation x² + 4x + k = 0 have real and equal roots?",
        "options": {"A": "4", "B": "2", "C": "8", "D": "1"},
        "answer": "A",
    },
    {
        "stem": "The roots of 2x² - 3x + 5 = 0 are:",
        "options": {
            "A": "Real and distinct",
            "B": "Real and equal",
            "C": "Complex",
            "D": "Irrational",
        },
        "answer": "C",
    },
    {
        "stem": "Which of these is a polynomial?",
        "options": {
            "A": "1⁄x",
            "B": "x³ + 2x + 1",
            "C": "√x",
            "D": "1⁄(x + 2)",
        },
        "answer": "B",
    },
    {
        "stem": "If f(x) = x² + 3x - 4, find f(2).",
        "options": {"A": "6", "B": "10", "C": "4", "D": "2"},
        "answer": "A",
    },
    {
        "stem": "Divide x³ - x² - x + 1 by x - 1.",
        "options": {
            "A": "x² - 1",
            "B": "x² + x + 1",
            "C": "x² - x - 1",
            "D": "x² - x + 1",
        },
        "answer": "A",
    },
    {
        "stem": "If f(x) = x³ - 6x² + 11x - 6, find the sum of its roots.",
        "options": {"A": "-6", "B": "-11", "C": "6", "D": "7"},
        "answer": "C",
    },
    {
        "stem": "In the cubic polynomial x³ - 6x² + 11x - 6, the product of the roots is:",
        "options": {"A": "6", "B": "-6", "C": "-11", "D": "1"},
        "answer": "A",
    },
    {
        "stem": "Factor completely: x³ - x² - x + 1.",
        "options": {
            "A": "(x - 1)(x² - 1)",
            "B": "(x - 1)²(x + 1)",
            "C": "(x - 1)(x + 1)²",
            "D": "(x + 1)(x² - x + 1)",
        },
        "answer": "B",
    },
    {
        "stem": "If a polynomial f(x) is divisible by x - 3, then:",
        "options": {
            "A": "f(3) = 0",
            "B": "f(-3) = 0",
            "C": "f(3) = 1",
            "D": "f(-3) = 1",
        },
        "answer": "A",
    },
    {
        "stem": "What is the factor of x³ - 8?",
        "options": {
            "A": "(x - 2)(x² + 2x + 4)",
            "B": "(x + 2)(x² - 2x + 4)",
            "C": "(x - 2)³",
            "D": "x³ + 2³",
        },
        "answer": "A",
    },
    {
        "stem": "Which of these represents the factor theorem?",
        "options": {
            "A": "If x - a is a factor, then f(a) = 0",
            "B": "If f(a) = 0, then x + a is a factor",
            "C": "If x - a divides f(x), then f(a) = 1",
            "D": "None of the above",
        },
        "answer": "A",
    },
    {
        "stem": "Find the derivative of sec x.",
        "options": {
            "A": "cos x sin x",
            "B": "sin x cos x",
            "C": "sec x tan x",
            "D": "tan x cos x",
        },
        "answer": "C",
    },
    {
        "stem": "Find the derivative of cosec x.",
        "options": {
            "A": "cosec x tan x",
            "B": "cosec x cot x",
            "C": "-cosec x tan x",
            "D": "-cosec x cot x",
        },
        "answer": "D",
    },
    {
        "stem": "Find the derivative of cot x.",
        "options": {"A": "cosec² x", "B": "-cosec² x", "C": "-2cosec x", "D": "2cosec x"},
        "answer": "B",
    },
    {
        "stem": "Evaluate lim(x→1) ((x² - 1)⁄(x² + x - 2)).",
        "options": {"A": "3⁄2", "B": "2⁄2", "C": "2⁄3", "D": "0"},
        "answer": "C",
    },
    {
        "stem": "If the roots of x² - 5x + 6 = 0 are α and β, then the sum and product of the roots are:",
        "options": {"A": "6 and 5", "B": "5 and 6", "C": "-5 and 6", "D": "-6 and 5"},
        "answer": "B",
    },
    {
        "stem": "If a line y = mx + c is tangent to the curve y = x², then the equation x² = mx + c has:",
        "options": {
            "A": "No solution",
            "B": "Two equal solutions",
            "C": "One real solution",
            "D": "Two complex solutions",
        },
        "answer": "B",
    },
    {
        "stem": "The condition for a line to intersect a curve is:",
        "options": {
            "A": "Discriminant = 0",
            "B": "Discriminant > 0",
            "C": "Discriminant < 0",
            "D": "Determinant > 0",
        },
        "answer": "B",
    },
    {
        "stem": "Find the nature of the roots of x² + 2x + 3 = 0:",
        "options": {
            "A": "Real and equal",
            "B": "Real and distinct",
            "C": "Imaginary (complex)",
            "D": "Rational",
        },
        "answer": "C",
    },
    {
        "stem": "The remainder when f(x) = x³ + 4x² - 3x + 2 is divided by x + 1 is:",
        "options": {"A": "8", "B": "2", "C": "1", "D": "0"},
        "answer": "A",
    },
    {
        "stem": "Which of the following is NOT a polynomial operation?",
        "options": {"A": "Addition", "B": "Subtraction", "C": "Integration", "D": "Multiplication"},
        "answer": "C",
    },
    {
        "stem": "If x = 2 is a root of f(x) = x³ - 3x² - 4x + 12, what is the value of f(2)?",
        "options": {"A": "0", "B": "1", "C": "2", "D": "-1"},
        "answer": "A",
    },
    {
        "stem": "Find the derivative of tan x.",
        "options": {"A": "sec x", "B": "sec² x", "C": "sec 2x", "D": "2sec x"},
        "answer": "B",
    },
    {
        "stem": "Given that P(x) = 2x³ + 5x² - 9x - 18, find P(-1).",
        "options": {"A": "7", "B": "6", "C": "-7", "D": "-6"},
        "answer": "D",
    },
    {
        "stem": "Find the derivative of sin x.",
        "options": {"A": "cos x", "B": "-cos x", "C": "cos² x", "D": "sin² x"},
        "answer": "A",
    },
    {
        "stem": (
            "Use the following information: P₁(x) = 7x³ - 4x² + 3x + 4 and P₂(x) = 5x² + 6x + 1. "
            "Find P₁(x) + P₂(x)."
        ),
        "options": {
            "A": "7x³ + x² + 9x + 5",
            "B": "7x³ + 2x² + 6x + 7",
            "C": "7x³ + 4x² + 2x + 5",
            "D": "6x³ + 2x² + 2x + 2",
        },
        "answer": "A",
    },
    {
        "stem": (
            "Use the following information: P₁(x) = 7x³ - 4x² + 3x + 4 and P₂(x) = 5x² + 6x + 1. "
            "Find P₁(x) - P₂(x)."
        ),
        "options": {
            "A": "7x³ - 9x² - 3x + 3",
            "B": "7x³ + 9x² + 3x + 3",
            "C": "7x³ + 9x² + 9x + 9",
            "D": "7x³ - 9x² - 9x - 9",
        },
        "answer": "A",
    },
    {
        "stem": "Find the quotient and remainder when x³ + 8 is divided by x² - 2x + 4.",
        "options": {
            "A": "Q = x + 5, R = 0",
            "B": "Q = x + 2, R = 1",
            "C": "Q = x + 2, R = 2",
            "D": "Q = x + 2, R = 0",
        },
        "answer": "D",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α + β.",
        "options": {"A": "7⁄3", "B": "7⁄2", "C": "8⁄3", "D": "5⁄6"},
        "answer": "B",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find αβ.",
        "options": {"A": "3⁄5", "B": "5⁄3", "C": "3⁄2", "D": "-3⁄2"},
        "answer": "D",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find αβ² + α²β.",
        "options": {"A": "21⁄4", "B": "-21⁄4", "C": "-22⁄5", "D": "-5⁄22"},
        "answer": "B",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α² + β².",
        "options": {"A": "61⁄4", "B": "60⁄3", "C": "62⁄5", "D": "62⁄4"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α³ + β³.",
        "options": {"A": "469⁄8", "B": "469⁄10", "C": "-8⁄469", "D": "10⁄469"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find 1⁄α + 1⁄β.",
        "options": {"A": "7⁄4", "B": "7", "C": "-7⁄3", "D": "7⁄3"},
        "answer": "C",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α⁄(β + 1) + β⁄(α + 1).",
        "options": {"A": "20⁄4", "B": "25⁄5", "C": "-25⁄4", "D": "25⁄4"},
        "answer": "D",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α⁄(α + 1) + β⁄(β + 1).",
        "options": {"A": "1⁄6", "B": "-1⁄6", "C": "2⁄7", "D": "1⁄2"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find α⁄β + β⁄α.",
        "options": {"A": "-61⁄6", "B": "57⁄8", "C": "-60⁄5", "D": "61⁄5"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: α and β are the roots of 2x² - 7x - 3 = 0. Find 3⁄β + 3⁄α.",
        "options": {"A": "8", "B": "7", "C": "-7", "D": "6"},
        "answer": "C",
    },
]

THEORY = [
    {
        "stem": (
            "1. (a) Write down the binomial expansion of (1 + ¼x)⁶, simplifying all the terms.\n"
            "(b) Use the expansion in (a) to evaluate (1.0025)⁶ correct to five significant figures."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. (a) Investigate the nature of the stationary values of the function y = x³⁄3 - x² - 3x.\n"
            "(b) Differentiate y = 3x² + 10x + 20 using first principles."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. Given that P₁(x) = 7x³ - 4x² + 3x + 4, P₂(x) = 5x² + 6x + 1, and P₃(x) = 4x³ + 2x - 3, find:\n"
            "(i) P₁(x) + P₂(x)\n"
            "(ii) P₁(x) + P₃(x)\n"
            "(iii) P₁(x) - P₂(x)\n"
            "(iv) P₃(x) - P₂(x)\n"
            "(v) P₁(x) + P₂(x) + P₃(x)"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4. (a) Differentiate y = (x + 2)²⁄(3x² + 2x - 1).\n"
            "(b) Find the derivative of y = (x² + 1)⁴.\n"
            "(c) Find the derivative of y = (2x + 1)(x² + 2)."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. If α and β are the roots of the equation 2x² - 7x - 3 = 0, find the value of:\n"
            "(i) α + β\n"
            "(ii) αβ\n"
            "(iii) αβ² + α²β\n"
            "(iv) α² + β²\n"
            "(v) α³ + β³"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. Two fair dice are tossed. Find the probability that the total score is:\n"
            "(i) 8\n"
            "(ii) less than 6\n"
            "(iii) greater than or equal to 9\n"
            "(iv) a prime number"
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="FTM")
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
    schedule_start = datetime(2026, 3, 25, 9, 15, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 10, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Wednesday morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 9:15 AM WAT.",
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
    exam.dean_review_comment = "Approved for Wednesday morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 9:15 AM WAT."
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
            rich_stem=item["stem"],
            marks=Decimal("1.00"),
            source_reference=f"SS2-FTM-20260325-OBJ-{index:02d}",
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
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=Decimal("1.00"),
        )
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            rich_stem=item["stem"].replace("\n", "<br>"),
            marks=item["marks"],
            source_reference=f"SS2-FTM-20260325-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=item["marks"],
        )
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS2-FTM-EXAM",
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
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
        }
    )


if __name__ == "__main__":
    main()
