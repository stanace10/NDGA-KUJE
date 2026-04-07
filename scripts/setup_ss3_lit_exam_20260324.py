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


TITLE = "TUE 9:30-10:30 SS3 Literature Second Term Exam"
DESCRIPTION = "SS3 Literature Second Term Examination"
BANK_NAME = "SS3 Literature Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer the required questions from each section. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 60 minutes. Exam window closes at 10:30 AM WAT on Tuesday, March 24, 2026."
)

OBJECTIVES = [
    {"stem": "A dominant impression created in a literary work is known as ______.", "options": {"A": "Theme", "B": "Mood", "C": "Plot", "D": "Tone"}, "answer": "B"},
    {"stem": "A narrative that begins in the middle of the story is said to start ______.", "options": {"A": "In medias res", "B": "Flashback", "C": "Climax", "D": "Prologue"}, "answer": "A"},
    {"stem": "The technique of using a story within a story is called ______.", "options": {"A": "Foreshadowing", "B": "Frame narrative", "C": "Parody", "D": "Allegory"}, "answer": "B"},
    {"stem": "A character who contrasts with another character is a ______.", "options": {"A": "Round character", "B": "Foil", "C": "Static character", "D": "Hero"}, "answer": "B"},
    {"stem": "Which of the following best defines catharsis?", "options": {"A": "Emotional purification", "B": "Comic relief", "C": "Conflict resolution", "D": "Plot twist"}, "answer": "A"},
    {"stem": "A story that teaches a moral lesson is a ______.", "options": {"A": "Fable", "B": "Epic", "C": "Ode", "D": "Ballad"}, "answer": "A"},
    {"stem": "The turning point in a narrative is called ______.", "options": {"A": "Resolution", "B": "Exposition", "C": "Climax", "D": "Denouement"}, "answer": "C"},
    {"stem": "The repetition of consonant sounds at the beginning of words is ______.", "options": {"A": "Assonance", "B": "Alliteration", "C": "Consonance", "D": "Onomatopoeia"}, "answer": "B"},
    {"stem": "A tragic flaw is technically known as ______.", "options": {"A": "Hubris", "B": "Nemesis", "C": "Hamartia", "D": "Pathos"}, "answer": "C"},
    {"stem": "A literary work that ridicules human weaknesses is ______.", "options": {"A": "Satire", "B": "Elegy", "C": "Epic", "D": "Ode"}, "answer": "A"},
    {"stem": "A character that does not change throughout a story is ______.", "options": {"A": "Dynamic", "B": "Flat", "C": "Static", "D": "Round"}, "answer": "C"},
    {"stem": "The perspective from which a story is told is ______.", "options": {"A": "Theme", "B": "Point of view", "C": "Plot", "D": "Setting"}, "answer": "B"},
    {"stem": "Which device involves exaggeration for emphasis?", "options": {"A": "Irony", "B": "Hyperbole", "C": "Metaphor", "D": "Simile"}, "answer": "B"},
    {"stem": "A comparison using 'like' or 'as' is ______.", "options": {"A": "Metaphor", "B": "Simile", "C": "Personification", "D": "Symbolism"}, "answer": "B"},
    {"stem": "The background time and place of a story is ______.", "options": {"A": "Plot", "B": "Theme", "C": "Setting", "D": "Conflict"}, "answer": "C"},
    {"stem": "Verbal irony occurs when ______.", "options": {"A": "words mean the opposite of what is said", "B": "characters act differently", "C": "events are tragic", "D": "dialogue is humorous"}, "answer": "A"},
    {"stem": "A poem of mourning is called ______.", "options": {"A": "Ode", "B": "Ballad", "C": "Elegy", "D": "Lyric"}, "answer": "C"},
    {"stem": "The main idea of a literary work is ______.", "options": {"A": "Plot", "B": "Theme", "C": "Tone", "D": "Style"}, "answer": "B"},
    {"stem": "A long narrative poem about heroic deeds is ______.", "options": {"A": "Ode", "B": "Epic", "C": "Lyric", "D": "Sonnet"}, "answer": "B"},
    {"stem": "The sequence of events in a story is ______.", "options": {"A": "Setting", "B": "Plot", "C": "Theme", "D": "Tone"}, "answer": "B"},
    {"stem": "The rhyme scheme of the poem is ______.", "options": {"A": "ABAB", "B": "AABB", "C": "ABBA", "D": "AAAA"}, "answer": "B"},
    {"stem": "The tone of the poem is ______.", "options": {"A": "Joyful", "B": "Reflective", "C": "Angry", "D": "Satirical"}, "answer": "B"},
    {"stem": "'Night whispers' is an example of ______.", "options": {"A": "Metaphor", "B": "Personification", "C": "Simile", "D": "Irony"}, "answer": "B"},
    {"stem": "The mood of the poem is ______.", "options": {"A": "Peaceful and sad", "B": "Excited", "C": "Violent", "D": "Comic"}, "answer": "A"},
    {"stem": "The 'lonely heart' suggests ______.", "options": {"A": "Happiness", "B": "Isolation", "C": "Strength", "D": "Courage"}, "answer": "B"},
    {"stem": "The imagery in the poem appeals mainly to the sense of ______.", "options": {"A": "Taste", "B": "Sight", "C": "Smell", "D": "Touch"}, "answer": "B"},
    {"stem": "The poem is an example of ______.", "options": {"A": "Dramatic poetry", "B": "Narrative poetry", "C": "Lyric poetry", "D": "Epic poetry"}, "answer": "C"},
    {"stem": "The central theme of the poem is ______.", "options": {"A": "War", "B": "Loneliness", "C": "Wealth", "D": "Nature's power"}, "answer": "B"},
    {"stem": "The poet's attitude is ______.", "options": {"A": "Indifferent", "B": "Reflective", "C": "Hostile", "D": "Humorous"}, "answer": "B"},
    {"stem": "'Silver stars' is an example of ______.", "options": {"A": "Symbolism", "B": "Hyperbole", "C": "Euphemism", "D": "Irony"}, "answer": "A"},
    {"stem": "The setting of the prose passage is ______.", "options": {"A": "Busy market", "B": "Quiet street", "C": "School", "D": "Village"}, "answer": "B"},
    {"stem": "The mood of the prose passage is ______.", "options": {"A": "Joyful", "B": "Suspenseful", "C": "Romantic", "D": "Comic"}, "answer": "B"},
    {"stem": "'Silence was heavy' is ______.", "options": {"A": "Simile", "B": "Metaphor", "C": "Irony", "D": "Personification"}, "answer": "B"},
    {"stem": "Ade's emotion is mainly ______.", "options": {"A": "Happiness", "B": "Fear", "C": "Anger", "D": "Pride"}, "answer": "B"},
    {"stem": "The passage is written in ______.", "options": {"A": "First person", "B": "Second person", "C": "Third person", "D": "Dramatic form"}, "answer": "C"},
    {"stem": "The tone of the prose passage is ______.", "options": {"A": "Suspenseful", "B": "Humorous", "C": "Sarcastic", "D": "Joyful"}, "answer": "A"},
    {"stem": "'Creeping fear' suggests ______.", "options": {"A": "Sudden shock", "B": "Gradual anxiety", "C": "Excitement", "D": "Anger"}, "answer": "B"},
    {"stem": "The dog's cry contributes to ______.", "options": {"A": "Humor", "B": "Suspense", "C": "Celebration", "D": "Romance"}, "answer": "B"},
    {"stem": "Ade's situation can best be described as ______.", "options": {"A": "Peaceful", "B": "Threatening", "C": "Celebratory", "D": "Normal"}, "answer": "B"},
    {"stem": "The prose passage emphasizes ______.", "options": {"A": "Courage", "B": "Suspense", "C": "Wealth", "D": "Friendship"}, "answer": "B"},
    {"stem": "The setting of Antony and Cleopatra is mainly ______.", "options": {"A": "Greece and Persia", "B": "Rome and Egypt", "C": "England and France", "D": "Italy only"}, "answer": "B"},
    {"stem": "Antony is torn between ______.", "options": {"A": "Duty and love", "B": "War and peace", "C": "Wealth and poverty", "D": "Honor and shame"}, "answer": "A"},
    {"stem": "Cleopatra is portrayed as ______.", "options": {"A": "Weak and timid", "B": "Proud and manipulative", "C": "Silent", "D": "Passive"}, "answer": "B"},
    {"stem": "Octavius Caesar represents ______.", "options": {"A": "Passion", "B": "Discipline and order", "C": "Chaos", "D": "Romance"}, "answer": "B"},
    {"stem": "The play is mainly a ______.", "options": {"A": "Comedy", "B": "Farce", "C": "Tragedy", "D": "Satire"}, "answer": "C"},
    {"stem": "Antony's tragic flaw is ______.", "options": {"A": "Greed", "B": "Excessive love for Cleopatra", "C": "Pride only", "D": "Laziness"}, "answer": "B"},
    {"stem": "Cleopatra dies by ______.", "options": {"A": "Drowning", "B": "Hanging", "C": "Sword", "D": "Snake bite"}, "answer": "D"},
    {"stem": "The conflict between Rome and Egypt symbolizes ______.", "options": {"A": "Culture clash", "B": "Friendship", "C": "Unity", "D": "Peace"}, "answer": "A"},
    {"stem": "Enobarbus is ______.", "options": {"A": "a soldier loyal to Antony", "B": "a king", "C": "a servant", "D": "a spy"}, "answer": "A"},
    {"stem": "Antony's downfall is mainly due to ______.", "options": {"A": "fate only", "B": "his emotional decisions", "C": "war losses", "D": "betrayal only"}, "answer": "B"},
    {"stem": "The speaker of 'If it be love indeed, tell me how much' is ______.", "options": {"A": "Antony", "B": "Cleopatra", "C": "Enobarbus", "D": "Caesar"}, "answer": "B"},
    {"stem": "The immediate listener to the first speaker is ______.", "options": {"A": "Caesar", "B": "Enobarbus", "C": "Antony", "D": "Lepidus"}, "answer": "C"},
    {"stem": "The speaker of 'There's beggary in the love that can be reckon'd' is ______.", "options": {"A": "Caesar", "B": "Antony", "C": "Enobarbus", "D": "Messenger"}, "answer": "B"},
    {"stem": "The second speaker's statement implies that ______.", "options": {"A": "love can be measured", "B": "measured love is inferior", "C": "love is temporary", "D": "love is political"}, "answer": "B"},
    {"stem": "The speaker of 'I'll set a bourn how far to be belov'd' is ______.", "options": {"A": "Cleopatra", "B": "Antony", "C": "Octavius", "D": "Charmian"}, "answer": "A"},
    {"stem": "The listener to the final line 'Then must thou needs find out new heaven, new earth' is ______.", "options": {"A": "Caesar", "B": "Enobarbus", "C": "Cleopatra", "D": "Antony"}, "answer": "C"},
    {"stem": "The relationship between the speakers is best described as ______.", "options": {"A": "Political rivals", "B": "Romantic partners", "C": "Master and servant", "D": "Enemies"}, "answer": "B"},
    {"stem": "The first speaker's attitude toward love is that it should be ______.", "options": {"A": "Unlimited", "B": "Measurable", "C": "Ignored", "D": "Feared"}, "answer": "B"},
    {"stem": "The second speaker's attitude toward love is that it is ______.", "options": {"A": "Quantifiable", "B": "Boundless", "C": "Weak", "D": "Unreal"}, "answer": "B"},
    {"stem": "The phrase 'new heaven, new earth' suggests ______.", "options": {"A": "Political ambition", "B": "Endless expansion beyond limits", "C": "Religious devotion", "D": "War"}, "answer": "B"},
]

