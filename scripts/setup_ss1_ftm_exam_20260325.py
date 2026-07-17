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


TITLE = "WED 9:15-11:15 SS1 Further Mathematics Second Term Exam"
DESCRIPTION = "SS1 SECOND TERM EXAMINATION FURTHER MATHEMATICS"
BANK_NAME = "SS1 Further Mathematics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all questions. "
    "Timer is 120 minutes. Exam window closes at 11:15 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {
        "stem": "If f: x ↦ x² - 4, where x is a real number, find f⁻¹(5).",
        "options": {"A": "+3", "B": "-5", "C": "-3", "D": "+5"},
        "answer": "A",
    },
    {
        "stem": "Given that p = (5i - 3j) and q = (4i + 7j), find the sum p + q.",
        "options": {"A": "9i + 4j", "B": "5i + 4j", "C": "9i - 4j", "D": "i - 5j"},
        "answer": "A",
    },
    {
        "stem": "If g: x ↦ (2x - 3)⁄4, find g⁻¹(-3).",
        "options": {"A": "-2.5", "B": "-3.5", "C": "-4.5", "D": "-5.5"},
        "answer": "C",
    },
    {
        "stem": "If √7 = 2.646, evaluate 1⁄(√7 - 1) to 3 significant figures.",
        "options": {"A": "6.607", "B": "6.606", "C": "0.6080", "D": "0.6077"},
        "answer": "D",
    },
    {
        "stem": "Simplify (10√2)⁄√5.",
        "options": {"A": "2", "B": "10", "C": "2√10", "D": "3√10"},
        "answer": "C",
    },
    {
        "stem": "Given the function f(x) = 5x - 2, find f(1).",
        "options": {"A": "1⁄5", "B": "5", "C": "1⁄3", "D": "3"},
        "answer": "D",
    },
    {
        "stem": "If f(x) = 10x - 3, find f(2).",
        "options": {"A": "17", "B": "16", "C": "15", "D": "14"},
        "answer": "A",
    },
    {
        "stem": "Given that a = 7i - 3j and b = 5i + 7j, find 3a + b.",
        "options": {"A": "26i - 2j", "B": "21i - 2j", "C": "16i - 2j", "D": "26i + 2j"},
        "answer": "A",
    },
    {
        "stem": "If f(x - 2) = 3x² + 4x + 1, find f(1).",
        "options": {"A": "8", "B": "40", "C": "7", "D": "32"},
        "answer": "B",
    },
    {
        "stem": "If tan β = 5⁄12 where β is an acute angle, evaluate cosβ⁄(sinβ + cosβ).",
        "options": {"A": "17⁄13", "B": "13⁄17", "C": "12⁄17", "D": "17⁄12"},
        "answer": "C",
    },
    {
        "stem": "Given that p(3, 1) + q(2, 4) = (8, 6), where p and q are constants, find p + q.",
        "options": {"A": "3", "B": "4", "C": "5", "D": "6"},
        "answer": "A",
    },
    {
        "stem": "Find the 28th term of the linear sequence 3, 8, 13, 18, 23, ...",
        "options": {"A": "114", "B": "133", "C": "135", "D": "138"},
        "answer": "D",
    },
    {
        "stem": "Use the following information: Given the linear sequence 5, 8, 11, 14, ... find the first term.",
        "options": {"A": "5", "B": "3", "C": "-5", "D": "-3"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: Given the linear sequence 5, 8, 11, 14, ... find the common difference.",
        "options": {"A": "-5", "B": "3", "C": "5", "D": "-3"},
        "answer": "B",
    },
    {
        "stem": "Use the following information: Given the linear sequence 5, 8, 11, 14, ... find the 8th term.",
        "options": {"A": "26", "B": "27", "C": "36", "D": "19"},
        "answer": "A",
    },
    {
        "stem": "The first term of a linear sequence is 3 and the 8th term is 31. Find the common difference.",
        "options": {"A": "1", "B": "2", "C": "3", "D": "4"},
        "answer": "D",
    },
    {
        "stem": "The first term of a linear sequence is 5 and the common difference is 3. Find the 15th term.",
        "options": {"A": "50", "B": "47", "C": "60", "D": "37"},
        "answer": "B",
    },
    {
        "stem": "Use the following information: If 3, 6, 12, 24, ... are in geometric progression, find the first term.",
        "options": {"A": "3", "B": "6", "C": "12", "D": "2"},
        "answer": "A",
    },
    {
        "stem": "Use the following information: If 3, 6, 12, 24, ... are in geometric progression, find the common ratio.",
        "options": {"A": "3", "B": "2", "C": "1", "D": "4"},
        "answer": "B",
    },
    {
        "stem": "Use the following information: If 3, 6, 12, 24, ... are in geometric progression, find the 7th term.",
        "options": {"A": "64", "B": "192", "C": "36", "D": "100"},
        "answer": "B",
    },
    {
        "stem": "The following are examples of mapping except ______.",
        "options": {"A": "Onto mapping", "B": "One-to-one mapping", "C": "Inverse mapping", "D": "Projective mapping"},
        "answer": "D",
    },
    {
        "stem": "Find the 9th term of the arithmetic progression 18, 12, 6, 0, ...",
        "options": {"A": "-30", "B": "30", "C": "66", "D": "-66"},
        "answer": "A",
    },
    {
        "stem": "A mapping that is both injective and surjective is ______.",
        "options": {"A": "Inverse", "B": "Bijective", "C": "Trijective", "D": "Conjective"},
        "answer": "B",
    },
    {
        "stem": "Evaluate (27⁄8)^(-2⁄3).",
        "options": {"A": "1⁄9", "B": "2⁄7", "C": "3⁄7", "D": "4⁄9"},
        "answer": "D",
    },
    {
        "stem": "Rationalize 1⁄√3.",
        "options": {"A": "√3⁄2", "B": "√3⁄3", "C": "√3⁄4", "D": "√3⁄5"},
        "answer": "B",
    },
    {
        "stem": "Find the conjugate of 2 - √3.",
        "options": {"A": "2 + √3", "B": "3 - √2", "C": "3 + √3", "D": "3 - √3"},
        "answer": "A",
    },
    {
        "stem": "Find the value of (16)^(3⁄2).",
        "options": {"A": "32", "B": "64", "C": "16", "D": "8"},
        "answer": "B",
    },
    {
        "stem": "If 64^x = 16^(x - 1), find the value of x.",
        "options": {"A": "-2", "B": "-1⁄2", "C": "-3⁄2", "D": "-2⁄3"},
        "answer": "A",
    },
    {
        "stem": "Find, without using tables, the value of log₂(4^(x + 1)) = 4.",
        "options": {"A": "1", "B": "-1", "C": "-2", "D": "2"},
        "answer": "A",
    },
    {
        "stem": "Find the common ratio in the exponential sequence 4, -8, 16, -32, ...",
        "options": {"A": "2", "B": "-2", "C": "-4", "D": "4"},
        "answer": "B",
    },
    {
        "stem": "Find x if log₉x = 1.5.",
        "options": {"A": "72.0", "B": "27.0", "C": "36.0", "D": "3.5"},
        "answer": "B",
    },
    {
        "stem": "Given that sin θ = 5⁄13 and θ is an acute angle, find sec θ.",
        "options": {"A": "12⁄13", "B": "5⁄12", "C": "13⁄12", "D": "13⁄5"},
        "answer": "C",
    },
    {
        "stem": "If θ is an acute angle and cos θ = 1⁄2, find the value of cot²θ.",
        "options": {"A": "1⁄3", "B": "3", "C": "1⁄2", "D": "2"},
        "answer": "A",
    },
    {
        "stem": (
            "The first and the last term of a linear sequence (AP) are -12 and 40 respectively. "
            "If the sum of the sequence is 196, find the number of terms."
        ),
        "options": {"A": "14", "B": "13", "C": "12", "D": "11"},
        "answer": "A",
    },
    {
        "stem": "If the mean of 4, 6, 9, y, 16 and 19 is 13, what is the value of y?",
        "options": {"A": "12", "B": "24", "C": "25", "D": "30"},
        "answer": "B",
    },
    {
        "stem": "The average of x, 3, (x - 1), and (2x - 2) is 5. Find the value of x.",
        "options": {"A": "6", "B": "5", "C": "7", "D": "0"},
        "answer": "B",
    },
    {
        "stem": (
            "If the mean of -1, 0, 9, 3, k, 5 is 2, where k is a constant, "
            "find the median of the set of numbers."
        ),
        "options": {"A": "0", "B": "3⁄2", "C": "7⁄2", "D": "6"},
        "answer": "B",
    },
    {
        "stem": "Find the angle between i + 5j and 5i - j.",
        "options": {"A": "30°", "B": "45°", "C": "60°", "D": "90°"},
        "answer": "D",
    },
    {
        "stem": "The magnitude of a null vector is ______.",
        "options": {"A": "Constant", "B": "Zero", "C": "Negative", "D": "AB⃗"},
        "answer": "B",
    },
    {
        "stem": "If a = 3i + 4j, find |a|.",
        "options": {"A": "24", "B": "25", "C": "5", "D": "9"},
        "answer": "C",
    },
]

