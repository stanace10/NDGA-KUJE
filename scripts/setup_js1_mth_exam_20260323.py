from decimal import Decimal
from zoneinfo import ZoneInfo
from datetime import datetime

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


TITLE = "MON 8:00-9:20 JS1 Mathematics Second Term Exam"
DESCRIPTION = "JS1 2ND TERM EXAM ON MATH M 26"
BANK_NAME = "JS1 Mathematics Second Term Exam M26"
INSTRUCTIONS = (
    "Answer all objective questions in Section A and all theory questions in Section B. "
    "Objective section carries 20 marks after normalization. Theory section carries 40 marks after marking. "
    "Timer is 65 minutes. Exam window closes at 9:20 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {
        "stem": "1. Simplify 7/10 - 4/15",
        "options": {"A": "5/24", "B": "8/24", "C": "13/30", "D": "3/30"},
        "answer": "C",
    },
    {
        "stem": "2. Simplify 3/4 - 2/3",
        "options": {"A": "3/12", "B": "1/12", "C": "1/4", "D": "5/7"},
        "answer": "B",
    },
    {
        "stem": "3. A girl spends 1/4 of her pocket money on Monday and 3/8 on Wednesday. What fraction of her money is left?",
        "options": {"A": "3/8", "B": "4/8", "C": "1/4", "D": "3/5"},
        "answer": "A",
    },
    {
        "stem": "4. Convert 0.05 to a fraction in the lowest terms",
        "options": {"A": "5/10", "B": "2/10", "C": "1/10", "D": "1/20"},
        "answer": "D",
    },
    {
        "stem": "5. Round 678 to the nearest hundred.",
        "options": {"A": "600", "B": "700", "C": "680", "D": "650"},
        "answer": "B",
    },
    {
        "stem": "6. Round 4,482 to the nearest thousand.",
        "options": {"A": "4,000", "B": "5,000", "C": "4,500", "D": "4,800"},
        "answer": "A",
    },
    {
        "stem": "7. Find x: If x - 9 = 14",
        "options": {"A": "24", "B": "44", "C": "23", "D": "54"},
        "answer": "C",
    },
    {
        "stem": "8. Round 2,349 to the nearest hundred.",
        "options": {"A": "2,300", "B": "2,400", "C": "2,350", "D": "2,000"},
        "answer": "A",
    },
    {
        "stem": "9. 5,501 rounded to the nearest thousand is",
        "options": {"A": "5,000", "B": "5,500", "C": "6,000", "D": "5,100"},
        "answer": "C",
    },
    {
        "stem": "10. Round 946 to the nearest ten.",
        "options": {"A": "940", "B": "950", "C": "945", "D": "900"},
        "answer": "B",
    },
    {
        "stem": "11. Approximate 3,249 to the nearest thousand.",
        "options": {"A": "3,000", "B": "3,200", "C": "4,000", "D": "3,500"},
        "answer": "A",
    },
    {
        "stem": "12. Round 121 to the nearest ten.",
        "options": {"A": "120", "B": "130", "C": "125", "D": "100"},
        "answer": "A",
    },
    {
        "stem": "13. 7,449 rounded to the nearest thousand is",
        "options": {"A": "7,000", "B": "7,400", "C": "7,500", "D": "8,000"},
        "answer": "A",
    },
    {
        "stem": "14. Round 86 to the nearest ten.",
        "options": {"A": "80", "B": "90", "C": "85", "D": "86"},
        "answer": "B",
    },
    {
        "stem": "15. Approximate 999 to the nearest hundred.",
        "options": {"A": "900", "B": "1,000", "C": "990", "D": "950"},
        "answer": "B",
    },
    {
        "stem": "16. Simplify: 3x + 5x + x + x",
        "options": {"A": "8", "B": "15x", "C": "8x", "D": "10x"},
        "answer": "C",
    },
    {
        "stem": "17. Simplify: 7a - 2a",
        "options": {"A": "5a", "B": "9a", "C": "-2a", "D": "-5a"},
        "answer": "A",
    },
    {
        "stem": "18. Simplify: 4y + y - 2y",
        "options": {"A": "3y", "B": "y", "C": "7y", "D": "2y"},
        "answer": "A",
    },
    {
        "stem": "19. Expand: 2(x + 3)",
        "options": {"A": "2x + 3", "B": "x + 6", "C": "2x + 6", "D": "6x"},
        "answer": "C",
    },
    {
        "stem": "20. Expand: 3(a - 4)",
        "options": {"A": "3a - 4", "B": "3a - 12", "C": "a - 12", "D": "12a"},
        "answer": "B",
    },
    {
        "stem": "21. Simplify: 5m + 2n - 3m",
        "options": {"A": "7mn", "B": "2m + 2n", "C": "8mn", "D": "m + n"},
        "answer": "B",
    },
    {
        "stem": "22. Solve: x + 6 = 10",
        "options": {"A": "4", "B": "6", "C": "10", "D": "16"},
        "answer": "A",
    },
    {
        "stem": "23. Solve: y - 5 = 3",
        "options": {"A": "2", "B": "8", "C": "-2", "D": "15"},
        "answer": "B",
    },
    {
        "stem": "24. Solve: 4x = 20",
        "options": {"A": "4", "B": "5", "C": "20", "D": "80"},
        "answer": "B",
    },
    {
        "stem": "25. Solve: x / 3 = 6",
        "options": {"A": "2", "B": "9", "C": "18", "D": "3"},
        "answer": "C",
    },
    {
        "stem": "26. Simplify: 6p - p + 2p",
        "options": {"A": "7p", "B": "6p", "C": "5p", "D": "9p"},
        "answer": "A",
    },
    {
        "stem": "27. Expand: 4(y + 2)",
        "options": {"A": "4y + 2", "B": "y + 8", "C": "4y + 8", "D": "8y"},
        "answer": "C",
    },
    {
        "stem": "28. Base 2 is also known as",
        "options": {"A": "Decimal system", "B": "Binary system", "C": "Octal system", "D": "Denary system"},
        "answer": "B",
    },
    {
        "stem": "29. Multiply 141 by 17",
        "options": {"A": "3397", "B": "2397", "C": "4397", "D": "5397"},
        "answer": "B",
    },
    {
        "stem": "30. Express 11 4/5 as improper fraction",
        "options": {"A": "69/5", "B": "59/5", "C": "49/5", "D": "39/5"},
        "answer": "B",
    },
    {
        "stem": "31. Add: 1111_2 + 101_2",
        "options": {"A": "11111_2", "B": "10100_2", "C": "0111_2", "D": "1100_2"},
        "answer": "B",
    },
    {
        "stem": "32. Express 4/5 as percentage",
        "options": {"A": "60%", "B": "70%", "C": "80%", "D": "90%"},
        "answer": "C",
    },
    {
        "stem": "33. Find the L C M of 6, 8 and 10",
        "options": {"A": "100", "B": "110", "C": "120", "D": "130"},
        "answer": "C",
    },
    {
        "stem": "34. Subtract: 100_2 - 11_2",
        "options": {"A": "0_2", "B": "1_2", "C": "10_2", "D": "11_2"},
        "answer": "B",
    },
    {
        "stem": "35. Find the H C F of 44, 66 and 88",
        "options": {"A": "2", "B": "22", "C": "4", "D": "44"},
        "answer": "B",
    },
    {
        "stem": "36. Convert 18/7 to mixed numbers",
        "options": {"A": "2 4/7", "B": "3 4/7", "C": "4 4/7", "D": "5 4/7"},
        "answer": "A",
    },
    {
        "stem": "37. Reduce 450/630 to the lowest terms",
        "options": {"A": "45/63", "B": "5/7", "C": "5/11", "D": "7/11"},
        "answer": "B",
    },
    {
        "stem": "38. Solve the equation 11x + 4 = 70",
        "options": {"A": "5", "B": "6", "C": "8", "D": "11"},
        "answer": "B",
    },
    {
        "stem": "39. Simplify 120 x 3/10",
        "options": {"A": "560", "B": "460", "C": "36", "D": "60"},
        "answer": "C",
    },
    {
        "stem": "40. Round off to the nearest hundred and simplify 125 x 105 kg",
        "options": {"A": "10,000 kg", "B": "100,000 kg", "C": "1,000 kg", "D": "100 kg"},
        "answer": "A",
    },
]

