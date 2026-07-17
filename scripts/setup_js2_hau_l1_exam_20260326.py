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

TITLE = "THU 9:30-11:00 JS2 Hausa Language 1 Second Term Exam"
DESCRIPTION = "JSS 2 HAUSA LANGUAGE 1 SECOND TERM EXAMINATION"
BANK_NAME = "JS2 Hausa Language 1 Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Dahun dukkan tambayoyin da ke sashe na farko. A sashe na biyu, amsa tambayoyi hudu. "
    "Timer is 90 minutes. Exam window closes at 11:00 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "'Furuci' simply means ----", "options": {"A": "Crying", "B": "Talking", "C": "Singing", "D": "Laughter"}, "answer": "B"},
    {"stem": "All these are Organs of Speech except ----", "options": {"A": "Lebba", "B": "Hakora", "C": "Hannu", "D": "Huhu"}, "answer": "C"},
    {"stem": "The sound 'B' is pronounced with the help of ----", "options": {"A": "hanka", "B": "handa", "C": "lebba", "D": "harshe"}, "answer": "C"},
    {"stem": "Letter 'a' is pronounced with the help of ----", "options": {"A": "hanci", "B": "harshe", "C": "tantanin makwallato", "D": "huhu"}, "answer": "C"},
    {"stem": "Air is very important to be used by ----", "options": {"A": "huhu", "B": "makogoro", "C": "hakora", "D": "none of the above"}, "answer": "A"},
    {"stem": "An arrangement of word in order and gives meaning is called ---- in Hausa Language.", "options": {"A": "Jumla", "B": "magana", "C": "Abinci", "D": "Karatu"}, "answer": "A"},
    {"stem": "'Ina ne zaki?' da Turanci yana nufin ----", "options": {"A": "where are you going?", "B": "Come and eat.", "C": "what are you eating?", "D": "the boy is going."}, "answer": "A"},
    {"stem": "'Zan tafi gida' means ----", "options": {"A": "I am going home.", "B": "I am coming.", "C": "the man is dancing.", "D": "She is coming."}, "answer": "A"},
    {"stem": "The word 'Keep quiet' means ----", "options": {"A": "Yi dariya", "B": "Yi shiru", "C": "Yi kuka", "D": "Yi barci"}, "answer": "B"},
    {"stem": "'Shut up your mouth' simply means ----", "options": {"A": "rufe kofa", "B": "rufe kwano", "C": "rufe takarda", "D": "rufe mana baki"}, "answer": "D"},
    {"stem": "'Safe journey' yana nufin ----", "options": {"A": "Ina zuwa?", "B": "A sauka lafiya", "C": "Ina rawa", "D": "Zan tafi"}, "answer": "B"},
    {"stem": "Kalmar 'Makogoro' yana nufin ----", "options": {"A": "Tongue", "B": "Nose", "C": "Throat", "D": "Lips"}, "answer": "C"},
    {"stem": "'Welcome' yana nufin ----", "options": {"A": "Zo", "B": "tafi", "C": "Sannu da zuwa", "D": "Kwanta"}, "answer": "C"},
    {"stem": "The word 'Proverb' means ---- in Hausa language.", "options": {"A": "Hansi", "B": "Kafa", "C": "Karin magana", "D": "Magana"}, "answer": "C"},
    {"stem": "Stitch in time saves ----", "options": {"A": "Eight", "B": "Five", "C": "Three", "D": "Nine"}, "answer": "D"},
    {"stem": "To jump from ----", "options": {"A": "pot", "B": "bed", "C": "frying pan", "D": "a tree"}, "answer": "C"},
    {"stem": "'Prevention is better than cure' means ----", "options": {"A": "Ya kameta a hana", "B": "Baza a ji ba", "C": "Rigakafi yafi magani", "D": "Babu magani"}, "answer": "C"},
    {"stem": "Kidaya means ----", "options": {"A": "counting", "B": "number", "C": "a name", "D": "animal"}, "answer": "A"},
    {"stem": "Dari daya is equally means ----", "options": {"A": "10", "B": "20", "C": "1000", "D": "100"}, "answer": "D"},
    {"stem": "4 + 50 x 7 = 100", "options": {"A": "Dari", "B": "Talatin", "C": "Hamsin", "D": "Casa'ini"}, "answer": "A"},
    {"stem": "60 is also called ----", "options": {"A": "hamsin", "B": "Saba'in", "C": "Ashirin", "D": "Sitin"}, "answer": "D"},
    {"stem": "100 - 99 = 1", "options": {"A": "daya", "B": "uku", "C": "bude", "D": "biyu"}, "answer": "A"},
    {"stem": "40 ÷ 5 = 8", "options": {"A": "Goma", "B": "Ashirin", "C": "Takwas", "D": "Uku"}, "answer": "C"},
    {"stem": "All of these are Hausa food except ----", "options": {"A": "Tuwo", "B": "Fura", "C": "Shinkafa", "D": "Awara"}, "answer": "C"},
    {"stem": "Kuli-kuli is produced from ----", "options": {"A": "Doya", "B": "Gyada", "C": "Masara", "D": "Dankali"}, "answer": "B"},
    {"stem": "Awara is produced from ----", "options": {"A": "Doya", "B": "Gero", "C": "Wake", "D": "Waken suya"}, "answer": "D"},
    {"stem": "Alele is also known as ----", "options": {"A": "Stew", "B": "moin-moin", "C": "jollof rice", "D": "soup"}, "answer": "A"},
    {"stem": "'Kunu' is made up from ----", "options": {"A": "Gero", "B": "wake", "C": "Gwaza", "D": "Albasa"}, "answer": "A"},
    {"stem": "In Hausa land, food is eaten ---- times in a day.", "options": {"A": "2", "B": "1", "C": "3", "D": "4"}, "answer": "C"},
    {"stem": "'Nama' is translated as ---- in English language", "options": {"A": "salad", "B": "drinks", "C": "meat", "D": "egg"}, "answer": "C"},
    {"stem": "All these are Hausa names except ----", "options": {"A": "Musa", "B": "Ibrahim", "C": "Olu", "D": "Kabiru"}, "answer": "C"},
    {"stem": "Duk wadannan sunaye dabbobi ne sai dai ----", "options": {"A": "Adamu", "B": "Akuya", "C": "Alade", "D": "Talo-talo"}, "answer": "A"},
    {"stem": "Wadannan sunaye ne na zahiri sai dai ----", "options": {"A": "pencil", "B": "takarda", "C": "Kujera", "D": "soyayya"}, "answer": "D"},
    {"stem": "Fitar da sunan gari daga wadannan sunayen.", "options": {"A": "Daura", "B": "Ali", "C": "Musa", "D": "Abdullahi"}, "answer": "A"},
    {"stem": "Bring out the abstract noun from the following list.", "options": {"A": "dog", "B": "peace", "C": "bed", "D": "car"}, "answer": "B"},
    {"stem": "Insha'i means ---- in English language.", "options": {"A": "Literature", "B": "Essay Writing", "C": "Grammar", "D": "Phonology"}, "answer": "B"},
    {"stem": "All these are types of composition writing except ----", "options": {"A": "Narrative", "B": "Descriptive", "C": "Letter writing", "D": "Art and Culture"}, "answer": "D"},
    {"stem": "All these are conditions someone engaged in except ----", "options": {"A": "murna", "B": "halin tsoro", "C": "ciwo", "D": "All of the above"}, "answer": "D"},
    {"stem": "Mene ne kan ba mutum tsoro?", "options": {"A": "Driver", "B": "Snake", "C": "Abinci", "D": "Kudi"}, "answer": "B"},
    {"stem": "Wani hali ne yakan sa mutum yin kuka?", "options": {"A": "Enjoyment", "B": "Fear", "C": "Sadness", "D": "Tiredness"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Mene ne furuci?\n(b) Write five organs of speech you know.", "marks": Decimal("10.00")},
    {"stem": "2. Kawo sunayen wadannan adadin da Hausa:\n(a) 150\n(b) 600\n(c) 520\n(d) 710", "marks": Decimal("10.00")},
    {"stem": "3. Fito da abincin Bahaushe daga wadannan:\nSakwara, Kunu, Danwake, Miyar kuka, Tuwo, Shinkafa, Jollof rice, Iwedu soup, Masa, Waina da miya, Tuwon garin kwaki.", "marks": Decimal("10.00")},
    {"stem": "4. Kawo sunayen garuruwa kasar Hausa guda 5 da kin sani.", "marks": Decimal("10.00")},
    {"stem": "5. Define Essay writing (Rubutun Insha'i).\n(b) Write four types of essay writing in Hausa language.", "marks": Decimal("10.00")},
    {"stem": "6. Translate the following conditions into English language:\n(i) Halin jin dadi\n(ii) Halin bakin ciki\n(iii) Halin jin tsoro\n(iv) Halin gajiya", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="HAU")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS2 Hausa assignment found")
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
                rich_stem=item["stem"],
                marks=Decimal("1.00"),
                source_reference=f"JS2-HAU-L1-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS2-HAU-L1-20260326-TH-{index:02d}",
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
            "paper_code": "JS2-HAU-L1",
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
