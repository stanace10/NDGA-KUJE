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

TITLE = "THU 9:30-11:00 JS2 Yoruba Language L2 Second Term Exam"
DESCRIPTION = "SECOND TERM EXAMINATION 2025/2026 ACADEMIC SESSION. SUBJECT: EDE YORUBA L2 CLASS: JS2"
BANK_NAME = "JS2 Yoruba Language L2 Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Dahun gbogbo awon ibeere wonyii. For questions 1 to 7, read the ayoka and answer accordingly. "
    "Timer is 90 minutes. Exam window closes at 11:00 AM WAT on Thursday, March 26, 2026."
)

AYOKA = (
    "Ka ayoka yii ki o si dahun awon ibeere ti o tele e.\n"
    "Orisiirisii eso igi ni Olodumare seda sinu igbo. Pupo ninu awon igi wonyii ni won maa n so esoi "
    "fun igbadun eye inu igbo ati awon eda miiran.\n"
    "Lara eso ti awon igi bee n pese ni osan orombo, osan agbalumo, kasu, orogbo, ogede, gooba, iyeye, "
    "agbon, awusa abbl.\n"
    "Pataki ni eso je fun eda eniyan nitori opolopo anfaani ati iwulo re. Jije eso ti o dara loorekoore "
    "maa n se ara lore, o si maa n dena aisan. Bakan naa, o maa n je ki a se igbonse wooro lai-laagun.\n"
    "Atoojo-ateerun, ile alakan kii gbe, ni oro eso je nitori pe, ko so akoko kan ninu odun ti a ko ni "
    "ba eso kan tabi omiiran pade loja.\n"
    "Ko si ibi ti eso ko le hu si, bi o tile je pe, o dara ni awon agbegbe kan ju omiiran lo.\n"
    "Amo saa, o se pataki lati fo eso ati owo wa fun imototo, ki a to je e.\n"
    "A gbodo sakiyesi wi pe, iru eso bee ko ni kokoro ninu, ki o ma baa fa ijamba fun wa.\n"
    "A ko gbodo se ojukokoro lati ka tabi je eso ti ko pon daradara, ki o ma ba a fa aisan."
)

def ayoka_stem(text: str) -> str:
    return f"{AYOKA}\n\n{text}"


