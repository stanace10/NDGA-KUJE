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


TITLE = "WED 7:45-9:00 SS1 Christian Religious Studies Second Term Exam"
DESCRIPTION = "CHRISTIAN RELIGIOUS STUDIES CLASS: SS1"
BANK_NAME = "SS1 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions only. "
    "Timer is 55 minutes. Exam window closes at 9:00 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {
        "stem": "According to James, faith without works is ______.",
        "options": {"A": "growing", "B": "active", "C": "dead", "D": "perfect"},
        "answer": "C",
    },
    {
        "stem": "Jesus described Himself as the true vine in order to teach that ______.",
        "options": {
            "A": "Israel was rejected",
            "B": "believers must depend on Him for spiritual life",
            "C": "farming is holy",
            "D": "obedience comes from the law",
        },
        "answer": "B",
    },
    {
        "stem": "Paul's teaching on forgiveness is best illustrated in his letter to ______.",
        "options": {"A": "Titus", "B": "Philemon", "C": "Galatians", "D": "Romans"},
        "answer": "B",
    },
    {
        "stem": "Saul was travelling to Damascus mainly to ______.",
        "options": {"A": "preach the gospel", "B": "escape persecution", "C": "arrest Christians", "D": "meet the apostles"},
        "answer": "C",
    },
    {
        "stem": "\"For God so loved the world\" shows that God's love is ______.",
        "options": {"A": "conditional", "B": "selective", "C": "universal", "D": "temporary"},
        "answer": "C",
    },
    {
        "stem": "The raising of Lazarus demonstrated that Jesus ______.",
        "options": {"A": "feared death", "B": "had power over life and death", "C": "avoided suffering", "D": "depended on prophets"},
        "answer": "B",
    },
    {
        "stem": "Which of the following is NOT a fruit of the Spirit?",
        "options": {"A": "Love", "B": "Joy", "C": "Tongues", "D": "Self-control"},
        "answer": "C",
    },
    {
        "stem": "According to Jesus, branches that do not bear fruit are ______.",
        "options": {"A": "rewarded", "B": "ignored", "C": "cut off", "D": "replanted"},
        "answer": "C",
    },
    {
        "stem": "James used Abraham to teach that ______.",
        "options": {"A": "faith is useless", "B": "works replace faith", "C": "faith must be shown by works", "D": "obedience is unnecessary"},
        "answer": "C",
    },
    {
        "stem": "The living bread discourse is recorded in ______.",
        "options": {"A": "Matthew 6", "B": "Mark 4", "C": "Luke 15", "D": "John 6"},
        "answer": "D",
    },
    {
        "stem": "Saul lost his sight for ______.",
        "options": {"A": "one day", "B": "two days", "C": "three days", "D": "seven days"},
        "answer": "C",
    },
    {
        "stem": "Humility can best be described as ______.",
        "options": {"A": "weakness", "B": "pride", "C": "lowliness of mind", "D": "fear of failure"},
        "answer": "C",
    },
    {
        "stem": "Jesus taught humility practically by ______.",
        "options": {"A": "fasting forty days", "B": "washing His disciples' feet", "C": "preaching on the mount", "D": "performing miracles"},
        "answer": "B",
    },
    {
        "stem": "Paul taught that spiritual gifts should be exercised with ______.",
        "options": {"A": "power", "B": "boldness", "C": "love", "D": "authority"},
        "answer": "C",
    },
    {
        "stem": "The fruits of the Spirit reflect ______.",
        "options": {"A": "spiritual gifts", "B": "natural abilities", "C": "Christian character", "D": "church offices"},
        "answer": "C",
    },
    {
        "stem": "Saul later became known as ______.",
        "options": {"A": "Peter", "B": "John", "C": "Stephen", "D": "Paul"},
        "answer": "D",
    },
    {
        "stem": "God demonstrated His love for mankind by ______.",
        "options": {"A": "giving the law", "B": "choosing Israel", "C": "sending His Son", "D": "creating angels"},
        "answer": "C",
    },
    {
        "stem": "According to Paul, forgiveness among believers promotes ______.",
        "options": {"A": "fear", "B": "weakness", "C": "unity", "D": "pride"},
        "answer": "C",
    },
    {
        "stem": "Which of the following is a spiritual gift?",
        "options": {"A": "Farming", "B": "Teaching", "C": "Singing", "D": "Trading"},
        "answer": "B",
    },
    {
        "stem": "Jesus described Himself as the resurrection and the life when speaking to ______.",
        "options": {"A": "Mary Magdalene", "B": "Martha", "C": "Peter", "D": "Nicodemus"},
        "answer": "B",
    },
    {
        "stem": "According to Galatians 5, the fruit of the Spirit includes ______.",
        "options": {"A": "faith healing", "B": "speaking in tongues", "C": "patience", "D": "prophecy"},
        "answer": "C",
    },
    {
        "stem": "Saul's conversion experience involved ______.",
        "options": {"A": "thunder", "B": "earthquake", "C": "a bright light", "D": "fire"},
        "answer": "C",
    },
    {
        "stem": "Spiritual gifts are given primarily for ______.",
        "options": {"A": "personal pride", "B": "competition", "C": "service in the church", "D": "material gain"},
        "answer": "C",
    },
    {
        "stem": "The letter to Philemon teaches Christians to ______.",
        "options": {"A": "punish offenders", "B": "forgive offenders", "C": "reject wrongdoers", "D": "report sinners"},
        "answer": "B",
    },
    {
        "stem": "Jesus called Himself the living bread because He ______.",
        "options": {"A": "performed miracles", "B": "gives eternal life", "C": "fed the hungry", "D": "was born in Bethlehem"},
        "answer": "B",
    },
    {
        "stem": "God resists the proud but gives grace to the ______.",
        "options": {"A": "rich", "B": "strong", "C": "wise", "D": "humble"},
        "answer": "D",
    },
    {
        "stem": "Rahab was justified by works because she ______.",
        "options": {"A": "prayed constantly", "B": "fasted regularly", "C": "helped the spies", "D": "kept the law"},
        "answer": "C",
    },
    {
        "stem": "Paul's major teaching on spiritual gifts is found in ______.",
        "options": {"A": "Romans 8", "B": "1 Corinthians 12", "C": "Galatians 5", "D": "Ephesians 6"},
        "answer": "B",
    },
    {
        "stem": "Saul's conversion shows that ______.",
        "options": {"A": "sinners cannot change", "B": "persecution ends faith", "C": "God can transform anyone", "D": "obedience comes first"},
        "answer": "C",
    },
    {
        "stem": "The true vine metaphor teaches believers to ______.",
        "options": {"A": "obey tradition", "B": "work independently", "C": "remain in Christ", "D": "rely on prophets"},
        "answer": "C",
    },
    {
        "stem": "Which of the following best describes humility?",
        "options": {"A": "Self-importance", "B": "Dependence on God", "C": "Fear of people", "D": "Public display"},
        "answer": "B",
    },
    {
        "stem": "Ananias helped Saul by ______.",
        "options": {"A": "judging him", "B": "arresting him", "C": "restoring his sight", "D": "teaching him the law"},
        "answer": "C",
    },
    {
        "stem": "Paul advised Christians to forgive because ______.",
        "options": {"A": "revenge is sinful", "B": "Christ forgave them", "C": "punishment is useless", "D": "enemies deserve mercy"},
        "answer": "B",
    },
    {
        "stem": "The fruit of the Spirit differs from spiritual gifts because it ______.",
        "options": {"A": "is temporary", "B": "is given to few people", "C": "shows character", "D": "causes division"},
        "answer": "C",
    },
    {
        "stem": "Jesus said, \"Apart from me you can do nothing\" to emphasize ______.",
        "options": {"A": "human wisdom", "B": "dependence on God", "C": "the law of Moses", "D": "personal effort"},
        "answer": "B",
    },
    {
        "stem": "The greatest proof of God's love is seen in ______.",
        "options": {"A": "miracles", "B": "creation", "C": "the crucifixion of Jesus", "D": "answered prayers"},
        "answer": "C",
    },
    {
        "stem": "Which of the following promotes Christian maturity?",
        "options": {"A": "Spiritual gifts only", "B": "Fruits of the Spirit", "C": "Church titles", "D": "Wealth"},
        "answer": "B",
    },
    {
        "stem": "Saul's conversion contributed greatly to the ______.",
        "options": {"A": "fall of Judaism", "B": "end of persecution", "C": "spread of Christianity", "D": "destruction of Rome"},
        "answer": "C",
    },
    {
        "stem": "According to James, works are important because they ______.",
        "options": {"A": "replace grace", "B": "save by themselves", "C": "prove genuine faith", "D": "cancel sin"},
        "answer": "C",
    },
    {
        "stem": "Humility before God results in ______.",
        "options": {"A": "shame", "B": "punishment", "C": "exaltation", "D": "sorrow"},
        "answer": "C",
    },
]

THEORY = [
    {
        "stem": (
            "1. (a) Distinguish between the fruits of the flesh and the fruits of the Spirit.\n"
            "(b) List five ways of bearing the fruits of the Spirit."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. (a) List five functions of spiritual gifts.\n"
            "(b) Explain the differences between spiritual gifts and talents."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. (a) List five importance of forgiveness.\n"
            "(b) Explain forgiveness based on Paul's teaching."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4. (a) Define humility and list four significance of humility.\n"
            "(b) List five ways Christians can express humility."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. (a) Define covenant and enumerate four features of the new covenant.\n"
            "(b) List five implications of the new covenant."
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="CRS")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="juliemokidi@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 7, 45, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 9, 0, tzinfo=lagos)

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
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 7:45 AM WAT.",
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
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 7:45 AM WAT."
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
            source_reference=f"SS1-CRS-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS1-CRS-20260325-TH-{index:02d}",
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
        "paper_code": "SS1-CRS-EXAM",
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
