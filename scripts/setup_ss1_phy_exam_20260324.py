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


TITLE = "TUE 8:30-9:30 SS1 Physics Second Term Exam"
DESCRIPTION = "SS1 PHYSICS EXAMINATION, 2026"
BANK_NAME = "SS1 Physics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer four questions only. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Heat is a form of ______.", "options": {"A": "light", "B": "energy", "C": "wave", "D": "temperature"}, "answer": "B"},
    {"stem": "The SI unit of heat is the ______.", "options": {"A": "ampere", "B": "joule", "C": "candela", "D": "watt"}, "answer": "B"},
    {"stem": "The quantity of heat required to raise the temperature of 1 kg of a substance by 1 degree C is called ______.", "options": {"A": "latent heat", "B": "heat capacity", "C": "specific heat capacity", "D": "thermal conductivity"}, "answer": "C"},
    {"stem": "The tendency of a solid to expand when heated is known as ______.", "options": {"A": "thermal resistivity", "B": "thermal expansivity", "C": "specific expansion", "D": "heat transfer"}, "answer": "B"},
    {"stem": "Which of the following expands most when heated?", "options": {"A": "solids", "B": "liquids", "C": "gases", "D": "metals"}, "answer": "C"},
    {"stem": "Linear expansivity is measured in ______.", "options": {"A": "degree C", "B": "m", "C": "/degree C", "D": "J/kg degree C"}, "answer": "C"},
    {"stem": "The transfer of heat through solids is called ______.", "options": {"A": "convection", "B": "conduction", "C": "radiation", "D": "oscillation"}, "answer": "B"},
    {"stem": "Heat transfer without a medium is ______.", "options": {"A": "conduction", "B": "convection", "C": "radiation", "D": "evaporation"}, "answer": "C"},
    {"stem": "Convection occurs only in ______.", "options": {"A": "solids", "B": "liquids", "C": "liquids and gases", "D": "gases only"}, "answer": "C"},
    {"stem": "Radiation from the sun reaches the earth through ______.", "options": {"A": "liquids", "B": "solids", "C": "vacuum", "D": "conduction"}, "answer": "C"},
    {"stem": "A body that has gained or lost electrons is said to be ______.", "options": {"A": "charged", "B": "neutral", "C": "grounded", "D": "magnetic"}, "answer": "A"},
    {"stem": "The type of charge carried by an electron is ______.", "options": {"A": "positive", "B": "negative", "C": "neutral", "D": "varying"}, "answer": "B"},
    {"stem": "Like charges ______.", "options": {"A": "attract", "B": "repel", "C": "combine", "D": "disappear"}, "answer": "B"},
    {"stem": "The region where electric force acts on a charge is called ______.", "options": {"A": "electric potential", "B": "electric field", "C": "magnetic field", "D": "charge zone"}, "answer": "B"},
    {"stem": "Electric field lines move from ______.", "options": {"A": "negative to positive", "B": "positive to negative", "C": "neutral to negative", "D": "north to south"}, "answer": "B"},
    {"stem": "A crystal is a solid whose particles are arranged in a ______.", "options": {"A": "random form", "B": "parallel line", "C": "definite geometric pattern", "D": "circular form"}, "answer": "C"},
    {"stem": "Which of the following is NOT a crystal type?", "options": {"A": "cubic", "B": "tetragonal", "C": "hexagonal", "D": "spherical"}, "answer": "D"},
    {"stem": "Which state of matter has particles closely packed together?", "options": {"A": "solid", "B": "liquid", "C": "gas", "D": "plasma"}, "answer": "A"},
    {"stem": "The random motion of tiny particles suspended in a fluid is known as ______.", "options": {"A": "expansion", "B": "sublimation", "C": "Brownian motion", "D": "conduction"}, "answer": "C"},
    {"stem": "The kinetic theory explains the behaviour of ______.", "options": {"A": "only solids", "B": "only liquids", "C": "only gases", "D": "matter in all states"}, "answer": "D"},
    {"stem": "The amount of heat required to change a solid to liquid without change in temperature is called ______.", "options": {"A": "convection", "B": "specific heat", "C": "latent heat of fusion", "D": "radiation"}, "answer": "C"},
    {"stem": "The ability of a material to conduct heat is called ______.", "options": {"A": "thermal capacity", "B": "conductivity", "C": "radiativity", "D": "expansivity"}, "answer": "B"},
    {"stem": "A body that allows heat to pass through easily is called a ______.", "options": {"A": "conductor", "B": "radiator", "C": "insulator", "D": "reflector"}, "answer": "A"},
    {"stem": "Metals are good conductors because they contain ______.", "options": {"A": "protons", "B": "neutrons", "C": "free electrons", "D": "ions"}, "answer": "C"},
    {"stem": "A charged rod can attract small pieces of paper due to ______.", "options": {"A": "magnetism", "B": "electrification", "C": "induction", "D": "convection"}, "answer": "C"},
    {"stem": "Electric field intensity is measured in ______.", "options": {"A": "N/C", "B": "C/N", "C": "J/C", "D": "C/J"}, "answer": "A"},
    {"stem": "Which of the following is used to detect charge?", "options": {"A": "voltmeter", "B": "ammeter", "C": "electroscope", "D": "galvanometer"}, "answer": "C"},
    {"stem": "The force between two-point charges varies directly with the product of the charges and inversely with the ______.", "options": {"A": "distance", "B": "square of distance", "C": "sum of distance", "D": "cube of distance"}, "answer": "B"},
    {"stem": "Solids expand when heated because particles ______.", "options": {"A": "come closer", "B": "move faster", "C": "slow down", "D": "remain fixed"}, "answer": "B"},
    {"stem": "Heat energy can be transferred by radiation through ______.", "options": {"A": "vacuum", "B": "only solids", "C": "only liquids", "D": "only gases"}, "answer": "A"},
    {"stem": "When a metal rod is heated at one end, heat moves by ______.", "options": {"A": "convection", "B": "conduction", "C": "radiation", "D": "expansion"}, "answer": "B"},
    {"stem": "Which device works mainly by the principle of thermal expansion?", "options": {"A": "thermometer", "B": "ammeter", "C": "voltmeter", "D": "fuse"}, "answer": "A"},
    {"stem": "In crystals, the smallest repeating unit is called ______.", "options": {"A": "cell", "B": "unit cell", "C": "atom", "D": "lattice"}, "answer": "B"},
    {"stem": "The energy possessed by particles due to motion is ______.", "options": {"A": "potential", "B": "kinetic", "C": "latent", "D": "thermal"}, "answer": "B"},
    {"stem": "Fields that require contact to act are called ______.", "options": {"A": "contact fields", "B": "non-contact fields", "C": "gravitational fields", "D": "repulsive fields"}, "answer": "A"},
    {"stem": "The field produced by electric charges in motion is called ______.", "options": {"A": "gravitational field", "B": "electric field", "C": "magnetic field", "D": "neutral field"}, "answer": "C"},
    {"stem": "The point where the field intensity is strongest is where the lines are ______.", "options": {"A": "sparse", "B": "curved", "C": "close together", "D": "straight"}, "answer": "C"},
    {"stem": "Thermal expansion can cause ______.", "options": {"A": "earthquake", "B": "cracks in railway lines", "C": "rainfall", "D": "landslides"}, "answer": "B"},
    {"stem": "The property of matter that causes resistance to change in temperature is ______.", "options": {"A": "latent heat", "B": "heat capacity", "C": "conduction", "D": "expansion"}, "answer": "B"},
    {"stem": "Ice floats on water because it is ______.", "options": {"A": "heavier", "B": "denser", "C": "lighter", "D": "warmer"}, "answer": "C"},
]

