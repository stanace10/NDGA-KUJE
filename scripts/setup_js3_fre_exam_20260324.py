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


TITLE = "TUE 1:30-2:30 JS3 French Second Term Exam"
DESCRIPTION = "JS3 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "JS3 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all theory questions in Section B. "
    "For questions 1 to 6, use the first comprehension passage. For questions 7 to 11, use the second passage. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:30 PM WAT on Tuesday, March 24, 2026."
)

TEXTE_1 = (
    "COMPREHENSION\n"
    "Read the passage below carefully and answer the questions that follow.\n\n"
    "TEXTE: La salle de classe\n"
    "Le professeur arrive a sept heures et entre dans la salle de classe a sept heures et demie.\n"
    "Les eleves arrivent a l'ecole. Pierre, un eleve, arrive en retard.\n"
    "Il a mange son petit dejeuner a la maison.\n"
    "Il va a l'ecole a pied chaque matin."
)

TEXTE_2 = (
    "COMPREHENSION\n"
    "Read the passage below carefully and answer the questions that follow.\n\n"
    "TEXTE: La famille\n"
    "Marie et son frere, Jean, sont a l'ecole. Marie est une eleve studieuse.\n"
    "Jean est un eleve sportif. Ils sont contents d'aller a l'ecole tous les jours.\n"
    "Ils etudient bien, et ils aiment leurs enseignants."
)


def with_texte_1(stem: str) -> str:
    return f"{TEXTE_1}\n\n{stem}"


def with_texte_2(stem: str) -> str:
    return f"{TEXTE_2}\n\n{stem}"


