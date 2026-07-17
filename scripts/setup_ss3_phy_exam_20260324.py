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


TITLE = "TUE 9:30-11:00 SS3 Physics Second Term Exam"
DESCRIPTION = "PHYSICS EXAMINATION SECOND TERM CLASS: SS3"
BANK_NAME = "SS3 Physics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any five questions. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 75 minutes. Exam window closes at 11:00 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "A particle moves with uniform acceleration. If its velocity changes from 12 m/s to 30 m/s in 6 s, the acceleration is ______.", "options": {"A": "2 m/s^2", "B": "3 m/s^2", "C": "4 m/s^2", "D": "5 m/s^2"}, "answer": "B"},
    {"stem": "A stone is projected vertically upward with velocity 20 m/s. The maximum height reached is ______. (g = 10 m/s^2)", "options": {"A": "10 m", "B": "15 m", "C": "20 m", "D": "25 m"}, "answer": "C"},
    {"stem": "A force of 25 N acts on a body of mass 5 kg initially at rest. The velocity after 4 s is ______.", "options": {"A": "10 m/s", "B": "15 m/s", "C": "20 m/s", "D": "25 m/s"}, "answer": "C"},
    {"stem": "A body of mass 2 kg moving with velocity 6 m/s collides with another body of mass 4 kg moving in the same direction with velocity 2 m/s. If they move together after collision, their common velocity is ______.", "options": {"A": "2.3 m/s", "B": "3.3 m/s", "C": "4.5 m/s", "D": "5.3 m/s"}, "answer": "B"},
    {"stem": "The moment of a force of 12 N acting at a perpendicular distance of 0.5 m from the pivot is ______.", "options": {"A": "3 Nm", "B": "4 Nm", "C": "6 Nm", "D": "8 Nm"}, "answer": "C"},
    {"stem": "A body of mass 500 g moving with velocity 8 m/s has momentum ______.", "options": {"A": "2 kgm/s", "B": "3 kgm/s", "C": "4 kgm/s", "D": "5 kgm/s"}, "answer": "C"},
    {"stem": "A machine lifts 500 N load through 2 m in 5 s. Power developed is ______.", "options": {"A": "200 W", "B": "300 W", "C": "400 W", "D": "500 W"}, "answer": "A"},
    {"stem": "A block slides down a plane inclined at 30 degrees to the horizontal. If the length of plane is 10 m, the vertical height is ______.", "options": {"A": "4 m", "B": "5 m", "C": "6 m", "D": "7 m"}, "answer": "B"},
    {"stem": "A body moving in a circle experiences ______.", "options": {"A": "constant velocity", "B": "constant speed", "C": "zero acceleration", "D": "decreasing velocity"}, "answer": "B"},
    {"stem": "Escape velocity from a planet depends on ______.", "options": {"A": "radius only", "B": "mass only", "C": "both mass and radius", "D": "atmospheric pressure"}, "answer": "C"},
    {"stem": "A metal of mass 0.2 kg is heated from 20 degrees C to 100 degrees C. Specific heat capacity = 900 J/kgK. Heat absorbed is ______.", "options": {"A": "7200 J", "B": "14400 J", "C": "18000 J", "D": "20000 J"}, "answer": "B"},
    {"stem": "If 200 g of ice melts at 0 degrees C, heat absorbed is ______. (L = 3.36 x 10^5 J/kg)", "options": {"A": "6.72 x 10^4 J", "B": "3.36 x 10^4 J", "C": "6.72 x 10^3 J", "D": "3.36 x 10^3 J"}, "answer": "A"},
    {"stem": "Boyle's law is valid when temperature is ______.", "options": {"A": "constant", "B": "increasing", "C": "decreasing", "D": "zero"}, "answer": "A"},
    {"stem": "A gas occupies 0.3 m^3 at 100 kPa. If pressure becomes 300 kPa, new volume is ______.", "options": {"A": "0.1 m^3", "B": "0.2 m^3", "C": "0.3 m^3", "D": "0.9 m^3"}, "answer": "A"},
    {"stem": "The SI unit of linear expansivity is ______.", "options": {"A": "Wm^-1K^-1", "B": "JK^-1", "C": "W/K", "D": "Jkg^-1"}, "answer": "B"},
    {"stem": "A wave has frequency 250 Hz and wavelength 0.8 m. Speed of the wave is ______.", "options": {"A": "200 m/s", "B": "150 m/s", "C": "300 m/s", "D": "350 m/s"}, "answer": "A"},
    {"stem": "The phenomenon responsible for the spreading of waves around obstacles is ______.", "options": {"A": "reflection", "B": "diffraction", "C": "refraction", "D": "polarization"}, "answer": "B"},
    {"stem": "The distance between two successive crests is called ______.", "options": {"A": "amplitude", "B": "wavelength", "C": "period", "D": "frequency"}, "answer": "B"},
    {"stem": "Sound waves are ______.", "options": {"A": "transverse waves", "B": "electromagnetic waves", "C": "longitudinal waves", "D": "stationary waves"}, "answer": "C"},
    {"stem": "Beats are produced when ______.", "options": {"A": "two waves have same frequency", "B": "frequencies differ slightly", "C": "waves cancel", "D": "resonance occurs"}, "answer": "B"},
    {"stem": "The refractive index of glass is 1.5. Critical angle is approximately ______.", "options": {"A": "42 degrees", "B": "50 degrees", "C": "60 degrees", "D": "70 degrees"}, "answer": "A"},
    {"stem": "An object 10 cm from a concave mirror forms image 20 cm away. Magnification is ______.", "options": {"A": "0.5", "B": "1", "C": "2", "D": "3"}, "answer": "C"},
    {"stem": "Optical fibres operate based on ______.", "options": {"A": "diffraction", "B": "refraction", "C": "total internal reflection", "D": "interference"}, "answer": "C"},
    {"stem": "Power of a lens of focal length 25 cm is ______.", "options": {"A": "2 D", "B": "3 D", "C": "4 D", "D": "5 D"}, "answer": "C"},
    {"stem": "A convex lens produces real image when object is ______.", "options": {"A": "within focal length", "B": "at focal length", "C": "beyond focal length", "D": "at infinity"}, "answer": "C"},
    {"stem": "Current through a 10 ohm resistor connected to 20 V battery is ______.", "options": {"A": "1 A", "B": "2 A", "C": "3 A", "D": "4 A"}, "answer": "B"},
    {"stem": "Electrical power consumed by a device drawing 5 A from 240 V supply is ______.", "options": {"A": "600 W", "B": "800 W", "C": "1000 W", "D": "1200 W"}, "answer": "D"},
    {"stem": "Equivalent resistance of 4 ohm and 6 ohm in series is ______.", "options": {"A": "2.4 ohm", "B": "5 ohm", "C": "10 ohm", "D": "24 ohm"}, "answer": "C"},
    {"stem": "Equivalent resistance of 4 ohm and 6 ohm in parallel is approximately ______.", "options": {"A": "2.4 ohm", "B": "5 ohm", "C": "10 ohm", "D": "24 ohm"}, "answer": "A"},
    {"stem": "The unit of electrical energy is ______.", "options": {"A": "watt", "B": "kilowatt-hour", "C": "volt", "D": "coulomb"}, "answer": "B"},
    {"stem": "Magnetic field around a straight conductor carrying current is ______.", "options": {"A": "radial", "B": "circular", "C": "straight", "D": "spiral"}, "answer": "B"},
    {"stem": "Fleming's left-hand rule is used to determine ______.", "options": {"A": "current direction", "B": "magnetic field", "C": "force on conductor", "D": "voltage"}, "answer": "C"},
    {"stem": "Photoelectric effect supports ______.", "options": {"A": "wave theory", "B": "particle nature of light", "C": "classical mechanics", "D": "gravitational theory"}, "answer": "B"},
    {"stem": "The binding force inside nucleus is ______.", "options": {"A": "gravitational", "B": "electrostatic", "C": "nuclear force", "D": "magnetic force"}, "answer": "C"},
    {"stem": "Alpha particle has charge ______.", "options": {"A": "+1e", "B": "+2e", "C": "-1e", "D": "0"}, "answer": "B"},
    {"stem": "Density of a substance of mass 600 g and volume 200 cm^3 is ______.", "options": {"A": "2 g/cm^3", "B": "3 g/cm^3", "C": "4 g/cm^3", "D": "5 g/cm^3"}, "answer": "B"},
    {"stem": "Pressure exerted by 200 N force on area 0.5 m^2 is ______.", "options": {"A": "100 Pa", "B": "200 Pa", "C": "300 Pa", "D": "400 Pa"}, "answer": "D"},
    {"stem": "Kinetic energy of a 4 kg body moving at 5 m/s is ______.", "options": {"A": "25 J", "B": "50 J", "C": "75 J", "D": "100 J"}, "answer": "B"},
    {"stem": "A wave of frequency 400 Hz has period ______.", "options": {"A": "0.0025 s", "B": "0.004 s", "C": "0.005 s", "D": "0.025 s"}, "answer": "A"},
    {"stem": "Electric charge Q = It. Charge passing in 5 s when current = 2 A is ______.", "options": {"A": "5 C", "B": "10 C", "C": "15 C", "D": "20 C"}, "answer": "B"},
    {"stem": "The unit of force is ______.", "options": {"A": "joule", "B": "newton", "C": "watt", "D": "pascal"}, "answer": "B"},
    {"stem": "Acceleration due to gravity on Earth is approximately ______.", "options": {"A": "5 m/s^2", "B": "9.8 m/s^2", "C": "15 m/s^2", "D": "20 m/s^2"}, "answer": "B"},
    {"stem": "Work done is zero when ______.", "options": {"A": "force is large", "B": "displacement is zero", "C": "time is zero", "D": "velocity is high"}, "answer": "B"},
    {"stem": "The SI unit of power is ______.", "options": {"A": "joule", "B": "watt", "C": "newton", "D": "volt"}, "answer": "B"},
    {"stem": "A body floats when ______.", "options": {"A": "density is greater than liquid", "B": "density is equal or less than liquid", "C": "weight is zero", "D": "pressure is zero"}, "answer": "B"},
    {"stem": "The image formed by a plane mirror is ______.", "options": {"A": "real and inverted", "B": "virtual and upright", "C": "real and upright", "D": "inverted only"}, "answer": "B"},
    {"stem": "Frequency is measured in ______.", "options": {"A": "seconds", "B": "hertz", "C": "metres", "D": "joules"}, "answer": "B"},
    {"stem": "The speed of light in vacuum is ______.", "options": {"A": "3 x 10^8 m/s", "B": "3 x 10^6 m/s", "C": "3 x 10^5 m/s", "D": "3 x 10^7 m/s"}, "answer": "A"},
    {"stem": "Resistance depends on ______.", "options": {"A": "length", "B": "area", "C": "material", "D": "all of the above"}, "answer": "D"},
    {"stem": "A fuse protects electrical appliances by ______.", "options": {"A": "increasing current", "B": "decreasing voltage", "C": "melting when current is high", "D": "storing charge"}, "answer": "C"},
    {"stem": "The unit of momentum is ______.", "options": {"A": "Ns", "B": "N", "C": "J", "D": "W"}, "answer": "A"},
    {"stem": "Heat transfer by convection occurs in ______.", "options": {"A": "solids", "B": "liquids and gases", "C": "vacuum", "D": "metals only"}, "answer": "B"},
    {"stem": "Refraction occurs due to change in ______.", "options": {"A": "speed of light", "B": "wavelength only", "C": "frequency only", "D": "amplitude"}, "answer": "A"},
    {"stem": "A transformer works on ______.", "options": {"A": "DC", "B": "AC", "C": "both", "D": "none"}, "answer": "B"},
    {"stem": "The unit of capacitance is ______.", "options": {"A": "farad", "B": "henry", "C": "ohm", "D": "tesla"}, "answer": "A"},
    {"stem": "Half-life is associated with ______.", "options": {"A": "waves", "B": "radioactivity", "C": "heat", "D": "optics"}, "answer": "B"},
    {"stem": "Potential difference is measured in ______.", "options": {"A": "ampere", "B": "volt", "C": "ohm", "D": "watt"}, "answer": "B"},
    {"stem": "The centre of gravity is the point where ______.", "options": {"A": "mass is zero", "B": "weight acts", "C": "velocity is maximum", "D": "pressure is zero"}, "answer": "B"},
    {"stem": "Efficiency of a machine is always ______.", "options": {"A": ">100%", "B": "=100%", "C": "<100%", "D": "zero"}, "answer": "C"},
    {"stem": "Energy cannot be created or destroyed according to ______.", "options": {"A": "Newton's law", "B": "conservation of energy", "C": "Ohm's law", "D": "Boyle's law"}, "answer": "B"},
]

