from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

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

TITLE = "THU 8:00-9:30 SS2 Data Processing Second Term Exam"
DESCRIPTION = "SS2 DATA PROCESSING SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Data Processing Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer only three questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "The Internet can best be described as ______.", "options": {"A": "a single large computer", "B": "a global system of interconnected computer networks", "C": "a local area network", "D": "a software package"}, "answer": "B"},
    {"stem": "Which of the following allows computers worldwide to communicate on the Internet?", "options": {"A": "Hardware drivers", "B": "Communication protocols", "C": "Power supply", "D": "Application software"}, "answer": "B"},
    {"stem": "Which of the following is NOT a service provided by the Internet?", "options": {"A": "Email", "B": "Cloud storage", "C": "Desktop publishing", "D": "Social media"}, "answer": "C"},
    {"stem": "A software used to access and view web pages is called ______.", "options": {"A": "Search engine", "B": "Web server", "C": "Internet browser", "D": "Operating system"}, "answer": "C"},
    {"stem": "Which of the following is a web browser?", "options": {"A": "Google", "B": "Yahoo", "C": "Mozilla Firefox", "D": "WhatsApp"}, "answer": "C"},
    {"stem": "One major benefit of the Internet in education is ______.", "options": {"A": "computer virus", "B": "online learning", "C": "hacking", "D": "cyberbullying"}, "answer": "B"},
    {"stem": "Which of the following devices is essential for Internet connection?", "options": {"A": "Scanner", "B": "Modem", "C": "Printer", "D": "Joystick"}, "answer": "B"},
    {"stem": "An Internet Service Provider (ISP) is responsible for ______.", "options": {"A": "designing websites", "B": "providing Internet access", "C": "repairing computers", "D": "writing programs"}, "answer": "B"},
    {"stem": "Fibre optic cable is an example of ______.", "options": {"A": "browser software", "B": "transmission media", "C": "output device", "D": "antivirus"}, "answer": "B"},
    {"stem": "Which of the following is a form of Internet abuse?", "options": {"A": "Online banking", "B": "E-learning", "C": "Cyber fraud", "D": "Video conferencing"}, "answer": "C"},
    {"stem": "Internet security mainly protects users against ______.", "options": {"A": "slow computers", "B": "power failure", "C": "unauthorized access", "D": "large files"}, "answer": "C"},
    {"stem": "Which of these is an antivirus software?", "options": {"A": "Microsoft Word", "B": "Norton Antivirus", "C": "Google Chrome", "D": "PowerPoint"}, "answer": "B"},
    {"stem": "A search engine is mainly used to ______.", "options": {"A": "store files", "B": "type documents", "C": "find information online", "D": "send emails"}, "answer": "C"},
    {"stem": "Which of the following is a search engine?", "options": {"A": "Opera", "B": "Google", "C": "Firefox", "D": "Edge"}, "answer": "B"},
    {"stem": "The first step in searching for information online is to ______.", "options": {"A": "click download", "B": "open a browser", "C": "shut down the system", "D": "open antivirus"}, "answer": "B"},
    {"stem": "Downloading means ______.", "options": {"A": "deleting a file", "B": "copying a file from the Internet to a computer", "C": "printing a file", "D": "opening a website"}, "answer": "B"},
    {"stem": "Which option allows reuse of text from a web page?", "options": {"A": "Delete", "B": "Paste", "C": "Copy", "D": "Save"}, "answer": "C"},
    {"stem": "A presentation package is mainly used to ______.", "options": {"A": "process data", "B": "create slide shows", "C": "browse the Internet", "D": "manage databases"}, "answer": "B"},
    {"stem": "An example of a presentation package is ______.", "options": {"A": "Excel", "B": "PowerPoint", "C": "Access", "D": "Dreamweaver"}, "answer": "B"},
    {"stem": "Which of the following is NOT a use of presentation software?", "options": {"A": "Classroom teaching", "B": "Seminars", "C": "Website hosting", "D": "Business presentation"}, "answer": "C"},
    {"stem": "The title bar in PowerPoint displays ______.", "options": {"A": "slide content", "B": "file name and program name", "C": "animations", "D": "slide number"}, "answer": "B"},
    {"stem": "Slides pane is used to ______.", "options": {"A": "save files", "B": "show list of slides", "C": "print slides", "D": "add animations"}, "answer": "B"},
    {"stem": "Adding new ideas in PowerPoint requires ______.", "options": {"A": "inserting slides", "B": "formatting text", "C": "running slide show", "D": "closing presentation"}, "answer": "A"},
    {"stem": "Design templates in PowerPoint are used to ______.", "options": {"A": "delete slides", "B": "improve appearance", "C": "protect files", "D": "run animations"}, "answer": "B"},
    {"stem": "Changing font size and colour is an example of ______.", "options": {"A": "saving presentation", "B": "formatting text", "C": "slide transition", "D": "publishing"}, "answer": "B"},
    {"stem": "Entrance and exit effects are types of ______.", "options": {"A": "templates", "B": "transitions", "C": "animations", "D": "layouts"}, "answer": "C"},
    {"stem": "Slide transition determines ______.", "options": {"A": "how slides change", "B": "text colour", "C": "font size", "D": "slide content"}, "answer": "A"},
    {"stem": "Files created in PowerPoint are saved with the extension ______.", "options": {"A": ".docx", "B": ".xlsx", "C": ".pptx", "D": ".html"}, "answer": "C"},
    {"stem": "Running a slide show manually requires ______.", "options": {"A": "timer", "B": "mouse click", "C": "printer", "D": "modem"}, "answer": "B"},
    {"stem": "Web design packages are used to ______.", "options": {"A": "process numbers", "B": "create and manage websites", "C": "scan documents", "D": "play music"}, "answer": "B"},
    {"stem": "Which of the following is a web design package?", "options": {"A": "Dreamweaver", "B": "PowerPoint", "C": "Excel", "D": "Access"}, "answer": "A"},
    {"stem": "Navigation structure in web design refers to ______.", "options": {"A": "font colour", "B": "movement between web pages", "C": "image size", "D": "file storage"}, "answer": "B"},
    {"stem": "Effective typography in web design deals with ______.", "options": {"A": "sound effects", "B": "text appearance", "C": "background music", "D": "animations"}, "answer": "B"},
    {"stem": "Adding text and images to a webpage is known as ______.", "options": {"A": "publishing", "B": "formatting", "C": "adding content", "D": "navigation"}, "answer": "C"},
    {"stem": "A hyperlink is used to ______.", "options": {"A": "format text", "B": "connect web pages", "C": "store data", "D": "design slides"}, "answer": "B"},
    {"stem": "Publishing a website means ______.", "options": {"A": "designing it", "B": "editing text", "C": "making it available on the Internet", "D": "deleting pages"}, "answer": "C"},
    {"stem": "Adjusting background and layout belongs to ______.", "options": {"A": "publishing", "B": "page formatting", "C": "navigation", "D": "downloading"}, "answer": "B"},
    {"stem": "Which of the following improves website appearance?", "options": {"A": "Solid layout", "B": "Virus", "C": "Hacking", "D": "Spam"}, "answer": "A"},
    {"stem": "Colour scheme in web design refers to ______.", "options": {"A": "sound pattern", "B": "choice of colours", "C": "number of pages", "D": "hyperlinks"}, "answer": "B"},
    {"stem": "UC Browser is an example of ______.", "options": {"A": "antivirus", "B": "search engine", "C": "web browser", "D": "web server"}, "answer": "C"},
    {"stem": "Which activity is unethical on the Internet?", "options": {"A": "Online research", "B": "Cyberbullying", "C": "E-learning", "D": "Emailing"}, "answer": "B"},
    {"stem": "Internet addiction refers to ______.", "options": {"A": "virus infection", "B": "excessive Internet use", "C": "fast browsing", "D": "online teaching"}, "answer": "B"},
    {"stem": "Which device connects a home network to the Internet?", "options": {"A": "Router", "B": "Monitor", "C": "Keyboard", "D": "Speaker"}, "answer": "A"},
    {"stem": "Animation schemes are applied to ______.", "options": {"A": "hard disk", "B": "slides", "C": "browser", "D": "modem"}, "answer": "B"},
    {"stem": "Copying text from a webpage requires first ______.", "options": {"A": "deleting it", "B": "highlighting it", "C": "saving it", "D": "printing it"}, "answer": "B"},
    {"stem": "A website address is also known as ______.", "options": {"A": "URL", "B": "ISP", "C": "HTML", "D": "WWW"}, "answer": "A"},
    {"stem": "Which of the following helps protect data online?", "options": {"A": "Firewall", "B": "Search engine", "C": "Browser", "D": "Router"}, "answer": "A"},
    {"stem": "The status bar in PowerPoint shows ______.", "options": {"A": "slide information", "B": "file location", "C": "browser history", "D": "animations"}, "answer": "A"},
    {"stem": "Motion paths are used to ______.", "options": {"A": "move objects on slides", "B": "delete slides", "C": "change font", "D": "save files"}, "answer": "A"},
    {"stem": "HTML Pro is mainly used for ______.", "options": {"A": "word processing", "B": "spreadsheet calculation", "C": "web design", "D": "presentation"}, "answer": "C"},
]

