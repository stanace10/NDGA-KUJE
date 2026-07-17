from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.cbt.models import CorrectAnswer, Exam, ExamQuestion, Option


EXAM_ID = 156
TITLE = "MON 10:10-11:10 JS1 Christian Religious Studies Second Term Exam"
LAGOS = ZoneInfo("Africa/Lagos")
START = datetime(2026, 3, 23, 10, 10, tzinfo=LAGOS)
END = datetime(2026, 3, 23, 11, 10, tzinfo=LAGOS)
INSTRUCTIONS = (
    "SECOND TERM EXAMINATION\n"
    "SUBJECT: CRS\n"
    "CLASS: JSS1\n"
    "Answer all objective questions in Section A and answer only four questions in Section B."
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
        "stem": "2. Prophet Nathan rebuked King David because he ______",
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
        "options": {
            "A": "King David",
            "B": "Solomon",
            "C": "Moses",
            "D": "Prophet Isaiah",
        },
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
        "stem": "10. The message of John the Baptist prepared the way for the ______.",
        "options": {"A": "Moses", "B": "Elijah", "C": "Messiah", "D": "Peter"},
        "answer": "C",
    },
    {
        "stem": "11. The act of doing what we are told to do without questioning is called _________.",
        "options": {"A": "Repentance", "B": "Obedience", "C": "Disobedience", "D": "Reconciliation"},
        "answer": "B",
    },
    {
        "stem": "12. The two sons of Eli were ________ and ___________.",
        "options": {
            "A": "Hophni and Phinehas",
            "B": "Hophni and Ichabod",
            "C": "Samuel and Isaac",
            "D": "David and Solomon",
        },
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
        "options": {
            "A": "Pray aloud",
            "B": "fast like the hypocrites",
            "C": "rob anyone by violence",
            "D": "travel to the promised land",
        },
        "answer": "C",
    },
    {
        "stem": "16. \"Today, salvation had come to this house, since he is also a son of Abraham...\" this statement was said by Jesus to ______.",
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
        "options": {
            "A": "Protected by the Philistines",
            "B": "hidden in the desert",
            "C": "captured in a war",
            "D": "blessed by the priest",
        },
        "answer": "C",
    },
    {
        "stem": "20. Nathan used a ______ to teach David a lesson and rebuke his sinful deeds.",
        "options": {"A": "song", "B": "story", "C": "dream", "D": "Parable"},
        "answer": "D",
    },
    {
        "stem": "21. Who did God give the priesthood after the death of Eli and his sons?",
        "options": {"A": "Samuel", "B": "Phinehas' wife", "C": "Ichabod", "D": "the women at tent"},
        "answer": "A",
    },
    {
        "stem": "22. The name Ichabod means ______________.",
        "options": {
            "A": "The glory has departed from Israel for the ark of God has been captured",
            "B": "The glory has been revealed to the Philistines",
            "C": "God has made me laugh at last",
            "D": "Glory to God in the highest",
        },
        "answer": "A",
    },
    {
        "stem": "23. Eli was _______ years old when he died.",
        "options": {"A": "70", "B": "90", "C": "98", "D": "100"},
        "answer": "C",
    },
    {
        "stem": "24. Who was the nephew of Abraham that accompanied him to the unknown land?",
        "options": {"A": "Samuel", "B": "Nahor", "C": "Lot", "D": "Hagar"},
        "answer": "C",
    },
    {
        "stem": "25. Sackcloth is a symbol of ________.",
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
        "stem": "32. John the Baptist warned the people that every tree that does not bear good fruit will be __________.",
        "options": {
            "A": "praised by God",
            "B": "cut down and thrown into hell",
            "C": "watered and killed",
            "D": "decorated by God",
        },
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
        "stem": "36. \"To your descendants, I will give this land\". God said this statement to _________.",
        "options": {"A": "Abraham", "B": "Nahor", "C": "Lot", "D": "Terah"},
        "answer": "A",
    },
    {
        "stem": "37. Where did God appear to show Abraham the promised land _________?",
        "options": {"A": "Shechem", "B": "at the oak of Moreh", "C": "Joppa", "D": "Tarshish"},
        "answer": "B",
    },
    {
        "stem": "38. Abraham was ________ years old when he left his father's land.",
        "options": {"A": "ninety-nine", "B": "seventy-five", "C": "hundred", "D": "seventeen"},
        "answer": "B",
    },
    {
        "stem": "39. Abraham's father's land is known as ___________.",
        "options": {"A": "Canaan", "B": "Haran", "C": "Shechem", "D": "Oak of Moreh"},
        "answer": "B",
    },
    {
        "stem": "40. God promised to make Abraham's name __________.",
        "options": {"A": "great", "B": "famous", "C": "popular", "D": "Awesome"},
        "answer": "A",
    },
]

THEORY = [
    "1a. What is repentance?\n1b. Describe how King David repented from his sins.\n1c. State three consequences of lack of repentance.",
    "2a. Narrate how Zacchaeus encountered Jesus.\n2b. State three lessons Christians can learn from the story.",
    "3a. What is obedience?\n3b. Describe how Abraham obeyed the call of God.",
    "4a. Describe the repentance of the people of Nineveh.\n4b. State two lessons from the story.",
    "5a. Who was John the Baptist?\n5b. Identify four groups of people that came to John the Baptist for repentance and the advice he gave to each one.",
    "6a. How did the sons of Eli sin against God?\n6b. State four ways God punished the household of Eli for lack of repentance.\n6c. State three lessons Christians can learn from the story.",
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
    exam.description = "SECOND TERM EXAMINATION CLASS: JSS1 SUBJECT: CRS"
    exam.save(update_fields=["title", "schedule_start", "schedule_end", "description", "updated_at"])

    blueprint = exam.blueprint
    blueprint.duration_minutes = 50
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS1-CRS-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": 40,
        "theory_count": 6,
        "objective_target_max": "20.00",
        "theory_target_max": "40.00",
    }
    blueprint.save(update_fields=["duration_minutes", "instructions", "section_config", "updated_at"])

    for idx, payload in enumerate(OBJECTIVES, start=1):
        row = rows[idx - 1]
        question = row.question
        question.stem = payload["stem"]
        question.marks = Decimal("1.00")
        question.save(update_fields=["stem", "marks", "updated_at"])

        options = list(question.options.order_by("sort_order"))
        if len(options) != 4:
            raise RuntimeError(f"Question {idx} expected 4 options, found {len(options)}")
        for sort_order, label in enumerate(["A", "B", "C", "D"], start=1):
            option = options[sort_order - 1]
            option.label = label
            option.option_text = payload["options"][label]
            option.sort_order = sort_order
            option.save(update_fields=["label", "option_text", "sort_order", "updated_at"])
        correct = CorrectAnswer.objects.get(question=question)
        correct.correct_options.set(question.options.filter(label=payload["answer"]))
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
