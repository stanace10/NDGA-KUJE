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


TITLE = "TUE 11:00-12:00 JS2 CCA Second Term Exam"
DESCRIPTION = "JSS2 CULTURAL AND CREATIVE ARTS SECOND TERM EXAMINATION"
BANK_NAME = "JS2 CCA Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 12:00 PM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Trinket box is better made by ______.", "options": {"A": "slabbing", "B": "pinching", "C": "drawing", "D": "scooping"}, "answer": "A"},
    {"stem": "The Egyptians originated meaningful letters called ______.", "options": {"A": "vowel", "B": "consonant", "C": "hieroglyphics", "D": "cursive"}, "answer": "C"},
    {"stem": "Which of the following is a quality of good clay?", "options": {"A": "plasticity", "B": "dryness", "C": "gumming", "D": "ageing"}, "answer": "A"},
    {"stem": "The art of constructing letters of the alphabet with the aim of communicating and designing is ______.", "options": {"A": "pattern", "B": "lettering", "C": "schooling", "D": "designing"}, "answer": "B"},
    {"stem": "Graphic art is also called ______.", "options": {"A": "commercial art", "B": "liberal art", "C": "computer art", "D": "non visual art"}, "answer": "A"},
    {"stem": "To construct letter 'A' ______ and ______ lines are used.", "options": {"A": "diagonal and horizontal", "B": "curve and vertical", "C": "vertical and diagonal", "D": "curve and zig zag"}, "answer": "A"},
    {"stem": "One of the following is not a source of funding art.", "options": {"A": "individuals", "B": "government", "C": "non-governmental organization", "D": "executive officer"}, "answer": "D"},
    {"stem": "The art of producing and selling art works at different prices and places is said to be ______.", "options": {"A": "art vendors", "B": "art gallery", "C": "art production", "D": "art marketing"}, "answer": "D"},
    {"stem": "The process of massaging and removing some particles from clay is called ______.", "options": {"A": "kneading", "B": "plastering", "C": "picking", "D": "casting"}, "answer": "A"},
    {"stem": "A liquid substance used in joining clay works is called ______.", "options": {"A": "adhesive", "B": "mud", "C": "gum", "D": "slip"}, "answer": "D"},
    {"stem": "A place where artifacts are displayed for historical purpose is known as ______.", "options": {"A": "gallery", "B": "art studio", "C": "museum", "D": "art shop"}, "answer": "C"},
    {"stem": "Museums perform the following functions EXCEPT ______.", "options": {"A": "acquisition of materials", "B": "production", "C": "research", "D": "preservation of materials"}, "answer": "B"},
    {"stem": "Block letters with cross lines are called ______.", "options": {"A": "serif", "B": "san serif", "C": "italic", "D": "text"}, "answer": "A"},
    {"stem": "______ is another name for one man exhibition.", "options": {"A": "solo exhibition", "B": "mono exhibition", "C": "single exhibition", "D": "duet exhibition"}, "answer": "A"},
    {"stem": "Pinching technique is associated with ______.", "options": {"A": "blacksmithing", "B": "calabash decoration", "C": "leather product", "D": "pottery"}, "answer": "D"},
    {"stem": "The place clay works are fired is called ______.", "options": {"A": "an oven", "B": "a stove", "C": "fire house", "D": "a kiln"}, "answer": "D"},
    {"stem": "The purest or finest form of clay is ______.", "options": {"A": "ball clay", "B": "primary clay", "C": "kaolin", "D": "Indian clay"}, "answer": "C"},
    {"stem": "A design done on wrappers that protect some products is called ______.", "options": {"A": "package design", "B": "shoe design", "C": "cloth design", "D": "paper design"}, "answer": "A"},
    {"stem": "Package designs are usually done on ______.", "options": {"A": "product", "B": "stone", "C": "billboard", "D": "food crop"}, "answer": "A"},
    {"stem": "Artifacts are kept in the ______.", "options": {"A": "gallery", "B": "workshop", "C": "studio", "D": "museum"}, "answer": "D"},
    {"stem": "One of the following is not a step in preparing artworks for exhibition.", "options": {"A": "pricing", "B": "fixing", "C": "mounting", "D": "labeling"}, "answer": "B"},
    {"stem": "A substance sprayed on charcoal or pastel work is known as ______.", "options": {"A": "raid", "B": "gum", "C": "acrylic", "D": "fixative"}, "answer": "D"},
    {"stem": "When white is added to a colour, it is known as ______.", "options": {"A": "blend", "B": "tint", "C": "shade", "D": "shadow"}, "answer": "B"},
    {"stem": "NGO means ______.", "options": {"A": "Northern Great Organization", "B": "Nigeria Greenwich Organization", "C": "National Golf Organization", "D": "Non Government Organization"}, "answer": "D"},
    {"stem": "The art of displaying artworks for people to see and buy is known as ______.", "options": {"A": "elimination", "B": "improvisation", "C": "exhibition", "D": "desecration"}, "answer": "C"},
    {"stem": "The pottery technique that requires the use of machine is ______.", "options": {"A": "coiling", "B": "throwing", "C": "slabbing", "D": "pinching"}, "answer": "B"},
    {"stem": "Spatula is a tool used in ______.", "options": {"A": "ceramics", "B": "graphics", "C": "painting", "D": "weaving"}, "answer": "A"},
    {"stem": "The following techniques can be used in pottery making EXCEPT ______.", "options": {"A": "coiling", "B": "throwing", "C": "stabbing", "D": "smudging"}, "answer": "C"},
    {"stem": "______ is a unit of design.", "options": {"A": "pattern", "B": "drawing", "C": "motif", "D": "painting"}, "answer": "C"},
    {"stem": "______ serves as a major theme in pattern making.", "options": {"A": "motif", "B": "pattern", "C": "packaging", "D": "drawing"}, "answer": "A"},
    {"stem": "The middle man between the artist and the buyer of an artwork is called ______.", "options": {"A": "art dealer", "B": "art vendor", "C": "art collector", "D": "a curator"}, "answer": "A"},
    {"stem": "The oldest museum in Nigeria is that of ______.", "options": {"A": "Esie museum", "B": "Lagos museum", "C": "Benin museum", "D": "Jos museum"}, "answer": "A"},
    {"stem": "Good spacing is essential in lettering for ______.", "options": {"A": "economy of paper", "B": "judicious use of paper", "C": "decoration", "D": "legibility"}, "answer": "D"},
    {"stem": "Another name for calligraphy is ______.", "options": {"A": "type face", "B": "handwriting", "C": "hieroglyphics", "D": "pen"}, "answer": "B"},
    {"stem": "Upper case in lettering is also known as ______.", "options": {"A": "capital letter", "B": "medium letter", "C": "small letter", "D": "types of letter"}, "answer": "A"},
    {"stem": "A room for displaying, exhibiting and sales of art work is ______.", "options": {"A": "art room", "B": "art studio", "C": "gallery", "D": "museum"}, "answer": "C"},
    {"stem": "Which of the following areas is most suitable for marketing art work?", "options": {"A": "banks", "B": "hospitals", "C": "hotels", "D": "museum"}, "answer": "C"},
    {"stem": "An officer that oversees artifacts kept in a museum is known as ______.", "options": {"A": "curator", "B": "painter", "C": "librarian", "D": "rector"}, "answer": "A"},
    {"stem": "Letters without strokes are known as ______ letters.", "options": {"A": "Roman", "B": "serif", "C": "san-serif", "D": "Gothic"}, "answer": "C"},
    {"stem": "Each artwork in an exhibition is called ______.", "options": {"A": "items", "B": "art piece", "C": "exhibit", "D": "displays"}, "answer": "C"},
]

