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


TITLE = "MON 1:15-2:15 JS1 Livestock Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: JSS1 SUBJECT: LIVESTOCK FARMING"
BANK_NAME = "JS1 Livestock Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all theory questions shown. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Which of the following is a poultry bird?", "options": {"A": "Goat", "B": "Sheep", "C": "fowl", "D": "Rabbit"}, "answer": "C"},
    {"stem": "2. The hard mouth part of poultry used for eating is called", "options": {"A": "comb", "B": "beak", "C": "wattle", "D": "spur"}, "answer": "B"},
    {"stem": "3. The comb of a chicken is found on the", "options": {"A": "wing", "B": "leg", "C": "head", "D": "tail"}, "answer": "C"},
    {"stem": "4. Feathers in poultry are mainly used for", "options": {"A": "walking", "B": "breathing", "C": "protection and warmth", "D": "feeding"}, "answer": "C"},
    {"stem": "5. The legs of poultry are covered with", "options": {"A": "fur", "B": "hair", "C": "scales", "D": "skin"}, "answer": "C"},
    {"stem": "6. Which of the following helps poultry to fly short distances?", "options": {"A": "Beak", "B": "Wing", "C": "Comb", "D": "Wattle"}, "answer": "B"},
    {"stem": "7. Equipment used for feeding poultry is called", "options": {"A": "drinker", "B": "feeder", "C": "brooder", "D": "cage"}, "answer": "B"},
    {"stem": "8. A poultry drinker is used for", "options": {"A": "bathing birds", "B": "feeding birds", "C": "giving water to birds", "D": "storing feed"}, "answer": "C"},
    {"stem": "9. A brooder is mainly used for", "options": {"A": "adult birds", "B": "sick birds", "C": "young chicks", "D": "laying eggs"}, "answer": "C"},
    {"stem": "10. Which of the following is used for housing poultry?", "options": {"A": "Pen", "B": "Coop", "C": "Cage", "D": "All of the above"}, "answer": "D"},
    {"stem": "11. Maize belongs to which class of feed?", "options": {"A": "protein", "B": "energy", "C": "mineral", "D": "vitamin"}, "answer": "B"},
    {"stem": "12. Feed ingredients that help in growth and repair are", "options": {"A": "carbohydrates", "B": "fats", "C": "proteins", "D": "minerals"}, "answer": "C"},
    {"stem": "13. Which of the following is a protein feed?", "options": {"A": "Maize", "B": "Fish meal", "C": "Cassava", "D": "Rice"}, "answer": "B"},
    {"stem": "14. Major feed ingredients are those that", "options": {"A": "are rarely used", "B": "form a large part of feed", "C": "are expensive", "D": "cure diseases"}, "answer": "B"},
    {"stem": "15. Which of these is a major feed ingredient?", "options": {"A": "Maize", "B": "Salt", "C": "Vitamins", "D": "Premix"}, "answer": "A"},
    {"stem": "16. Minor feed ingredients are added mainly to", "options": {"A": "replace water", "B": "improve feed quality", "C": "increase feed quantity", "D": "stop feeding"}, "answer": "B"},
    {"stem": "17. A female rabbit is called", "options": {"A": "buck", "B": "doe", "C": "ewe", "D": "sow"}, "answer": "B"},
    {"stem": "18. A male rabbit is called", "options": {"A": "buck", "B": "ram", "C": "bull", "D": "cock"}, "answer": "A"},
    {"stem": "19. Which of the following is a breed of rabbit?", "options": {"A": "New Zealand White", "B": "White Fulani", "C": "Rhode Island Red", "D": "Sokoto Red"}, "answer": "A"},
    {"stem": "20. Rabbits are mainly reared for", "options": {"A": "milk", "B": "eggs", "C": "meat", "D": "wool only"}, "answer": "C"},
    {"stem": "21. Rabbits feed mainly on", "options": {"A": "grass and vegetables", "B": "meat", "C": "grains only", "D": "insects"}, "answer": "A"},
    {"stem": "22. A goat is an example of", "options": {"A": "poultry", "B": "ruminant", "C": "reptile", "D": "rodent"}, "answer": "B"},
    {"stem": "23. The male goat is called", "options": {"A": "ram", "B": "buck", "C": "bull", "D": "boar"}, "answer": "B"},
    {"stem": "24. The female goat is called", "options": {"A": "ewe", "B": "doe", "C": "sow", "D": "hen"}, "answer": "B"},
    {"stem": "25. West African Dwarf is a breed of", "options": {"A": "sheep", "B": "cattle", "C": "goat", "D": "rabbit"}, "answer": "C"},
    {"stem": "26. One major challenge of goat and sheep production is", "options": {"A": "good feeding", "B": "disease", "C": "improved breeds", "D": "veterinary services"}, "answer": "B"},
    {"stem": "27. Lack of good housing can lead to", "options": {"A": "rapid growth", "B": "disease outbreak", "C": "good health", "D": "more meat"}, "answer": "B"},
    {"stem": "28. Theft of animals is an example of", "options": {"A": "biological problem", "B": "management problem", "C": "economic challenge", "D": "nutritional benefit"}, "answer": "B"},
    {"stem": "29. Poor feeding causes", "options": {"A": "fast growth", "B": "good reproduction", "C": "poor growth", "D": "high milk yield"}, "answer": "C"},
    {"stem": "30. Water is important to goats and sheep because it", "options": {"A": "reduces growth", "B": "aids digestion", "C": "causes sickness", "D": "stops feeding"}, "answer": "B"},
    {"stem": "31. One importance of livestock is", "options": {"A": "pollution", "B": "protein supply", "C": "erosion", "D": "deforestation"}, "answer": "B"},
    {"stem": "32. Which of the following animals lays eggs?", "options": {"A": "Goat", "B": "Rabbit", "C": "Chicken", "D": "Sheep"}, "answer": "C"},
    {"stem": "33. The food given to animals is called", "options": {"A": "manure", "B": "feed", "C": "medicine", "D": "bedding"}, "answer": "B"},
    {"stem": "34. Which feed nutrient supplies energy?", "options": {"A": "protein", "B": "vitamins", "C": "carbohydrates", "D": "minerals"}, "answer": "C"},
    {"stem": "35. Animals kept for meat production include", "options": {"A": "goats", "B": "fish", "C": "poultry", "D": "all of the above"}, "answer": "D"},
    {"stem": "36. One benefit of rearing rabbits is that they", "options": {"A": "grow slowly", "B": "eat much feed", "C": "reproduce fast", "D": "are difficult to manage"}, "answer": "C"},
    {"stem": "37. Good management of livestock leads to", "options": {"A": "losses", "B": "poor health", "C": "high productivity", "D": "diseases"}, "answer": "C"},
    {"stem": "38. Which of these animals is not a mammal?", "options": {"A": "Rabbit", "B": "Goat", "C": "Turkey", "D": "Sheep"}, "answer": "C"},
    {"stem": "39. Which of the following is not a poultry equipment?", "options": {"A": "Sickle", "B": "Drinker", "C": "Feeder", "D": "Brooder"}, "answer": "A"},
    {"stem": "40. A male fowl below one year of age is called", "options": {"A": "Pullet", "B": "Capon", "C": "Cockerel", "D": "Doe"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. (a) What is poultry production?\n(b) State three importance of poultry farming.", "marks": Decimal("7.00")},
    {"stem": "2. (a) List four major feed ingredients for poultry.\n(b) Mention three poultry equipments and state their uses.", "marks": Decimal("7.00")},
    {"stem": "3. (a) List four signs of illness in goat.\n(b) Mention four ways of preventing diseases in goat.", "marks": Decimal("7.00")},
    {"stem": "4. (a) List three breeds of rabbit.\n(b) List four feeds eaten by rabbits.", "marks": Decimal("6.00")},
    {"stem": "5. State the meaning of the following terminologies used in rabbit: Buck, Doe, Hutch, Litter, Breed.", "marks": Decimal("6.00")},
    {"stem": "6. (a) State three challenges facing goat and sheep production.\n(b) Mention two feed stuffs eaten by goat and sheep.", "marks": Decimal("7.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="LIV")
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
            source_reference=f"JS1-LIV-20260323-OBJ-{index:02d}",
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
            source_reference=f"JS1-LIV-20260323-TH-{index:02d}",
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
        "paper_code": "JS1-LIV-EXAM",
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