THEORY = [
    {"stem": "(a) Define heat energy.\n(b) List and explain three methods of heat transfer.\n(c) A metal block of mass 2 kg is heated from 25 degrees C to 75 degrees C. If its specific heat capacity is 500 J/kg degree C, calculate the heat gained.", "marks": Decimal("10.00")},
    {"stem": "(a) Define thermal expansivity.\n(b) Explain two practical applications of thermal expansion.\n(c) A metal rod of length 80 cm expands to 80.12 cm when heated through 60 degrees C. Calculate its linear expansivity.", "marks": Decimal("10.00")},
    {"stem": "(a) What is an electric charge?\n(b) Explain charging by induction.\n(c) Two charges +4 C and +2 C are placed 3 m apart. Calculate the electrostatic force between them. (k = 9 x 10^9 Nm^2/C^2)", "marks": Decimal("10.00")},
    {"stem": "(a) Define electric field.\n(b) State two properties of electric field lines.\n(c) Calculate the electric field intensity at a point 2 m from a 6 C charge. (k = 9 x 10^9 Nm^2/C^2)", "marks": Decimal("10.00")},
    {"stem": "(a) State the kinetic theory of matter.\n(b) Explain Brownian motion.\n(c) List three differences between solids and gases.", "marks": Decimal("10.00")},
    {"stem": "(a) What is a crystal?\n(b) Give three examples of crystal structures.\n(c) State three characteristics of crystalline solids.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="PHY")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="okeh@ndgakuje.org",
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
            source_reference=f"SS1-PHY-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS1-PHY-20260324-TH-{index:02d}",
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
        "paper_code": "SS1-PHY-EXAM",
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
