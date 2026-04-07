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

TITLE = "MON 1:15-2:15 JS2 Agricultural Science Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: JSS2 SUBJECT: AGRICULTURAL SCIENCE"
BANK_NAME = "JS2 Agricultural Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Which of the following is not a type of forest?", "options": {"A": "Rain forest", "B": "Water forest", "C": "Mangrove forest", "D": "Deciduous forest"}, "answer": "B"},
    {"stem": "2. Latex can be used in making the following except", "options": {"A": "Rubber band", "B": "Balls", "C": "Tyre", "D": "Pencil"}, "answer": "D"},
    {"stem": "3. The forest trees purify air by absorbing ______.", "options": {"A": "Oxygen", "B": "Carbon dioxide", "C": "Nitrate", "D": "Potassium"}, "answer": "B"},
    {"stem": "4. The valuable materials that are obtained from the forest are called ______.", "options": {"A": "Materials", "B": "Wild life", "C": "Resources", "D": "Timber"}, "answer": "C"},
    {"stem": "5. The quantity of goods a producer is willing and able to offer for sale at a given price is ____.", "options": {"A": "Supply", "B": "Demand", "C": "Utility", "D": "Demand and supply"}, "answer": "A"},
    {"stem": "6. When the quantity of commodities supplied to the market is more than the quantity demanded, what happens to the price?", "options": {"A": "Falls", "B": "Rises", "C": "Fluctuates", "D": "All of the above"}, "answer": "A"},
    {"stem": "7. Large population of livestock is produced in the savanna region because of the presence of ___.", "options": {"A": "Grass", "B": "Tse-tse-fly", "C": "Trypanosomiasis", "D": "River"}, "answer": "A"},
    {"stem": "8. Which of the following products is best preserved by canning?", "options": {"A": "Rice", "B": "Tomato", "C": "Maize", "D": "Carrot"}, "answer": "B"},
    {"stem": "9. Which of these fishing gears requires a bait?", "options": {"A": "Gourd", "B": "Hook", "C": "Spear", "D": "Trawl net"}, "answer": "B"},
    {"stem": "10. A group of fish swimming together is termed __.", "options": {"A": "shoal", "B": "fry", "C": "gears", "D": "stocking"}, "answer": "A"},
    {"stem": "11. Natural food of fishes in water is called __.", "options": {"A": "spawning", "B": "school", "C": "plankton", "D": "aquarium"}, "answer": "C"},
    {"stem": "12. Forest product includes the following except", "options": {"A": "Gum", "B": "Rubber", "C": "Timber", "D": "Rock"}, "answer": "D"},
    {"stem": "13. The vegetation zone most suitable for cocoa production in Nigeria is ______.", "options": {"A": "Derived savanna", "B": "Mangrove", "C": "Rainforest", "D": "Sudan savanna"}, "answer": "C"},
    {"stem": "14. Forest provides employment for the following workers except", "options": {"A": "Tourist", "B": "Sculptor", "C": "Hunter", "D": "Forest guard"}, "answer": "A"},
    {"stem": "15. Which of the following is the benefit of forest on the environment?", "options": {"A": "Hindrance to farm work", "B": "Provision of foreign exchange", "C": "Provision of medicine", "D": "Purification of air"}, "answer": "D"},
    {"stem": "16. The two major types of vegetation in Nigeria are ______ and ______.", "options": {"A": "Forest, Sahel savanna", "B": "Guinea savanna, mangrove", "C": "Forest, savanna", "D": "Montane, Sudan savanna"}, "answer": "C"},
    {"stem": "17. The technology of enclosing or protecting products for distribution, storage, sale and use is known as __.", "options": {"A": "storage", "B": "packaging", "C": "protection", "D": "processing"}, "answer": "B"},
    {"stem": "18. All these materials were used for packaging in the ancient era except __.", "options": {"A": "basket", "B": "wine skin", "C": "woven bags", "D": "tin plates"}, "answer": "D"},
    {"stem": "19. The first material that envelops the product and holds it is referred to as __.", "options": {"A": "tertiary packaging", "B": "first packaging", "C": "primary packaging", "D": "secondary package"}, "answer": "C"},
    {"stem": "20. Which of the following will increase quantity of production by a farmer?", "options": {"A": "increase in the price of fertilizer", "B": "improved technology", "C": "prolonged dry season", "D": "use of crude tool"}, "answer": "B"},
    {"stem": "21. The following are advertising media except __.", "options": {"A": "newspaper", "B": "radio", "C": "television", "D": "Classroom"}, "answer": "D"},
    {"stem": "22. Farm records and accounts help the farmer to __.", "options": {"A": "adopt modern techniques of farming", "B": "be less dependent on farming for income", "C": "determine market price", "D": "manage his farm as a business"}, "answer": "D"},
    {"stem": "23. Which of the following operations should be carried out to prevent diseases in farm animals?", "options": {"A": "Branding", "B": "Vaccination", "C": "Breeding", "D": "Castration"}, "answer": "B"},
    {"stem": "24. The record of all assets in the farm is referred to as __.", "options": {"A": "farm diary", "B": "farm inventory", "C": "input record", "D": "production record"}, "answer": "B"},
    {"stem": "25. A record which shows the number of livestock produced and the quantity of crops harvested is called __ record.", "options": {"A": "consumption", "B": "input", "C": "production", "D": "inventory"}, "answer": "C"},
    {"stem": "26. A record of day-to-day activities of the farm is known as __.", "options": {"A": "farm diary", "B": "farm inventory", "C": "labour record", "D": "production record"}, "answer": "A"},
    {"stem": "27. The record of all the items the farmer invested into the farm is known as ______ record.", "options": {"A": "Input", "B": "Inventory", "C": "Consumption", "D": "Production"}, "answer": "A"},
    {"stem": "28. The piece of land where trees, other plants and animals are found is called ______.", "options": {"A": "Farm", "B": "Plot", "C": "Forest", "D": "School"}, "answer": "C"},
    {"stem": "29. ______ contains the record of what the farmer and his family consumed.", "options": {"A": "Farm diary", "B": "Output record", "C": "Consumption record", "D": "Production"}, "answer": "C"},
    {"stem": "30. Which of these agricultural products is used for building of houses?", "options": {"A": "Timber", "B": "Coffee", "C": "Rubber", "D": "Tea"}, "answer": "A"},
    {"stem": "31. Which of the following is not an aquatic organism?", "options": {"A": "Crab", "B": "Prawn", "C": "Bee", "D": "Tilapia"}, "answer": "C"},
    {"stem": "32. The study and management of aquatic animals is called", "options": {"A": "Forestry", "B": "Apiculture", "C": "Fishery", "D": "Snailry"}, "answer": "C"},
    {"stem": "33. The process of creating awareness about the existing product is known as ________.", "options": {"A": "Distributing", "B": "Advertising", "C": "Branding", "D": "None of the above"}, "answer": "B"},
    {"stem": "34. The establishment of forest in an area where there was previously none is called", "options": {"A": "Afforestation", "B": "Deforestation", "C": "Exploitation", "D": "All of the above"}, "answer": "A"},
    {"stem": "35. Forest provides employment for the following workers except", "options": {"A": "Forest guard", "B": "Game wardens", "C": "Hunters", "D": "Tourist"}, "answer": "D"},
    {"stem": "36. A game reserve is referred to as a / an _______.", "options": {"A": "Area for protecting wild animals", "B": "Area kept for ranching", "C": "Field kept for sport", "D": "Area reserved for keeping farm animals"}, "answer": "A"},
    {"stem": "37. Most green plants manufacture their own food through the process called", "options": {"A": "Vapor", "B": "Evaporation", "C": "Photosynthesis", "D": "All of the above"}, "answer": "C"},
    {"stem": "38. Sahel savanna can be found in ______ part of the country?", "options": {"A": "Eastern", "B": "Northern", "C": "Central", "D": "Southern"}, "answer": "B"},
    {"stem": "39. Importance of agriculture include all except __.", "options": {"A": "provision of food", "B": "provision of shelter", "C": "Foreign exchange", "D": "Creation of job for the disabled"}, "answer": "D"},
    {"stem": "40. Agriculture can be described as the production of ______.", "options": {"A": "Export crops", "B": "Food for man", "C": "Fibre crops for man", "D": "Meat for man"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. (a) Explain the following terms: (i) Afforestation (ii) Deforestation (iii) Selective exploitation.\n(b) Define forest and list three resources obtained from forest.\n(c) State four effects of forest on the environment.", "marks": Decimal("10.00")},
    {"stem": "2. Write short notes on the following vegetations: (i) Rain forest (ii) Guinea savanna (iii) Sahel savanna.", "marks": Decimal("8.00")},
    {"stem": "3. Explain the following types of farm records: (i) Farm diary (ii) Farm inventory (iii) Input record (iv) Sales record (v) Consumption record.", "marks": Decimal("8.00")},
    {"stem": "4. (a) List four benefits of keeping farm records.\n(b) Name two items that may be recorded in farm input record.", "marks": Decimal("7.00")},
    {"stem": "5. (a) What is packaging?\n(b) List four packaging materials and one item that may be packed in each.", "marks": Decimal("7.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="AGR")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="victoria@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 23, 13, 15, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 14, 15, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Monday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 1:15 PM WAT.",
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
    exam.dean_review_comment = "Approved for Monday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 1:15 PM WAT."
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
            source_reference=f"JS2-AGR-20260323-OBJ-{index:02d}",
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
            source_reference=f"JS2-AGR-20260323-TH-{index:02d}",
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
        "paper_code": "JS2-AGR-EXAM",
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
        "status": exam.status,
        "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
        "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
        "duration_minutes": blueprint.duration_minutes,
        "objective_questions": len(OBJECTIVES),
        "theory_questions": len(THEORY),
    })

main()
