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


TITLE = "TUE 8:50-9:50 JS1 CCA Second Term Exam"
DESCRIPTION = "JSS1 CULTURAL AND CREATIVE ARTS SECOND TERM EXAMINATION"
BANK_NAME = "JS1 CCA Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:50 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Which of the following is an element of design?", "options": {"A": "Balance", "B": "Line", "C": "Unity", "D": "Rhythm"}, "answer": "B"},
    {"stem": "The principle of design that shows equal visual weight is called ______.", "options": {"A": "Balance", "B": "Colour", "C": "Shape", "D": "Texture"}, "answer": "A"},
    {"stem": "Which of the following is an example of an art material?", "options": {"A": "Paper", "B": "Easel", "C": "Brush holder", "D": "Table"}, "answer": "A"},
    {"stem": "A tool commonly used for cutting paper in art is ______.", "options": {"A": "Brush", "B": "Ruler", "C": "Scissors", "D": "Sponge"}, "answer": "C"},
    {"stem": "Collage is an art technique that involves ______.", "options": {"A": "Carving wood", "B": "Painting pictures", "C": "Drawing with pencil", "D": "Pasting different materials on a surface"}, "answer": "D"},
    {"stem": "Which element of design refers to the lightness or darkness of a colour?", "options": {"A": "Texture", "B": "Tone", "C": "Line", "D": "Shape"}, "answer": "B"},
    {"stem": "Mosaic art is made by arranging ______.", "options": {"A": "pieces of coloured materials", "B": "only paint", "C": "pencil drawings", "D": "clay objects"}, "answer": "A"},
    {"stem": "Which of the following is a natural art material?", "options": {"A": "Plastic", "B": "Nylon", "C": "Leaves", "D": "Glass"}, "answer": "C"},
    {"stem": "Bead making is commonly used to produce ______.", "options": {"A": "Jewellery", "B": "Buildings", "C": "Furniture", "D": "Paintings"}, "answer": "A"},
    {"stem": "The element of design that has length and direction is ______.", "options": {"A": "Shape", "B": "Space", "C": "Line", "D": "Form"}, "answer": "C"},
    {"stem": "Texture in art refers to ______.", "options": {"A": "how an object smells", "B": "how an object feels or appears to feel", "C": "how an object sounds", "D": "how an object tastes"}, "answer": "B"},
    {"stem": "Which of the following is a principle of design?", "options": {"A": "Line", "B": "Colour", "C": "Emphasis", "D": "Shape"}, "answer": "C"},
    {"stem": "Paper mache is made mainly from ______.", "options": {"A": "paper and paste", "B": "cement and sand", "C": "wood and glue", "D": "plastic and water"}, "answer": "A"},
    {"stem": "Which tool is used for applying paint or glue?", "options": {"A": "Brush", "B": "Knife", "C": "Needle", "D": "Hammer"}, "answer": "A"},
    {"stem": "In art, space refers to ______.", "options": {"A": "the colour used", "B": "the empty area around objects", "C": "the texture of objects", "D": "the size of materials"}, "answer": "B"},
    {"stem": "Which principle of design shows movement in an artwork?", "options": {"A": "Rhythm", "B": "Shape", "C": "Colour", "D": "Texture"}, "answer": "A"},
    {"stem": "The element of design that has height and width is called ______.", "options": {"A": "Shape", "B": "Tone", "C": "Texture", "D": "Line"}, "answer": "A"},
    {"stem": "The main material used for bead making is ______.", "options": {"A": "Clay", "B": "Beads", "C": "Stone", "D": "Wood"}, "answer": "B"},
    {"stem": "Equipment used to support drawing boards while drawing is called ______.", "options": {"A": "Easel", "B": "Palette", "C": "Needle", "D": "Sponge"}, "answer": "A"},
    {"stem": "A collage artwork is usually made by ______.", "options": {"A": "Carving wood", "B": "Drawing lines", "C": "Pasting different materials together", "D": "Mixing colours"}, "answer": "C"},
    {"stem": "Which of the following is an example of art equipment?", "options": {"A": "Easel", "B": "Paper", "C": "Paint", "D": "Pencil"}, "answer": "A"},
    {"stem": "The principle that makes an artwork look united is called ______.", "options": {"A": "Unity", "B": "Texture", "C": "Line", "D": "Colour"}, "answer": "A"},
    {"stem": "Small coloured pieces used in mosaic art are called ______.", "options": {"A": "Tesserae", "B": "Threads", "C": "Beads", "D": "Tiles"}, "answer": "A"},
    {"stem": "Which of the following is used to make paste for paper mache?", "options": {"A": "Flour and water", "B": "Sand and cement", "C": "Clay and sand", "D": "Plastic and water"}, "answer": "A"},
    {"stem": "Which element of design deals with colours?", "options": {"A": "Colour", "B": "Space", "C": "Shape", "D": "Texture"}, "answer": "A"},
    {"stem": "Which principle of design deals with size relationship?", "options": {"A": "Proportion", "B": "Rhythm", "C": "Balance", "D": "Unity"}, "answer": "A"},
    {"stem": "Beads can be made from ______.", "options": {"A": "glass or seeds", "B": "water only", "C": "paper only", "D": "cement"}, "answer": "A"},
    {"stem": "Which art tool is used for joining collage materials?", "options": {"A": "Glue", "B": "Brush", "C": "Knife", "D": "Pencil"}, "answer": "A"},
    {"stem": "The arrangement of elements to show importance is called ______.", "options": {"A": "Emphasis", "B": "Texture", "C": "Space", "D": "Line"}, "answer": "A"},
    {"stem": "Which of the following is an artificial art material?", "options": {"A": "Leaves", "B": "Stone", "C": "Paper", "D": "Sand"}, "answer": "C"},
    {"stem": "Mosaic art is commonly used for decoration of ______.", "options": {"A": "walls and floors", "B": "books", "C": "paper drawings", "D": "chalk boards"}, "answer": "A"},
    {"stem": "The element that shows how rough or smooth a surface is called ______.", "options": {"A": "Texture", "B": "Colour", "C": "Line", "D": "Shape"}, "answer": "A"},
    {"stem": "Beads are commonly arranged using ______.", "options": {"A": "thread or wire", "B": "wood", "C": "sand", "D": "stone"}, "answer": "A"},
    {"stem": "Paper mache objects must be ______.", "options": {"A": "painted immediately", "B": "dried before use", "C": "frozen", "D": "boiled"}, "answer": "B"},
    {"stem": "Which of the following is NOT an element of design?", "options": {"A": "Line", "B": "Colour", "C": "Unity", "D": "Shape"}, "answer": "C"},
    {"stem": "The repeated use of elements in design creates ______.", "options": {"A": "Rhythm", "B": "Colour", "C": "Shape", "D": "Texture"}, "answer": "A"},
    {"stem": "A brush is classified as ______.", "options": {"A": "Tool", "B": "Equipment", "C": "Material", "D": "Design"}, "answer": "A"},
    {"stem": "Collage encourages creativity by ______.", "options": {"A": "using only pencils", "B": "combining different materials", "C": "avoiding colour", "D": "drawing only lines"}, "answer": "B"},
    {"stem": "Paper mache is often used to make ______.", "options": {"A": "Masks and models", "B": "Cars", "C": "Buildings", "D": "Metal tools"}, "answer": "A"},
    {"stem": "Art tools should be ______.", "options": {"A": "thrown anywhere", "B": "shared carelessly", "C": "kept and maintained properly", "D": "left on the floor"}, "answer": "C"},
]

THEORY = [
    {"stem": "Define elements of design.\n\nList and explain five elements of design.", "marks": Decimal("10.00")},
    {"stem": "Explain five principles of design.", "marks": Decimal("10.00")},
    {"stem": "Define collage.\n\nMention four materials used in collage making.\n\nState two steps involved in collage making.", "marks": Decimal("10.00")},
    {"stem": "Describe mosaic art and state four materials used in making mosaic.", "marks": Decimal("10.00")},
    {"stem": "Explain paper mache modelling and list the materials used.", "marks": Decimal("10.00")},
    {"stem": "Explain bead making and list four materials or tools used.", "marks": Decimal("10.00")},
]


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="CCA")
    academic_class = AcademicClass.objects.get(code="JS1")
    teacher = User.objects.get(username="noahluka@ndgakuje.org")
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
    schedule_start = datetime(2026, 3, 24, 8, 50, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 9, 50, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 8:50 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 8:50 AM WAT."
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
            source_reference=f"JS1-CCA-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS1-CCA-20260324-TH-{index:02d}",
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
        "paper_code": "JS1-CCA-EXAM",
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
