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


TITLE = "WED 7:45-9:00 SS2 Christian Religious Studies Second Term Exam"
DESCRIPTION = "CHRISTIAN RELIGIOUS STUDIES CLASS: SS2"
BANK_NAME = "SS2 Christian Religious Studies Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions only. "
    "Timer is 55 minutes. Exam window closes at 9:00 AM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {
        "stem": "The mother of Moses hid him for three months mainly because ______.",
        "options": {
            "A": "she feared the Egyptians",
            "B": "the king ordered all male children to be killed",
            "C": "Moses was sickly",
            "D": "she wanted him to grow stronger",
        },
        "answer": "B",
    },
    {
        "stem": "Joseph became ruler in Egypt because he ______.",
        "options": {
            "A": "was the eldest son of Jacob",
            "B": "interpreted Pharaoh's dreams correctly",
            "C": "was loved by the Egyptians",
            "D": "fought in Pharaoh's army",
        },
        "answer": "B",
    },
    {
        "stem": "Deborah was known in Israel as a ______.",
        "options": {"A": "queen", "B": "priestess", "C": "prophetess and judge", "D": "military commander"},
        "answer": "C",
    },
    {
        "stem": "Joshua succeeded Moses mainly because he ______.",
        "options": {"A": "was Moses' son", "B": "had military experience", "C": "was chosen by God", "D": "requested for leadership"},
        "answer": "C",
    },
    {
        "stem": "One way God provided for the Israelites in the wilderness was by giving them ______.",
        "options": {"A": "bread and fish", "B": "manna and quails", "C": "fruits and vegetables", "D": "honey and milk"},
        "answer": "B",
    },
    {
        "stem": "Eli failed in his parental responsibility because he ______.",
        "options": {"A": "hated his children", "B": "did not train them at all", "C": "failed to restrain his sons", "D": "sent them away from home"},
        "answer": "C",
    },
    {
        "stem": "Samuel demonstrated good leadership by ______.",
        "options": {"A": "appointing his sons judges", "B": "obeying God's instructions", "C": "collecting bribes", "D": "pleasing the elders"},
        "answer": "B",
    },
    {
        "stem": "Solomon showed wisdom when he asked God for ______.",
        "options": {"A": "riches", "B": "long life", "C": "wisdom to rule", "D": "victory in war"},
        "answer": "C",
    },
    {
        "stem": "One unwise decision of Solomon was that he ______.",
        "options": {"A": "built the temple", "B": "judged wisely between two women", "C": "married foreign wives", "D": "asked for wisdom"},
        "answer": "C",
    },
    {
        "stem": "Moses was saved from death as a baby through the help of ______.",
        "options": {"A": "Miriam", "B": "Pharaoh's daughter", "C": "Aaron", "D": "the midwives"},
        "answer": "B",
    },
    {
        "stem": "Joseph demonstrated leadership by ______.",
        "options": {"A": "revenging on his brothers", "B": "imprisoning his family", "C": "forgiving his brothers", "D": "sending them away"},
        "answer": "C",
    },
    {
        "stem": "Deborah encouraged Barak to fight against ______.",
        "options": {"A": "the Philistines", "B": "the Amalekites", "C": "Sisera", "D": "the Egyptians"},
        "answer": "C",
    },
    {
        "stem": "Joshua led the Israelites into the Promised Land after crossing ______.",
        "options": {"A": "the Red Sea", "B": "the River Jordan", "C": "the Nile", "D": "the Euphrates"},
        "answer": "B",
    },
    {
        "stem": "God protected the Israelites in the wilderness by ______.",
        "options": {"A": "building cities for them", "B": "sending angels to fight", "C": "guiding them with fire and cloud", "D": "giving them weapons"},
        "answer": "C",
    },
    {
        "stem": "The sons of Eli sinned mainly by ______.",
        "options": {"A": "refusing to pray", "B": "stealing temple offerings", "C": "neglecting sacrifices", "D": "abandoning worship"},
        "answer": "B",
    },
    {
        "stem": "Samuel anointed Saul as king following the instruction of ______.",
        "options": {"A": "the elders", "B": "the people", "C": "God", "D": "Eli"},
        "answer": "C",
    },
    {
        "stem": "Solomon's wisdom was first tested when he ______.",
        "options": {"A": "built the temple", "B": "married Pharaoh's daughter", "C": "judged a difficult case", "D": "became king"},
        "answer": "C",
    },
    {
        "stem": "Solomon displeased God because he ______.",
        "options": {"A": "built many houses", "B": "married many wives", "C": "worshipped foreign gods", "D": "ruled for many years"},
        "answer": "C",
    },
    {
        "stem": "The basket Moses was placed in was put among ______.",
        "options": {"A": "rocks", "B": "reeds", "C": "trees", "D": "flowers"},
        "answer": "B",
    },
    {
        "stem": "Joseph recognized that God sent him to Egypt in order to ______.",
        "options": {"A": "punish his brothers", "B": "become rich", "C": "save many lives", "D": "please Pharaoh"},
        "answer": "C",
    },
    {
        "stem": "Deborah judged Israel under ______.",
        "options": {"A": "a mountain", "B": "the temple", "C": "a palm tree", "D": "the city gate"},
        "answer": "C",
    },
    {
        "stem": "Joshua renewed the covenant with the Israelites at ______.",
        "options": {"A": "Bethel", "B": "Gilgal", "C": "Shechem", "D": "Jericho"},
        "answer": "C",
    },
    {
        "stem": "The Israelites complained in the wilderness mainly because of ______.",
        "options": {"A": "hunger and thirst", "B": "wild animals", "C": "enemies", "D": "sickness"},
        "answer": "A",
    },
    {
        "stem": "\"Stand firm and see the salvation of God.\" What complaint prompted this statement made by Moses?",
        "options": {"A": "The approaching of the Egyptians", "B": "lack of water", "C": "heat in the wilderness", "D": "lack of food"},
        "answer": "A",
    },
    {
        "stem": "Samuel was called by God while he was serving under ______.",
        "options": {"A": "Saul", "B": "David", "C": "Eli", "D": "Moses"},
        "answer": "C",
    },
    {
        "stem": "Solomon's request pleased God because it showed ______.",
        "options": {"A": "ambition", "B": "humility", "C": "greed", "D": "pride"},
        "answer": "B",
    },
    {
        "stem": "Solomon's kingdom later divided because ______.",
        "options": {"A": "of war", "B": "of heavy taxation", "C": "God was angry with Solomon", "D": "of foreign invasion"},
        "answer": "C",
    },
    {
        "stem": "Moses' parents showed faith by ______.",
        "options": {"A": "fleeing Egypt", "B": "hiding Moses", "C": "naming him", "D": "training him"},
        "answer": "B",
    },
    {
        "stem": "Joseph's leadership qualities included ______.",
        "options": {"A": "pride and anger", "B": "wisdom and forgiveness", "C": "fear and hatred", "D": "stubbornness"},
        "answer": "B",
    },
    {
        "stem": "Deborah's leadership showed that ______.",
        "options": {"A": "only men can lead", "B": "women cannot lead", "C": "God can use women", "D": "leadership is inherited"},
        "answer": "C",
    },
    {
        "stem": "Joshua encouraged the people to ______.",
        "options": {"A": "worship idols", "B": "obey God", "C": "fight Egypt", "D": "return to Egypt"},
        "answer": "B",
    },
    {
        "stem": "God provided water for the Israelites from ______.",
        "options": {"A": "the river", "B": "the sea", "C": "a rock", "D": "a well"},
        "answer": "C",
    },
    {
        "stem": "Eli's sons were priests who ______.",
        "options": {"A": "feared God", "B": "respected worship", "C": "abused their office", "D": "obeyed their father"},
        "answer": "C",
    },
    {
        "stem": "Samuel was respected because he ______.",
        "options": {"A": "was rich", "B": "was fearless", "C": "was obedient to God", "D": "pleased kings"},
        "answer": "C",
    },
    {
        "stem": "One result of Solomon's unwise decisions was ______.",
        "options": {"A": "peace in Israel", "B": "increase in wisdom", "C": "decline in wealth", "D": "loss of God's favour"},
        "answer": "D",
    },
    {
        "stem": "Moses was raised in the palace of ______.",
        "options": {"A": "Pharaoh", "B": "Joseph", "C": "Potiphar", "D": "Herod"},
        "answer": "A",
    },
    {
        "stem": "Joseph stored food during the years of plenty to ______.",
        "options": {"A": "sell to foreigners", "B": "enrich Egypt", "C": "prepare for famine", "D": "impress Pharaoh"},
        "answer": "C",
    },
    {
        "stem": "Deborah's song was sung to praise ______.",
        "options": {"A": "Barak", "B": "the army", "C": "God", "D": "Israel"},
        "answer": "C",
    },
    {
        "stem": "Joshua is remembered for saying, \"As for me and my household, we will serve ______.\"",
        "options": {"A": "Israel", "B": "Moses", "C": "God", "D": "the law"},
        "answer": "C",
    },
    {
        "stem": "The major lesson from Solomon's unwise decisions is that ______.",
        "options": {"A": "wisdom brings wealth", "B": "obedience is optional", "C": "disobedience leads to punishment", "D": "leadership is permanent"},
        "answer": "C",
    },
]

THEORY = [
    {
        "stem": (
            "1. (a) Narrate how God protected and provided for the Israelites in the wilderness.\n"
            "(b) Explain five ways church leaders can care for their members."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. (a) Explain the circumstances that led to the removal of the priesthood from Eli's lineage.\n"
            "(b) List five effects of children's disobedience on the family."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "3. (a) Describe the circumstances that led to Shadrach, Meshach and Abednego being thrown into the fiery furnace.\n"
            "(b) List three lessons Christians can learn from the story."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "4. (a) Narrate Saul's disobedience.\n"
            "(b) List five lessons leaders should learn from Saul's downfall."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. (a) Narrate the circumstances that led Moses to Pharaoh's palace.\n"
            "(b) List five qualities that made Moses a good leader."
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
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
            source_reference=f"SS2-CRS-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS2-CRS-20260325-TH-{index:02d}",
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
        "paper_code": "SS2-CRS-EXAM",
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
