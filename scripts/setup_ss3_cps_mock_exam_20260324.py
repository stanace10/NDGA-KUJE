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


TITLE = "TUE 1:30-3:00 SS3 Computer Studies Mock Examination"
DESCRIPTION = "SS3 COMPUTER STUDIES MOCK EXAMINATION"
BANK_NAME = "SS3 Computer Studies Mock Examination 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 90 minutes. Exam window closes at 3:00 PM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Convert the binary number 1011 (base 2) to decimal.", "options": {"A": "9", "B": "10", "C": "11", "D": "12"}, "answer": "C"},
    {"stem": "Convert the decimal number 13 (base 10) to binary.", "options": {"A": "1101", "B": "1011", "C": "1110", "D": "1001"}, "answer": "A"},
    {"stem": "Which of the following represents a valid hexadecimal number?", "options": {"A": "1G3", "B": "2F9", "C": "45Z", "D": "9H2"}, "answer": "B"},
    {"stem": "The result of the binary addition 1 + 1 is ______.", "options": {"A": "1", "B": "10", "C": "11", "D": "0"}, "answer": "B"},
    {"stem": "The logic gate that produces an output only when all inputs are true is ______.", "options": {"A": "OR", "B": "NOT", "C": "AND", "D": "XOR"}, "answer": "C"},
    {"stem": "The output of a NOT gate is always ______.", "options": {"A": "the same as input", "B": "opposite of input", "C": "zero", "D": "one"}, "answer": "B"},
    {"stem": "In Boolean algebra, the expression A + 0 = ______.", "options": {"A": "0", "B": "A", "C": "1", "D": "NOT A"}, "answer": "B"},
    {"stem": "Which logic gate gives an output of 1 when only one input is 1?", "options": {"A": "AND", "B": "OR", "C": "XOR", "D": "NAND"}, "answer": "C"},
    {"stem": "The register that holds the address of the next instruction is ______.", "options": {"A": "MDR", "B": "MAR", "C": "PC", "D": "CIR"}, "answer": "C"},
    {"stem": "The register that stores the current instruction being executed is ______.", "options": {"A": "PC", "B": "MAR", "C": "CIR", "D": "MDR"}, "answer": "C"},
    {"stem": "The fetch-decode-execute cycle is controlled by the ______.", "options": {"A": "ALU", "B": "Control Unit", "C": "RAM", "D": "Cache"}, "answer": "B"},
    {"stem": "The function of the MAR (Memory Address Register) is to ______.", "options": {"A": "store instructions", "B": "store data temporarily", "C": "hold memory addresses", "D": "decode instructions"}, "answer": "C"},
    {"stem": "Which of the following best improves CPU performance?", "options": {"A": "Increasing RAM only", "B": "Increasing clock speed and cache", "C": "Adding printer", "D": "Using antivirus"}, "answer": "B"},
    {"stem": "Cache memory is used to ______.", "options": {"A": "store permanent files", "B": "speed up processing", "C": "connect networks", "D": "display output"}, "answer": "B"},
    {"stem": "One kilobyte (KB) is equal to ______.", "options": {"A": "1000 bytes", "B": "1024 bytes", "C": "512 bytes", "D": "2048 bytes"}, "answer": "B"},
    {"stem": "Which of the following is a volatile memory?", "options": {"A": "ROM", "B": "Hard disk", "C": "RAM", "D": "CD-ROM"}, "answer": "C"},
    {"stem": "Which storage device has the fastest access time?", "options": {"A": "Hard disk", "B": "SSD", "C": "CD-ROM", "D": "Flash disk"}, "answer": "B"},
    {"stem": "The process of checking errors in data transmission is called ______.", "options": {"A": "Debugging", "B": "Validation", "C": "Verification", "D": "Authentication"}, "answer": "C"},
    {"stem": "In a star topology, failure of the central device leads to ______.", "options": {"A": "partial failure", "B": "total network failure", "C": "no effect", "D": "faster communication"}, "answer": "B"},
    {"stem": "Which topology uses a single communication line?", "options": {"A": "Star", "B": "Ring", "C": "Bus", "D": "Mesh"}, "answer": "C"},
    {"stem": "A device that regenerates signals in a network is a ______.", "options": {"A": "Router", "B": "Switch", "C": "Repeater", "D": "Modem"}, "answer": "C"},
    {"stem": "IP address is used to ______.", "options": {"A": "identify devices on a network", "B": "store data", "C": "run programs", "D": "print documents"}, "answer": "A"},
    {"stem": "Which protocol is used for sending emails?", "options": {"A": "HTTP", "B": "FTP", "C": "SMTP", "D": "IP"}, "answer": "C"},
    {"stem": "Which protocol is used for receiving emails?", "options": {"A": "POP3", "B": "FTP", "C": "HTTP", "D": "TCP"}, "answer": "A"},
    {"stem": "The domain name system (DNS) is used to ______.", "options": {"A": "store files", "B": "translate domain names to IP addresses", "C": "send emails", "D": "connect printers"}, "answer": "B"},
    {"stem": "Which of the following is a valid domain extension?", "options": {"A": ".com", "B": ".exe", "C": ".doc", "D": ".ppt"}, "answer": "A"},
    {"stem": "A hyperlink is used to ______.", "options": {"A": "print documents", "B": "link web pages", "C": "store files", "D": "scan images"}, "answer": "B"},
    {"stem": "In a spreadsheet, a function is used to ______.", "options": {"A": "draw charts", "B": "perform calculations", "C": "print sheets", "D": "format text"}, "answer": "B"},
    {"stem": "The Excel function =SUM(A1:A5) is used to ______.", "options": {"A": "multiply values", "B": "add values", "C": "count values", "D": "average values"}, "answer": "B"},
    {"stem": "Which feature allows tracking changes in a document?", "options": {"A": "Mail Merge", "B": "Track Changes", "C": "Auto Save", "D": "Page Setup"}, "answer": "B"},
    {"stem": "A slide transition controls ______.", "options": {"A": "text formatting", "B": "movement between slides", "C": "data entry", "D": "printing"}, "answer": "B"},
    {"stem": "The first stage of the System Development Life Cycle is ______.", "options": {"A": "Design", "B": "Implementation", "C": "Analysis", "D": "Testing"}, "answer": "C"},
    {"stem": "Debugging is the process of ______.", "options": {"A": "writing programs", "B": "correcting errors in programs", "C": "running programs", "D": "installing programs"}, "answer": "B"},
    {"stem": "An algorithm is best described as ______.", "options": {"A": "a program", "B": "a step-by-step solution to a problem", "C": "a hardware device", "D": "a network"}, "answer": "B"},
    {"stem": "Encryption is used to ______.", "options": {"A": "delete data", "B": "protect data", "C": "copy data", "D": "format data"}, "answer": "B"},
    {"stem": "A firewall is used to ______.", "options": {"A": "increase speed", "B": "block unauthorized access", "C": "store files", "D": "run programs"}, "answer": "B"},
    {"stem": "Which of the following is a form of cyber attack?", "options": {"A": "Phishing", "B": "Printing", "C": "Formatting", "D": "Typing"}, "answer": "A"},
    {"stem": "The use of another person's identity online is called ______.", "options": {"A": "Piracy", "B": "Identity theft", "C": "Spamming", "D": "Hacking"}, "answer": "B"},
    {"stem": "Artificial Intelligence refers to ______.", "options": {"A": "human intelligence", "B": "machine simulation of human intelligence", "C": "computer hardware", "D": "network design"}, "answer": "B"},
    {"stem": "Cloud computing allows users to ______.", "options": {"A": "store data locally", "B": "access data via Internet", "C": "print documents", "D": "scan files"}, "answer": "B"},
    {"stem": "Virtual memory is used to ______.", "options": {"A": "increase RAM capacity", "B": "store files permanently", "C": "display images", "D": "connect networks"}, "answer": "A"},
    {"stem": "Which of the following is an example of an embedded system?", "options": {"A": "Desktop computer", "B": "Washing machine controller", "C": "Laptop", "D": "Server"}, "answer": "B"},
    {"stem": "The binary system uses base ______.", "options": {"A": "2", "B": "8", "C": "10", "D": "16"}, "answer": "A"},
    {"stem": "The hexadecimal system uses base ______.", "options": {"A": "2", "B": "8", "C": "10", "D": "16"}, "answer": "D"},
    {"stem": "Which of the following represents parity check?", "options": {"A": "Error detection method", "B": "Storage method", "C": "Processing method", "D": "Output method"}, "answer": "A"},
    {"stem": "A compiler translates ______.", "options": {"A": "entire program at once", "B": "one line at a time", "C": "machine code to English", "D": "hardware to software"}, "answer": "A"},
    {"stem": "An interpreter translates ______.", "options": {"A": "entire program at once", "B": "line by line", "C": "binary to decimal", "D": "data to information"}, "answer": "B"},
    {"stem": "Which of the following is a low-level language?", "options": {"A": "Python", "B": "Java", "C": "Assembly language", "D": "HTML"}, "answer": "C"},
    {"stem": "A flowchart is used to ______.", "options": {"A": "draw images", "B": "represent algorithms graphically", "C": "store data", "D": "process data"}, "answer": "B"},
    {"stem": "Which of the following best describes multitasking?", "options": {"A": "Running one program at a time", "B": "Running multiple programs simultaneously", "C": "Using multiple computers", "D": "Using multiple users"}, "answer": "B"},
    {"stem": "A device that converts digital signals to analogue signals is called a ______.", "options": {"A": "Switch", "B": "Router", "C": "Modem", "D": "Repeater"}, "answer": "C"},
    {"stem": "The use of computers to perform banking transactions online is called ______.", "options": {"A": "E-learning", "B": "E-commerce", "C": "E-banking", "D": "E-library"}, "answer": "C"},
    {"stem": "The use of computers in education to facilitate teaching and learning is known as ______.", "options": {"A": "E-learning", "B": "E-commerce", "C": "E-banking", "D": "Telemarketing"}, "answer": "A"},
    {"stem": "A password that combines letters, numbers and symbols is considered ______.", "options": {"A": "Weak", "B": "Strong", "C": "Invalid", "D": "Temporary"}, "answer": "B"},
    {"stem": "The ethical principle that requires respecting other people's digital information is ______.", "options": {"A": "Privacy", "B": "Networking", "C": "Programming", "D": "Formatting"}, "answer": "A"},
    {"stem": "Which of the following describes cloud computing?", "options": {"A": "Storing and accessing data via the Internet", "B": "Storing files only on flash drives", "C": "Running programs offline", "D": "Printing documents online"}, "answer": "A"},
    {"stem": "An example of cloud storage service is ______.", "options": {"A": "Google Drive", "B": "Windows Explorer", "C": "BIOS", "D": "Notepad"}, "answer": "A"},
    {"stem": "The BIOS in a computer is responsible for ______.", "options": {"A": "booting the computer hardware", "B": "printing documents", "C": "creating spreadsheets", "D": "connecting to Wi-Fi"}, "answer": "A"},
    {"stem": "The part of the operating system that allows users to interact with the computer is called ______.", "options": {"A": "Interface", "B": "Kernel", "C": "Driver", "D": "Protocol"}, "answer": "A"},
    {"stem": "A spreadsheet program is mainly used for ______.", "options": {"A": "numerical calculations", "B": "typing letters", "C": "browsing websites", "D": "editing pictures"}, "answer": "A"},
    {"stem": "The process of arranging data in a particular order is known as ______.", "options": {"A": "Sorting", "B": "Formatting", "C": "Editing", "D": "Saving"}, "answer": "A"},
]

