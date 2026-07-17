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


TITLE = "WED 7:45-9:45 JS2 Business Studies Second Term Exam"
DESCRIPTION = "BUSINESS STUDIES JSS2 SECOND TERM EXAMINATION"
BANK_NAME = "JS2 Business Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer question one and any other three questions. "
    "Timer is 55 minutes. Exam window closes at 9:45 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "______ is the principal book of accounts in which business transactions in subsidiary books are permanently recorded.", "options": {"A": "journal", "B": "cash book", "C": "ledger", "D": "record book"}, "answer": "C"},
    {"stem": "The individual pages in the ledger where transactions are recorded are called ______.", "options": {"A": "Journals", "B": "Folios", "C": "Accounts", "D": "Columns"}, "answer": "C"},
    {"stem": "Which of the following is NOT a type of ledger?", "options": {"A": "General ledger", "B": "Sales ledger", "C": "Purchases ledger", "D": "Cash ledger"}, "answer": "D"},
    {"stem": "The left side of a ledger account is known as the ______.", "options": {"A": "Debit side", "B": "Credit side", "C": "Balance side", "D": "Contra side"}, "answer": "A"},
    {"stem": "The act of transferring entries from the journal to the ledger is called ______.", "options": {"A": "Casting", "B": "Posting", "C": "Entry-making", "D": "Trial balancing"}, "answer": "B"},
    {"stem": "A ledger that contains personal accounts of customers is the ______.", "options": {"A": "Sales ledger", "B": "General ledger", "C": "Purchases ledger", "D": "Private ledger"}, "answer": "A"},
    {"stem": "The format of a ledger account usually includes all except ______.", "options": {"A": "Date", "B": "Particulars", "C": "Debit/Credit", "D": "Invoice number"}, "answer": "D"},
    {"stem": "Which ledger contains both personal and impersonal accounts?", "options": {"A": "Private ledger", "B": "General ledger", "C": "Sales ledger", "D": "Purchases ledger"}, "answer": "B"},
    {"stem": "A ledger account has columns for date, particulars, folio and ______ on both sides.", "options": {"A": "Naira", "B": "Amount", "C": "Dollar", "D": "Pound"}, "answer": "B"},
    {"stem": "Cash receipts are recorded on the ______ side of the cash book.", "options": {"A": "Credit", "B": "Debit", "C": "Both sides", "D": "None"}, "answer": "B"},
    {"stem": "Cash payments are recorded on the ______ side of the cash book.", "options": {"A": "Debit", "B": "Credit", "C": "Both debit and credit", "D": "Neither"}, "answer": "B"},
    {"stem": "Discount allowed is treated as ______ in the books of the business.", "options": {"A": "Expense", "B": "Income", "C": "Liability", "D": "Asset"}, "answer": "A"},
    {"stem": "Discount received is treated as ______ by the business.", "options": {"A": "Expense", "B": "Income", "C": "Capital", "D": "Liability"}, "answer": "B"},
    {"stem": "Cash receipts and payments are recorded in a ______.", "options": {"A": "Ledger only", "B": "Cash book", "C": "Sales journal", "D": "Purchases journal"}, "answer": "B"},
    {"stem": "When a customer pays early and is given a reduction, the reduction is known as ______.", "options": {"A": "Trade discount", "B": "Cash discount", "C": "Quantity discount", "D": "Price discount"}, "answer": "B"},
    {"stem": "The petty cash book is used to record ______.", "options": {"A": "Major expenses", "B": "Minor expenses", "C": "Credit transactions", "D": "Cash and credit transactions"}, "answer": "B"},
    {"stem": "Which of the following is not an item of expenditure in the petty cash book?", "options": {"A": "Postage", "B": "Recharge cards", "C": "Sundry expenses", "D": "Land"}, "answer": "D"},
    {"stem": "The petty cash can also be called the following names except ______.", "options": {"A": "Float", "B": "Imprest", "C": "Small cash", "D": "Loan"}, "answer": "D"},
    {"stem": "The ledger is divided into ______ parts.", "options": {"A": "3", "B": "4", "C": "2", "D": "5"}, "answer": "C"},
    {"stem": "The debit side of a ledger is for recording items ______.", "options": {"A": "Given", "B": "Rejected", "C": "Received", "D": "Delivered"}, "answer": "C"},
    {"stem": "Which of the following is a column in a petty cash book?", "options": {"A": "Ledger folio", "B": "Cash discount", "C": "Analysis column", "D": "Trial balance"}, "answer": "C"},
    {"stem": "The balance carried down in petty cash book appears on the ______.", "options": {"A": "Debit side only", "B": "Credit side only", "C": "Both sides", "D": "None"}, "answer": "B"},
    {"stem": "The imprest system means ______.", "options": {"A": "Keeping unlimited cash", "B": "Giving petty cashier a fixed amount to spend", "C": "Daily balancing of accounts", "D": "Ignoring small expenses"}, "answer": "B"},
    {"stem": "The cash book is regarded as ______.", "options": {"A": "a memorandum", "B": "a ledger and a book of original entry", "C": "a trial balance", "D": "an income statement"}, "answer": "B"},
    {"stem": "The columns of a simple cash book are ______ in number.", "options": {"A": "8", "B": "7", "C": "5", "D": "4"}, "answer": "D"},
    {"stem": "A single-column cash book has only ______.", "options": {"A": "Cash column", "B": "Bank column", "C": "Discount column", "D": "Petty cash column"}, "answer": "A"},
    {"stem": "Double-column cash book contains ______.", "options": {"A": "Cash and petty cash", "B": "Cash and discount", "C": "Bank and petty cash", "D": "Petty cash and discount"}, "answer": "B"},
    {"stem": "Items in a double-column cash book include ______.", "options": {"A": "Returns inward", "B": "Discounts allowed and received", "C": "Drawings only", "D": "Purchases only"}, "answer": "B"},
    {"stem": "A contra entry occurs when ______.", "options": {"A": "Cash is paid to creditors", "B": "Goods are sold on credit", "C": "Cash is paid into bank", "D": "Petty cash is used"}, "answer": "C"},
    {"stem": "Contra entries are marked with ______.", "options": {"A": "CC", "B": "C", "C": "LF", "D": "Doc no."}, "answer": "B"},
    {"stem": "Three-column cash book contains ______.", "options": {"A": "Cash, bank, ledger folio", "B": "Cash, bank, discount", "C": "Cash, petty, discount", "D": "Petty, bank, discount"}, "answer": "B"},
    {"stem": "Discount allowed is treated as ______.", "options": {"A": "Income", "B": "Expense", "C": "Liability", "D": "Asset"}, "answer": "B"},
    {"stem": "Discount received is treated as ______.", "options": {"A": "Income", "B": "Expense", "C": "Asset", "D": "Liability"}, "answer": "A"},
    {"stem": "One major difference between petty cash book and cash book is that ______.", "options": {"A": "petty cash book records large transactions", "B": "cash book records small expenses", "C": "petty cash book is for minor expenses", "D": "petty cash book contains bank column"}, "answer": "C"},
    {"stem": "Petty cash analysis columns include ______.", "options": {"A": "Rent, wages, expenses", "B": "Stationery, postage, transport", "C": "Sales, purchases, returns", "D": "Assets, liabilities, capital"}, "answer": "B"},
    {"stem": "The imprest amount is restored ______.", "options": {"A": "Weekly", "B": "Monthly", "C": "Whenever petty cash balance is low", "D": "End of the year only"}, "answer": "C"},
    {"stem": "A three-column cash book does NOT include ______.", "options": {"A": "Cash", "B": "Bank", "C": "Discount", "D": "Petty cash"}, "answer": "D"},
    {"stem": "The credit side of cash column shows ______.", "options": {"A": "Cash received", "B": "Cash paid", "C": "Cash shortage", "D": "Final balance"}, "answer": "B"},
    {"stem": "If cash is withdrawn from bank, it is entered as ______.", "options": {"A": "Debit in bank, credit in cash", "B": "Debit cash, credit bank", "C": "Credit both", "D": "Debit both"}, "answer": "B"},
    {"stem": "The exchange of goods for goods is referred to as ______.", "options": {"A": "Barter", "B": "Business", "C": "Commerce", "D": "Trade"}, "answer": "A"},
]