THEORY = [
    {"stem": "(a) Define velocity and acceleration.\n(b) Derive the equation v^2 = u^2 + 2as.\n(c) A car accelerates from 10 m/s to 30 m/s over 50 m. Find acceleration.", "marks": Decimal("10.00")},
    {"stem": "(a) State Newton's three laws of motion.\n(b) Explain inertia with examples.\n(c) A force of 20 N acts on a 4 kg body. Find acceleration.", "marks": Decimal("10.00")},
    {"stem": "(a) Define work, energy and power.\n(b) State the law of conservation of energy.\n(c) A machine lifts 1000 N through 5 m in 10 s. Calculate power.", "marks": Decimal("10.00")},
    {"stem": "(a) Explain conduction, convection and radiation.\n(b) State Boyle's law.\n(c) A gas changes volume from 0.5 m^3 to 0.25 m^3. Find new pressure if initial pressure is 100 kPa.", "marks": Decimal("10.00")},
    {"stem": "(a) Define wavelength, frequency and wave speed.\n(b) State two properties of sound waves.\n(c) Calculate speed of a wave with frequency 500 Hz and wavelength 0.6 m.", "marks": Decimal("10.00")},
    {"stem": "(a) State laws of reflection.\n(b) Explain total internal reflection.\n(c) A ray passes from glass to air. Explain what happens.", "marks": Decimal("10.00")},
    {"stem": "(a) State Ohm's law.\n(b) Define resistance and resistivity.\n(c) Calculate current when 12 V is applied across 6 ohm.", "marks": Decimal("10.00")},
    {"stem": "(a) Explain series and parallel connections.\n(b) Derive formula for equivalent resistance in parallel.\n(c) Find equivalent resistance of 3 ohm and 6 ohm in parallel.", "marks": Decimal("10.00")},
    {"stem": "(a) Describe magnetic field around a conductor.\n(b) State Fleming's left-hand rule.\n(c) List two applications of electromagnetism.", "marks": Decimal("10.00")},
    {"stem": "(a) Define radioactivity.\n(b) List types of radioactive emissions.\n(c) State two uses of radioactive isotopes.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
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
    schedule_start = datetime(2026, 3, 24, 9, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 11, 0, tzinfo=lagos)

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
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 9:30 AM WAT.",
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
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 9:30 AM WAT."
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
            source_reference=f"SS3-PHY-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS3-PHY-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 75
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-PHY-EXAM",
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
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
        }
    )


main()