THEORY = [
    {"stem": "1. What is the sum of 1 7/12 and 3 5/8?", "marks": Decimal("5.00")},
    {"stem": "2. Find the product of 3 1/4 and 2 2/5.", "marks": Decimal("5.00")},
    {"stem": "3. Simplify 1 4/5 / 6 3/10.", "marks": Decimal("5.00")},
    {
        "stem": "4. Evaluate the following in base two (2):\n(a) 11100 + 10111\n(b) 1111 - 1101",
        "marks": Decimal("5.00"),
    },
    {
        "stem": "5. Find the product in base 2:\n(a) 1011 x 11\n(b) 11111 x 110",
        "marks": Decimal("5.00"),
    },
    {
        "stem": "6. A fruit grower uses 1/2 of his land for bananas, 3/8 for pineapple, 1/6 for mangoes and the remainder for oranges. What fraction of his land does he use for oranges?",
        "marks": Decimal("5.00"),
    },
    {
        "stem": "7. Round up the following: (i) 4,768 (ii) 3,999 to:\n(a) the nearest thousand\n(b) the nearest hundred",
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
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

    for index, item in enumerate(OBJECTIVES, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            marks=Decimal("1.00"),
            source_reference=f"JS1-MTH-M26-OBJ-{index:02d}",
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
            marks=item["marks"],
            source_reference=f"JS1-MTH-M26-TH-{index:02d}",
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
    blueprint.duration_minutes = 65
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "M26",
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
        }
    )


main()