THEORY = [
    {"stem": "QUESTION 1\n(a) Define the Internet.\n(b) Explain four major services provided by the Internet.", "marks": Decimal("10.00")},
    {"stem": "QUESTION 2\n(a) What is an Internet browser?\n(b) Describe the steps involved in searching for information on the Internet.\n(c) State four examples of Internet browsers.", "marks": Decimal("10.00")},
    {"stem": "QUESTION 3\n(a) Explain Internet security.\n(b) Discuss four common abuses of the Internet.\n(c) State four measures for safe Internet usage.", "marks": Decimal("10.00")},
    {"stem": "QUESTION 4\n(a) Define a presentation package.\n(b) Explain four uses of presentation packages.\n(c) Describe four components of the PowerPoint interface.", "marks": Decimal("10.00")},
    {"stem": "QUESTION 5\n(a) Explain the term slide animation.\n(b) Describe three types of animations used in PowerPoint.\n(c) Explain the steps involved in creating and saving a presentation.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="DAP")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS2 Data Processing assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 8, 0, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 9, 30, 0), lagos)

    with transaction.atomic():
        bank, _ = QuestionBank.objects.get_or_create(
            name=BANK_NAME,
            subject=subject,
            academic_class=academic_class,
            session=session,
            term=term,
            defaults={"description": DESCRIPTION, "assignment": assignment, "owner": teacher, "is_active": True},
        )
        bank.description = DESCRIPTION
        bank.assignment = assignment
        bank.owner = teacher
        bank.is_active = True
        bank.save()

        exam, created = Exam.objects.get_or_create(
            title=TITLE,
            session=session,
            term=term,
            subject=subject,
            academic_class=academic_class,
            defaults={
                "description": DESCRIPTION,
                "exam_type": CBTExamType.EXAM,
                "status": CBTExamStatus.ACTIVE,
                "created_by": teacher,
                "assignment": assignment,
                "question_bank": bank,
                "schedule_start": schedule_start,
                "schedule_end": schedule_end,
                "is_time_based": True,
                "open_now": False,
            },
        )
        exam.description = DESCRIPTION
        exam.exam_type = CBTExamType.EXAM
        exam.status = CBTExamStatus.ACTIVE
        exam.created_by = teacher
        exam.assignment = assignment
        exam.question_bank = bank
        exam.schedule_start = schedule_start
        exam.schedule_end = schedule_end
        exam.is_time_based = True
        exam.open_now = False
        exam.save()

        exam.exam_questions.all().delete()
        Question.objects.filter(question_bank=bank).delete()

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
                source_reference=f"SS2-DAP-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS2-DAP-20260326-TH-{index:02d}",
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
            "paper_code": "SS2-DAP-EXAM",
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

        print({
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
        })

if __name__ == "__main__":
    main()
