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


TITLE = "MON 9:45-10:45 JS3 Christian Religious Studies Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION CLASS: JSS3 SUBJECT: CHRISTIAN RELIGIOUS STUDIES"
BANK_NAME = "JS3 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions you know. "
    "Timer is 50 minutes. Exam window closes at 10:45 AM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Jesus promised His disciples that they would receive the ______.", "options": {"A": "Crown", "B": "Holy Spirit", "C": "Kingdom", "D": "Reward"}, "answer": "B"},
    {"stem": "2. The disciples were told to wait in ______ for the promise of the Holy Spirit.", "options": {"A": "Nazareth", "B": "Bethlehem", "C": "Jerusalem", "D": "Samaria"}, "answer": "C"},
    {"stem": "3. The coming of the Holy Spirit would give the disciples ______ to preach the Gospel.", "options": {"A": "Riches", "B": "Power", "C": "Land", "D": "Wisdom"}, "answer": "B"},
    {"stem": "4. The promise of the Holy Spirit helped the disciples to become ______ witnesses.", "options": {"A": "Fearful", "B": "Bold", "C": "Silent", "D": "doubtful"}, "answer": "B"},
    {"stem": "5. Paul and Barnabas were commissioned in the church at ______.", "options": {"A": "Jerusalem", "B": "Antioch", "C": "Rome", "D": "Corinth"}, "answer": "B"},
    {"stem": "6. The instruction to set apart Paul and Barnabas came through the ______.", "options": {"A": "Prophets", "B": "Holy Spirit", "C": "Apostles", "D": "Elders"}, "answer": "B"},
    {"stem": "7. Before sending Paul and Barnabas out, the church leaders ______.", "options": {"A": "prayed and fasted", "B": "fought", "C": "argued", "D": "slept"}, "answer": "A"},
    {"stem": "8. The church laid their ______ on Paul and Barnabas.", "options": {"A": "Clothes", "B": "Books", "C": "Hands", "D": "Staffs"}, "answer": "C"},
    {"stem": "9. Prophecy means receiving a message from ______.", "options": {"A": "Kings", "B": "People", "C": "God", "D": "Angels"}, "answer": "C"},
    {"stem": "10. One prophet in the church at Antioch was ______.", "options": {"A": "Peter", "B": "Agabus", "C": "Matthew", "D": "Luke"}, "answer": "B"},
    {"stem": "11. The church in Antioch started after believers were scattered because of ______.", "options": {"A": "Celebration", "B": "Persecution", "C": "Famine", "D": "Travel"}, "answer": "B"},
    {"stem": "12. The gospel was first preached in Antioch to the ______.", "options": {"A": "Gentiles", "B": "Jews only", "C": "Kings", "D": "Soldiers"}, "answer": "A"},
    {"stem": "13. ______ was sent from Jerusalem to encourage the believers in the church in Antioch.", "options": {"A": "Barnabas", "B": "James", "C": "Andrew", "D": "Philip"}, "answer": "A"},
    {"stem": "14. The disciples were first called ______ at Antioch.", "options": {"A": "believers", "B": "Apostles", "C": "Christians", "D": "prophets"}, "answer": "C"},
    {"stem": "15. Peter was imprisoned by King ______.", "options": {"A": "Herod", "B": "Caesar", "C": "David", "D": "Solomon"}, "answer": "A"},
    {"stem": "16. While Peter was in prison, the church was ______ in the house of a woman named Mary.", "options": {"A": "Celebrating", "B": "Praying", "C": "Sleeping", "D": "Fighting"}, "answer": "B"},
    {"stem": "17. Peter was released from prison by ______.", "options": {"A": "Soldiers", "B": "an angel", "C": "the king", "D": "a guard"}, "answer": "B"},
    {"stem": "18. When the angel appeared, the chains on Peter's hands ______.", "options": {"A": "broke off", "B": "tightened", "C": "doubled", "D": "burned"}, "answer": "A"},
    {"stem": "19. In the creation story, God created the heavens and the earth in ______.", "options": {"A": "Genesis", "B": "Exodus", "C": "Matthew", "D": "Acts"}, "answer": "A"},
    {"stem": "20. God created man and the land animals on the ______ day.", "options": {"A": "Fourth", "B": "Fifth", "C": "Sixth", "D": "Seventh"}, "answer": "C"},
    {"stem": "21. God rested on the ______ day.", "options": {"A": "Sixth", "B": "Seventh", "C": "Fifth", "D": "Fourth"}, "answer": "B"},
    {"stem": "22. God placed Adam and Eve in the Garden of ______.", "options": {"A": "Eden", "B": "Jericho", "C": "Galilee", "D": "Samaria"}, "answer": "A"},
    {"stem": "23. The serpent tempted ______ in the garden.", "options": {"A": "Adam", "B": "Eve", "C": "Cain", "D": "Abel"}, "answer": "B"},
    {"stem": "24. The forbidden fruit was from the tree of the knowledge of ______.", "options": {"A": "Life", "B": "Wisdom", "C": "good and evil", "D": "power"}, "answer": "C"},
    {"stem": "25. After eating the fruit, Adam and Eve realized they were ______.", "options": {"A": "hungry", "B": "naked", "C": "tired", "D": "sick"}, "answer": "B"},
    {"stem": "26. Jesus was tempted by the ______.", "options": {"A": "angel", "B": "devil", "C": "king", "D": "priest"}, "answer": "B"},
    {"stem": "27. Jesus fasted for ______ days and nights.", "options": {"A": "20", "B": "30", "C": "40", "D": "50"}, "answer": "C"},
    {"stem": "28. The devil first asked Jesus to turn ______ into bread.", "options": {"A": "Sand", "B": "Stones", "C": "Water", "D": "Trees"}, "answer": "B"},
    {"stem": "29. Jesus answered the devil by quoting from the ______.", "options": {"A": "Bible", "B": "Psalms", "C": "Scriptures", "D": "Prophets"}, "answer": "C"},
    {"stem": "30. Jesus was baptized in the River ______.", "options": {"A": "Nile", "B": "Jordan", "C": "Euphrates", "D": "Tigris"}, "answer": "B"},
    {"stem": "31. Jesus was baptized by ______.", "options": {"A": "Peter", "B": "John the Baptist", "C": "James", "D": "Andrew"}, "answer": "B"},
    {"stem": "32. During Jesus' baptism, the Holy Spirit descended like a ______.", "options": {"A": "Flame", "B": "Dove", "C": "Cloud", "D": "Wind"}, "answer": "B"},
    {"stem": "33. A voice from heaven said, \"This is my ______ Son.\"", "options": {"A": "Good", "B": "Faithful", "C": "Beloved", "D": "Righteous"}, "answer": "C"},
    {"stem": "34. Persecution means ______ Christians because of their faith.", "options": {"A": "Helping and punishing", "B": "Praising and harassing", "C": "Punishing and molesting", "D": "Teaching and insulting"}, "answer": "C"},
    {"stem": "35. One of the early persecutors of the church was ______.", "options": {"A": "Paul", "B": "Luke", "C": "John", "D": "Timothy"}, "answer": "A"},
    {"stem": "36. The believers scattered during persecution and began to ______.", "options": {"A": "boldly fight the gentiles", "B": "boldly preach the gospel", "C": "hide forever", "D": "stop praying"}, "answer": "B"},
    {"stem": "37. James the brother of John was killed with a ______.", "options": {"A": "Sword", "B": "Spear", "C": "Stone", "D": "Arrow"}, "answer": "A"},
    {"stem": "38. The early church grew stronger despite ______.", "options": {"A": "Wealth", "B": "Persecution", "C": "Celebrations", "D": "Silence"}, "answer": "B"},
    {"stem": "39. The Holy Spirit helps believers to ______.", "options": {"A": "Preach", "B": "Learn", "C": "be bold", "D": "All of the above"}, "answer": "D"},
    {"stem": "40. Christians today learn from the early church to remain ______ in faith.", "options": {"A": "Weak", "B": "Doubtful", "C": "Faithful", "D": "Fearful"}, "answer": "C"},
    {"stem": "41. Zacchaeus said he would repay ______ times anyone he cheated.", "options": {"A": "Two", "B": "Three", "C": "Four", "D": "Five"}, "answer": "C"},
    {"stem": "42. Zacchaeus was short in ______.", "options": {"A": "Age", "B": "stature", "C": "Wisdom", "D": "Wealth"}, "answer": "B"},
    {"stem": "43. John the Baptist warned the people that every tree that does not bear good fruit will be ______.", "options": {"A": "praised by God", "B": "cut down and thrown into hell", "C": "watered and killed", "D": "decorated by God"}, "answer": "B"},
    {"stem": "44. God saw the true repentance of the Ninevites and ______.", "options": {"A": "changed His mind", "B": "destroyed them", "C": "ignored them", "D": "fought them"}, "answer": "A"},
    {"stem": "45. Zacchaeus showed his true repentance to Jesus through ______.", "options": {"A": "words only", "B": "restitution", "C": "hiding", "D": "fighting"}, "answer": "B"},
    {"stem": "46. John the Baptist told the people to share with those who have ______.", "options": {"A": "much", "B": "two houses", "C": "none", "D": "cars"}, "answer": "C"},
    {"stem": "47. \"To your descendants I will give this land.\" God said this statement to ______.", "options": {"A": "Abraham", "B": "Nahor", "C": "Lot", "D": "Terah"}, "answer": "A"},
    {"stem": "48. Where did God appear to show Abraham the promised land?", "options": {"A": "Shechem", "B": "at the oak of Moreh", "C": "Joppa", "D": "Tarshish"}, "answer": "B"},
    {"stem": "49. Abraham was ______ years old when he left his father's land.", "options": {"A": "ninety-nine", "B": "seventy-five", "C": "hundred", "D": "seventeen"}, "answer": "B"},
    {"stem": "50. Abraham's father's land is known as ______.", "options": {"A": "Canaan", "B": "Haran", "C": "Shechem", "D": "Oak of Moreh"}, "answer": "B"},
    {"stem": "51. God promised to make Abraham's name ______.", "options": {"A": "great", "B": "famous", "C": "popular", "D": "Awesome"}, "answer": "A"},
    {"stem": "52. Paul and Barnabas began their first missionary journey from ______.", "options": {"A": "Antioch", "B": "Jerusalem", "C": "Seleucia", "D": "Lystra"}, "answer": "C"},
    {"stem": "53. Seleucia is important in Paul's missionary journey because it was ______.", "options": {"A": "where Paul performed miracles", "B": "the seaport from which they sailed", "C": "where Paul was imprisoned", "D": "a place of persecution"}, "answer": "B"},
    {"stem": "54. At Salamis, Paul and Barnabas preached in the ______.", "options": {"A": "market places", "B": "synagogues of the Jews", "C": "temples of idols", "D": "streets only"}, "answer": "B"},
    {"stem": "55. Who accompanied Paul and Barnabas to Salamis as their assistant?", "options": {"A": "Silas", "B": "Timothy", "C": "John Mark", "D": "Luke"}, "answer": "C"},
    {"stem": "56. At Paphos, Paul confronted a false prophet named ______.", "options": {"A": "Demas", "B": "Elymas", "C": "Ananias", "D": "Simon"}, "answer": "B"},
    {"stem": "57. What miracle did Paul perform on Elymas at Paphos?", "options": {"A": "He healed him", "B": "He raised him from the dead", "C": "He made him blind", "D": "He cast him into prison"}, "answer": "C"},
    {"stem": "58. The proconsul who believed the message at Paphos was ______.", "options": {"A": "Sergius Paulus", "B": "Cornelius", "C": "Felix", "D": "Festus"}, "answer": "A"},
    {"stem": "59. At Lystra, Paul healed a man who was ______.", "options": {"A": "blind from birth", "B": "deaf and dumb", "C": "lame from birth", "D": "paralyzed by disease"}, "answer": "C"},
    {"stem": "60. After the miracle at Lystra, the people thought Paul and Barnabas were ______.", "options": {"A": "Angels", "B": "Prophets", "C": "gods", "D": "King"}, "answer": "C"},
]

THEORY = [
    {
        "stem": "1. (a) Narrate how the apostles received the Holy Spirit on the day of Pentecost.\n(b) State three lessons Christians can learn from the coming of the Holy Spirit.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "2. (a) Describe how Paul and Barnabas were commissioned for missionary work in the church of Antioch.\n(b) List three proper attitudes a true Christian can show towards his persecutors.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "3. (a) Narrate the miraculous release of Peter from prison.\n(b) State two lessons Christians can learn from this story.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "5. (a) Briefly explain the missionary activity of Paul and Barnabas at Paphos.\n(b) State three lessons present-day missionaries can learn from the story.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "6. (a) What is persecution?\n(b) How did Saul persecute the early church?\n(c) State three effects of Saul's conversion.",
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
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
            source_reference=f"JS3-CRS-20260323-OBJ-{index:02d}",
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
            source_reference=f"JS3-CRS-20260323-TH-{index:02d}",
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
        "paper_code": "JS3-CRS-EXAM",
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
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
        }
    )


main()
