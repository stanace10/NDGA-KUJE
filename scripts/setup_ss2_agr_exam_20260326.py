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

TITLE = "THU 9:30-11:30 SS2 Agricultural Science Second Term Exam"
DESCRIPTION = "SS2 AGRICULTURAL SCIENCE SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Agricultural Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Which of the following best defines range land?", "options": {"A": "Land used for crop production", "B": "Land supporting grasses and legumes for grazing", "C": "Land used for fish farming", "D": "Land used for forestry"}, "answer": "B"},
    {"stem": "The practice of controlling the number of animals grazing on a pasture is called:", "options": {"A": "Rotational cropping", "B": "Stocking rate", "C": "Mulching", "D": "Tethering"}, "answer": "B"},
    {"stem": "A major advantage of rotational grazing is that it:", "options": {"A": "Encourages overgrazing", "B": "Allows uniform grazing", "C": "Prevents weed control", "D": "Reduces forage growth"}, "answer": "B"},
    {"stem": "The method of improving range land by planting desirable grasses is known as:", "options": {"A": "Fertilization", "B": "Tethering", "C": "Trampling", "D": "Reseeding"}, "answer": "D"},
    {"stem": "Overgrazing results in:", "options": {"A": "Increase in soil fertility", "B": "Soil erosion", "C": "Increase in vegetation cover", "D": "None of the above"}, "answer": "B"},
    {"stem": "The type of grazing where animals are moved from one paddock to another is:", "options": {"A": "Free-range grazing", "B": "Rotational grazing", "C": "Zero grazing", "D": "Strip grazing"}, "answer": "B"},
    {"stem": "Which of the following is a sign of good pasture?", "options": {"A": "Presence of shrubs", "B": "High weed population", "C": "High density of palatable grasses", "D": "Bare soil patches"}, "answer": "C"},
    {"stem": "Controlled burning on rangeland helps to:", "options": {"A": "Kill beneficial organisms", "B": "Encourage new grass growth", "C": "Reduce soil fertility", "D": "Reduce pasture yield"}, "answer": "B"},
    {"stem": "The ratio of animals to the grazing area is called:", "options": {"A": "Stocking rate", "B": "Stocking density", "C": "Carrying capacity", "D": "Animal unit"}, "answer": "A"},
    {"stem": "Which nutrient supplies the highest amount of energy?", "options": {"A": "Proteins", "B": "Lipids", "C": "Vitamins", "D": "Minerals"}, "answer": "B"},
    {"stem": "Which of the following is a carbohydrate-rich feed?", "options": {"A": "Groundnut cake", "B": "Fish meal", "C": "Maize", "D": "Bone meal"}, "answer": "C"},
    {"stem": "A deficiency of vitamin A causes:", "options": {"A": "Blindness", "B": "Rickets", "C": "Anaemia", "D": "Muscle paralysis"}, "answer": "A"},
    {"stem": "The most important nutrient for tissue building is:", "options": {"A": "Carbohydrates", "B": "Water", "C": "Proteins", "D": "Minerals"}, "answer": "C"},
    {"stem": "Green forages are good sources of:", "options": {"A": "Vitamins", "B": "Calcium", "C": "Fats", "D": "Salt"}, "answer": "A"},
    {"stem": "Which of the following is an example of animal protein feed?", "options": {"A": "Fish meal", "B": "Cassava peels", "C": "Sorghum", "D": "Wheat bran"}, "answer": "A"},
    {"stem": "Roughages are feeds that are:", "options": {"A": "High in fibre", "B": "High in protein", "C": "Low in water", "D": "Low in fibre"}, "answer": "A"},
    {"stem": "One function of water in animal nutrition is:", "options": {"A": "Building of bones", "B": "Transporting nutrients", "C": "Providing energy", "D": "Supplying nitrogen"}, "answer": "B"},
    {"stem": "A ration is defined as the:", "options": {"A": "Total feed eaten in a day", "B": "Amount of feed eaten in one week", "C": "Feed mixed with water", "D": "Total feed consumed in a month"}, "answer": "A"},
    {"stem": "A balanced ration must contain:", "options": {"A": "Mainly proteins", "B": "All nutrients in correct proportion", "C": "Only carbohydrates and vitamins", "D": "Only water and minerals"}, "answer": "B"},
    {"stem": "A production ration is fed to animals to:", "options": {"A": "Maintain their weight", "B": "Increase milk, meat or egg yield", "C": "Reduce body size", "D": "Help them sleep"}, "answer": "B"},
    {"stem": "Maintenance ration is required for:", "options": {"A": "Pregnant animals", "B": "Animals producing milk", "C": "Animals not gaining or losing weight", "D": "Fast-growing animals"}, "answer": "C"},
    {"stem": "One factor affecting ration formulation is:", "options": {"A": "Colour of feed", "B": "Cost of feed ingredients", "C": "Weight of feedbag", "D": "Time of the day"}, "answer": "B"},
    {"stem": "A ration high in energy but low in fibre is classified as:", "options": {"A": "Roughage", "B": "Concentrate", "C": "Silage", "D": "Hay"}, "answer": "B"},
    {"stem": "Feeds preserved through fermentation are called:", "options": {"A": "Silage", "B": "Hay", "C": "Meal", "D": "Concentrate"}, "answer": "A"},
    {"stem": "Which feedstuff is commonly used as a protein supplement?", "options": {"A": "Urea", "B": "Rice bran", "C": "Soybean meal", "D": "Yam peels"}, "answer": "C"},
    {"stem": "The energy requirement of a farm animal depends on:", "options": {"A": "Age", "B": "Colour", "C": "Breed", "D": "Season"}, "answer": "A"},
    {"stem": "Which ration is needed for pregnant animals?", "options": {"A": "Fatting ration", "B": "Lactation ration", "C": "Gestation ration", "D": "Maintenance ration"}, "answer": "C"},
    {"stem": "Which of the following is an abiotic factor?", "options": {"A": "Soil", "B": "Earthworm", "C": "Fungi", "D": "Goat"}, "answer": "A"},
    {"stem": "High temperature in crops generally leads to:", "options": {"A": "Reduced transpiration", "B": "Wilting", "C": "Increased soil moisture", "D": "Increase in crop yield"}, "answer": "B"},
    {"stem": "Wind is beneficial to crops because it:", "options": {"A": "Helps pollination", "B": "Causes lodging", "C": "Increases erosion", "D": "Breaks stems"}, "answer": "A"},
    {"stem": "Soil pH affects:", "options": {"A": "Plant height", "B": "Nutrient availability", "C": "Cloud formation", "D": "Wind speed"}, "answer": "B"},
    {"stem": "Flooding on farmland may cause:", "options": {"A": "Increased aeration", "B": "Waterlogging", "C": "Soil hardening", "D": "Increased microbial activity"}, "answer": "B"},
    {"stem": "Which factor determines the type of crops grown in an area?", "options": {"A": "Soil type", "B": "Colour of leaves", "C": "Shape of land", "D": "Size of seeds"}, "answer": "A"},
    {"stem": "Nitrogen deficiency in plants causes:", "options": {"A": "Chlorosis", "B": "Purple leaves", "C": "Strong stems", "D": "Deep green leaves"}, "answer": "A"},
    {"stem": "Which nutrient promotes root development?", "options": {"A": "Nitrogen", "B": "Phosphorus", "C": "Sulphur", "D": "Iron"}, "answer": "B"},
    {"stem": "Which of these is a micronutrient?", "options": {"A": "Calcium", "B": "Magnesium", "C": "Zinc", "D": "Carbon"}, "answer": "C"},
    {"stem": "The cycle that involves conversion of ammonia to nitrate is called:", "options": {"A": "Water cycle", "B": "Nitrogen cycle", "C": "Carbon cycle", "D": "Mineral cycle"}, "answer": "B"},
    {"stem": "Which organism converts atmospheric nitrogen to nitrate?", "options": {"A": "Fungi", "B": "Nitrogen-fixing bacteria", "C": "Viruses", "D": "Protozoa"}, "answer": "B"},
    {"stem": "The release of carbon dioxide into the atmosphere during respiration is part of the:", "options": {"A": "Nitrogen cycle", "B": "Sulphur cycle", "C": "Water cycle", "D": "Carbon cycle"}, "answer": "D"},
    {"stem": "Organic matter decomposition adds ____ to the soil:", "options": {"A": "Humus", "B": "Gravel", "C": "Sand", "D": "Stones"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. (a) Explain briefly the term range land.\n(b) Enumerate five importance of rangeland to livestock.", "marks": Decimal("10.00")},
    {"stem": "2. List and discuss four methods of rangeland improvement.", "marks": Decimal("10.00")},
    {"stem": "3. Write short notes on the following:\n(a) Maintenance ration\n(b) Production ration\n(c) Balanced ration\n(d) Mal-nutrition", "marks": Decimal("10.00")},
    {"stem": "4. (a) State and explain three effects of feed shortage in animal production.\n(b) Mention four factors normally considered when deciding the type of feed an animal should be placed on.", "marks": Decimal("10.00")},
    {"stem": "5. (a) Mention four effects of drought on plant growth and development.\n(b) Discuss briefly three biotic factors that affect agricultural production.", "marks": Decimal("10.00")},
    {"stem": "6. (a) State two functions of each of the following macro-nutrients in plant nutrition:\n(i) Nitrogen\n(ii) Phosphorus\n(iii) Potassium\n(b) List four factors that affect the availability of nutrients to crops.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="AGR")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS2 Agricultural Science assignment found")
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
                source_reference=f"SS2-AGR-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS2-AGR-20260326-TH-{index:02d}",
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
            "paper_code": "SS2-AGR-EXAM",
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
