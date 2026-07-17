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

TITLE = "THU 9:30-11:30 JS3 Igbo Language Second Term Exam"
DESCRIPTION = "JS3 2ND TERM IGBO EXAM 2026"
BANK_NAME = "JS3 Igbo Language Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Zaa ajuju niile di na ngalaba nke mbu. Na agba nke abuo, zaa ajuju ato. "
    "For questions 1 to 5, read the aghotaazaa and answer accordingly. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

AGHOTAAZAA = (
    "AGHOTAAZAA\n"
    "Akuoma na Akudo bu enyi. Ha bu ndi Okohia di n'Imo Steeti. Ha guru akwukwo na Mahadum Nsukka "
    "ebe ha nwetara nzere digirii na Injiniarin. Akuoma luru di ozugbo ha guchara akwukwo. Aha di ya "
    "bu Gozie. Gozie na-aru oru n'ulo aku di n'Owere. Akudo lutara di na-aru n'ulo aku ahu. Aha di ya "
    "bu Onyeka.\n"
    "Ebe di ha abuo na-aru otu ebe, enyi ha na-abawanyekwa. Akuoma mutara umu ato ebe Akudo mutara "
    "umu ano. Di ha abuo zuru ala ma ruokwa ulo nke mere ha jiri buru agbataobi. Mgbe otu onye mere "
    "njem, nke ozo na-elekota ezinaulo onye nke ahu. Nke a gosiri na agbataobi onye bu nwanne ya."
)


def passage_stem(text: str) -> str:
    return f"{AGHOTAAZAA}\n\n{text}"


