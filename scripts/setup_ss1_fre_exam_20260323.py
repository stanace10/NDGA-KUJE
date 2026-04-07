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

TITLE = "MON 1:15-2:15 SS1 French Second Term Exam"
DESCRIPTION = "CLASS SS1 FRENCH SECOND TERM EXAMINATION"
BANK_NAME = "SS1 French Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all essay questions in Section B. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Marie est ___", "options": {"A": "professeur", "B": "eleve", "C": "medecin", "D": "commercante"}, "answer": "B"},
    {"stem": "2. Elle habite avec ___", "options": {"A": "ses amis", "B": "ses parents", "C": "son oncle", "D": "sa soeur"}, "answer": "B"},
    {"stem": "3. Chaque matin, elle ___ a l'ecole.", "options": {"A": "va", "B": "allait", "C": "ira", "D": "est allee"}, "answer": "A"},
    {"stem": "4. Hier, Marie ___ Anne.", "options": {"A": "rencontre", "B": "rencontrait", "C": "rencontrera", "D": "a rencontre"}, "answer": "D"},
    {"stem": "5. Marie aime ___", "options": {"A": "l'anglais", "B": "les maths", "C": "le francais", "D": "le sport"}, "answer": "C"},
    {"stem": "6. 'qui habite avec ses parents' est un ___", "options": {"A": "verbe", "B": "adjectif", "C": "pronom relatif", "D": "article"}, "answer": "C"},
    {"stem": "7. 'elle allait' est au ___", "options": {"A": "present", "B": "futur", "C": "imparfait", "D": "passe compose"}, "answer": "C"},
    {"stem": "8. 'Cette eleve' cette est un ___", "options": {"A": "pronom relatif", "B": "article partitif", "C": "adjectif demonstratif", "D": "verbe"}, "answer": "C"},
    {"stem": "9. '--------- langue aime Marie ?'", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "10. Paul est un ___", "options": {"A": "homme", "B": "professeur", "C": "garcon", "D": "medecin"}, "answer": "B"},
    {"stem": "11. Il aime ___", "options": {"A": "le pain", "B": "le riz et le poisson", "C": "le lait", "D": "les fruits"}, "answer": "B"},
    {"stem": "12. Hier, il ___ a la maison.", "options": {"A": "mange", "B": "mangeait", "C": "mangera", "D": "a mange"}, "answer": "A"},
    {"stem": "13. Demain, il ___ a l'ecole.", "options": {"A": "ira", "B": "allait", "C": "va", "D": "est alle"}, "answer": "C"},
    {"stem": "14. Paul est ___", "options": {"A": "paresseux", "B": "serieux", "C": "malade", "D": "absent"}, "answer": "B"},
    {"stem": "15. 'du riz' est un ___", "options": {"A": "adjectif", "B": "pronom", "C": "article partitif", "D": "verbe"}, "answer": "C"},
    {"stem": "16. ----------- garcon est beau", "options": {"A": "ce", "B": "cet", "C": "cette", "D": "ces"}, "answer": "A"},
    {"stem": "17. '------------ nourriture aime Paul ?'", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "18. 'Paul est un eleve ___ travaille bien.'", "options": {"A": "que", "B": "ou", "C": "qui", "D": "dont"}, "answer": "B"},
    {"stem": "19. ___ hospital est jolie", "options": {"A": "Cette", "B": "Ces", "C": "Ce", "D": "Cet"}, "answer": "D"},
    {"stem": "20. ___ ecole est grande.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "21. ___ livres sont sur la table.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "22. ___ homme est professeur.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "23. ___ maison est belle.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "24. ___ eleves arrivent tot.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "25. ___ voiture est rouge.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "26. ___ livre est a toi ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "27. ___ classe es-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "28. ___ robe preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "29. ___ matieres aimes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "30. ___ ecole frequentes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "31. ___ langues parles-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "32. ___ cahier est nouveau ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "33. Le garcon ___ parles-tu est mon frere.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "D"},
    {"stem": "34. Le livre ___ j'aime est bleu.", "options": {"A": "qui", "B": "ou", "C": "que", "D": "dont"}, "answer": "B"},
    {"stem": "35. Voici la maison ___ je vis.", "options": {"A": "qui", "B": "que", "C": "ou", "D": "dont"}, "answer": "C"},
    {"stem": "36. L'eleve ___ arrive est en SS1.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "B"},
    {"stem": "37. Quand j'etais petit, j ___ le francais.", "options": {"A": "aime", "B": "aimais", "C": "aimerai", "D": "ai aime"}, "answer": "A"},
    {"stem": "38. Hier, il ___ a l'ecole.", "options": {"A": "va", "B": "allait", "C": "ira", "D": "est alle"}, "answer": "C"},
    {"stem": "39. Hier, elle ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "B"},
    {"stem": "40. Quand il pleuvait, nous ___ a la maison.", "options": {"A": "restons", "B": "restions", "C": "resterons", "D": "sommes restes"}, "answer": "B"},
    {"stem": "41. La semaine prochaine, j'___ le francais.", "options": {"A": "etudiais", "B": "ai etudie", "C": "etudie", "D": "etudierai"}, "answer": "C"},
    {"stem": "42. Quand j'etais en SS1, je ___ tot.", "options": {"A": "me leve", "B": "me levais", "C": "me leverai", "D": "me suis leve"}, "answer": "B"},
    {"stem": "43. Nous ___ a Paris l'annee prochaine.", "options": {"A": "voyageons", "B": "voyagions", "C": "voyagerons", "D": "avons voyage"}, "answer": "B"},
    {"stem": "44. Elle ___ malade la semaine passee.", "options": {"A": "est", "B": "etait", "C": "sera", "D": "a ete"}, "answer": "B"},
    {"stem": "45. Quand il faisait chaud, ils ___ de l'eau.", "options": {"A": "boivent", "B": "buvaient", "C": "boiront", "D": "ont bu"}, "answer": "B"},
    {"stem": "46. Je mange ___ riz.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "47. Elle boit ___ eau.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "48. Nous achetons ___ fruits.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "49. Il prend ___ pain.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "50. Je veux ___ viande.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
    {"stem": "51. Elle mange ___ Ananas", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "D"},
    {"stem": "52. Ils boivent ___ lait.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "A"},
    {"stem": "53. Nous prenons ___ huile.", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "C"},
    {"stem": "54. Elle mange ___ banane", "options": {"A": "du", "B": "de la", "C": "de l'", "D": "des"}, "answer": "B"},
    {"stem": "55. Je parle francais", "options": {"A": "Je ne parle francais", "B": "Je ne parle pas francais", "C": "Je ne parle francais pas", "D": "Je n'ai pas parle francais"}, "answer": "B"},
    {"stem": "56. Mon pere est docteur", "options": {"A": "Mon pere n'est docteur pas", "B": "Mon pere n'est pas docteur", "C": "Mon pere n'ai pas docteur", "D": "Mon pere docteur n'est pas"}, "answer": "B"},
    {"stem": "57. Tu as un velo ? Non", "options": {"A": "Elle n'a pas de velo", "B": "Tu n'as pas de velo", "C": "Je n'ai pas de velo", "D": "Il n'a pas de velo"}, "answer": "C"},
    {"stem": "58. Je parle Anglais", "options": {"A": "Je ne parle anglais", "B": "Je ne parle pas anglais", "C": "Je ne parle anglais pas", "D": "Je n'ai pas parle anglais"}, "answer": "B"},
    {"stem": "59. Mon pere est policier", "options": {"A": "Mon pere n'est policier pas", "B": "Mon pere n'est pas policier", "C": "Mon pere n'ai pas policier", "D": "Mon pere policier n'est pas"}, "answer": "B"},
    {"stem": "60. Tu as un taxi ? Non", "options": {"A": "Elle n'a pas de taxi", "B": "Tu n'as pas de taxi", "C": "Je n'ai pas de taxi", "D": "Il n'a pas de taxi"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Write a letter to your parents thanking them for paying your school fees in French language. Write about 12 lines.", "marks": Decimal("20.00")},
    {"stem": "2. Introduce yourself in French language. Write about 10 lines.", "marks": Decimal("20.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
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
            source_reference=f"SS1-FRE-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS1-FRE-20260323-TH-{index:02d}",
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
        "paper_code": "SS1-FRE-EXAM",
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
