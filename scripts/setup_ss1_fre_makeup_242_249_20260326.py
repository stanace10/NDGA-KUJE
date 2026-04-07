# -*- coding: utf-8 -*-
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Subject, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTAttemptStatus,
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamAttempt,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)

TITLE = "THU 11:30-12:30 SS1 French Make-Up Exam"
DESCRIPTION = "CLASS SS1 FRENCH SECOND TERM MAKE-UP EXAMINATION"
BANK_NAME = "SS1 French Make-Up Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all essay questions in Section B. "
    "Timer is 30 minutes. Exam window closes at 12:30 PM WAT on Thursday, March 26, 2026."
)
TARGET_STUDENT_NUMBERS = {"NDGAK/22/242", "NDGAK/22/249"}
TEXT_1 = (
    "Texte 1: Le depart pour l'ecole\n"
    "Marie est un eleve de SS1.\n"
    "Elle habite a Lagos avec ses parents.\n"
    "Chaque matin, elle allait a l'ecole a pied.\n"
    "Hier, elle a rencontre son amie Anne.\n"
    "Marie aime le francais."
)
TEXT_2 = (
    "Texte 2\n"
    "Paul est un garcon intelligent, il va a l'ecole pour etudier.\n"
    "Il mange le riz et le poisson chaque jour car il aime.\n"
    "Hier, il a mange a la maison avant de partir a l'ecole.\n"
    "Demain, il ira a l'ecole pour etudier.\n"
    "Paul est un eleve serieux et intelligente."
)

