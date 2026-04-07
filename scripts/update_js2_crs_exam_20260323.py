from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.cbt.models import CorrectAnswer, Exam


EXAM_ID = 157
TITLE = "MON 10:10-11:10 JS2 Christian Religious Studies Second Term Exam"
LAGOS = ZoneInfo("Africa/Lagos")
START = datetime(2026, 3, 23, 10, 10, tzinfo=LAGOS)
END = datetime(2026, 3, 23, 11, 10, tzinfo=LAGOS)
INSTRUCTIONS = (
    "SECOND TERM EXAMINATION\n"
    "SUBJECT: CRS\n"
    "CLASS: JSS2\n"
    "Answer all objective questions in Section A and answer all questions in Section B."
)

OBJECTIVES = [
    ("1. \"Let your light shine\" means believers should ______.", {"A": "Hide", "B": "Boast", "C": "do good works", "D": "fight"}, "C"),
    ("2. Jesus called His first four disciples while they were ______.", {"A": "Praying", "B": "Fishing", "C": "Teaching", "D": "Farming"}, "B"),
    ("3. The first two disciples called by Jesus were ______.", {"A": "James and John", "B": "Peter and Andrew", "C": "Matthew and Thomas", "D": "Philip and Bartholomew"}, "B"),
    ("4. Jesus said, \"Follow me, and I will make you ______.\"", {"A": "Prophets", "B": "Teachers", "C": "fishers of men", "D": "rulers"}, "C"),
    ("5. Peter was also called ______.", {"A": "Saul", "B": "Cephas", "C": "Simon", "D": "John"}, "B"),
    ("6. James and John were the sons of ______.", {"A": "Zebedee", "B": "Alphaeus", "C": "Jonah", "D": "Cleopas"}, "A"),
    ("7. At the call of the twelve, Jesus surnamed James and John, ______. This means sons of thunder.", {"A": "Boanerges", "B": "Alphaeus", "C": "Jonah", "D": "Cleopas"}, "A"),
    ("8. According to Luke 5 at the call of the first four disciples, Jesus taught the crowd from ______.", {"A": "the temple", "B": "a mountain", "C": "Peter's boat", "D": "the synagogue"}, "B"),
    ("9. The miraculous catch of fish at the call of the first four disciples showed Jesus' ______.", {"A": "Weakness", "B": "authority and power", "C": "fear", "D": "doubt"}, "B"),
    ("10. Peter's reaction after the miracle at the lake of Gennesaret was to ______.", {"A": "celebrate loudly", "B": "run away", "C": "kneel before Jesus", "D": "hide the fish"}, "C"),
    ("11. According to Jesus' teaching on the mount, salt that loses its taste is good for ______.", {"A": "Cooking", "B": "Planting", "C": "Nothing", "D": "Medicine"}, "C"),
    ("12. \"Blessed are the poor in spirit, for theirs is the ______.\"", {"A": "Earth", "B": "kingdom of heaven", "C": "riches", "D": "power"}, "B"),
    ("13. \"Blessed are the meek, for they shall ______.\"", {"A": "Be punished", "B": "inherit the earth", "C": "Be forgotten", "D": "Be rejected"}, "B"),
    ("14. The meek as underlined refers to those who are ______.", {"A": "humble and obedient", "B": "tired", "C": "punished", "D": "rejected"}, "A"),
    ("15. Those persecuted for righteousness' sake will receive ______.", {"A": "Gold", "B": "the kingdom of heaven", "C": "land", "D": "praise"}, "B"),
    ("16. Salt is used mainly to ______.", {"A": "destroy", "B": "preserve and flavor", "C": "hide", "D": "weaken"}, "B"),
    ("17. Christians are called the light of the ______.", {"A": "Fire", "B": "Sun", "C": "world", "D": "Rulers"}, "C"),
    ("18. Jesus said Christians are the city set on a hill that cannot be ______.", {"A": "strong", "B": "hidden", "C": "broken", "D": "Shaken"}, "B"),
    ("19. As Christians Jesus encouraged us that let our good works glorify our ______.", {"A": "Friends", "B": "Church", "C": "Father in heaven", "D": "Leaders"}, "C"),
    ("20. In Matthew 6:14-15, if you forgive others, your heavenly Father will ______ you.", {"A": "Punish", "B": "Bless", "C": "forgive", "D": "Ignore"}, "C"),
    ("21. The call of the first four disciples proves that discipleship requires total ______.", {"A": "obedience and sacrifice", "B": "Wealth", "C": "Pride", "D": "Comfort"}, "A"),
    ("22. Following Jesus may involve ______.", {"A": "Luxury", "B": "Persecution and insult", "C": "Entertainment and pleasure", "D": "Laziness and meditation"}, "B"),
    ("23. The call of the disciples teaches immediate ______.", {"A": "Delay", "B": "Obedience", "C": "Argument", "D": "Fear"}, "B"),
    ("24. Who among the twelve disciples is called a traitor?", {"A": "Judas Iscariot", "B": "James son of Alphaeus", "C": "Bartholomew", "D": "Thomas the twin"}, "A"),
    ("25. At the lake Simon Peter said to Jesus ______.", {"A": "Depart from me, for I am a sinful man", "B": "All authority and power has been given unto you.", "C": "Fear not I am with you", "D": "Have mercy upon me oh Lord"}, "A"),
    ("26. Before Jesus called the twelve disciples He ______.", {"A": "prayed", "B": "fasted", "C": "gave alms to the poor", "D": "summoned his disciples"}, "A"),
    ("27. Andrew was the brother of ______.", {"A": "John", "B": "James", "C": "Peter", "D": "Matthew"}, "C"),
    ("28. Beatitude is derived from the Latin word ______.", {"A": "Betrius", "B": "sanctus", "C": "Beatus", "D": "Alpha"}, "C"),
    ("29. According to Jesus, prayer should be offered __________.", {"A": "only in the synagogue", "B": "quietly and sincerely to God", "C": "loudly to impress people", "D": "only during festivals"}, "B"),
    ("30. Jesus warned that people who pray just to be seen by others are ________.", {"A": "Wise", "B": "Humble", "C": "Hypocrites", "D": "Prophets"}, "C"),
    ("31. Jesus taught His disciples a model prayer known as the ___________.", {"A": "Prayer of Moses", "B": "Lord's Prayer", "C": "Prayer of David", "D": "Angel's Prayer"}, "B"),
    ("32. In the Lord's Prayer, \"Give us this day our daily bread\" teaches us to ______.", {"A": "store food for many years", "B": "depend on God for our daily needs", "C": "borrow from friends", "D": "work only on Sundays"}, "B"),
    ("33. According to Jesus' teaching, when people fast they should __________.", {"A": "look sad and weak", "B": "announce it publicly", "C": "appear neat and cheerful", "D": "stop talking to others"}, "C"),
    ("34. Jesus condemned those who disfigure their faces while fasting because they ______.", {"A": "wanted to gain attention from people", "B": "were sick", "C": "wanted to help others", "D": "were hungry"}, "A"),
    ("35. Fasting, according to Jesus, should be done mainly to _______.", {"A": "punish the body", "B": "draw closer to God", "C": "impress friends", "D": "avoid work"}, "B"),
    ("36. Jesus taught that instead of taking revenge, a Christian should _________.", {"A": "fight back immediately", "B": "forgive the offender", "C": "ignore everyone", "D": "report to the king"}, "B"),
    ("37. In His teaching on revenge, Jesus said if someone slaps you on one cheek, you should _______.", {"A": "slap back harder", "B": "run away", "C": "turn the other cheek", "D": "shout loudly"}, "C"),
    ("38. Jesus taught that we should love ______.", {"A": "only our friends", "B": "only our family", "C": "our neighbours and enemies", "D": "only rich people"}, "C"),
    ("39. The teaching of Jesus about loving enemies encourages believers to ________.", {"A": "hate their enemies", "B": "seek revenge", "C": "pray for those who persecute them", "D": "avoid everyone"}, "C"),
    ("40. Jesus' teaching on prayer, fasting, and revenge mainly promotes __________.", {"A": "pride and anger", "B": "humility, forgiveness, and sincerity", "C": "selfishness and revenge", "D": "wealth and power"}, "B"),
]

