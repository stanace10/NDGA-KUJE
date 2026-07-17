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

TITLE = "THU 9:30-11:30 JS2 Igbo Language Second Term Exam"
DESCRIPTION = "JS2 IGBO EXAM"
BANK_NAME = "JS2 Igbo Language Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Zaa ajuju niile di na ngalaba nke mbu. Na agba nke abuo, zaa ajuju ano. "
    "For questions 1 to 5, read the aghotaazaa and answer accordingly. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

AGHOTAAZAA = (
    "AGHOTAAZAA\n"
    "Adaku bu nwata nwaanyi gbara afo iri na ise. O bituru mma aka. O toro ogologo, guzoro kwekem. "
    "Imi ya di wara wara. Ntutu isi ya di yoriyori ka aji aturu bekee. O bu naani ya ka nne na nna ya, "
    "Eze na Lolo Onyekwere mutara.\n"
    "Eze Onyekwere bu ogaranya a na-anu aha ya n'obodo ya gbaa gburugburu. O na-atubata ngwa ahia di iche "
    "iche site na Jamany nakwa mba Afrika ndi ozo. Aha otutu e jiri mara ya bu Akajiaku. O na-enyere ndi "
    "ogbenye aka nke ukwuu. Nwunye ya bu Lolo Onyekwere na-azukwa ahia nke ya. O na-ere umu ihe olu, ola "
    "nti na mgbanaka di iche iche ndi e jiri ola edo mee."
)


def passage_stem(text: str) -> str:
    return f"{AGHOTAAZAA}\n\n{text}"


