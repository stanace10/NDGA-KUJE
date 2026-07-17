from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.cbt.models import CBTQuestionType, CorrectAnswer, Exam, ExamQuestion, Question


EXAM_ID = 158
TITLE = "MON 10:10-11:10 JS3 Christian Religious Studies Second Term Exam"
LAGOS = ZoneInfo("Africa/Lagos")
START = datetime(2026, 3, 23, 10, 10, tzinfo=LAGOS)
END = datetime(2026, 3, 23, 11, 10, tzinfo=LAGOS)
INSTRUCTIONS = (
    "SECOND TERM EXAMINATION\n"
    "SUBJECT: CHRISTIAN RELIGIOUS STUDIES\n"
    "CLASS: JSS3\n"
    "Answer all objective questions in Section A and answer any four questions in Section B."
)

OBJECTIVES = [
    ("1. Jesus promised His disciples that they would receive the ______.", {"A": "Crown", "B": "Holy Spirit", "C": "Kingdom", "D": "Reward"}, "B"),
    ("2. The disciples were told to wait in ______ for the promise of the Holy Spirit.", {"A": "Nazareth", "B": "Bethlehem", "C": "Jerusalem", "D": "Samaria"}, "C"),
    ("3. The coming of the Holy Spirit would give the disciples ______ to preach the Gospel.", {"A": "Riches", "B": "Power", "C": "Land", "D": "Wisdom"}, "B"),
    ("4. The promise of the Holy Spirit helped the disciples to become ______ witnesses.", {"A": "Fearful", "B": "Bold", "C": "Silent", "D": "doubtful"}, "B"),
    ("5. Paul and Barnabas were commissioned in the church at ______.", {"A": "Jerusalem", "B": "Antioch", "C": "Rome", "D": "Corinth"}, "B"),
    ("6. The instruction to set apart Paul and Barnabas came through the ______.", {"A": "Prophets", "B": "Holy Spirit", "C": "Apostles", "D": "Elders"}, "B"),
    ("7. Before sending Paul and Barnabas out, the church leaders ______.", {"A": "prayed and fasted", "B": "fought", "C": "argued", "D": "slept"}, "A"),
    ("8. The church laid their ______ on Paul and Barnabas.", {"A": "Clothes", "B": "Books", "C": "Hands", "D": "Staffs"}, "C"),
    ("9. Prophecy means receiving a message from ______.", {"A": "Kings", "B": "People", "C": "God", "D": "Angels"}, "C"),
    ("10. One prophet in the church at Antioch was ______.", {"A": "Peter", "B": "Agabus", "C": "Matthew", "D": "Luke"}, "B"),
    ("11. The church in Antioch started after believers were scattered because of ______.", {"A": "Celebration", "B": "Persecution", "C": "Famine", "D": "Travel"}, "B"),
    ("12. The gospel was first preached in Antioch to the ______.", {"A": "Gentiles", "B": "Jews only", "C": "Kings", "D": "Soldiers"}, "A"),
    ("13. ______ was sent from Jerusalem to encourage the believers in the church in Antioch.", {"A": "Barnabas", "B": "James", "C": "Andrew", "D": "Philip"}, "A"),
    ("14. The disciples were first called ______ at Antioch.", {"A": "believers", "B": "Apostles", "C": "Christians", "D": "prophets"}, "C"),
    ("15. Peter was imprisoned by King ______.", {"A": "Herod", "B": "Caesar", "C": "David", "D": "Solomon"}, "A"),
    ("16. While Peter was in prison, the church was ______ in the house of the woman named Mary.", {"A": "Celebrating", "B": "Praying", "C": "Sleeping", "D": "Fighting"}, "B"),
    ("17. Peter was released from prison by ______.", {"A": "Soldiers", "B": "an angel", "C": "the king", "D": "a guard"}, "B"),
    ("18. When the angel appeared, the chains on Peter's hands ______.", {"A": "broke off", "B": "tightened", "C": "doubled", "D": "burned"}, "A"),
    ("19. In the creation story, God created the heavens and the earth in ______.", {"A": "Genesis", "B": "Exodus", "C": "Matthew", "D": "Acts"}, "A"),
    ("20. God created man and the land animals on the ______ day.", {"A": "Fourth", "B": "Fifth", "C": "Sixth", "D": "Seventh"}, "C"),
    ("21. God rested on the ______ day.", {"A": "Sixth", "B": "Seventh", "C": "Fifth", "D": "Fourth"}, "B"),
    ("22. God punished Adam and Eve because they ______.", {"A": "ate the forbidden fruit in the Garden of Eden", "B": "disobeyed His instruction", "C": "questioned His instruction", "D": "wanted to be wise"}, "B"),
    ("23. The serpent tempted ______ in the garden.", {"A": "Adam", "B": "Eve", "C": "Cain", "D": "Abel"}, "B"),
    ("24. The forbidden fruit was from the tree of the knowledge of ______.", {"A": "Life", "B": "Wisdom", "C": "good and evil", "D": "power"}, "C"),
    ("25. After eating the fruit, Adam and Eve realized they were ______.", {"A": "hungry", "B": "naked", "C": "tired", "D": "sick"}, "B"),
    ("26. Jesus was tempted by the devil after He fasted for ______.", {"A": "Forty days", "B": "Fourteen days", "C": "30 days", "D": "Forty-four days"}, "A"),
    ("27. Jesus was ________ years old when He started His ministry.", {"A": "20", "B": "30", "C": "40", "D": "50"}, "B"),
    ("28. The devil first asked Jesus to turn ______ into bread.", {"A": "Sand", "B": "Stones", "C": "Water", "D": "Trees"}, "B"),
    ("29. Jesus answered the devil by quoting from the ______.", {"A": "Bible", "B": "Psalms", "C": "Scriptures", "D": "Prophets"}, "C"),
    ("30. Jesus was baptized in the River ______.", {"A": "Nile", "B": "Jordan", "C": "Euphrates", "D": "Tigris"}, "B"),
    ("31. The forerunner of Jesus was ______.", {"A": "Peter", "B": "John the Baptist", "C": "James", "D": "Andrew"}, "B"),
    ("32. During Jesus' baptism, the Holy Spirit descended like a ______.", {"A": "Flame", "B": "Dove", "C": "Cloud", "D": "Wind"}, "B"),
    ("33. A voice from heaven said, \"This is my ______ Son.\"", {"A": "Good", "B": "Faithful", "C": "Beloved", "D": "Righteous"}, "C"),
    ("34. Persecution means ______ Christians because of their faith.", {"A": "Helping and punishing", "B": "Praising and harassing", "C": "Punishing and molesting", "D": "Teaching and insulting"}, "C"),
    ("35. One of the early persecutors of the church was ______.", {"A": "Paul", "B": "Luke", "C": "John", "D": "Timothy"}, "A"),
    ("36. The believers scattered during persecution and began to ______.", {"A": "boldly fight the Gentiles", "B": "boldly preach the gospel", "C": "hide forever", "D": "stop praying"}, "B"),
    ("37. James the brother of John was killed with a ______.", {"A": "Sword", "B": "Spear", "C": "Stone", "D": "Arrow"}, "A"),
    ("38. The early church grew stronger despite ______.", {"A": "Wealth", "B": "Persecution", "C": "Celebrations", "D": "Silence"}, "B"),
    ("39. The Holy Spirit helps believers to ______.", {"A": "Preach", "B": "Learn", "C": "be bold", "D": "All of the above"}, "D"),
    ("40. Christians today learn from the early church to remain ______ in faith.", {"A": "Weak", "B": "Doubtful", "C": "Faithful", "D": "Fearful"}, "C"),
    ("41. Zacchaeus said he would repay ______ times anyone he cheated.", {"A": "Two", "B": "Three", "C": "Four", "D": "Five"}, "C"),
    ("42. Zacchaeus was short in ______.", {"A": "Age", "B": "stature", "C": "Wisdom", "D": "Wealth"}, "B"),
    ("43. John the Baptist warned the people that every tree that does not bear good fruit will be __________.", {"A": "praised by God", "B": "cut down and thrown into hell", "C": "watered and killed", "D": "decorated by God"}, "B"),
    ("44. God saw the true repentance of the Ninevites and ______.", {"A": "changed His mind", "B": "destroyed them", "C": "ignored them", "D": "fought them"}, "A"),
    ("45. Zacchaeus showed his true repentance to Jesus through ______.", {"A": "words only", "B": "restitution", "C": "hiding", "D": "fighting"}, "B"),
    ("46. John the Baptist told the people to share with those who have ______.", {"A": "much", "B": "two houses", "C": "none", "D": "cars"}, "C"),
    ("47. \"To your descendants I will give this land\". God said this statement to _________.", {"A": "Abraham", "B": "Nahor", "C": "Lot", "D": "Terah"}, "A"),
    ("48. Where did God appear to show Abraham the promised land _________?", {"A": "Shechem", "B": "at the oak of Moreh", "C": "Joppa", "D": "Tarshish"}, "B"),
    ("49. Abraham was ________ years old when he left his father's land.", {"A": "ninety-nine", "B": "seventy-five", "C": "hundred", "D": "seventeen"}, "B"),
    ("50. Abraham's father's land is known as ___________.", {"A": "Canaan", "B": "Haran", "C": "Shechem", "D": "Oak of Moreh"}, "B"),
    ("51. God promised to make Abraham's name __________.", {"A": "great", "B": "famous", "C": "popular", "D": "Awesome"}, "A"),
    ("52. Paul and Barnabas began their first missionary journey from _______.", {"A": "Antioch", "B": "Jerusalem", "C": "Seleucia", "D": "Lystra"}, "C"),
    ("53. Seleucia is important in Paul's missionary journey because it was ______.", {"A": "Where Paul performed miracles", "B": "the seaport from which they sailed", "C": "Where Paul was imprisoned", "D": "A place of persecution"}, "B"),
    ("54. At Salamis, Paul and Barnabas preached in the __________.", {"A": "Market places", "B": "Synagogues of the Jews", "C": "Temples of idols", "D": "Streets only"}, "B"),
    ("55. Who accompanied Paul and Barnabas to Salamis as their assistant?", {"A": "Silas", "B": "Timothy", "C": "John Mark", "D": "Luke"}, "C"),
    ("56. At Paphos, Paul confronted a false prophet named ________.", {"A": "Demas", "B": "Elymas", "C": "Ananias", "D": "Simon"}, "B"),
    ("57. What miracle did Paul perform on Elymas at Paphos?", {"A": "He healed him", "B": "He raised him from the dead", "C": "He made him blind", "D": "He cast him into prison"}, "C"),
    ("58. The proconsul who believed the message at Paphos was ______.", {"A": "Sergius Paulus", "B": "Cornelius", "C": "Felix", "D": "Festus"}, "A"),
    ("59. At Lystra, Paul healed a man who was ______.", {"A": "Blind from birth", "B": "Deaf and dumb", "C": "Lame from birth", "D": "Paralyzed by disease"}, "C"),
    ("60. After the miracle at Lystra, the people thought Paul and Barnabas were __________.", {"A": "Angels", "B": "Prophets", "C": "gods", "D": "King"}, "C"),
]

