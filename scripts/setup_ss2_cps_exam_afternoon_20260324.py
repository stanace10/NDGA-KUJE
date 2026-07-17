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


TITLE = "TUE 1:30-2:30 SS2 Computer Studies Second Term Exam"
DESCRIPTION = "SS2 COMPUTER STUDIES SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Computer Studies Afternoon Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any three questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:30 PM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "A register is best described as a ______.", "options": {"A": "permanent storage unit", "B": "storage location inside the CPU", "C": "storage on hard disk", "D": "secondary memory"}, "answer": "B"},
    {"stem": "Which of the following registers temporarily holds data fetched from memory?", "options": {"A": "CIR", "B": "MAR", "C": "MDR", "D": "PC"}, "answer": "C"},
    {"stem": "The register that stores the instruction currently being executed is the ______.", "options": {"A": "Accumulator", "B": "MDR", "C": "CIR", "D": "Address register"}, "answer": "C"},
    {"stem": "Which of the following is NOT a type of register?", "options": {"A": "Floating Point Register", "B": "Vector Register", "C": "Hard Disk Register", "D": "General Purpose Register"}, "answer": "C"},
    {"stem": "Registers differ from main memory because registers are ______.", "options": {"A": "larger in size", "B": "slower in speed", "C": "located inside the CPU", "D": "non-volatile"}, "answer": "C"},
    {"stem": "The main memory of a computer is also called ______.", "options": {"A": "ROM", "B": "Cache", "C": "Register", "D": "RAM"}, "answer": "D"},
    {"stem": "The bus that carries actual data between CPU and memory is ______.", "options": {"A": "Control bus", "B": "Address bus", "C": "Data bus", "D": "System bus"}, "answer": "C"},
    {"stem": "The width of a bus affects the computer's ______.", "options": {"A": "storage size", "B": "processing speed", "C": "display quality", "D": "power consumption"}, "answer": "B"},
    {"stem": "The fetch-execute cycle begins when the computer ______.", "options": {"A": "shuts down", "B": "loads software", "C": "is powered on", "D": "connects to internet"}, "answer": "C"},
    {"stem": "During the fetch cycle, instructions are first stored in the ______.", "options": {"A": "RAM", "B": "CIR", "C": "MDR", "D": "Cache"}, "answer": "C"},
    {"stem": "A computer file is a collection of ______.", "options": {"A": "programs only", "B": "hardware devices", "C": "related data or information", "D": "instructions only"}, "answer": "C"},
    {"stem": "The smallest unit of data stored in a computer file is called ______.", "options": {"A": "record", "B": "field", "C": "data item", "D": "file"}, "answer": "C"},
    {"stem": "A collection of related fields forms a ______.", "options": {"A": "file", "B": "record", "C": "database", "D": "folder"}, "answer": "B"},
    {"stem": "Which of the following is an example of numeric data?", "options": {"A": "Abuja", "B": "2026", "C": "A23", "D": "True"}, "answer": "B"},
    {"stem": "Alphabetic data consists of ______.", "options": {"A": "numbers only", "B": "symbols only", "C": "letters only", "D": "letters and numbers"}, "answer": "C"},
    {"stem": "Alphanumeric data is best described as ______.", "options": {"A": "letters only", "B": "numbers only", "C": "symbols only", "D": "letters and numbers"}, "answer": "D"},
    {"stem": "Boolean data is usually represented as ______.", "options": {"A": "A-Z", "B": "0-9", "C": "True/False", "D": "A1"}, "answer": "C"},
    {"stem": "Which arrangement is correct?", "options": {"A": "File -> Record -> Field -> Data Item", "B": "Data Item -> Field -> Record -> File", "C": "Record -> File -> Data Item -> Field", "D": "Field -> File -> Record -> Data Item"}, "answer": "B"},
    {"stem": "Records stored in the order they occur use ______.", "options": {"A": "random organization", "B": "indexed organization", "C": "serial organization", "D": "sequential organization"}, "answer": "C"},
    {"stem": "Sequential file organization stores records ______.", "options": {"A": "without order", "B": "randomly", "C": "in sorted order", "D": "by size"}, "answer": "C"},
    {"stem": "A primary key is mostly used in ______.", "options": {"A": "serial files", "B": "indexed files", "C": "transaction files", "D": "reference files"}, "answer": "B"},
    {"stem": "Which file organization allows fastest direct access?", "options": {"A": "Serial", "B": "Sequential", "C": "Random", "D": "Tape"}, "answer": "C"},
    {"stem": "Serial files are best stored on ______.", "options": {"A": "hard disk", "B": "flash drive", "C": "magnetic tape", "D": "optical disk"}, "answer": "C"},
    {"stem": "The method of accessing random files is called ______.", "options": {"A": "serial access", "B": "sequential access", "C": "random access", "D": "indirect access"}, "answer": "C"},
    {"stem": "To access the 20th record in a sequential file, the computer must ______.", "options": {"A": "read only record 20", "B": "read records 1-20", "C": "read records 20-30", "D": "skip earlier records"}, "answer": "B"},
    {"stem": "A file containing permanent data such as payroll is a ______.", "options": {"A": "transaction file", "B": "reference file", "C": "master file", "D": "serial file"}, "answer": "C"},
    {"stem": "Transaction files are mainly used to ______.", "options": {"A": "store permanent data", "B": "update master files", "C": "store software", "D": "archive data"}, "answer": "B"},
    {"stem": "Price lists are examples of ______.", "options": {"A": "master files", "B": "transaction files", "C": "reference files", "D": "random files"}, "answer": "C"},
    {"stem": "File creation refers to ______.", "options": {"A": "deleting files", "B": "opening files", "C": "creating new files", "D": "closing files"}, "answer": "C"},
    {"stem": "Updating a file means ______.", "options": {"A": "copying it", "B": "changing its content", "C": "deleting it", "D": "closing it"}, "answer": "B"},
    {"stem": "File insecurity refers to ______.", "options": {"A": "file storage size", "B": "vulnerability to attacks", "C": "file format", "D": "file organization"}, "answer": "B"},
    {"stem": "Which of the following can cause data loss?", "options": {"A": "virus attack", "B": "human error", "C": "system failure", "D": "All of the above"}, "answer": "D"},
    {"stem": "Overwriting occurs when ______.", "options": {"A": "files are deleted", "B": "old data is replaced by new data", "C": "files are copied", "D": "files are opened"}, "answer": "B"},
    {"stem": "The primary purpose of backup is to ______.", "options": {"A": "save time", "B": "recover lost data", "C": "increase speed", "D": "reduce storage"}, "answer": "B"},
    {"stem": "Which is NOT a file security method?", "options": {"A": "Password", "B": "Backup", "C": "Antivirus", "D": "Formatting"}, "answer": "D"},
    {"stem": "Antivirus software helps to ______.", "options": {"A": "create files", "B": "format disks", "C": "protect against malware", "D": "organize files"}, "answer": "C"},
    {"stem": "One advantage of computerized files is that they ______.", "options": {"A": "occupy more space", "B": "are difficult to retrieve", "C": "allow fast data access", "D": "require no power"}, "answer": "C"},
    {"stem": "A limitation of computerized files is ______.", "options": {"A": "fast processing", "B": "easy retrieval", "C": "high cost of setup", "D": "reliability"}, "answer": "C"},
    {"stem": "Labeling storage devices helps to ______.", "options": {"A": "increase speed", "B": "avoid accidental deletion", "C": "format files", "D": "compress data"}, "answer": "B"},
    {"stem": "Which of the following is an advantage of computerized files?", "options": {"A": "prone to hacking", "B": "requires skilled labour", "C": "easy correction of errors", "D": "expensive to maintain"}, "answer": "C"},
    {"stem": "The register that stores memory addresses is the ______.", "options": {"A": "data register", "B": "address register", "C": "accumulator", "D": "CIR"}, "answer": "B"},
    {"stem": "Bus speed is measured in ______.", "options": {"A": "Bytes", "B": "Bits", "C": "Hertz", "D": "Volts"}, "answer": "C"},
    {"stem": "A wider bus allows ______.", "options": {"A": "less data flow", "B": "more data flow", "C": "slower transfer", "D": "data loss"}, "answer": "B"},
    {"stem": "Which operation allows viewing file content?", "options": {"A": "File close", "B": "File view", "C": "File delete", "D": "File copy"}, "answer": "B"},
    {"stem": "Which file has a very short life span?", "options": {"A": "master file", "B": "reference file", "C": "transaction file", "D": "index file"}, "answer": "C"},
    {"stem": "Which is NOT a data type?", "options": {"A": "Numeric", "B": "Alphabetic", "C": "Boolean", "D": "Magnetic"}, "answer": "D"},
    {"stem": "Data items are stored inside ______.", "options": {"A": "files only", "B": "records only", "C": "fields", "D": "folders"}, "answer": "C"},
    {"stem": "File retrieval means ______.", "options": {"A": "deleting files", "B": "copying files", "C": "recovering stored files", "D": "formatting files"}, "answer": "C"},
    {"stem": "A computer file is stored in ______.", "options": {"A": "CPU", "B": "memory only", "C": "storage devices", "D": "register"}, "answer": "C"},
    {"stem": "The execute cycle ______.", "options": {"A": "fetches instructions", "B": "decodes instructions", "C": "processes instructions", "D": "stores instructions"}, "answer": "C"},
]

THEORY = [
    {"stem": "Define a computer register.\n\nExplain any four types of registers and their functions.", "marks": Decimal("10.00")},
    {"stem": "Define computer file.\n\nExplain the terms data item, field, record and file using a clear example.", "marks": Decimal("10.00")},
    {"stem": "What is file insecurity?\n\nExplain four effects of file insecurity.", "marks": Decimal("10.00")},
    {"stem": "State five basic operations performed on computer files.\n\nExplain any two file security methods.", "marks": Decimal("10.00")},
    {"stem": "State four advantages of computerized files.\n\nState three limitations of computerized files.\n\nExplain two purposes of file backup.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="CPS")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="ukaegbu@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 24, 13, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 14, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 1:30 PM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 1:30 PM WAT."
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
            source_reference=f"SS2-CPS-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS2-CPS-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 50
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS2-CPS-EXAM",
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

