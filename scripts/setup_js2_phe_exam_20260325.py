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


TITLE = "WED 1:20-2:30 JS2 PHE Second Term Exam"
DESCRIPTION = "JSS2 PHYSICAL AND HEALTH EDUCATION SECOND TERM EXAMINATION"
BANK_NAME = "JS2 PHE Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 2:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "First aid is the ______.", "options": {"A": "final treatment given in hospital", "B": "immediate care given to an injured person", "C": "punishment for injuries", "D": "medical operation"}, "answer": "B"},
    {"stem": "The main aim of first aid is to ______.", "options": {"A": "delay treatment", "B": "prevent further injury", "C": "cause pain", "D": "replace a doctor"}, "answer": "B"},
    {"stem": "A first aid box should contain ______.", "options": {"A": "stones", "B": "bandages", "C": "food", "D": "toys"}, "answer": "B"},
    {"stem": "One safety rule at home is to ______.", "options": {"A": "leave sharp objects anywhere", "B": "run on wet floors", "C": "keep dangerous objects away from children", "D": "play with fire"}, "answer": "C"},
    {"stem": "An accident is an event that ______.", "options": {"A": "is planned", "B": "happens suddenly and causes injury", "C": "happens only in school", "D": "is enjoyable"}, "answer": "B"},
    {"stem": "A common cause of sports injuries is ______.", "options": {"A": "warming up properly", "B": "wearing protective equipment", "C": "carelessness", "D": "resting"}, "answer": "C"},
    {"stem": "A sprain affects the ______.", "options": {"A": "bone", "B": "muscle", "C": "ligaments", "D": "skin"}, "answer": "C"},
    {"stem": "The best immediate treatment for minor cuts is ______.", "options": {"A": "rubbing sand", "B": "washing with clean water", "C": "ignoring it", "D": "pouring oil"}, "answer": "B"},
    {"stem": "Personal health refers to ______.", "options": {"A": "caring for one's body", "B": "caring for animals", "C": "caring for teachers only", "D": "caring for visitors"}, "answer": "A"},
    {"stem": "One way of maintaining personal hygiene is ______.", "options": {"A": "bathing regularly", "B": "wearing dirty clothes", "C": "avoiding exercise", "D": "skipping meals"}, "answer": "A"},
    {"stem": "School health includes ______.", "options": {"A": "clean classrooms", "B": "dirty toilets", "C": "broken windows", "D": "scattered refuse"}, "answer": "A"},
    {"stem": "Community health deals with ______.", "options": {"A": "one person", "B": "family only", "C": "people in a community", "D": "school only"}, "answer": "C"},
    {"stem": "Environmental pollution means ______.", "options": {"A": "clean surroundings", "B": "contamination of the environment", "C": "farming activities", "D": "good sanitation"}, "answer": "B"},
    {"stem": "An example of air pollution is ______.", "options": {"A": "smoke from vehicles", "B": "clean water", "C": "fresh air", "D": "rainfall"}, "answer": "A"},
    {"stem": "Noise pollution can be caused by ______.", "options": {"A": "loud music", "B": "planting trees", "C": "sweeping", "D": "rainfall"}, "answer": "A"},
    {"stem": "One effect of pollution is ______.", "options": {"A": "good health", "B": "clean environment", "C": "spread of diseases", "D": "comfort"}, "answer": "C"},
    {"stem": "Non-communicable diseases are diseases that ______.", "options": {"A": "spread easily", "B": "cannot be transmitted", "C": "are caused by germs", "D": "are infectious"}, "answer": "B"},
    {"stem": "An example of a non-communicable disease is ______.", "options": {"A": "malaria", "B": "cholera", "C": "diabetes", "D": "typhoid"}, "answer": "C"},
    {"stem": "One cause of non-communicable diseases is ______.", "options": {"A": "balanced diet", "B": "regular exercise", "C": "unhealthy lifestyle", "D": "clean water"}, "answer": "C"},
    {"stem": "Obesity is caused by ______.", "options": {"A": "regular exercise", "B": "eating balanced diet", "C": "overeating and inactivity", "D": "bathing regularly"}, "answer": "C"},
    {"stem": "The human body is made up of ______.", "options": {"A": "one system", "B": "two systems", "C": "several systems", "D": "no system"}, "answer": "C"},
    {"stem": "The skeletal system helps to ______.", "options": {"A": "digest food", "B": "pump blood", "C": "support the body", "D": "remove waste"}, "answer": "C"},
    {"stem": "The muscular system helps in ______.", "options": {"A": "breathing", "B": "body movement", "C": "digestion", "D": "thinking"}, "answer": "B"},
    {"stem": "The circulatory system transports ______.", "options": {"A": "air", "B": "food only", "C": "blood", "D": "waste"}, "answer": "C"},
    {"stem": "Food is important because it ______.", "options": {"A": "causes sickness", "B": "provides energy", "C": "causes laziness", "D": "weakens the body"}, "answer": "B"},
    {"stem": "A balanced diet contains ______.", "options": {"A": "one food class", "B": "two food classes", "C": "all food classes", "D": "only carbohydrates"}, "answer": "C"},
    {"stem": "Protein is mainly needed for ______.", "options": {"A": "body building", "B": "energy only", "C": "protection", "D": "digestion"}, "answer": "A"},
    {"stem": "Deficiency of vitamins can cause ______.", "options": {"A": "fitness", "B": "diseases", "C": "strength", "D": "happiness"}, "answer": "B"},
    {"stem": "High jump is an athletic event that involves ______.", "options": {"A": "jumping over a bar", "B": "running long distances", "C": "throwing objects", "D": "swimming"}, "answer": "A"},
    {"stem": "One basic skill in high jump is ______.", "options": {"A": "take-off", "B": "dribbling", "C": "serving", "D": "passing"}, "answer": "A"},
    {"stem": "The landing area in high jump should be ______.", "options": {"A": "hard ground", "B": "concrete", "C": "soft and padded", "D": "muddy"}, "answer": "C"},
    {"stem": "The aim of high jump is to ______.", "options": {"A": "run fastest", "B": "jump highest without knocking the bar", "C": "throw far", "D": "jump longest"}, "answer": "B"},
    {"stem": "Wearing protective equipment helps to ______.", "options": {"A": "increase injury", "B": "prevent injury", "C": "cause pain", "D": "slow athletes"}, "answer": "B"},
    {"stem": "A safe environment helps to ______.", "options": {"A": "reduce accidents", "B": "increase pollution", "C": "spread diseases", "D": "cause fear"}, "answer": "A"},
    {"stem": "One way to prevent accidents in school is ______.", "options": {"A": "running on corridors", "B": "obeying safety rules", "C": "fighting", "D": "playing roughly"}, "answer": "B"},
    {"stem": "First aid should be given ______.", "options": {"A": "late", "B": "immediately", "C": "after many hours", "D": "next day"}, "answer": "B"},
    {"stem": "Good nutrition helps to ______.", "options": {"A": "weaken the body", "B": "improve health", "C": "cause illness", "D": "reduce growth"}, "answer": "B"},
    {"stem": "Environmental sanitation helps to ______.", "options": {"A": "spread diseases", "B": "keep environment clean", "C": "cause pollution", "D": "attract pests"}, "answer": "B"},
    {"stem": "Regular exercise helps to ______.", "options": {"A": "increase sickness", "B": "improve fitness", "C": "weaken muscles", "D": "cause obesity"}, "answer": "B"},
    {"stem": "Safety education helps people to ______.", "options": {"A": "take risks", "B": "prevent accidents", "C": "ignore dangers", "D": "cause injuries"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. (a) Define first aid.\n(b) State four importance of first aid.", "marks": Decimal('10.00')},
    {"stem": "2. (a) What is an accident?\n(b) Mention and explain three types of sports injuries.", "marks": Decimal('10.00')},
    {"stem": "3. (a) Define environmental pollution.\n(b) List and explain four types or sources of environmental pollution.", "marks": Decimal('10.00')},
    {"stem": "4. (a) What are non-communicable diseases?\n(b) Give four examples of non-communicable diseases.", "marks": Decimal('10.00')},
    {"stem": "5. (a) Explain high jump.\n(b) Mention four basic skills in high jump.", "marks": Decimal('10.00')},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="PHE")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="saiki@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 13, 20, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 14, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Wednesday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 1:20 PM WAT.",
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
    exam.dean_review_comment = "Approved for Wednesday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 1:20 PM WAT."
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
            source_reference=f"JS2-PHE-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS2-PHE-20260325-TH-{index:02d}",
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
        "paper_code": "JS2-PHE-EXAM",
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