THEORY = [
    {"stem": "Define art exhibition.\n\nList and explain two types of exhibition.\n\nMention four types of repeat pattern.", "marks": Decimal("10.00")},
    {"stem": "What is marketing of artworks?\n\nMention four sources of funding for art business.\n\nList four outlets for marketing artworks.", "marks": Decimal("10.00")},
    {"stem": "State the meaning of lettering.\n\nList and explain two types of lettering.\n\nName four parts of a letter.", "marks": Decimal("10.00")},
    {"stem": "Differentiate between a museum and a gallery.\n\nName four museums in Nigeria.\n\nList four functions of a museum.", "marks": Decimal("10.00")},
    {"stem": "What is clay?\n\nList and explain two types of clay.\n\nMention four methods of molding with clay in pottery.", "marks": Decimal("10.00")},
    {"stem": "Define package design.\n\nState four functions of package design.\n\nWhat is a trade label?", "marks": Decimal("10.00")},
]


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="CCA")
    academic_class = AcademicClass.objects.get(code="JS2")
    teacher = User.objects.get(username="abel@ndgakuje.org")
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
    schedule_start = datetime(2026, 3, 24, 11, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 12, 0, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday late morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 11:00 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday late morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 11:00 AM WAT."
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
            source_reference=f"JS2-CCA-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS2-CCA-20260324-TH-{index:02d}",
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
        "paper_code": "JS2-CCA-EXAM",
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
