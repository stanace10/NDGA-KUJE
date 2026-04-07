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

TITLE = "THU 8:00-9:30 SS3 Home Management Second Term Mock Exam"
DESCRIPTION = "SS3 HOME MANAGEMENT MOCK EXAMINATION"
BANK_NAME = "SS3 Home Management Mock Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Sanitation in the home refers to:", "options": {"A": "Decoration of the house", "B": "Proper maintenance of cleanliness and hygiene", "C": "Buying new furniture", "D": "Painting the walls"}, "answer": "B"},
    {"stem": "One importance of home sanitation is to:", "options": {"A": "Increase house value only", "B": "Prevent diseases and infections", "C": "Attract visitors", "D": "Reduce rent"}, "answer": "B"},
    {"stem": "Which of the following is a cleaning material?", "options": {"A": "Detergent", "B": "Kerosene", "C": "Cement", "D": "Sand"}, "answer": "A"},
    {"stem": "Refuse can best be described as:", "options": {"A": "Stored food", "B": "Household waste materials", "C": "Cleaning agents", "D": "Furniture"}, "answer": "B"},
    {"stem": "The safest method of refuse disposal in urban areas is:", "options": {"A": "Dumping in open space", "B": "Burning inside the house", "C": "Sanitary landfill", "D": "Throwing in gutters"}, "answer": "C"},
    {"stem": "Which of the following is biodegradable waste?", "options": {"A": "Nylon", "B": "Plastic bottle", "C": "Vegetable peels", "D": "Tin can"}, "answer": "C"},
    {"stem": "A good sanitation practice includes:", "options": {"A": "Sweeping once a month", "B": "Leaving waste uncovered", "C": "Cleaning regularly and disinfecting surfaces", "D": "Storing waste indoors"}, "answer": "C"},
    {"stem": "Which tool is used for cleaning floors?", "options": {"A": "Broom", "B": "Spoon", "C": "Knife", "D": "Plate"}, "answer": "A"},
    {"stem": "Poor sanitation can result in:", "options": {"A": "Good health", "B": "Spread of diseases", "C": "Increased appetite", "D": "Clean water"}, "answer": "B"},
    {"stem": "Covered refuse bins help to:", "options": {"A": "Decorate the house", "B": "Prevent pest infestation", "C": "Store water", "D": "Dry clothes"}, "answer": "B"},
    {"stem": "Household pests are:", "options": {"A": "Domestic animals", "B": "Harmful organisms found in homes", "C": "Cleaning tools", "D": "Garden plants"}, "answer": "B"},
    {"stem": "Which of the following is a common household pest?", "options": {"A": "Dog", "B": "Cat", "C": "Cockroach", "D": "Goat"}, "answer": "C"},
    {"stem": "Rats are dangerous because they:", "options": {"A": "Beautify homes", "B": "Spread diseases and damage property", "C": "Improve sanitation", "D": "Eat only grass"}, "answer": "B"},
    {"stem": "Mosquitoes cause:", "options": {"A": "Typhoid", "B": "Malaria", "C": "Ulcer", "D": "Diabetes"}, "answer": "B"},
    {"stem": "One method of controlling flies is:", "options": {"A": "Leaving food uncovered", "B": "Proper refuse disposal and covering food", "C": "Spilling water", "D": "Opening gutters"}, "answer": "B"},
    {"stem": "Termites mainly destroy:", "options": {"A": "Food", "B": "Clothes", "C": "Wooden structures", "D": "Tiles"}, "answer": "C"},
    {"stem": "Insecticides are used to:", "options": {"A": "Feed insects", "B": "Kill or control insects", "C": "Wash plates", "D": "Disinfect water"}, "answer": "B"},
    {"stem": "Bedbugs are commonly found in:", "options": {"A": "Ceilings", "B": "Beds and mattresses", "C": "Gutters", "D": "Kitchens only"}, "answer": "B"},
    {"stem": "Good sanitation helps to:", "options": {"A": "Attract pests", "B": "Reduce pest infestation", "C": "Increase rats", "D": "Multiply flies"}, "answer": "B"},
    {"stem": "One effect of pest infestation is:", "options": {"A": "Improved hygiene", "B": "Food contamination", "C": "Increased ventilation", "D": "Better health"}, "answer": "B"},
    {"stem": "A kitchen plan refers to:", "options": {"A": "Cooking style", "B": "Arrangement and design of kitchen space", "C": "Menu list", "D": "Table decoration"}, "answer": "B"},
    {"stem": "The work triangle in kitchen planning involves:", "options": {"A": "Sink, cooker, refrigerator", "B": "Chair, table, plate", "C": "Spoon, fork, knife", "D": "Door, window, roof"}, "answer": "A"},
    {"stem": "A good kitchen should be:", "options": {"A": "Poorly ventilated", "B": "Well ventilated and well lit", "C": "Dark", "D": "Small and congested"}, "answer": "B"},
    {"stem": "Kitchen hygiene involves:", "options": {"A": "Wearing dirty clothes", "B": "Proper cleaning and safe food handling", "C": "Cooking without washing hands", "D": "Storing raw and cooked food together"}, "answer": "B"},
    {"stem": "To prevent kitchen accidents:", "options": {"A": "Leave spills unattended", "B": "Keep knives properly stored", "C": "Run on wet floors", "D": "Overload sockets"}, "answer": "B"},
    {"stem": "The best flooring material for kitchen safety is:", "options": {"A": "Slippery tiles", "B": "Rough, non-slip surface", "C": "Carpet", "D": "Mud"}, "answer": "B"},
    {"stem": "Personal hygiene in the kitchen includes:", "options": {"A": "Long dirty nails", "B": "Covering hair while cooking", "C": "Wearing jewelry", "D": "Tasting food with fingers"}, "answer": "B"},
    {"stem": "Cross contamination occurs when:", "options": {"A": "Raw food contacts cooked food", "B": "Food is covered", "C": "Plates are clean", "D": "Hands are washed"}, "answer": "A"},
    {"stem": "Fire in the kitchen can be prevented by:", "options": {"A": "Leaving gas on", "B": "Checking gas connections regularly", "C": "Pouring water on oil fire", "D": "Ignoring leaks"}, "answer": "B"},
    {"stem": "The purpose of ventilation in the kitchen is to:", "options": {"A": "Increase heat", "B": "Remove smoke and odors", "C": "Store food", "D": "Block light"}, "answer": "B"},
    {"stem": "Table setting refers to:", "options": {"A": "Cooking food", "B": "Arranging tableware for serving meals", "C": "Washing plates", "D": "Sweeping dining area"}, "answer": "B"},
    {"stem": "Basic table setting includes:", "options": {"A": "Plate, cutlery, napkin", "B": "Pot and stove", "C": "Broom and mop", "D": "Sink and tap"}, "answer": "A"},
    {"stem": "Napkins are placed:", "options": {"A": "Under the table", "B": "On the chair", "C": "On the plate or beside it", "D": "On the floor"}, "answer": "C"},
    {"stem": "The purpose of meal service is to:", "options": {"A": "Serve food attractively and efficiently", "B": "Waste time", "C": "Increase cost", "D": "Store leftovers"}, "answer": "A"},
    {"stem": "The host usually sits:", "options": {"A": "Anywhere", "B": "At the head of the table", "C": "Under the table", "D": "Near the kitchen only"}, "answer": "B"},
    {"stem": "Buffet service involves:", "options": {"A": "Guests serving themselves", "B": "Waiters serving each guest", "C": "No food arrangement", "D": "Eating without plates"}, "answer": "A"},
    {"stem": "Formal table setting uses:", "options": {"A": "Plastic plates only", "B": "Proper arrangement of cutlery according to course", "C": "No napkins", "D": "Only one spoon"}, "answer": "B"},
    {"stem": "Glassware is placed:", "options": {"A": "Left side", "B": "Right side above knife", "C": "Under plate", "D": "Behind chair"}, "answer": "B"},
    {"stem": "Meal service should promote:", "options": {"A": "Disorder", "B": "Courtesy and good manners", "C": "Noise", "D": "Rushing"}, "answer": "B"},
    {"stem": "Table setting enhances:", "options": {"A": "Appetite and presentation", "B": "Dirtiness", "C": "Heat", "D": "Fire risk"}, "answer": "A"},
    {"stem": "Test interpretation helps to:", "options": {"A": "Evaluate practical performance", "B": "Cook faster", "C": "Reduce ingredients", "D": "Wash dishes"}, "answer": "A"},
    {"stem": "Sensory evaluation includes:", "options": {"A": "Smell, taste, texture, appearance", "B": "Price and size", "C": "Market location", "D": "Cooking time only"}, "answer": "A"},
    {"stem": "In practical tests, cleanliness is assessed to determine:", "options": {"A": "Food color", "B": "Hygiene standard", "C": "Cost", "D": "Decoration"}, "answer": "B"},
    {"stem": "Proper measurement in practical ensures:", "options": {"A": "Food wastage", "B": "Accuracy in results", "C": "Burning food", "D": "Delays"}, "answer": "B"},
    {"stem": "Presentation of food affects:", "options": {"A": "Taste only", "B": "Appetite and acceptability", "C": "Weight", "D": "Storage"}, "answer": "B"},
    {"stem": "Time management during practical test shows:", "options": {"A": "Laziness", "B": "Efficiency and skill", "C": "Carelessness", "D": "Fear"}, "answer": "B"},
    {"stem": "A marking scheme in practical examination ensures:", "options": {"A": "Fairness and objectivity", "B": "Bias", "C": "Confusion", "D": "Waste of time"}, "answer": "A"},
    {"stem": "Texture of food refers to:", "options": {"A": "Smell", "B": "Feel or consistency in the mouth", "C": "Price", "D": "Size"}, "answer": "B"},
    {"stem": "Overcooked food in practical test may result in:", "options": {"A": "High marks", "B": "Loss of quality", "C": "Better flavor always", "D": "More nutrients"}, "answer": "B"},
    {"stem": "Evaluation comments help students to:", "options": {"A": "Improve future performance", "B": "Stop cooking", "C": "Waste food", "D": "Ignore corrections"}, "answer": "A"},
    {"stem": "Proper refuse disposal reduces:", "options": {"A": "Cleanliness", "B": "Pest infestation", "C": "Hygiene", "D": "Safety"}, "answer": "B"},
    {"stem": "Good home management promotes:", "options": {"A": "Disorder", "B": "Comfort and efficiency", "C": "Dirt", "D": "Waste"}, "answer": "B"},
    {"stem": "Kitchen safety rules are meant to:", "options": {"A": "Increase accidents", "B": "Prevent injuries", "C": "Delay cooking", "D": "Waste gas"}, "answer": "B"},
    {"stem": "Pest control improves:", "options": {"A": "Food safety", "B": "Dirtiness", "C": "Infections", "D": "Damage"}, "answer": "A"},
    {"stem": "Hygiene practices prevent:", "options": {"A": "Illness and contamination", "B": "Decoration", "C": "Cooking", "D": "Ventilation"}, "answer": "A"},
    {"stem": "Fire extinguisher in kitchen is used to:", "options": {"A": "Decorate walls", "B": "Control fire outbreaks", "C": "Cool food", "D": "Clean plates"}, "answer": "B"},
    {"stem": "Balanced meal service ensures:", "options": {"A": "Poor appetite", "B": "Nutritional adequacy", "C": "Waste", "D": "High cost"}, "answer": "B"},
    {"stem": "Waste segregation means:", "options": {"A": "Mixing all waste", "B": "Separating biodegradable and non-biodegradable waste", "C": "Burning plastics", "D": "Throwing waste anywhere"}, "answer": "B"},
    {"stem": "Clean water supply in the home promotes:", "options": {"A": "Disease", "B": "Good health", "C": "Pest growth", "D": "Dirt"}, "answer": "B"},
    {"stem": "Effective home management requires:", "options": {"A": "Planning and organization", "B": "Laziness", "C": "Negligence", "D": "Wastefulness"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. (a) Define sanitation in the home.\n(b) Explain four types of sanitation commonly practiced at home.", "marks": Decimal("15.00")},
    {"stem": "2. (a) List four materials needed for cleaning the home.\n(b) Discuss four methods of proper disposal of household refuse.", "marks": Decimal("15.00")},
    {"stem": "3. (a) What is meant by household pests?\n(b) Explain four common types of household pests and their effects.", "marks": Decimal("15.00")},
    {"stem": "4. (a) State four effects of household pests on health and property.\n(b) Explain four methods of controlling household pests.", "marks": Decimal("15.00")},
    {"stem": "5. (a) What is kitchen planning?\n(b) Outline four principles to consider when designing a safe and hygienic kitchen.", "marks": Decimal("15.00")},
    {"stem": "6. (a) Define kitchen hygiene.\n(b) Explain four practices to maintain hygiene and safety in the kitchen.", "marks": Decimal("15.00")},
    {"stem": "7. (a) What is table setting?\n(b) Describe four different types of table setting used in homes or hotels.", "marks": Decimal("15.00")},
    {"stem": "8. (a) Explain the meaning of meal service.\n(b) Discuss four principles to follow when serving meals to ensure hygiene and proper presentation.", "marks": Decimal("15.00")},
    {"stem": "9. (a) Define test interpretation in Home Management practicals.\n(b) Explain four reasons why test interpretation is important in practical examinations.", "marks": Decimal("15.00")},
    {"stem": "10. (a) State the meaning of safety in the home.\n(b) Explain four ways to ensure safety in the kitchen and dining areas.", "marks": Decimal("15.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="HMG")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS3 Home Management assignment found")
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
                source_reference=f"SS3-HMG-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS3-HMG-20260326-TH-{index:02d}",
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
            "paper_code": "SS3-HMG-MOCK",
            "flow_type": "OBJECTIVE_THEORY",
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "objective_target_max": "40.00",
            "theory_target_max": "60.00",
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
