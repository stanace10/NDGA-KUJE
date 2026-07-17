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


TITLE = "TUE 8:30-9:30 JS2 Basic Science Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION SUBJECT: BASIC SCIENCE CLASS: JSS2"
BANK_NAME = "JS2 Basic Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer question one and any other question. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {
        "stem": "The human skeleton is made up mainly of ______.",
        "options": {"A": "muscles and tendons", "B": "bones and cartilage", "C": "nerves and veins", "D": "skin and tissues"},
        "answer": "B",
    },
    {
        "stem": "How many bones are there in the adult human skeleton?",
        "options": {"A": "106", "B": "186", "C": "206", "D": "306"},
        "answer": "C",
    },
    {
        "stem": "The main function of the skeleton is to ______.",
        "options": {"A": "digest food", "B": "protect internal organs", "C": "pump blood", "D": "produce hormones"},
        "answer": "B",
    },
    {
        "stem": "Which part of the skeleton protects the brain?",
        "options": {"A": "Skull", "B": "Rib cage", "C": "Backbone", "D": "Pelvic girdle"},
        "answer": "A",
    },
    {
        "stem": "The backbone is also known as the ______.",
        "options": {"A": "rib cage", "B": "femur", "C": "humerus", "D": "vertebral column"},
        "answer": "D",
    },
    {
        "stem": "Which of the following organs is protected by the rib cage?",
        "options": {"A": "Liver", "B": "Brain", "C": "Heart", "D": "Stomach"},
        "answer": "C",
    },
    {
        "stem": "The bones of the arms and legs belong to the ______.",
        "options": {"A": "appendicular skeleton", "B": "axial skeleton", "C": "skull", "D": "rib cage"},
        "answer": "A",
    },
    {
        "stem": "Which bone is the longest in the human body?",
        "options": {"A": "Tibia", "B": "Femur", "C": "Ulna", "D": "Radius"},
        "answer": "B",
    },
    {
        "stem": "The skeletal system works closely with the ______.",
        "options": {"A": "digestive system", "B": "circulatory system", "C": "respiratory system", "D": "muscular system"},
        "answer": "D",
    },
    {
        "stem": "The pelvic girdle protects the ______.",
        "options": {"A": "lungs", "B": "heart", "C": "reproductive organs", "D": "brain"},
        "answer": "C",
    },
    {
        "stem": "Which of the following is a function of the skeleton?",
        "options": {"A": "Movement", "B": "Thinking", "C": "Breathing", "D": "Digestion"},
        "answer": "A",
    },
    {
        "stem": "The ribs are connected to the ______.",
        "options": {"A": "skull", "B": "arms", "C": "backbone", "D": "pelvis"},
        "answer": "C",
    },
    {
        "stem": "Which bone forms the shoulder girdle?",
        "options": {"A": "Scapula", "B": "Femur", "C": "Tibia", "D": "Patella"},
        "answer": "A",
    },
    {
        "stem": "Cartilage is found mainly at the ______.",
        "options": {"A": "ends of bones", "B": "middle of bones", "C": "bone marrow", "D": "skull"},
        "answer": "A",
    },
    {
        "stem": "Which part of the skeleton gives shape to the body?",
        "options": {"A": "Skull", "B": "Skeleton", "C": "Rib cage", "D": "Pelvic girdle"},
        "answer": "B",
    },
    {
        "stem": "The process of taking air into the lungs is called ______.",
        "options": {"A": "exhalation", "B": "respiration", "C": "inhalation", "D": "diffusion"},
        "answer": "C",
    },
    {
        "stem": "Which of the following organs is NOT part of the respiratory system?",
        "options": {"A": "Nose", "B": "Trachea", "C": "Lungs", "D": "Kidney"},
        "answer": "D",
    },
    {
        "stem": "Air enters the human body through the ______.",
        "options": {"A": "mouth only", "B": "nose only", "C": "nose and mouth", "D": "lungs"},
        "answer": "C",
    },
    {
        "stem": "The windpipe is also known as the ______.",
        "options": {"A": "bronchus", "B": "bronchiole", "C": "alveolus", "D": "trachea"},
        "answer": "D",
    },
    {
        "stem": "The tiny air sacs in the lungs where gas exchange takes place are called ______.",
        "options": {"A": "bronchi", "B": "alveoli", "C": "diaphragm", "D": "ribs"},
        "answer": "B",
    },
    {
        "stem": "Which gas is taken in during breathing?",
        "options": {"A": "Carbon dioxide", "B": "Nitrogen", "C": "Oxygen", "D": "Hydrogen"},
        "answer": "C",
    },
    {
        "stem": "Which gas is given out during breathing?",
        "options": {"A": "Oxygen", "B": "Carbon monoxide", "C": "Nitrogen", "D": "Carbon dioxide"},
        "answer": "D",
    },
    {
        "stem": "The movement of the diaphragm during inhalation is ______.",
        "options": {"A": "downward", "B": "upward", "C": "sideways", "D": "backward"},
        "answer": "A",
    },
    {
        "stem": "Which organ helps the lungs to expand and contract during breathing?",
        "options": {"A": "Heart", "B": "Diaphragm", "C": "Liver", "D": "Kidney"},
        "answer": "B",
    },
    {
        "stem": "Breathing out is also called ______.",
        "options": {"A": "inhalation", "B": "diffusion", "C": "respiration", "D": "exhalation"},
        "answer": "D",
    },
    {
        "stem": "The respiratory system works closely with the ______.",
        "options": {"A": "digestive system", "B": "nervous system", "C": "circulatory system", "D": "skeletal system"},
        "answer": "C",
    },
    {
        "stem": "Which of the following can damage the respiratory system?",
        "options": {"A": "Clean air", "B": "Smoking", "C": "Exercise", "D": "Balanced diet"},
        "answer": "B",
    },
    {
        "stem": "One function of the nose in breathing is to ______.",
        "options": {"A": "pump blood", "B": "digest food", "C": "filter air", "D": "store oxygen"},
        "answer": "C",
    },
    {
        "stem": "The organ that pumps blood round the body is the ______.",
        "options": {"A": "heart", "B": "lung", "C": "kidney", "D": "liver"},
        "answer": "A",
    },
    {
        "stem": "Blood vessels that carry blood away from the heart are called ______.",
        "options": {"A": "veins", "B": "capillaries", "C": "valves", "D": "arteries"},
        "answer": "D",
    },
    {
        "stem": "Blood vessels that carry blood back to the heart are known as ______.",
        "options": {"A": "arteries", "B": "veins", "C": "capillaries", "D": "chamber"},
        "answer": "B",
    },
    {
        "stem": "The smallest blood vessels in the body are ______.",
        "options": {"A": "arteries", "B": "veins", "C": "capillaries", "D": "aorta"},
        "answer": "C",
    },
    {
        "stem": "The red colour of blood is due to ______.",
        "options": {"A": "haemoglobin", "B": "plasma", "C": "platelets", "D": "serum"},
        "answer": "A",
    },
    {
        "stem": "Which part of the blood helps in clotting?",
        "options": {"A": "Red blood cells", "B": "White blood cells", "C": "Plasma", "D": "Platelets"},
        "answer": "D",
    },
    {
        "stem": "White blood cells are mainly responsible for ______.",
        "options": {"A": "carrying oxygen", "B": "fighting diseases", "C": "clotting blood", "D": "digesting food"},
        "answer": "B",
    },
    {
        "stem": "The liquid part of blood is called ______.",
        "options": {"A": "serum", "B": "plasma", "C": "platelets", "D": "haemoglobin"},
        "answer": "B",
    },
    {
        "stem": "How many chambers does the human heart have?",
        "options": {"A": "Two", "B": "Three", "C": "Four", "D": "Five"},
        "answer": "C",
    },
    {
        "stem": "Which of the following carries oxygen to body cells?",
        "options": {"A": "plasma", "B": "white blood cells", "C": "red blood cells", "D": "platelets"},
        "answer": "C",
    },
    {
        "stem": "The movement of blood through the heart and body is called ______.",
        "options": {"A": "digestion", "B": "circulation", "C": "respiration", "D": "excretion"},
        "answer": "B",
    },
    {
        "stem": "The circulatory system works closely with the ______.",
        "options": {"A": "respiratory system", "B": "skeletal system", "C": "digestive system", "D": "reproductive system"},
        "answer": "A",
    },
]

THEORY = [
    {
        "stem": (
            "(a) Define reproductive system.\n"
            "(b) Mention four parts of the male reproductive system.\n"
            "(c) Mention four parts of the female reproductive system.\n"
            "(d) What is fertilization?\n"
            "(e) Define puberty."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "(a) What is body image?\n"
            "(b) State three factors that can influence a person's body image.\n"
            "(c) State three positive body image habits.\n"
            "(d) State three negative body image habits."
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "(a) What is digestive system?\n"
            "(b) Mention the role of teeth, tongue, and saliva.\n"
            "(c) Explain the functions of the following organs:\n"
            "    (i) Oesophagus\n"
            "    (ii) Stomach\n"
            "    (iii) Small intestine\n"
            "    (iv) Large intestine"
        ),
        "marks": Decimal("10.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="BSC")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="mattawada@ndgakuje.org",
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
            source_reference=f"JS2-BSC-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS2-BSC-20260324-TH-{index:02d}",
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
        "paper_code": "JS2-BSC-EXAM",
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
