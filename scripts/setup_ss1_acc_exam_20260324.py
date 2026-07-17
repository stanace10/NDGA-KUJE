from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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


TITLE = "TUE 8:30-9:30 SS1 Financial Accounting Second Term Exam"
DESCRIPTION = "SS1 Financial Accounting Second Term Examination"
BANK_NAME = "SS1 Financial Accounting Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 60 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "A Bank Reconciliation Statement is prepared mainly to ______.", "options": {"A": "determine bank charges", "B": "reconcile differences between cash book and bank statement balances", "C": "calculate profit of a business", "D": "record credit sales"}, "answer": "B"},
    {"stem": "One cause of disagreement between the cash book and bank statement is ______.", "options": {"A": "purchases journal", "B": "outstanding cheques", "C": "trading account", "D": "capital account"}, "answer": "B"},
    {"stem": "A cheque issued but not yet presented for payment is called ______.", "options": {"A": "dishonoured cheque", "B": "stale cheque", "C": "outstanding cheque", "D": "endorsed cheque"}, "answer": "C"},
    {"stem": "Bank charges recorded in the bank statement but not yet in the cash book will cause the ______.", "options": {"A": "cash book balance to be lower", "B": "bank statement balance to be higher", "C": "cash book balance to be higher", "D": "bank statement balance to be lower"}, "answer": "C"},
    {"stem": "A deposit made but not yet recorded in the bank statement is known as ______.", "options": {"A": "outstanding deposit", "B": "dishonoured cheque", "C": "standing order", "D": "bank overdraft"}, "answer": "A"},
    {"stem": "When preparing a bank reconciliation statement, outstanding cheques are ______.", "options": {"A": "added to bank statement balance", "B": "deducted from bank statement balance", "C": "added to cash book balance", "D": "ignored completely"}, "answer": "B"},
    {"stem": "The balance as per cash book is N12,000 while outstanding cheques amount to N2,000. The adjusted bank balance will be ______.", "options": {"A": "N10,000", "B": "N12,000", "C": "N14,000", "D": "N8,000"}, "answer": "A"},
    {"stem": "If deposits in transit amount to N3,000 and bank statement balance is N15,000, the adjusted balance will be ______.", "options": {"A": "N12,000", "B": "N15,000", "C": "N18,000", "D": "N10,000"}, "answer": "C"},
    {"stem": "The cash book shows N20,000 while bank charges of N500 appear only in the bank statement. The corrected cash book balance is ______.", "options": {"A": "N20,500", "B": "N19,500", "C": "N20,000", "D": "N19,000"}, "answer": "B"},
    {"stem": "Standing orders paid by the bank but not yet entered in the cash book will be ______.", "options": {"A": "added to cash book", "B": "deducted from cash book", "C": "added to bank statement", "D": "ignored"}, "answer": "B"},
    {"stem": "Which of the following is a personal account?", "options": {"A": "Furniture account", "B": "Sales account", "C": "Debtors account", "D": "Rent account"}, "answer": "C"},
    {"stem": "A real account relates to ______.", "options": {"A": "assets and properties", "B": "expenses", "C": "incomes", "D": "liabilities only"}, "answer": "A"},
    {"stem": "Which of the following is a nominal account?", "options": {"A": "Machinery", "B": "Rent", "C": "Cash", "D": "Motor vehicle"}, "answer": "B"},
    {"stem": "The rule of debit and credit for real accounts is ______.", "options": {"A": "debit the giver, credit the receiver", "B": "debit what comes in, credit what goes out", "C": "debit expenses, credit incomes", "D": "debit capital, credit drawings"}, "answer": "B"},
    {"stem": "The rule for nominal accounts is ______.", "options": {"A": "debit expenses and losses, credit incomes and gains", "B": "debit receiver, credit giver", "C": "debit capital, credit assets", "D": "debit liabilities, credit expenses"}, "answer": "A"},
    {"stem": "A trial balance is prepared mainly to ______.", "options": {"A": "determine net profit", "B": "test arithmetic accuracy of ledger accounts", "C": "prepare balance sheet", "D": "record transactions"}, "answer": "B"},
    {"stem": "A trial balance contains ______.", "options": {"A": "debit and credit balances of ledger accounts", "B": "cash balances only", "C": "assets and liabilities only", "D": "expenses only"}, "answer": "A"},
    {"stem": "If the debit side of a trial balance exceeds the credit side by N1,200, the difference is called ______.", "options": {"A": "balancing figure", "B": "suspense account", "C": "capital", "D": "profit"}, "answer": "B"},
    {"stem": "The trial balance totals N50,000 on debit side and N48,000 on credit side. The difference is ______.", "options": {"A": "N2,000", "B": "N1,000", "C": "N48,000", "D": "N50,000"}, "answer": "A"},
    {"stem": "Error of omission occurs when ______.", "options": {"A": "transaction is recorded twice", "B": "transaction is completely omitted", "C": "wrong amount is recorded", "D": "correct entry is made in wrong account"}, "answer": "B"},
    {"stem": "Error of commission occurs when ______.", "options": {"A": "correct amount is posted to wrong account", "B": "transaction is omitted entirely", "C": "wrong principle is applied", "D": "compensating errors occur"}, "answer": "A"},
    {"stem": "Error of principle occurs when ______.", "options": {"A": "wrong classification of accounts is made", "B": "entry is omitted", "C": "figures are added wrongly", "D": "ledger is balanced wrongly"}, "answer": "A"},
    {"stem": "Compensating errors occur when ______.", "options": {"A": "two errors cancel each other", "B": "one error exists", "C": "arithmetic mistake occurs", "D": "entries are omitted"}, "answer": "A"},
    {"stem": "If goods worth N5,000 are posted as N500, the error is ______.", "options": {"A": "error of principle", "B": "error of commission", "C": "compensating error", "D": "complete omission"}, "answer": "B"},
    {"stem": "If rent paid N4,000 is debited to furniture account, it is ______.", "options": {"A": "error of omission", "B": "error of commission", "C": "error of principle", "D": "compensating error"}, "answer": "C"},
    {"stem": "The trading account is prepared to determine ______.", "options": {"A": "net profit", "B": "gross profit or loss", "C": "capital", "D": "expenses"}, "answer": "B"},
    {"stem": "The difference between sales and cost of goods sold is ______.", "options": {"A": "net profit", "B": "gross profit", "C": "capital", "D": "expenses"}, "answer": "B"},
    {"stem": "Opening stock N10,000, purchases N40,000, closing stock N8,000. Cost of goods sold is ______.", "options": {"A": "N42,000", "B": "N48,000", "C": "N32,000", "D": "N50,000"}, "answer": "A"},
    {"stem": "Sales N70,000 and cost of goods sold N50,000. Gross profit equals ______.", "options": {"A": "N20,000", "B": "N30,000", "C": "N50,000", "D": "N10,000"}, "answer": "A"},
    {"stem": "Opening stock N5,000, purchases N25,000, closing stock N4,000. Cost of goods sold equals ______.", "options": {"A": "N26,000", "B": "N30,000", "C": "N24,000", "D": "N20,000"}, "answer": "A"},
    {"stem": "If sales are N60,000 and gross profit is N15,000, cost of goods sold is ______.", "options": {"A": "N45,000", "B": "N75,000", "C": "N30,000", "D": "N50,000"}, "answer": "A"},
    {"stem": "The general journal is also known as ______.", "options": {"A": "day book", "B": "ledger", "C": "petty cash book", "D": "trial balance"}, "answer": "A"},
    {"stem": "The general journal is mainly used to record ______.", "options": {"A": "routine transactions only", "B": "special transactions and adjustments", "C": "cash sales", "D": "credit purchases only"}, "answer": "B"},
    {"stem": "One advantage of the general journal is ______.", "options": {"A": "it simplifies recording complex transactions", "B": "it replaces ledger", "C": "it eliminates trial balance", "D": "it records cash transactions only"}, "answer": "A"},
    {"stem": "Opening entries in accounting are made to ______.", "options": {"A": "record previous balances in new books", "B": "record sales only", "C": "calculate profit", "D": "close accounts"}, "answer": "A"},
    {"stem": "Closing entries are made to ______.", "options": {"A": "transfer balances to trading and profit accounts", "B": "record purchases", "C": "record expenses", "D": "record assets only"}, "answer": "A"},
    {"stem": "Cash book balance N25,000; bank charges N1,000 not recorded. Correct balance is ______.", "options": {"A": "N24,000", "B": "N26,000", "C": "N25,000", "D": "N23,000"}, "answer": "A"},
    {"stem": "Cash book shows N30,000 while outstanding cheque N5,000 exists. Adjusted bank balance is ______.", "options": {"A": "N35,000", "B": "N25,000", "C": "N30,000", "D": "N20,000"}, "answer": "B"},
    {"stem": "Bank statement N40,000; deposit in transit N3,000. Adjusted balance equals ______.", "options": {"A": "N43,000", "B": "N37,000", "C": "N40,000", "D": "N36,000"}, "answer": "A"},
    {"stem": "Opening stock N6,000, purchases N14,000, closing stock N5,000. Cost of goods sold equals ______.", "options": {"A": "N15,000", "B": "N20,000", "C": "N10,000", "D": "N19,000"}, "answer": "A"},
    {"stem": "Sales N80,000; cost of goods sold N60,000. Gross profit equals ______.", "options": {"A": "N20,000", "B": "N30,000", "C": "N40,000", "D": "N60,000"}, "answer": "A"},
    {"stem": "Purchases N50,000; opening stock N10,000; closing stock N15,000. Cost of goods sold equals ______.", "options": {"A": "N45,000", "B": "N55,000", "C": "N60,000", "D": "N35,000"}, "answer": "A"},
    {"stem": "Sales N90,000; cost of goods sold N70,000. Gross profit equals ______.", "options": {"A": "N20,000", "B": "N10,000", "C": "N30,000", "D": "N70,000"}, "answer": "A"},
    {"stem": "Opening stock N12,000; purchases N48,000; closing stock N10,000. Cost of goods sold equals ______.", "options": {"A": "N50,000", "B": "N60,000", "C": "N48,000", "D": "N40,000"}, "answer": "A"},
]