OBJECTIVES = [
    {"stem": passage_stem("1. Olee ebe ndi enyi abuo ahu guru mahadum?"), "options": {"A": "Okohia", "B": "Owere", "C": "Amakaohia", "D": "Nsuka"}, "answer": "D"},
    {"stem": passage_stem("2. Nwunye Gozie n'ederede a bu"), "options": {"A": "Aku", "B": "Akuoma", "C": "Onyeka", "D": "Akudo"}, "answer": "B"},
    {"stem": passage_stem("3. Umu olee ka Akudo mutara?"), "options": {"A": "Ato", "B": "Abuo", "C": "Ano", "D": "Onweghi"}, "answer": "C"},
    {"stem": passage_stem("4. Kedu aha obodo Akuoma na Akudo?"), "options": {"A": "Owere", "B": "Akaohia", "C": "Nsuka", "D": "Amakohia"}, "answer": "B"},
    {"stem": passage_stem("5. Gozie na Onyeka na-aru n'ulo ____"), "options": {"A": "Uka", "B": "Oriri", "C": "Aku", "D": "Ogwu"}, "answer": "C"},
    {"stem": "6. Myiri udaume gunyere:", "options": {"A": "M, N", "B": "Ny, Nw", "C": "Kp, Kw", "D": "Gb, Gw"}, "answer": "B"},
    {"stem": "7. Mputara agwa ojoo na bekee bu...", "options": {"A": "Bad behaviour", "B": "Good attitude", "C": "Good child", "D": "Bad child"}, "answer": "A"},
    {"stem": "8. Gini ka akporo mgbe mmadu na eziputa ole ihe di?", "options": {"A": "Ngu", "B": "Ogu", "C": "Onuogugu", "D": "I guputa ihe"}, "answer": "C"},
    {"stem": "9. Otu esoghi na njirimara ndi Igbo", "options": {"A": "Uloobibi", "B": "Omenaala ha", "C": "Asusu ha", "D": "Nri ha"}, "answer": "A"},
    {"stem": "10. Mputara 8:00am o'clock na bekee bu...", "options": {"A": "O kuola elekere asato nke otutu.", "B": "O kuola elekere asato nke abali.", "C": "Asato nke otutu na-aku", "D": "Asato nke abali na-aku"}, "answer": "A"},
    {"stem": "11. Mputara 2:30PM na bekee bu...", "options": {"A": "Ofoduru nkeji abuo ka o kuo elekere iri ato.", "B": "O jirila okara gafee elekere abuo nke ehihie", "C": "Elekere iri ato na-aku", "D": "O jirila okara gafee elekere iri ato nke ehihie"}, "answer": "B"},
    {"stem": "12. Nkwo, Orie, Afo na Eke bu ahia ndi....", "options": {"A": "Awusa", "B": "Igbo", "C": "Abuja", "D": "Yoruba"}, "answer": "B"},
    {"stem": "13. 'Were ehihie chowa ewu ojii' means", "options": {"A": "make hay while the sun shines", "B": "make hay during the day", "C": "use the day wisely", "D": "make use of the daylight"}, "answer": "A"},
    {"stem": "14. 'Aka aja aja na-ebute onu mmanu mmanu' means", "options": {"A": "no cross no crown", "B": "no cross no victory", "C": "no crown no victory", "D": "no cross no pain"}, "answer": "A"},
    {"stem": "15. 'E mee ngwa ngwa emeghara odachi' means", "options": {"A": "a stitch in time saves nine", "B": "a stitch do saves quick", "C": "a stitch always saves", "D": "stitches do save money"}, "answer": "A"},
    {"stem": "16. 'O bughi ihe niile na-egbuke egbuke bu olaedo' means", "options": {"A": "all that glitters are not gold", "B": "all that glitters are glod", "C": "gold goes with glittering", "D": "with glitters gold is recognized"}, "answer": "A"},
    {"stem": "17. What is double consonant called in Igbo?", "options": {"A": "Mgbochiume mkpi", "B": "Mgbochiume", "C": "Mkpi", "D": "Mgbochiume uda"}, "answer": "A"},
    {"stem": "18. Kedu mputara agwugwa na bekee?", "options": {"A": "Proverb", "B": "Riddles", "C": "Joke", "D": "Guess work"}, "answer": "B"},
    {"stem": "19. Kedu ka esi amalite agwugwa?", "options": {"A": "Gwa m gwa m gwa m", "B": "agwugwa", "C": "Gwa m", "D": "Gwam gwa m"}, "answer": "A"},
    {"stem": "20. Kedu mputara edemede mfe na bekee?", "options": {"A": "Essay", "B": "simple essay", "C": "Essay writing", "D": "Simple introduction"}, "answer": "B"},
    {"stem": "21. What is punctuation mark called in Igbo?", "options": {"A": "akara edemede", "B": "akara ihe", "C": "Odide akara", "D": "Edemede akara"}, "answer": "A"},
    {"stem": "22. Otu na ndi a esoghi n'udi atumatuokwu Igbo enwere.", "options": {"A": "akpaalaokwu", "B": "ahiriokwu", "C": "ilu", "D": "mburu"}, "answer": "D"},
    {"stem": "23. 'Nwaada ahu joro njo ka udele.' Olee atumatuokwu putara ihe ebe a?", "options": {"A": "Egbeokwu", "B": "Ilu", "C": "Mmemmadu", "D": "Myiri"}, "answer": "D"},
    {"stem": "24. 'Okochi egbuchaala ihe anyi koro n'ubi.' Atumatuokwu putara ihe n'ahiriokwu a bu", "options": {"A": "akpaalaokwu", "B": "ilu", "C": "myiri", "D": "mmemmadu"}, "answer": "D"},
    {"stem": "25. 'Onwu e mee anyi aru ooo!' Abu a bu abu...", "options": {"A": "agha", "B": "nwa", "C": "nkocha", "D": "akwamozo"}, "answer": "D"},
    {"stem": "26. Hoputa nke na-abughi mburu na ndi a.", "options": {"A": "Nkechi bu azu no na mmiri", "B": "Tobenna bu ezi", "C": "Ume bu mbe", "D": "Umu ejima uloma dika ya"}, "answer": "D"},
    {"stem": "27. Otu na ndia abughi anu ulo", "options": {"A": "Osa", "B": "Nkita", "C": "Ewu", "D": "Okuku"}, "answer": "A"},
    {"stem": "28. Otu na ndi a ebighi na mmiri", "options": {"A": "Isha", "B": "Ochicha", "C": "Azu", "D": "Mbe mmiri"}, "answer": "B"},
    {"stem": "29. ______ bu ihe a na-anu maka ahuike maobu ka ahu oria na-anya mmadu laa.", "options": {"A": "Oria", "B": "Nri", "C": "Mmiri", "D": "Ogwu"}, "answer": "D"},
    {"stem": "30. Kedu nke dabara adaba mgbe mmadu ji anu ogwu?", "options": {"A": "Mgbe mmadu meruru ahu", "B": "Mgbe mmadu riri oke nri", "C": "Mgbe mmadu nwuru", "D": "Mgbe ike kwuru mmadu"}, "answer": "A"},
    {"stem": "31. Gini bu mputara nkejiasusu na bekee?", "options": {"A": "Parts of speech", "B": "figure of speech", "C": "Phrase", "D": "clause"}, "answer": "A"},
    {"stem": "32. 'Gwa gwa gwa m' bu ...", "options": {"A": "atumatuokwu", "B": "agumagu odinaala", "C": "agumagu ugbua", "D": "nkejiokwu"}, "answer": "B"},
    {"stem": "33. ______ bu mmanu ndi Igbo ji eri okwu.", "options": {"A": "Ilu", "B": "Oku", "C": "Nri", "D": "Ji"}, "answer": "A"},
    {"stem": "34. 'O bi na Legosi.' Ebe a, 'na' na-aru oru dika", "options": {"A": "enyemakangwaa", "B": "mbuuzo", "C": "ngwaa", "D": "nsonaazu"}, "answer": "A"},
    {"stem": "35. Hoputa nke na-abughi omenaala e jiri mara ndi Igbo.", "options": {"A": "Ibe ugwu", "B": "Igba akwukwo", "C": "Ichi ozo", "D": "Iwa oji"}, "answer": "B"},
    {"stem": "36. Kedu nke na-esoghi n'ihe e nwere ike iji edu nwaanyi ulo ma o na-aba be di ya", "options": {"A": "Igwe ntuoyi", "B": "Igwe njuoyi", "C": "Mmadu", "D": "Ugboala"}, "answer": "C"},
    {"stem": "37. Otu n'ime ekele ndi a abughi ihe a na-ekele nwaanyi muru nwa ohuru.", "options": {"A": "Chukwu aruola", "B": "Chukwu emeela", "C": "Ekele diri Chukwu", "D": "Ndo-na nwa i muru"}, "answer": "D"},
    {"stem": "38. Olee nke na-esoghi na njirimara ndi Igbo?", "options": {"A": "Asusu ha", "B": "Ekike ha", "C": "Nri ha", "D": "Uburu isi ha"}, "answer": "D"},
    {"stem": "39. Gini ka ndi Igbo ji eri okwu?", "options": {"A": "Mmanu", "B": "Aka", "C": "Ngaji", "D": "Ilu"}, "answer": "D"},
    {"stem": "40. Kedu ndi kwesiri iti mmonwu n'omenaala Igbo?", "options": {"A": "Umuada", "B": "Umuagbogho", "C": "Umunwoke", "D": "Umuaka"}, "answer": "C"},
    {"stem": "41. Kedu onye dere 'Omezue: Nwa Anyari'?", "options": {"A": "Anthonia Okoro-Opara", "B": "Anthonia Okoro", "C": "Anthonia Opara", "D": "Anthonia Okoye"}, "answer": "A"},
    {"stem": "42. 'Omezue: Nwa Anyari' bu udi agumagu ederede.....", "options": {"A": "Iduuazi", "B": "Abu", "C": "Ejiji", "D": "Ejije"}, "answer": "A"},
    {"stem": "43. Albino is called what in Igbo?", "options": {"A": "Anyari", "B": "Anyari ocha", "C": "Ndi ocha", "D": "Nwa Anyari"}, "answer": "D"},
    {"stem": "44. What is pineapple called in Igbo?", "options": {"A": "Nkwuaba", "B": "Okwuru bekee", "C": "Oka", "D": "Unere"}, "answer": "A"},
    {"stem": "45. Kedu nke bu 888?", "options": {"A": "asato asato asato", "B": "iri asato na asato na asato", "C": "Nari asato na asato na asato", "D": "Nari asato na iri asato na asato"}, "answer": "D"},
    {"stem": "46. What is matches called in Igbo?", "options": {"A": "Ekwuigwe", "B": "Mkpooku", "C": "Osite", "D": "Oku osisi"}, "answer": "B"},
    {"stem": "47. What is train called in Igbo?", "options": {"A": "Ugbo oloko", "B": "Ugbo mmiri", "C": "Ugbo", "D": "Ugbo okoko"}, "answer": "A"},
    {"stem": "48. Gini bu mputara elekere na bekee?", "options": {"A": "Clock", "B": "wrist watch", "C": "Time", "D": "Table clock"}, "answer": "A"},
    {"stem": "49. Nkowa onwe na-agunye ____", "options": {"A": "aha na afo", "B": "nri na uwe", "C": "ego na ulo", "D": "ahia na okporo uzo"}, "answer": "A"},
    {"stem": "50. Kedu nke a bu ihe eji eme nkowa onwe?", "options": {"A": "\"Aha m bu...\"", "B": "\"Nodu ala\"", "C": "\"Biko\"", "D": "\"Mechie\""}, "answer": "A"},
    {"stem": "51. Nri ndi Igbo na-enyere ahu ____", "options": {"A": "ike", "B": "oria", "C": "mwute", "D": "ura"}, "answer": "A"},
    {"stem": "52. Ulo ogwu na-enyere anyi aka ____", "options": {"A": "izu ahia", "B": "imu ihe", "C": "igwo oria", "D": "iri nri"}, "answer": "C"},
    {"stem": "53. Onye na-asa oria n'ulo ogwu bu ____", "options": {"A": "noosu", "B": "onye ahia", "C": "onye uweojii", "D": "onye ugbo"}, "answer": "A"},
    {"stem": "54. 'Gwa m aha gi' bu ____", "options": {"A": "aririo", "B": "ntimiywu", "C": "ajuju", "D": "aziza"}, "answer": "C"},
    {"stem": "55. Ajuju na-ejedebe na ____", "options": {"A": "akara mkpuru okwu", "B": "akara ajuju (?)", "C": "akara nkwusi (.)", "D": "akara mkpu (!)"}, "answer": "B"},
    {"stem": "56. 'I ga-abia echi?' bu ____", "options": {"A": "aririo", "B": "ajuju", "C": "ntimiywu", "D": "nkowa"}, "answer": "B"},
    {"stem": "57. Uwe omenala Igbo gunyere ____", "options": {"A": "suit", "B": "tie", "C": "akwa Igbo", "D": "jeans"}, "answer": "C"},
    {"stem": "58. Kedu nke a bu uwe isi?", "options": {"A": "okpu", "B": "akpukpo ukwu", "C": "uwe elu", "D": "uwe ime"}, "answer": "A"},
    {"stem": "59. Onuogugu 175 bu ____", "options": {"A": "otu nari na iri asaa na ise", "B": "otu puku na iri ise", "C": "nari iri ise", "D": "iri asaa"}, "answer": "A"},
    {"stem": "60. 'Daalu' putara ____", "options": {"A": "juo", "B": "okwu", "C": "ekele", "D": "abu"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Kowaa izu na inu ogwu agharaaghara na ogwu.\n(b) Deputa udi ogwu Igbo ano i maara ma tugharia na bekee.", "marks": Decimal("10.00")},
    {"stem": "2. Gini bu mpu ule?\n(b) Ziputa mmadu ano nwere ike ime mpu ule.\n(c) Deputa jenda ano i maara.", "marks": Decimal("10.00")},
    {"stem": "3. Jiri ahiriokwu iri kowa uloakwukwo gi.", "marks": Decimal("10.00")},
    {"stem": "4. Kpoputa uzo ano eji ezi ozi ogbe gboo na uzo ano ogbara ohuu.\n(b) Gini bu edemede leta?", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="IGB")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS3 Igbo assignment found")
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
                source_reference=f"JS3-IGB-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS3-IGB-20260326-TH-{index:02d}",
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
            "paper_code": "JS3-IGB-EXAM",
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