THEORY = [
    {
        "stem": (
            "1. Enter the following transactions in the cash book of Brogbenda Nguliyan for the month of January, 2019:\n"
            "Jan 1: Started a retail business with ₦200,000 cash\n"
            "Jan 6: Bought goods worth ₦40,000 by cash\n"
            "Jan 7: Received ₦10,000\n"
            "Jan 11: Paid the following expenses in cash: Stamps ₦200, diesel ₦1,700\n"
            "Jan 13: Paid cash ₦5,000 to Alison\n"
            "Jan 16: Bought a motorcycle by cash ₦75,000\n"
            "Jan 18: Received a cash loan of ₦50,000 from Joy Idakwo\n"
            "Jan 24: Bought goods worth ₦7,000 by cash\n"
            "Jan 30: Paid salaries of sales person ₦20,000"
        ),
        "marks": Decimal("10.00"),
    },
    {"stem": "2. (a) Define petty cash book and state four items recorded in it.\n(b) Explain the imprest system and give two advantages of using it.", "marks": Decimal("10.00")},
    {"stem": "3. (a) Define a cash book and write three reasons it is called both a book of original entry and a ledger.\n(b) State four differences between cash book and petty cash book.", "marks": Decimal("10.00")},
    {"stem": "4. (a) Explain the term contra entry and give two examples.\n(b) Explain the difference between discount allowed and discount received.", "marks": Decimal("10.00")},
    {"stem": "5. (a) Define a ledger.\n(b) List and explain two types of ledgers.\n(c) State three importance of a ledger.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
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
            source_reference=f"JS2-BST-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS2-BST-20260325-TH-{index:02d}",
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
        "paper_code": "JS2-BST-EXAM",
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