OBJECTIVES = [
    {"stem": "Marie est ___", "options": {"A": "professeur", "B": "eleve", "C": "medecin", "D": "commercante"}, "answer": "B", "context": TEXT_1},
    {"stem": "Elle habite avec ___", "options": {"A": "ses amis", "B": "ses parents", "C": "son oncle", "D": "sa soeur"}, "answer": "B", "context": TEXT_1},
    {"stem": "Chaque matin, elle ___ a l'ecole.", "options": {"A": "va", "B": "allait", "C": "ira", "D": "est allee"}, "answer": "A", "context": TEXT_1},
    {"stem": "Hier, Marie ___ Anne.", "options": {"A": "rencontre", "B": "rencontrait", "C": "rencontrera", "D": "a rencontre"}, "answer": "D", "context": TEXT_1},
    {"stem": "Marie aime ___", "options": {"A": "l'anglais", "B": "les maths", "C": "le francais", "D": "le sport"}, "answer": "C", "context": TEXT_1},
    {"stem": "\"qui habite avec ses parents\" est un ___", "options": {"A": "verbe", "B": "adjectif", "C": "pronom relatif", "D": "article"}, "answer": "C", "context": TEXT_1},
    {"stem": "\"elle allait\" est au ___", "options": {"A": "present", "B": "futur", "C": "imparfait", "D": "passe compose"}, "answer": "C", "context": TEXT_1},
    {"stem": "\"Cette eleve\" cette est un ___", "options": {"A": "pronom relatif", "B": "article partitif", "C": "adjectif demonstratif", "D": "verbe"}, "answer": "C", "context": TEXT_1},
    {"stem": "\"--------- langue aime Marie ?\"", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B", "context": TEXT_1},
    {"stem": "Paul est un ___", "options": {"A": "homme", "B": "professeur", "C": "garcon", "D": "medecin"}, "answer": "B", "context": TEXT_2},
    {"stem": "Il aime ___", "options": {"A": "le pain", "B": "le riz et le poisson", "C": "le lait", "D": "les fruits"}, "answer": "B", "context": TEXT_2},
    {"stem": "Hier, il ___ a la maison.", "options": {"A": "mange", "B": "mangeait", "C": "mangera", "D": "a mange"}, "answer": "A", "context": TEXT_2},
    {"stem": "Demain, il ___ a l'ecole.", "options": {"A": "ira", "B": "allait", "C": "va", "D": "est alle"}, "answer": "C", "context": TEXT_2},
    {"stem": "Paul est ___", "options": {"A": "paresseux", "B": "serieux", "C": "malade", "D": "absent"}, "answer": "B", "context": TEXT_2},
    {"stem": "\"du riz\" est un ___", "options": {"A": "adjectif", "B": "pronom", "C": "article partitif", "D": "verbe"}, "answer": "C", "context": TEXT_2},
    {"stem": "----------- garcon est beau", "options": {"A": "ce", "B": "cet", "C": "cette", "D": "ces"}, "answer": "A", "context": TEXT_2},
    {"stem": "\"------------ nourriture aime Paul ?\"", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B", "context": TEXT_2},
    {"stem": "\"Paul est un eleve ___ travaille bien.\"", "options": {"A": "que", "B": "ou", "C": "qui", "D": "dont"}, "answer": "C", "context": TEXT_2},
    {"stem": "___ hospital est jolie", "options": {"A": "Cette", "B": "Ces", "C": "Ce", "D": "Cet"}, "answer": "D"},
    {"stem": "___ ecole est grande.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "___ livres sont sur la table.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ homme est professeur.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "B"},
    {"stem": "___ maison est belle.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ eleves arrivent tot.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "D"},
    {"stem": "___ voiture est rouge.", "options": {"A": "Ce", "B": "Cet", "C": "Cette", "D": "Ces"}, "answer": "C"},
    {"stem": "___ livre est a toi ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ classe es-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ robe preferes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ matieres aimes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "D"},
    {"stem": "___ ecole frequentes-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "___ langues parles-tu ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "B"},
    {"stem": "___ cahier est nouveau ?", "options": {"A": "Quel", "B": "Quelle", "C": "Quels", "D": "Quelles"}, "answer": "A"},
    {"stem": "Le garcon ___ parles-tu est mon frere.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "D"},
    {"stem": "Le livre ___ j'aime est bleu.", "options": {"A": "qui", "B": "ou", "C": "que", "D": "dont"}, "answer": "C"},
    {"stem": "Voici la maison ___ je vis.", "options": {"A": "qui", "B": "que", "C": "ou", "D": "dont"}, "answer": "C"},
    {"stem": "L'eleve ___ arrive est en SS1.", "options": {"A": "que", "B": "qui", "C": "ou", "D": "dont"}, "answer": "B"},
    {"stem": "Quand j'etais petit, j ___ le francais.", "options": {"A": "aime", "B": "aimais", "C": "aimerai", "D": "ai aime"}, "answer": "A"},
    {"stem": "Hier, il ___ a l'ecole.", "options": {"A": "va", "B": "allait", "C": "ira", "D": "est alle"}, "answer": "C"},
    {"stem": "Hier, elle ___ ses devoirs.", "options": {"A": "fait", "B": "faisait", "C": "fera", "D": "a fait"}, "answer": "B"},
    {"stem": "Quand il pleuvait, nous ___ a la maison.", "options": {"A": "restons", "B": "restions", "C": "resterons", "D": "sommes restes"}, "answer": "B"},
    {"stem": "La semaine prochaine, j'___ le francais.", "options": {"A": "etudiais", "B": "ai etudie", "C": "etudie", "D": "etudierai"}, "answer": "C"},
    {"stem": "Quand j'etais en SS1, je ___ tot.", "options": {"A": "me leve", "B": "me levais", "C": "me leverai", "D": "me suis leve"}, "answer": "B"},
    {"stem": "Nous ___ a Paris l'annee prochaine.", "options": {"A": "voyageons", "B": "voyagions", "C": "voyagerons", "D": "avons voyage"}, "answer": "B"},
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
    {"stem": "Je parle francais.", "options": {"A": "Je ne parle francais", "B": "Je ne parle pas francais", "C": "Je ne parle francais pas", "D": "Je n'ai pas parle francais"}, "answer": "B"},
    {"stem": "Mon pere est docteur.", "options": {"A": "Mon pere n'est docteur pas", "B": "Mon pere n'est pas docteur", "C": "Mon pere n'ai pas docteur", "D": "Mon pere docteur n'est pas"}, "answer": "B"},
    {"stem": "Tu as un velo ? Non", "options": {"A": "Elle n'a pas de velo", "B": "Tu n'as pas de velo", "C": "Je n'ai pas de velo", "D": "Il n'a pas de velo"}, "answer": "C"},
    {"stem": "Je parle anglais.", "options": {"A": "Je ne parle anglais", "B": "Je ne parle pas anglais", "C": "Je ne parle anglais pas", "D": "Je n'ai pas parle anglais"}, "answer": "B"},
    {"stem": "Mon pere est policier.", "options": {"A": "Mon pere n'est policier pas", "B": "Mon pere n'est pas policier", "C": "Mon pere n'ai pas policier", "D": "Mon pere policier n'est pas"}, "answer": "B"},
    {"stem": "Tu as un taxi ? Non", "options": {"A": "Elle n'a pas de taxi", "B": "Tu n'as pas de taxi", "C": "Je n'ai pas de taxi", "D": "Il n'a pas de taxi"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Write a letter to your parents thanking them for paying your school fee in French language. Write 12 lines.", "marks": Decimal("20.00")},
    {"stem": "2. Introduce yourself in French language. Write 10 lines.", "marks": Decimal("20.00")},
]


def _render_stem(item):
    context = item.get("context")
    if not context:
        return item["stem"]
    return f"{context}\n\n{item['stem']}"


def _render_rich_stem(item):
    context = item.get("context")
    if not context:
        return item["stem"]
    context_html = "<br>".join(context.splitlines())
    return f"<strong>{context_html}</strong><br><br>{item['stem']}"


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
    target_students = list(User.objects.filter(student_profile__student_number__in=TARGET_STUDENT_NUMBERS).order_by("id"))
    if len(target_students) != 2:
        raise RuntimeError("Could not resolve both target students for French make-up.")

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 26, 11, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 26, 12, 30, tzinfo=lagos)

    original_exam = Exam.objects.get(id=178)
    original_attempts = original_exam.attempts.count()

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
            "dean_review_comment": "Approved for two-student make-up paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Activated for missed SS1 French candidates.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.filter(is_locked=False).exclude(student__in=target_students).exists():
        raise RuntimeError(f"Exam {exam.id} already has unlocked non-target attempts.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for two-student make-up paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Activated for missed SS1 French candidates."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    if not exam.attempts.exists():
        ExamQuestion.objects.filter(exam=exam).delete()
        bank.questions.all().delete()

        sort_order = 1
        for index, item in enumerate(OBJECTIVES, start=1):
            question = Question.objects.create(
                question_bank=bank,
                created_by=teacher,
                subject=subject,
                question_type=CBTQuestionType.OBJECTIVE,
                stem=_render_stem(item),
                rich_stem=_render_rich_stem(item),
                marks=Decimal("1.00"),
                source_reference=f"SS1-FRE-MAKEUP-20260326-OBJ-{index:02d}",
                shared_stimulus_key="SS1-FRE-TEXTE-1" if index <= 9 else ("SS1-FRE-TEXTE-2" if index <= 18 else ""),
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
                rich_stem=item["stem"].replace("\n", "<br>"),
                marks=item["marks"],
                source_reference=f"SS1-FRE-MAKEUP-20260326-TH-{index:02d}",
                is_active=True,
            )
            CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
            sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 30
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS1-FRE-MAKEUP-EXAM",
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

    target_student_ids = {row.id for row in target_students}
    ss1_student_ids = list(
        StudentClassEnrollment.objects.filter(
            session=session,
            academic_class_id__in=academic_class.cohort_class_ids(),
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    for student_id in ss1_student_ids:
        if student_id in target_student_ids:
            continue
        attempt, _ = ExamAttempt.objects.get_or_create(
            exam=exam,
            student_id=student_id,
            attempt_number=1,
            defaults={
                "status": CBTAttemptStatus.IN_PROGRESS,
                "is_locked": True,
                "lock_reason": "MAKEUP_ONLY",
                "locked_at": timezone.now(),
                "allow_resume_by_it": False,
            },
        )
        fields = []
        if not attempt.is_locked:
            attempt.is_locked = True
            fields.append("is_locked")
        if attempt.lock_reason != "MAKEUP_ONLY":
            attempt.lock_reason = "MAKEUP_ONLY"
            fields.append("lock_reason")
        if attempt.locked_at is None:
            attempt.locked_at = timezone.now()
            fields.append("locked_at")
        if attempt.allow_resume_by_it:
            attempt.allow_resume_by_it = False
            fields.append("allow_resume_by_it")
        if fields:
            fields.append("updated_at")
            attempt.save(update_fields=fields)

    print(
        {
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "target_students": sorted(TARGET_STUDENT_NUMBERS),
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
            "locked_other_students": ExamAttempt.objects.filter(exam=exam, is_locked=True).exclude(
                student_id__in=target_student_ids
            ).count(),
            "original_exam_id": original_exam.id,
            "original_exam_attempts_before": original_attempts,
            "original_exam_attempts_after": original_exam.attempts.count(),
        }
    )


if __name__ == "__main__":
    main()