OBJECTIVES = [
    {"stem": passage_stem("1. Kedu nwata akporo aha ya n'akuko a?"), "options": {"A": "Adaku", "B": "Ada", "C": "Adaeze", "D": "Adaobi"}, "answer": "A"},
    {"stem": passage_stem("2. Kedu aha nne na nna ya?"), "options": {"A": "Eze na Lolo Onyekwere", "B": "Mrs and Mr Onyekwere", "C": "Ezinaulo Onyekwere", "D": "Onyekwere"}, "answer": "A"},
    {"stem": passage_stem("3. Umu ole ka Eze Onyekwere muru?"), "options": {"A": "Otu", "B": "Abuo", "C": "Ano", "D": "Onweghi"}, "answer": "A"},
    {"stem": passage_stem("4. Kedu aha otutu e jiri mara Eze Onyekwere?"), "options": {"A": "Akajiaku", "B": "Ogbuefi", "C": "Akpujindu", "D": "Akaji"}, "answer": "A"},
    {"stem": passage_stem("5. Afo ole ka Adaku di?"), "options": {"A": "iri na ise", "B": "iri", "C": "ise", "D": "ise na iri"}, "answer": "A"},
    {"stem": "6. Gini bu mputara izu na ire aha na bekee?", "options": {"A": "Market Relationship", "B": "Buying and selling", "C": "Business", "D": "Market Communication"}, "answer": "B"},
    {"stem": "7. Hoputa nke na adabara nke oma n'ebe a.", "options": {"A": "Ego olee?", "B": "O garaka onu.", "C": "Gini bu ereghi gi?", "D": "Ewo! ebe ka o di?"}, "answer": "D"},
    {"stem": "8. Gini bu mputara ufoego m na bekee?", "options": {"A": "Balance", "B": "Money", "C": "Cost", "D": "Goods"}, "answer": "A"},
    {"stem": "9. Kedu nke na adabara n'okwu ndi metutara njem?", "options": {"A": "Ije oma", "B": "Gaa nkeoma", "C": "Ugbommiri", "D": "Ikuku ike"}, "answer": "D"},
    {"stem": "10. What is 'flower' called in Igbo?", "options": {"A": "oko osisi", "B": "okooko", "C": "osisi", "D": "obere osisi"}, "answer": "B"},
    {"stem": "11. Mputara Nari na bekee bu...", "options": {"A": "Trillion", "B": "Million", "C": "Billion", "D": "Hundred"}, "answer": "D"},
    {"stem": "12. Nari abuo na iri itoolu na itoolu na onuogugu bu...", "options": {"A": "200", "B": "209", "C": "290", "D": "299"}, "answer": "D"},
    {"stem": "13. Words", "options": {"A": "Odide", "B": "edemede", "C": "Mkpuruokwu", "D": "Ahiri"}, "answer": "C"},
    {"stem": "14. Vowels", "options": {"A": "Edemede", "B": "Mkpuruokwu", "C": "Udaume", "D": "Mgbochiume"}, "answer": "C"},
    {"stem": "15. Consonant", "options": {"A": "Udamfe", "B": "Udaaro", "C": "Mgbochiume", "D": "Udaume"}, "answer": "C"},
    {"stem": "16. What is four cardinal points called in Igbo?", "options": {"A": "Mba ano di n'uwa", "B": "Mba niile", "C": "Mba uwa", "D": "Mba"}, "answer": "A"},
    {"stem": "17. Hoputa nke dabara adaba.", "options": {"A": "mgbago ugwu, mkpuruugwu na ndida anyanwu", "B": "mgbago ugwu, owuwa anyanwu na ndida anyanwu", "C": "odida anyanwu, owuwa anyanwu na mkpu ugwu", "D": "odida anyanwu, ugwu odida na ugwu"}, "answer": "B"},
    {"stem": "18. What is signs called in Igbo?", "options": {"A": "mpempe", "B": "akara", "C": "ntakiri", "D": "mpe"}, "answer": "B"},
    {"stem": "19. Myiri udaume Igbo o di ole n'Igbo?", "options": {"A": "abuo", "B": "ano", "C": "asato", "D": "otu"}, "answer": "A"},
    {"stem": "20. __________ bu ihe a na-ejikota onu wee mebe mkpuruokwu.", "options": {"A": "mkpuruedemede/ abidii", "B": "mkpuruokwu", "C": "okwu uda", "D": "mkpuruokwu uda"}, "answer": "A"},
    {"stem": "21. __________ bu mmadu isi na otu obodo gaa n'obodo ozo.", "options": {"A": "ije", "B": "Ime njem", "C": "Iga ije", "D": "Ugbo"}, "answer": "B"},
    {"stem": "22. Otu esoghi na okwu ndi metutara njem.", "options": {"A": "Ugboelu", "B": "Ugboala", "C": "Ijeoma", "D": "Onwu"}, "answer": "D"},
    {"stem": "23. Kedu nke na-esoghi n'uzo esi eme njem.", "options": {"A": "Njem okporouzo", "B": "Njem n'elu mmiri", "C": "Njem n'ikuku", "D": "Njem mmadu"}, "answer": "D"},
    {"stem": "24. What is transportation called in Igbo?", "options": {"A": "Ije", "B": "Ime njem", "C": "Njem ala", "D": "Njem elu"}, "answer": "B"},
    {"stem": "25. Gini bu mputara akaoru na bekee?", "options": {"A": "Occupation", "B": "Work", "C": "Job", "D": "Business"}, "answer": "A"},
    {"stem": "26. What is buying and selling called in Igbo?", "options": {"A": "Izu na ire ahia", "B": "Ahia", "C": "Ngwa ahia", "D": "Onye ahia"}, "answer": "A"},
    {"stem": "27. Otu esoghi na nnochiaha nwere naani otu mkpuruokwu hoputa ya.", "options": {"A": "A", "B": "I", "C": "E", "D": "Ha"}, "answer": "D"},
    {"stem": "28. Mputara akunauba na bekee bu.....", "options": {"A": "Materials", "B": "Healthy", "C": "Riches", "D": "Wealth"}, "answer": "D"},
    {"stem": "29. Gini bu mputara uzo ezighi ezi na bekee.", "options": {"A": "Illegal means", "B": "illegal", "C": "evil means", "D": "Fraudsters"}, "answer": "A"},
    {"stem": "30. Hoputa nke na-esoghi na oghom di na ikpata akunauba n'uzo ezighi ezi.", "options": {"A": "oganiihu", "B": "Ojije nga", "C": "Ihere", "D": "Onwu ike"}, "answer": "A"},
    {"stem": "31. Kedu aha ozo e nwere ike ikpo akaoru?", "options": {"A": "Oruaka", "B": "Oru", "C": "oru ahia", "D": "oru oyibo"}, "answer": "B"},
    {"stem": "32. Kedu ka i mere?", "options": {"A": "Where are you?", "B": "How are you?", "C": "What is that?", "D": "How was your night?"}, "answer": "B"},
    {"stem": "33. Gini ka i na-eme?", "options": {"A": "What is your name?", "B": "What are you doing?", "C": "Who are you?", "D": "How are you?"}, "answer": "B"},
    {"stem": "34. Ebee ka o di?", "options": {"A": "Where are you?", "B": "Where is it?", "C": "Where are you?", "D": "Where are we?"}, "answer": "B"},
    {"stem": "35. Ego olee?", "options": {"A": "How many?", "B": "How much?", "C": "How big?", "D": "How things?"}, "answer": "B"},
    {"stem": "36. Gini ka a na-akpo mgbochiume mkpii n'asusu bekee?", "options": {"A": "Double Consonant", "B": "vowel", "C": "Consonant", "D": "Alphabet"}, "answer": "A"},
    {"stem": "37. Udamkpi Igbo di olee?", "options": {"A": "Itoolu", "B": "Asato", "C": "Iri abuo na asato", "D": "Iri ato na isii"}, "answer": "A"},
    {"stem": "38. Kedu aha ozo enwere ike ikpo idiochi?", "options": {"A": "onu nkwu", "B": "ite nkwu", "C": "ote nkwu", "D": "Nkwu"}, "answer": "C"},
    {"stem": "39. __________ bu eserese na-egosiputa iwu na-echkwa okporouzo.", "options": {"A": "Okporouzo", "B": "iwu okporouzo", "C": "iwu gbasara okporouzo", "D": "Akara okporouzo"}, "answer": "D"},
    {"stem": "40. Azumahia putara __________ na bekee?", "options": {"A": "Trading", "B": "Business", "C": "Transaction", "D": "deal"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. Gini bu ime njem?\n(b) Deputa uzo ato mmadu si eme njem.\n(c) Kpoputa ngwa ano eji eme njem.", "marks": Decimal("10.00")},
    {"stem": "2. Jiri eserese gosiputa mgba ano di n'uwa.\n(b) Gosiputa ebe steeti, local goomenti na obodo gi no na ya.", "marks": Decimal("10.00")},
    {"stem": "3. Kowa iwu gbasara okporouzo na akara okporouzo.\n(B) Jiri eserese gosiputa akara okporouzo ano i maara ma dee aha ha.", "marks": Decimal("10.00")},
    {"stem": "4. Jiri eserese gosiputa ihe ndia na-aku n'Igbo:\n(i) 9:20am\n(ii) 7:30\n(iii) 11:00pm\n(iv) 4:40\n(v) 8:00pm", "marks": Decimal("10.00")},
    {"stem": "5. Kedu ihe bu oruaka?\n(b) Deputa oruaka ano e ji mara ndi Igbo mgbe gboo.\n(c) Ziput akaoru ise ugba n'Igbo.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="IGB")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS2 Igbo assignment found")
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
                rich_stem=item["stem"].replace("\n", "<br>"),
                marks=Decimal("1.00"),
                source_reference=f"JS2-IGB-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS2-IGB-20260326-TH-{index:02d}",
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
            "paper_code": "JS2-IGB-EXAM",
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
