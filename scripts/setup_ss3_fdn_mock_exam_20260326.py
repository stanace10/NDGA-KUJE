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

TITLE = "THU 8:00-9:30 SS3 Food and Nutrition Second Term Mock Exam"
DESCRIPTION = "SS3 FOODS AND NUTRITION SECOND TERM MOCK EXAMINATION"
BANK_NAME = "SS3 Food and Nutrition Mock Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Rechauffe refers to ______.", "options": {"A": "freshly cooked meals", "B": "reheated leftover food", "C": "raw food", "D": "preserved food"}, "answer": "B"},
    {"stem": "The main aim of rechauffe is to ______.", "options": {"A": "waste food", "B": "increase cost", "C": "avoid food wastage", "D": "spoil food"}, "answer": "C"},
    {"stem": "A good leftover dish must be ______.", "options": {"A": "stale", "B": "nutritious and safe", "C": "burnt", "D": "sour"}, "answer": "B"},
    {"stem": "Before reheating leftovers, one should ______.", "options": {"A": "leave uncovered", "B": "taste first", "C": "check for spoilage", "D": "add water"}, "answer": "C"},
    {"stem": "Leftover meat can be used for ______.", "options": {"A": "meat pie filling", "B": "burning", "C": "disposal", "D": "drying"}, "answer": "A"},
    {"stem": "Improper storage of leftovers may cause ______.", "options": {"A": "freshness", "B": "contamination", "C": "preservation", "D": "sweetness"}, "answer": "B"},
    {"stem": "Meat is mainly a source of ______.", "options": {"A": "carbohydrate", "B": "protein", "C": "fibre", "D": "vitamin C"}, "answer": "B"},
    {"stem": "The tenderness of meat depends on ______.", "options": {"A": "age of animal", "B": "colour", "C": "price", "D": "smell"}, "answer": "A"},
    {"stem": "Tough cuts of meat are best cooked by ______.", "options": {"A": "frying", "B": "grilling", "C": "boiling briefly", "D": "stewing"}, "answer": "D"},
    {"stem": "Marinating meat helps to ______.", "options": {"A": "harden it", "B": "reduce flavour", "C": "tenderize it", "D": "spoil it"}, "answer": "C"},
    {"stem": "Red meat contains high amount of ______.", "options": {"A": "iron", "B": "starch", "C": "sugar", "D": "fibre"}, "answer": "A"},
    {"stem": "Offal refers to ______.", "options": {"A": "muscle meat", "B": "internal organs", "C": "bones", "D": "skin"}, "answer": "B"},
    {"stem": "An example of poultry is ______.", "options": {"A": "goat", "B": "chicken", "C": "cow", "D": "sheep"}, "answer": "B"},
    {"stem": "Young poultry is tender because it ______.", "options": {"A": "has less connective tissue", "B": "is older", "C": "is fatter", "D": "is heavier"}, "answer": "A"},
    {"stem": "Poultry should be stored at ______.", "options": {"A": "room temperature", "B": "high heat", "C": "refrigeration temperature", "D": "sunlight"}, "answer": "C"},
    {"stem": "Stuffing poultry is done ______.", "options": {"A": "after cooking", "B": "during frying", "C": "before roasting", "D": "after serving"}, "answer": "C"},
    {"stem": "Salmonella infection is linked to ______.", "options": {"A": "vegetables", "B": "poultry", "C": "fruits", "D": "cereals"}, "answer": "B"},
    {"stem": "The best method for cooking old poultry is ______.", "options": {"A": "grilling", "B": "roasting quickly", "C": "frying", "D": "stewing"}, "answer": "D"},
    {"stem": "Fish is classified into ______.", "options": {"A": "red and white", "B": "freshwater and saltwater", "C": "hot and cold", "D": "soft and hard"}, "answer": "B"},
    {"stem": "An example of freshwater fish is ______.", "options": {"A": "mackerel", "B": "tuna", "C": "tilapia", "D": "sardine"}, "answer": "C"},
    {"stem": "An example of saltwater fish is ______.", "options": {"A": "catfish", "B": "tilapia", "C": "tuna", "D": "mudfish"}, "answer": "C"},
    {"stem": "Oily fish contains high ______.", "options": {"A": "carbohydrates", "B": "omega-3 fatty acids", "C": "fibre", "D": "starch"}, "answer": "B"},
    {"stem": "The best way to retain nutrients in fish is by ______.", "options": {"A": "deep frying", "B": "overcooking", "C": "steaming", "D": "burning"}, "answer": "C"},
    {"stem": "Signs of fresh fish include ______.", "options": {"A": "dull eyes", "B": "bad odour", "C": "firm flesh", "D": "dry gills"}, "answer": "C"},
    {"stem": "Fish cooks faster than meat because it ______.", "options": {"A": "has less connective tissue", "B": "has more bones", "C": "is larger", "D": "is tougher"}, "answer": "A"},
    {"stem": "Smoking fish helps to ______.", "options": {"A": "increase moisture", "B": "preserve it", "C": "spoil it", "D": "reduce flavour"}, "answer": "B"},
    {"stem": "A balanced diet contains ______.", "options": {"A": "one nutrient", "B": "two nutrients", "C": "three nutrients", "D": "all nutrients"}, "answer": "D"},
    {"stem": "Vitamins help in ______.", "options": {"A": "body regulation", "B": "energy only", "C": "fat storage", "D": "spoilage"}, "answer": "A"},
    {"stem": "Carbohydrates are mainly for ______.", "options": {"A": "repair", "B": "energy", "C": "regulation", "D": "insulation"}, "answer": "B"},
    {"stem": "Protein deficiency leads to ______.", "options": {"A": "kwashiorkor", "B": "obesity", "C": "hypertension", "D": "scurvy"}, "answer": "A"},
    {"stem": "Minerals are important for ______.", "options": {"A": "decoration", "B": "flavour", "C": "body building", "D": "sweetness"}, "answer": "C"},
    {"stem": "Overcooking vegetables causes ______.", "options": {"A": "nutrient retention", "B": "flavour increase", "C": "nutrient loss", "D": "preservation"}, "answer": "C"},
    {"stem": "Food poisoning is caused by ______.", "options": {"A": "clean utensils", "B": "contamination", "C": "refrigeration", "D": "washing"}, "answer": "B"},
    {"stem": "Hygienic kitchen practices include ______.", "options": {"A": "hand washing", "B": "dirty apron", "C": "uncovered hair", "D": "stale food"}, "answer": "A"},
    {"stem": "Preservation methods include ______.", "options": {"A": "freezing", "B": "burning", "C": "exposure", "D": "soaking"}, "answer": "A"},
    {"stem": "Stewing is suitable for ______.", "options": {"A": "tender meat", "B": "tough meat", "C": "fruits", "D": "cereals"}, "answer": "B"},
    {"stem": "The first step in menu planning is ______.", "options": {"A": "cooking", "B": "serving", "C": "planning", "D": "eating"}, "answer": "C"},
    {"stem": "Reheating food should be done ______.", "options": {"A": "partially", "B": "thoroughly", "C": "slowly", "D": "carelessly"}, "answer": "B"},
    {"stem": "A good source of calcium is ______.", "options": {"A": "milk", "B": "rice", "C": "oil", "D": "sugar"}, "answer": "A"},
    {"stem": "Iron deficiency causes ______.", "options": {"A": "anaemia", "B": "rickets", "C": "obesity", "D": "scurvy"}, "answer": "A"},
    {"stem": "Frying fish at high heat may cause ______.", "options": {"A": "nutrient gain", "B": "moisture increase", "C": "nutrient loss", "D": "preservation"}, "answer": "C"},
    {"stem": "Fresh poultry has ______.", "options": {"A": "bad odour", "B": "firm flesh", "C": "green skin", "D": "dry texture"}, "answer": "B"},
    {"stem": "The main function of fats is ______.", "options": {"A": "regulation", "B": "energy storage", "C": "digestion", "D": "colour"}, "answer": "B"},
    {"stem": "Meat inspection prevents ______.", "options": {"A": "spoilage", "B": "contamination", "C": "tenderness", "D": "freshness"}, "answer": "B"},
    {"stem": "Proper storage of fish requires ______.", "options": {"A": "heat", "B": "refrigeration", "C": "sunlight", "D": "dryness"}, "answer": "B"},
    {"stem": "Rechauffe dishes must be ______.", "options": {"A": "safe and nutritious", "B": "stale", "C": "sour", "D": "burnt"}, "answer": "A"},
    {"stem": "Omega-3 is found mainly in ______.", "options": {"A": "cereals", "B": "oily fish", "C": "fruits", "D": "tubers"}, "answer": "B"},
    {"stem": "Tender meat can be cooked by ______.", "options": {"A": "stewing", "B": "grilling", "C": "boiling long", "D": "smoking"}, "answer": "B"},
    {"stem": "Poultry meat is rich in ______.", "options": {"A": "protein", "B": "fibre", "C": "starch", "D": "sugar"}, "answer": "A"},
    {"stem": "Spoiled fish smells ______.", "options": {"A": "fresh", "B": "sweet", "C": "offensive", "D": "mild"}, "answer": "C"},
    {"stem": "The aim of revision is to ______.", "options": {"A": "forget", "B": "reinforce learning", "C": "confuse", "D": "delay"}, "answer": "B"},
    {"stem": "Food flavour can be retained by ______.", "options": {"A": "overcooking", "B": "steaming lightly", "C": "burning", "D": "soaking"}, "answer": "B"},
    {"stem": "Internal organs of animals are called ______.", "options": {"A": "carcass", "B": "offal", "C": "flesh", "D": "cuts"}, "answer": "B"},
    {"stem": "Good kitchen hygiene prevents ______.", "options": {"A": "illness", "B": "flavour", "C": "colour", "D": "cost"}, "answer": "A"},
    {"stem": "Meat should be thawed ______.", "options": {"A": "at room temperature", "B": "in refrigerator", "C": "in sunlight", "D": "near heat"}, "answer": "B"},
    {"stem": "Fish eyes are clear when the fish is ______.", "options": {"A": "stale", "B": "fresh", "C": "rotten", "D": "dry"}, "answer": "B"},
    {"stem": "Connective tissue in meat affects ______.", "options": {"A": "tenderness", "B": "colour", "C": "smell", "D": "size"}, "answer": "A"},
    {"stem": "Reheating leftovers repeatedly may cause ______.", "options": {"A": "safety", "B": "spoilage", "C": "preservation", "D": "flavour"}, "answer": "B"},
    {"stem": "Balanced meals must consider ______.", "options": {"A": "colour only", "B": "nutrition", "C": "cost only", "D": "taste only"}, "answer": "B"},
    {"stem": "Examination preparation involves ______.", "options": {"A": "ignoring notes", "B": "consistent revision", "C": "guessing", "D": "sleeping"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Name two major types of kitchen.\n(b) State six sanitary rules to observe while cooking in the kitchen.\n(c) State three ways of saving time and energy in food preparation.", "marks": Decimal("15.00")},
    {"stem": "2. State five reasons why breastfeeding is better than artificial feeding formula.\n(b) State six sources of calcium and three deficiencies of calcium.", "marks": Decimal("15.00")},
    {"stem": "3. Differentiate between reheating and rechauffe.\n(b) State four advantages of convenience foods.", "marks": Decimal("15.00")},
    {"stem": "4. Define the term budgeting.\n(b) State five factors to be considered when planning a budget.\n(c) State four advantages of bulk purchasing.", "marks": Decimal("15.00")},
    {"stem": "5. State two functions each of the following nutrients:\n(i) Carbohydrates\n(ii) Proteins\n(iii) Vitamins\n(iv) Water\n(b) State two guidelines for selecting convenience food.", "marks": Decimal("15.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="FDN")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS3 Food and Nutrition assignment found")
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
                source_reference=f"SS3-FDN-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS3-FDN-20260326-TH-{index:02d}",
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
            "paper_code": "SS3-FDN-MOCK",
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
