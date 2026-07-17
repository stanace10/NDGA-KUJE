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

TITLE = "THU 1:40-2:40 SS1 Food and Nutrition Second Term Exam"
DESCRIPTION = "SS1 FOODS AND NUTRITION SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Food and Nutrition Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in Section A. In Section B, answer any four questions. "
    "Timer is 25 minutes. Exam window closes at 2:40 PM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "1. The study of foods in a scientific way includes:", "options": {"A": "Taste and smell only", "B": "Measurements, units, and nutrient weights", "C": "Cooking with fire only", "D": "Buying food from the market"}, "answer": "B"},
    {"stem": "2. Which of the following tools is used to measure liquids accurately in food preparation?", "options": {"A": "Knife", "B": "Measuring cup", "C": "Frying pan", "D": "Grater"}, "answer": "B"},
    {"stem": "3. Accuracy in food weighing is important because it:", "options": {"A": "Reduces waste and ensures proper nutrition", "B": "Increases cooking time", "C": "Changes the taste of food", "D": "Only affects the colour of food"}, "answer": "A"},
    {"stem": "4. Nutrient weight refers to:", "options": {"A": "The quantity of food sold in the market", "B": "The amount of nutrients present in a given food", "C": "The total weight of the food container", "D": "The weight of the chef"}, "answer": "B"},
    {"stem": "5. Which of the following is an energy-giving nutrient?", "options": {"A": "Protein", "B": "Carbohydrate", "C": "Vitamin C", "D": "Water"}, "answer": "B"},
    {"stem": "6. Which nutrient is most affected by heat during cooking?", "options": {"A": "Water", "B": "Minerals", "C": "Vitamins", "D": "Fibre"}, "answer": "C"},
    {"stem": "7. Boiling milk for too long may reduce its content of:", "options": {"A": "Carbohydrates", "B": "Proteins and vitamins", "C": "Water", "D": "Minerals"}, "answer": "B"},
    {"stem": "8. Which test is used to detect the presence of protein in a food sample?", "options": {"A": "Iodine test", "B": "Sudan III test", "C": "Biuret test", "D": "Litmus test"}, "answer": "C"},
    {"stem": "9. The Million test is used to test for:", "options": {"A": "Fats", "B": "Carbohydrates", "C": "Proteins", "D": "Minerals"}, "answer": "C"},
    {"stem": "10. The coagulation test for protein involves:", "options": {"A": "Heating the protein solution", "B": "Adding iodine", "C": "Mixing with ethanol", "D": "Measuring weight"}, "answer": "A"},
    {"stem": "11. The iodine test is used to detect:", "options": {"A": "Protein", "B": "Starch", "C": "Fat", "D": "Vitamin C"}, "answer": "B"},
    {"stem": "12. Blue-black colour in the iodine test indicates:", "options": {"A": "Protein is present", "B": "Starch is present", "C": "Fat is present", "D": "Vitamin is present"}, "answer": "B"},
    {"stem": "13. Litmus paper can be used to test for:", "options": {"A": "Carbohydrates", "B": "Sugar and acidity", "C": "Protein only", "D": "Minerals"}, "answer": "B"},
    {"stem": "14. Which of the following is a test for fats?", "options": {"A": "Sudan III test", "B": "Form test", "C": "Biuret test", "D": "Iodine test"}, "answer": "A"},
    {"stem": "15. A translucent spot on brown paper indicates:", "options": {"A": "Protein", "B": "Carbohydrate", "C": "Fat or oil", "D": "Vitamin"}, "answer": "C"},
    {"stem": "16. Ethanol test is used to detect:", "options": {"A": "Carbohydrates", "B": "Fats and oils", "C": "Protein", "D": "Minerals"}, "answer": "B"},
    {"stem": "17. Digestion is defined as:", "options": {"A": "The production of energy from exercise", "B": "The breakdown of food into absorbable substances", "C": "Cooking food using heat", "D": "Eating large quantities of food"}, "answer": "B"},
    {"stem": "18. The enzyme found in saliva is:", "options": {"A": "Lipase", "B": "Pepsin", "C": "Ptyalin (salivary amylase)", "D": "Rennin"}, "answer": "C"},
    {"stem": "19. The small intestine is mainly responsible for:", "options": {"A": "Storage of food", "B": "Absorption of nutrients", "C": "Mechanical digestion", "D": "Production of saliva"}, "answer": "B"},
    {"stem": "20. Which of the following is an accessory organ of the digestive system?", "options": {"A": "Stomach", "B": "Oesophagus", "C": "Liver", "D": "Small intestine"}, "answer": "C"},
    {"stem": "21. Metabolism includes:", "options": {"A": "Digestion, absorption, and utilization of nutrients", "B": "Only digestion of food", "C": "Cooking food at high temperature", "D": "Storage of food"}, "answer": "A"},
    {"stem": "22. The organ where chemical digestion of protein begins is:", "options": {"A": "Mouth", "B": "Stomach", "C": "Small intestine", "D": "Oesophagus"}, "answer": "B"},
    {"stem": "23. Reproductive health can be promoted by:", "options": {"A": "Eating balanced meals", "B": "Avoiding exercise", "C": "Sleeping less", "D": "Consuming junk food"}, "answer": "A"},
    {"stem": "24. The female reproductive organ where fertilization occurs is:", "options": {"A": "Uterus", "B": "Ovary", "C": "Fallopian tube", "D": "Vagina"}, "answer": "C"},
    {"stem": "25. Testes in males are responsible for:", "options": {"A": "Producing urine", "B": "Producing sperm and testosterone", "C": "Digestion of proteins", "D": "Storing nutrients"}, "answer": "B"},
    {"stem": "26. A well-planned kitchen saves:", "options": {"A": "Money and energy", "B": "Time, energy, and reduces fatigue", "C": "Food only", "D": "Water only"}, "answer": "B"},
    {"stem": "27. One factor affecting kitchen size is:", "options": {"A": "Colour of walls", "B": "Family size", "C": "Type of floors", "D": "Type of clothes"}, "answer": "B"},
    {"stem": "28. The kitchen work triangle connects:", "options": {"A": "Sink, cooker, refrigerator", "B": "Stove, shelf, table", "C": "Cooker, oven, fridge", "D": "Refrigerator, blender, sink"}, "answer": "A"},
    {"stem": "29. Large kitchen equipment includes:", "options": {"A": "Knife and spatula", "B": "Refrigerator and cooker", "C": "Whisk and sieve", "D": "Grater and peeler"}, "answer": "B"},
    {"stem": "30. Factors to consider when selecting kitchen equipment include:", "options": {"A": "Purpose, cost, durability", "B": "Colour, shape, smell", "C": "Brand only", "D": "Material only"}, "answer": "A"},
    {"stem": "31. Small kitchen utensils include:", "options": {"A": "Refrigerator, cooker", "B": "Knife, spatula, whisk", "C": "Oven, blender", "D": "Stove, sink"}, "answer": "B"},
    {"stem": "32. Labour-saving devices:", "options": {"A": "Increase fatigue", "B": "Reduce effort in cooking", "C": "Increase cooking time", "D": "Are unnecessary in small kitchens"}, "answer": "B"},
    {"stem": "33. Peeler is used for:", "options": {"A": "Chopping meat", "B": "Removing skin from vegetables", "C": "Cutting fat", "D": "Measuring ingredients"}, "answer": "B"},
    {"stem": "34. Measuring cups are used for:", "options": {"A": "Cutting", "B": "Weighing solid foods", "C": "Measuring liquids accurately", "D": "Serving food"}, "answer": "C"},
    {"stem": "35. Care of kitchen utensils includes:", "options": {"A": "Using only once", "B": "Washing and storing properly", "C": "Burning after use", "D": "Ignoring cleaning"}, "answer": "B"},
    {"stem": "36. Proteins are detected by:", "options": {"A": "Sudan III test", "B": "Iodine test", "C": "Form test", "D": "Litmus paper test"}, "answer": "C"},
    {"stem": "37. Vitamins are mainly affected by:", "options": {"A": "Refrigeration", "B": "Exposure to heat and sunlight", "C": "Cutting", "D": "Boiling water only"}, "answer": "B"},
    {"stem": "38. Absorption of nutrients mainly occurs in:", "options": {"A": "Large intestine", "B": "Small intestine", "C": "Stomach", "D": "Mouth"}, "answer": "B"},
    {"stem": "39. The main function of the liver in digestion is:", "options": {"A": "Produces bile to emulsify fats", "B": "Stores water", "C": "Absorbs sugar", "D": "Kills enzymes"}, "answer": "A"},
    {"stem": "40. Laboratory test for starch is:", "options": {"A": "Biuret test", "B": "Form test", "C": "Iodine test", "D": "Sudan III test"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. (a) Define the scientific study of foods and explain why it is important in Food and Nutrition.\n(b) Explain the effects of heat on carbohydrates, proteins, fats, and vitamins.", "marks": Decimal('10.00')},
    {"stem": "2. (a) Describe the tests used to identify proteins in foods.\n(b) Explain how fats and oils are detected in foods.", "marks": Decimal('10.00')},
    {"stem": "3. (a) Describe the processes of digestion, absorption, and utilization of nutrients.\n(b) Discuss the functions of enzymes in the digestive system.", "marks": Decimal('10.00')},
    {"stem": "4. (a) Describe male and female reproductive organs and their functions.\n(b) Explain the relationship between nutrition and reproductive health.", "marks": Decimal('10.00')},
    {"stem": "5. (a) Explain the factors affecting the size of a kitchen and advantages of a well-planned kitchen.\n(b) Discuss the selection and care of kitchen equipment and small utensils.", "marks": Decimal('10.00')},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="FDN")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS1 Food and Nutrition assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 13, 40, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 14, 40, 0), lagos)

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
                source_reference=f"SS1-FDN-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS1-FDN-20260326-TH-{index:02d}",
                is_active=True,
            )
            CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
            sort_order += 1

        blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
        blueprint.duration_minutes = 25
        blueprint.max_attempts = 1
        blueprint.shuffle_questions = True
        blueprint.shuffle_options = True
        blueprint.instructions = INSTRUCTIONS
        blueprint.section_config = {
            "paper_code": "SS1-FDN-EXAM",
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
