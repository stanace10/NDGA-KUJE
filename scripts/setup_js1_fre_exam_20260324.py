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


TITLE = "TUE 1:30-2:30 JS1 French Second Term Exam"
DESCRIPTION = "JS1 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "JS1 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all theory questions in Section B. "
    "For questions 1 to 10, read the comprehension passage shown with each question. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:30 PM WAT on Tuesday, March 24, 2026."
)

COMPREHENSION_PASSAGE = (
    "COMPREHENSION\n"
    "Read the passage below carefully and answer the questions that follow.\n\n"
    "Texte se presenter\n"
    "Je m'appelle Esther Jonathan. Je suis une fille, j'ai dix ans.\n"
    "J'ai le teint clair, je parle francais et l'anglais.\n"
    "J'habite a Lagos et je frequente le college Saint Louis.\n"
    "Je suis en classe de JSS1 et j'ai la figure ronde et le nez fin.\n"
    "Je suis grande et grosse.\n"
    "Mes yeux sont petits et marron.\n"
    "J'ai les cheveux noirs, les dents blanches et je m'aime parce que je suis belle."
)


def with_passage(stem: str) -> str:
    return f"{COMPREHENSION_PASSAGE}\n\n{stem}"


OBJECTIVES = [
    {
        "stem": with_passage("Le narrateur s'appelle ______."),
        "options": {"A": "Marie Louise", "B": "Esther Jonathan", "C": "Esther Josephine", "D": "Esther Francoise"},
        "answer": "B",
    },
    {
        "stem": with_passage("Elle est une ______."),
        "options": {"A": "fillette", "B": "fille", "C": "filson", "D": "femme"},
        "answer": "B",
    },
    {
        "stem": with_passage("Elle a ______ ans."),
        "options": {"A": "dix", "B": "onze", "C": "neuf", "D": "sept"},
        "answer": "A",
    },
    {
        "stem": with_passage("Elle a le teint ______."),
        "options": {"A": "noir", "B": "rouge", "C": "blanc", "D": "clair"},
        "answer": "D",
    },
    {
        "stem": with_passage("Sa figure est ______."),
        "options": {"A": "ronde", "B": "verte", "C": "jaune", "D": "marron"},
        "answer": "A",
    },
    {
        "stem": with_passage("Elle est grande et ______."),
        "options": {"A": "petite", "B": "grosse", "C": "jeans", "D": "courte"},
        "answer": "B",
    },
    {
        "stem": with_passage("Ses yeux sont petits et ______."),
        "options": {"A": "verts", "B": "marron", "C": "jaunes", "D": "rouges"},
        "answer": "B",
    },
    {
        "stem": with_passage("Elle est une belle ______."),
        "options": {"A": "fille", "B": "garcon", "C": "jolie", "D": "filson"},
        "answer": "A",
    },
    {
        "stem": with_passage("Ses cheveux sont ______."),
        "options": {"A": "jaunes", "B": "noirs", "C": "verts", "D": "marron"},
        "answer": "B",
    },
    {
        "stem": with_passage("Ses dents sont ______."),
        "options": {"A": "jaunes", "B": "blanches", "C": "noires", "D": "bleues"},
        "answer": "B",
    },
    {"stem": "Comment dit-on car en francais ?", "options": {"A": "Le bus", "B": "La voiture", "C": "Le train", "D": "Le velo"}, "answer": "B"},
    {"stem": "Le moyen de transport sur l'eau est :", "options": {"A": "L'avion", "B": "Le bateau", "C": "Le bus", "D": "Le velo"}, "answer": "B"},
    {"stem": "Je vais a l'ecole en ______.", "options": {"A": "bateau", "B": "avion", "C": "velo", "D": "bateau"}, "answer": "C"},
    {"stem": "L'avion voyage dans :", "options": {"A": "la route", "B": "la mer", "C": "le ciel", "D": "la maison"}, "answer": "C"},
    {"stem": "Le train voyage sur :", "options": {"A": "les rails", "B": "la route", "C": "la mer", "D": "l'air"}, "answer": "A"},
    {"stem": "Comment dit-on bicycle en francais ?", "options": {"A": "Le bus", "B": "La moto", "C": "Le velo", "D": "Le train"}, "answer": "C"},
    {"stem": "Le bus transporte :", "options": {"A": "une personne", "B": "beaucoup de personnes", "C": "les animaux", "D": "les maisons"}, "answer": "B"},
    {"stem": "Je vais au village en ______.", "options": {"A": "train", "B": "radio", "C": "telephone", "D": "voiture"}, "answer": "D"},
    {"stem": "La moto est un moyen de transport :", "options": {"A": "aerien", "B": "maritime", "C": "terrestre", "D": "spatial"}, "answer": "C"},
    {"stem": "Le bateau est utilise sur :", "options": {"A": "la terre", "B": "la route", "C": "la maison", "D": "la mer"}, "answer": "D"},
    {"stem": "Comment dit-on road en francais ?", "options": {"A": "la mer", "B": "la route", "C": "la maison", "D": "l'ecole"}, "answer": "B"},
    {"stem": "Le velo a ______ roues.", "options": {"A": "trois", "B": "quatre", "C": "deux", "D": "cinq"}, "answer": "C"},
    {"stem": "Le transport le plus rapide est :", "options": {"A": "le velo", "B": "le bus", "C": "l'avion", "D": "la moto"}, "answer": "C"},
    {"stem": "Je prends le bus pour aller a ______.", "options": {"A": "parler", "B": "l'ecole", "C": "habiter", "D": "famille"}, "answer": "B"},
    {"stem": "Le transport terrestre est :", "options": {"A": "l'avion", "B": "le bateau", "C": "la voiture", "D": "la radio"}, "answer": "C"},
    {"stem": "Comment dit-on telephone en francais ?", "options": {"A": "La radio", "B": "Le telephone", "C": "La television", "D": "La lettre"}, "answer": "B"},
    {"stem": "La radio sert a :", "options": {"A": "voyager", "B": "parler", "C": "ecouter", "D": "ecrire"}, "answer": "C"},
    {"stem": "On ecrit une ______ pour communiquer.", "options": {"A": "voiture", "B": "lettre", "C": "moto", "D": "maison"}, "answer": "B"},
    {"stem": "La television sert a :", "options": {"A": "parler", "B": "danser", "C": "ecrire", "D": "regarder"}, "answer": "D"},
    {"stem": "Le telephone sert a :", "options": {"A": "ecouter la musique", "B": "parler avec quelqu'un", "C": "ecrire une lettre", "D": "voyager"}, "answer": "B"},
    {"stem": "Comment dit-on father en francais ?", "options": {"A": "la mere", "B": "le frere", "C": "le pere", "D": "l'oncle"}, "answer": "C"},
    {"stem": "La mere et le pere sont les :", "options": {"A": "enfants", "B": "amies", "C": "cousins", "D": "parents"}, "answer": "D"},
    {"stem": "Mon frere est le fils de :", "options": {"A": "ma soeur", "B": "mes parents", "C": "mon oncle", "D": "mon ami"}, "answer": "B"},
    {"stem": "Comment dit-on sister en francais ?", "options": {"A": "frere", "B": "soeur", "C": "tante", "D": "mere"}, "answer": "B"},
    {"stem": "La famille vit dans une :", "options": {"A": "ecole", "B": "voiture", "C": "maison", "D": "radio"}, "answer": "C"},
    {"stem": "Mon oncle est le frere de :", "options": {"A": "mon pere", "B": "mon ami", "C": "mon frere", "D": "mon fils"}, "answer": "A"},
    {"stem": "Les parents aiment leurs :", "options": {"A": "voisins", "B": "enfants", "C": "professeurs", "D": "amis"}, "answer": "B"},
    {"stem": "J'______ a Lagos.", "options": {"A": "habite", "B": "habites", "C": "habitons", "D": "habitez"}, "answer": "A"},
    {"stem": "Nous ______ francais.", "options": {"A": "parle", "B": "parles", "C": "parlons", "D": "parlez"}, "answer": "C"},
    {"stem": "Il ______ anglais a l'ecole.", "options": {"A": "parlent", "B": "parle", "C": "parles", "D": "parler"}, "answer": "B"},
]

THEORY = [
    {
        "stem": "1. Introduce yourself in French. Write about 10 lines.",
        "marks": Decimal("20.00"),
    },
    {
        "stem": (
            "2. Translate into French:\n"
            "a. My father is rich.\n"
            "b. My mother is in the village with my father.\n"
            "c. My sister is going to the market.\n"
            "d. I go to school with my brother.\n"
            "e. My uncle is a doctor."
        ),
        "marks": Decimal("20.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS1")
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
            source_reference=f"JS1-FRE-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS1-FRE-20260324-TH-{index:02d}",
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
        "paper_code": "JS1-FRE-EXAM",
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
