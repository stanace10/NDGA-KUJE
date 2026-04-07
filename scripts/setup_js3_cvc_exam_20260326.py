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

TITLE = "THU 8:00-9:30 JS3 Civic Education Second Term Exam"
DESCRIPTION = "JS3 CIVIC EDUCATION SECOND TERM EXAMINATION"
BANK_NAME = "JS3 Civic Education Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any three questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Rule of law means", "options": {"A": "rule by the military", "B": "rule according to law", "C": "rule by the rich", "D": "rule by force"}, "answer": "B"},
    {"stem": "One major benefit of rule of law is", "options": {"A": "oppression", "B": "equality before the law", "C": "dictatorship", "D": "corruption"}, "answer": "B"},
    {"stem": "Under the rule of law, no one is", "options": {"A": "punished", "B": "arrested", "C": "above the law", "D": "protected"}, "answer": "C"},
    {"stem": "Breaking the law attracts", "options": {"A": "reward", "B": "promotion", "C": "punishment", "D": "praise"}, "answer": "C"},
    {"stem": "Rule of law promotes", "options": {"A": "favoritism", "B": "fairness", "C": "bribery", "D": "injustice"}, "answer": "B"},
    {"stem": "The rule of law helps to protect", "options": {"A": "criminals", "B": "human rights", "C": "only leaders", "D": "only the poor"}, "answer": "B"},
    {"stem": "A person who breaks the law may be punished by", "options": {"A": "fine", "B": "praise", "C": "promotion", "D": "award"}, "answer": "A"},
    {"stem": "Human rights are", "options": {"A": "privileges", "B": "party rights", "C": "fundamental rights", "D": "borrowed rights"}, "answer": "C"},
    {"stem": "Right to life means", "options": {"A": "freedom to travel", "B": "freedom to vote", "C": "freedom from unlawful killing", "D": "freedom to speak"}, "answer": "C"},
    {"stem": "Rule of law ensures that human rights are", "options": {"A": "abused", "B": "protected", "C": "ignored", "D": "suspended"}, "answer": "B"},
    {"stem": "Which body protects human rights in Nigeria?", "options": {"A": "Police", "B": "NDLEA", "C": "National Human Rights Commission", "D": "FRSC"}, "answer": "C"},
    {"stem": "Arrest without trial violates the", "options": {"A": "rule of law", "B": "civic duty", "C": "discipline", "D": "democracy"}, "answer": "A"},
    {"stem": "Which of the following enforces the law?", "options": {"A": "Judiciary", "B": "Police", "C": "Legislature", "D": "INEC"}, "answer": "B"},
    {"stem": "Law courts are responsible for", "options": {"A": "making laws", "B": "enforcing laws", "C": "interpreting laws", "D": "breaking laws"}, "answer": "C"},
    {"stem": "The legislature performs the function of", "options": {"A": "law enforcement", "B": "law interpretation", "C": "law making", "D": "punishment"}, "answer": "C"},
    {"stem": "Civil society organizations help to promote", "options": {"A": "injustice", "B": "lawlessness", "C": "human rights", "D": "corruption"}, "answer": "C"},
    {"stem": "A consumer is a person who", "options": {"A": "produces goods", "B": "advertises goods", "C": "buys goods and services", "D": "imports goods"}, "answer": "C"},
    {"stem": "Right to safety means the right to", "options": {"A": "cheap goods", "B": "quality goods", "C": "safe products", "D": "free goods"}, "answer": "C"},
    {"stem": "One consumer responsibility is to", "options": {"A": "cheat sellers", "B": "damage goods", "C": "pay for goods bought", "D": "steal goods"}, "answer": "C"},
    {"stem": "Right to information enables consumers to", "options": {"A": "know product details", "B": "break the law", "C": "refuse payment", "D": "hide facts"}, "answer": "A"},
    {"stem": "A dishonest consumer is one who", "options": {"A": "obeys rules", "B": "demands receipt", "C": "cheats sellers", "D": "reports fake goods"}, "answer": "C"},
    {"stem": "Democracy means", "options": {"A": "rule by the military", "B": "rule by one person", "C": "rule by the people", "D": "rule by elders"}, "answer": "C"},
    {"stem": "Leaders in a democracy are chosen through", "options": {"A": "inheritance", "B": "election", "C": "force", "D": "appointment"}, "answer": "B"},
    {"stem": "One feature of democracy is", "options": {"A": "dictatorship", "B": "rule of law", "C": "oppression", "D": "censorship"}, "answer": "B"},
    {"stem": "The executive arm of government is responsible for", "options": {"A": "making laws", "B": "interpreting laws", "C": "enforcing laws", "D": "amending laws"}, "answer": "C"},
    {"stem": "The judiciary performs the function of", "options": {"A": "law enforcement", "B": "law making", "C": "law interpretation", "D": "campaigning"}, "answer": "C"},
    {"stem": "The legislature consists of", "options": {"A": "courts", "B": "ministers", "C": "lawmakers", "D": "judges"}, "answer": "C"},
    {"stem": "Discipline means", "options": {"A": "obedience to rules", "B": "disobedience", "C": "stubbornness", "D": "violence"}, "answer": "A"},
    {"stem": "A disciplined student is", "options": {"A": "lazy", "B": "obedient", "C": "careless", "D": "rude"}, "answer": "B"},
    {"stem": "Courage means", "options": {"A": "fear", "B": "boldness", "C": "cowardice", "D": "weakness"}, "answer": "B"},
    {"stem": "Contentment means", "options": {"A": "greed", "B": "satisfaction", "C": "jealousy", "D": "envy"}, "answer": "B"},
    {"stem": "Contentment helps to reduce", "options": {"A": "honesty", "B": "peace", "C": "greed", "D": "patience"}, "answer": "C"},
    {"stem": "Federation means", "options": {"A": "concentration of power", "B": "sharing of power", "C": "military rule", "D": "dictatorship"}, "answer": "B"},
    {"stem": "Nigeria practices", "options": {"A": "unitary system", "B": "federal system", "C": "confederal system", "D": "monarchical system"}, "answer": "B"},
    {"stem": "One characteristic of federation is", "options": {"A": "central control", "B": "division of powers", "C": "military dominance", "D": "dictatorship"}, "answer": "B"},
    {"stem": "One need for federation is", "options": {"A": "oppression", "B": "unity in diversity", "C": "conflict", "D": "domination"}, "answer": "B"},
    {"stem": "Civic education teaches citizens their", "options": {"A": "crimes", "B": "duties and rights", "C": "punishments", "D": "weaknesses"}, "answer": "B"},
    {"stem": "One importance of civic education is that it", "options": {"A": "promotes violence", "B": "creates awareness", "C": "encourages crime", "D": "promotes corruption"}, "answer": "B"},
    {"stem": "A constitution is the", "options": {"A": "party rule", "B": "supreme law of a country", "C": "military order", "D": "school rule"}, "answer": "B"},
    {"stem": "A written constitution is", "options": {"A": "oral", "B": "documented", "C": "customary", "D": "unwritten"}, "answer": "B"},
    {"stem": "One importance of constitution is that it", "options": {"A": "limits government powers", "B": "encourages dictatorship", "C": "causes confusion", "D": "promotes corruption"}, "answer": "A"},
    {"stem": "The constitution helps to", "options": {"A": "protect human rights", "B": "ignore the law", "C": "promote injustice", "D": "create chaos"}, "answer": "A"},
    {"stem": "The Clifford Constitution was introduced in", "options": {"A": "1914", "B": "1922", "C": "1946", "D": "1954"}, "answer": "B"},
    {"stem": "One feature of the Clifford Constitution was", "options": {"A": "elective principle", "B": "universal suffrage", "C": "federal system", "D": "military rule"}, "answer": "A"},
    {"stem": "One merit of the Clifford Constitution was", "options": {"A": "Nigerians participated in governance", "B": "it encouraged dictatorship", "C": "no elections were held", "D": "it favored the military"}, "answer": "A"},
    {"stem": "One demerit of the Clifford Constitution was", "options": {"A": "limited franchise", "B": "too much freedom", "C": "federalism", "D": "democracy"}, "answer": "A"},
    {"stem": "Richards Constitution was introduced in", "options": {"A": "1922", "B": "1946", "C": "1951", "D": "1960"}, "answer": "B"},
    {"stem": "One feature of the Richards Constitution was", "options": {"A": "regional councils", "B": "military rule", "C": "unitary system", "D": "dictatorship"}, "answer": "A"},
    {"stem": "One merit of the Richards Constitution was", "options": {"A": "recognition of regional diversity", "B": "abolition of regions", "C": "military dominance", "D": "dictatorship"}, "answer": "A"},
    {"stem": "One demerit of the Richards Constitution was", "options": {"A": "it was imposed without consultation", "B": "it promoted democracy", "C": "it encouraged elections", "D": "it granted independence"}, "answer": "A"},
    {"stem": "The Nigerian currency is called", "options": {"A": "Dollar", "B": "Pound", "C": "Naira", "D": "Euro"}, "answer": "C"},
    {"stem": "One Nigerian coin is", "options": {"A": "N1000", "B": "N500", "C": "50 Kobo", "D": "N200"}, "answer": "C"},
    {"stem": "N1000 note carries the image of", "options": {"A": "Tafawa Balewa", "B": "Aliyu Mai-Bornu and Clement Isong", "C": "Nnamdi Azikiwe", "D": "Obafemi Awolowo"}, "answer": "B"},
    {"stem": "N100 note has the image of", "options": {"A": "Nnamdi Azikiwe", "B": "Obafemi Awolowo", "C": "Ahmadu Bello", "D": "Yakubu Gowon"}, "answer": "B"},
    {"stem": "Which of the following is a negative behaviour?", "options": {"A": "Honesty", "B": "Discipline", "C": "Stealing", "D": "Courage"}, "answer": "C"},
    {"stem": "Drug abuse is an example of", "options": {"A": "good habit", "B": "civic duty", "C": "negative behaviour", "D": "discipline"}, "answer": "C"},
    {"stem": "Examination malpractice is", "options": {"A": "rewarded", "B": "acceptable", "C": "illegal", "D": "encouraged"}, "answer": "C"},
    {"stem": "One effect of negative behaviour is", "options": {"A": "development", "B": "peace", "C": "social problems", "D": "progress"}, "answer": "C"},
    {"stem": "Truancy means", "options": {"A": "regular attendance", "B": "skipping school", "C": "obedience", "D": "punctuality"}, "answer": "B"},
    {"stem": "Fighting in school shows", "options": {"A": "courage", "B": "discipline", "C": "indiscipline", "D": "contentment"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Explain the meaning of rule of law.\n(b) State five benefits and three disadvantage.", "marks": Decimal("10.00")},
    {"stem": "2. Define democracy.\n(b) State four difference between the independence constitution of 1960 and 1963 Republican constitutions.", "marks": Decimal("10.00")},
    {"stem": "3. Explain election.\n(b) State four examples of election in Nigeria and four importance of election in a democratic state.", "marks": Decimal("10.00")},
    {"stem": "4. What is a constitution?\n(b) Explain its types and five importance.", "marks": Decimal("10.00")},
    {"stem": "5. Explain negative behavior.\n(b) State five types of negative behavior and three effects on the society.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS3")
    subject = Subject.objects.get(code="CVC")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS3 Civic assignment found")
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
                source_reference=f"JS3-CVC-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS3-CVC-20260326-TH-{index:02d}",
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
            "paper_code": "JS3-CVC-EXAM",
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
