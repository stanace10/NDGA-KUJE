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


TITLE = "WED 9:15-11:15 SS3 Further Mathematics Mock Examination"
DESCRIPTION = "SUBJECT: FURTHER MATHEMATICS CLASS: SS3 MOCK EXAMINATION"
BANK_NAME = "SS3 Further Mathematics Mock Examination 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In the theory section, answer all questions. "
    "Timer is 120 minutes. Exam window closes at 11:15 AM WAT on Wednesday, March 25, 2026."
)


# Question 9 from the scanned source is omitted because the matrix statement is visibly incomplete
# in the PDF and cannot be recovered into a fair, solvable question.
OBJECTIVES = [
    {
        "stem": "Solve 8^(x - 2) = 4^(3x).",
        "options": {"A": "-2", "B": "-1", "C": "1", "D": "2"},
        "answer": "A",
    },
    {
        "stem": "Evaluate tan 75°, leaving the answer in surd form.",
        "options": {"A": "√3 + 2", "B": "√3 + 1", "C": "√3 - 1", "D": "√3 - 2"},
        "answer": "A",
    },
    {
        "stem": "Given that f(x) = (x + 1)⁄2, find f⁻¹(2).",
        "options": {"A": "-5", "B": "-3", "C": "3", "D": "5"},
        "answer": "C",
    },
    {
        "stem": "Find the coefficient of x⁴ in the expansion of (1 - 2x)⁶.",
        "options": {"A": "-320", "B": "-240", "C": "240", "D": "320"},
        "answer": "C",
    },
    {
        "stem": "How many ways can six students be seated around a circular table?",
        "options": {"A": "36", "B": "48", "C": "72", "D": "120"},
        "answer": "D",
    },
    {
        "stem": "If nC₂ = 15, find the value of n.",
        "options": {"A": "8", "B": "7", "C": "6", "D": "5"},
        "answer": "C",
    },
    {
        "stem": "Given that α and β are roots of 2x² - 3x + 4 = 0, find α + β.",
        "options": {"A": "-2", "B": "-3⁄2", "C": "3⁄2", "D": "2"},
        "answer": "C",
    },
    {
        "stem": "Find the sum of the first 20 terms of the sequence -7, -3, 1, ...",
        "options": {"A": "620", "B": "660", "C": "690", "D": "1240"},
        "answer": "A",
    },
    {
        "stem": (
            "Use the following information: A particle starts from rest and moves in a straight line "
            "with velocity v = 3t² - 6t m s⁻¹ at time t seconds. Calculate the distance travelled in 4 seconds."
        ),
        "options": {"A": "12 m", "B": "16 m", "C": "64 m", "D": "96 m"},
        "answer": "B",
    },
    {
        "stem": (
            "Use the following information: A particle starts from rest and moves in a straight line "
            "with velocity v = 3t² - 6t m s⁻¹ at time t seconds. Calculate the acceleration at t = 3 seconds."
        ),
        "options": {"A": "0 m s⁻²", "B": "3 m s⁻²", "C": "6 m s⁻²", "D": "9 m s⁻²"},
        "answer": "C",
    },
    {
        "stem": "Find the constant term in the binomial expansion of (2x² + 1⁄x²)⁴.",
        "options": {"A": "10", "B": "12", "C": "24", "D": "42"},
        "answer": "C",
    },
    {
        "stem": "Find the fourth term in the expansion of (3x - y)⁶.",
        "options": {
            "A": "-540x³y³",
            "B": "-540x⁴y²",
            "C": "-27x³y³",
            "D": "540x⁴y⁴",
        },
        "answer": "A",
    },
    {
        "stem": "Simplify nP₅⁄nC₅.",
        "options": {"A": "80", "B": "90", "C": "110", "D": "120"},
        "answer": "D",
    },
    {
        "stem": "Solve the equation 5^x × 5^(x + 1) = 25.",
        "options": {"A": "-2", "B": "-1⁄2", "C": "1⁄2", "D": "2"},
        "answer": "C",
    },
    {
        "stem": "A fair coin is tossed three times. Find the probability of obtaining two heads.",
        "options": {"A": "1⁄8", "B": "3⁄8", "C": "5⁄8", "D": "7⁄8"},
        "answer": "B",
    },
    {
        "stem": "Given that tan x = 5⁄12 and tan y = 3⁄4, find tan(x + y).",
        "options": {"A": "16⁄33", "B": "33⁄56", "C": "33⁄16", "D": "56⁄33"},
        "answer": "D",
    },
    {
        "stem": "Point E(-2, -1) and F(3, 2) are ends of the diameter of a circle. Find the equation of the circle.",
        "options": {
            "A": "x² + y² - 5x + 3 = 0",
            "B": "x² + y² - 2x - 6y - 13 = 0",
            "C": "x² + y² - x + 5y - 6 = 0",
            "D": "x² + y² - x - y - 8 = 0",
        },
        "answer": "D",
    },
    {
        "stem": "Given that r = 3i + 4j and t = -5i + 12j, find the acute angle between them.",
        "options": {"A": "14.3°", "B": "55.9°", "C": "59.5°", "D": "75.6°"},
        "answer": "C",
    },
    {
        "stem": "If log₃ x = log₉ 3, find the value of x.",
        "options": {"A": "3²", "B": "3^(1⁄2)", "C": "3^(1⁄3)", "D": "2^(1⁄3)"},
        "answer": "B",
    },
    {
        "stem": "Solve 4(2^x) = 8x.",
        "options": {"A": "1 and 2", "B": "1 and -2", "C": "-1 and 2", "D": "-1 and -2"},
        "answer": "A",
    },
    {
        "stem": "Find the third term of (x⁄2 - 1)⁸ in descending powers of x.",
        "options": {"A": "x⁷⁄8", "B": "7x⁶⁄16", "C": "7x⁶", "D": "5x⁶"},
        "answer": "B",
    },
    {
        "stem": "Find the minimum value of y = x² + 6x - 12.",
        "options": {"A": "-21", "B": "-12", "C": "-6", "D": "-3"},
        "answer": "A",
    },
    {
        "stem": (
            "In how many ways can a committee of five be selected from eight students "
            "if two particular students are to be included?"
        ),
        "options": {"A": "20", "B": "28", "C": "54", "D": "58"},
        "answer": "A",
    },
    {
        "stem": "If x = i - 3j and y = 6i + j, calculate the angle between x and y.",
        "options": {"A": "60°", "B": "75°", "C": "81°", "D": "85°"},
        "answer": "C",
    },
    {
        "stem": (
            "Use the following information: A particle starts from rest and moves in a straight line such that its "
            "acceleration after t seconds is a = (3t - 2) m s⁻². Find the other time when the velocity is zero."
        ),
        "options": {"A": "1⁄3", "B": "3⁄4", "C": "4⁄3", "D": "2"},
        "answer": "C",
    },
    {
        "stem": (
            "Use the following information: A particle starts from rest and moves in a straight line such that its "
            "acceleration after t seconds is a = (3t - 2) m s⁻². Find the displacement after 3 seconds."
        ),
        "options": {"A": "10 m", "B": "9 m", "C": "4.5 m", "D": "2 m"},
        "answer": "C",
    },
    {
        "stem": (
            "A group of 5 boys and 4 girls is to be chosen from a class of 8 boys "
            "and 6 girls. In how many ways can this be done?"
        ),
        "options": {"A": "840", "B": "480", "C": "408", "D": "380"},
        "answer": "A",
    },
    {
        "stem": "Four fair coins are tossed once. Calculate the probability of obtaining equal numbers of heads and tails.",
        "options": {"A": "1⁄4", "B": "3⁄8", "C": "1⁄2", "D": "15⁄16"},
        "answer": "B",
    },
    {
        "stem": "If |4  x; 4  3| = 32, find the value of x.",
        "options": {"A": "-5", "B": "11", "C": "12", "D": "-24"},
        "answer": "A",
    },
    {
        "stem": "Find the median of the numbers 9, 7, 5, 2, 12, 9, 9, 2, 10, 10 and 8.",
        "options": {"A": "7", "B": "9", "C": "10", "D": "11"},
        "answer": "B",
    },
    {
        "stem": "In how many ways can the letters of the word MEMBER be arranged?",
        "options": {"A": "720", "B": "360", "C": "180", "D": "90"},
        "answer": "C",
    },
    {
        "stem": "Solve 3^(2x) - 3^(x + 2) = 3^(x + 1) - 27.",
        "options": {"A": "1 or 0", "B": "1 or 2", "C": "1 or -2", "D": "-1 or 2"},
        "answer": "B",
    },
    {
        "stem": "Evaluate ∫₁² x³ dx.",
        "options": {"A": "-1 1⁄2", "B": "-15⁄4", "C": "15⁄4", "D": "1 1⁄2"},
        "answer": "C",
    },
    {
        "stem": "If |3  x; 2  x - 2| = -2, find the value of x.",
        "options": {"A": "-8", "B": "-4", "C": "4", "D": "8"},
        "answer": "C",
    },
    {
        "stem": (
            "A stone is dropped from the top of a building 40 m high. "
            "Find, correct to one decimal place, the time it takes the stone to reach the ground. "
            "(Take g = 9.8 m s⁻².)"
        ),
        "options": {"A": "2.9 s", "B": "2.8 s", "C": "2.6 s", "D": "1.4 s"},
        "answer": "A",
    },
    {
        "stem": "Given that the binomial expansion of (1 + 3x)⁶ is used to evaluate (0.97)⁶, find the value of x.",
        "options": {"A": "0.03", "B": "0.01", "C": "-0.01", "D": "-0.03"},
        "answer": "C",
    },
    {
        "stem": "If the sum of the roots of 2x² + 5mx + n = 0 is 5, find the value of m.",
        "options": {"A": "-2.5", "B": "-2.0", "C": "2.0", "D": "2.5"},
        "answer": "B",
    },
    {
        "stem": "Find the angle between i + 5j and 5i - j.",
        "options": {"A": "0°", "B": "45°", "C": "60°", "D": "90°"},
        "answer": "D",
    },
]

