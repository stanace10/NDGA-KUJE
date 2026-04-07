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


TITLE = "WED 2:00-4:00 JS1 PHE Second Term Exam"
DESCRIPTION = "JS1 PHYSICAL AND HEALTH EDUCATION SECOND TERM EXAMINATION"
BANK_NAME = "JS1 PHE Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 4:00 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "Contact sports are sports in which players ______.", "options": {"A": "play alone", "B": "do not touch each other", "C": "have physical body contact", "D": "play in water"}, "answer": "C"},
    {"stem": "An example of a contact sport is ______.", "options": {"A": "Swimming", "B": "Wrestling", "C": "Table tennis", "D": "Athletics"}, "answer": "B"},
    {"stem": "Wrestling is a sport that involves ______.", "options": {"A": "running fast", "B": "throwing balls", "C": "physical struggle between opponents", "D": "swimming skills"}, "answer": "C"},
    {"stem": "The main aim of wrestling is to ______.", "options": {"A": "score goals", "B": "pin an opponent", "C": "swim faster", "D": "jump higher"}, "answer": "B"},
    {"stem": "Judo originated from ______.", "options": {"A": "Nigeria", "B": "Japan", "C": "China", "D": "Brazil"}, "answer": "B"},
    {"stem": "Judo mainly teaches ______.", "options": {"A": "running skills", "B": "swimming skills", "C": "self-defence skills", "D": "dancing skills"}, "answer": "C"},
    {"stem": "One benefit of judo is ______.", "options": {"A": "indiscipline", "B": "self-control", "C": "laziness", "D": "fear"}, "answer": "B"},
    {"stem": "Non-contact sports are sports where players ______.", "options": {"A": "fight each other", "B": "avoid physical contact", "C": "wrestle", "D": "kick opponents"}, "answer": "B"},
    {"stem": "An example of a non-contact sport is ______.", "options": {"A": "Boxing", "B": "Wrestling", "C": "Badminton", "D": "Judo"}, "answer": "C"},
    {"stem": "Which of these is NOT a non-contact sport?", "options": {"A": "Athletics", "B": "Volleyball", "C": "Karate", "D": "Table tennis"}, "answer": "C"},
    {"stem": "Aquatic sports are sports performed ______.", "options": {"A": "on land", "B": "in water", "C": "in the air", "D": "on roads"}, "answer": "B"},
    {"stem": "An example of an aquatic sport is ______.", "options": {"A": "Football", "B": "Swimming", "C": "Wrestling", "D": "Gymnastics"}, "answer": "B"},
    {"stem": "Gymnastics mainly helps to develop ______.", "options": {"A": "balance and flexibility", "B": "swimming skills", "C": "fighting skills", "D": "throwing skills"}, "answer": "A"},
    {"stem": "One equipment used in gymnastics is ______.", "options": {"A": "bat", "B": "racket", "C": "mat", "D": "net"}, "answer": "C"},
    {"stem": "Traditional sports are sports that ______.", "options": {"A": "are modern", "B": "are foreign", "C": "are inherited from ancestors", "D": "are only for adults"}, "answer": "C"},
    {"stem": "An example of a traditional sport in Nigeria is ______.", "options": {"A": "Tennis", "B": "Basketball", "C": "Traditional wrestling", "D": "Swimming"}, "answer": "C"},
    {"stem": "Personal health means ______.", "options": {"A": "caring for animals", "B": "caring for one's body and hygiene", "C": "caring for the environment only", "D": "caring for others only"}, "answer": "B"},
    {"stem": "One way of maintaining personal health is ______.", "options": {"A": "bathing regularly", "B": "wearing dirty clothes", "C": "avoiding exercise", "D": "refusing to eat"}, "answer": "A"},
    {"stem": "School health involves ______.", "options": {"A": "students only", "B": "teachers only", "C": "everyone in the school", "D": "visitors only"}, "answer": "C"},
    {"stem": "A clean school environment helps to ______.", "options": {"A": "spread diseases", "B": "promote good health", "C": "attract insects", "D": "cause sickness"}, "answer": "B"},
    {"stem": "Community health refers to ______.", "options": {"A": "individual health", "B": "family health only", "C": "health of people in a community", "D": "school health"}, "answer": "C"},
    {"stem": "Sewage refers to ______.", "options": {"A": "rainwater", "B": "clean water", "C": "waste water from homes", "D": "drinking water"}, "answer": "C"},
    {"stem": "Proper sewage disposal helps to ______.", "options": {"A": "spread diseases", "B": "prevent diseases", "C": "cause pollution", "D": "block drainage"}, "answer": "B"},
    {"stem": "One method of sewage disposal is ______.", "options": {"A": "pit latrine", "B": "open defecation", "C": "roadside dumping", "D": "river disposal"}, "answer": "A"},
    {"stem": "Refuse means ______.", "options": {"A": "liquid waste", "B": "solid waste materials", "C": "gas", "D": "clean water"}, "answer": "B"},
    {"stem": "An example of refuse is ______.", "options": {"A": "urine", "B": "smoke", "C": "nylon bags", "D": "rainwater"}, "answer": "C"},
    {"stem": "Proper refuse disposal helps to ______.", "options": {"A": "spread germs", "B": "block drainage", "C": "keep the environment clean", "D": "attract flies"}, "answer": "C"},
    {"stem": "One method of refuse disposal is ______.", "options": {"A": "burning", "B": "throwing on roads", "C": "dumping in rivers", "D": "scattering"}, "answer": "A"},
    {"stem": "Poor refuse disposal can cause ______.", "options": {"A": "cleanliness", "B": "diseases", "C": "fitness", "D": "happiness"}, "answer": "B"},
    {"stem": "Which disease can result from poor sanitation?", "options": {"A": "Malaria", "B": "Cholera", "C": "Typhoid", "D": "All of the above"}, "answer": "D"},
    {"stem": "Wrestling requires ______.", "options": {"A": "mat and headgear", "B": "bat and ball", "C": "net and racket", "D": "javelin"}, "answer": "A"},
    {"stem": "A wrestling skill is ______.", "options": {"A": "gripping", "B": "serving", "C": "passing", "D": "shooting"}, "answer": "A"},
    {"stem": "Another wrestling skill is ______.", "options": {"A": "pinning", "B": "sprinting", "C": "dribbling", "D": "heading"}, "answer": "A"},
    {"stem": "Aquatic sports require ______.", "options": {"A": "water facilities", "B": "gymnasium", "C": "mats", "D": "sticks"}, "answer": "A"},
    {"stem": "Gymnastics activities should be done on ______.", "options": {"A": "hard ground", "B": "slippery surface", "C": "padded mat", "D": "bare floor"}, "answer": "C"},
    {"stem": "Judo teaches discipline and ______.", "options": {"A": "fear", "B": "laziness", "C": "self-control", "D": "anger"}, "answer": "C"},
    {"stem": "Traditional sports help to ______.", "options": {"A": "destroy culture", "B": "promote cultural heritage", "C": "cause sickness", "D": "waste time"}, "answer": "B"},
    {"stem": "Community health programmes help to ______.", "options": {"A": "spread sickness", "B": "promote healthy living", "C": "encourage pollution", "D": "reduce hygiene"}, "answer": "B"},
    {"stem": "Contact sports should be played ______.", "options": {"A": "without rules", "B": "carelessly", "C": "under strict rules", "D": "without officials"}, "answer": "C"},
    {"stem": "Regular participation in sports improves ______.", "options": {"A": "illness", "B": "weakness", "C": "physical fitness", "D": "laziness"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. (a) Define contact sports.\n(b) Mention four examples of contact sports.", "marks": Decimal("10.00")},
    {"stem": "2. (a) Explain wrestling.\n(b) Mention four wrestling skills.\n(c) State two facilities used for wrestling.", "marks": Decimal("10.00")},
    {"stem": "3. (a) What is judo?\n(b) Mention three benefits of judo.\n(c) List two equipment used in judo.", "marks": Decimal("10.00")},
    {"stem": "4. (a) Define personal, school and community health.\n(b) State four ways of maintaining personal health.", "marks": Decimal("10.00")},
    {"stem": "5. (a) What is sewage and refuse disposal?\n(b) Mention four methods of refuse disposal.\n(c) State two importance of proper refuse disposal.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
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
    schedule_start = datetime(2026, 3, 25, 14, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 16, 0, tzinfo=lagos)

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
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 2:00 PM WAT.",
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
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 2:00 PM WAT."
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
            source_reference=f"JS1-PHE-20260325-OBJ-{index:02d}",
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
            source_reference=f"JS1-PHE-20260325-TH-{index:02d}",
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
        "paper_code": "JS1-PHE-EXAM",
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

main()
