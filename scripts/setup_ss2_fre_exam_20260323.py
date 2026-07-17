# -*- coding: utf-8 -*-
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

TITLE = "MON 1:15-2:15 SS2 French Second Term Exam"
DESCRIPTION = "CLASS SS2 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "SS2 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all essay questions in Section B. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Paul est ___", "options": {"A": "professeur", "B": "eleve", "C": "commercant", "D": "medecin"}, "answer": "B"},
    {"stem": "2. Il habite a ___", "options": {"A": "Lagos", "B": "Abuja", "C": "Ibadan", "D": "Paris"}, "answer": "A"},
    {"stem": "3. Chaque matin, Paul ___ a l'ecole.", "options": {"A": "ira", "B": "allait", "C": "est alle", "D": "va"}, "answer": "D"},
    {"stem": "4. L'ecole etait ___ de sa maison.", "options": {"A": "loin", "B": "chere", "C": "pres", "D": "grande"}, "answer": "C"},
    {"stem": "5. Hier, Paul ___ un ami.", "options": {"A": "rencontre", "B": "rencontrait", "C": "rencontrera", "D": "a rencontre"}, "answer": "D"},
    {"stem": "6. Son ami etudie dans ___ ecole.", "options": {"A": "cette", "B": "ce", "C": "une autre", "D": "ces"}, "answer": "C"},
    {"stem": "7. Demain, Paul ___ a Lagos.", "options": {"A": "va", "B": "allait", "C": "est alle", "D": "ira"}, "answer": "D"},
    {"stem": "8. Il va visiter ___", "options": {"A": "son pere", "B": "son professeur", "C": "son oncle", "D": "son ami"}, "answer": "C"},
    {"stem": "9. Son oncle ___ a Lagos.", "options": {"A": "etudie", "B": "habite", "C": "travaille", "D": "joue"}, "answer": "C"},
    {"stem": "10. Paul aime le francais parce que ___", "options": {"A": "c'est facile", "B": "c'est interessant", "C": "c'est difficile", "D": "c'est cher"}, "answer": "B"},
    {"stem": "11. 'qui travaille la-bas' qui est un ___", "options": {"A": "adjectif", "B": "verbe", "C": "pronom relatif", "D": "article"}, "answer": "C"},
    {"stem": "12. 'Il allait a l'ecole' est au ___", "options": {"A": "present", "B": "futur", "C": "imparfait", "D": "passe compose"}, "answer": "C"},
    {"stem": "13. 'Il a rencontre' est au ___", "options": {"A": "present", "B": "futur", "C": "imparfait", "D": "passe compose"}, "answer": "D"},
    {"stem": "14. 'Quelle langue aime Paul ?'", "options": {"A": "anglais", "B": "Francais", "C": "Igbo", "D": "Espagnol"}, "answer": "B"},
    {"stem": "15. '___ langue est interessante ?'", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "16. 'Cette langue' est un ___", "options": {"A": "article partitif", "B": "pronom relatif", "C": "adjectif demonstratif", "D": "verbe"}, "answer": "C"},
    {"stem": "17. ___ garcon est tres poli.", "options": {"A": "Cette", "B": "Ces", "C": "Ce", "D": "Cet"}, "answer": "C"},
    {"stem": "18. ___ ecole est loin d'ici.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "19. ___ eleves sont en classe.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "20. ___ homme est mon pere.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "21. ___ voiture est nouvelle.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "22. ___ arbres sont verts.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "23. ___ ami arrive demain.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "A"},
    {"stem": "24. ___ maison appartient a Paul.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "25. ___ livre lis-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "26. ___ classe est la tienne ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "27. ___ eleves sont absents aujourd'hui ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "C"},
    {"stem": "28. ___ robe preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "29. ___ matieres etudies-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "30. ___ professeur enseigne le francais ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "31. ___ langues parlez-vous ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "32. ___ ecole frequentes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "33. Le garcon ___ parle est mon frere.", "options": {"A": "que", "B": "qui", "C": "dont", "D": "ou"}, "answer": "B"},
    {"stem": "34. Le livre ___ j'ai achete est interessant.", "options": {"A": "qui", "B": "ou", "C": "que", "D": "dont"}, "answer": "C"},
    {"stem": "35. La ville ___ je suis ne est Lagos.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "C"},
    {"stem": "36. L'eleve ___ le pere est malade est absent.", "options": {"A": "qui", "B": "que", "C": "ou", "D": "dont"}, "answer": "B"},
    {"stem": "37. Voici la femme ___ travaille ici.", "options": {"A": "que", "B": "dont", "C": "qui", "D": "ou"}, "answer": "C"},
    {"stem": "38. Le film ___ nous regardons est drole.", "options": {"A": "qui", "B": "que", "C": "dont", "D": "ou"}, "answer": "B"},
    {"stem": "39. C'est l'ecole ___ j'etudie.", "options": {"A": "qui", "B": "que", "C": "ou", "D": "dont"}, "answer": "C"},
    {"stem": "40. Le professeur ___ je parle est gentil.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "A"},
    {"stem": "41. Quand j'etais petit, je ___ au football.", "options": {"A": "joue", "B": "jouais", "C": "jouerai", "D": "ai joue"}, "answer": "B"},
    {"stem": "42. Demain, nous ___ a l'ecole.", "options": {"A": "allons", "B": "allions", "C": "irons", "D": "sommes alles"}, "answer": "C"},
    {"stem": "43. Hier, elle ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "B"},
    {"stem": "44. Quand il pleuvait, nous ___ a la maison.", "options": {"A": "restons", "B": "restions", "C": "resterons", "D": "sommes restes"}, "answer": "B"},
    {"stem": "45. La semaine prochaine, j'___ le francais.", "options": {"A": "etudiais", "B": "ai etudie", "C": "etudie", "D": "etudierai"}, "answer": "C"},
    {"stem": "46. Ils ___ le match hier soir.", "options": {"A": "regardent", "B": "regardaient", "C": "regarderont", "D": "ont regarde"}, "answer": "B"},
    {"stem": "47. Quand j'etais en SS1, je ___ tot.", "options": {"A": "me leve", "B": "me levais", "C": "me leverai", "D": "me suis leve"}, "answer": "B"},
    {"stem": "48. Nous ___ a Paris l'annee prochaine.", "options": {"A": "voyageons", "B": "voyagions", "C": "voyagerons", "D": "avons voyage"}, "answer": "C"},
    {"stem": "49. Elle ___ malade la semaine passee.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "50. Quand il faisait chaud, ils ___ de l'eau.", "options": {"A": "boivent", "B": "buvaient", "C": "boiront", "D": "ont bu"}, "answer": "B"},
    {"stem": "51. Demain, tu ___ avec ton ami.", "options": {"A": "vois", "B": "voyais", "C": "serais", "D": "as vu"}, "answer": "C"},
    {"stem": "52. Hier, nous ___ en retard.", "options": {"A": "arrivons", "B": "arriver", "C": "arriverons", "D": "sommes arrives"}, "answer": "D"},
    {"stem": "53. Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "54. Elle boit ___ eau.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "55. Nous achetons ___ fruits.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "56. Il prend ___ pain.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "57. Je veux ___ viande.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
    {"stem": "58. Elle mange ___ Ananas", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "59. Ils boivent ___ lait.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "60. Nous prenons ___ huile.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Decrivez votre famille. Parlez de: le nombre de personnes, leur profession, leurs qualites.", "marks": Decimal("20.00")},
    {"stem": "2. Write a letter to your parents thanking them for paying your school fees in French language. Write about 12 lines.", "marks": Decimal("20.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
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
            source_reference=f"SS2-FRE-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS2-FRE-20260323-TH-{index:02d}",
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
        "paper_code": "SS2-FRE-EXAM",
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
