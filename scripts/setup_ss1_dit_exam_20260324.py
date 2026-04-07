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


TITLE = "TUE 11:20-12:20 SS1 Digital Technology Second Term Exam"
DESCRIPTION = "SS1 DIGITAL TECHNOLOGY SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Digital Technology Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any three questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 55 minutes. Exam window closes at 12:20 PM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "A computer network is best defined as ______.", "options": {"A": "a computer with internet access", "B": "a group of computers connected to share resources", "C": "computers used for communication only", "D": "a system unit with accessories"}, "answer": "B"},
    {"stem": "Which of the following is an example of a Local Area Network (LAN)?", "options": {"A": "The Internet", "B": "A city-wide bank network", "C": "A school computer laboratory", "D": "Satellite communication system"}, "answer": "C"},
    {"stem": "The type of network that covers a town or city is called ______.", "options": {"A": "LAN", "B": "PAN", "C": "MAN", "D": "WAN"}, "answer": "C"},
    {"stem": "A Wide Area Network (WAN) is characterized by ______.", "options": {"A": "very small coverage", "B": "high speed and low cost", "C": "global coverage", "D": "private ownership only"}, "answer": "C"},
    {"stem": "Which of the following is NOT a feature of LAN?", "options": {"A": "High speed", "B": "Low cost", "C": "Covers continents", "D": "Small geographical area"}, "answer": "C"},
    {"stem": "The Internet is an example of ______.", "options": {"A": "LAN", "B": "MAN", "C": "PAN", "D": "WAN"}, "answer": "D"},
    {"stem": "Which device directs data between different networks?", "options": {"A": "Switch", "B": "Router", "C": "NIC", "D": "Hub"}, "answer": "B"},
    {"stem": "A Network Interface Card (NIC) is used to ______.", "options": {"A": "display images", "B": "connect a computer to a network", "C": "store data", "D": "process information"}, "answer": "B"},
    {"stem": "Which transmission medium uses light signals?", "options": {"A": "Twisted pair", "B": "Coaxial cable", "C": "Fibre optic cable", "D": "Copper wire"}, "answer": "C"},
    {"stem": "A server in a network is a computer that ______.", "options": {"A": "receives only", "B": "shares resources", "C": "cannot connect to clients", "D": "is used for typing only"}, "answer": "B"},
    {"stem": "The Internet can best be described as ______.", "options": {"A": "a computer program", "B": "a global system of connected computers", "C": "a search engine", "D": "a browser"}, "answer": "B"},
    {"stem": "Which of the following is an Internet service?", "options": {"A": "Spreadsheet", "B": "Word processing", "C": "Email", "D": "Formatting"}, "answer": "C"},
    {"stem": "The World Wide Web (WWW) allows users to ______.", "options": {"A": "repair computers", "B": "browse web pages", "C": "install hardware", "D": "manage files offline"}, "answer": "B"},
    {"stem": "Which of the following is a search engine?", "options": {"A": "Firefox", "B": "Google", "C": "Chrome", "D": "Edge"}, "answer": "B"},
    {"stem": "A web browser is used to ______.", "options": {"A": "design websites", "B": "search the Internet only", "C": "access and view websites", "D": "send emails only"}, "answer": "C"},
    {"stem": "Which of the following is NOT a browser?", "options": {"A": "Bing", "B": "Chrome", "C": "Firefox", "D": "Edge"}, "answer": "A"},
    {"stem": "Online buying and selling is known as ______.", "options": {"A": "e-learning", "B": "e-commerce", "C": "e-mailing", "D": "e-banking"}, "answer": "B"},
    {"stem": "Email etiquette refers to ______.", "options": {"A": "fast typing", "B": "correct spelling only", "C": "proper and respectful email use", "D": "sending many emails"}, "answer": "C"},
    {"stem": "Which of the following is a rule of email etiquette?", "options": {"A": "Typing in capital letters", "B": "Using unclear subject", "C": "Being polite", "D": "Sending empty emails"}, "answer": "C"},
    {"stem": "Instant messaging allows ______.", "options": {"A": "delayed communication", "B": "printed messages", "C": "real-time communication", "D": "offline messaging"}, "answer": "C"},
    {"stem": "WhatsApp and Telegram are examples of ______.", "options": {"A": "browsers", "B": "search engines", "C": "instant messaging tools", "D": "storage devices"}, "answer": "C"},
    {"stem": "Online conferencing is best used for ______.", "options": {"A": "gaming", "B": "virtual meetings", "C": "data storage", "D": "virus scanning"}, "answer": "B"},
    {"stem": "RAM is an example of ______.", "options": {"A": "secondary storage", "B": "cloud storage", "C": "primary storage", "D": "backup storage"}, "answer": "C"},
    {"stem": "Which of the following is a secondary storage device?", "options": {"A": "ROM", "B": "CPU", "C": "Flash drive", "D": "Cache"}, "answer": "C"},
    {"stem": "Cloud computing means ______.", "options": {"A": "storing data on flash drives", "B": "storing data on remote servers", "C": "installing software only", "D": "printing documents"}, "answer": "B"},
    {"stem": "Google Drive is an example of ______.", "options": {"A": "primary storage", "B": "cloud storage", "C": "system software", "D": "hardware device"}, "answer": "B"},
    {"stem": "One advantage of cloud computing is ______.", "options": {"A": "difficult access", "B": "high cost", "C": "easy data access", "D": "virus infection"}, "answer": "C"},
    {"stem": "Data backup is important because it ______.", "options": {"A": "deletes data", "B": "prevents data loss", "C": "reduces memory", "D": "slows down system"}, "answer": "B"},
    {"stem": "Cybersecurity deals with ______.", "options": {"A": "typing skills", "B": "protecting digital systems", "C": "computer repairs", "D": "printing documents"}, "answer": "B"},
    {"stem": "Which of the following is a cyber threat?", "options": {"A": "Antivirus", "B": "Firewall", "C": "Malware", "D": "Password"}, "answer": "C"},
    {"stem": "Phishing is best described as ______.", "options": {"A": "legal hacking", "B": "fake messages to steal information", "C": "virus removal", "D": "data backup"}, "answer": "B"},
    {"stem": "Hacking involves ______.", "options": {"A": "legal software use", "B": "unauthorized system access", "C": "email writing", "D": "cloud storage"}, "answer": "B"},
    {"stem": "Which is a cybersecurity protection method?", "options": {"A": "Malware", "B": "Virus", "C": "Firewall", "D": "Spam"}, "answer": "C"},
    {"stem": "Strong passwords should ______.", "options": {"A": "be simple", "B": "be shared", "C": "combine letters, numbers, symbols", "D": "be written openly"}, "answer": "C"},
    {"stem": "Data privacy involves ______.", "options": {"A": "sharing personal data", "B": "protecting personal information", "C": "deleting files", "D": "formatting disks"}, "answer": "B"},
    {"stem": "Digital ethics refers to ______.", "options": {"A": "online gaming", "B": "responsible technology use", "C": "hacking skills", "D": "programming"}, "answer": "B"},
    {"stem": "Cyberbullying is ______.", "options": {"A": "online teaching", "B": "online harassment", "C": "online shopping", "D": "online banking"}, "answer": "B"},
    {"stem": "An example of responsible digital behavior is ______.", "options": {"A": "sharing passwords", "B": "insulting others online", "C": "respecting others online", "D": "spreading fake news"}, "answer": "C"},
    {"stem": "Social media platforms allow users to ______.", "options": {"A": "repair computers", "B": "create and share content", "C": "store RAM", "D": "format disks"}, "answer": "B"},
    {"stem": "Facebook and Instagram are examples of ______.", "options": {"A": "browsers", "B": "search engines", "C": "social media platforms", "D": "email services"}, "answer": "C"},
    {"stem": "One benefit of social media is ______.", "options": {"A": "addiction", "B": "privacy risk", "C": "communication", "D": "cybercrime"}, "answer": "C"},
    {"stem": "One risk of social media is ______.", "options": {"A": "learning", "B": "communication", "C": "addiction", "D": "collaboration"}, "answer": "C"},
    {"stem": "Excessive social media use may lead to ______.", "options": {"A": "productivity", "B": "addiction", "C": "data security", "D": "skill development"}, "answer": "B"},
    {"stem": "Which of the following helps prevent cyber threats?", "options": {"A": "Ignoring updates", "B": "Antivirus software", "C": "Weak passwords", "D": "Unknown downloads"}, "answer": "B"},
    {"stem": "A firewall is used to ______.", "options": {"A": "block unauthorized access", "B": "store files", "C": "type documents", "D": "print data"}, "answer": "A"},
    {"stem": "Which action promotes digital safety?", "options": {"A": "Clicking unknown links", "B": "Sharing login details", "C": "Updating security software", "D": "Using public passwords"}, "answer": "C"},
    {"stem": "Online identity theft is related to ______.", "options": {"A": "hardware damage", "B": "data privacy violation", "C": "software installation", "D": "file compression"}, "answer": "B"},
    {"stem": "Data protection laws are meant to ______.", "options": {"A": "control computers", "B": "protect users' personal data", "C": "promote hacking", "D": "delete records"}, "answer": "B"},
    {"stem": "Responsible digital citizenship includes ______.", "options": {"A": "spreading rumors", "B": "respecting online rules", "C": "hacking accounts", "D": "sharing fake news"}, "answer": "B"},
    {"stem": "The main purpose of cybersecurity is to ______.", "options": {"A": "slow networks", "B": "protect digital information", "C": "delete data", "D": "limit internet use"}, "answer": "B"},
]

THEORY = [
    {"stem": "Definition of computer network.\n\nState three differences between LAN and WAN.\n\nGive one example each of LAN and WAN.", "marks": Decimal("10.00")},
    {"stem": "Explain the Internet.\n\nState three Internet services with their uses.\n\nState one importance of the Internet to students.", "marks": Decimal("10.00")},
    {"stem": "What is email etiquette?\n\nState four rules of email etiquette.", "marks": Decimal("10.00")},
    {"stem": "Distinguish between primary and secondary storage.\n\nExplain cloud computing.\n\nState three advantages of cloud computing.", "marks": Decimal("10.00")},
    {"stem": "Define cybersecurity.\n\nExplain three cyber threats.\n\nState two ways cybersecurity protects users.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="DIT")
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
    schedule_start = datetime(2026, 3, 24, 11, 20, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 12, 20, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday mid-morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 11:20 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday mid-morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 11:20 AM WAT."
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
            source_reference=f"SS1-DIT-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS1-DIT-20260324-TH-{index:02d}",
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
        "paper_code": "SS1-DIT-EXAM",
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