THEORY = [
    {
        "stem": (
            "1. A binary operation * is defined on the set of real numbers, R, by\n"
            "p * q = p + q - pq⁄2, where p, q ∈ R.\n"
            "(a) Find the inverse of -1 under * given that the identity element is zero.\n"
            "(b) Find the truth set of m * 7 = m * 5."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. (a) Two functions p and q are defined on the set of real numbers, R, by\n"
            "p(y) = 2y + 3 and q(y) = 3y² - 2. Find q∘p.\n"
            "(b) Solve the simultaneous equations:\n"
            "log₂x - log₂y = 2,\n"
            "log₂(x - 2y) = 3."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. If (3x² + 3x - 2)⁄(x² - 1) = P + Q⁄(x - 1) + R⁄(x + 1), "
            "find the values of Q and R."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4. The sum of the first twelve terms of an arithmetic progression is 168. "
            "If the third term is 7, find the common difference and the first term."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. Two panels of judges X and Y rank 8 brands of cooking oil as follows:\n"
            "Type: A  B  C  D  E  F  G  H\n"
            "X:    8  5  1  7  2  6  3  4\n"
            "Y:    5  3  4  8  5  7  1  2"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. (a) The probability that Kunle solves a particular question is 1⁄3 while that of Tayo is 1⁄5. "
            "If both of them attempt the question, find the probability that only one of them solves it.\n"
            "(b) A committee of 8 is to be chosen from 10 persons. In how many ways can this be done if there is no restriction?"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "7. Given that m = 3i - 2j, n = 2i + 3j and p = -i + 6j, find |4m + 2n - 3p|."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "8. A body of mass 20 kg moving with velocity 80 m s⁻¹ collides with another body of mass 30 kg "
            "moving with velocity 50 m s⁻¹. If the two bodies move together after collision, find their common velocity if they moved in the:\n"
            "(a) same direction before collision\n"
            "(b) opposite direction before collision"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "9. A circle is drawn through the points (3, 2), (-1, -2) and (5, -4). Find the:\n"
            "(a) coordinates of the centre\n"
            "(b) radius of the circle\n"
            "(c) equation of the circle"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "10. (a)(i) Write down the expansion of (2 - 1⁄2x)⁵ in ascending powers of x.\n"
            "(ii) Using the expansion in 10(a)(i), find correct to two decimal places the value of (1.99)⁵."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "11. The polynomial x³ + qx² + rx + 9, where q and r are constants, has (x + 1) as a factor "
            "and has a remainder of -17 when divided by (x + 2). Find the values of q and r."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "12. The table shows the distribution of marks scored by some candidates in an examination.\n"
            "Marks: 11-20, 21-30, 31-40, 41-50, 51-60, 61-70, 71-80, 81-90, 91-100\n"
            "Number of candidates: 5, 39, 14, 40, 57, 25, 11, 8, 1\n"
            "(a) Construct a cumulative frequency table for the distribution.\n"
            "(b) Draw a cumulative frequency curve for the distribution.\n"
            "(c) Use the curve to estimate:\n"
            "(i) the number of candidates who scored between 24 and 58\n"
            "(ii) the lowest mark for distinction if 12% of the candidates passed with distinction"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "13. (a) A bag contains 16 identical balls of which 4 are green. A boy picks a ball at random and replaces it. "
            "If this is repeated 5 times, what is the probability that he:\n"
            "(i) did not pick a green ball\n"
            "(ii) picked a green ball at least three times?\n"
            "(b) The deviations from the mean of a set of data are -2, (m - 1), (m² + 1), -1, 2, (2m - 1) and -2. "
            "Find the possible values of m."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "14. A particle of mass 2 kg moves under the action of a constant force F N, "
            "with initial velocity (3i + 2j) m s⁻¹ and velocity (15i - 4j) m s⁻¹ after 4 seconds. Find:\n"
            "(a) the acceleration of the particle\n"
            "(b) the magnitude of the force F\n"
            "(c) the magnitude of the velocity of the particle after 8 seconds, correct to three decimal places"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "15. A load of mass 120 kg is placed on a lift. Calculate the reaction between the floor of the lift and the load when the lift moves upwards:\n"
            "(i) at a constant velocity\n"
            "(ii) with an acceleration of 3 m s⁻²\n"
            "(Take g = 10 m s⁻².)"
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="FTM")
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
            "dean_review_comment": "Approved for Wednesday morning mock paper.",
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
    exam.dean_review_comment = "Approved for Wednesday morning mock paper."
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
            source_reference=f"SS3-FTM-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS3-FTM-20260325-TH-{index:02d}",
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
    blueprint.duration_minutes = 120
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-FTM-MOCK",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "40.00",
        "theory_target_max": "60.00",
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
