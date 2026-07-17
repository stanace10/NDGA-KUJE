from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

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


TITLE = "TUE 9:30-10:30 SS2 Literature Second Term Exam"
DESCRIPTION = "SS2 Literature Second Term Examination"
BANK_NAME = "SS2 Literature Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer only four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 10:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "In drama, a speech delivered when a character is alone on stage is a ______.", "options": {"A": "Aside", "B": "Monologue", "C": "Soliloquy", "D": "Dialogue"}, "answer": "C"},
    {"stem": "Which of the following best defines dramatic irony?", "options": {"A": "When the character knows more than the audience", "B": "When the audience knows more than the character", "C": "When events are humorous", "D": "When language is exaggerated"}, "answer": "B"},
    {"stem": "The climax of a plot occurs when ______.", "options": {"A": "the story begins", "B": "conflict is introduced", "C": "tension reaches its peak", "D": "the story ends"}, "answer": "C"},
    {"stem": "A character who does not change throughout a story is ______.", "options": {"A": "Round", "B": "Dynamic", "C": "Static", "D": "Protagonist"}, "answer": "C"},
    {"stem": "Which literary device involves exaggeration?", "options": {"A": "Irony", "B": "Hyperbole", "C": "Euphemism", "D": "Allusion"}, "answer": "B"},
    {"stem": "A tragedy usually ends with ______.", "options": {"A": "Marriage", "B": "Celebration", "C": "Death or downfall", "D": "Victory"}, "answer": "C"},
    {"stem": "A reference to a well-known event or figure is ______.", "options": {"A": "Allegory", "B": "Allusion", "C": "Satire", "D": "Pun"}, "answer": "B"},
    {"stem": "In poetry, a stanza is ______.", "options": {"A": "a line", "B": "a paragraph", "C": "a group of lines", "D": "a rhyme"}, "answer": "C"},
    {"stem": "The use of contrasting ideas in a sentence is ______.", "options": {"A": "Irony", "B": "Simile", "C": "Antithesis", "D": "Metaphor"}, "answer": "C"},
    {"stem": "A play on words is called ______.", "options": {"A": "Pun", "B": "Irony", "C": "Metaphor", "D": "Symbolism"}, "answer": "A"},
    {"stem": "A narrative that has a double meaning is ______.", "options": {"A": "Satire", "B": "Allegory", "C": "Parody", "D": "Elegy"}, "answer": "B"},
    {"stem": "The hero in a tragedy is called ______.", "options": {"A": "Villain", "B": "Protagonist", "C": "Tragic hero", "D": "Antagonist"}, "answer": "C"},
    {"stem": "The emotional atmosphere created by a writer is ______.", "options": {"A": "Tone", "B": "Mood", "C": "Theme", "D": "Plot"}, "answer": "B"},
    {"stem": "A poem that mourns the dead is ______.", "options": {"A": "Ode", "B": "Elegy", "C": "Sonnet", "D": "Ballad"}, "answer": "B"},
    {"stem": "Which of the following is NOT a feature of tragedy?", "options": {"A": "Noble character", "B": "Comic relief", "C": "Happy ending", "D": "Fatal flaw"}, "answer": "C"},
    {"stem": "Words that have the same ending sound are called ______.", "options": {"A": "Rhythm", "B": "Rhyme", "C": "Tone", "D": "Mood"}, "answer": "B"},
    {"stem": "Repetition of consonant sounds is called ______.", "options": {"A": "Assonance", "B": "Alliteration", "C": "Rhyme", "D": "Rhythm"}, "answer": "B"},
    {"stem": "A poem that tells a story is ______.", "options": {"A": "Lyric", "B": "Ode", "C": "Narrative", "D": "Sonnet"}, "answer": "C"},
    {"stem": "The repetition of vowel sounds is ______.", "options": {"A": "Alliteration", "B": "Assonance", "C": "Consonance", "D": "Rhythm"}, "answer": "B"},
    {"stem": "A figure of speech comparing two unlike things directly is ______.", "options": {"A": "Simile", "B": "Metaphor", "C": "Irony", "D": "Symbol"}, "answer": "B"},
    {"stem": "The house in the passage is best described as ______.", "options": {"A": "Modern", "B": "Abandoned", "C": "Beautiful", "D": "New"}, "answer": "B"},
    {"stem": "The tone of the unseen prose passage is ______.", "options": {"A": "Cheerful", "B": "Mysterious", "C": "Humorous", "D": "Romantic"}, "answer": "B"},
    {"stem": "\"Whispering secrets\" is an example of ______.", "options": {"A": "Simile", "B": "Irony", "C": "Personification", "D": "Hyperbole"}, "answer": "C"},
    {"stem": "The mood created by the unseen prose passage is ______.", "options": {"A": "Fearful", "B": "Joyful", "C": "Angry", "D": "Excited"}, "answer": "A"},
    {"stem": "The phrase \"dull colour of neglect\" suggests ______.", "options": {"A": "Beauty", "B": "Carelessness", "C": "Wealth", "D": "Happiness"}, "answer": "B"},
    {"stem": "The villagers avoid the house because ______.", "options": {"A": "it is too small", "B": "it is expensive", "C": "of frightening stories", "D": "it is far away"}, "answer": "C"},
    {"stem": "The setting of the unseen prose passage is ______.", "options": {"A": "City", "B": "Village edge", "C": "Market", "D": "School"}, "answer": "B"},
    {"stem": "The doors creaking suggests ______.", "options": {"A": "Silence", "B": "Movement and age", "C": "Happiness", "D": "Strength"}, "answer": "B"},
    {"stem": "The unseen prose passage mainly explores ______.", "options": {"A": "Wealth", "B": "Fear of the unknown", "C": "Friendship", "D": "Education"}, "answer": "B"},
    {"stem": "The narrative point of view in the unseen prose passage is ______.", "options": {"A": "First person", "B": "Second person", "C": "Third person", "D": "Dramatic"}, "answer": "C"},
    {"stem": "The rhyme scheme of the poem is ______.", "options": {"A": "ABAB", "B": "AABB", "C": "AAAA", "D": "ABBA"}, "answer": "C"},
    {"stem": "\"Thunder roars\" is an example of ______.", "options": {"A": "Simile", "B": "Personification", "C": "Metaphor", "D": "Irony"}, "answer": "B"},
    {"stem": "\"A lion's cry\" is ______.", "options": {"A": "Metaphor", "B": "Simile", "C": "Hyperbole", "D": "Irony"}, "answer": "A"},
    {"stem": "The mood of the poem is ______.", "options": {"A": "Peaceful", "B": "Tense", "C": "Joyful", "D": "Calm"}, "answer": "B"},
    {"stem": "The tone of the poem is ______.", "options": {"A": "Gentle", "B": "Fearful", "C": "Playful", "D": "Calm"}, "answer": "B"},
    {"stem": "The poem appeals mostly to ______.", "options": {"A": "Taste", "B": "Smell", "C": "Sight and sound", "D": "Touch"}, "answer": "C"},
    {"stem": "The central theme of the poem is ______.", "options": {"A": "Love", "B": "Nature's power", "C": "Wealth", "D": "Friendship"}, "answer": "B"},
    {"stem": "\"Dark clouds\" symbolize ______.", "options": {"A": "Joy", "B": "Danger", "C": "Peace", "D": "Wealth"}, "answer": "B"},
    {"stem": "The poem can be classified as ______.", "options": {"A": "Lyric", "B": "Epic", "C": "Sonnet", "D": "Ballad"}, "answer": "A"},
    {"stem": "The expression \"storms draw nigh\" means ______.", "options": {"A": "storms are ending", "B": "storms are weak", "C": "storms are far away", "D": "storms are approaching"}, "answer": "D"},
]

THEORY = [
    {"stem": "Identify and discuss two themes in the play.", "marks": Decimal("10.00")},
    {"stem": "Who is Eva Smith, and why is she important in the play?", "marks": Decimal("10.00")},
    {"stem": "Examine the setting of the play and its significance.", "marks": Decimal("10.00")},
    {"stem": "What is your opinion of the Birling family?", "marks": Decimal("10.00")},
    {"stem": "Briefly examine three linguistic and stylistic features used in the play.", "marks": Decimal("10.00")},
    {"stem": "What is the relevance of the play to our modern society today?", "marks": Decimal("10.00")},
]


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="LIT")
    academic_class = AcademicClass.objects.get(code="SS2")
    teacher = User.objects.get(username="mr.literature@ndgakuje.org")
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher=teacher,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    )

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 24, 9, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 10, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday second paper.",
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
    exam.dean_review_comment = "Approved for Tuesday second paper."
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
            source_reference=f"SS2-LIT-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS2-LIT-20260324-TH-{index:02d}",
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
        "paper_code": "SS2-LIT-EXAM",
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
            "duration": blueprint.duration_minutes,
        }
    )


main()
