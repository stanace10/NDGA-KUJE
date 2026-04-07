from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.constants import ROLE_SUBJECT_TEACHER
from apps.accounts.forms import generate_temporary_password
from apps.accounts.models import Role, StaffProfile, User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
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


USERNAME = "mr.literature@ndgakuje.org"
STAFF_ID = "NDGAK/STAFF/031"
FIRST_NAME = "Mr"
LAST_NAME = "Literature"
DISPLAY_NAME = "Mr Literature"
DESIGNATION = "Literature Teacher"

TITLE = "TUE 8:30-9:30 SS1 Literature Second Term Exam"
DESCRIPTION = "LITERATURE SS1 SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Literature Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer only four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 9:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "The central message of a literary work is its ______.", "options": {"A": "Plot", "B": "Theme", "C": "Style", "D": "Structure"}, "answer": "B"},
    {"stem": "A didactic work is ______.", "options": {"A": "Humorous", "B": "Tragic", "C": "Moral or instructional", "D": "Emotional"}, "answer": "C"},
    {"stem": "The technique of hinting at future events is ______.", "options": {"A": "Suspense", "B": "Foreshadowing", "C": "Irony", "D": "Flashback"}, "answer": "B"},
    {"stem": "The turning point in a story is ______.", "options": {"A": "Exposition", "B": "Conflict", "C": "Resolution", "D": "Climax"}, "answer": "D"},
    {"stem": "A sudden unexpected change in a story is ______.", "options": {"A": "Twist", "B": "Resolution", "C": "Theme", "D": "Setting"}, "answer": "A"},
    {"stem": "\"The wind whispered through the trees\" is ______.", "options": {"A": "Hyperbole", "B": "Irony", "C": "Metaphor", "D": "Personification"}, "answer": "D"},
    {"stem": "\"He runs like a cheetah\" is ______.", "options": {"A": "Metaphor", "B": "Simile", "C": "Oxymoron", "D": "Irony"}, "answer": "B"},
    {"stem": "A statement that contradicts itself but reveals truth is ______.", "options": {"A": "Paradox", "B": "Irony", "C": "Pun", "D": "Euphemism"}, "answer": "A"},
    {"stem": "\"Living dead\" is an example of ______.", "options": {"A": "Metaphor", "B": "Hyperbole", "C": "Oxymoron", "D": "Irony"}, "answer": "C"},
    {"stem": "Repetition of vowel sounds is ______.", "options": {"A": "Alliteration", "B": "Assonance", "C": "Consonance", "D": "Rhythm"}, "answer": "B"},
    {"stem": "A long narrative poem about heroic deeds is ______.", "options": {"A": "Ode", "B": "Epic", "C": "Lyric", "D": "Sonnet"}, "answer": "B"},
    {"stem": "The writer of a poem is called a/an ______.", "options": {"A": "Poet", "B": "Narrator", "C": "Persona", "D": "Orator"}, "answer": "A"},
    {"stem": "A 14-line poem is a/an ______.", "options": {"A": "Ode", "B": "Sonnet", "C": "Ballad", "D": "Elegy"}, "answer": "B"},
    {"stem": "An elegy is a poem written to ______.", "options": {"A": "Praise love", "B": "Mourn the dead", "C": "Tell a story", "D": "Entertain"}, "answer": "B"},
    {"stem": "The resolution ______.", "options": {"A": "starts the story", "B": "ends the conflict", "C": "builds suspense", "D": "introduces characters"}, "answer": "B"},
    {"stem": "A long speech by one character alone is ______.", "options": {"A": "Dialogue", "B": "Aside", "C": "Soliloquy", "D": "Chorus"}, "answer": "C"},
    {"stem": "A remark made for the audience alone is ______.", "options": {"A": "Dialogue", "B": "Aside", "C": "Monologue", "D": "Soliloquy"}, "answer": "B"},
    {"stem": "When the audience knows more than the characters, it is ______.", "options": {"A": "Dramatic irony", "B": "Situational irony", "C": "Verbal irony", "D": "Paradox"}, "answer": "A"},
    {"stem": "A tragic flaw is ______.", "options": {"A": "Physical strength", "B": "Talent", "C": "Good habit", "D": "Moral weakness"}, "answer": "D"},
    {"stem": "The protagonist in a tragedy usually ______.", "options": {"A": "wins", "B": "falls due to a flaw", "C": "is perfect", "D": "is always evil"}, "answer": "B"},
    {"stem": "Catharsis refers to ______.", "options": {"A": "Fear", "B": "Conflict", "C": "Emotional release", "D": "Irony"}, "answer": "C"},
    {"stem": "Flashback is used to ______.", "options": {"A": "show future", "B": "recall past events", "C": "end story", "D": "introduce characters"}, "answer": "B"},
    {"stem": "Imagery appeals to ______.", "options": {"A": "senses", "B": "logic", "C": "grammar", "D": "plot"}, "answer": "A"},
    {"stem": "Symbolism means ______.", "options": {"A": "literal meaning", "B": "use of symbols for deeper meaning", "C": "repetition", "D": "comparison"}, "answer": "B"},
    {"stem": "Satire is used to ______.", "options": {"A": "praise society", "B": "criticize society", "C": "entertain only", "D": "describe events"}, "answer": "B"},
    {"stem": "A character that develops is ______.", "options": {"A": "Flat", "B": "Static", "C": "Round", "D": "Minor"}, "answer": "C"},
    {"stem": "Suspense helps to ______.", "options": {"A": "end story quickly", "B": "build tension", "C": "confuse readers", "D": "add humour"}, "answer": "B"},
    {"stem": "Diction refers to ______.", "options": {"A": "choice of words", "B": "plot", "C": "setting", "D": "tone"}, "answer": "A"},
    {"stem": "Tone is ______.", "options": {"A": "reader's feeling", "B": "writer's attitude", "C": "plot structure", "D": "theme"}, "answer": "B"},
    {"stem": "Mood is ______.", "options": {"A": "writer's opinion", "B": "setting", "C": "character's role", "D": "reader's feeling"}, "answer": "D"},
    {"stem": "What is the central theme of Once Upon an Elephant?", "options": {"A": "Romantic love", "B": "Tyranny and abuse of power", "C": "Educational development", "D": "Cultural exchange"}, "answer": "B"},
    {"stem": "Which character in the play acts as the custodian of tradition and is often misunderstood as mad?", "options": {"A": "Serubawon", "B": "Ajanaku", "C": "Iya Agba", "D": "Desola"}, "answer": "C"},
    {"stem": "How did Ajanaku rise to the throne in the play?", "options": {"A": "Through honest election", "B": "By rightful inheritance", "C": "Through manipulation, bribery, and corruption", "D": "By a popular vote of the people"}, "answer": "C"},
    {"stem": "Which character is portrayed as the chief strategist behind Ajanaku's ascent and a supporter of his corrupt regime?", "options": {"A": "Odekunle", "B": "Serubawon", "C": "Lere", "D": "The Guild of Hunters"}, "answer": "B"},
    {"stem": "Who is the daughter of Serubawon that becomes a victim of Ajanaku's actions?", "options": {"A": "Desola", "B": "Amoyani", "C": "Iya Agba", "D": "Yele"}, "answer": "A"},
    {"stem": "What metaphor is used throughout the play to represent tyranny?", "options": {"A": "A lion", "B": "A lioness", "C": "An elephant", "D": "A tiger"}, "answer": "C"},
    {"stem": "What is the ultimate fate of Ajanaku in the play?", "options": {"A": "He reconciles with the village", "B": "He rules for life", "C": "He is killed in battle", "D": "His tyranny collapses, bringing him down"}, "answer": "D"},
    {"stem": "The play Once Upon an Elephant is predominantly set in which type of setting?", "options": {"A": "A modern city", "B": "A rural Nigerian village", "C": "A coastal town", "D": "An urban slum"}, "answer": "B"},
    {"stem": "What does the character of Iya Agba represent?", "options": {"A": "Corrupt leadership", "B": "Youthful exuberance", "C": "Wisdom, tradition, and the conscience of the land", "D": "Foreign intervention"}, "answer": "C"},
    {"stem": "Who is the wife of Serubawon?", "options": {"A": "Adebisi", "B": "Omoyeni", "C": "Desola", "D": "Demoke"}, "answer": "D"},
]

