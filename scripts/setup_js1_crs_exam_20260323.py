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


TITLE = "MON 9:45-10:45 JS1 Christian Religious Studies Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: JSS1 CHRISTIAN RELIGIOUS STUDIES"
BANK_NAME = "JS1 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer only four questions. "
    "Timer is 50 minutes. Exam window closes at 10:45 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {
        "stem": "1. Repentance is the act of ______.",
        "options": {
            "A": "Singing",
            "B": "turning away from sin and asking God for mercy",
            "C": "Fighting",
            "D": "Traveling",
        },
        "answer": "B",
    },
    {
        "stem": "2. Prophet Nathan rebuked King David because he ______.",
        "options": {
            "A": "Failed to pray",
            "B": "Stole money",
            "C": "took Uriah's wife",
            "D": "Refused to fight",
        },
        "answer": "C",
    },
    {
        "stem": "3. King David said, \"I have sinned against the ______.\"",
        "options": {"A": "People", "B": "Lord", "C": "Army", "D": "Prophet"},
        "answer": "B",
    },
    {
        "stem": "4. Who wrote Psalm 51?",
        "options": {"A": "King David", "B": "Solomon", "C": "Moses", "D": "Prophet Isaiah"},
        "answer": "A",
    },
    {
        "stem": "5. Psalm 51 is a prayer of ______.",
        "options": {"A": "thanksgiving", "B": "praise", "C": "repentance", "D": "victory"},
        "answer": "C",
    },
    {
        "stem": "6. The people of Nineveh showed repentance by ______.",
        "options": {"A": "fighting", "B": "fasting and praying", "C": "traveling", "D": "dancing"},
        "answer": "B",
    },
    {
        "stem": "7. When we refuse to obey the rules, orders or command given to us by someone in authority, we are being ______.",
        "options": {"A": "respectful", "B": "obedient", "C": "disobedient", "D": "disrespectful"},
        "answer": "C",
    },
    {
        "stem": "8. Because Nineveh repented, God ______.",
        "options": {"A": "Destroyed them", "B": "Forgave them", "C": "Ignored them", "D": "Punished them"},
        "answer": "B",
    },
    {
        "stem": "9. John the Baptist preached in the wilderness of ______.",
        "options": {"A": "Galilee", "B": "Judea", "C": "Egypt", "D": "Samaria"},
        "answer": "B",
    },
    {
        "stem": "10. The message of John the Baptist prepared the way for ______.",
        "options": {"A": "Moses", "B": "Elijah", "C": "Messiah", "D": "Peter"},
        "answer": "C",
    },
    {
        "stem": "11. The act of doing what we are told to do without questioning is called ______.",
        "options": {"A": "Repentance", "B": "Obedience", "C": "Disobedience", "D": "Reconciliation"},
        "answer": "B",
    },
    {
        "stem": "12. The two sons of Eli were ______ and ______.",
        "options": {"A": "Hophni and Phinehas", "B": "Hophni and Ichabod", "C": "Samuel and Isaac", "D": "David and Solomon"},
        "answer": "A",
    },
    {
        "stem": "13. John the Baptist baptized people in River ______ after confessing their sins.",
        "options": {"A": "Nile", "B": "Jordan", "C": "Euphrates", "D": "Tigris"},
        "answer": "B",
    },
    {
        "stem": "14. The tax collectors were told by John to ______.",
        "options": {"A": "steal more", "B": "collect only what is required", "C": "stop working", "D": "fight soldiers"},
        "answer": "B",
    },
    {
        "stem": "15. The soldiers were told by John the Baptist not to ______.",
        "options": {"A": "pray aloud", "B": "fast like the hypocrites", "C": "rob anyone by violence", "D": "travel to the promised land"},
        "answer": "C",
    },
    {
        "stem": "16. \"Today, salvation has come to this house, since he is also a son of Abraham...\" This statement was said by Jesus to ______.",
        "options": {"A": "Jonah", "B": "Zacchaeus", "C": "Obadiah", "D": "Abraham"},
        "answer": "B",
    },
    {
        "stem": "17. Eli was a ______ at the temple in Shiloh.",
        "options": {"A": "King", "B": "Priest", "C": "Farmer", "D": "Soldier"},
        "answer": "B",
    },
    {
        "stem": "18. Eli failed to control his ______ and God became angry with him.",
        "options": {"A": "Servants", "B": "Sons", "C": "Soldiers", "D": "Friends"},
        "answer": "B",
    },
    {
        "stem": "19. Because Eli's sons did not repent, God allowed the ark to be ______.",
        "options": {"A": "protected by the Philistines", "B": "hidden in the desert", "C": "captured in a war", "D": "blessed by the priest"},
        "answer": "C",
    },
    {
        "stem": "20. Nathan used a ______ to teach David a lesson and rebuke his sinful deeds.",
        "options": {"A": "song", "B": "story", "C": "dream", "D": "parable"},
        "answer": "D",
    },
    {
        "stem": "21. Who did God give the priesthood after the death of Eli and his sons?",
        "options": {"A": "Samuel", "B": "Phinehas' wife", "C": "Ichabod", "D": "the women at the tent"},
        "answer": "A",
    },
    {
        "stem": "22. The name Ichabod means ______.",
        "options": {
            "A": "The glory has departed from Israel for the ark of God has been captured",
            "B": "The glory has been revealed to the Philistines",
            "C": "God has made me laugh at last",
            "D": "Glory to God in the highest",
        },
        "answer": "A",
    },
    {
        "stem": "23. Eli was ______ years old when he died.",
        "options": {"A": "70", "B": "90", "C": "98", "D": "100"},
        "answer": "C",
    },
    {
        "stem": "24. Who was the nephew of Abraham that accompanied him to the unknown land?",
        "options": {"A": "Samuel", "B": "Nahor", "C": "Lot", "D": "Hagar"},
        "answer": "C",
    },
    {
        "stem": "25. Sackcloth is a symbol of ______.",
        "options": {"A": "Wealth", "B": "Humility and sorrow", "C": "Victory", "D": "Pride"},
        "answer": "B",
    },
    {
        "stem": "26. The people of Nineveh believed God and proclaimed a ______.",
        "options": {"A": "great war", "B": "feast", "C": "fast", "D": "celebration"},
        "answer": "C",
    },
    {
        "stem": "27. Zacchaeus was a chief ______.",
        "options": {"A": "Fisherman", "B": "Soldier", "C": "Tax collector", "D": "Farmer"},
        "answer": "C",
    },
    {
        "stem": "28. Zacchaeus climbed a ______ tree to see Jesus.",
        "options": {"A": "Palm", "B": "Sycamore", "C": "Mango", "D": "Cedar"},
        "answer": "B",
    },
    {
        "stem": "29. Zacchaeus promised to give ______ of his goods to the poor.",
        "options": {"A": "One-quarter", "B": "Half", "C": "All", "D": "None"},
        "answer": "B",
    },
    {
        "stem": "30. Zacchaeus said he would repay ______ times anyone he cheated.",
        "options": {"A": "Two", "B": "Three", "C": "Four", "D": "Five"},
        "answer": "C",
    },
    {
        "stem": "31. Zacchaeus was short in ______.",
        "options": {"A": "Age", "B": "stature", "C": "Wisdom", "D": "Wealth"},
        "answer": "B",
    },
    {
        "stem": "32. John the Baptist warned the people that every tree that does not bear good fruit will be ______.",
        "options": {"A": "praised by God", "B": "cut down and thrown into hell", "C": "watered and killed", "D": "decorated by God"},
        "answer": "B",
    },
    {
        "stem": "33. God saw the true repentance of the Ninevites and ______.",
        "options": {"A": "changed His mind", "B": "destroyed them", "C": "ignored them", "D": "fought them"},
        "answer": "A",
    },
    {
        "stem": "34. Zacchaeus showed his true repentance to Jesus through ______.",
        "options": {"A": "words only", "B": "restitution", "C": "hiding", "D": "fighting"},
        "answer": "B",
    },
    {
        "stem": "35. John the Baptist told the people to share with those who have ______.",
        "options": {"A": "much", "B": "two houses", "C": "none", "D": "cars"},
        "answer": "C",
    },
    {
        "stem": "36. \"To your descendants, I will give this land.\" God said this statement to ______.",
        "options": {"A": "Abraham", "B": "Nahor", "C": "Lot", "D": "Terah"},
        "answer": "A",
    },
    {
        "stem": "37. Where did God appear to show Abraham the promised land?",
        "options": {"A": "Shechem", "B": "at the oak of Moreh", "C": "Joppa", "D": "Tarshish"},
        "answer": "B",
    },
    {
        "stem": "38. Abraham was ______ years old when he left his father's land.",
        "options": {"A": "ninety-nine", "B": "seventy-five", "C": "hundred", "D": "seventeen"},
        "answer": "B",
    },
    {
        "stem": "39. Abraham's father's land is known as ______.",
        "options": {"A": "Canaan", "B": "Haran", "C": "Shechem", "D": "Oak of Moreh"},
        "answer": "B",
    },
    {
        "stem": "40. God promised to make Abraham's name ______.",
        "options": {"A": "great", "B": "famous", "C": "popular", "D": "awesome"},
        "answer": "A",
    },
]

