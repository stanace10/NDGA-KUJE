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

TITLE = "MON 1:15-2:15 SS3 French Second Term Exam"
DESCRIPTION = "CLASS SS3 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "SS3 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all theory questions in Section B. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Paul est ___", "options": {"A": "professeur", "B": "eleve", "C": "commercant", "D": "medecin"}, "answer": "B"},
    {"stem": "2. Il habite a ___", "options": {"A": "Lagos", "B": "Abuja", "C": "Ibadan", "D": "Paris"}, "answer": "C"},
    {"stem": "3. Chaque matin, Paul ___ a l'ecole.", "options": {"A": "ira", "B": "allait", "C": "est alle", "D": "va"}, "answer": "D"},
    {"stem": "4. L'ecole etait ___ de sa maison.", "options": {"A": "loin", "B": "chere", "C": "pres", "D": "grande"}, "answer": "C"},
    {"stem": "5. Hier, Paul ___ un ami.", "options": {"A": "rencontre", "B": "rencontrait", "C": "rencontrera", "D": "a rencontre"}, "answer": "D"},
    {"stem": "6. Son ami etudie dans ___ ecole.", "options": {"A": "cette", "B": "ce", "C": "une autre", "D": "ces"}, "answer": "C"},
    {"stem": "7. Demain, Paul ___ a Lagos.", "options": {"A": "va", "B": "allait", "C": "est alle", "D": "ira"}, "answer": "D"},
    {"stem": "8. Il va visiter ___", "options": {"A": "son pere", "B": "son professeur", "C": "son oncle", "D": "son ami"}, "answer": "C"},
    {"stem": "9. Son oncle ___ a Lagos.", "options": {"A": "etudie", "B": "habite", "C": "travaille", "D": "joue"}, "answer": "C"},
    {"stem": "10. Paul aime le francais parce que ___", "options": {"A": "c'est facile", "B": "c'est interessant", "C": "c'est difficile", "D": "c'est cher"}, "answer": "B"},
    {"stem": "11. Quand j'etais jeune, je ___ souvent au parc.", "options": {"A": "joue", "B": "jouais", "C": "jouerai", "D": "ai joue"}, "answer": "B"},
    {"stem": "12. Hier, il ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "D"},
    {"stem": "13. Demain, nous ___ au marche.", "options": {"A": "allons", "B": "allions", "C": "irons", "D": "sommes alles"}, "answer": "C"},
    {"stem": "14. Elle ___ malade la semaine derniere.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "15. Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "16. Elle boit ___ lait.", "options": {"A": "des", "B": "de la", "C": "de l'", "D": "du"}, "answer": "D"},
    {"stem": "17. Nous achetons ___ fruits.", "options": {"A": "des", "B": "de la", "C": "de l'", "D": "du"}, "answer": "A"},
    {"stem": "18. Ma mere travaille a l'hopital. Elle est ___ .", "options": {"A": "medecin", "B": "professeur", "C": "avocate", "D": "cuisiniere"}, "answer": "A"},
    {"stem": "19. Mon pere repare les voitures, il est ___ .", "options": {"A": "ingenieur", "B": "mecanicien", "C": "fermier", "D": "vendeur"}, "answer": "B"},
    {"stem": "20. Ma soeur tresse les cheveux, elle est ___ .", "options": {"A": "infirmiere", "B": "artiste", "C": "coiffeuse", "D": "architecte"}, "answer": "C"},
    {"stem": "21. Ma tante travaille a l'ecole, elle est ___ .", "options": {"A": "institutrice", "B": "coiffeuse", "C": "secretaire", "D": "comptable"}, "answer": "A"},
    {"stem": "22. Mon cousin travaille a la radio, il est ___ .", "options": {"A": "musicien", "B": "docteur", "C": "journaliste", "D": "conducteur"}, "answer": "C"},
    {"stem": "23. Elle ___ malade la semaine passee.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "24. Quand il faisait chaud, ils ___ de l'eau.", "options": {"A": "boivent", "B": "buvaient", "C": "boiront", "D": "ont bu"}, "answer": "B"},
    {"stem": "25. Demain, tu ___ avec ton ami.", "options": {"A": "vois", "B": "voyais", "C": "seras", "D": "as vu"}, "answer": "C"},
    {"stem": "26. Hier, nous ___ en retard.", "options": {"A": "arrivons", "B": "arriver", "C": "arriverons", "D": "sommes arrives"}, "answer": "D"},
    {"stem": "27. Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "28. Elle boit ___ eau.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "29. Nous achetons ___ fruits.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "30. Il prend ___ pain.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "31. Je veux ___ viande.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
    {"stem": "32. Elle mange ___ ananas.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "33. Ils boivent ___ lait.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "34. Je parle francais.", "options": {"A": "Je ne parle francais", "B": "Je ne parle pas francais", "C": "Je ne parle francais pas", "D": "Je n'ai pas parle francais"}, "answer": "B"},
    {"stem": "35. Mon pere est docteur.", "options": {"A": "Mon pere n'est docteur pas", "B": "Mon pere n'est pas docteur", "C": "Mon pere n'ai pas docteur", "D": "Mon pere docteur n'est pas"}, "answer": "B"},
    {"stem": "36. Tu as un velo ? Non.", "options": {"A": "Elle n'a pas de velo", "B": "Tu n'as pas de velo", "C": "Je n'ai pas de velo", "D": "Il n'a pas de velo"}, "answer": "C"},
    {"stem": "37. C'est Marianne ___ fait le menage aujourd'hui.", "options": {"A": "Que", "B": "Qui", "C": "Quelle", "D": "Quel"}, "answer": "B"},
    {"stem": "38. Les eleves sont ___ village.", "options": {"A": "Au", "B": "aux", "C": "Dedans", "D": "Sur"}, "answer": "A"},
    {"stem": "39. A ___ heure vous allez au cinema ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "40. Tu preferes aller ___ ecole ?", "options": {"A": "a l'", "B": "a la", "C": "a le", "D": "aux"}, "answer": "A"},
    {"stem": "41. ___ jour tu vas au marche ?", "options": {"A": "Qui", "B": "Que", "C": "Quelle", "D": "Quel"}, "answer": "D"},
    {"stem": "42. Tu frequentes ___ ecole ?", "options": {"A": "Quelle", "B": "Quel", "C": "Que", "D": "Qui"}, "answer": "A"},
    {"stem": "43. ___ frere de Joseph aime ___ football.", "options": {"A": "Le/la", "B": "Le/l'", "C": "Un/une", "D": "Le/le"}, "answer": "D"},
    {"stem": "44. Chioma ecrit ___ lettre a Kekchi.", "options": {"A": "Le", "B": "Un", "C": "Une", "D": "Les"}, "answer": "C"},
    {"stem": "45. Regarde, j'ai ___ nouvelles chaussures.", "options": {"A": "Un", "B": "Les", "C": "La", "D": "Une"}, "answer": "B"},
    {"stem": "46. Qu'est-ce que tu achetes ? J'achete ___ stylo.", "options": {"A": "Un", "B": "Une", "C": "Les", "D": "La"}, "answer": "A"},
    {"stem": "47. J'aide ___ parents a la maison.", "options": {"A": "Ma", "B": "Mes", "C": "Ton", "D": "Sa"}, "answer": "B"},
    {"stem": "48. Aujourd'hui, je vais ___ Etats-Unis.", "options": {"A": "au", "B": "aux", "C": "en", "D": "les"}, "answer": "B"},
    {"stem": "49. Which of the following sentences uses demonstrative adjectives correctly?", "options": {"A": "Ces enfants sont sages.", "B": "Ce hommes sont gentils.", "C": "Cet livres sont interessants.", "D": "Cette chiens sont mignons."}, "answer": "A"},
    {"stem": "50. In which sentence is the interrogative adjective used incorrectly?", "options": {"A": "Quels est ton nom?", "B": "Quels films aimez-vous?", "C": "Quelle est la couleur de ta maison?", "D": "Quel film regardes-tu?"}, "answer": "A"},
    {"stem": "51. ___ fille", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "52. ___ enfants jouent dans le parc", "options": {"A": "Ces", "B": "Cette", "C": "Ce", "D": "Cet"}, "answer": "A"},
    {"stem": "53. Which sentence is using the imparfait form of 'avoir' correctly?", "options": {"A": "Nous avons une maison.", "B": "Nous avions une maison.", "C": "Nous aurons une maison.", "D": "Nous avons eu une maison."}, "answer": "B"},
    {"stem": "54. Il ___ un taxi", "options": {"A": "a", "B": "avaient", "C": "avait", "D": "avons"}, "answer": "A"},
    {"stem": "55. ___ pizza est delicieuse.", "options": {"A": "Ce", "B": "Ces", "C": "Cet", "D": "Cette"}, "answer": "D"},
    {"stem": "56. Ils ___ stylos rouge.", "options": {"A": "ont", "B": "a", "C": "avons", "D": "as"}, "answer": "A"},
    {"stem": "57. Which of the following is not a wild animal?", "options": {"A": "le lion", "B": "le singe", "C": "le chameau", "D": "le leopard"}, "answer": "C"},
    {"stem": "58. Tu ___ un chat.", "options": {"A": "as", "B": "a", "C": "avons", "D": "ont"}, "answer": "A"},
    {"stem": "59. Quelle est la capitale de la France ?", "options": {"A": "Londres", "B": "Berlin", "C": "Madrid", "D": "Paris"}, "answer": "D"},
    {"stem": "60. Le contraire de 'heureux' est :", "options": {"A": "Triste", "B": "Joyeux", "C": "Drole", "D": "Serieux"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. Mettez la phrase suivante a la voix passive: Notre gros chat noir devore une grosse souris grise.", "marks": Decimal("6.00")},
    {"stem": "2. Mettez la phrase suivante a la voix passive: Les villageois cultivent les vivres dans les champs.", "marks": Decimal("6.00")},
    {"stem": "3. Mettez la phrase suivante a la voix passive: Tout le monde aime le succes.", "marks": Decimal("6.00")},
    {"stem": "4. Mettez la phrase suivante a la voix passive: L'enfant finit son devoir.", "marks": Decimal("6.00")},
    {"stem": "5. Mettez la phrase suivante a la voix passive: Nous allumons un grand feu.", "marks": Decimal("6.00")},
    {"stem": "6. Ecris un court paragraphe sur ta famille ou ton meilleur ami.", "marks": Decimal("15.00")},
    {"stem": "7. Write a letter to your parents thanking them for paying your school fees in French language. Write about 12 lines.", "marks": Decimal("15.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
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
    schedule_start = datetime(2026, 3, 23, 13, 15, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 14, 15, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Monday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 1:15 PM WAT.",
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
    exam.dean_review_comment = "Approved for Monday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 1:15 PM WAT."
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
            source_reference=f"SS3-FRE-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS3-FRE-20260323-TH-{index:02d}",
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
        "paper_code": "SS3-FRE-EXAM",
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

    print({
        "created": created,
        "exam_id": exam.id,
        "title": exam.title,
        "status": exam.status,
        "schedule_start": exam.schedule_start.isoformat(),
        "schedule_end": exam.schedule_end.isoformat(),
        "duration_minutes": blueprint.duration_minutes,
        "objective_questions": len(OBJECTIVES),
        "theory_questions": len(THEORY),
    })

main()
