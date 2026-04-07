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

TITLE = "WED 8:00-10:30 JS1 Fashion Design and Garment Making Second Term Exam"
DESCRIPTION = "JSS1 FASHION DESIGN AND GARMENT MAKING SECOND TERM EXAMINATION"
BANK_NAME = "JS1 Fashion Design and Garment Making Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 50 minutes. Exam window closes at 10:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Fashion is best defined as ______.", "options": {"A": "all types of clothes", "B": "expensive garments", "C": "popular styles of dressing at a particular time", "D": "traditional clothing only"}, "answer": "C"},
    {"stem": "Fashion changes mainly because of ______.", "options": {"A": "sewing machines", "B": "time, culture, and trends", "C": "weather alone", "D": "population"}, "answer": "B"},
    {"stem": "One importance of fashion is that it ______.", "options": {"A": "wastes money", "B": "encourages pride", "C": "helps people express their personality", "D": "promotes laziness"}, "answer": "C"},
    {"stem": "Fashion contributes to national development by ______.", "options": {"A": "discouraging creativity", "B": "creating employment", "C": "increasing crime", "D": "destroying culture"}, "answer": "B"},
    {"stem": "Clothing refers to ______.", "options": {"A": "changing styles", "B": "garments worn to cover and protect the body", "C": "fashion trends", "D": "decorations"}, "answer": "B"},
    {"stem": "One difference between fashion and clothing is that ______.", "options": {"A": "fashion is permanent", "B": "clothing changes rapidly", "C": "fashion changes while clothing is a basic need", "D": "clothing is seasonal"}, "answer": "C"},
    {"stem": "Which of the following best describes fashion?", "options": {"A": "Permanent", "B": "Temporary", "C": "Unchanging", "D": "Traditional"}, "answer": "B"},
    {"stem": "Early Nigerian fashion was mainly influenced by ______.", "options": {"A": "American movies", "B": "European designers", "C": "culture and tradition", "D": "modern technology"}, "answer": "C"},
    {"stem": "Before colonial rule, Nigerians made clothes mainly from ______.", "options": {"A": "imported fabrics", "B": "nylon materials", "C": "locally produced materials", "D": "synthetic fibres"}, "answer": "C"},
    {"stem": "One traditional attire of the Yoruba people is ______.", "options": {"A": "Isi Agu", "B": "Babariga", "C": "Aso Oke", "D": "Kente"}, "answer": "C"},
    {"stem": "The traditional attire commonly associated with the Igbo is ______.", "options": {"A": "Buba", "B": "George", "C": "Isi Agu", "D": "Kaftan"}, "answer": "C"},
    {"stem": "The Hausa/Fulani traditional attire is known as ______.", "options": {"A": "Wrapper", "B": "Babariga", "C": "Blouse", "D": "Skirt"}, "answer": "B"},
    {"stem": "Traditional attire mainly reflects ______.", "options": {"A": "poverty", "B": "foreign influence", "C": "cultural identity", "D": "modern trends"}, "answer": "C"},
    {"stem": "Cultural festivals influence fashion by ______.", "options": {"A": "discouraging dressing", "B": "promoting traditional clothing", "C": "banning fashion", "D": "reducing creativity"}, "answer": "B"},
    {"stem": "A needle is a sewing tool used for ______.", "options": {"A": "measuring", "B": "cutting", "C": "stitching fabrics together", "D": "pressing"}, "answer": "C"},
    {"stem": "Scissors are used mainly for ______.", "options": {"A": "joining fabrics", "B": "cutting fabrics", "C": "measuring", "D": "pressing seams"}, "answer": "B"},
    {"stem": "The tape rule is used for ______.", "options": {"A": "decoration", "B": "cutting", "C": "measuring body and fabric", "D": "stitching"}, "answer": "C"},
    {"stem": "One proper way of caring for sewing tools is by ______.", "options": {"A": "keeping them on the floor", "B": "cleaning and storing them properly", "C": "washing with water always", "D": "leaving them exposed"}, "answer": "B"},
    {"stem": "Sewing tools should be maintained to ______.", "options": {"A": "increase rust", "B": "avoid damage and injury", "C": "waste money", "D": "reduce their use"}, "answer": "B"},
    {"stem": "One safety rule in the sewing room is ______.", "options": {"A": "running about", "B": "playing with tools", "C": "proper handling of equipment", "D": "eating while sewing"}, "answer": "C"},
    {"stem": "Needles should be kept in a ______.", "options": {"A": "pocket", "B": "mouth", "C": "pin cushion", "D": "bag"}, "answer": "C"},
    {"stem": "When passing scissors to someone, they should be ______.", "options": {"A": "open", "B": "pointed forward", "C": "closed and handle first", "D": "sharp side up"}, "answer": "C"},
    {"stem": "Sewing machines should be handled by ______.", "options": {"A": "untrained persons", "B": "trained users only", "C": "children", "D": "visitors"}, "answer": "B"},
    {"stem": "Fabric refers to ______.", "options": {"A": "finished garment", "B": "cloth material used for sewing", "C": "sewing equipment", "D": "fashion design"}, "answer": "B"},
    {"stem": "Cotton fabric is obtained from ______.", "options": {"A": "animals", "B": "plants", "C": "chemicals", "D": "nylon"}, "answer": "B"},
    {"stem": "Silk is produced from ______.", "options": {"A": "sheep", "B": "cotton plant", "C": "silkworm", "D": "goat"}, "answer": "C"},
    {"stem": "Wool is obtained from ______.", "options": {"A": "cotton", "B": "sheep", "C": "silkworm", "D": "nylon"}, "answer": "B"},
    {"stem": "Nylon is an example of a ______.", "options": {"A": "plant fibre", "B": "animal fibre", "C": "natural fibre", "D": "synthetic fibre"}, "answer": "D"},
    {"stem": "One characteristic of cotton fabric is that it ______.", "options": {"A": "melts easily", "B": "absorbs moisture", "C": "is slippery", "D": "does not crease"}, "answer": "B"},
    {"stem": "Synthetic fabrics are mainly ______.", "options": {"A": "plant-based", "B": "animal-based", "C": "man-made", "D": "natural"}, "answer": "C"},
    {"stem": "Hand stitches are made using ______.", "options": {"A": "sewing machine", "B": "needle and thread", "C": "iron", "D": "scissors"}, "answer": "B"},
    {"stem": "Tacking stitch is mainly used for ______.", "options": {"A": "decoration", "B": "permanent stitching", "C": "temporary holding of fabrics", "D": "embroidery"}, "answer": "C"},
    {"stem": "Hemming stitch is used to ______.", "options": {"A": "join two pieces of fabric", "B": "finish raw edges", "C": "cut cloth", "D": "measure fabric"}, "answer": "B"},
    {"stem": "Running stitch is ______.", "options": {"A": "strong and permanent", "B": "complex", "C": "simple and temporary", "D": "decorative only"}, "answer": "C"},
    {"stem": "Back stitch is stronger than ______.", "options": {"A": "running stitch", "B": "hemming stitch", "C": "tacking stitch", "D": "decorative stitch"}, "answer": "A"},
    {"stem": "One important part of a sewing machine is the ______.", "options": {"A": "needle", "B": "table", "C": "shelf", "D": "box"}, "answer": "A"},
    {"stem": "The function of the sewing machine needle is to ______.", "options": {"A": "cut fabric", "B": "hold fabric", "C": "form stitches", "D": "measure cloth"}, "answer": "C"},
    {"stem": "Threading a sewing machine means ______.", "options": {"A": "cleaning it", "B": "passing thread through the machine correctly", "C": "repairing it", "D": "oiling it"}, "answer": "B"},
    {"stem": "Replacing buttons on clothes is an example of ______.", "options": {"A": "fashion designing", "B": "decoration", "C": "simple repair", "D": "cutting"}, "answer": "C"},
    {"stem": "Mending tears in clothes helps to ______.", "options": {"A": "spoil garments", "B": "waste materials", "C": "extend the life of garments", "D": "reduce value"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Define fashion.\n(b) Write two differences between fashion and clothing.", "marks": Decimal("10.00")},
    {"stem": "2. Mention four Nigerian traditional attires and state the ethnic groups they belong to.", "marks": Decimal("10.00")},
    {"stem": "3. List three basic sewing tools.\n(b) State their functions.", "marks": Decimal("10.00")},
    {"stem": "4. Explain five safety rules in the sewing room.", "marks": Decimal("10.00")},
    {"stem": "5. Identify three types of fabrics.\n(b) State two characteristics of each.", "marks": Decimal("10.00")},
    {"stem": "6. Explain the following:\n1. Basic stitch\n2. Tacking stitch\n3. Hemming stitch\n4. Running stitch\n5. Back stitch", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="FAS")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS1 Fashion assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 25, 20, 0, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 25, 22, 30, 0), lagos)

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
                source_reference=f"JS1-FAS-20260325-OBJ-{index:02d}",
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
                source_reference=f"JS1-FAS-20260325-TH-{index:02d}",
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
            "paper_code": "JS1-FAS-EXAM",
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