OBJECTIVES = [
    {"stem": ayoka_stem("1. Eso jije maa n je ki a se ______ wooro lai-laagun?"), "options": {"A": "Jeun", "B": "Sise", "C": "Igbonse", "D": "Ko orin"}, "answer": "C"},
    {"stem": ayoka_stem("2. 'Atoojo-ateerun...' ninu akaye yii tumo si ______."), "options": {"A": "ile alakan kii gbe", "B": "eso nilo omi pupo", "C": "eso fe ojo ati erun", "D": "gbogbo igba yipo odun ni eso maa n wa"}, "answer": "D"},
    {"stem": ayoka_stem("3. Asiko ti o dara julo lati maa je eso ni ______."), "options": {"A": "ojo odun", "B": "ojoojumo", "C": "osoose", "D": "igba ojo"}, "answer": "B"},
    {"stem": ayoka_stem("4. O se pataki lati ______ eso ati owo wa fun imototo, ki a to je e."), "options": {"A": "fo", "B": "din", "C": "ge", "D": "se"}, "answer": "A"},
    {"stem": ayoka_stem("5. Ewo ni kii se eso ninu awon wonyii?"), "options": {"A": "kasu", "B": "ogede", "C": "agbon", "D": "iresi"}, "answer": "D"},
    {"stem": ayoka_stem("6. A gbodo sakiyesi wi pe eso ko ni kokoro ninu, ki o ma baa fa ______ fun wa."), "options": {"A": "ijamba", "B": "orun", "C": "erin", "D": "isubu"}, "answer": "A"},
    {"stem": ayoka_stem("7. Ayoka yii je mo ______."), "options": {"A": "ile olorogun", "B": "eso jije", "C": "obe sise", "D": "sise iyonda"}, "answer": "B"},
    {"stem": "8. Ege oro ti o kere julo ti a le fi ohun gbe jade ni eekan soso ni ______.", "options": {"A": "Litireso", "B": "Silebu", "C": "Oro", "D": "Iwa"}, "answer": "B"},
    {"stem": "9. Ewo ni oro onisilebu merin ninu awon wonyii?", "options": {"A": "alagbato", "B": "onigba", "C": "igbagbo", "D": "agbado"}, "answer": "A"},
    {"stem": "10. Oro wo ni o ba Batani yii mu ju 'FKFKFF'?", "options": {"A": "omode", "B": "olowo", "C": "eewo", "D": "akekoo"}, "answer": "D"},
    {"stem": "11. 'Baale' Batani ti o ba oro yii mu ni ______.", "options": {"A": "KFKF", "B": "KFFKF", "C": "FKFFK", "D": "KFFKFF"}, "answer": "B"},
    {"stem": "12. Awon nnkan wonyi ni ohun elo ogun jija, ayafi ______.", "options": {"A": "ibon", "B": "kumo", "C": "ofa", "D": "ike"}, "answer": "D"},
    {"stem": "13. Ki ni aburu ti o maa wa ninu ogun jija?", "options": {"A": "ipalurun", "B": "owo pupo", "C": "ijo jijo", "D": "orin kiko"}, "answer": "A"},
    {"stem": "14. Awon eni ti ogun ba ko ni a maa pe ni ______.", "options": {"A": "Olu-ode", "B": "Alagbara", "C": "Eru", "D": "Omode"}, "answer": "C"},
    {"stem": "15. Gbigbe ni irepo laarin ilu tabi orile-ede meji lai si aawo ni a mo si ______.", "options": {"A": "ogun", "B": "irepo", "C": "alaafia", "D": "ayo"}, "answer": "C"},
    {"stem": "16. Ohun ti won ko, ti a ka, ti gbogbo koko inu re si ye ni, ni a mo si ______.", "options": {"A": "Aroko", "B": "Akaye", "C": "Ewi", "D": "Owe"}, "answer": "B"},
    {"stem": "17. A le pin akaye pin si orisii ona ______.", "options": {"A": "Meta", "B": "Marun-un", "C": "Meji", "D": "Meje"}, "answer": "A"},
    {"stem": "18. Aawo tabi ija to maa n wa waye laarin ilu meji tabi orile-ede meji ni a pe ni ______.", "options": {"A": "Alaafia", "B": "Ogun", "C": "Ote", "D": "Ere idaraya"}, "answer": "B"},
    {"stem": "19. Oro-oruko maa n sise oluwa, abo ati ______.", "options": {"A": "Agbara", "B": "Eyan", "C": "Orin", "D": "Ilu", "E": "Ijo"}, "answer": "B"},
    {"stem": "20. Apeere ohun elo ogun jija ni ______.", "options": {"A": "Pensuru", "B": "Rula", "C": "Iwe", "D": "Ibon"}, "answer": "D"},
    {"stem": "21. Pari owe yii: 'Bi a ku, ise ______'.", "options": {"A": "po pupo", "B": "wa ni sise", "C": "ojo wa", "D": "o tan"}, "answer": "D"},
    {"stem": "22. Ewo ni ki i se owe ninu awon wonyi?", "options": {"A": "Ona kan ko wo oja", "B": "Kokoro tin jefo idi efo lowa", "C": "Akara tu sepo", "D": "Ila ki i ga ju onire lo"}, "answer": "C"},
    {"stem": "23. Faweli aranmupe ni ______.", "options": {"A": "ni", "B": "na", "C": "un", "D": "no"}, "answer": "C"},
    {"stem": "24. Konsonanti aranmupe ni ______.", "options": {"A": "P", "B": "N", "C": "GB", "D": "Y"}, "answer": "B"},
    {"stem": "25. Meloo ni gbogbo iro konsonanti?", "options": {"A": "mejidinlogun", "B": "mejilelogun", "C": "meje", "D": "marun-un"}, "answer": "A"},
    {"stem": "26. 'Otalenigba' ni onka Yoruba je ______.", "options": {"A": "100", "B": "260", "C": "200", "D": "155"}, "answer": "B"},
    {"stem": "27. Faweli aarin ayanupe ni ______.", "options": {"A": "o", "B": "e", "C": "a", "D": "i"}, "answer": "C"},
    {"stem": "28. Ami ohun wo ni o ba oro yii mu 'OMODE'?", "options": {"A": "re, re, re", "B": "re, mi, re", "C": "re, re, mi", "D": "re, do, mi"}, "answer": "C"},
    {"stem": "29. 'do, do, mi' oro wo ni o baa mi ohun yii mu?", "options": {"A": "adugbo", "B": "iyawo", "C": "ilule", "D": "agbara"}, "answer": "B"},
    {"stem": "30. Lara ona ipolowo oja ni wonyii, ayafi ______.", "options": {"A": "Ipate", "B": "Iwe iroyin", "C": "Ikiri oja", "D": "Pipa oja mo sinu ile"}, "answer": "D"},
    {"stem": "31. Ewo ni ki i se ona ipolowo oja atijo?", "options": {"A": "ikiri oja", "B": "ipate oja", "C": "ipolowo lori telifisan", "D": "ki ke ibosi"}, "answer": "C"},
    {"stem": "32. 'Gbanjo! Gbanjo! O lo nile ko dowo.'", "options": {"A": "Eran", "B": "Eja", "C": "Isu", "D": "Aso"}, "answer": "D"},
    {"stem": "33. 'Okoolelugba' ni a mo si ______.", "options": {"A": "220", "B": "210", "C": "200", "D": "205"}, "answer": "A"},
    {"stem": "34. Kin ni onka Yoruba fun '250'?", "options": {"A": "otalelugba", "B": "aadotalelugba", "C": "ogun ati aadota", "D": "aadota"}, "answer": "B"},
    {"stem": "35. 'Oodunrun' ni onka Yoruba je ______.", "options": {"A": "300", "B": "200", "C": "250", "D": "220"}, "answer": "A"},
    {"stem": "36. Idakeji dudu ni ______.", "options": {"A": "Iya", "B": "Funfun", "C": "Omo", "D": "Ayo"}, "answer": "B"},
    {"stem": "37. Kin ni idakeji iwaju?", "options": {"A": "Tobi", "B": "Epe", "C": "Kere", "D": "Eyin"}, "answer": "D"},
    {"stem": "38. Kin ni idakeji oke?", "options": {"A": "Tobi", "B": "Epe", "C": "Osi", "D": "Isale"}, "answer": "D"},
    {"stem": "39. Kin ni idakeji ekun?", "options": {"A": "Tobi", "B": "Epe", "C": "Erin", "D": "Iye"}, "answer": "C"},
    {"stem": "40. Kin ni idakeji okunrin?", "options": {"A": "Tobi", "B": "Obinrin", "C": "Kere", "D": "Iye"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Se apejuwe awon iro faweli airanmupe wonyii:\n(i) I\n(ii) E\n(iii) A\n(iv) U\n(v) O", "marks": Decimal("10.00")},
    {"stem": "2. Pa orisii owe Yoruba marun-un ti o ba mo.", "marks": Decimal("10.00")},
    {"stem": "3. Ko idakeji oro wonyii:\n(a) Tobi\n(b) Obinrin\n(c) Kere\n(d) Iye\n(e) Otun", "marks": Decimal("10.00")},
    {"stem": "4. (a) Kin ni silebu?\n(b) Ko oro onisilebu meta-meta ni ona marun-un.", "marks": Decimal("10.00")},
    {"stem": "5. (a) Daruko ona marun-un ti a n gba se ipolowo oja ni ode-oni.\n(b) Daruko ohun elo ogun marun-un ti o ba mo.", "marks": Decimal("10.00")},
    {"stem": "6. Kin ni a n pe awon nonba wonyii ni ede Yoruba?\n(i) 50\n(ii) 202\n(iii) 200\n(iv) 240\n(v) 220", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="YOR")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS2 Yoruba assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 9, 30, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 11, 0, 0), lagos)

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
                source_reference=f"JS2-YOR-L2-20260326-OBJ-{index:02d}",
                is_active=True,
            )
            option_map = {}
            labels = list(item["options"].keys())
            for option_index, label in enumerate(labels, start=1):
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
                source_reference=f"JS2-YOR-L2-20260326-TH-{index:02d}",
                is_active=True,
            )
            CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
            sort_order += 1

        blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
        blueprint.duration_minutes = 90
        blueprint.max_attempts = 1
        blueprint.shuffle_questions = True
        blueprint.shuffle_options = True
        blueprint.instructions = INSTRUCTIONS
        blueprint.section_config = {
            "paper_code": "JS2-YOR-L2",
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
