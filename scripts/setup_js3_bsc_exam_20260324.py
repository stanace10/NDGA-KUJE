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


TITLE = "TUE 8:30-9:30 JS3 Basic Science Second Term Exam"
DESCRIPTION = "BASIC SCIENCE JSS3 SECOND TERM EXAMINATION"
BANK_NAME = "JS3 Basic Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Resources obtained from plants and animals are called ______.", "options": {"A": "Non-living resources", "B": "Mineral resources", "C": "Living resources", "D": "Artificial resources"}, "answer": "C"},
    {"stem": "Which of the following is NOT a living resource?", "options": {"A": "Fish", "B": "Timber", "C": "Crude oil", "D": "Cattle"}, "answer": "C"},
    {"stem": "An example of non-living resource is ______.", "options": {"A": "Goat", "B": "Cotton", "C": "Coal", "D": "Maize"}, "answer": "C"},
    {"stem": "Which of these comes from animals?", "options": {"A": "Rubber", "B": "Wool", "C": "Paper", "D": "Palm oil"}, "answer": "B"},
    {"stem": "Crude oil is classified as ______.", "options": {"A": "Living resource", "B": "Renewable resource", "C": "Non-living resource", "D": "Agricultural product"}, "answer": "C"},
    {"stem": "One importance of natural resources is that they ______.", "options": {"A": "Cause pollution", "B": "Produce diseases", "C": "Provide raw materials", "D": "Destroy land"}, "answer": "C"},
    {"stem": "Which is obtained from trees?", "options": {"A": "Steel", "B": "Plastic", "C": "Timber", "D": "Cement"}, "answer": "C"},
    {"stem": "Which resource is renewable?", "options": {"A": "Coal", "B": "Natural gas", "C": "Fish", "D": "Iron ore"}, "answer": "C"},
    {"stem": "The nervous system controls the body through ______.", "options": {"A": "Blood", "B": "Bones", "C": "Nerves", "D": "Muscles"}, "answer": "C"},
    {"stem": "The main control centre of the body is the ______.", "options": {"A": "Heart", "B": "Brain", "C": "Kidney", "D": "Liver"}, "answer": "B"},
    {"stem": "The spinal cord is found inside the ______.", "options": {"A": "Skull", "B": "Rib cage", "C": "Vertebral column", "D": "Pelvis"}, "answer": "C"},
    {"stem": "Which part coordinates body activities?", "options": {"A": "Brain", "B": "Stomach", "C": "Lung", "D": "Kidney"}, "answer": "A"},
    {"stem": "A nerve that carries messages from sense organs to the brain is called ______.", "options": {"A": "Motor nerve", "B": "Sensory nerve", "C": "Mixed nerve", "D": "Spinal nerve"}, "answer": "B"},
    {"stem": "Motor nerves carry impulses from ______.", "options": {"A": "Brain to muscles", "B": "Eyes to brain", "C": "Skin to brain", "D": "Ear to brain"}, "answer": "A"},
    {"stem": "Which of these is NOT part of the nervous system?", "options": {"A": "Brain", "B": "Nerves", "C": "Spinal cord", "D": "Heart"}, "answer": "D"},
    {"stem": "The smallest unit of the nervous system is ______.", "options": {"A": "Cell", "B": "Neuron", "C": "Tissue", "D": "Fibre"}, "answer": "B"},
    {"stem": "The organ for sight is the ______.", "options": {"A": "Ear", "B": "Nose", "C": "Eye", "D": "Tongue"}, "answer": "C"},
    {"stem": "Taste is detected by the ______.", "options": {"A": "Nose", "B": "Skin", "C": "Eye", "D": "Tongue"}, "answer": "D"},
    {"stem": "Hearing is done by the ______.", "options": {"A": "Nose", "B": "Ear", "C": "Tongue", "D": "Eye"}, "answer": "B"},
    {"stem": "The sense organ for smelling is the ______.", "options": {"A": "Skin", "B": "Nose", "C": "Ear", "D": "Tongue"}, "answer": "B"},
    {"stem": "Touch is sensed by the ______.", "options": {"A": "Skin", "B": "Eye", "C": "Ear", "D": "Nose"}, "answer": "A"},
    {"stem": "The main function of sense organs is to ______.", "options": {"A": "Digest food", "B": "Protect the body", "C": "Detect stimuli", "D": "Produce hormones"}, "answer": "C"},
    {"stem": "Coordination means ______.", "options": {"A": "Movement of blood", "B": "Working together of body parts", "C": "Digestion of food", "D": "Growth of bones"}, "answer": "B"},
    {"stem": "Hormones are produced by ______.", "options": {"A": "Muscles", "B": "Glands", "C": "Bones", "D": "Blood"}, "answer": "B"},
    {"stem": "The endocrine system controls activities using ______.", "options": {"A": "Nerves", "B": "Bones", "C": "Hormones", "D": "Muscles"}, "answer": "C"},
    {"stem": "Which gland controls growth?", "options": {"A": "Thyroid", "B": "Pituitary", "C": "Adrenal", "D": "Pancreas"}, "answer": "B"},
    {"stem": "Insulin is produced by the ______.", "options": {"A": "Kidney", "B": "Pancreas", "C": "Liver", "D": "Heart"}, "answer": "B"},
    {"stem": "The nervous system gives ______.", "options": {"A": "Slow response", "B": "Permanent effect", "C": "Quick response", "D": "Chemical control"}, "answer": "C"},
    {"stem": "Crushing of minerals is called ______.", "options": {"A": "Sorting", "B": "Grinding", "C": "Smelting", "D": "Washing"}, "answer": "B"},
    {"stem": "Heating ore to extract metal is ______.", "options": {"A": "Refining", "B": "Smelting", "C": "Mining", "D": "Screening"}, "answer": "B"},
    {"stem": "Iron is obtained from ______.", "options": {"A": "Limestone", "B": "Bauxite", "C": "Iron ore", "D": "Quartz"}, "answer": "C"},
    {"stem": "Petroleum is refined in a ______.", "options": {"A": "Factory", "B": "Furnace", "C": "Refinery", "D": "Mine"}, "answer": "C"},
    {"stem": "Which is a processed mineral product?", "options": {"A": "Crude oil", "B": "Gold ore", "C": "Petrol", "D": "Iron stone"}, "answer": "C"},
    {"stem": "One use of mineral resources is ______.", "options": {"A": "Decoration", "B": "Building roads", "C": "Polluting rivers", "D": "Destroying land"}, "answer": "B"},
    {"stem": "Diseases caused by germs are called ______.", "options": {"A": "Hereditary", "B": "Deficiency", "C": "Communicable", "D": "Mental"}, "answer": "C"},
    {"stem": "Malaria is transmitted by ______.", "options": {"A": "Housefly", "B": "Mosquito", "C": "Rat", "D": "Lizard"}, "answer": "B"},
    {"stem": "Cholera is caused by ______.", "options": {"A": "Virus", "B": "Fungus", "C": "Bacteria", "D": "Worm"}, "answer": "C"},
    {"stem": "Which is a non-communicable disease?", "options": {"A": "Tuberculosis", "B": "Measles", "C": "Hypertension", "D": "Cholera"}, "answer": "C"},
    {"stem": "One way of preventing diseases is ______.", "options": {"A": "Dirty environment", "B": "Poor feeding", "C": "Immunization", "D": "Sharing needles"}, "answer": "C"},
    {"stem": "HIV is spread through ______.", "options": {"A": "Handshake", "B": "Sharing food", "C": "Blood contact", "D": "Air"}, "answer": "C"},
    {"stem": "Drug abuse means ______.", "options": {"A": "Correct use of drugs", "B": "Misuse of drugs", "C": "Selling drugs", "D": "Buying drugs"}, "answer": "B"},
    {"stem": "Which of these is a hard drug?", "options": {"A": "Coffee", "B": "Cocaine", "C": "Tea", "D": "Sugar"}, "answer": "B"},
    {"stem": "One effect of drug abuse is ______.", "options": {"A": "Good health", "B": "Improved memory", "C": "Mental disorder", "D": "Strength"}, "answer": "C"},
    {"stem": "Smoking affects the ______.", "options": {"A": "Brain", "B": "Heart", "C": "Lungs", "D": "Kidney"}, "answer": "C"},
    {"stem": "Drug abuse can lead to ______.", "options": {"A": "Success", "B": "Discipline", "C": "Crime", "D": "Happiness"}, "answer": "C"},
    {"stem": "Which is NOT a reason for drug abuse?", "options": {"A": "Peer pressure", "B": "Curiosity", "C": "Medical advice", "D": "Frustration"}, "answer": "C"},
    {"stem": "Biotechnology involves the use of ______.", "options": {"A": "Machines only", "B": "Living organisms", "C": "Metals", "D": "Rocks"}, "answer": "B"},
    {"stem": "Yoghurt production is an example of ______.", "options": {"A": "Mining", "B": "Fermentation", "C": "Smelting", "D": "Refining"}, "answer": "B"},
    {"stem": "Which organism is used in bread making?", "options": {"A": "Bacteria", "B": "Virus", "C": "Yeast", "D": "Algae"}, "answer": "C"},
    {"stem": "Tissue culture is used to ______.", "options": {"A": "Destroy crops", "B": "Multiply plants", "C": "Kill bacteria", "D": "Produce metals"}, "answer": "B"},
    {"stem": "One benefit of biotechnology is ______.", "options": {"A": "Pollution", "B": "Food production", "C": "Disease spread", "D": "Deforestation"}, "answer": "B"},
    {"stem": "Genetic engineering involves ______.", "options": {"A": "Mixing soil", "B": "Changing genes", "C": "Burning waste", "D": "Digging land"}, "answer": "B"},
    {"stem": "The control centre of hormones is the ______.", "options": {"A": "Heart", "B": "Brain", "C": "Pituitary gland", "D": "Kidney"}, "answer": "C"},
    {"stem": "Which sense organ detects heat?", "options": {"A": "Eye", "B": "Ear", "C": "Skin", "D": "Nose"}, "answer": "C"},
    {"stem": "The movement of impulses along nerves is called ______.", "options": {"A": "Respiration", "B": "Reflex action", "C": "Digestion", "D": "Excretion"}, "answer": "B"},
    {"stem": "A deficiency disease is caused by lack of ______.", "options": {"A": "Germs", "B": "Vitamins", "C": "Air", "D": "Water"}, "answer": "B"},
    {"stem": "Tobacco contains ______.", "options": {"A": "Alcohol", "B": "Nicotine", "C": "Sugar", "D": "Protein"}, "answer": "B"},
    {"stem": "One use of limestone is in ______.", "options": {"A": "Medicine", "B": "Cement making", "C": "Cooking", "D": "Farming"}, "answer": "B"},
    {"stem": "Which gland prepares the body for emergency?", "options": {"A": "Thyroid", "B": "Adrenal", "C": "Pancreas", "D": "Pituitary"}, "answer": "B"},
    {"stem": "Which is a renewable living resource?", "options": {"A": "Coal", "B": "Fish", "C": "Gold", "D": "Natural gas"}, "answer": "B"},
]