THEORY = [
    {
        "stem": "1. (a) What is repentance?\n(b) Describe how King David repented from his sins.\n(c) State three consequences of lack of repentance.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "2. (a) Narrate how Zacchaeus encountered Jesus.\n(b) State three lessons Christians can learn from the story.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "3. (a) What is obedience?\n(b) Describe how Abraham obeyed the call of God.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4. (a) Describe the repentance of the people of Nineveh.\n(b) State two lessons from the story.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "5. (a) Who was John the Baptist?\n(b) Identify four groups of people that came to John the Baptist for repentance.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "6. (a) How did the sons of Eli sin against God?\n(b) State four ways God punished the household of Eli for lack of repentance.\n(c) State three lessons Christians can learn from the story.",
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="CRS")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="joynwakaegu@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 23, 9, 45, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 10, 45, tzinfo=lagos)

    bank, _ = QuestionBank.objects.get_or_create(
        owner=teacher,
        name=BANK_NAME,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={
            "description": DESCRIPTION,
            "assignment": assignment,
            "is_active": True,
        },
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
            "dean_review_comment": "Approved for Monday second paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 9:45 AM WAT.",
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
    exam.dean_review_comment = "Approved for Monday second paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 9:45 AM WAT."
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
            source_reference=f"JS1-CRS-20260323-OBJ-{index:02d}",
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
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=Decimal("1.00"),
        )
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            marks=item["marks"],
            source_reference=f"JS1-CRS-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=item["marks"],
        )
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 50
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS1-CRS-EXAM",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
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
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
        }
    )


main()
