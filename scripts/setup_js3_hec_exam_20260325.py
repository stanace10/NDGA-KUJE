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


TITLE = "WED 9:45-11:00 JS3 Home Economics Second Term Exam"
DESCRIPTION = "JSS3 HOME ECONOMICS SECOND TERM EXAMINATION"
BANK_NAME = "JS3 Home Economics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 11:00 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Textiles are materials produced mainly from ______.", "options": {"A": "metals", "B": "fibres and yarns", "C": "plastics", "D": "wood"}, "answer": "B"},
    {"stem": "Which of the following is an example of a textile material?", "options": {"A": "Leather shoe", "B": "Plastic bucket", "C": "Cotton cloth", "D": "Aluminium pot"}, "answer": "C"},
    {"stem": "Fibres can best be described as ______.", "options": {"A": "finished garments", "B": "long thin strands used in making yarn", "C": "sewing equipment", "D": "woven fabrics"}, "answer": "B"},
    {"stem": "The process of twisting fibres together to form yarn is known as ______.", "options": {"A": "knitting", "B": "weaving", "C": "spinning", "D": "dyeing"}, "answer": "C"},
    {"stem": "Fabric is formed when yarns are ______.", "options": {"A": "stitched", "B": "dyed", "C": "bleached", "D": "interlaced"}, "answer": "D"},
    {"stem": "One major reason for studying textiles is to ______.", "options": {"A": "reduce clothing production", "B": "understand fabric care and use", "C": "discourage fashion", "D": "waste materials"}, "answer": "B"},
    {"stem": "Textiles are important because they ______.", "options": {"A": "replace food", "B": "cause pollution", "C": "provide clothing and household items", "D": "reduce comfort"}, "answer": "C"},
    {"stem": "Natural fibres are obtained from ______.", "options": {"A": "chemicals", "B": "petroleum", "C": "plastics", "D": "plants and animals"}, "answer": "D"},
    {"stem": "Cotton fibre is obtained from the ______.", "options": {"A": "sheep", "B": "cotton plant", "C": "silkworm", "D": "flax stem"}, "answer": "B"},
    {"stem": "Wool is a fibre obtained from ______.", "options": {"A": "goat", "B": "rabbit", "C": "cow", "D": "sheep"}, "answer": "D"},
    {"stem": "Silk is produced by the ______.", "options": {"A": "flax plant", "B": "cotton plant", "C": "silkworm", "D": "sheep"}, "answer": "C"},
    {"stem": "Nylon is classified as a ______.", "options": {"A": "plant fibre", "B": "animal fibre", "C": "synthetic fibre", "D": "natural fibre"}, "answer": "C"},
    {"stem": "One property of cotton fibre is that it ______.", "options": {"A": "melts easily", "B": "repels water", "C": "absorbs moisture", "D": "is very slippery"}, "answer": "C"},
    {"stem": "Wool is suitable for cold weather because it ______.", "options": {"A": "is shiny", "B": "melts easily", "C": "is light in weight", "D": "retains warmth"}, "answer": "D"},
    {"stem": "The best way to care for textiles is to ______.", "options": {"A": "ignore care labels", "B": "store them when wet", "C": "follow the manufacturer's care instructions", "D": "dry them in fire"}, "answer": "C"},
    {"stem": "Laundering refers to the ______.", "options": {"A": "sewing of garments", "B": "washing and care of clothes", "C": "cutting of fabrics", "D": "dyeing of materials"}, "answer": "B"},
    {"stem": "One main purpose of laundering clothes is to ______.", "options": {"A": "remove dirt and germs", "B": "weaken the fabric", "C": "change fabric colour", "D": "shorten garments"}, "answer": "A"},
    {"stem": "Soap and detergents are mainly used to ______.", "options": {"A": "press clothes", "B": "store clothes", "C": "clean fabrics", "D": "dry clothes"}, "answer": "C"},
    {"stem": "Sorting clothes before washing helps to ______.", "options": {"A": "waste time", "B": "mix colours", "C": "tear fabrics", "D": "prevent colour staining"}, "answer": "D"},
    {"stem": "Proper drying of clothes helps to ______.", "options": {"A": "shrink fabrics", "B": "increase dirt", "C": "prevent mould growth", "D": "weaken fibres"}, "answer": "C"},
    {"stem": "A sewing machine is a device used to ______.", "options": {"A": "measure fabrics", "B": "join fabrics together", "C": "wash clothes", "D": "cut materials"}, "answer": "B"},
    {"stem": "One example of a sewing machine is the ______.", "options": {"A": "industrial knife", "B": "cooking machine", "C": "knitting tool", "D": "hand sewing machine"}, "answer": "D"},
    {"stem": "The needle of a sewing machine is used to ______.", "options": {"A": "hold fabric", "B": "form stitches", "C": "oil the machine", "D": "cut thread"}, "answer": "B"},
    {"stem": "The presser foot helps to ______.", "options": {"A": "hold the fabric firmly during sewing", "B": "change the needle", "C": "wind the bobbin", "D": "cut the fabric"}, "answer": "A"},
    {"stem": "The spool pin carries the ______.", "options": {"A": "bobbin", "B": "upper thread", "C": "needle", "D": "presser foot"}, "answer": "B"},
    {"stem": "Facing in garment construction is used to ______.", "options": {"A": "fasten garments", "B": "cut patterns", "C": "strengthen seams", "D": "finish raw edges"}, "answer": "D"},
    {"stem": "A hem is usually found at the ______.", "options": {"A": "neckline", "B": "sleeve head", "C": "shoulder", "D": "lower edge of a garment"}, "answer": "D"},
    {"stem": "Openings in garments are provided to ______.", "options": {"A": "decorate clothes", "B": "weaken garments", "C": "allow easy wearing", "D": "waste fabric"}, "answer": "C"},
    {"stem": "Buttons, hooks and zippers are examples of ______.", "options": {"A": "seams", "B": "hems", "C": "facings", "D": "fastenings"}, "answer": "D"},
    {"stem": "A seam is formed when ______.", "options": {"A": "garments are washed", "B": "fabrics are ironed", "C": "two pieces of fabric are joined", "D": "fabric is folded"}, "answer": "C"},
    {"stem": "Food hygiene means ______.", "options": {"A": "eating raw food", "B": "cooking food only", "C": "keeping food clean and safe", "D": "storing food anyhow"}, "answer": "C"},
    {"stem": "One reason for practicing food hygiene is to ______.", "options": {"A": "delay meals", "B": "prevent food poisoning", "C": "waste food", "D": "spoil food"}, "answer": "B"},
    {"stem": "Washing hands before handling food helps to ______.", "options": {"A": "add flavour", "B": "reduce appetite", "C": "remove germs", "D": "spoil food"}, "answer": "C"},
    {"stem": "Food contamination occurs when food is ______.", "options": {"A": "properly cooked", "B": "fresh and clean", "C": "refrigerated", "D": "polluted by harmful substances"}, "answer": "D"},
    {"stem": "Which of the following can contaminate food?", "options": {"A": "Clean water", "B": "Refrigerator", "C": "Flies", "D": "Clean utensils"}, "answer": "C"},
    {"stem": "Food poisoning is mainly caused by ______.", "options": {"A": "vitamins", "B": "minerals", "C": "proteins", "D": "microorganisms"}, "answer": "D"},
    {"stem": "A sensory sign of food spoilage is ______.", "options": {"A": "pleasant smell", "B": "fresh taste", "C": "change in colour", "D": "firm texture"}, "answer": "C"},
    {"stem": "Microorganisms grow best in food that is ______.", "options": {"A": "dry and cold", "B": "frozen", "C": "warm and moist", "D": "hot and dry"}, "answer": "C"},
    {"stem": "Proper handling of food helps to ______.", "options": {"A": "spread diseases", "B": "promote good health", "C": "increase contamination", "D": "waste food"}, "answer": "B"},
    {"stem": "Cleaning kitchen utensils after use helps to ______.", "options": {"A": "attract insects", "B": "spoil food", "C": "prevent contamination", "D": "delay cooking"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. (a) Define textiles.\n(b) Give examples of textile materials.", "marks": Decimal('10.00')},
    {"stem": "2. State five reasons for studying textiles.", "marks": Decimal('10.00')},
    {"stem": "3. Write two differences between natural fibres and synthetic fibres, giving one example each.", "marks": Decimal('10.00')},
    {"stem": "4. (a) What is a sewing machine?\n(b) Mention four parts of a sewing machine and their functions.", "marks": Decimal('10.00')},
    {"stem": "5. Explain the following garment construction terms:\n(a) Facing\n(b) Hem\n(c) Opening\n(d) Fastening", "marks": Decimal('10.00')},
    {"stem": "6. (a) Define food hygiene and safety.\n(b) State three reasons for healthy food handling.\n(c) Mention two sources of food contamination.\n(d) State two sensory signs of food spoilage.", "marks": Decimal('10.00')},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="HEC")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="nwachukwu@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 9, 45, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 11, 0, tzinfo=lagos)

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
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 9:45 AM WAT.",
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
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 9:45 AM WAT."
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
            source_reference=f"JS3-HEC-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS3-HEC-20260325-TH-{index:02d}",
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
        "paper_code": "JS3-HEC-EXAM",
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