THEORY = [
    "1a. Narrate the call of the first four disciples of Jesus.\n1b. State three lessons Christians can learn from the call of the first four disciples.",
    "2a. Mention the names of the twelve apostles.\n2b. State four reasons for calling the twelve apostles.",
    "3a. Narrate the temptation of Jesus Christ.\n3b. State four ways Christians can overcome temptation.",
    "4a. What is fasting?\n4b. How did Jesus advise Christians to fast?\n4c. State four importance of fasting.",
    "5a. What is prayer?\n5b. Describe the right way Jesus advised Christians to fast.\n5c. State the importance of prayer.",
    "6a. What is beatitude?\n6b. List six beatitudes of Jesus on the mount.\n6c. Explain any two you know.",
]


def update_exam():
    exam = Exam.objects.select_related("blueprint").get(id=EXAM_ID)
    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts; refusing to modify live paper.")

    rows = list(exam.exam_questions.select_related("question").order_by("sort_order"))
    if len(rows) != 46:
        raise RuntimeError(f"Expected 46 rows, found {len(rows)}")

    exam.title = TITLE
    exam.schedule_start = START
    exam.schedule_end = END
    exam.description = "SECOND TERM EXAMINATION CLASS: JSS2 SUBJECT: CRS"
    exam.save(update_fields=["title", "schedule_start", "schedule_end", "description", "updated_at"])

    blueprint = exam.blueprint
    blueprint.duration_minutes = 50
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS2-CRS-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": 40,
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

    for offset, stem in enumerate(THEORY, start=41):
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