THEORY = [
    {
        "stem": (
            "Question 1\n"
            "A. Describe three major characteristics of the first generation of computers.\n"
            "B. Explain two technological improvements that distinguish second generation computers from first generation computers.\n"
            "C. Evaluate two ways in which modern (fourth or fifth generation) computers have improved productivity in education or business environments."
        ),
        "marks": Decimal("15.00"),
    },
    {
        "stem": (
            "Question 2\n"
            "A. Explain the term operating system and describe its role as a resource manager.\n"
            "B. Discuss three core functions of an operating system.\n"
            "C. A school computer laboratory experiences frequent system crashes. Suggest three possible causes related to the operating system and propose appropriate solutions."
        ),
        "marks": Decimal("15.00"),
    },
    {
        "stem": (
            "Question 3\n"
            "A. Define a database and a Database Management System (DBMS).\n"
            "B. Explain the following database concepts: Table, Record, Field.\n"
            "C. A school intends to computerize its student records. Design a simple database structure, listing four fields and justifying their inclusion."
        ),
        "marks": Decimal("15.00"),
    },
    {
        "stem": (
            "Question 4\n"
            "A. Differentiate between preventive maintenance and corrective maintenance.\n"
            "B. Describe three common hardware faults in a computer system and explain how each can be resolved.\n"
            "C. Outline three best practices for maintaining computer systems in a school environment."
        ),
        "marks": Decimal("15.00"),
    },
    {
        "stem": (
            "Question 5\n"
            "A. Define Information and Communication Technology (ICT).\n"
            "B. List three applications of ICT in the following sectors: Education, Healthcare, Banking.\n"
            "C. Discuss two challenges facing ICT adoption in developing countries and suggest solutions."
        ),
        "marks": Decimal("15.00"),
    },
    {
        "stem": (
            "Question 6\n"
            "A. Define computer graphics and multimedia.\n"
            "B. Differentiate between vector graphics and bitmap graphics.\n"
            "C. Explain two practical applications of multimedia in education or entertainment.\n"
            "D. State two advantages of using multimedia presentations over text-only presentations."
        ),
        "marks": Decimal("15.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
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
    schedule_end = datetime(2026, 3, 24, 15, 0, tzinfo=lagos)

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
            source_reference=f"SS3-CPS-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS3-CPS-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-CPS-MOCK",
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
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat(),
            "schedule_end": exam.schedule_end.isoformat(),
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
        }
    )


main()
