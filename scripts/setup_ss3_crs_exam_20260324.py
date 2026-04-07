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


TITLE = "TUE 1:30-3:00 SS3 Christian Religious Studies Second Term Exam"
DESCRIPTION = "SUBJECT: CHRISTIAN RELIGIOUS STUDIES CLASS: SS3"
BANK_NAME = "SS3 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions only. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 60 minutes. Exam window closes at 3:00 PM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "According to the book of Matthew, John's response to Jesus' request for baptism indicates ______.", "options": {"A": "arrogance", "B": "wisdom", "C": "humility", "D": "fear"}, "answer": "C"},
    {"stem": "Which of the following in the life of Jesus formed the foundation of the Christian faith?", "options": {"A": "death", "B": "transfiguration", "C": "baptism", "D": "resurrection"}, "answer": "D"},
    {"stem": "Which of the synoptic gospels states that after Jesus was crucified, the earth shook and rocks were split?", "options": {"A": "Matthew", "B": "Mark", "C": "Luke", "D": "John"}, "answer": "A"},
    {"stem": "Herod's arrest of Peter after the execution of James was meant to ______.", "options": {"A": "establish Herod as a good and thoughtful king", "B": "show his hatred for the disciples of Christ", "C": "win favour and approval of the Jews", "D": "hinder the further spread of the gospel"}, "answer": "C"},
    {"stem": "Which of the following ways did God evaluate His work after creation?", "options": {"A": "very perfect", "B": "satisfactory", "C": "excellent", "D": "very good"}, "answer": "D"},
    {"stem": "Eli's failure to decisively discipline his children led to all the following except ______.", "options": {"A": "capture of the ark", "B": "collapse of his priestly lineage", "C": "institution of monarchy in Israel", "D": "humiliation of Israel by the Philistines"}, "answer": "C"},
    {"stem": "The rebuilding of the temple in Jerusalem became successful because of God's influence over king ______.", "options": {"A": "Josiah", "B": "Cyrus", "C": "Darius", "D": "Nebuchadnezzar"}, "answer": "C"},
    {"stem": "The greatest enemy of our soul according to Peter is ______.", "options": {"A": "the devil", "B": "partiality", "C": "desire of the flesh", "D": "idolatry"}, "answer": "A"},
    {"stem": "After the Mount Carmel contest, the four hundred and fifty prophets of Baal were killed by Elijah at ______.", "options": {"A": "Cherith", "B": "Kidron", "C": "Kishon", "D": "Horeb"}, "answer": "C"},
    {"stem": "The caravan of traders who bought Joseph carried items which included ______.", "options": {"A": "gum, balm and myrrh", "B": "gum, spices and gold", "C": "myrrh, gold and frankincense", "D": "frankincense, balm and gum"}, "answer": "A"},
    {"stem": "The men travelling with Saul to Damascus stood speechless because ______.", "options": {"A": "Saul suddenly fell off his horse", "B": "Saul lost his sight", "C": "they heard a voice without seeing the speaker", "D": "they saw how Saul's eyes were restored"}, "answer": "C"},
    {"stem": "Which of the following characterized the life of the early church?", "options": {"A": "selfishness", "B": "selflessness", "C": "class system", "D": "convention"}, "answer": "B"},
    {"stem": "The request made by the northern delegation to Rehoboam was meant to ______.", "options": {"A": "accept them as brothers", "B": "have their burden reduced", "C": "enable them to abdicate the throne", "D": "give the north independence"}, "answer": "B"},
    {"stem": "After the death of Ehud, God punished the Israelites for their sins using the ______.", "options": {"A": "Philistines", "B": "Midianites", "C": "Canaanites", "D": "Moabites"}, "answer": "C"},
    {"stem": "Immediately the Israelites heard the evil report of the majority of the spies they ______.", "options": {"A": "cried aloud and wept that night", "B": "chose a leader to take them back to Egypt", "C": "prayed to God for deliverance", "D": "decided they would go to Canaan"}, "answer": "A"},
    {"stem": "Which of the following action occurred before Joseph made himself known to his brothers in Egypt?", "options": {"A": "fed them", "B": "kissed them", "C": "prayed with them", "D": "wept aloud"}, "answer": "D"},
    {"stem": "To prevent Jesus from being arrested in Gethsemane, a disciple cut off the ear of the ______.", "options": {"A": "slave of the high priest", "B": "servant of the high priest", "C": "high priest's butler", "D": "chief priest's bodyguard"}, "answer": "A"},
    {"stem": "Which attribute of Joshua and Caleb distinguished them from the other spies?", "options": {"A": "the confidence they had in themselves", "B": "their knowledge of the land they spied", "C": "their preparedness to face challenge", "D": "the absolute trust they had in God"}, "answer": "D"},
    {"stem": "One lesson we can learn from the story of the merciful servant is that we should ______.", "options": {"A": "forgive our debtors seventy times", "B": "be patient with our debtors", "C": "ignore the plight of our debtors", "D": "take our debtors to the appropriate authority for sanctions"}, "answer": "B"},
    {"stem": "What was the reason for Ananias' reluctance to pray over Saul to regain his sight?", "options": {"A": "Saul had not yet repented of his deeds", "B": "Saul was not one of the disciples of Christ", "C": "he was aware of his persecution of Christians in Damascus", "D": "he was not sure Saul was converted already"}, "answer": "C"},
    {"stem": "One major lesson that can be derived from the priestly account is that the world ______.", "options": {"A": "is not a product of chance", "B": "is a by-product of evolution", "C": "came into being after a series of attempts", "D": "was created when man was formed"}, "answer": "A"},
    {"stem": "\"Can we find such a man as this in whom is the Spirit of God?\" Which of the following is not an action taken by Pharaoh after his request was granted?", "options": {"A": "Joseph was given a priest's daughter to marry", "B": "a signet ring was given to signify Joseph's authority", "C": "a new name was given to Joseph", "D": "Joseph regained his freedom and went back to Canaan"}, "answer": "D"},
    {"stem": "After Jesus broke bread with the men going to Emmaus, they were ______.", "options": {"A": "enlightened", "B": "wise", "C": "astonished", "D": "saddened"}, "answer": "A"},
    {"stem": "\"This book of the law shall not depart out of your mouth, but you shall meditate on it day and night...\" This instruction was given to ______.", "options": {"A": "Moses", "B": "Aaron", "C": "Joshua", "D": "Caleb"}, "answer": "C"},
    {"stem": "God carried out His punishment upon Eli's house through the ______.", "options": {"A": "Philistines", "B": "Amalekites", "C": "Ammonites", "D": "Babylonians"}, "answer": "A"},
    {"stem": "According to Matthew, which of the following took place first immediately Jesus died?", "options": {"A": "the temple curtain was torn", "B": "the earth shook", "C": "the tombs opened", "D": "the rocks split"}, "answer": "A"},
    {"stem": "The underlying reasons attributed to the Israelites' request for a king were the ______.", "options": {"A": "age of Samuel and the conduct of his sons", "B": "old age of Eli and the conduct of his sons", "C": "failure of both Samuel and Eli to correct their sons", "D": "need to fight other nations who had kings and be unique"}, "answer": "A"},
    {"stem": "The profession of Levi was ______.", "options": {"A": "fishing", "B": "shepherding", "C": "tax collecting", "D": "vine dressing"}, "answer": "C"},
    {"stem": "What was Jesus' response to the would-be disciple who wanted to bury his father?", "options": {"A": "Foxes have holes and birds have nests", "B": "He could go and give his father a befitting burial", "C": "Follow me and let your siblings bury him", "D": "Follow me and leave the dead to bury their dead"}, "answer": "D"},
    {"stem": "The river that flowed out of Eden divided into ______.", "options": {"A": "5", "B": "4", "C": "3", "D": "2"}, "answer": "B"},
    {"stem": "\"Is it you, you troubler of Israel?\" These words were said by king ______ to ______.", "options": {"A": "Saul to Samuel", "B": "Ahab to Elijah", "C": "Ahab to Elisha", "D": "David to Nathan"}, "answer": "B"},
    {"stem": "The taskmaster in charge of forced labour in Israel during the reign of Rehoboam was ______.", "options": {"A": "Hadad", "B": "Segub", "C": "Adoram", "D": "Absalom"}, "answer": "C"},
    {"stem": "James advised that Christians should sing praises when they are ______.", "options": {"A": "wealthy", "B": "happy", "C": "lonely", "D": "suffering"}, "answer": "B"},
    {"stem": "Which of the following took place during the trial of Jesus?", "options": {"A": "healing of the servant's ear", "B": "healing of the haemorrhage woman", "C": "the splitting of the temple curtain", "D": "reconciliation between Herod and Pilate"}, "answer": "D"},
    {"stem": "The election of Matthias to succeed Judas was ______.", "options": {"A": "a command from Peter", "B": "the fulfilment of the scriptures", "C": "an instruction from Jesus", "D": "a way of getting more disciples"}, "answer": "B"},
    {"stem": "Which of this statements was not made by Peter during the second trial of the apostles by the high priest?", "options": {"A": "We must always obey God rather than men", "B": "God raised Jesus up whom you killed by hanging on the cross", "C": "God exalted Jesus as a leader and saviour", "D": "We cannot but speak what we have seen and heard"}, "answer": "D"},
    {"stem": "Pure and undefiled religion, according to James, involves all these practices except ______.", "options": {"A": "visiting orphans in their suffering", "B": "going to church daily", "C": "visiting widows in their affliction", "D": "being unstained from the world"}, "answer": "B"},
    {"stem": "The prophecy concerning the denial of Jesus by Peter was fulfilled during the ______.", "options": {"A": "arrest of Jesus", "B": "trial of Jesus", "C": "agony at Gethsemane", "D": "transfiguration of Jesus"}, "answer": "B"},
    {"stem": "Man became a living being when God ______.", "options": {"A": "formed him from dust", "B": "gave him breath", "C": "spoke to him", "D": "gave him a helpmate"}, "answer": "B"},
    {"stem": "Joseph's brothers pastured their father's flock at ______.", "options": {"A": "Bethel", "B": "Shechem", "C": "Hebron", "D": "Peniel"}, "answer": "B"},
    {"stem": "Which of these virtues of Jesus is embedded in the Lord's prayer?", "options": {"A": "love", "B": "humility", "C": "peace", "D": "kindness"}, "answer": "B"},
    {"stem": "Which of these singular acts earned David a place after God's own heart?", "options": {"A": "the zeal he had to fight and kill Goliath", "B": "fasting seven days for the sick child", "C": "refusal to terminate his predecessor", "D": "playing the lyre to soothe Saul's insanity"}, "answer": "C"},
    {"stem": "Naaman's request to take home soil from Israel was because he thought Yahweh was ______.", "options": {"A": "limited to the land of Israel", "B": "only represented by the earth", "C": "familiar with Israel's earth", "D": "to become the God of Damascus"}, "answer": "A"},
    {"stem": "The divine voice \"Thou art my beloved Son\" at Jesus' baptism declared Jesus as the ______.", "options": {"A": "Son of God", "B": "Holy One of Israel", "C": "Anointed One of God", "D": "Son of David"}, "answer": "A"},
    {"stem": "Rehoboam's preference to be a dictator was influenced by ______.", "options": {"A": "his love for the youth", "B": "the counsel of his peers", "C": "the will and accord of God", "D": "the love for the kingdom"}, "answer": "B"},
    {"stem": "\"The Lord forbid that I should give you the inheritance of my fathers.\" What did Ahab do immediately when he heard this information?", "options": {"A": "called his wife to organize men to kill Naboth", "B": "invited Naboth to come and face the council of elders", "C": "organized that Naboth's property should be confiscated", "D": "went home in a sad mood to sleep without food"}, "answer": "D"},
    {"stem": "The first four disciples of Jesus were ______.", "options": {"A": "Simon, Andrew, Philip and James", "B": "Simon, James, Philip and Peter", "C": "Simon, Andrew, James and John", "D": "Andrew, Peter, John and Matthew"}, "answer": "C"},
    {"stem": "\"If you are the Son of God, command these stones to become loaves of bread.\" This text is common to the books of ______.", "options": {"A": "Mark and John", "B": "Luke and Mark", "C": "John and Matthew", "D": "Matthew and Luke"}, "answer": "D"},
    {"stem": "Which of the following was God's instruction to Adam after creation?", "options": {"A": "to eat of any of the trees except that of the knowledge of good and evil", "B": "to eat freely of every tree except the one with apples", "C": "to eat from the tree in the middle of the garden", "D": "to eat any animal and plant in Eden"}, "answer": "A"},
    {"stem": "Which of the following is not a sign of freedom according to Peter?", "options": {"A": "loving the brotherhood", "B": "using it as a pretext for evil", "C": "honouring all men", "D": "giving honour to the emperor"}, "answer": "B"},
]

