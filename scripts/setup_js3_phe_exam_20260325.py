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


TITLE = "WED 1:20-2:30 JS3 PHE Second Term Exam"
DESCRIPTION = "JSS3 PHYSICAL AND HEALTH EDUCATION SECOND TERM EXAMINATION"
BANK_NAME = "JS3 PHE Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 2:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "A relay race involves ______.", "options": {"A": "One athlete", "B": "Two athletes", "C": "A team passing a baton", "D": "Jumping only"}, "answer": "C"},
    {"stem": "The baton exchange takes place in the ______.", "options": {"A": "Starting line", "B": "Exchange zone", "C": "Finish line", "D": "Field"}, "answer": "B"},
    {"stem": "An example of relay race is ______.", "options": {"A": "100m", "B": "4×100m", "C": "Marathon", "D": "200m"}, "answer": "B"},
    {"stem": "Athletics consists of ______.", "options": {"A": "Swimming only", "B": "Running, jumping and throwing", "C": "Football only", "D": "Dancing"}, "answer": "B"},
    {"stem": "Long jump is a ______.", "options": {"A": "Track event", "B": "Field event", "C": "Court event", "D": "Water event"}, "answer": "B"},
    {"stem": "1500m race is a ______.", "options": {"A": "Field event", "B": "Track event", "C": "Jump event", "D": "Throw event"}, "answer": "B"},
    {"stem": "A false start can lead to ______.", "options": {"A": "Medal", "B": "Disqualification", "C": "Promotion", "D": "Warning only"}, "answer": "B"},
    {"stem": "Sprint races require ______.", "options": {"A": "Standing start", "B": "Crouch start", "C": "Rolling start", "D": "Walking start"}, "answer": "B"},
    {"stem": "Shot put is a ______.", "options": {"A": "Jump", "B": "Throw", "C": "Race", "D": "Dance"}, "answer": "B"},
    {"stem": "The official who controls a race is the ______.", "options": {"A": "Coach", "B": "Referee", "C": "Captain", "D": "Spectator"}, "answer": "B"},
    {"stem": "Volleyball is played by ___ players per team.", "options": {"A": "5", "B": "6", "C": "7", "D": "8"}, "answer": "B"},
    {"stem": "The game starts with a ______.", "options": {"A": "Pass", "B": "Serve", "C": "Throw", "D": "Kick"}, "answer": "B"},
    {"stem": "Each team is allowed a maximum of ___ touches.", "options": {"A": "2", "B": "3", "C": "4", "D": "5"}, "answer": "B"},
    {"stem": "A powerful downward hit is called a ______.", "options": {"A": "Dig", "B": "Spike", "C": "Toss", "D": "Serve"}, "answer": "B"},
    {"stem": "The volleyball court is divided by a ______.", "options": {"A": "Rope", "B": "Net", "C": "Pole", "D": "Line"}, "answer": "B"},
    {"stem": "Rotation in volleyball is done ______.", "options": {"A": "Clockwise", "B": "Anti-clockwise", "C": "Forward", "D": "Backward"}, "answer": "A"},
    {"stem": "A point scored from a direct serve is called ______.", "options": {"A": "Ace", "B": "Foul", "C": "Toss", "D": "Pass"}, "answer": "A"},
    {"stem": "Basketball was invented by ______.", "options": {"A": "Michael Jordan", "B": "James Naismith", "C": "Kobe Bryant", "D": "Usain Bolt"}, "answer": "B"},
    {"stem": "A basketball team has ___ players on court.", "options": {"A": "4", "B": "5", "C": "6", "D": "7"}, "answer": "B"},
    {"stem": "Bouncing the ball while moving is ______.", "options": {"A": "Passing", "B": "Shooting", "C": "Dribbling", "D": "Traveling"}, "answer": "C"},
    {"stem": "Moving without dribbling is ______.", "options": {"A": "Pivoting", "B": "Traveling", "C": "Rebounding", "D": "Shooting"}, "answer": "B"},
    {"stem": "A shot beyond the arc scores ______.", "options": {"A": "1 point", "B": "2 points", "C": "3 points", "D": "4 points"}, "answer": "C"},
    {"stem": "A basketball game begins with a ______.", "options": {"A": "Serve", "B": "Jump ball", "C": "Throw-in", "D": "Kick-off"}, "answer": "B"},
    {"stem": "The ring and net are called the ______.", "options": {"A": "Goal", "B": "Basket", "C": "Post", "D": "Target"}, "answer": "B"},
    {"stem": "An injury that occurs suddenly is ______.", "options": {"A": "Chronic", "B": "Acute", "C": "Minor", "D": "Major"}, "answer": "B"},
    {"stem": "A strain affects the ______.", "options": {"A": "Ligament", "B": "Muscle", "C": "Bone", "D": "Skin"}, "answer": "B"},
    {"stem": "RICE stands for ______.", "options": {"A": "Rest, Ice, Compress, Elevate", "B": "Run, Ice, Cover, End", "C": "Rest, Improve, Care, End", "D": "Relax, Ice, Control, Exercise"}, "answer": "A"},
    {"stem": "One cause of sports injury is ______.", "options": {"A": "Proper warm-up", "B": "Carelessness", "C": "Training", "D": "Obedience"}, "answer": "B"},
    {"stem": "First aid means ______.", "options": {"A": "Immediate treatment", "B": "Final treatment", "C": "Surgery", "D": "Therapy"}, "answer": "A"},
    {"stem": "Wearing protective gear helps to ______.", "options": {"A": "Cause injury", "B": "Prevent injury", "C": "Delay play", "D": "Increase speed"}, "answer": "B"},
    {"stem": "Pollution means ______.", "options": {"A": "Cleanliness", "B": "Contamination", "C": "Exercise", "D": "Fitness"}, "answer": "B"},
    {"stem": "Smoke from cars causes ______.", "options": {"A": "Air pollution", "B": "Water pollution", "C": "Noise pollution", "D": "Land pollution"}, "answer": "A"},
    {"stem": "Noise pollution affects ______.", "options": {"A": "Hearing", "B": "Vision", "C": "Smell", "D": "Taste"}, "answer": "A"},
    {"stem": "Dumping refuse in rivers causes ______.", "options": {"A": "Clean water", "B": "Water pollution", "C": "Fitness", "D": "Growth"}, "answer": "B"},
    {"stem": "Pollution can lead to ______.", "options": {"A": "Good health", "B": "Disease", "C": "Strength", "D": "Energy"}, "answer": "B"},
    {"stem": "Recreation is ______.", "options": {"A": "Hard labour", "B": "Refreshing activity", "C": "Competition", "D": "Punishment"}, "answer": "B"},
    {"stem": "Leisure means ______.", "options": {"A": "Busy time", "B": "Free time", "C": "Exam time", "D": "School time"}, "answer": "B"},
    {"stem": "An example of recreation is ______.", "options": {"A": "Reading", "B": "Fighting", "C": "Cheating", "D": "Sleeping in class"}, "answer": "A"},
    {"stem": "Dance improves ______.", "options": {"A": "Fitness", "B": "Pollution", "C": "Laziness", "D": "Injury"}, "answer": "A"},
    {"stem": "Traditional dance promotes ______.", "options": {"A": "Culture", "B": "Conflict", "C": "Sickness", "D": "War"}, "answer": "A"},
    {"stem": "Physical fitness is the ability to ______.", "options": {"A": "Sleep well", "B": "Perform daily tasks without fatigue", "C": "Eat more", "D": "Rest always"}, "answer": "B"},
    {"stem": "Cardiovascular endurance involves the ______.", "options": {"A": "Bones", "B": "Heart and lungs", "C": "Skin", "D": "Hair"}, "answer": "B"},
    {"stem": "Push-ups develop ______.", "options": {"A": "Arm strength", "B": "Leg strength", "C": "Eye muscles", "D": "Neck muscles"}, "answer": "A"},
    {"stem": "Sit-ups strengthen the ______.", "options": {"A": "Abdomen", "B": "Ear", "C": "Nose", "D": "Neck"}, "answer": "A"},
    {"stem": "Flexibility is improved by ______.", "options": {"A": "Sleeping", "B": "Stretching", "C": "Eating", "D": "Sitting"}, "answer": "B"},
    {"stem": "Warm-up prepares the body for ______.", "options": {"A": "Injury", "B": "Exercise", "C": "Sleep", "D": "Rest"}, "answer": "B"},
    {"stem": "Cool-down helps to ______.", "options": {"A": "Relax muscles", "B": "Increase speed", "C": "Cause fatigue", "D": "Stop breathing"}, "answer": "A"},
    {"stem": "Skipping improves ______.", "options": {"A": "Endurance", "B": "Laziness", "C": "Fear", "D": "Weakness"}, "answer": "A"},
    {"stem": "Obesity is caused by ______.", "options": {"A": "Regular exercise", "B": "Balanced diet", "C": "Lack of exercise", "D": "Stretching"}, "answer": "C"},
    {"stem": "Body conditioning improves ______.", "options": {"A": "Weakness", "B": "Strength and endurance", "C": "Pollution", "D": "Injury"}, "answer": "B"},
    {"stem": "Marathon is a ______.", "options": {"A": "Sprint", "B": "Long-distance race", "C": "Relay", "D": "Jump"}, "answer": "B"},
    {"stem": "High jump is a ______.", "options": {"A": "Field event", "B": "Track event", "C": "Court event", "D": "Water event"}, "answer": "A"},
    {"stem": "Overtraining may cause ______.", "options": {"A": "Fitness", "B": "Injury", "C": "Strength", "D": "Speed"}, "answer": "B"},
    {"stem": "Environmental sanitation promotes ______.", "options": {"A": "Pollution", "B": "Cleanliness", "C": "Illness", "D": "Accident"}, "answer": "B"},
    {"stem": "Relay baton must not be ______.", "options": {"A": "Passed", "B": "Held", "C": "Dropped", "D": "Carried"}, "answer": "C"},
    {"stem": "Rebounding in basketball means ______.", "options": {"A": "Catching missed shot", "B": "Dribbling", "C": "Passing", "D": "Shooting"}, "answer": "A"},
    {"stem": "Volleyball is mainly played with the ______.", "options": {"A": "Feet", "B": "Hands", "C": "Head", "D": "Shoulders"}, "answer": "B"},
    {"stem": "Athletics develops ______.", "options": {"A": "Fear", "B": "Fitness", "C": "Laziness", "D": "Weakness"}, "answer": "B"},
    {"stem": "Leisure activities help reduce ______.", "options": {"A": "Stress", "B": "Health", "C": "Energy", "D": "Growth"}, "answer": "A"},
    {"stem": "Exercise should be done ______.", "options": {"A": "Once a year", "B": "Regularly", "C": "Never", "D": "Occasionally"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. (a) Define relay race.\n(b) State four rules of relay race.", "marks": Decimal('10.00')},
    {"stem": "2. (a) Define sports injury.\n(b) Mention four causes and explain four ways of preventing sports injuries.", "marks": Decimal('10.00')},
    {"stem": "3. (a) Define environmental pollution.\n(b) Mention four types and explain four effects.", "marks": Decimal('10.00')},
    {"stem": "4. (a) Define physical fitness.\n(b) Mention and explain four components of physical fitness.", "marks": Decimal('10.00')},
    {"stem": "5. Write short notes on:\n(a) Recreation\n(b) Leisure\n(c) Dance activities", "marks": Decimal('10.00')},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
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
            source_reference=f"JS3-PHE-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS3-PHE-20260325-TH-{index:02d}",
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
        "paper_code": "JS3-PHE-EXAM",
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