THEORY = [
    {
        "stem": (
            "1. Given the mapping f: x ↦ 7x - 2, determine:\n"
            "(a) f⁻¹(4)\n"
            "(b) f⁻¹(6)\n"
            "(c) f⁻¹(3)"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. Given that f(x) = x⁵ + 4x⁴ - 6x² + 2x + 2, find f(-1).\n"
            "(a) Find the value of m + n."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. Given that sin θ = 5⁄13 and θ is an acute angle, find the value of:\n"
            "(i) cosec²θ\n"
            "(ii) cot θ\n"
            "(iii) cot²θ"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4. If 16⁄9, x, 1, y are in geometric progression, find the product of x and y.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "5. If 8, x, y, z and 20 are in arithmetic progression, find x, y and z.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. Given that U = i - j, V = 2i + 3j and 3U + V - q = 0,\n"
            "(a) find |q|\n"
            "(b) find the angle between U and V"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": "7. Given that M = 3i - 2j, N = 2i + 3j and p = -i - 6j, find |3M + 2N|.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "8. The first, third and seventh terms of an AP form three consecutive terms of a GP. "
            "If the sum of the first two terms of the AP is 6, find its:\n"
            "(a) first term\n"
            "(b) common difference"
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="FTM")
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
    schedule_start = datetime(2026, 3, 25, 9, 15, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 11, 15, tzinfo=lagos)

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
            source_reference=f"SS1-FTM-20260325-OBJ-{index:02d}",
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
            rich_stem=item["stem"].replace("\n", "<br>"),
            marks=item["marks"],
            source_reference=f"SS1-FTM-20260325-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 120
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS1-FTM-EXAM",
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
