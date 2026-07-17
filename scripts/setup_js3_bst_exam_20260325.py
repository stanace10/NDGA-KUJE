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


TITLE = "WED 7:45-9:45 JS3 Business Studies Second Term Exam"
DESCRIPTION = "J.S.3 BUSINESS STUDIES SECOND TERM EXAMINATION"
BANK_NAME = "JS3 Business Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all questions. "
    "Timer is 55 minutes. Exam window closes at 9:45 AM WAT on Wednesday, March 25, 2026."
)

# Source question 4 was blank in the supplied paper, so it is intentionally omitted.
OBJECTIVES = [
    {"stem": "Page size commonly used for letters and assignments is ______.", "options": {"A": "A3", "B": "A4", "C": "A5", "D": "Legal"}, "answer": "B"},
    {"stem": "Which page size is mostly used for posters and charts?", "options": {"A": "A5", "B": "A4", "C": "A3", "D": "A6"}, "answer": "C"},
    {"stem": "A5 page size is mostly used for ______.", "options": {"A": "Newspapers", "B": "Posters", "C": "Notebooks", "D": "Journals"}, "answer": "C"},
    {"stem": "Display in word processing refers to ______.", "options": {"A": "Printing the document", "B": "What appears on the screen", "C": "Type of paper used", "D": "Number of headings"}, "answer": "B"},
    {"stem": "Which of the following is NOT a method of display?", "options": {"A": "Horizontal", "B": "Vertical", "C": "Diagonal", "D": "None of the above"}, "answer": "C"},
    {"stem": "Horizontal display is also called ______.", "options": {"A": "Portrait", "B": "Landscape", "C": "Column", "D": "Margin"}, "answer": "B"},
    {"stem": "Vertical display is also called ______.", "options": {"A": "Landscape", "B": "Portrait", "C": "Banner", "D": "Table"}, "answer": "B"},
    {"stem": "To create a table in Word, you go to ______.", "options": {"A": "File > New", "B": "Insert > Table", "C": "View > Table", "D": "Home > Table"}, "answer": "B"},
    {"stem": "Main heading is usually written ______.", "options": {"A": "At the bottom of the page", "B": "At the centre top of the page", "C": "Along the left margin", "D": "At the right margin"}, "answer": "B"},
    {"stem": "An expression of dissatisfaction which is oral or written can be termed ______.", "options": {"A": "Complaint", "B": "Bad expression", "C": "Quarrelling", "D": "Information"}, "answer": "A"},
    {"stem": "The following are government agencies responsible for protection of consumers except ______.", "options": {"A": "Investment promotion board", "B": "Price control board", "C": "Rent tribunal", "D": "Standard Organization of Nigeria"}, "answer": "A"},
    {"stem": "Purchases in accounting refers to goods bought for ______.", "options": {"A": "Resale", "B": "Repairs", "C": "Decoration of staff offices", "D": "Processing"}, "answer": "A"},
    {"stem": "Manuscript means ______.", "options": {"A": "Typed document", "B": "Handwritten document", "C": "Printed document", "D": "Computerized document"}, "answer": "B"},
    {"stem": "Longhand manuscript refers to ______.", "options": {"A": "Writing in full words", "B": "Writing in symbols", "C": "Writing in shorthand", "D": "Writing in codes"}, "answer": "A"},
    {"stem": "Abbreviations on manuscript are used to ______.", "options": {"A": "Make writing longer", "B": "Save time and space", "C": "Reduce accuracy", "D": "Increase errors"}, "answer": "B"},
    {"stem": "Which of the following is an abbreviation?", "options": {"A": "School", "B": "Government", "C": "Govt", "D": "Education"}, "answer": "C"},
    {"stem": "Standard manuscript refers to ______.", "options": {"A": "Accepted rules of writing", "B": "Informal writing", "C": "Personal notes", "D": "Rough draft"}, "answer": "A"},
    {"stem": "Printer's correction signs are used to ______.", "options": {"A": "Change page size", "B": "Correct errors in manuscripts", "C": "Add tables", "D": "Change display"}, "answer": "B"},
    {"stem": "The correction sign used to delete a word is ______.", "options": {"A": "^", "B": "¶", "C": "~", "D": "/"}, "answer": "C"},
    {"stem": "Erasing techniques are used to ______.", "options": {"A": "Make the paper dirty", "B": "Correct mistakes", "C": "Increase typing speed", "D": "Change the page size"}, "answer": "B"},
    {"stem": "Which of the following is a method of erasing?", "options": {"A": "Using a pencil", "B": "Using an eraser", "C": "Using a ruler", "D": "Using a stapler"}, "answer": "B"},
    {"stem": "Calculate the total fixed asset. (Fixed assets = Furniture ₦2,000 + Machinery ₦3,200.)", "options": {"A": "₦5,600", "B": "₦5,200", "C": "₦5,000", "D": "₦3,400"}, "answer": "B"},
    {"stem": "Calculate the current asset. (Cash in hand ₦1,400 + Stock ₦300 + Bank ₦1,200 + Debtor ₦500.)", "options": {"A": "₦2,500", "B": "₦4,500", "C": "₦4,000", "D": "₦3,400"}, "answer": "D"},
    {"stem": "Carbon copy should be erased with ______.", "options": {"A": "Hard pressure", "B": "Soft pressure", "C": "No pressure", "D": "Medium pressure"}, "answer": "B"},
    {"stem": "Erasing on carbon copy requires ______.", "options": {"A": "Heavy erasing", "B": "Gentle erasing", "C": "Using a pen", "D": "Using scissors"}, "answer": "B"},
    {"stem": "Which copy is most sensitive to erasing?", "options": {"A": "Top copy", "B": "Carbon copy", "C": "Third copy", "D": "None"}, "answer": "B"},
    {"stem": "Correct keyboarding technique helps to ______.", "options": {"A": "Increase typing speed", "B": "Reduce errors", "C": "Improve posture", "D": "All of the above"}, "answer": "D"},
    {"stem": "The top row of the keyboard contains ______.", "options": {"A": "Numbers", "B": "Letters", "C": "Function keys", "D": "Space bar"}, "answer": "C"},
    {"stem": "The home row of the keyboard is where ______.", "options": {"A": "Typing begins", "B": "Fingers rest", "C": "Function keys are found", "D": "Numbers are typed"}, "answer": "B"},
    {"stem": "The bottom row of the keyboard contains ______.", "options": {"A": "Space bar and Ctrl keys", "B": "Function keys", "C": "Numbers", "D": "None of the above"}, "answer": "A"},
    {"stem": "The upper row of the keyboard contains ______.", "options": {"A": "Letters A-Z", "B": "Numbers 1-0", "C": "Function keys", "D": "Cursor keys"}, "answer": "B"},
    {"stem": "The keyboard is divided into how many sides?", "options": {"A": "One", "B": "Two", "C": "Three", "D": "Four"}, "answer": "B"},
    {"stem": "The left hand side of the keyboard contains ______.", "options": {"A": "Numeric keypad", "B": "Letters and symbols", "C": "Function keys", "D": "Arrow keys"}, "answer": "B"},
    {"stem": "The right hand side of the keyboard contains ______.", "options": {"A": "Letters and symbols", "B": "Numeric keypad and arrow keys", "C": "Function keys", "D": "Space bar"}, "answer": "B"},
    {"stem": "Alphanumeric keys are used for typing ______.", "options": {"A": "Letters only", "B": "Numbers only", "C": "Letters and numbers", "D": "Symbols only"}, "answer": "C"},
    {"stem": "Identification of alphanumeric keys means ______.", "options": {"A": "Knowing their position", "B": "Ignoring them", "C": "Deleting them", "D": "Replacing them"}, "answer": "A"},
    {"stem": "Soft touch manipulation refers to ______.", "options": {"A": "Typing very hard", "B": "Typing gently", "C": "Not typing at all", "D": "Using only one finger"}, "answer": "B"},
    {"stem": "Correct finger placement on the keyboard helps to ______.", "options": {"A": "Increase errors", "B": "Reduce speed", "C": "Improve accuracy", "D": "Break the keyboard"}, "answer": "C"},
    {"stem": "The home keys on the keyboard are ______.", "options": {"A": "A, S, D, F, J, K, L, ;", "B": "Q, W, E, R, T, Y, U, I", "C": "Z, X, C, V, B, N, M", "D": "1, 2, 3, 4, 5"}, "answer": "A"},
    {"stem": "The key used to delete characters to the left of the cursor is ______.", "options": {"A": "Enter", "B": "Backspace", "C": "Shift", "D": "Tab"}, "answer": "B"},
    {"stem": "The key used to delete characters to the right of the cursor is ______.", "options": {"A": "Delete", "B": "Backspace", "C": "Spacebar", "D": "Enter"}, "answer": "A"},
    {"stem": "A list of balances to check the arithmetical accuracy of the entries in the ledger is called ______.", "options": {"A": "Balance sheet", "B": "Purchases account", "C": "Sales account", "D": "Trading account", "E": "Trial balance"}, "answer": "E"},
    {"stem": "Trial balance is based on ______ entry system.", "options": {"A": "Accounting", "B": "Credit", "C": "Debit", "D": "Double"}, "answer": "D"},
    {"stem": "Which one of the following best defines net profit?", "options": {"A": "Administrative plus warehouse expenses", "B": "Difference between purchase and discounts", "C": "Net sales minus total expenses", "D": "Returns outward minus inwards"}, "answer": "C"},
    {"stem": "Profit and loss account is prepared to show the ______.", "options": {"A": "Cash at bank", "B": "Gross profit", "C": "Gross purchases", "D": "Gross sales", "E": "Net profit or loss"}, "answer": "E"},
    {"stem": "Trading account is prepared to show the ______.", "options": {"A": "Cash at bank", "B": "Gross profit or loss", "C": "Gross purchases", "D": "Gross sales", "E": "Profit or loss"}, "answer": "B"},
    {"stem": "The difference between sales and cost of goods sold is the ______.", "options": {"A": "Gross profit", "B": "Market value", "C": "Net loss", "D": "Net profit"}, "answer": "A"},
    {"stem": "Capital is shown on the liabilities side of the balance sheet because it is ______.", "options": {"A": "money used to start the business", "B": "not a fixed asset", "C": "owed by the business to the owner", "D": "owed to the business by the government"}, "answer": "C"},
    {"stem": "Items in the balance sheet are classified into ______.", "options": {"A": "Assets and liabilities", "B": "Capital and current liabilities", "C": "Fixed assets and current liabilities", "D": "Fixed assets and current liabilities"}, "answer": "A"},
    {"stem": "The two types of assets are ______ and ______ assets.", "options": {"A": "Cash and capital", "B": "Cash and current", "C": "Fixed and current", "D": "Fixed and machinery"}, "answer": "C"},
    {"stem": "The following are the qualities of a clerical staff EXCEPT ______.", "options": {"A": "Arrogance", "B": "Carefulness", "C": "Courtesy", "D": "Diligence"}, "answer": "A"},
    {"stem": "Where does the clerical activity of an organization take place?", "options": {"A": "Board room", "B": "Conference room", "C": "Office", "D": "Shop"}, "answer": "C"},
    {"stem": "Which of these will a filing clerk find MOST useful in carrying out his duty?", "options": {"A": "Calculator", "B": "Computer", "C": "Perforator", "D": "Photocopying machine"}, "answer": "B"},
    {"stem": "The filing system most commonly used by business organizations in Nigeria is ______.", "options": {"A": "Desk", "B": "Electronic", "C": "Lateral", "D": "Shelf"}, "answer": "D"},
    {"stem": "The gift of nature from the following is ______.", "options": {"A": "Capital", "B": "Entrepreneur", "C": "Labour", "D": "Land"}, "answer": "D"},
    {"stem": "Which one of these is correct of production? It is ______.", "options": {"A": "creating services", "B": "doing something for leisure", "C": "making of goods", "D": "making services and goods for satisfaction"}, "answer": "D"},
    {"stem": "The production process is completed by the ______.", "options": {"A": "Consumer", "B": "Manufacturer", "C": "Producer", "D": "Retailer"}, "answer": "A"},
    {"stem": "Which of the following is used for the production of further wealth?", "options": {"A": "Capital", "B": "Entrepreneur", "C": "Goodwill", "D": "Labour", "E": "Land"}, "answer": "A"},
    {"stem": "The reward for capital is ______.", "options": {"A": "Effectiveness", "B": "Efficiency", "C": "Interest", "D": "Rent"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Define keyboard.\n(b) List and explain the four keyboard rows.\n(c) State three functions of the home row.", "marks": Decimal("10.00")},
    {"stem": "2. (a) What is a page size?\n(b) Mention three types of page sizes and state one use of each.", "marks": Decimal("10.00")},
    {"stem": "3. (a) Describe the correct division of the keyboard between the left and right hands.\n(b) Using a diagram or explanation, show the correct finger placement on:\n- home row keys\n- top row keys\n- bottom row keys\n(c) State three benefits of correct keyboarding techniques.", "marks": Decimal("10.00")},
    {"stem": "4. (a) Define a manuscript.\n(b) List four abbreviations commonly used in manuscript preparation.\n(c) Explain any three printer's correction signs.", "marks": Decimal("10.00")},
    {"stem": "5. (a) What is erasing?\n(b) Mention two methods of erasing.\n(c) State three instruments used for erasing.\n(d) Describe how to erase on top copy, carbon copy, and multiple copies.", "marks": Decimal("10.00")},
    {"stem": "6. (a) Define display in keyboarding.\n(b) List and explain three types of display headings.\n(c) State two reasons why display is important.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
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
            source_reference=f"JS3-BST-20260325-OBJ-{index:02d}",
            is_active=True,
        )
        option_map = {}
        labels = list(item["options"].keys())
        for option_index, label in enumerate(labels, start=1):
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
            source_reference=f"JS3-BST-20260325-TH-{index:02d}",
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
        "paper_code": "JS3-BST-EXAM",
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