THEORY = [
    {"stem": "Resources from Living and Non-Living Things.\n(a) Define resources.\n(b) Describe living resources with examples.\n(c) Explain non-living resources with examples.", "marks": Decimal("10.00")},
    {"stem": "Nervous System and Its Functions.\n(a) Define nervous system.\n(b) Mention the parts of the nervous system.\n(c) State the functions of the nervous system.", "marks": Decimal("10.00")},
    {"stem": "Write short notes on the Sense Organs.\n(a) Definition.\n(b) State the five sense organs.\n(c) List the functions of the sense organs.", "marks": Decimal("10.00")},
    {"stem": "Biotechnology.\n(a) Define biotechnology.\n(b) State four uses of biotechnology.\n(c) Write short notes on the types of biotechnology.", "marks": Decimal("10.00")},
    {"stem": "Processing of Mineral Resources.\n(a) Definition of mineral processing.\n(b) Mention the steps involved in mineral processing.\n(c) State the importance of minerals to man.", "marks": Decimal("10.00")},
    {"stem": "Discuss Drug Abuse.\n(a) Definition of drug abuse.\n(b) Effects of drug abuse to humans.\n(c) State some prevention measures in curbing drug abuse.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="BSC")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="uwakwe@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 24, 8, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 9, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday first paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 8:30 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday first paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 8:30 AM WAT."
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
            source_reference=f"JS3-BSC-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS3-BSC-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 50
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS3-BSC-EXAM",
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
