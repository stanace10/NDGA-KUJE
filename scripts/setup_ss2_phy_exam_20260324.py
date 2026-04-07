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


TITLE = "TUE 8:30-9:30 SS2 Physics Second Term Exam"
DESCRIPTION = "PHYSICS EXAMINATION SECOND TERM CLASS: SS2"
BANK_NAME = "SS2 Physics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, attempt any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "Sound is produced by ______.", "options": {"A": "heat", "B": "vibrating bodies", "C": "light", "D": "radiation"}, "answer": "B"},
    {"stem": "Sound cannot travel through ______.", "options": {"A": "solids", "B": "liquids", "C": "gases", "D": "vacuum"}, "answer": "D"},
    {"stem": "The speed of sound is greatest in ______.", "options": {"A": "air", "B": "water", "C": "steel", "D": "vacuum"}, "answer": "C"},
    {"stem": "The pitch of a sound depends on its ______.", "options": {"A": "frequency", "B": "amplitude", "C": "wavelength", "D": "speed"}, "answer": "A"},
    {"stem": "The loudness of sound depends on ______.", "options": {"A": "frequency", "B": "amplitude", "C": "period", "D": "velocity"}, "answer": "B"},
    {"stem": "Sound waves are ______ waves.", "options": {"A": "longitudinal", "B": "transverse", "C": "electromagnetic", "D": "optical"}, "answer": "A"},
    {"stem": "The reflection of sound is known as ______.", "options": {"A": "echo", "B": "pitch", "C": "refraction", "D": "diffraction"}, "answer": "A"},
    {"stem": "Which instrument is used to measure sound intensity level?", "options": {"A": "barometer", "B": "audiometer", "C": "galvanometer", "D": "photometer"}, "answer": "B"},
    {"stem": "Ultrasonic waves have frequencies ______.", "options": {"A": "above 20 Hz", "B": "below 20 Hz", "C": "above 20,000 Hz", "D": "between 20-200 Hz"}, "answer": "C"},
    {"stem": "One application of ultrasound is ______.", "options": {"A": "ironing", "B": "medical imaging", "C": "cooking", "D": "welding metals"}, "answer": "B"},
    {"stem": "The molecular theory of matter states that matter is made up of ______.", "options": {"A": "atoms in rest", "B": "tiny particles in motion", "C": "empty space", "D": "electrons only"}, "answer": "B"},
    {"stem": "Brownian motion is evidence of ______.", "options": {"A": "gravity", "B": "sound", "C": "molecular motion", "D": "magnetism"}, "answer": "C"},
    {"stem": "Diffusion occurs fastest in ______.", "options": {"A": "solids", "B": "liquids", "C": "gases", "D": "plasma"}, "answer": "C"},
    {"stem": "The kinetic energy of molecules increases when ______.", "options": {"A": "temperature decreases", "B": "temperature increases", "C": "pressure decreases", "D": "mass increases"}, "answer": "B"},
    {"stem": "Electromagnetic waves do not require ______.", "options": {"A": "space", "B": "time", "C": "a medium", "D": "energy"}, "answer": "C"},
    {"stem": "Which of the following is an electromagnetic wave?", "options": {"A": "sound", "B": "X-ray", "C": "water wave", "D": "seismic wave"}, "answer": "B"},
    {"stem": "The speed of electromagnetic waves in vacuum is ______.", "options": {"A": "3 x 10^3 m/s", "B": "3 x 10^6 m/s", "C": "3 x 10^8 m/s", "D": "3 x 10^10 m/s"}, "answer": "C"},
    {"stem": "Radio waves have the ______ wavelength.", "options": {"A": "shortest", "B": "intermediate", "C": "longest", "D": "equal"}, "answer": "C"},
    {"stem": "Gamma rays are produced by ______.", "options": {"A": "heating", "B": "nuclear reactions", "C": "friction", "D": "sound vibration"}, "answer": "B"},
    {"stem": "One harmful effect of ultraviolet radiation is ______.", "options": {"A": "tanning", "B": "sunburn", "C": "heating water", "D": "producing echoes"}, "answer": "B"},
    {"stem": "A gravitational field is a region where a ______ experiences force.", "options": {"A": "charge", "B": "magnet", "C": "mass", "D": "stone"}, "answer": "C"},
    {"stem": "The unit of gravitational field strength is ______.", "options": {"A": "N/C", "B": "N/kg", "C": "J/kg", "D": "m/s"}, "answer": "B"},
    {"stem": "The force of attraction between two masses is called ______.", "options": {"A": "electric force", "B": "magnetic force", "C": "gravitational force", "D": "nuclear force"}, "answer": "C"},
    {"stem": "Weight is a ______.", "options": {"A": "scalar", "B": "vector", "C": "mass", "D": "density"}, "answer": "B"},
    {"stem": "The acceleration due to gravity on Earth is approximately ______.", "options": {"A": "0 m/s^2", "B": "4.9 m/s^2", "C": "9.8 m/s^2", "D": "15 m/s^2"}, "answer": "C"},
    {"stem": "The electric field around a positive charge is directed ______.", "options": {"A": "toward the charge", "B": "away from the charge", "C": "perpendicular to the charge", "D": "circular around the charge"}, "answer": "B"},
    {"stem": "Electric field intensity is measured in ______.", "options": {"A": "N", "B": "N/C", "C": "C/N", "D": "J/C"}, "answer": "B"},
    {"stem": "The instrument used to detect charge is ______.", "options": {"A": "voltmeter", "B": "ammeter", "C": "electroscope", "D": "potentiometer"}, "answer": "C"},
    {"stem": "The region around a charge where its influence is felt is called ______.", "options": {"A": "magnetic field", "B": "electric field", "C": "gravitational field", "D": "potential field"}, "answer": "B"},
    {"stem": "Insulators ______.", "options": {"A": "allow electrons to move freely", "B": "do not allow electrons to move freely", "C": "produce electric fields", "D": "store only positive charge"}, "answer": "B"},
    {"stem": "Charging by friction occurs when ______.", "options": {"A": "charges flow", "B": "bodies move apart", "C": "two bodies rub together", "D": "two metals combine"}, "answer": "C"},
    {"stem": "When like charges meet, they ______.", "options": {"A": "attract", "B": "repel", "C": "remain neutral", "D": "combine"}, "answer": "B"},
    {"stem": "The force between two charges increases when distance ______.", "options": {"A": "increases", "B": "decreases", "C": "doubles", "D": "becomes zero"}, "answer": "B"},
    {"stem": "The type of wave that requires a medium is ______.", "options": {"A": "gamma ray", "B": "light", "C": "sound", "D": "X-ray"}, "answer": "C"},
    {"stem": "Which wave phenomenon proves that sound is mechanical?", "options": {"A": "Reflection", "B": "Refraction", "C": "Diffraction", "D": "Requirement of medium"}, "answer": "D"},
    {"stem": "The pitch of a sound increases when ______ increases.", "options": {"A": "amplitude", "B": "frequency", "C": "wavelength", "D": "speed"}, "answer": "B"},
    {"stem": "A tuning fork vibrates at 512 Hz. This value represents its ______.", "options": {"A": "amplitude", "B": "intensity", "C": "frequency", "D": "speed"}, "answer": "C"},
    {"stem": "The distance between two successive compressions is called ______.", "options": {"A": "amplitude", "B": "wavelength", "C": "frequency", "D": "timbre"}, "answer": "B"},
    {"stem": "Bats use ultrasound for ______.", "options": {"A": "cooking", "B": "walking", "C": "echolocation", "D": "heating"}, "answer": "C"},
    {"stem": "The electromagnetic wave with the highest frequency is ______.", "options": {"A": "radio", "B": "microwave", "C": "infrared", "D": "gamma ray"}, "answer": "D"},
]

THEORY = [
    {
        "stem": "(a) Define sound waves.\n(b) Explain any two characteristics of sound.\n(c) State three applications of sound waves.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "(a) State the molecular theory of matter.\n(b) Describe Brownian motion using smoke in air.\n(c) Explain why diffusion occurs faster in gases than liquids.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "(a) What are electromagnetic waves?\n(b) List four examples of electromagnetic waves.\n(c) State three properties of electromagnetic waves.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "(a) Define gravitational field.\n(b) State Newton's law of universal gravitation.\n(c) Calculate the gravitational force between two masses 5 kg and 10 kg separated by 2 m. (G = 6.67 x 10^-11 Nm^2/kg^2)",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "(a) Define electric field.\n(b) State two properties of electric field lines.\n(c) Calculate the electric field intensity at 1.5 m from a charge of 4 C. (k = 9 x 10^9 Nm^2/C^2)",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "(a) List three differences between sound waves and electromagnetic waves.\n(b) Explain why sound cannot travel in vacuum.\n(c) State two uses of electromagnetic waves in communication.",
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
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
            source_reference=f"SS2-PHY-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS2-PHY-20260324-TH-{index:02d}",
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
        "paper_code": "SS2-PHY-EXAM",
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
