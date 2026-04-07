from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

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

TITLE = "THU 9:30-11:30 JS1 Igbo Language Second Term Exam"
DESCRIPTION = "ASUSU IGBO ULE JS1 SECOND TERM EXAMINATION"
BANK_NAME = "JS1 Igbo Language Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Zaa ajụjụ niile dị na ngalaba nke mbụ. Na ngalaba nke abụọ, zaa ajụjụ anọ. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "\"Aha m bụ Chinedu\" ahiriokwu a bu ____", "options": {"A": "ajụjụ", "B": "nkowa onwe", "C": "arịrịọ", "D": "ntịmịwu"}, "answer": "B"},
    {"stem": "Kedu nke eji amata ebe mmadụ si?", "options": {"A": "Aha", "B": "Afọ", "C": "Obodo", "D": "Akwụkwọ"}, "answer": "C"},
    {"stem": "Ọnụọgụ 100 n'asụsụ Igbo bụ ____", "options": {"A": "otu narị", "B": "iri narị", "C": "narị otu", "D": "otu puku"}, "answer": "A"},
    {"stem": "Ọnụọgụ '99' bụ ____", "options": {"A": "Iri itoolu na itoolu", "B": "iri itoolu", "C": "otu itoolu na itoolu", "D": "itoolu na itoolu"}, "answer": "A"},
    {"stem": "200 n'asụsụ Igbo bụ ___", "options": {"A": "narị abụọ", "B": "iri abụọ", "C": "puku abụọ", "D": "narị iri"}, "answer": "A"},
    {"stem": "Ebe a na-agwọ ndị ọrịa bụ ____", "options": {"A": "ahịa", "B": "ụlọ akwụkwọ", "C": "ụlọ ọgwụ", "D": "ụka"}, "answer": "C"},
    {"stem": "Onye na-agwọ ọrịa n'ụlọ ọgwụ bụ ____", "options": {"A": "onye nkuzi", "B": "dọkịta", "C": "onye uweojii", "D": "onye ọzụzụ"}, "answer": "B"},
    {"stem": "Kedu ihe a na-eji ewere okpomọkụ ahụ?", "options": {"A": "ite", "B": "temomita", "C": "mma", "D": "efere"}, "answer": "B"},
    {"stem": "Nri a na-akpọ \"fufu\" bụ nri ____", "options": {"A": "ndị ọcha", "B": "ndị oyibo", "C": "ndị Igbo", "D": "ụmụaka"}, "answer": "C"},
    {"stem": "Kedu nke a bụ nri Igbo?", "options": {"A": "achịcha bekee", "B": "pizza", "C": "ji na ofe", "D": "spaghetti"}, "answer": "C"},
    {"stem": "Ofe egusi bụ ____", "options": {"A": "uwe", "B": "nri", "C": "ụlọ", "D": "ngwa"}, "answer": "B"},
    {"stem": "A na-eyi uwe iji ____", "options": {"A": "rie nri", "B": "zoo ego", "C": "kpuchie ahụ", "D": "kwụọ ụtụ"}, "answer": "C"},
    {"stem": "Kedu nke a bụ uwe?", "options": {"A": "akpa", "B": "agwa", "C": "ite", "D": "oche"}, "answer": "B"},
    {"stem": "Uwe a na-eyi n'ụkwụ bụ ____", "options": {"A": "okpu", "B": "uwe ime", "C": "akpụkpọ ụkwụ", "D": "uwe aka"}, "answer": "C"},
    {"stem": "\"Biko, nyere m aka\" bụ omumaatu nke ____", "options": {"A": "ajụjụ", "B": "arịrịọ mfe", "C": "nkowa onwe", "D": "iwu"}, "answer": "B"},
    {"stem": "\"Kedu aha gị?\" bụ ____", "options": {"A": "azịza", "B": "arịrịọ", "C": "ajụjụ", "D": "ntịmịwu"}, "answer": "C"},
    {"stem": "Azịza ziri ezi nye \"Kedu ka ị mere?\" bụ ____", "options": {"A": "Kedu aha gị?", "B": "Ọ dị mma", "C": "Biko", "D": "Ee"}, "answer": "B"},
    {"stem": "\"Nọdụ ala\" bụ ____", "options": {"A": "ajụjụ", "B": "arịrịọ", "C": "ntịmịwu mfe", "D": "nkowa onwe"}, "answer": "C"},
    {"stem": "Ahịrịokwu ntịmịwu na-egosi ____", "options": {"A": "ajụjụ", "B": "iwu", "C": "nkowa", "D": "ekele"}, "answer": "B"},
    {"stem": "\"Mechie ọnụ ụzọ\" bụ ahịrịokwu ____", "options": {"A": "ajụjụ", "B": "ntịmịwu", "C": "arịrịọ", "D": "nkowa onwe"}, "answer": "B"},
    {"stem": "\"Biko, mee ngwa\" bụ ____", "options": {"A": "ntịmịwu mfe", "B": "arịrịọ mfe", "C": "ajụjụ", "D": "azịza"}, "answer": "B"},
    {"stem": "Arịrịọ na-amalitekarị na okwu ____", "options": {"A": "ee", "B": "mba", "C": "biko", "D": "nọọ"}, "answer": "C"},
    {"stem": "Agwa ọjọọ pụtara ____", "options": {"A": "ezi agwa", "B": "agwa ọma", "C": "agwa na-adịghị mma", "D": "omume ọma"}, "answer": "C"},
    {"stem": "Izu ohi bụ ____", "options": {"A": "agwa ọma", "B": "agwa ọjọọ", "C": "ekele", "D": "arịrịọ"}, "answer": "B"},
    {"stem": "Ịgha ụgha bụ ____", "options": {"A": "eziokwu", "B": "agwa ọjọọ", "C": "nri", "D": "uwe"}, "answer": "B"},
    {"stem": "Kedu nke a abụghị agwa ọjọọ?", "options": {"A": "izu ohi", "B": "ime ihe ike", "C": "ịsọpụrụ ndị okenye", "D": "ịgha ụgha"}, "answer": "C"},
    {"stem": "Ụmụaka kwesị ị ____ ndị okenye ùgwù", "options": {"A": "kpasuo", "B": "sọọpụrụ", "C": "kụọ", "D": "tie"}, "answer": "B"},
    {"stem": "Nkowa onwe na-agụnye ____", "options": {"A": "aha na afọ", "B": "nri na uwe", "C": "ego na ụlọ", "D": "ahịa na okporo ụzọ"}, "answer": "A"},
    {"stem": "Kedu nke a bụ ihe eji eme nkowa onwe?", "options": {"A": "\"Aha m bụ...\"", "B": "\"Nọdụ ala\"", "C": "\"Biko\"", "D": "\"Mechie\""}, "answer": "A"},
    {"stem": "Nri ndị Igbo na-enyere ahụ ____", "options": {"A": "ike", "B": "ọrịa", "C": "mwute", "D": "ụra"}, "answer": "A"},
    {"stem": "Ụlọ ọgwụ na-enyere anyị aka ____", "options": {"A": "ịzụ ahịa", "B": "ịmụ ihe", "C": "ịgwọ ọrịa", "D": "iri nri"}, "answer": "C"},
    {"stem": "Onye na-enyere dọkịta aka n'ụlọ ọgwụ bụ ____", "options": {"A": "nọọsụ", "B": "onye ahịa", "C": "onye uweojii", "D": "onye ugbo"}, "answer": "A"},
    {"stem": "\"Gwa m aha gị\" bụ ____", "options": {"A": "arịrịọ", "B": "ntịmịwu", "C": "ajụjụ", "D": "azịza"}, "answer": "B"},
    {"stem": "Ajụjụ means ____ in English", "options": {"A": "Exclamation mark(!)", "B": "Question(?)", "C": "Full Stop(.)", "D": "Hyphen(-)"}, "answer": "B"},
    {"stem": "\"Ị ga-abịa echi?\" bụ ____", "options": {"A": "arịrịọ", "B": "ajụjụ", "C": "ntịmịwu", "D": "nkowa"}, "answer": "B"},
    {"stem": "Uwe omenala Igbo gụnyere ____", "options": {"A": "suit", "B": "tie", "C": "akwa omuma", "D": "jeans"}, "answer": "C"},
    {"stem": "Kedu nke a bụ uwe isi?", "options": {"A": "okpu", "B": "akpụkpọ ụkwụ", "C": "uwe elu", "D": "uwe ime"}, "answer": "A"},
    {"stem": "Ọnụọgụ 80 bụ ____", "options": {"A": "iri asato", "B": "asato na asato", "C": "narị iri asato", "D": "asato"}, "answer": "A"},
    {"stem": "\"Daalu\" pụtara ____", "options": {"A": "question", "B": "thanks", "C": "punctuation", "D": "words"}, "answer": "B"},
    {"stem": "Ịsacha aka tupu iri nri bụ ____", "options": {"A": "agwa ọjọọ", "B": "agwa ọma", "C": "ajụjụ", "D": "ntịmịwu"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Kọwaa onwe gị n'asụsụ Igbo n'ahịrịokwu ise.", "marks": Decimal("10.00")},
    {"stem": "2. Dee ọnụọgụ ndị a n'Igbo: 100, 99, 89, 51.\n(B) Jiri otu mebe ahịrịokwu.", "marks": Decimal("10.00")},
    {"stem": "3. Kpọpụta ngwa isii i nwere ike ịhụ n'ụlọ ọgwụ.\n(B) Kpọọ aha mmadụ abụọ na-arụ ọrụ ebe ahụ n'Igbo ma tụgharịa na Bekee.", "marks": Decimal("10.00")},
    {"stem": "4. Kpọọ nri Igbo ise ma (B) kọpụta ofe ise.", "marks": Decimal("10.00")},
    {"stem": "5. Kọwaa uwe na (B) ụdị uwe isii ị maara na ihe oyiyi abụọ ndị ọzọ n'asụsụ Igbo ma tụgharịa na Bekee.", "marks": Decimal("10.00")},
    {"stem": "6. Gịnị bụ agwa ọjọọ?\n(B) Depụta agwa ọjọọ isii.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="IGB")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS1 Igbo assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 9, 30, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 11, 30, 0), lagos)

    with transaction.atomic():
        bank, _ = QuestionBank.objects.get_or_create(
            name=BANK_NAME,
            subject=subject,
            academic_class=academic_class,
            session=session,
            term=term,
            defaults={"description": DESCRIPTION, "assignment": assignment, "owner": teacher, "is_active": True},
        )
        bank.description = DESCRIPTION
        bank.assignment = assignment
        bank.owner = teacher
        bank.is_active = True
        bank.save()

        exam, created = Exam.objects.get_or_create(
            title=TITLE,
            session=session,
            term=term,
            subject=subject,
            academic_class=academic_class,
            defaults={
                "description": DESCRIPTION,
                "exam_type": CBTExamType.EXAM,
                "status": CBTExamStatus.ACTIVE,
                "created_by": teacher,
                "assignment": assignment,
                "question_bank": bank,
                "schedule_start": schedule_start,
                "schedule_end": schedule_end,
                "is_time_based": True,
                "open_now": False,
            },
        )
        exam.description = DESCRIPTION
        exam.exam_type = CBTExamType.EXAM
        exam.status = CBTExamStatus.ACTIVE
        exam.created_by = teacher
        exam.assignment = assignment
        exam.question_bank = bank
        exam.schedule_start = schedule_start
        exam.schedule_end = schedule_end
        exam.is_time_based = True
        exam.open_now = False
        exam.save()

        exam.exam_questions.all().delete()
        Question.objects.filter(question_bank=bank).delete()

        sort_order = 1
        for index, item in enumerate(OBJECTIVES, start=1):
            question = Question.objects.create(
                question_bank=bank,
                created_by=teacher,
                subject=subject,
                question_type=CBTQuestionType.OBJECTIVE,
                stem=item["stem"],
                rich_stem=item["stem"],
                marks=Decimal("1.00"),
                source_reference=f"JS1-IGB-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS1-IGB-20260326-TH-{index:02d}",
                is_active=True,
            )
            CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
            sort_order += 1

        blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
        blueprint.duration_minutes = 55
        blueprint.max_attempts = 1
        blueprint.shuffle_questions = True
        blueprint.shuffle_options = True
        blueprint.instructions = INSTRUCTIONS
        blueprint.section_config = {
            "paper_code": "JS1-IGB-EXAM",
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
                "duration_minutes": blueprint.duration_minutes,
            }
        )


if __name__ == "__main__":
    main()
