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


TITLE = "TUE 1:30-2:30 JS2 French Second Term Exam"
DESCRIPTION = "JS2 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "JS2 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all theory questions in Section B. "
    "For questions 1 to 6, use Texte 1. For questions 7 to 11, use Texte 2. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:30 PM WAT on Tuesday, March 24, 2026."
)

TEXTE_1 = (
    "COMPREHENSION\n"
    "Read the passage below carefully and answer the questions that follow.\n\n"
    "TEXTE 1\n"
    "Je m'appelle Sophie et je vais a l'ecole chaque matin a 7h30.\n"
    "Hier, je suis allee au parc avec mes amis. Nous avons joue au football.\n"
    "Toute la journee avant aller a la maison pour se reposer.\n"
    "J'aime beaucoup le sport et je fais du tennis chaque week-end."
)

TEXTE_2 = (
    "COMPREHENSION\n"
    "Read the passage below carefully and answer the questions that follow.\n\n"
    "TEXTE 2\n"
    "Thomas est un eleve de JSS2. Il est passionne par l'informatique. "
    "Il reve de devenir docteur.\n"
    "Tous les jours, il passe deux heures a etudier les ordinateurs et a apprendre a coder. "
    "A l'ecole, il a de bonnes notes, surtout en francais et en anglais."
)


def with_texte_1(stem: str) -> str:
    return f"{TEXTE_1}\n\n{stem}"


def with_texte_2(stem: str) -> str:
    return f"{TEXTE_2}\n\n{stem}"


OBJECTIVES = [
    {"stem": with_texte_1("Sophie va a l'ecole a ______."), "options": {"A": "7h", "B": "7h30", "C": "8h", "D": "9h"}, "answer": "B"},
    {"stem": with_texte_1("Hier, Sophie ______ au parc."), "options": {"A": "va", "B": "est alle", "C": "est allee", "D": "allait"}, "answer": "C"},
    {"stem": with_texte_1("Sophie aime ______."), "options": {"A": "chanter", "B": "faire du sport", "C": "lire", "D": "dessiner"}, "answer": "B"},
    {"stem": with_texte_1("Sophie joue au ______ chaque week-end."), "options": {"A": "football", "B": "tennis", "C": "basket", "D": "volleyball"}, "answer": "B"},
    {"stem": with_texte_1("Elle va a ______ se reposer."), "options": {"A": "la maison", "B": "l'eglise", "C": "la mosquee", "D": "l'hopital"}, "answer": "A"},
    {"stem": with_texte_1("Sophie fait du sport ______."), "options": {"A": "tous les jours", "B": "chaque week-end", "C": "le soir", "D": "a l'ecole"}, "answer": "B"},
    {"stem": with_texte_2("Thomas est un eleve de ______."), "options": {"A": "JSS1", "B": "JSS2", "C": "JSS3", "D": "SS1"}, "answer": "B"},
    {"stem": with_texte_2("Thomas est passionne par ______."), "options": {"A": "les animaux", "B": "l'informatique", "C": "les voyages", "D": "les langues"}, "answer": "B"},
    {"stem": with_texte_2("Thomas reve de devenir ______."), "options": {"A": "professeur", "B": "medecin", "C": "docteur", "D": "ingenieur"}, "answer": "C"},
    {"stem": with_texte_2("Il etudie ______ chaque jour."), "options": {"A": "les langues", "B": "l'informatique", "C": "les sciences", "D": "les arts"}, "answer": "B"},
    {"stem": with_texte_2("Thomas est particulierement bon en ______."), "options": {"A": "anglais", "B": "sport", "C": "francais et anglais", "D": "histoire"}, "answer": "C"},
    {"stem": "___ livre est interessant.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "___ filles sont tres gentilles.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ garcon est tres intelligent.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "___ voiture est rouge.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ professeur est gentil.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "___ maison est grande.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ animaux sont gentils.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ film est tres interessant.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "___ livre preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ film as-tu vu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ matieres etudies-tu a l'ecole ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "___ est ton professeur de francais ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ travail fais-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "Il est ___ heures.", "options": {"A": "huit et demie", "B": "huit et demie", "C": "huit", "D": "huit et quart"}, "answer": "C"},
    {"stem": "A quelle heure commence l'ecole ?", "options": {"A": "A huit heures", "B": "A neuf heures", "C": "A sept heures", "D": "A six heures"}, "answer": "C"},
    {"stem": "Il est midi. Quelle heure est-ce ?", "options": {"A": "Douze heures", "B": "Onze heures", "C": "Dix heures", "D": "Trois heures"}, "answer": "A"},
    {"stem": "Quand j'etais jeune, je ___ souvent au parc.", "options": {"A": "joue", "B": "jouais", "C": "jouerai", "D": "ai joue"}, "answer": "B"},
    {"stem": "Hier, il ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "D"},
    {"stem": "Demain, nous ___ au marche.", "options": {"A": "allons", "B": "allions", "C": "irons", "D": "sommes alles"}, "answer": "C"},
    {"stem": "Elle ___ malade la semaine derniere.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "Elle boit ___ lait.", "options": {"A": "des", "B": "de la", "C": "de l'", "D": "du"}, "answer": "D"},
    {"stem": "Nous achetons ___ fruits.", "options": {"A": "des", "B": "de la", "C": "de l'", "D": "du"}, "answer": "A"},
    {"stem": "Ma mere travaille a l'hopital. Elle est ___ .", "options": {"A": "medecin", "B": "professeur", "C": "avocate", "D": "cuisiniere"}, "answer": "A"},
    {"stem": "Mon pere repare les voitures, il est ___ .", "options": {"A": "ingenieur", "B": "mecanicien", "C": "fermier", "D": "vendeur"}, "answer": "B"},
    {"stem": "Ma soeur tresse les cheveux, elle est ___ .", "options": {"A": "infirmiere", "B": "artiste", "C": "coiffeuse", "D": "architecte"}, "answer": "C"},
    {"stem": "Ma tante travaille a l'ecole, elle est ___ .", "options": {"A": "institutrice", "B": "coiffeuse", "C": "secretaire", "D": "comptable"}, "answer": "A"},
    {"stem": "Mon cousin travaille a la radio, il est ___ .", "options": {"A": "musicien", "B": "docteur", "C": "journaliste", "D": "conducteur"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Se presenter (introduce yourself in French). Write about 10 lines.", "marks": Decimal("20.00")},
    {
        "stem": (
            "2. Decrivez votre famille. Parlez de :\n"
            "- le nombre de personnes\n"
            "- leur profession\n"
            "- leurs qualites\n\n"
            "(Describe your family.)"
        ),
        "marks": Decimal("20.00"),
    },
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="JS2")
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
            source_reference=f"JS2-FRE-20260324-OBJ-{index:02d}",
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
            source_reference=f"JS2-FRE-20260324-TH-{index:02d}",
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
        "paper_code": "JS2-FRE-EXAM",
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
