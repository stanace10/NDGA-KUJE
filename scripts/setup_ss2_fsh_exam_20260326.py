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

TITLE = "THU 9:30-11:30 SS2 Fishery Second Term Exam"
DESCRIPTION = "FISHERIES SS2 SECOND TERM EXAM"
BANK_NAME = "SS2 Fishery Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all questions in section A. In section B, answer all questions. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "1. Fish feed refers to", "options": {"A": "Water given to fish", "B": "Food provided for fish growth", "C": "Medicine for fish", "D": "Shelter for fish"}, "answer": "B"},
    {"stem": "2. Fish require feed mainly for", "options": {"A": "Decoration", "B": "Growth and energy", "C": "Changing water colour", "D": "Heating ponds"}, "answer": "B"},
    {"stem": "3. Which of the following is a natural fish feed?", "options": {"A": "Plankton", "B": "Cement", "C": "Plastic", "D": "Sand"}, "answer": "A"},
    {"stem": "4. An example of artificial fish feed is", "options": {"A": "Algae", "B": "Insects", "C": "Formulated pellets", "D": "Zooplankton"}, "answer": "C"},
    {"stem": "5. The main nutrient needed for fish growth is", "options": {"A": "Protein", "B": "Water", "C": "Sand", "D": "Salt"}, "answer": "A"},
    {"stem": "6. Fish feed that floats on water is called", "options": {"A": "Floating feed", "B": "Sinking feed", "C": "Wet feed", "D": "Powder feed"}, "answer": "A"},
    {"stem": "7. Which ingredient is commonly used in fish feed?", "options": {"A": "Cassava peel", "B": "Fish meal", "C": "Sand", "D": "Stone"}, "answer": "B"},
    {"stem": "8. Feeding fish too much may lead to", "options": {"A": "Fast swimming", "B": "Water pollution", "C": "Clear water", "D": "Fish reproduction"}, "answer": "B"},
    {"stem": "9. Nutritive value of feed refers to", "options": {"A": "Taste of feed", "B": "Colour of feed", "C": "Nutrients present in feed", "D": "Size of feed"}, "answer": "C"},
    {"stem": "10. Which nutrient supplies energy to fish?", "options": {"A": "Carbohydrates", "B": "Sand", "C": "Iron", "D": "Gravel"}, "answer": "A"},
    {"stem": "11. Vitamins in fish feed help in", "options": {"A": "Disease prevention", "B": "Water heating", "C": "Pond construction", "D": "Fish catching"}, "answer": "A"},
    {"stem": "12. Minerals in fish feed help in", "options": {"A": "Bone formation", "B": "Water movement", "C": "Feeding speed", "D": "Pond digging"}, "answer": "A"},
    {"stem": "13. A fish pond is", "options": {"A": "A natural forest", "B": "An artificial water body for fish culture", "C": "A fishing net", "D": "A fish market"}, "answer": "B"},
    {"stem": "14. The most common type of fish pond is", "options": {"A": "Concrete pond", "B": "Earthen pond", "C": "Plastic pond", "D": "Wooden pond"}, "answer": "B"},
    {"stem": "15. A concrete pond is made with", "options": {"A": "Soil", "B": "Cement and blocks", "C": "Clay only", "D": "Sand only"}, "answer": "B"},
    {"stem": "16. A tarpaulin pond is made from", "options": {"A": "Iron sheets", "B": "Plastic material", "C": "Wood", "D": "Glass"}, "answer": "B"},
    {"stem": "17. One advantage of earthen ponds is", "options": {"A": "Natural food production", "B": "High cost", "C": "Difficult maintenance", "D": "Poor drainage"}, "answer": "A"},
    {"stem": "18. Which of these is a fish culturing facility?", "options": {"A": "Hatchery", "B": "Classroom", "C": "Farm house", "D": "Warehouse"}, "answer": "A"},
    {"stem": "19. A cage culture system is practiced in", "options": {"A": "Rivers and lakes", "B": "Desert", "C": "Forest", "D": "Mountains"}, "answer": "A"},
    {"stem": "20. Tanks used for fish culture are usually made of", "options": {"A": "Cement or plastic", "B": "Paper", "C": "Cloth", "D": "Leaves"}, "answer": "A"},
    {"stem": "21. One component of a fish pond is", "options": {"A": "Inlet", "B": "Window", "C": "Door", "D": "Fence"}, "answer": "A"},
    {"stem": "22. The inlet in a pond allows", "options": {"A": "Fish to escape", "B": "Water to enter", "C": "Feed to dissolve", "D": "Nets to pass"}, "answer": "B"},
    {"stem": "23. The outlet in a pond is used to", "options": {"A": "Remove water", "B": "Add fish", "C": "Store feed", "D": "Build walls"}, "answer": "A"},
    {"stem": "24. The pond dike is the", "options": {"A": "Pond wall", "B": "Pond water", "C": "Pond feed", "D": "Pond fish"}, "answer": "A"},
    {"stem": "25. Pond bottom is important because it", "options": {"A": "Supports pond water and fish", "B": "Holds buildings", "C": "Produces electricity", "D": "Stores nets"}, "answer": "A"},
    {"stem": "26. Fish culture system refers to", "options": {"A": "Method of growing fish", "B": "Method of catching fish", "C": "Method of selling fish", "D": "Method of cooking fish"}, "answer": "A"},
    {"stem": "27. Culture of one species of fish in a pond is called", "options": {"A": "Polyculture", "B": "Monoculture", "C": "Mixed farming", "D": "Rotation"}, "answer": "B"},
    {"stem": "28. Growing different species of fish together is called", "options": {"A": "Monoculture", "B": "Polyculture", "C": "Agriculture", "D": "Irrigation"}, "answer": "B"},
    {"stem": "29. Intensive fish culture involves", "options": {"A": "High stocking and feeding", "B": "No feeding", "C": "No fish", "D": "Fishing only"}, "answer": "A"},
    {"stem": "30. Extensive culture system uses", "options": {"A": "Natural food mostly", "B": "Heavy feeding only", "C": "Chemicals only", "D": "Nets only"}, "answer": "A"},
    {"stem": "31. Water quality refers to", "options": {"A": "Colour of water only", "B": "Condition of water for fish survival", "C": "Quantity of water only", "D": "Depth of pond only"}, "answer": "B"},
    {"stem": "32. Dissolved oxygen in water is needed for", "options": {"A": "Fish breathing", "B": "Fish colour", "C": "Fish size", "D": "Fish selling"}, "answer": "A"},
    {"stem": "33. Poor water quality may cause", "options": {"A": "Healthy fish", "B": "Fish death", "C": "Fast growth", "D": "Clean ponds"}, "answer": "B"},
    {"stem": "34. Water temperature affects", "options": {"A": "Fish growth and survival", "B": "Pond colour only", "C": "Pond shape", "D": "Pond size"}, "answer": "A"},
    {"stem": "35. Clear water with moderate plankton is", "options": {"A": "Good for fish culture", "B": "Bad for fish culture", "C": "Dangerous for fish", "D": "Useless for fish"}, "answer": "A"},
    {"stem": "36. Too much organic waste in water causes", "options": {"A": "Pollution", "B": "Clear water", "C": "Fish happiness", "D": "Pond strength"}, "answer": "A"},
    {"stem": "37. Aeration helps to increase", "options": {"A": "Oxygen in water", "B": "Sand in water", "C": "Mud in water", "D": "Stones in water"}, "answer": "A"},
    {"stem": "38. Regular water exchange helps to", "options": {"A": "Improve water quality", "B": "Reduce fish size", "C": "Kill fish", "D": "Break ponds"}, "answer": "A"},
    {"stem": "39. Overcrowding fish in a pond may lead to", "options": {"A": "Competition for food", "B": "Faster growth", "C": "Clean water", "D": "Strong ponds"}, "answer": "A"},
    {"stem": "40. Good pond management helps to", "options": {"A": "Increase fish production", "B": "Reduce fish growth", "C": "Pollute water", "D": "Destroy ponds"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. Fish Feed.\n• Meaning of fish feed\n• Types of fish feed\n• Importance of fish feed in fish farming", "marks": Decimal("10.00")},
    {"stem": "2. Fish Ponds and Their Components.\n• Meaning of fish pond\n• Types of ponds\n• Components of ponds", "marks": Decimal("10.00")},
    {"stem": "3. Fish Culture Systems.\n• Meaning of culture system\n• State the types of culture system\n• Advantages of culture system", "marks": Decimal("10.00")},
    {"stem": "4. Water Quality in Fish Farming.\n• Meaning of water quality\n• Factors affecting water quality\n• Importance of good water quality in fish culture", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="FSH")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS2 Fishery assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 9, 30, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 11, 30, 0), lagos)

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
                source_reference=f"SS2-FSH-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS2-FSH-20260326-TH-{index:02d}",
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
            "paper_code": "SS2-FSH-EXAM",
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
