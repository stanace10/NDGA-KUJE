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

TITLE = "THU 9:30-11:30 JS3 Hausa Language 1 Second Term Exam"
DESCRIPTION = "JSS 3 HAUSA LANGUAGE 1 SECOND TERM EXAMINATION"
BANK_NAME = "JS3 Hausa Language 1 Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Dahun dukkan tambayoyi a Sashe na A. A Sashe na B, amsa tambayoyi hudu. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Sana'ar 'Kira' shi ne ----- da Turanci", "options": {"A": "Blacksmith", "B": "Fishing", "C": "Farming", "D": "Teaching"}, "answer": "A"},
    {"stem": "The people that are into this occupation are called -----", "options": {"A": "makera", "B": "malamai", "C": "'yan kasuwa", "D": "'yan makaranta"}, "answer": "A"},
    {"stem": "Masu kira suna yin amfani ne ----- in their place of work", "options": {"A": "Fata", "B": "takardu", "C": "Karfe", "D": "Keken dinki"}, "answer": "C"},
    {"stem": "Masu kira suna samar da -----", "options": {"A": "Riga", "B": "wando", "C": "Garma", "D": "mabudi"}, "answer": "C"},
    {"stem": "Duk wadannan kayayyakin Kira ne sai dai -----", "options": {"A": "Lauje", "B": "adda", "C": "wuka", "D": "Kwando"}, "answer": "D"},
    {"stem": "How will you apologize in Hausa language?", "options": {"A": "Kai zo nan!", "B": "Bani zuciga", "C": "don Allah yi hakuri", "D": "Dawo"}, "answer": "C"},
    {"stem": "Yaya ne akan roki ruwan sha?", "options": {"A": "Don Allah kawo mani ruwa", "B": "Dawo gida", "C": "Ka zo don Allah", "D": "Karbi tuwo"}, "answer": "A"},
    {"stem": "Duk wadannan hanyoyi ne na yadda ake amsa rokon taimako sai dai -----", "options": {"A": "To", "B": "Ga shi", "C": "To, ga su", "D": "Allah kiyaye"}, "answer": "D"},
    {"stem": "Yaya ake yin godiya?", "options": {"A": "Na gode", "B": "Waiyo Allah", "C": "Sam sam", "D": "Tashi"}, "answer": "A"},
    {"stem": "'Don Allah' simply means -----", "options": {"A": "Because of you", "B": "I don't know you", "C": "For goodness sake", "D": "All of the above"}, "answer": "C"},
    {"stem": "'Wane ne sunan ki?' simply means -----", "options": {"A": "Who is your teacher?", "B": "What is your name?", "C": "What tribe are you?", "D": "How old are you?"}, "answer": "B"},
    {"stem": "How do you answer this greeting 'Sannu da hutawa'?", "options": {"A": "Yauwa sannu", "B": "da sauki", "C": "Na gode", "D": "Lafiya"}, "answer": "A"},
    {"stem": "'Zo mu tafi' means -----", "options": {"A": "run away", "B": "come and eat", "C": "come let us go", "D": "come and sit down"}, "answer": "C"},
    {"stem": "'Wani irin abinci ne ka fi so?' means -----", "options": {"A": "What do you care for?", "B": "How old are you?", "C": "Where are you coming from", "D": "Where are you going?"}, "answer": "A"},
    {"stem": "'Wane ne sunan malamin ka?' means -----", "options": {"A": "what is the name of your teacher", "B": "who is your brother", "C": "who is your grandfather?", "D": "what is your occupation?"}, "answer": "A"},
    {"stem": "'Kande tana dafa abinci' means -----", "options": {"A": "Kande is sleeping", "B": "Kande is washing cloth", "C": "Kande is dancing", "D": "Kande is cooking"}, "answer": "D"},
    {"stem": "'Bala yana faskare ice' means -----", "options": {"A": "Bala is breaking fire wood", "B": "Bala is dancing", "C": "Bala is drawing fire wood", "D": "Bala is piling fire wood"}, "answer": "A"},
    {"stem": "'Fatima tana share aji' means -----", "options": {"A": "Fatima is mopping a class", "B": "Fatima is sweeping a class", "C": "Fatima is walking round the class", "D": "Fatima is doing nothing in the class"}, "answer": "B"},
    {"stem": "'Mene ne kake yi?' means -----", "options": {"A": "What are you doing", "B": "Where are you coming from", "C": "What can you do", "D": "How do you do it?"}, "answer": "A"},
    {"stem": "'Zan tafi gobe' means -----", "options": {"A": "I will go tomorrow", "B": "I am not going", "C": "they are going", "D": "all of the above"}, "answer": "A"},
    {"stem": "'Fassara da Turanci' shi ake kira --------", "options": {"A": "Reading", "B": "writing", "C": "translation", "D": "Resting"}, "answer": "C"},
    {"stem": "January = -----", "options": {"A": "Jamus", "B": "James", "C": "Janairu", "D": "Jauro"}, "answer": "C"},
    {"stem": "Maris = -----", "options": {"A": "may", "B": "march", "C": "mayu", "D": "juli"}, "answer": "B"},
    {"stem": "August = -----", "options": {"A": "Augusta", "B": "Augustine", "C": "Audu", "D": "Auta"}, "answer": "A"},
    {"stem": "Which is the shortest month in the year?", "options": {"A": "mayu", "B": "Satamba", "C": "Nuwamba", "D": "Febrairu"}, "answer": "D"},
    {"stem": "Muna da watani nawa ne a shekara?", "options": {"A": "7", "B": "6", "C": "10", "D": "12"}, "answer": "D"},
    {"stem": "'Mother' means -----", "options": {"A": "Baba", "B": "Kaka", "C": "mama", "D": "yaya"}, "answer": "C"},
    {"stem": "Father in-law in Hausa language is called -----", "options": {"A": "Suruki", "B": "Sarki", "C": "yaya", "D": "iyar uwa"}, "answer": "A"},
    {"stem": "While 'gwaggo' in English is called -----", "options": {"A": "sister", "B": "Aunt", "C": "mother in-law", "D": "wife"}, "answer": "B"},
    {"stem": "The word 'Relation' in Hausa language is called -----", "options": {"A": "gida", "B": "gari", "C": "dangi", "D": "dadi"}, "answer": "C"},
    {"stem": "Animals are called ------ in Hausa", "options": {"A": "Dabbobi", "B": "gida", "C": "motoci", "D": "Abinci"}, "answer": "A"},
    {"stem": "Monkey is also called ---- in Hausa language", "options": {"A": "Kura", "B": "Biri", "C": "Kare", "D": "Kaza"}, "answer": "B"},
    {"stem": "'Kifi' is known as ....... in English language.", "options": {"A": "Snake", "B": "Fish", "C": "Goat", "D": "Rat"}, "answer": "B"},
    {"stem": "'Zomo' is known as ..... in English", "options": {"A": "Rat", "B": "dog", "C": "Rabbit", "D": "Ram"}, "answer": "C"},
    {"stem": "Child bearing in Hausa language is called ----", "options": {"A": "Suna", "B": "mutuwa", "C": "yaye", "D": "Haihuwa"}, "answer": "D"},
    {"stem": "------ is another name for twins in Hausa language.", "options": {"A": "Bomboi", "B": "bebe", "C": "'yan biyu", "D": "Taro"}, "answer": "C"},
    {"stem": "Naming ceremony takes place after how many days in Hausa land?", "options": {"A": "4", "B": "5", "C": "7", "D": "3"}, "answer": "C"},
    {"stem": "Mace tana wankan safe da yamma har na kwana nawa a kasar Hausa?", "options": {"A": "30", "B": "10", "C": "20", "D": "40"}, "answer": "D"},
    {"stem": "Wace ce mai karbar haihuwa a kasar Hausa?", "options": {"A": "Alkali", "B": "Baba", "C": "Mallama", "D": "Ungozoma"}, "answer": "D"},
    {"stem": "Wane ne ke rada suna idan an haihu a kasar Hausa?", "options": {"A": "Liman", "B": "Baba", "C": "Mama", "D": "Kaka"}, "answer": "A"},
    {"stem": "The word 'Mat' is ---- in Hausa", "options": {"A": "Riga", "B": "Tabarma", "C": "Kwano", "D": "Tsintsiya"}, "answer": "B"},
    {"stem": "Curtain is known as ----- in Hausa", "options": {"A": "Kujara", "B": "Cokali", "C": "Labule", "D": "Gado"}, "answer": "C"},
    {"stem": "Pillows in Hausa language is called -----", "options": {"A": "Filo", "B": "Teburi", "C": "daki", "D": "Sanda"}, "answer": "A"},
    {"stem": "We use bed in our various houses to ----- on", "options": {"A": "Zama", "B": "kwanciya", "C": "zuba ruwa", "D": "all of the above"}, "answer": "B"},
    {"stem": "'Chair' shi ne ----- da Hausa.", "options": {"A": "Kujera", "B": "wuta", "C": "Sanda", "D": "window"}, "answer": "A"},
    {"stem": "A naming ceremony in Hausa land takes place after ..... days", "options": {"A": "5", "B": "2", "C": "6", "D": "7"}, "answer": "D"},
    {"stem": "Who is in charge of that occasion?", "options": {"A": "Liman", "B": "Baba", "C": "Mama", "D": "Kaka"}, "answer": "A"},
    {"stem": "Wankan jego takes place only when a woman is ......", "options": {"A": "pregnant", "B": "delivered", "C": "married", "D": "divorced"}, "answer": "B"},
    {"stem": "Hausa people are allowed to circumcise their male children after how many days?", "options": {"A": "10", "B": "12", "C": "8", "D": "7"}, "answer": "D"},
    {"stem": "During naming ceremony, the father must slaughter ......", "options": {"A": "Kare", "B": "Kaza", "C": "Akuya / Rago", "D": "Zomo"}, "answer": "C"},
    {"stem": "All these are Hausa occupation except --", "options": {"A": "Noma", "B": "Kiwo", "C": "Kira", "D": "All of the above"}, "answer": "D"},
    {"stem": "What is magani?", "options": {"A": "Farming", "B": "Studies", "C": "medicine", "D": "None of the above"}, "answer": "C"},
    {"stem": "These people can give 'magani' except ---", "options": {"A": "Boka", "B": "magori", "C": "Wanzami", "D": "dukansu"}, "answer": "D"},
    {"stem": "'Honesty' in Hausa is called ---", "options": {"A": "Halin mugunta", "B": "Halin sata", "C": "Halin kyauta", "D": "Halin nagarta"}, "answer": "D"},
    {"stem": "All these are the characteristics of honesty except ---", "options": {"A": "Sata", "B": "gaskiya", "C": "taimako", "D": "Adini"}, "answer": "A"},
    {"stem": "The people that use iron to make a hoe, cutlass, knives are called ---", "options": {"A": "masunta", "B": "manoma", "C": "makera", "D": "malamai"}, "answer": "C"},
    {"stem": "A village square where Hausa acted their drama is called ... in Hausa language", "options": {"A": "gida", "B": "makaranta", "C": "Dandali", "D": "Kasuwa"}, "answer": "C"},
    {"stem": "'Wasan kwaikwayo' means ... in English", "options": {"A": "prose", "B": "poetry", "C": "Drama", "D": "Drum"}, "answer": "C"},
    {"stem": "Poetry is called ... in Hausa language", "options": {"A": "rawa", "B": "waka", "C": "kida", "D": "Dambe"}, "answer": "B"},
    {"stem": "Mutum nawa ne sukan iya shiga cikin wasan kwaikwayo a kasar Hausa?", "options": {"A": "So many", "B": "5", "C": "7", "D": "8"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. Write five 'command' statements in Hausa.", "marks": Decimal("10.00")},
    {"stem": "2. Rubuta kalmomi guda biyar na neman alfarma da ka sani.", "marks": Decimal("10.00")},
    {"stem": "3. Sana'ar Kira: Kawo abubuwan da ake samu a wannan sana'a guda biyar.", "marks": Decimal("10.00")},
    {"stem": "4. Rubuta kayan adon mata guda biyar da kin sani.", "marks": Decimal("10.00")},
    {"stem": "5. Kawo jam'in wadannan sunayen:\n(i) mutum\n(ii) yaro\n(iii) riga\n(iv) wando\n(v) takalma", "marks": Decimal("10.00")},
    {"stem": "6. Translate the following into English language:\n(a) Baba\n(b) Kaka\n(c) Kawo\n(d) Ika", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="HAU")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS3 Hausa assignment found")
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
                source_reference=f"JS3-HAU-L1-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS3-HAU-L1-20260326-TH-{index:02d}",
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
            "paper_code": "JS3-HAU-L1",
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