THEORY = [
    {
        "stem": "1. (a) Give account of the outpouring of the Holy Spirit and its effect on the apostles.\n(b) Discuss Saul's opposition to the gospel.",
        "marks": Decimal("15.00"),
    },
    {
        "stem": "2. (a) Discuss how James addressed the subject of prayer.\n(b) Discuss the circumstances that led to the death of Eli's sons.",
        "marks": Decimal("15.00"),
    },
    {
        "stem": "3. (a) Narrate the circumstances that led to Moses' encounter with the priest of Midian.\n(b) Narrate the circumstances under which Peter was rescued from prison.",
        "marks": Decimal("15.00"),
    },
    {
        "stem": "4. (a) Narrate how the problem of discrimination was solved in the early church.\n(b) Narrate how Deborah stopped the oppression of the Jews.",
        "marks": Decimal("15.00"),
    },
    {
        "stem": "5. (a) Narrate the healing of Naaman.\n(b) Highlight James' teaching on impartiality.",
        "marks": Decimal("15.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
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
    schedule_start = datetime(2026, 3, 24, 13, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 15, 0, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 1:30 PM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 1:30 PM WAT."
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
            source_reference=f"SS3-CRS-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS3-CRS-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 60
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-CRS-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "40.00",
        "theory_target_max": "60.00",
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
            "schedule_start": exam.schedule_start.isoformat(),
            "schedule_end": exam.schedule_end.isoformat(),
            "duration_minutes": blueprint.duration_minutes,
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
        }
    )


main()
