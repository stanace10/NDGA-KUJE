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


TITLE = "WED 9:45-11:00 JS2 Home Economics Second Term Exam"
DESCRIPTION = "JSS2 HOME ECONOMICS SECOND TERM EXAMINATION"
BANK_NAME = "JS2 Home Economics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 11:00 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Pattern drafting refers to the ______.", "options": {"A": "decoration of clothes", "B": "drawing of garment shapes on paper using measurements", "C": "sewing of garments", "D": "cutting of fabrics without measurement"}, "answer": "B"},
    {"stem": "A pattern can best be described as a ______.", "options": {"A": "finished garment", "B": "sewing machine", "C": "paper template for cutting fabric", "D": "needle and thread"}, "answer": "C"},
    {"stem": "One major importance of pattern drafting is that it ______.", "options": {"A": "wastes materials", "B": "delays garment making", "C": "ensures good fitting of garments", "D": "destroys fabrics"}, "answer": "C"},
    {"stem": "Which of the following is regarded as a basic pattern?", "options": {"A": "Pocket pattern", "B": "Collar pattern", "C": "Skirt pattern", "D": "Cuff pattern"}, "answer": "C"},
    {"stem": "A bodice pattern is mainly used for the ______.", "options": {"A": "waist alone", "B": "lower part of the body", "C": "upper part of the body", "D": "hip region"}, "answer": "C"},
    {"stem": "The skirt pattern covers the body area from the ______.", "options": {"A": "shoulder to waist", "B": "waist to knee", "C": "neck to chest", "D": "arm to wrist"}, "answer": "B"},
    {"stem": "One tool commonly used in pattern drafting is the ______.", "options": {"A": "cooking pot", "B": "spoon", "C": "measuring tape", "D": "frying pan"}, "answer": "C"},
    {"stem": "Pattern drafting helps to ______.", "options": {"A": "improve accuracy and neatness", "B": "waste time", "C": "reduce garment quality", "D": "spoil clothing materials"}, "answer": "A"},
    {"stem": "The first step in drafting a basic bodice is to ______.", "options": {"A": "sew the fabric", "B": "cut out the pattern", "C": "take correct body measurements", "D": "iron the fabric"}, "answer": "C"},
    {"stem": "The waistline on a bodice pattern indicates the ______.", "options": {"A": "bust level", "B": "shoulder line", "C": "hip level", "D": "waist position"}, "answer": "D"},
    {"stem": "Snacks are foods eaten ______.", "options": {"A": "as breakfast only", "B": "between main meals", "C": "only at night", "D": "once in a week"}, "answer": "B"},
    {"stem": "Which of the following is an example of a snack?", "options": {"A": "Rice and stew", "B": "Soup", "C": "Chin chin", "D": "Pounded yam"}, "answer": "C"},
    {"stem": "Snacks are important because they ______.", "options": {"A": "replace main meals", "B": "cause illness", "C": "supply energy between meals", "D": "reduce appetite"}, "answer": "C"},
    {"stem": "Chin chin belongs to the group of ______.", "options": {"A": "boiled snacks", "B": "baked snacks", "C": "steamed foods", "D": "roasted foods"}, "answer": "B"},
    {"stem": "An important ingredient used in making chin chin is ______.", "options": {"A": "vegetables", "B": "flour", "C": "pepper", "D": "fish"}, "answer": "B"},
    {"stem": "Another ingredient commonly used for chin chin is ______.", "options": {"A": "leaves", "B": "sugar", "C": "yam", "D": "salt water only"}, "answer": "B"},
    {"stem": "Snacks should always be ______.", "options": {"A": "prepared carelessly", "B": "unhygienic", "C": "hygienically prepared", "D": "overcooked"}, "answer": "C"},
    {"stem": "Practical lessons on snacks help students to ______.", "options": {"A": "avoid cooking", "B": "spoil food", "C": "waste ingredients", "D": "develop cooking skills"}, "answer": "D"},
    {"stem": "Washing up after meals involves ______.", "options": {"A": "serving food", "B": "cleaning plates and utensils", "C": "cooking meals", "D": "buying ingredients"}, "answer": "B"},
    {"stem": "One guideline for washing up after meals is to ______.", "options": {"A": "store dirty plates", "B": "leave utensils till next day", "C": "wash utensils immediately after use", "D": "mix clean and dirty plates"}, "answer": "C"},
    {"stem": "Proper serving of meals helps to ______.", "options": {"A": "discourage eating", "B": "make food attractive", "C": "waste food", "D": "delay digestion"}, "answer": "B"},
    {"stem": "Meals should be served ______.", "options": {"A": "anyhow", "B": "uncovered", "C": "late", "D": "neatly and attractively"}, "answer": "D"},
    {"stem": "Which of the following is a method of cooking food?", "options": {"A": "Sweeping", "B": "Washing", "C": "Boiling", "D": "Slicing"}, "answer": "C"},
    {"stem": "Frying as a cooking method mainly uses ______.", "options": {"A": "air", "B": "water", "C": "oil", "D": "steam"}, "answer": "C"},
    {"stem": "Steaming food is important because it ______ nutrients.", "options": {"A": "destroys", "B": "preserves", "C": "burns", "D": "spoils"}, "answer": "B"},
    {"stem": "Food hygiene means ______.", "options": {"A": "eating plenty food", "B": "cooking food quickly", "C": "eating raw food", "D": "keeping food clean and safe"}, "answer": "D"},
    {"stem": "One importance of food hygiene is that it ______.", "options": {"A": "causes sickness", "B": "prevents food poisoning", "C": "wastes food", "D": "delays cooking"}, "answer": "B"},
    {"stem": "Washing hands before handling food helps to ______.", "options": {"A": "add flavour", "B": "remove germs", "C": "reduce appetite", "D": "spoil food"}, "answer": "B"},
    {"stem": "A good guideline for food hygiene is to ______.", "options": {"A": "leave food uncovered", "B": "use dirty utensils", "C": "cover food properly", "D": "store food near refuse"}, "answer": "C"},
    {"stem": "Food nutrients are substances that ______.", "options": {"A": "spoil food", "B": "add colour to food", "C": "nourish the body", "D": "cause illness"}, "answer": "C"},
    {"stem": "Which of the following is a body-building nutrient?", "options": {"A": "Carbohydrate", "B": "Protein", "C": "Fat", "D": "Water"}, "answer": "B"},
    {"stem": "The main function of carbohydrates in the body is to ______.", "options": {"A": "build tissues", "B": "supply energy", "C": "protect organs", "D": "form bones"}, "answer": "B"},
    {"stem": "Protein is needed in the body to ______.", "options": {"A": "provide vitamins", "B": "prevent thirst", "C": "build and repair tissues", "D": "digest food"}, "answer": "C"},
    {"stem": "A disease caused by lack of protein is ______.", "options": {"A": "rickets", "B": "scurvy", "C": "kwashiorkor", "D": "beriberi"}, "answer": "C"},
    {"stem": "Deficiency of vitamin C leads to ______.", "options": {"A": "night blindness", "B": "rickets", "C": "scurvy", "D": "goitre"}, "answer": "C"},
    {"stem": "Rickets is caused by lack of ______.", "options": {"A": "vitamin A", "B": "protein", "C": "vitamin C", "D": "vitamin D"}, "answer": "D"},
    {"stem": "One sign of kwashiorkor is ______.", "options": {"A": "strong muscles", "B": "swollen stomach", "C": "clear skin", "D": "good appetite"}, "answer": "B"},
    {"stem": "Minerals are important in the body for ______.", "options": {"A": "energy only", "B": "bone and teeth formation", "C": "digestion only", "D": "taste"}, "answer": "B"},
    {"stem": "Iron deficiency in the body can lead to ______.", "options": {"A": "scurvy", "B": "obesity", "C": "anaemia", "D": "rickets"}, "answer": "C"},
    {"stem": "A balanced diet helps to ______.", "options": {"A": "weaken the body", "B": "cause diseases", "C": "reduce growth", "D": "promote good health"}, "answer": "D"},
]

THEORY = [
    {"stem": "1. (a) Define pattern drafting.\n(b) State three importance of pattern drafting.", "marks": Decimal('10.00')},
    {"stem": "2. (a) State three types of snacks.\n(b) List two main ingredients used in making puff-puff.", "marks": Decimal('10.00')},
    {"stem": "3. State five guidelines for washing up after meals.", "marks": Decimal('10.00')},
    {"stem": "4. Explain five guidelines for serving meals properly.", "marks": Decimal('10.00')},
    {"stem": "5. (a) Define food hygiene.\n(b) State three importance of food hygiene.", "marks": Decimal('10.00')},
    {"stem": "6. (a) What are food nutrients?\n(b) State one function and one deficiency disease of any three nutrients.", "marks": Decimal('10.00')},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="HEC")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="nwachukwu@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 9, 45, tzinfo=lagos)
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
            "dean_review_comment": "Approved for Wednesday morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 9:45 AM WAT.",
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
    exam.dean_review_comment = "Approved for Wednesday morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 9:45 AM WAT."
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
            source_reference=f"JS2-HEC-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS2-HEC-20260325-TH-{index:02d}",
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
        "paper_code": "JS2-HEC-EXAM",
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