THEORY = [
    {"stem": "Section 1: African Prose: So The Path Does Not Die by Pede Hollist. Discuss in detail the love for African heritage in the novel. Or examine and discuss Finaba Cammy's aborted wedding in the novel.", "marks": Decimal("15.00")},
    {"stem": "Section 2: Non-African Prose: To Kill a Mockingbird. Give a detailed account of the novel To Kill a Mockingbird. Or examine the role of Scout Finch in the novel.", "marks": Decimal("15.00")},
    {"stem": "Section 3: African Drama: The Marriage of Anansewa by Efua T. Sutherland. Give a detailed account of the ceremony in the play. Or describe the character of Christie.", "marks": Decimal("15.00")},
    {"stem": "Section 4: Non-African Drama: An Inspector Calls by J. B. Priestley. Give an account of Eva Smith's dismissal at work. Or, with detailed explanation, discuss the role of class in the drama.", "marks": Decimal("15.00")},
    {"stem": "Section 5: African Poetry: Not My Business by Niyi Osundare. Examine the theme of oppression and injustice in the poem. Or highlight and discuss any four figurative expressions used in the poem.", "marks": Decimal("15.00")},
    {"stem": "Section 6: Non-African Poem: She Walks in Beauty by Lord Byron. Discuss the theme of beauty in the poem. Or examine the structure of the poem.", "marks": Decimal("15.00")},
]


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="LIT")
    academic_class = AcademicClass.objects.get(code="SS3")
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
            source_reference=f"SS3-LIT-20260324-OBJ-{index:02d}",
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
            source_reference=f"SS3-LIT-20260324-TH-{index:02d}",
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
        "paper_code": "SS3-LIT-EXAM",
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
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration": blueprint.duration_minutes,
        }
    )


main()
