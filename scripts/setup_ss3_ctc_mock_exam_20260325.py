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


TITLE = "WED 9:41-11:00 SS3 Catering Craft Practice Mock Exam"
DESCRIPTION = "SS3 CATERING CRAFT PRACTICE SECOND TERM MOCK EXAMINATION"
BANK_NAME = "SS3 Catering Craft Practice Mock Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 70 minutes. Exam window closes at 11:00 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "A suitable meal for an invalid should be ______.", "options": {"A": "easily digestible", "B": "heavily spiced", "C": "fried", "D": "very oily"}, "answer": "A"},
    {"stem": "A convalescent requires food that promotes ______.", "options": {"A": "weight loss", "B": "quick recovery", "C": "fasting", "D": "appetite suppression"}, "answer": "B"},
    {"stem": "An example of a clear soup suitable for invalids is ______.", "options": {"A": "egusi soup", "B": "vegetable soup", "C": "consomme", "D": "ogbono soup"}, "answer": "C"},
    {"stem": "Liquid diets are mainly given to patients who ______.", "options": {"A": "can chew properly", "B": "need more fibre", "C": "cannot tolerate solid food", "D": "prefer snacks"}, "answer": "C"},
    {"stem": "A soft diet may include ______.", "options": {"A": "roasted meat", "B": "mashed potatoes", "C": "fried plantain", "D": "grilled fish"}, "answer": "B"},
    {"stem": "Breast milk is ideal for infants because it ______.", "options": {"A": "is difficult to digest", "B": "contains natural antibodies", "C": "is expensive", "D": "lacks nutrients"}, "answer": "B"},
    {"stem": "Complementary feeding normally begins at ______.", "options": {"A": "six months", "B": "one year", "C": "three months", "D": "two months"}, "answer": "A"},
    {"stem": "Adolescents need more nutrients because of ______.", "options": {"A": "aging", "B": "inactivity", "C": "rapid growth", "D": "illness"}, "answer": "C"},
    {"stem": "Iron deficiency in adolescents may lead to ______.", "options": {"A": "rickets", "B": "obesity", "C": "anaemia", "D": "scurvy"}, "answer": "C"},
    {"stem": "Adults engaged in heavy labour require more ______.", "options": {"A": "vitamins", "B": "fibre", "C": "energy", "D": "water only"}, "answer": "C"},
    {"stem": "A vegan avoids ______.", "options": {"A": "meat only", "B": "milk only", "C": "eggs only", "D": "all animal products"}, "answer": "D"},
    {"stem": "Lacto-ovo vegetarians consume ______.", "options": {"A": "vegetables only", "B": "cereals only", "C": "eggs and milk", "D": "fish"}, "answer": "C"},
    {"stem": "A good plant protein combination is ______.", "options": {"A": "rice and beans", "B": "beef and fish", "C": "chicken and egg", "D": "milk and meat"}, "answer": "A"},
    {"stem": "Overcooking vegetables results in ______.", "options": {"A": "improved nutrients", "B": "nutrient loss", "C": "protein increase", "D": "fat increase"}, "answer": "B"},
    {"stem": "A diabetic patient should avoid ______.", "options": {"A": "excessive sugar", "B": "vegetables", "C": "fibre", "D": "water"}, "answer": "A"},
    {"stem": "A convalescent diet should be ______.", "options": {"A": "coarse", "B": "stale", "C": "nourishing and light", "D": "spicy"}, "answer": "C"},
    {"stem": "An example of semi-solid food is ______.", "options": {"A": "tea", "B": "pap", "C": "water", "D": "broth"}, "answer": "B"},
    {"stem": "Infants require frequent feeding because ______.", "options": {"A": "they dislike food", "B": "they grow rapidly", "C": "they sleep often", "D": "they overeat"}, "answer": "B"},
    {"stem": "Balanced diet contains ______.", "options": {"A": "only protein", "B": "only carbohydrate", "C": "only fat", "D": "all classes of food"}, "answer": "D"},
    {"stem": "A bland diet is recommended for ______.", "options": {"A": "athletes", "B": "ulcer patients", "C": "healthy adults", "D": "chefs"}, "answer": "B"},
    {"stem": "Menu planning should consider ______.", "options": {"A": "cost and nutrition", "B": "cook's mood", "C": "religion only", "D": "colour of plates"}, "answer": "A"},
    {"stem": "Garnishing improves the ______ of food.", "options": {"A": "taste only", "B": "appearance", "C": "cost", "D": "weight"}, "answer": "B"},
    {"stem": "Food hygiene is important to prevent ______.", "options": {"A": "flavour", "B": "appetite", "C": "contamination", "D": "decoration"}, "answer": "C"},
    {"stem": "Time management in practical means ______.", "options": {"A": "rushing", "B": "delaying", "C": "planning properly", "D": "ignoring instructions"}, "answer": "C"},
    {"stem": "A liquid diet is often served ______.", "options": {"A": "to invalids", "B": "to athletes", "C": "to chefs", "D": "to waiters"}, "answer": "A"},
    {"stem": "Vitamin C helps in ______.", "options": {"A": "fat storage", "B": "bone growth", "C": "wound healing", "D": "dehydration"}, "answer": "C"},
    {"stem": "Adolescents need calcium for ______.", "options": {"A": "weak bones", "B": "strong bones", "C": "poor appetite", "D": "fatigue"}, "answer": "B"},
    {"stem": "A vegetarian may lack ______.", "options": {"A": "vitamin B12", "B": "carbohydrate", "C": "fibre", "D": "vitamin C"}, "answer": "A"},
    {"stem": "An adult's diet depends on ______.", "options": {"A": "clothing", "B": "occupation", "C": "hairstyle", "D": "hobbies"}, "answer": "B"},
    {"stem": "Proper revision helps students to ______.", "options": {"A": "forget topics", "B": "improve understanding", "C": "fear exams", "D": "avoid practice"}, "answer": "B"},
    {"stem": "A convalescent meal should be ______.", "options": {"A": "attractive", "B": "burnt", "C": "stale", "D": "very hot"}, "answer": "A"},
    {"stem": "Infant food should be ______.", "options": {"A": "contaminated", "B": "clean and safe", "C": "very spicy", "D": "oily"}, "answer": "B"},
    {"stem": "Protein is essential for ______.", "options": {"A": "tissue repair", "B": "sweating", "C": "sleeping", "D": "dancing"}, "answer": "A"},
    {"stem": "High fibre diets help prevent ______.", "options": {"A": "malaria", "B": "fever", "C": "constipation", "D": "infection"}, "answer": "C"},
    {"stem": "A lacto-vegetarian consumes ______.", "options": {"A": "fish", "B": "meat", "C": "milk", "D": "poultry"}, "answer": "C"},
    {"stem": "Special meals for invalids should be served ______.", "options": {"A": "untidily", "B": "hurriedly", "C": "attractively", "D": "roughly"}, "answer": "C"},
    {"stem": "Energy-giving foods are mainly ______.", "options": {"A": "carbohydrates", "B": "vitamins", "C": "minerals", "D": "water"}, "answer": "A"},
    {"stem": "A practical test marking scheme ensures ______.", "options": {"A": "bias", "B": "fairness", "C": "confusion", "D": "delay"}, "answer": "B"},
    {"stem": "Infants should avoid ______.", "options": {"A": "clean water", "B": "mashed fruits", "C": "contaminated food", "D": "breast milk"}, "answer": "C"},
    {"stem": "Balanced vegetarian meals combine ______.", "options": {"A": "oil and sugar", "B": "cereals and legumes", "C": "meat and fish", "D": "eggs and beef"}, "answer": "B"},
    {"stem": "Hygiene in catering includes ______.", "options": {"A": "dirty aprons", "B": "hand washing", "C": "uncovered hair", "D": "unclean utensils"}, "answer": "B"},
    {"stem": "A suitable snack for adolescents is ______.", "options": {"A": "soft drinks only", "B": "fried chips only", "C": "sweets only", "D": "bread and egg"}, "answer": "D"},
    {"stem": "The first step in any examination is ______.", "options": {"A": "cooking immediately", "B": "reading instructions", "C": "serving food", "D": "washing plates"}, "answer": "B"},
    {"stem": "Convalescents require extra ______.", "options": {"A": "spices", "B": "alcohol", "C": "nutrients", "D": "fat"}, "answer": "C"},
    {"stem": "Menu evaluation helps in ______.", "options": {"A": "quality control", "B": "confusion", "C": "waste", "D": "delay"}, "answer": "A"},
    {"stem": "Dehydration can be prevented by ______.", "options": {"A": "excess oil", "B": "adequate fluids", "C": "fried food", "D": "sugar"}, "answer": "B"},
    {"stem": "A soft diet excludes ______.", "options": {"A": "roasted meat", "B": "mashed yam", "C": "custard", "D": "pap"}, "answer": "A"},
    {"stem": "The aim of special meals is to ______.", "options": {"A": "entertain guests", "B": "restore health", "C": "increase cost", "D": "decorate tables"}, "answer": "B"},
    {"stem": "Elderly adults need a ______.", "options": {"A": "moderate balanced diet", "B": "junk food", "C": "spicy food", "D": "heavy meal"}, "answer": "A"},
    {"stem": "Test interpretation helps to ______.", "options": {"A": "lower standards", "B": "ensure objective grading", "C": "encourage bias", "D": "waste time"}, "answer": "B"},
    {"stem": "Complementary foods should be ______.", "options": {"A": "stale", "B": "unsafe", "C": "nutritious", "D": "oily"}, "answer": "C"},
    {"stem": "Adults doing sedentary work need ______.", "options": {"A": "moderate calories", "B": "excessive calories", "C": "fasting", "D": "junk food"}, "answer": "A"},
    {"stem": "Presentation of food affects ______.", "options": {"A": "appetite", "B": "infection", "C": "contamination", "D": "spoilage"}, "answer": "A"},
    {"stem": "Infants require protein for ______.", "options": {"A": "decoration", "B": "growth", "C": "sweating", "D": "dancing"}, "answer": "B"},
    {"stem": "A vegetarian protein source is ______.", "options": {"A": "beans", "B": "beef", "C": "chicken", "D": "fish"}, "answer": "A"},
    {"stem": "Planning before cooking helps to ______.", "options": {"A": "waste time", "B": "burn food", "C": "reduce efficiency", "D": "save time"}, "answer": "D"},
    {"stem": "Revision before exams ______.", "options": {"A": "weakens knowledge", "B": "strengthens confidence", "C": "causes fear", "D": "wastes effort"}, "answer": "B"},
    {"stem": "An invalid should avoid ______.", "options": {"A": "light soup", "B": "fruit juice", "C": "heavy fried foods", "D": "soft diet"}, "answer": "C"},
    {"stem": "Adolescents require iron to prevent ______.", "options": {"A": "obesity", "B": "scurvy", "C": "anaemia", "D": "rickets"}, "answer": "C"},
    {"stem": "A balanced diet must contain ______.", "options": {"A": "one nutrient", "B": "two nutrients", "C": "three nutrients", "D": "all essential nutrients"}, "answer": "D"},
]

