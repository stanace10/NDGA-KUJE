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


TITLE = "MON 9:45-10:45 JS2 Christian Religious Studies Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION SUBJECT: CRS CLASS: JSS2"
BANK_NAME = "JS2 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all questions. "
    "Timer is 50 minutes. Exam window closes at 10:45 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. \"Let your light shine\" means believers should ______.", "options": {"A": "Hide", "B": "Boast", "C": "do good works", "D": "fight"}, "answer": "C"},
    {"stem": "2. Jesus called His first four disciples while they were ______.", "options": {"A": "Praying", "B": "Fishing", "C": "Teaching", "D": "Farming"}, "answer": "B"},
    {"stem": "3. The first two disciples called by Jesus were ______.", "options": {"A": "James and John", "B": "Peter and Andrew", "C": "Matthew and Thomas", "D": "Philip and Bartholomew"}, "answer": "B"},
    {"stem": "4. Jesus said, \"Follow me, and I will make you ______.\"", "options": {"A": "Prophets", "B": "Teachers", "C": "fishers of men", "D": "rulers"}, "answer": "C"},
    {"stem": "5. Peter was also called ______.", "options": {"A": "Saul", "B": "Cephas", "C": "Simon", "D": "John"}, "answer": "B"},
    {"stem": "6. James and John were the sons of ______.", "options": {"A": "Zebedee", "B": "Alphaeus", "C": "Jonah", "D": "Cleopas"}, "answer": "A"},
    {"stem": "7. At the call of the twelve, Jesus surnamed James and John, ______. This means sons of thunder.", "options": {"A": "Boanerges", "B": "Alphaeus", "C": "Jonah", "D": "Cleopas"}, "answer": "A"},
    {"stem": "8. According to Luke 5, at the call of the first four disciples, Jesus taught the crowd from ______.", "options": {"A": "the temple", "B": "a mountain", "C": "Peter's boat", "D": "the synagogue"}, "answer": "C"},
    {"stem": "9. The miraculous catch of fish at the call of the first four disciples showed Jesus' ______.", "options": {"A": "weakness", "B": "authority and power", "C": "fear", "D": "doubt"}, "answer": "B"},
    {"stem": "10. Peter's reaction after the miracle at the lake of Gennesaret was to ______.", "options": {"A": "celebrate loudly", "B": "run away", "C": "kneel before Jesus", "D": "hide the fish"}, "answer": "C"},
    {"stem": "11. According to Jesus' teaching on the mount, salt that loses its taste is good for ______.", "options": {"A": "Cooking", "B": "Planting", "C": "Nothing", "D": "Medicine"}, "answer": "C"},
    {"stem": "12. \"Blessed are the poor in spirit, for theirs is the ______.\"", "options": {"A": "Earth", "B": "kingdom of heaven", "C": "riches", "D": "power"}, "answer": "B"},
    {"stem": "13. \"Blessed are the meek, for they shall be ______.\"", "options": {"A": "Punished", "B": "inherit the earth", "C": "Forgotten", "D": "Rejected"}, "answer": "B"},
    {"stem": "14. The meek refers to those who are ______.", "options": {"A": "Humble and obedient", "B": "Tired", "C": "Punished", "D": "Rejected"}, "answer": "A"},
    {"stem": "15. Those persecuted for righteousness' sake will receive ______.", "options": {"A": "Gold", "B": "kingdom of heaven", "C": "land", "D": "praise"}, "answer": "B"},
    {"stem": "16. Salt is used mainly to ______.", "options": {"A": "destroy", "B": "preserve and flavor", "C": "hide", "D": "weaken"}, "answer": "B"},
    {"stem": "17. Christians are called the light of the ______.", "options": {"A": "Fire", "B": "Sun", "C": "world", "D": "Rulers"}, "answer": "C"},
    {"stem": "18. Jesus said Christians are the city set on a hill that cannot be ______.", "options": {"A": "strong", "B": "hidden", "C": "broken", "D": "shaken"}, "answer": "B"},
    {"stem": "19. As Christians, Jesus encouraged us that our good works should glorify our ______.", "options": {"A": "Friends", "B": "Church", "C": "Father in heaven", "D": "Leaders"}, "answer": "C"},
    {"stem": "20. In Matthew 6:14-15, if you forgive others, your heavenly Father will ______ you.", "options": {"A": "Punish", "B": "Bless", "C": "Forgive", "D": "Ignore"}, "answer": "C"},
    {"stem": "21. Discipleship requires total ______.", "options": {"A": "Obedience", "B": "Wealth", "C": "Pride", "D": "Comfort"}, "answer": "A"},
    {"stem": "22. Following Jesus may involve ______.", "options": {"A": "Luxury", "B": "Persecution", "C": "Entertainment", "D": "Laziness"}, "answer": "B"},
    {"stem": "23. The call of the disciples teaches immediate ______.", "options": {"A": "Delay", "B": "Obedience", "C": "Argument", "D": "Fear"}, "answer": "B"},
    {"stem": "24. James and John were the sons of ______.", "options": {"A": "Zebedee", "B": "Alphaeus", "C": "Jonah", "D": "Cleopas"}, "answer": "A"},
    {"stem": "25. The miraculous catch of fish at the call of the first four disciples showed Jesus' ______.", "options": {"A": "weakness", "B": "authority and power", "C": "fear", "D": "doubt"}, "answer": "B"},
    {"stem": "26. As Christians, Jesus encouraged us that our good works should glorify our ______.", "options": {"A": "Friends", "B": "Church", "C": "Father in heaven", "D": "Leaders"}, "answer": "C"},
    {"stem": "27. Andrew was the brother of ______.", "options": {"A": "John", "B": "James", "C": "Peter", "D": "Matthew"}, "answer": "C"},
    {"stem": "28. Beatitude is derived from the Latin word ______.", "options": {"A": "Betrius", "B": "sanctus", "C": "Beatus", "D": "Alpha"}, "answer": "C"},
    {"stem": "29. According to Jesus, prayer should be offered ______.", "options": {"A": "only in the synagogue", "B": "quietly and sincerely to God", "C": "loudly to impress people", "D": "only during festivals"}, "answer": "B"},
    {"stem": "30. Jesus warned that people who pray just to be seen by others are ______.", "options": {"A": "Wise", "B": "Humble", "C": "Hypocrites", "D": "Prophets"}, "answer": "C"},
    {"stem": "31. Jesus taught His disciples a model prayer known as the ______.", "options": {"A": "Prayer of Moses", "B": "Lord's Prayer", "C": "Prayer of David", "D": "Angel's Prayer"}, "answer": "B"},
    {"stem": "32. In the Lord's Prayer, \"Give us this day our daily bread\" teaches us to ______.", "options": {"A": "store food for many years", "B": "depend on God for our daily needs", "C": "borrow from friends", "D": "work only on Sundays"}, "answer": "B"},
    {"stem": "33. According to Jesus' teaching, when people fast they should ______.", "options": {"A": "look sad and weak", "B": "announce it publicly", "C": "appear neat and cheerful", "D": "stop talking to others"}, "answer": "C"},
    {"stem": "34. Jesus condemned those who disfigure their faces while fasting because they ______.", "options": {"A": "wanted to gain attention from people", "B": "were sick", "C": "wanted to help others", "D": "were hungry"}, "answer": "A"},
    {"stem": "35. Fasting, according to Jesus, should be done mainly to ______.", "options": {"A": "punish the body", "B": "draw closer to God", "C": "impress friends", "D": "avoid work"}, "answer": "B"},
    {"stem": "36. Jesus taught that instead of taking revenge, a Christian should ______.", "options": {"A": "fight back immediately", "B": "forgive the offender", "C": "ignore everyone", "D": "report to the king"}, "answer": "B"},
    {"stem": "37. In His teaching on revenge, Jesus said if someone slaps you on one cheek, you should ______.", "options": {"A": "slap back harder", "B": "run away", "C": "turn the other cheek", "D": "shout loudly"}, "answer": "C"},
    {"stem": "38. Jesus taught that we should love ______.", "options": {"A": "only our friends", "B": "only our family", "C": "our neighbours and enemies", "D": "only rich people"}, "answer": "C"},
    {"stem": "39. The teaching of Jesus about loving enemies encourages believers to ______.", "options": {"A": "hate their enemies", "B": "seek revenge", "C": "pray for those who persecute them", "D": "avoid everyone"}, "answer": "C"},
    {"stem": "40. Jesus' teaching on prayer, fasting, and revenge mainly promotes ______.", "options": {"A": "pride and anger", "B": "humility, forgiveness, and sincerity", "C": "selfishness and revenge", "D": "wealth and power"}, "answer": "B"},
]

THEORY = [
    {
        "stem": "1. (a) Narrate the call of the first four disciples of Jesus.\n(b) State three lessons Christians can learn from the call of the first four disciples.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "2. (a) Mention the names of the twelve apostles.\n(b) State three reasons for calling the twelve apostles.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "3. (a) Narrate the temptation of Jesus Christ.\n(b) State four ways Christians can overcome temptation.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4. (a) What is fasting?\n(b) How did Jesus advise Christians to fast?\n(c) State four importance of fasting.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "5. (a) What is prayer?\n(b) Describe the right way Jesus advised Christians to pray and fast.\n(c) State the importance of prayer.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "6. (a) What is Beatitude?\n(b) List four beatitudes of Jesus on the mount and explain any two.",
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
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
            source_reference=f"JS2-CRS-20260323-OBJ-{index:02d}",
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
            source_reference=f"JS2-CRS-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 50
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = False
    blueprint.shuffle_options = False
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS2-CRS-EXAM",
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
