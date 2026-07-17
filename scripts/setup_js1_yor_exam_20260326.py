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

TITLE = "THU 9:30-11:30 JS1 Yoruba Language Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION 2025/2026 ACADEMIC SESSION. SUBJECT: EDE YORUBA CLASS: JS1"
BANK_NAME = "JS1 Yoruba Language Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Dahun gbogbo awon ibeere wonyii. Ni apa keji, dahun ibeere meta pere. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "1. Ta ni baba nla Yoruba?", "options": {"A": "Adekola", "B": "Oriyomi", "C": "Oduduwa", "D": "Bankole"}, "answer": "C"},
    {"stem": "2. Litireso inu ede Yoruba pin si ona ___", "options": {"A": "meji", "B": "merin", "C": "kan soso", "D": "meta"}, "answer": "A"},
    {"stem": "3. Ki ni a n pe ere ti a maa n se leyin ise oojo?", "options": {"A": "Ere idaraya", "B": "Ere kere", "C": "Erede", "D": "Ere apa"}, "answer": "A"},
    {"stem": "4. Apeere ere idaraya ti o maa n waye ni asale ni akoko osupa ni __", "options": {"A": "Ayo tita", "B": "Guluso", "C": "Bojuboju", "D": "Ijakadi"}, "answer": "C"},
    {"stem": "5. Igbese akoko ninu eto igbeyawo ni ile Yoruba ni __", "options": {"A": "ifojusode", "B": "iwadii", "C": "itoro", "D": "idana"}, "answer": "A"},
    {"stem": "6. Kin ni '2' ni onka Yoruba?", "options": {"A": "alabaso", "B": "alatunse", "C": "onibara", "D": "Alarina"}, "answer": "D"},
    {"stem": "7. Awon wonyii ni ilana eto igbeyawo, ayafi _", "options": {"A": "itoro", "B": "idajo", "C": "iwadii", "D": "ijohen"}, "answer": "B"},
    {"stem": "8. Ewo ni ki i se oro-oruko?", "options": {"A": "Owo", "B": "Iwe", "C": "Je", "D": "Aja"}, "answer": "C"},
    {"stem": "9. Kin ni imo to fi akojopo ogbon, imo, oye, akiyesi ati iriri aye awon Yoruba?", "options": {"A": "Ede", "B": "Litireso", "C": "Asa", "D": "Igbagbo"}, "answer": "B"},
    {"stem": "10. Ilu wo ni ede Yoruba ti koko di kiko sile?", "options": {"A": "ilu Oyo", "B": "ilu Gombe", "C": "Ilu Freetown", "D": "ilu Abuja"}, "answer": "C"},
    {"stem": "11. Ewo ni ki i se ara isori oro Yoruba? ______", "options": {"A": "oro ise", "B": "oro aropo-oruko", "C": "oro-apa", "D": "oro oruko"}, "answer": "C"},
    {"stem": "12. Apeere oro-oruko nnkan ni _________", "options": {"A": "Mercy", "B": "bata", "C": "Kuje", "D": "Sola"}, "answer": "B"},
    {"stem": "13. Oro oruko eranko ni ________", "options": {"A": "iwe", "B": "tabili", "C": "Maluu", "D": "ayo"}, "answer": "C"},
    {"stem": "14. Kin ni a n lo dipo oro-oruko?", "options": {"A": "Oro-ise", "B": "oro-aponle", "C": "oro-apejuwe", "D": "oro-aropo-oruko"}, "answer": "D"},
    {"stem": "15. Apeere oro-aropo-oruko ni ____", "options": {"A": "Ile", "B": "Aso", "C": "Ade", "D": "Mo"}, "answer": "D"},
    {"stem": "16. '50' ni ede Yoruba je ______", "options": {"A": "Ogbon", "B": "Ogun", "C": "Ogota", "D": "Aadota"}, "answer": "D"},
    {"stem": "17. Kin ni a n pe '10' ni ede Yoruba.", "options": {"A": "Marundinlogun", "B": "Eewaa", "C": "Ogoji", "D": "Mejila"}, "answer": "B"},
    {"stem": "18. 'Ogoji' je _________", "options": {"A": "80", "B": "40", "C": "50", "D": "100"}, "answer": "B"},
    {"stem": "19. 'Ogorun-un' ni a n pe _______", "options": {"A": "35", "B": "100", "C": "65", "D": "45"}, "answer": "B"},
    {"stem": "20. Ki ni a n pe nonba yii ni ede Yoruba? '60' ____", "options": {"A": "Aadorin", "B": "Ogota", "C": "Aadojo", "D": "Aadosan-an"}, "answer": "B"},
    {"stem": "21. '30' ni ede Yoruba je _______", "options": {"A": "Eeta ati rin", "B": "Eetalemerin", "C": "Eerinlelogbon", "D": "Ogbon"}, "answer": "D"},
    {"stem": "22. Awon wo ni o maa sere osupa? Awon ___", "options": {"A": "iyaafin", "B": "agbalagba", "C": "arugbo", "D": "omode"}, "answer": "D"},
    {"stem": "23. Ona meloo ni faweli inu ede Yoruba pin si? _____", "options": {"A": "meji", "B": "marun-un", "C": "meta", "D": "meje"}, "answer": "A"},
    {"stem": "24. Ewo ni ko si ninu alifabeeti ede Yoruba? _____", "options": {"A": "E", "B": "GB", "C": "X", "D": "U"}, "answer": "C"},
    {"stem": "25. Apeere iro konsonanti Yoruba ni ____", "options": {"A": "U", "B": "O", "C": "GB", "D": "A"}, "answer": "C"},
    {"stem": "26. Iro faweli ni awon wonyii, ayafi ____", "options": {"A": "E", "B": "U", "C": "F", "D": "I"}, "answer": "C"},
    {"stem": "27. Meloo ni gbogbo iro ede Yoruba? ____", "options": {"A": "18", "B": "25", "C": "15", "D": "26"}, "answer": "B"},
    {"stem": "28. Eya ara eniyan ni wonyii, ayafi ______", "options": {"A": "ese", "B": "ori", "C": "enu", "D": "abo"}, "answer": "D"},
    {"stem": "29. Apeere ere ojojumo ni ___", "options": {"A": "bojuboju", "B": "eebu", "C": "Alo pipa", "D": "ijakadi"}, "answer": "D"},
    {"stem": "30. Ta ni o bi Oduduwa?", "options": {"A": "Okanbi", "B": "Oduduwa", "C": "Oranmiyan", "D": "Lamurudu"}, "answer": "D"},
    {"stem": "31. Yoruba ni gbogbo awon to n gbe ipinle wonyii, ayafi __", "options": {"A": "Oyo", "B": "Osun", "C": "Ekiti", "D": "Jos"}, "answer": "D"},
    {"stem": "32. Omo meloo ni Okanbi bi?", "options": {"A": "meji", "B": "merin", "C": "meje", "D": "eyokan"}, "answer": "C"},
    {"stem": "33. Odun wo ni ede Yoruba koko di kiko sile?", "options": {"A": "1983", "B": "1832", "C": "1820", "D": "1842"}, "answer": "D"},
    {"stem": "34. Orisii iro ohun meloo lo wa ninu ede Yoruba", "options": {"A": "meji", "B": "merin", "C": "meta", "D": "eyokan"}, "answer": "C"},
    {"stem": "35. Orisii litireso meloo lo wa?", "options": {"A": "meji", "B": "merin", "C": "meta", "D": "eyokan"}, "answer": "A"},
    {"stem": "36. Ibagbepo okunrin ati obinrin to ti balaga gege bi oko ati aya ni a mo _", "options": {"A": "Isomoloruko", "B": "Igbeyawo", "C": "Oriki", "D": "Oja tita"}, "answer": "B"},
    {"stem": "37. Igbese akoko ninu eto igbeyawo ibile ni ______", "options": {"A": "Iwadii", "B": "Itoro", "C": "Ifojusode", "D": "Idana"}, "answer": "C"},
    {"stem": "38. Igbeyawo ode-oni pin si orisii ona ____", "options": {"A": "Meji", "B": "Mefa", "C": "Marun-un", "D": "Meta"}, "answer": "A"},
    {"stem": "39. Ewo ni oro-aropo-oruko ninu awon wonyi? ___", "options": {"A": "won", "B": "kini", "C": "sare", "D": "owo-ile"}, "answer": "A"},
    {"stem": "40. Oro to maa n toka si oruko eniyan, eranko, ilu tabi nnkan ni ___", "options": {"A": "Oro-oruko", "B": "Oro-ise", "C": "Oro-apejuwe", "D": "Oro-aropo-oruko"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. (i) Ki ni litireso?\n(ii) Daruko ona meloo ni litireso Yoruba pin si?", "marks": Decimal("10.00")},
    {"stem": "2. Ko awon nonba wonyi ni ede Yoruba.\n(i) 30\n(ii) 40\n(iii) 100\n(iv) 50\n(v) 10", "marks": Decimal("10.00")},
    {"stem": "3. Daruko awon ilana eto igbeyawo marun-un ti o wa.", "marks": Decimal("10.00")},
    {"stem": "4. Tun oro wonyii ko ni akoto ode-oni:\n(a) Shade\n(b) Eiye\n(c) Iddo\n(d) Ogbomosho\n(e) Pepeiye", "marks": Decimal("10.00")},
    {"stem": "5. (a) Kin ni oro-oruko?\n(b) Ko apeere oruko eranko marun-un ni ede Yoruba.", "marks": Decimal("10.00")},
    {"stem": "6. Daruko apeere ere idaraya omode marun-un.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="YOR")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS1 Yoruba assignment found")
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
                source_reference=f"JS1-YOR-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS1-YOR-20260326-TH-{index:02d}",
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
            "paper_code": "JS1-YOR-EXAM",
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
