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

TITLE = "THU 8:00-9:30 JS1 Hausa Language Second Term Exam"
DESCRIPTION = "JSS1 HAUSA LANGUAGE SECOND TERM EXAMINATION"
BANK_NAME = "JS1 Hausa Language Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all required questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Agogo in Hausa language means ____ in English.", "options": {"A": "house", "B": "book", "C": "clock", "D": "pencil"}, "answer": "C"},
    {"stem": "Dakika shi ne -------", "options": {"A": "seconds", "B": "minute", "C": "hours", "D": "days"}, "answer": "A"},
    {"stem": "How many minutes make 1 hour?", "options": {"A": "goma", "B": "talatin", "C": "hamsin", "D": "sittin"}, "answer": "D"},
    {"stem": "How many hours do we have in a day?", "options": {"A": "goma sha biyu", "B": "goma sha biyar", "C": "ashirin", "D": "ashirin da hudu"}, "answer": "D"},
    {"stem": "Amfanin Agogo shi ne ----", "options": {"A": "show us time", "B": "give us food", "C": "to sing for us", "D": "none of the above"}, "answer": "A"},
    {"stem": "In Nigeria, Hausa people are found in the ----", "options": {"A": "Kudu", "B": "Yamma", "C": "Arewa", "D": "gabas"}, "answer": "C"},
    {"stem": "Manyan koguna a Kasar Hausa guda naowa ne?", "options": {"A": "3", "B": "4", "C": "1", "D": "2"}, "answer": "D"},
    {"stem": "Daruzulka guda naowa ne muka da su a kasar Hausa?", "options": {"A": "2", "B": "4", "C": "5", "D": "3"}, "answer": "A"},
    {"stem": "The major Hausa occupations were ---- and ----", "options": {"A": "Karatu da rubutu", "B": "Fawa da su", "C": "Noma da kiwo", "D": "Kida da rawu"}, "answer": "C"},
    {"stem": "Duk wadannan jihokin kasar Hausa ne, sai", "options": {"A": "Sokoto", "B": "Gombe", "C": "Jos", "D": "Katsina"}, "answer": "C"},
    {"stem": "In Hausa Language, 'Abinci' means ----", "options": {"A": "cloth", "B": "Hand bag", "C": "food", "D": "school"}, "answer": "C"},
    {"stem": "Ground nut is ---- in Hausa language.", "options": {"A": "masara", "B": "soja", "C": "gyada", "D": "Dankale"}, "answer": "C"},
    {"stem": "Da wani hatsi ne ake toya Kosai da shi?", "options": {"A": "wake", "B": "rogo", "C": "Dawa", "D": "Rice"}, "answer": "A"},
    {"stem": "'Onions' is called ---- in Hausa language", "options": {"A": "Alayaho", "B": "Karas", "C": "Albasa", "D": "Timatir"}, "answer": "C"},
    {"stem": "'Rogo' shi ne ----", "options": {"A": "Rice", "B": "Beans", "C": "cassava", "D": "Yam"}, "answer": "C"},
    {"stem": "All of these are fruit except ---", "options": {"A": "Ayaba", "B": "Lemo", "C": "Mangworo", "D": "Gwaza"}, "answer": "D"},
    {"stem": "All the following are Hausa traditional food except ---", "options": {"A": "Sakwara", "B": "Fura", "C": "Dambu", "D": "Dan wake"}, "answer": "A"},
    {"stem": "100 in Hausa language is called ---", "options": {"A": "goma", "B": "hamsin", "C": "dari daya", "D": "ashirin"}, "answer": "C"},
    {"stem": "\"Dozin\" a Hausa yana nufin ---", "options": {"A": "10", "B": "12", "C": "15", "D": "20"}, "answer": "B"},
    {"stem": "Idan Bahaushe ya ce \"Dari da hamsin\" yana nufin", "options": {"A": "70", "B": "110", "C": "104", "D": "150"}, "answer": "D"},
    {"stem": "Adabi simply means --- in English", "options": {"A": "prose", "B": "drama", "C": "play", "D": "literature"}, "answer": "D"},
    {"stem": "How many types of Adabi do we have?", "options": {"A": "4", "B": "2", "C": "6", "D": "1"}, "answer": "B"},
    {"stem": "Which type of Adabi involves the use of drums and folk tales?", "options": {"A": "Gargajiya", "B": "Zamani", "C": "waka", "D": "None of the above"}, "answer": "A"},
    {"stem": "Yaushe aka fara Adabi a kasar Hausa?", "options": {"A": "1900", "B": "2022", "C": "1304", "D": "Ba wanda ya sani"}, "answer": "D"},
    {"stem": "All of these are the importance of Adabi except--------", "options": {"A": "Kebe tarihi", "B": "Sana'a", "C": "nuna al'adar bahaushe", "D": "niman fada"}, "answer": "D"},
    {"stem": "Duk wadannan Sunaye ne na Hausawa sai dai------", "options": {"A": "Joseph", "B": "Sani", "C": "Bello", "D": "Yakubu"}, "answer": "A"},
    {"stem": "Duk wadannan Sunaye ne na matan Hausawa sai dai---------", "options": {"A": "Ummi", "B": "Habiba", "C": "Khadija", "D": "Ruth"}, "answer": "D"},
    {"stem": "Duk wadannan Sunaye ne na dabbobi sai dai ---------", "options": {"A": "Kaza", "B": "Akuya", "C": "Rakumi", "D": "Keke"}, "answer": "D"},
    {"stem": "All the following are the names of things except-----", "options": {"A": "takarda", "B": "daki", "C": "Alade", "D": "Kujera"}, "answer": "B"},
    {"stem": "Mai suna 'dan Asabe' an haife shi ne ran ----", "options": {"A": "Asabar", "B": "Lahadi", "C": "Litinin", "D": "Talata"}, "answer": "A"},
    {"stem": "Idan an haifi mace a ranar Lahadi, akan kira ta da suna ----", "options": {"A": "Ladi/Ladidi", "B": "Talatu", "C": "Balaraba", "D": "Lami"}, "answer": "A"},
    {"stem": "A teacher in Hausa Language is called ----", "options": {"A": "Yaro", "B": "malam", "C": "Yaringa", "D": "Audu"}, "answer": "B"},
    {"stem": "A pronoun always represent a ---- in a sentence.", "options": {"A": "Aikatau", "B": "Sifa", "C": "Suna", "D": "Bayanai"}, "answer": "C"},
    {"stem": "All the following are good examples of a pronoun except ----", "options": {"A": "Ni", "B": "Ke", "C": "Su", "D": "Idris"}, "answer": "D"},
    {"stem": "The importance of a pronoun is to avoid ---- in a sentence", "options": {"A": "maimaici", "B": "jin dadi", "C": "People", "D": "Animals"}, "answer": "A"},
    {"stem": "Aikatau is called ---- in English.", "options": {"A": "preposition", "B": "Verb", "C": "Noun", "D": "Adjective"}, "answer": "B"},
    {"stem": "Musa yana cin shinkafa: Bring out the Aikatau from this sentence.", "options": {"A": "Musa", "B": "cin", "C": "Shinkafa", "D": "yana"}, "answer": "B"},
    {"stem": "This sign in Hausa Language (?) is called ----", "options": {"A": "Aya", "B": "Wukar", "C": "Alamar tambaya", "D": "Baka biyu"}, "answer": "C"},
    {"stem": "DUK WADANNAN ALAMOMIN RUBUTU NE SAI DAI", "options": {"A": "e;", "B": "-", "C": "!", "D": "m"}, "answer": "D"},
    {"stem": "Alamar motsin rai shi ne--------", "options": {"A": "__", "B": "?", "C": "!", "D": "/"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Kawo sunayen wadannan adadin da harshen Hausa:\n(a) 110\n(b) 70\n(c) 51\n(d) 8\n(e) 15", "marks": Decimal("10.00")},
    {"stem": "2. Zana hoton Agogo, sai ki nuna wadannan lokutan:\n(i) 12:10\n(ii) 12:30\n(iii) 1:40\n(b) Kawo sunayen biyu daga cikin wadannan da Hausa:\n(i) hours\n(ii) minute\n(iii) seconds", "marks": Decimal("10.00")},
    {"stem": "3. Rubuta sunayen kasashen Hausa guda biyar da kin sani.", "marks": Decimal("10.00")},
    {"stem": "4. Draw and label two types of food items that are obtainable in Hausa land.", "marks": Decimal("10.00")},
    {"stem": "5. Fito da Aikatau guda biyar a cikin wadannan jimlolin:\n(1) Musa ya ci tuwo\n(2) Malami yana rubutu\n(3) Talatu ta dafa rogo\n(4) Mairo ta wanke kwano\n(5) Bello ya kama kaza", "marks": Decimal("10.00")},
    {"stem": "6. Kawo sunayen wadannan alamomin rubutu:\n(i) .\n(ii) ?\n(iii) /\n(iv) -\n(v) -", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS1")
    subject = Subject.objects.get(code="HAU")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS1 Hausa assignment found")
    teacher = assignment.teacher

    existing = Exam.objects.filter(title=TITLE).order_by("-id").first()
    if existing and existing.attempts.exists():
        print({"created": False, "exam_id": existing.id, "reason": "existing exam already has attempts"})
        return

    schedule_start = timezone.make_aware(datetime(2026, 3, 26, 8, 0, 0), lagos)
    schedule_end = timezone.make_aware(datetime(2026, 3, 26, 9, 30, 0), lagos)

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
                source_reference=f"JS1-HAU-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS1-HAU-20260326-TH-{index:02d}",
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
            "paper_code": "JS1-HAU-EXAM",
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
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
        })

if __name__ == "__main__":
    main()
