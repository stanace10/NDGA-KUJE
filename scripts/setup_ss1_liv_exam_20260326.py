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

TITLE = "THU 8:00-9:30 SS1 Livestock Farming Second Term Exam"
DESCRIPTION = "SS1 LIVESTOCK FARMING SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Livestock Farming Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Livestock production refers to the rearing of animals mainly for ______.", "options": {"A": "fun", "B": "companionship", "C": "food and income", "D": "research"}, "answer": "C"},
    {"stem": "Which of the following is NOT a livestock animal?", "options": {"A": "Goat", "B": "Cattle", "C": "Poultry", "D": "Lizard"}, "answer": "D"},
    {"stem": "One major importance of livestock production is the provision of ______.", "options": {"A": "shelter", "B": "manure", "C": "fuel", "D": "timber"}, "answer": "B"},
    {"stem": "Which of these animals is a ruminant?", "options": {"A": "Pig", "B": "Goat", "C": "Rabbit", "D": "Poultry"}, "answer": "B"},
    {"stem": "The process of keeping animals for commercial purposes is called ______.", "options": {"A": "domestication", "B": "livestock production", "C": "grazing", "D": "breeding"}, "answer": "B"},
    {"stem": "One major challenge of livestock production in Nigeria is ______.", "options": {"A": "good roads", "B": "disease outbreak", "C": "improved breeds", "D": "mechanization"}, "answer": "B"},
    {"stem": "Which of the following diseases affects livestock production?", "options": {"A": "Malaria", "B": "Tuberculosis", "C": "Foot and mouth disease", "D": "Cholera"}, "answer": "C"},
    {"stem": "Poor feeding leads to ______.", "options": {"A": "high productivity", "B": "rapid growth", "C": "malnutrition", "D": "good health"}, "answer": "C"},
    {"stem": "Which of the following is a climatic challenge in livestock production?", "options": {"A": "Theft", "B": "Drought", "C": "Poor management", "D": "Diseases"}, "answer": "B"},
    {"stem": "Livestock feed is best described as ______.", "options": {"A": "water only", "B": "food given to animals", "C": "drugs for animals", "D": "shelter for animals"}, "answer": "B"},
    {"stem": "The ability of an animal to reproduce is called ______.", "options": {"A": "fertility", "B": "longevity", "C": "adaptability", "D": "productivity"}, "answer": "A"},
    {"stem": "A male cattle is called ______.", "options": {"A": "cow", "B": "bull", "C": "heifer", "D": "calf"}, "answer": "B"},
    {"stem": "A young goat is known as ______.", "options": {"A": "kid", "B": "calf", "C": "lamb", "D": "foal"}, "answer": "A"},
    {"stem": "The female goat is called ______.", "options": {"A": "ram", "B": "ewe", "C": "doe", "D": "sow"}, "answer": "C"},
    {"stem": "The act of choosing good animals for breeding is called ______.", "options": {"A": "crossbreeding", "B": "selection", "C": "feeding", "D": "weaning"}, "answer": "B"},
    {"stem": "One factor to consider in breed selection is ______.", "options": {"A": "colour of pen", "B": "availability of water", "C": "adaptability to environment", "D": "size of farm house"}, "answer": "C"},
    {"stem": "A good breed should be ______.", "options": {"A": "aggressive", "B": "slow growing", "C": "disease resistant", "D": "weak"}, "answer": "C"},
    {"stem": "The White Fulani is a breed of ______.", "options": {"A": "goat", "B": "sheep", "C": "cattle", "D": "pig"}, "answer": "C"},
    {"stem": "Sokoto Red is a popular breed of ______.", "options": {"A": "cattle", "B": "goat", "C": "sheep", "D": "poultry"}, "answer": "B"},
    {"stem": "West African Dwarf is a breed of ______.", "options": {"A": "goat", "B": "cattle", "C": "pig", "D": "horse"}, "answer": "A"},
    {"stem": "Livestock nutrition deals with ______.", "options": {"A": "animal housing", "B": "feeding and nourishment of animals", "C": "breeding methods", "D": "animal diseases"}, "answer": "B"},
    {"stem": "Which nutrient provides energy?", "options": {"A": "Protein", "B": "Minerals", "C": "Carbohydrate", "D": "Vitamins"}, "answer": "C"},
    {"stem": "Vitamins help in ______.", "options": {"A": "bone formation only", "B": "growth regulation and disease resistance", "C": "energy supply", "D": "fat storage"}, "answer": "B"},
    {"stem": "Roughages are feeds that contain ______.", "options": {"A": "high fibre", "B": "no fibre", "C": "no water", "D": "drugs"}, "answer": "A"},
    {"stem": "An example of roughage is ______.", "options": {"A": "maize grain", "B": "groundnut cake", "C": "hay", "D": "fish meal"}, "answer": "C"},
    {"stem": "Concentrates are feeds that ______.", "options": {"A": "contain much fibre", "B": "have low nutrients", "C": "are rich in nutrients", "D": "are only for poultry"}, "answer": "C"},
    {"stem": "An example of concentrate feed is ______.", "options": {"A": "grass", "B": "silage", "C": "maize", "D": "straw"}, "answer": "C"},
    {"stem": "Which feed is best for ruminants?", "options": {"A": "concentrates only", "B": "roughages", "C": "vitamins only", "D": "water only"}, "answer": "B"},
    {"stem": "Water is important to livestock because it ______.", "options": {"A": "increases disease", "B": "aids digestion", "C": "reduces growth", "D": "causes fatigue"}, "answer": "B"},
    {"stem": "Which of the following is NOT a class of livestock feed?", "options": {"A": "Roughages", "B": "Concentrates", "C": "Supplements", "D": "Vaccines"}, "answer": "D"},
    {"stem": "Feed supplements are given to ______.", "options": {"A": "replace water", "B": "improve feed quality", "C": "cure diseases", "D": "increase housing space"}, "answer": "B"},
    {"stem": "Crossbreeding involves ______.", "options": {"A": "mating animals of same breed", "B": "mating animals of different breeds", "C": "feeding animals together", "D": "housing animals together"}, "answer": "B"},
    {"stem": "A cow that has not calved before is called ______.", "options": {"A": "heifer", "B": "calf", "C": "bull", "D": "steer"}, "answer": "A"},
    {"stem": "The male goat used for breeding is called ______.", "options": {"A": "buck", "B": "ram", "C": "boar", "D": "bull"}, "answer": "A"},
    {"stem": "One advantage of livestock production is ______.", "options": {"A": "unemployment", "B": "protein supply", "C": "soil erosion", "D": "deforestation"}, "answer": "B"},
    {"stem": "A major constraint to livestock production in rural areas is ______.", "options": {"A": "veterinary services", "B": "poor transportation", "C": "improved breeds", "D": "extension services"}, "answer": "B"},
    {"stem": "An example of leguminous forage is ______.", "options": {"A": "elephant grass", "B": "guinea grass", "C": "centrosema", "D": "straw"}, "answer": "C"},
    {"stem": "Which feed class helps in bone formation?", "options": {"A": "carbohydrates", "B": "fats", "C": "minerals", "D": "water"}, "answer": "C"},
    {"stem": "Which nutrient helps animals fight diseases?", "options": {"A": "vitamins", "B": "carbohydrates", "C": "fats", "D": "water"}, "answer": "A"},
    {"stem": "Feed given to young animals to stop suckling is called ______.", "options": {"A": "creep feed", "B": "roughage", "C": "supplement", "D": "silage"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. Explain extensive and intensive system of livestock production.\n(b) State four importance of livestock production.", "marks": Decimal("10.00")},
    {"stem": "2. List and explain five challenges facing livestock production in Nigeria.", "marks": Decimal("10.00")},
    {"stem": "3. Explain the meaning of breed and state four factors to consider when selecting a breed of livestock.", "marks": Decimal("10.00")},
    {"stem": "4. Write short notes on the following livestock terminologies:\n(a) serving\n(b) doe\n(c) steer\n(d) heifer\n(e) gestation", "marks": Decimal("10.00")},
    {"stem": "5. (a) List four sources of protein in livestock feed.\n(b) State four functions of protein.", "marks": Decimal("10.00")},
    {"stem": "6. Write two breeds of the following animals each:\nI. Cattle\nII. Goat\nIII. Sheep\nIV. Rabbit\nV. Poultry", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="LIV")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS1 Livestock assignment found")
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
                source_reference=f"SS1-LIV-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS1-LIV-20260326-TH-{index:02d}",
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
            "paper_code": "SS1-LIV-EXAM",
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
