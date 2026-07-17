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


TITLE = "WED 7:45-9:45 JS1 Business Studies Second Term Exam"
DESCRIPTION = "BUSINESS STUDIES JSS1 SECOND TERM EXAMINATION"
BANK_NAME = "JS1 Business Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all questions. "
    "Timer is 55 minutes. Exam window closes at 9:45 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Entrepreneurship is best defined as the ability to ______.", "options": {"A": "work for the government", "B": "take business risks to start and manage a business", "C": "save money in the bank", "D": "buy goods in the market"}, "answer": "B"},
    {"stem": "A person who organizes and manages a business enterprise is called a/an ______.", "options": {"A": "employee", "B": "consumer", "C": "entrepreneur", "D": "customer"}, "answer": "C"},
    {"stem": "An enterprise can be described as ______.", "options": {"A": "a government office", "B": "a business or economic activity", "C": "a market place", "D": "a family house"}, "answer": "B"},
    {"stem": "Self-employment means ______.", "options": {"A": "working for salary earners", "B": "depending on parents", "C": "owning and running one's own business", "D": "working in an office"}, "answer": "C"},
    {"stem": "Which of the following is a facility for self-employment?", "options": {"A": "Television", "B": "Loan or credit facility", "C": "School uniform", "D": "Chalkboard"}, "answer": "B"},
    {"stem": "Which of the following is NOT a facility for self-employment?", "options": {"A": "Capital", "B": "Skills training", "C": "Tools and equipment", "D": "Examination hall"}, "answer": "D"},
    {"stem": "A successful entrepreneur in Nigeria is ______.", "options": {"A": "Dangote", "B": "Nelson Mandela", "C": "Abraham Lincoln", "D": "William Shakespeare"}, "answer": "A"},
    {"stem": "Which of the following can be a successful entrepreneur in your locality?", "options": {"A": "A local tailor", "B": "A student", "C": "A house help", "D": "A passenger"}, "answer": "A"},
    {"stem": "One importance of entrepreneurship to individuals is that it ______.", "options": {"A": "causes unemployment", "B": "reduces skills", "C": "provides self-reliance", "D": "increases laziness"}, "answer": "C"},
    {"stem": "One importance of entrepreneurship to society is that it ______.", "options": {"A": "increases crime", "B": "creates employment opportunities", "C": "encourages dependency", "D": "reduces production"}, "answer": "B"},
    {"stem": "A business organisation can be defined as ______.", "options": {"A": "a social gathering", "B": "a system of arranging business activities to achieve set goals", "C": "a school club", "D": "a market union"}, "answer": "B"},
    {"stem": "Which of the following is NOT a form of business organisation?", "options": {"A": "Sole proprietorship", "B": "Partnership", "C": "Limited liability company", "D": "Scholarship"}, "answer": "D"},
    {"stem": "A business owned and controlled by one person is known as ______.", "options": {"A": "partnership", "B": "cooperative society", "C": "sole proprietorship", "D": "limited liability company"}, "answer": "C"},
    {"stem": "One major advantage of sole proprietorship is that ______.", "options": {"A": "it has unlimited capital", "B": "decision making is quick", "C": "ownership is shared", "D": "profits are shared"}, "answer": "B"},
    {"stem": "Partnership is a business organisation owned by ______.", "options": {"A": "one person", "B": "two or more persons", "C": "the government", "D": "a cooperative group"}, "answer": "B"},
    {"stem": "One disadvantage of partnership is that ______.", "options": {"A": "it has more capital", "B": "profit is not shared", "C": "partners may disagree", "D": "it has legal status"}, "answer": "C"},
    {"stem": "A limited liability company is owned by ______.", "options": {"A": "a sole trader", "B": "partners", "C": "shareholders", "D": "cooperative members"}, "answer": "C"},
    {"stem": "Which of the following is an advantage of a limited liability company?", "options": {"A": "Unlimited liability", "B": "Limited capital", "C": "Continuity of existence", "D": "Slow decision making"}, "answer": "C"},
    {"stem": "A cooperative society is formed mainly to ______.", "options": {"A": "maximize profit", "B": "serve the interest of members", "C": "employ many workers", "D": "pay high taxes"}, "answer": "B"},
    {"stem": "One disadvantage of cooperative societies is that ______.", "options": {"A": "capital is raised easily", "B": "members share benefits", "C": "decision making may be slow", "D": "members cooperate"}, "answer": "C"},
    {"stem": "______ does not take active part in the running of a partnership business.", "options": {"A": "General partner", "B": "Dormant or sleeping partner", "C": "Active partner", "D": "Limited partner"}, "answer": "B"},
    {"stem": "A consumer is a person who ______.", "options": {"A": "produces goods", "B": "buys and uses goods and services", "C": "sells goods in the market", "D": "transports goods"}, "answer": "B"},
    {"stem": "A market can best be defined as ______.", "options": {"A": "a shopping mall", "B": "a place where people meet socially", "C": "a place where buyers and sellers interact", "D": "a warehouse"}, "answer": "C"},
    {"stem": "Society refers to ______.", "options": {"A": "a group of animals", "B": "people living together and sharing common interests", "C": "a market place", "D": "a business organization"}, "answer": "B"},
    {"stem": "One major need for consumer education is to ______.", "options": {"A": "increase prices of goods", "B": "help consumers make wise choices", "C": "stop production", "D": "discourage buying"}, "answer": "B"},
    {"stem": "Which of the following is an importance of consumer education?", "options": {"A": "It promotes cheating", "B": "It encourages waste", "C": "It protects consumers from fake goods", "D": "It increases ignorance"}, "answer": "C"},
    {"stem": "Lack of consumer education may lead to ______.", "options": {"A": "wise spending", "B": "buying substandard goods", "C": "proper budgeting", "D": "good saving habit"}, "answer": "B"},
    {"stem": "Chemicals are substances that ______.", "options": {"A": "are always poisonous", "B": "are used only in schools", "C": "are used in industries, homes, and farms", "D": "cannot be controlled"}, "answer": "C"},
    {"stem": "Which of the following is a chemical suitable for use?", "options": {"A": "Expired drugs", "B": "Approved food preservatives", "C": "Fake fertilizer", "D": "Banned insecticides"}, "answer": "B"},
    {"stem": "A chemical NOT suitable for use is one that ______.", "options": {"A": "is approved by authorities", "B": "is properly labeled", "C": "has expired", "D": "is safe"}, "answer": "C"},
    {"stem": "Monitoring chemicals in food is important in order to ______.", "options": {"A": "increase food poisoning", "B": "reduce food supply", "C": "ensure food safety", "D": "stop food production"}, "answer": "C"},
    {"stem": "Drug control is necessary to prevent ______.", "options": {"A": "drug abuse", "B": "good health", "C": "proper treatment", "D": "hospital care"}, "answer": "A"},
    {"stem": "One reason for controlling chemicals is to ______.", "options": {"A": "protect human life", "B": "encourage pollution", "C": "promote fake products", "D": "increase illness"}, "answer": "A"},
    {"stem": "Book keeping is the recording of ______.", "options": {"A": "school activities", "B": "business transactions", "C": "market prices", "D": "government laws"}, "answer": "B"},
    {"stem": "One importance of book keeping is that it helps to ______.", "options": {"A": "hide business records", "B": "determine profit or loss", "C": "stop business growth", "D": "increase expenses"}, "answer": "B"},
    {"stem": "Which of the following is an essential quality of a book keeper?", "options": {"A": "Carelessness", "B": "Honesty", "C": "Laziness", "D": "Dishonesty"}, "answer": "B"},
    {"stem": "Accuracy in book keeping means ______.", "options": {"A": "guessing figures", "B": "writing figures correctly", "C": "delaying records", "D": "forgetting entries"}, "answer": "B"},
    {"stem": "A common book-keeping practice is ______.", "options": {"A": "delaying record keeping", "B": "keeping proper records", "C": "guessing expenses", "D": "hiding transactions"}, "answer": "B"},
    {"stem": "Failure to keep proper records can result in ______.", "options": {"A": "business success", "B": "confusion in business", "C": "accurate accounts", "D": "easy auditing"}, "answer": "B"},
    {"stem": "Book keeping helps business owners to ______.", "options": {"A": "waste money", "B": "plan for the future", "C": "increase losses", "D": "avoid saving"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Explain the following terms:\n(a) Consumer\n(b) Market\n(c) Society", "marks": Decimal("10.00")},
    {"stem": "2. State and explain three needs for consumer education.", "marks": Decimal("10.00")},
    {"stem": "3. Explain three reasons for monitoring and controlling chemicals used in food, drugs, and the environment.", "marks": Decimal("10.00")},
    {"stem": "4. Explain the meaning of the following terms:\n(a) Entrepreneurship\n(b) Enterprise\n(c) Self-employment", "marks": Decimal("10.00")},
    {"stem": "5. (a) Define book keeping.\n(b) State three importance of book keeping.", "marks": Decimal("10.00")},
    {"stem": "6. (a) Define business organization.\n(b) List three types of business organisation.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="BST")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="arinze@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 7, 45, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 9, 45, tzinfo=lagos)

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
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 7:45 AM WAT.",
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
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 7:45 AM WAT."
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
            source_reference=f"JS1-BST-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS1-BST-20260325-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 55
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS1-BST-EXAM",
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