OBJECTIVES = [
    {"stem": with_texte_1("Le professeur arrive a ___ ."), "options": {"A": "huit heures", "B": "sept heures", "C": "neuf heures", "D": "midi"}, "answer": "B"},
    {"stem": with_texte_1("Pierre ___ arrive en retard."), "options": {"A": "a", "B": "est", "C": "etaient", "D": "etait"}, "answer": "A"},
    {"stem": with_texte_1("Pierre mange ___ le matin."), "options": {"A": "a midi", "B": "le diner", "C": "le dejeuner", "D": "le petit dejeuner"}, "answer": "D"},
    {"stem": with_texte_1("Pierre ___ a l'ecole chaque matin."), "options": {"A": "marche", "B": "va", "C": "aller", "D": "est alle"}, "answer": "B"},
    {"stem": with_texte_1("Le professeur entre a ___ ."), "options": {"A": "sept heures et demie", "B": "neuf heures", "C": "huit heures", "D": "six heures"}, "answer": "A"},
    {"stem": with_texte_1("Les eleves arrivent a l'___ ."), "options": {"A": "park", "B": "universite", "C": "ecole", "D": "maison"}, "answer": "C"},
    {"stem": with_texte_2("Marie est ___ ."), "options": {"A": "sportive", "B": "studieuse", "C": "paresseuse", "D": "gentille"}, "answer": "B"},
    {"stem": with_texte_2("Jean est un eleve ___ ."), "options": {"A": "studieux", "B": "sportif", "C": "paresseux", "D": "gentil"}, "answer": "B"},
    {"stem": with_texte_2("Marie et Jean aiment ___ ."), "options": {"A": "la danse", "B": "l'ecole", "C": "les jeux video", "D": "la musique"}, "answer": "B"},
    {"stem": with_texte_2("Ils ___ bien a l'ecole."), "options": {"A": "mangent", "B": "etudient", "C": "jouent", "D": "chantent"}, "answer": "B"},
    {"stem": with_texte_2("Marie est ___ de ses enseignants."), "options": {"A": "amoureuse", "B": "triste", "C": "contente", "D": "fachee"}, "answer": "C"},
    {"stem": "___ livre est tres interessant.", "options": {"A": "Cette", "B": "Ce", "C": "Cet", "D": "Ces"}, "answer": "B"},
    {"stem": "___ enfants sont gentils.", "options": {"A": "Ce", "B": "Cette", "C": "Cet", "D": "Ces"}, "answer": "D"},
    {"stem": "___ garcon est mon frere.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "___ voiture est rouge.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ maisons sont grandes.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ fille parle francais.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ idee est tres bonne.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "___ amis sont toujours la pour moi.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ animal est ton prefere ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ couleur preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ garcon est mon ami.", "options": {"A": "Cette", "B": "Ces", "C": "Ce", "D": "Cet"}, "answer": "C"},
    {"stem": "___ ecole est grande.", "options": {"A": "Ce", "B": "Cette", "C": "Ces", "D": "Cet"}, "answer": "D"},
    {"stem": "___ livres sont sur la table.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ homme est professeur.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "___ maison est belle.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ eleves arrivent tot.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ voiture est rouge.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ livre est a toi ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ classe es-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ robe preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ matieres aimes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "___ ecole frequentes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ langues parles-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "___ cahier est nouveau ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "Je parle francais.", "options": {"A": "Je ne parle francais", "B": "Je ne parle pas francais", "C": "Je ne parle francais pas", "D": "Je n'ai pas parle francais"}, "answer": "B"},
    {"stem": "Mon pere est docteur.", "options": {"A": "Mon pere n'est docteur pas", "B": "Mon pere n'est pas docteur", "C": "Mon pere n'ai pas docteur", "D": "Mon pere docteur n'est pas"}, "answer": "B"},
    {"stem": "Tu as un velo ? Non.", "options": {"A": "Elle n'a pas de velo", "B": "Tu n'as pas de velo", "C": "Je n'ai pas de velo", "D": "Il n'a pas de velo"}, "answer": "C"},
    {"stem": "Nous ___ des stylos rouges.", "options": {"A": "avons", "B": "avez", "C": "ont", "D": "ai"}, "answer": "A"},
    {"stem": "Which of the following is an example of a domestic animal?", "options": {"A": "le lion", "B": "l'elephant", "C": "le chien", "D": "le tigre"}, "answer": "C"},
    {"stem": "Which sentence uses the present tense of the verb 'etre'?", "options": {"A": "Nous sommes etudiants.", "B": "Nous etions etudiants.", "C": "Vous serez etudiants.", "D": "Ils seront etudiants."}, "answer": "A"},
    {"stem": "Mon frere et moi ___ la vaisselle.", "options": {"A": "mange", "B": "manges", "C": "mangeons", "D": "mangerai"}, "answer": "C"},
    {"stem": "Which animal is an example of a wild animal?", "options": {"A": "le chien", "B": "le cheval", "C": "la panthere", "D": "la vache"}, "answer": "C"},
    {"stem": "Tu ___ la sieste.", "options": {"A": "fait", "B": "fais", "C": "faites", "D": "faisons"}, "answer": "B"},
    {"stem": "Hier, elle ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "D"},
    {"stem": "Quand il pleuvait, nous ___ a la maison.", "options": {"A": "restons", "B": "restions", "C": "resterons", "D": "sommes restes"}, "answer": "B"},
    {"stem": "La semaine prochaine, j'___ le francais.", "options": {"A": "etudiais", "B": "ai etudie", "C": "etudie", "D": "etudierai"}, "answer": "D"},
    {"stem": "Quand j'etais en SS1, je ___ tot.", "options": {"A": "me leve", "B": "me levais", "C": "me leverai", "D": "me suis leve"}, "answer": "B"},
    {"stem": "Nous ___ a Paris l'annee prochaine.", "options": {"A": "voyageons", "B": "voyagions", "C": "voyagerons", "D": "avons voyage"}, "answer": "C"},
    {"stem": "Elle ___ malade la semaine passee.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "Quand il faisait chaud, ils ___ de l'eau.", "options": {"A": "boivent", "B": "buvaient", "C": "boiront", "D": "ont bu"}, "answer": "B"},
    {"stem": "Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "Elle boit ___ eau.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "Nous achetons ___ fruits.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "Il prend ___ pain.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "Je veux ___ viande.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
    {"stem": "Elle mange ___ ananas.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "Ils boivent ___ lait.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "Nous prenons ___ huile.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "Elle mange ___ banane.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
]

THEORY = [
    {
        "stem": "1. Write a letter to your parents thanking them for paying your school fees in French language. Write about 12 lines.",
        "marks": Decimal("20.00"),
    },
    {
        "stem": "2. Introduce yourself in French language. Write about 10 lines.",
        "marks": Decimal("20.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="FRE")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="babem@ndgakuje.org",
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
    schedule_end = datetime(2026, 3, 24, 14, 30, tzinfo=lagos)

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
            source_reference=f"JS3-FRE-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS3-FRE-20260324-TH-{index:02d}",
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
        "paper_code": "JS3-FRE-EXAM",
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
            "schedule_start": exam.schedule_start.isoformat(),
            "schedule_end": exam.schedule_end.isoformat(),
            "duration_minutes": blueprint.duration_minutes,
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
        }
    )


main()