THEORY = [
    {"stem": "1. (a) Define special meals.\n(b) State and explain four characteristics of meals prepared for invalids.", "marks": Decimal("10.00")},
    {"stem": "2. (a) Who is a convalescent?\n(b) Discuss four nutritional requirements of a convalescent patient.", "marks": Decimal("10.00")},
    {"stem": "3. (a) Define complementary feeding.\n(b) Outline four guidelines for feeding infants safely.", "marks": Decimal("10.00")},
    {"stem": "4. (a) State three nutritional needs of adolescents.\n(b) Explain four factors that influence meal planning for adolescents.", "marks": Decimal("10.00")},
    {"stem": "5. (a) Define vegetarianism.\n(b) Describe four types of vegetarian diets.", "marks": Decimal("10.00")},
    {"stem": "6. (a) What is menu planning?\n(b) Discuss four principles to consider when planning special meals.", "marks": Decimal("10.00")},
    {"stem": "7. (a) Explain the meaning of a balanced diet.\n(b) List and explain four classes of food and their functions.", "marks": Decimal("10.00")},
    {"stem": "8. (a) Define test interpretation in catering practical examinations.\n(b) State four reasons why marking schemes are important in practical tests.", "marks": Decimal("10.00")},
    {"stem": "9. (a) State three hygiene practices necessary when preparing special meals.\n(b) Explain four consequences of poor food hygiene.", "marks": Decimal("10.00")},
    {"stem": "10. (a) Define energy-giving foods.\n(b) Discuss four factors that determine the energy requirements of adults.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="CTC")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="regina@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 9, 41, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 11, 0, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Wednesday morning mock paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 9:41 AM WAT.",
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
    exam.dean_review_comment = "Approved for Wednesday morning mock paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 9:41 AM WAT."
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
            rich_stem=item["stem"],
            marks=Decimal("1.00"),
            source_reference=f"SS3-CTC-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS3-CTC-20260325-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 70
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-CTC-MOCK",
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
