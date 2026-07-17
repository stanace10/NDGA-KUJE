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

TITLE = "THU 1:40-2:40 SS2 Food and Nutrition Second Term Exam"
DESCRIPTION = "SS2 FOODS AND NUTRITION SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Food and Nutrition Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in Section A. In Section B, answer any four questions. "
    "Timer is 25 minutes. Exam window closes at 2:40 PM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "1. Which of the following is a type of milk used in cooking?", "options": {"A": "Evaporated milk", "B": "Cocoa powder", "C": "Almond oil", "D": "Margarine"}, "answer": "A"},
    {"stem": "2. Yoghurt is made primarily through:", "options": {"A": "Freezing milk", "B": "Fermentation of milk with bacterial culture", "C": "Adding water to powdered milk", "D": "Boiling milk with sugar"}, "answer": "B"},
    {"stem": "3. Milk is important to our health because it provides:", "options": {"A": "Fiber", "B": "Vitamin C", "C": "Calcium and protein", "D": "Iron"}, "answer": "C"},
    {"stem": "4. Freshwater fish are mostly found in:", "options": {"A": "Salt ponds", "B": "Estuaries only", "C": "Oceans", "D": "Rivers and lakes"}, "answer": "D"},
    {"stem": "5. Which of the following is a sea fish?", "options": {"A": "Tilapia", "B": "Mackerel", "C": "Carp", "D": "Catfish"}, "answer": "B"},
    {"stem": "6. Cooking fish at high temperature for long periods can:", "options": {"A": "Reduce its nutritional value", "B": "Increase vitamins", "C": "Increase moisture only", "D": "Enhance fat content"}, "answer": "A"},
    {"stem": "7. When selecting meat, one should consider:", "options": {"A": "Colour, texture, and smell", "B": "Price only", "C": "Shape of bones", "D": "Weight of packaging"}, "answer": "A"},
    {"stem": "8. Beef is classified as:", "options": {"A": "Processed meat", "B": "Red meat", "C": "Poultry", "D": "White meat"}, "answer": "B"},
    {"stem": "9. Which nutrient is abundant in meat?", "options": {"A": "Protein", "B": "Carbohydrate", "C": "Vitamin A", "D": "Fiber"}, "answer": "A"},
    {"stem": "10. The connective tissue in meat affects:", "options": {"A": "Odor only", "B": "Tenderness and cooking time", "C": "Fat content only", "D": "Colour only"}, "answer": "B"},
    {"stem": "11. Poultry refers to:", "options": {"A": "Chicken, turkey, and ducks", "B": "Cows and goats", "C": "Fish and shellfish", "D": "Red meat only"}, "answer": "A"},
    {"stem": "12. When selecting poultry, you should look for:", "options": {"A": "Firm flesh and fresh smell", "B": "Yellowing skin and soft flesh", "C": "Frozen surface only", "D": "Dry skin and bad odour"}, "answer": "A"},
    {"stem": "13. Common methods of cooking poultry include:", "options": {"A": "Boiling, roasting, frying", "B": "Freezing only", "C": "Dehydration only", "D": "Sun drying only"}, "answer": "A"},
    {"stem": "14. Condiments and seasonings are mainly used to:", "options": {"A": "Improve taste and flavour", "B": "Cook meat", "C": "Preserve foods", "D": "Measure nutrients"}, "answer": "A"},
    {"stem": "15. Which of the following is a local herb?", "options": {"A": "Basil", "B": "Scent leaf", "C": "Thyme", "D": "Rosemary"}, "answer": "B"},
    {"stem": "16. Salt is considered a:", "options": {"A": "Fat", "B": "Condiment", "C": "Spice", "D": "Vitamin"}, "answer": "B"},
    {"stem": "17. Food preservation is important to:", "options": {"A": "Reduce food spoilage and waste", "B": "Make foods colourful", "C": "Increase water content", "D": "Change food taste only"}, "answer": "A"},
    {"stem": "18. One of the indigenous methods of food preservation is:", "options": {"A": "Freezing", "B": "Pasteurization", "C": "Sun drying", "D": "Refrigeration"}, "answer": "C"},
    {"stem": "19. Canning of food involves:", "options": {"A": "Sealing food in containers and heating", "B": "Boiling food for 5 minutes only", "C": "Mixing with salt only", "D": "Fermentation only"}, "answer": "A"},
    {"stem": "20. Storage of food at proper temperature helps to:", "options": {"A": "Reduce bacterial growth", "B": "Increase food weight", "C": "Enhance flavour", "D": "Reduce protein content"}, "answer": "A"},
    {"stem": "21. Butter is an example of:", "options": {"A": "Poultry", "B": "Meat product", "C": "Milk product", "D": "Condiment"}, "answer": "C"},
    {"stem": "22. Fermented milk products include:", "options": {"A": "Cheese and yoghurt", "B": "Ice cream only", "C": "Cream only", "D": "Margarine only"}, "answer": "A"},
    {"stem": "23. Fish should be prepared in ways that:", "options": {"A": "Retain flavour and nutrients", "B": "Remove all fats", "C": "Discard water only", "D": "Increase cooking time"}, "answer": "A"},
    {"stem": "24. One disadvantage of overcooking meat is:", "options": {"A": "Loss of colour", "B": "Toughness and nutrient loss", "C": "Dehydration only", "D": "Change of smell only"}, "answer": "B"},
    {"stem": "25. Protein content in meat is affected by:", "options": {"A": "Colour of meat", "B": "Price", "C": "Storage method", "D": "Shape of meat"}, "answer": "C"},
    {"stem": "26. Herbs commonly used in cooking include:", "options": {"A": "Scent leaf and thyme", "B": "Salt only", "C": "Tomato and onion", "D": "Sugar only"}, "answer": "A"},
    {"stem": "27. Spices are different from herbs because they:", "options": {"A": "Are derived from roots, bark, seeds", "B": "Contain protein", "C": "Are leafy", "D": "Are vitamins"}, "answer": "A"},
    {"stem": "28. Refrigeration helps to:", "options": {"A": "Slow bacterial growth", "B": "Remove fat", "C": "Decrease weight", "D": "Improve taste only"}, "answer": "A"},
    {"stem": "29. Smoking as a preservation method:", "options": {"A": "Adds flavour and prevents spoilage", "B": "Removes protein", "C": "Only colours the meat", "D": "Removes water only"}, "answer": "A"},
    {"stem": "30. Vacuum packing helps to:", "options": {"A": "Reduce oxygen and increase shelf life", "B": "Ferment food", "C": "Cook food", "D": "Expose food to air"}, "answer": "A"},
    {"stem": "31. Milk should be stored at:", "options": {"A": "Low temperature (refrigeration)", "B": "Sunlight", "C": "Room temperature", "D": "High heat"}, "answer": "A"},
    {"stem": "32. Yogurt can improve health by:", "options": {"A": "Providing probiotics", "B": "Increasing sugar only", "C": "Reducing protein", "D": "Increasing fat only"}, "answer": "A"},
    {"stem": "33. Fish retains nutrients better when:", "options": {"A": "Steamed or grilled", "B": "Roasted only", "C": "Deep fried only", "D": "Boiled for long hours"}, "answer": "A"},
    {"stem": "34. Meat quality is indicated by:", "options": {"A": "Colour, texture, marbling, smell", "B": "Packaging", "C": "Weight only", "D": "Price only"}, "answer": "A"},
    {"stem": "35. Poultry should be cooked:", "options": {"A": "Only fried", "B": "To ensure harmful bacteria are destroyed", "C": "Partially only", "D": "Without seasoning"}, "answer": "B"},
    {"stem": "36. Condiments can be:", "options": {"A": "Herbs and spices", "B": "Oils and fats", "C": "Milk and cheese", "D": "Meat and fish"}, "answer": "A"},
    {"stem": "37. Salt, sugar, and spices are examples of:", "options": {"A": "Proteins", "B": "Condiments and seasonings", "C": "Vitamins", "D": "Carbohydrates"}, "answer": "B"},
    {"stem": "38. Canning, freezing, and drying are examples of:", "options": {"A": "Food preparation only", "B": "Food preservation methods", "C": "Cooking methods only", "D": "Fermentation only"}, "answer": "B"},
    {"stem": "39. Tests in foods are important to:", "options": {"A": "Make food colourful", "B": "Taste food", "C": "Measure weight", "D": "Determine nutrient content and quality"}, "answer": "D"},
    {"stem": "40. Food storage helps to:", "options": {"A": "Increase fat", "B": "Reduce spoilage and maintain quality", "C": "Remove water only", "D": "Change taste only"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. (a) Explain the different types of milk and their uses in cooking and baking.\n(b) Describe how yoghurt is made and its importance to human health.", "marks": Decimal('10.00')},
    {"stem": "2. (a) Explain the classification of fish into local and sea fish and their nutritional values.\n(b) Discuss methods of cooking fish to retain nutrients and flavour.", "marks": Decimal('10.00')},
    {"stem": "3. (a) Define meat, types of meat, and factors to consider when selecting meat.\n(b) Describe the structure of meat and how it affects cooking and quality.", "marks": Decimal('10.00')},
    {"stem": "4. (a) Define poultry, its types, and preparation methods.\n(b) Discuss the types of herbs and spices used as condiments and seasonings.", "marks": Decimal('10.00')},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="FDN")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS2 Food and Nutrition assignment found")
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
                source_reference=f"SS2-FDN-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS2-FDN-20260326-TH-{index:02d}",
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
            "paper_code": "SS2-FDN-EXAM",
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
