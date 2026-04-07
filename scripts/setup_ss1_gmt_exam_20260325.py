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

TITLE = "WED 8:00-10:30 SS1 Garment Making Second Term Exam"
DESCRIPTION = "SS1 GARMENT MAKING SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Garment Making Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 50 minutes. Exam window closes at 10:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Temporary stitches are mainly used to ______.", "options": {"A": "decorate garments", "B": "hold fabrics in position before permanent stitching", "C": "strengthen seams", "D": "finish raw edges"}, "answer": "B"},
    {"stem": "Which of the following is NOT a temporary stitch?", "options": {"A": "Tacking", "B": "Basting", "C": "Running stitch", "D": "Tailor's tack"}, "answer": "C"},
    {"stem": "Tacking stitches are usually ______.", "options": {"A": "long and loose", "B": "short and firm", "C": "decorative", "D": "elastic"}, "answer": "A"},
    {"stem": "Basting is best used when ______.", "options": {"A": "joining thick fabrics permanently", "B": "holding large fabric pieces together", "C": "decorating garments", "D": "finishing hems"}, "answer": "B"},
    {"stem": "Which stitch is strongest among hand stitches?", "options": {"A": "Running stitch", "B": "Hemming stitch", "C": "Back stitch", "D": "Tacking stitch"}, "answer": "C"},
    {"stem": "The hemming stitch is mainly used to ______.", "options": {"A": "join seams", "B": "hold fullness", "C": "finish edges neatly", "D": "decorate fabric"}, "answer": "C"},
    {"stem": "Straight stitch on the sewing machine is mainly used for ______.", "options": {"A": "embroidery", "B": "joining fabric pieces", "C": "shirring", "D": "smocking"}, "answer": "B"},
    {"stem": "Zigzag stitch is useful for ______.", "options": {"A": "seam finishing and decoration", "B": "dart making", "C": "pleating", "D": "pressing"}, "answer": "A"},
    {"stem": "Decorative stitches are mainly used to ______.", "options": {"A": "strengthen seams", "B": "add beauty to garments", "C": "reduce fullness", "D": "remove excess fabric"}, "answer": "B"},
    {"stem": "Which stitch closely resembles machine stitching?", "options": {"A": "Basting stitch", "B": "Back stitch", "C": "Tacking stitch", "D": "Hemming stitch"}, "answer": "B"},
    {"stem": "A seam is formed when ______.", "options": {"A": "fabric is pressed", "B": "two or more fabrics are joined", "C": "fabric is cut", "D": "raw edges are trimmed"}, "answer": "B"},
    {"stem": "The most common seam used in garment construction is ______.", "options": {"A": "French seam", "B": "Open seam", "C": "Plain seam", "D": "Decorative seam"}, "answer": "C"},
    {"stem": "French seam is suitable for ______.", "options": {"A": "thick fabrics", "B": "transparent and light fabrics", "C": "leather", "D": "denim"}, "answer": "B"},
    {"stem": "An open seam is best finished by ______.", "options": {"A": "enclosing the raw edges", "B": "pressing seam allowances apart", "C": "zigzagging only", "D": "gathering"}, "answer": "B"},
    {"stem": "Overlocked seam finishes help to ______.", "options": {"A": "decorate fabric", "B": "prevent fraying", "C": "hold fullness", "D": "strengthen darts"}, "answer": "B"},
    {"stem": "Which seam gives a neat finish on both sides of the garment?", "options": {"A": "Plain seam", "B": "Open seam", "C": "French seam", "D": "Overlocked seam"}, "answer": "C"},
    {"stem": "Seam finishes are important because they ______.", "options": {"A": "reduce fabric size", "B": "prevent raveling of edges", "C": "add fullness", "D": "remove wrinkles"}, "answer": "B"},
    {"stem": "Which machine is used for overlocking?", "options": {"A": "Straight sewing machine", "B": "Embroidery machine", "C": "Overlocking machine", "D": "Quilting machine"}, "answer": "C"},
    {"stem": "A dart is used mainly to ______.", "options": {"A": "decorate garments", "B": "remove excess fullness", "C": "finish seams", "D": "hold fabric temporarily"}, "answer": "B"},
    {"stem": "Darts are commonly found at the ______.", "options": {"A": "hemline", "B": "neckline", "C": "waist and bust areas", "D": "sleeve edge"}, "answer": "C"},
    {"stem": "A tuck is formed by ______.", "options": {"A": "cutting away fabric", "B": "folding and stitching fabric", "C": "gathering fabric loosely", "D": "pressing fabric only"}, "answer": "B"},
    {"stem": "Tucks serve the purpose of ______.", "options": {"A": "decoration and shaping", "B": "seam finishing", "C": "hemming", "D": "pressing"}, "answer": "A"},
    {"stem": "Gathering is done by using ______.", "options": {"A": "short tight stitches", "B": "long loose stitches", "C": "zigzag stitches", "D": "hemming stitches"}, "answer": "B"},
    {"stem": "Which fullness technique adds fullness to garments?", "options": {"A": "Dart", "B": "Seam", "C": "Gathering", "D": "Pressing"}, "answer": "C"},
    {"stem": "Pleats are ______.", "options": {"A": "random folds", "B": "stitched darts", "C": "evenly folded fabric sections", "D": "gathers with elastic"}, "answer": "C"},
    {"stem": "Knife pleats face ______.", "options": {"A": "opposite directions", "B": "inward", "C": "one direction", "D": "upward"}, "answer": "C"},
    {"stem": "Smocking is best described as ______.", "options": {"A": "seam finishing technique", "B": "decorative embroidery on gathered fabric", "C": "hemming method", "D": "dart technique"}, "answer": "B"},
    {"stem": "Shirring is achieved by using ______.", "options": {"A": "cotton thread", "B": "elastic thread", "C": "silk thread", "D": "nylon thread"}, "answer": "B"},
    {"stem": "Smocking is commonly used on ______.", "options": {"A": "trousers", "B": "children's garments", "C": "jackets", "D": "uniforms"}, "answer": "B"},
    {"stem": "Pressing during garment construction helps to ______.", "options": {"A": "cut fabric accurately", "B": "improve garment shape and appearance", "C": "remove stitches", "D": "add fullness"}, "answer": "B"},
    {"stem": "Pressing should be done ______.", "options": {"A": "only before sewing", "B": "only after sewing", "C": "before, during, and after sewing", "D": "after cutting only"}, "answer": "C"},
    {"stem": "An iron is used to ______.", "options": {"A": "cut fabric", "B": "smooth and shape garments", "C": "mark patterns", "D": "join seams"}, "answer": "B"},
    {"stem": "A pressing cloth is used to ______.", "options": {"A": "decorate garments", "B": "protect fabric from heat damage", "C": "remove stains", "D": "hold seams"}, "answer": "B"},
    {"stem": "A pressing ham is mainly used for pressing ______.", "options": {"A": "straight seams", "B": "flat surfaces", "C": "curved areas", "D": "hems only"}, "answer": "C"},
    {"stem": "Which fabric requires low heat when pressing?", "options": {"A": "Cotton", "B": "Linen", "C": "Silk", "D": "Denim"}, "answer": "C"},
    {"stem": "A handkerchief is usually finished with ______.", "options": {"A": "dart", "B": "French seam", "C": "hemming stitch", "D": "gathering"}, "answer": "C"},
    {"stem": "An apron is mainly used for ______.", "options": {"A": "decoration", "B": "protection of clothes", "C": "sleeping", "D": "warmth"}, "answer": "B"},
    {"stem": "A pillowcase is commonly sewn using ______.", "options": {"A": "plain seam", "B": "dart", "C": "shirring", "D": "smocking"}, "answer": "A"},
    {"stem": "The first step in sewing a simple article is ______.", "options": {"A": "pressing", "B": "hemming", "C": "measuring and marking", "D": "stitching"}, "answer": "C"},
    {"stem": "Good finishing in garment making results in ______.", "options": {"A": "weak garments", "B": "untidy appearance", "C": "durability and neatness", "D": "fabric wastage"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Define temporary stitches.\n(b) List and explain two examples.", "marks": Decimal("10.00")},
    {"stem": "2. Differentiate between temporary stitches and permanent stitches, giving examples.", "marks": Decimal("10.00")},
    {"stem": "3. Explain what a seam is.\n(b) List three types of seams.", "marks": Decimal("10.00")},
    {"stem": "4. Explain pleats, smocking, and shirring, stating one use of any two.", "marks": Decimal("10.00")},
    {"stem": "5. Define the following:\n(a) Iron\n(b) Pressing ham\n(c) Pressing cloth", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by('id').first()
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="GMT")
    assignment = TeacherSubjectAssignment.objects.get(
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    )
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by('-id').first()
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
                source_reference=f"SS1-GMT-20260325-OBJ-{index:02d}",
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
                source_reference=f"SS1-GMT-20260325-TH-{index:02d}",
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
            "paper_code": "SS1-GMT-EXAM",
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




