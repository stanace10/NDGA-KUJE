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

TITLE = "MON 1:15-2:15 JS3 Agricultural Science Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: JSS3 SUBJECT: AGRICULTURAL SCIENCE"
BANK_NAME = "JS3 Agricultural Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Which of the following diseases is caused by fungus?", "options": {"A": "anthrax", "B": "aspergillosis", "C": "brucellosis", "D": "coccidiosis"}, "answer": "B"},
    {"stem": "2. One major reason for packaging farm produce is to", "options": {"A": "increase weight", "B": "prevent spoilage", "C": "reduce quality", "D": "delay harvesting"}, "answer": "B"},
    {"stem": "3. Which of the following sources of protein is of animal origin?", "options": {"A": "ground nut cake", "B": "blood meal", "C": "cotton seed cake", "D": "linseed meal"}, "answer": "B"},
    {"stem": "4. Human activity that negatively affects forest production is", "options": {"A": "afforestation", "B": "bush burning", "C": "mulching", "D": "trimming"}, "answer": "B"},
    {"stem": "5. Infestation by tick on farm animals can be controlled by", "options": {"A": "feeding the animals in time", "B": "giving the animals water every day", "C": "giving the animals vaccination", "D": "picking the ticks with hand"}, "answer": "D"},
    {"stem": "6. Which agricultural product is commonly packaged in jute bags?", "options": {"A": "Milk", "B": "Yam", "C": "Rice", "D": "Fish"}, "answer": "C"},
    {"stem": "7. Marketing of farm products involves", "options": {"A": "producing crops", "B": "buying farm inputs", "C": "selling farm produce", "D": "storing farm produce"}, "answer": "C"},
    {"stem": "8. Which of the following is not a protective function of the forest?", "options": {"A": "erosion control", "B": "soil conservation", "C": "tourist attraction", "D": "wind break"}, "answer": "D"},
    {"stem": "9. One importance of marketing farm products is", "options": {"A": "wastage", "B": "profit making", "C": "poor storage", "D": "price reduction"}, "answer": "B"},
    {"stem": "10. Which of the following is a marketing agent?", "options": {"A": "Farmer", "B": "Middleman", "C": "Wholesaler", "D": "All of the above"}, "answer": "D"},
    {"stem": "11. Stock exchange is important in agriculture because it", "options": {"A": "attracts foreign currency", "B": "encourages investment in agriculture", "C": "helps the country to manage their debt", "D": "exposes the weakness of representative"}, "answer": "B"},
    {"stem": "12. Poor roads affect marketing by", "options": {"A": "increasing profit", "B": "reducing transportation cost", "C": "causing spoilage", "D": "increasing demand"}, "answer": "C"},
    {"stem": "13. The value of agricultural produce from Nigeria sold to other countries will be paid in", "options": {"A": "export duty", "B": "foreign exchange", "C": "stock dividend", "D": "import duty"}, "answer": "B"},
    {"stem": "14. One factor that affects pricing is", "options": {"A": "weather", "B": "heat", "C": "storage", "D": "demand"}, "answer": "D"},
    {"stem": "15. When demand is high and supply is low, price", "options": {"A": "falls", "B": "remains constant", "C": "rises", "D": "disappears"}, "answer": "C"},
    {"stem": "16. The purpose of advertising farm produce in agribusiness includes the following except to", "options": {"A": "create awareness for the products", "B": "develop large market", "C": "increase the price of the products", "D": "promote the firm's image"}, "answer": "C"},
    {"stem": "17. Price control means", "options": {"A": "free selling", "B": "government fixing prices", "C": "bargaining", "D": "middlemen control"}, "answer": "B"},
    {"stem": "18. Seasonal products usually have", "options": {"A": "fixed prices", "B": "unstable prices", "C": "no prices", "D": "high storage"}, "answer": "B"},
    {"stem": "19. Farm records are", "options": {"A": "farm tools", "B": "written farm information", "C": "farm buildings", "D": "farm products"}, "answer": "B"},
    {"stem": "20. Which of the following is a cartilaginous fish?", "options": {"A": "cat fish", "B": "dolphin", "C": "carp", "D": "tilapia"}, "answer": "B"},
    {"stem": "21. Which of the following is a farm record?", "options": {"A": "Sales record", "B": "Hoe", "C": "Fertilizer", "D": "Tractor"}, "answer": "A"},
    {"stem": "22. Farm records help farmers to know their", "options": {"A": "tools", "B": "profit and loss", "C": "crops", "D": "weather"}, "answer": "B"},
    {"stem": "23. Which record shows daily farm expenses?", "options": {"A": "Production record", "B": "Inventory record", "C": "Cash book", "D": "Yield record"}, "answer": "C"},
    {"stem": "24. Keeping farm records encourages", "options": {"A": "poor management", "B": "efficiency", "C": "wastage", "D": "losses"}, "answer": "B"},
    {"stem": "25. Book keeping is the", "options": {"A": "buying of farm tools", "B": "recording of financial transactions", "C": "marketing of produce", "D": "harvesting crops"}, "answer": "B"},
    {"stem": "26. A cash book records", "options": {"A": "crops planted", "B": "money received and spent", "C": "animals owned", "D": "farm tools"}, "answer": "B"},
    {"stem": "27. Book keeping helps farmers to", "options": {"A": "avoid profit", "B": "know financial position", "C": "reduce output", "D": "increase waste"}, "answer": "B"},
    {"stem": "28. Which of the following is used in book keeping?", "options": {"A": "Ledger", "B": "Cutlass", "C": "Hoe", "D": "Rake"}, "answer": "A"},
    {"stem": "29. The record of farm properties is called", "options": {"A": "inventory", "B": "sales book", "C": "cash book", "D": "purchase book"}, "answer": "A"},
    {"stem": "30. Book keeping is important because it", "options": {"A": "encourages guessing", "B": "prevents planning", "C": "aids decision making", "D": "increases loss"}, "answer": "C"},
    {"stem": "31. Stock exchange is a place where", "options": {"A": "crops are stored", "B": "shares are bought and sold", "C": "animals are sold", "D": "tools are exchanged"}, "answer": "B"},
    {"stem": "32. Agricultural companies raise capital through", "options": {"A": "farming", "B": "borrowing only", "C": "stock exchange", "D": "taxation"}, "answer": "C"},
    {"stem": "33. A share represents", "options": {"A": "loan", "B": "ownership in a company", "C": "debt", "D": "expense"}, "answer": "B"},
    {"stem": "34. Which of these can be traded on the stock exchange?", "options": {"A": "Hoe", "B": "Shares", "C": "Fertilizer", "D": "Crops"}, "answer": "B"},
    {"stem": "35. Stock exchange helps agriculture by", "options": {"A": "reducing investment", "B": "providing funds", "C": "increasing losses", "D": "stopping production"}, "answer": "B"},
    {"stem": "36. An investor buys shares to", "options": {"A": "lose money", "B": "own farmland", "C": "earn dividends", "D": "pay tax"}, "answer": "C"},
    {"stem": "37. Fishery is the", "options": {"A": "planting of fish", "B": "rearing of fish", "C": "catching of birds", "D": "selling of meat"}, "answer": "B"},
    {"stem": "38. Fish farming is also known as", "options": {"A": "apiculture", "B": "pisciculture", "C": "horticulture", "D": "floriculture"}, "answer": "B"},
    {"stem": "39. Which of the following is a fish pond type?", "options": {"A": "Plastic pond", "B": "Earthen pond", "C": "Wooden pond", "D": "Glass pond"}, "answer": "B"},
    {"stem": "40. Fish is important because it", "options": {"A": "causes disease", "B": "spoils easily", "C": "supplies protein", "D": "reduces income"}, "answer": "C"},
    {"stem": "41. An example of cultured fish is", "options": {"A": "Tilapia", "B": "Crocodile", "C": "Crab", "D": "Frog"}, "answer": "A"},
    {"stem": "42. Which tool is used in fishing?", "options": {"A": "Net", "B": "Hoe", "C": "Cutlass", "D": "Rake"}, "answer": "A"},
    {"stem": "43. Soil fertility refers to the soil's ability to", "options": {"A": "hold water", "B": "support plant growth", "C": "resist erosion", "D": "absorb heat"}, "answer": "B"},
    {"stem": "44. One way of improving soil fertility is", "options": {"A": "bush burning", "B": "crop rotation", "C": "overgrazing", "D": "erosion"}, "answer": "B"},
    {"stem": "45. Which of the following improves soil fertility naturally?", "options": {"A": "manure", "B": "plastic waste", "C": "stones", "D": "glass"}, "answer": "A"},
    {"stem": "46. Nitrogen helps plants to", "options": {"A": "flower only", "B": "grow leaves", "C": "produce fruits", "D": "form roots"}, "answer": "B"},
    {"stem": "47. Poor soil fertility leads to", "options": {"A": "high yield", "B": "low yield", "C": "healthy crops", "D": "fertile land"}, "answer": "B"},
    {"stem": "48. Leguminous crops help soil by", "options": {"A": "removing nitrogen", "B": "adding nitrogen", "C": "drying soil", "D": "loosening rocks"}, "answer": "B"},
    {"stem": "49. Feed is the", "options": {"A": "shelter of animals", "B": "food given to animals", "C": "medicine for animals", "D": "waste of animals"}, "answer": "B"},
    {"stem": "50. Which of the following is an animal feed?", "options": {"A": "Grass", "B": "Plastic", "C": "Iron", "D": "Stone"}, "answer": "A"},
    {"stem": "51. Feeds that supply energy are rich in", "options": {"A": "protein", "B": "vitamins", "C": "carbohydrates", "D": "minerals"}, "answer": "C"},
    {"stem": "52. Roughages are feeds that contain", "options": {"A": "high fibre", "B": "no nutrients", "C": "drugs", "D": "minerals only"}, "answer": "A"},
    {"stem": "53. An example of concentrate feed is", "options": {"A": "hay", "B": "maize", "C": "straw", "D": "grass"}, "answer": "B"},
    {"stem": "54. Protein feeds help animals in", "options": {"A": "digestion", "B": "growth and repair", "C": "breathing", "D": "walking"}, "answer": "B"},
    {"stem": "55. Which feed helps in bone formation?", "options": {"A": "carbohydrates", "B": "minerals", "C": "fats", "D": "water"}, "answer": "B"},
    {"stem": "56. Animals require water mainly for", "options": {"A": "decoration", "B": "digestion", "C": "housing", "D": "transport"}, "answer": "B"},
    {"stem": "57. Fish meal is a", "options": {"A": "roughage", "B": "protein feed", "C": "mineral feed", "D": "vitamin feed"}, "answer": "B"},
    {"stem": "58. Feeding animals properly results in", "options": {"A": "diseases", "B": "poor growth", "C": "high productivity", "D": "death"}, "answer": "C"},
    {"stem": "59. Poor feeding can cause", "options": {"A": "malnutrition", "B": "fast growth", "C": "high yield", "D": "strength"}, "answer": "A"},
    {"stem": "60. Balanced diet means feed that contains", "options": {"A": "only carbohydrates", "B": "all nutrients in right proportion", "C": "only proteins", "D": "only mineral"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. (a) Explain marketing of farm products.\n(b) List four marketing channels.", "marks": Decimal("8.00")},
    {"stem": "2. (a) State four importance of marketing.\n(b) List and explain three marketing activities.", "marks": Decimal("8.00")},
    {"stem": "3. (a) Define farm records.\n(b) Explain four importance of keeping farm records.", "marks": Decimal("8.00")},
    {"stem": "4. Explain the following journal: (a) Sales journal (b) Purchase journal (c) Returned outward journal.", "marks": Decimal("8.00")},
    {"stem": "5. Explain the following types of farm records: (a) Profit and loss account (b) Input record (c) Farm inventory.", "marks": Decimal("8.00")},
    {"stem": "6. Explain soil fertility and state four methods of improving soil fertility.", "marks": Decimal("8.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
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
            source_reference=f"JS3-AGR-20260323-OBJ-{index:02d}",
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
            source_reference=f"JS3-AGR-20260323-TH-{index:02d}",
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
        "paper_code": "JS3-AGR-EXAM",
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
        "schedule_start": exam.schedule_start.isoformat(),
        "schedule_end": exam.schedule_end.isoformat(),
        "duration_minutes": blueprint.duration_minutes,
        "objective_questions": len(OBJECTIVES),
        "theory_questions": len(THEORY),
    })

main()