THEORY = [
    {"stem": "Explain the concept of Bank Reconciliation Statement and state four causes of differences between the cash book and bank statement.\n\nOn 31st December 1998, Ojoge and Co cash book showed a balance of cash as N700 but this was not the same as the bank statement on the same day. On investigation, the following items were discovered to show the discrepancy:\n(a) A cheque received for N2,000 entered in the cash book was not entered by the bank until January 9.\n(b) Cheques issued amounting to N4,000 had not been presented for payment.\n(c) A standing order with the bank for N200 subscription to a school was not recorded.\n(d) A dividend of N150 had been received by the bank but not entered in the cash book.\n(e) Bank charges N500 were not recorded in the cash book.\n(f) A customer paid N15 into the bank account as credit transfer. It had not been recorded in the cash book.\n\nPrepare the bank reconciliation statement as at 31st December 1998 to reconcile the two balances.", "marks": Decimal("10.00")},
    {"stem": "Classify the following accounts into personal, real and nominal accounts: (i) Lanju Nigeria Limited (ii) Account payable (iii) Machinery account (iv) Discount allowed (v) Account receivable.\n\nState and explain the rules of debit and credit for each class of account.", "marks": Decimal("10.00")},
    {"stem": "Define Trial Balance and explain its structure.\n\nState five limitations of a trial balance.", "marks": Decimal("10.00")},
    {"stem": "Identify the following errors as discovered from the book of Aramide: (i) Rent receivable of N500 had been recorded in the sales account (ii) Payment of N1,000 was completely omitted from the book (iii) Sales of N1,070 was entered as N7,010.\n\nDescribe how these errors are corrected in accounting records.", "marks": Decimal("10.00")},
    {"stem": "Explain the meaning of a Trading Account.\n\nPrepare a simple Trading Account from the following information: Opening Stock N10,000; Purchases N40,000; Sales N70,000; Closing Stock N8,000; Return outward N1,200; Return inward N2,400; Carriage inward N2,000.", "marks": Decimal("10.00")},
]


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="ACC")
    academic_class = AcademicClass.objects.get(code="SS1")
    teacher = User.objects.get(username="fadumo@ndgakuje.org")
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher=teacher,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    )

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 24, 8, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 9, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday first paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 8:30 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday first paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 8:30 AM WAT."
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
            source_reference=f"SS1-ACC-20260324-OBJ-{index:02d}",
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
            marks=item["marks"],
            source_reference=f"SS1-ACC-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 60
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS1-ACC-EXAM",
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
            "duration": blueprint.duration_minutes,
        }
    )


main()