THEORY = [
    {"stem": "What role does Serubawon play in the drama?", "marks": Decimal("10.00")},
    {"stem": "Identify and discuss two themes in the play.", "marks": Decimal("10.00")},
    {"stem": "Describe the Ijedodo ritual and its significance.", "marks": Decimal("10.00")},
    {"stem": "Examine how relevant the message of the play is to modern society today.", "marks": Decimal("10.00")},
    {"stem": "Mention five linguistic and stylistic features employed by the playwright in the play.", "marks": Decimal("10.00")},
    {"stem": "Write short notes on the following characters: (a) Ajanaku (b) Iya Agba (c) Odekunle.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject_teacher_role = Role.objects.get(code=ROLE_SUBJECT_TEACHER)
    subject = Subject.objects.get(code="LIT")
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")

    teacher, created_teacher = User.objects.get_or_create(
        username=USERNAME,
        defaults={
            "first_name": FIRST_NAME,
            "last_name": LAST_NAME,
            "display_name": DISPLAY_NAME,
            "primary_role": subject_teacher_role,
            "must_change_password": False,
            "is_active": True,
        },
    )
    if created_teacher:
        teacher.set_password(generate_temporary_password(STAFF_ID))
        teacher.save()
    else:
        dirty = False
        if teacher.primary_role_id != subject_teacher_role.id:
            teacher.primary_role = subject_teacher_role
            dirty = True
        if teacher.first_name != FIRST_NAME:
            teacher.first_name = FIRST_NAME
            dirty = True
        if teacher.last_name != LAST_NAME:
            teacher.last_name = LAST_NAME
            dirty = True
        if teacher.display_name != DISPLAY_NAME:
            teacher.display_name = DISPLAY_NAME
            dirty = True
        if teacher.must_change_password:
            teacher.must_change_password = False
            dirty = True
        if not teacher.is_active:
            teacher.is_active = True
            dirty = True
        if dirty:
            teacher.save()
    teacher.secondary_roles.add(subject_teacher_role)

    staff_profile, _ = StaffProfile.objects.get_or_create(
        user=teacher,
        defaults={"staff_id": STAFF_ID, "designation": DESIGNATION},
    )
    if staff_profile.staff_id != STAFF_ID or staff_profile.designation != DESIGNATION:
        staff_profile.staff_id = STAFF_ID
        staff_profile.designation = DESIGNATION
        staff_profile.save()

    class_codes = ["SS1", "SS2", "SS3"]
    mapped_classes = []
    assignment_count = 0
    enrolled_count = 0
    for code in class_codes:
        academic_class = AcademicClass.objects.get(code=code)
        mapped_classes.append(academic_class)
        ClassSubject.objects.update_or_create(
            academic_class=academic_class,
            subject=subject,
            defaults={"is_active": True},
        )
        TeacherSubjectAssignment.objects.update_or_create(
            subject=subject,
            academic_class=academic_class,
            session=session,
            term=term,
            defaults={"teacher": teacher, "is_active": True},
        )
        assignment_count += 1

    active_enrollments = (
        StudentClassEnrollment.objects.select_related("student", "academic_class", "academic_class__base_class")
        .filter(session=session, is_active=True)
    )
    target_ids = {row.id for row in mapped_classes}
    for enrollment in active_enrollments:
        instructional = enrollment.academic_class.instructional_class
        if instructional.id not in target_ids:
            continue
        _, created = StudentSubjectEnrollment.objects.update_or_create(
            student=enrollment.student,
            subject=subject,
            session=session,
            defaults={"is_active": True},
        )
        if created:
            enrolled_count += 1

    academic_class = AcademicClass.objects.get(code="SS1")
    assignment = TeacherSubjectAssignment.objects.get(
        academic_class=academic_class,
        subject=subject,
        session=session,
        term=term,
        is_active=True,
    )

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

    exam, created_exam = Exam.objects.get_or_create(
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
            source_reference=f"SS1-LIT-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS1-LIT-20260324-TH-{index:02d}",
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
        "paper_code": "SS1-LIT-EXAM",
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
            "teacher_created": created_teacher,
            "username": teacher.username,
            "staff_id": staff_profile.staff_id,
            "subject_assignments": assignment_count,
            "new_student_subject_enrollments": enrolled_count,
            "exam_created": created_exam,
            "exam_id": exam.id,
            "title": exam.title,
        }
    )


main()