THEORY = [
    "1a. Describe how Paul and Barnabas were commissioned for missionary work in the church of Antioch.\n1b. List three proper attitudes a true Christian can show towards his persecutors.",
    "2a. Narrate the miraculous release of Peter from prison.\n2b. State two lessons Christians can learn from this story.",
    "3a. Briefly explain the missionary activity of Paul and Barnabas at Paphos.\n3b. State three lessons present-day missionaries can learn from the story.",
    "4a. What is persecution?\n4b. How did Saul persecute the early church?\n4c. State three effects of Saul's conversion.",
    "5. Describe how the church began in Antioch.",
    "6a. Briefly give an account of Paul's missionary experience at Lystra.\n6b. State any two lessons Christians can learn from the story.",
]


def update_exam():
    exam = Exam.objects.select_related("blueprint").get(id=EXAM_ID)
    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts; refusing to modify live paper.")

    rows = list(exam.exam_questions.select_related("question").order_by("sort_order"))
    if len(rows) == 65:
        new_question = Question.objects.create(
            question_bank=exam.question_bank,
            created_by=exam.created_by,
            subject=exam.subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=THEORY[5],
            marks=Decimal("10.00"),
            is_active=True,
            source_reference="JS3-CRS-20260323-THEORY-06",
        )
        CorrectAnswer.objects.create(question=new_question, is_finalized=False)
        ExamQuestion.objects.create(
            exam=exam,
            question=new_question,
            sort_order=66,
            marks=Decimal("10.00"),
        )
        rows = list(exam.exam_questions.select_related("question").order_by("sort_order"))
    if len(rows) != 66:
        raise RuntimeError(f"Expected 66 rows, found {len(rows)}")

    exam.title = TITLE
    exam.schedule_start = START
    exam.schedule_end = END
    exam.description = "SECOND TERM EXAMINATION CLASS: JSS3 SUBJECT: CHRISTIAN RELIGIOUS STUDIES"
    exam.save(update_fields=["title", "schedule_start", "schedule_end", "description", "updated_at"])

    blueprint = exam.blueprint
    blueprint.duration_minutes = 50
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS3-CRS-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": 60,
        "theory_count": 6,
        "objective_target_max": "20.00",
        "theory_target_max": "40.00",
    }
    blueprint.save(update_fields=["duration_minutes", "instructions", "section_config", "updated_at"])

    for idx, (stem, options_map, answer) in enumerate(OBJECTIVES, start=1):
        row = rows[idx - 1]
        question = row.question
        question.stem = stem
        question.marks = Decimal("1.00")
        question.save(update_fields=["stem", "marks", "updated_at"])
        options = list(question.options.order_by("sort_order"))
        if len(options) != 4:
            raise RuntimeError(f"Question {idx} expected 4 options, found {len(options)}")
        for sort_order, label in enumerate(["A", "B", "C", "D"], start=1):
            option = options[sort_order - 1]
            option.label = label
            option.option_text = options_map[label]
            option.sort_order = sort_order
            option.save(update_fields=["label", "option_text", "sort_order", "updated_at"])
        correct = CorrectAnswer.objects.get(question=question)
        correct.correct_options.set(question.options.filter(label=answer))
        correct.is_finalized = True
        correct.save(update_fields=["is_finalized", "updated_at"])

    for offset, stem in enumerate(THEORY, start=61):
        row = rows[offset - 1]
        question = row.question
        question.stem = stem
        question.marks = row.marks
        question.save(update_fields=["stem", "marks", "updated_at"])

    print(
        {
            "exam_id": exam.id,
            "title": exam.title,
            "schedule_start": exam.schedule_start.isoformat(),
            "schedule_end": exam.schedule_end.isoformat(),
            "duration_minutes": blueprint.duration_minutes,
            "attempts": exam.attempts.count(),
        }
    )


update_exam()
