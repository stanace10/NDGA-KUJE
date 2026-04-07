from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
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


TITLE = "WED 1:00-2:30 SS2 Economics Second Term Exam"
DESCRIPTION = "SS2 ECONOMICS SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Economics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four essay questions. "
    "Timer is 90 minutes. Exam window closes at 2:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "An economic system refers to ______.", "options": {"A": "the pattern of government elections in a country", "B": "the method a society uses to allocate scarce resources", "C": "the system of taxation adopted by a nation", "D": "the process of determining wages in industries"}, "answer": "B"},
    {"stem": "In a centrally planned economic system, major economic decisions are made mainly by ______.", "options": {"A": "consumers", "B": "producers", "C": "government authorities", "D": "trade unions"}, "answer": "C"},
    {"stem": "A key feature of a market economic system is ______.", "options": {"A": "government ownership of resources", "B": "price mechanism determining resource allocation", "C": "absence of private enterprise", "D": "prohibition of competition"}, "answer": "B"},
    {"stem": "Which of the following is an advantage of a market economy?", "options": {"A": "Lack of innovation", "B": "Efficient allocation of resources through price signals", "C": "Elimination of private ownership", "D": "Centralized decision making"}, "answer": "B"},
    {"stem": "One disadvantage of a command economy is ______.", "options": {"A": "income equality", "B": "government planning", "C": "inefficiency due to lack of competition", "D": "stable prices"}, "answer": "C"},
    {"stem": "Which of the following countries historically practiced a command economic system?", "options": {"A": "China", "B": "United States", "C": "Canada", "D": "Australia"}, "answer": "A"},
    {"stem": "A mixed economy is characterized by ______.", "options": {"A": "absence of government intervention", "B": "combination of private and government ownership", "C": "elimination of competition", "D": "exclusive public ownership"}, "answer": "B"},
    {"stem": "Which of the following is a feature of a traditional economic system?", "options": {"A": "Use of sophisticated technology", "B": "Production guided by customs and traditions", "C": "High level of industrialization", "D": "Central government planning"}, "answer": "B"},
    {"stem": "The labour market refers to ______.", "options": {"A": "a market where machines are sold", "B": "the interaction between employers and workers for employment", "C": "a market where goods are exchanged", "D": "the place where agricultural products are sold"}, "answer": "B"},
    {"stem": "Demand for labour is said to be derived demand because ______.", "options": {"A": "labour creates demand for goods", "B": "labour demand depends on demand for the goods produced", "C": "labour demand is determined by workers", "D": "labour demand is fixed by law"}, "answer": "B"},
    {"stem": "Which of the following factors can increase the demand for labour?", "options": {"A": "fall in demand for goods", "B": "improvement in production technology requiring skilled labour", "C": "increase in labour cost", "D": "decrease in productivity"}, "answer": "B"},
    {"stem": "An increase in the price of a product will likely ______.", "options": {"A": "reduce labour demand", "B": "increase labour demand", "C": "eliminate labour demand", "D": "have no effect on labour demand"}, "answer": "B"},
    {"stem": "Supply of labour refers to ______.", "options": {"A": "the total number of machines available for work", "B": "the number of workers willing and able to work at various wage rates", "C": "the total population of a country", "D": "the number of unemployed persons"}, "answer": "B"},
    {"stem": "One factor influencing the supply of labour is ______.", "options": {"A": "climate conditions only", "B": "wage rate offered", "C": "price of raw materials", "D": "number of factories"}, "answer": "B"},
    {"stem": "Which of the following may reduce labour supply in a particular occupation?", "options": {"A": "improved working conditions", "B": "higher wages", "C": "occupational hazards", "D": "training opportunities"}, "answer": "C"},
    {"stem": "Wage rate refers to ______.", "options": {"A": "total income of a worker", "B": "payment made to labour for services rendered", "C": "profit made by firms", "D": "payment for raw materials"}, "answer": "B"},
    {"stem": "One determinant of wage rate is ______.", "options": {"A": "productivity of labour", "B": "population size only", "C": "price of exports", "D": "government revenue"}, "answer": "A"},
    {"stem": "Skilled workers usually earn higher wages because ______.", "options": {"A": "they work fewer hours", "B": "they have specialized training and productivity", "C": "they are unemployed", "D": "they are government workers"}, "answer": "B"},
    {"stem": "Trade unions influence wages mainly through ______.", "options": {"A": "agricultural production", "B": "collective bargaining", "C": "tax payment", "D": "international trade"}, "answer": "B"},
    {"stem": "One weapon used by trade unions to press their demands is ______.", "options": {"A": "taxation", "B": "strike action", "C": "importation", "D": "industrial licensing"}, "answer": "B"},
    {"stem": "Unemployment refers to ______.", "options": {"A": "people who are not working and not willing to work", "B": "people willing and able to work but unable to find jobs", "C": "people working part-time", "D": "retired workers"}, "answer": "B"},
    {"stem": "Structural unemployment occurs mainly due to ______.", "options": {"A": "seasonal changes", "B": "mismatch between skills and job requirements", "C": "temporary illness", "D": "bad weather"}, "answer": "B"},
    {"stem": "Seasonal unemployment is common in ______.", "options": {"A": "banking sector", "B": "agriculture", "C": "insurance", "D": "telecommunications"}, "answer": "B"},
    {"stem": "Frictional unemployment occurs when ______.", "options": {"A": "workers move between jobs", "B": "workers refuse to work", "C": "industries collapse permanently", "D": "government policies fail"}, "answer": "A"},
    {"stem": "Cyclical unemployment is associated with ______.", "options": {"A": "economic downturns", "B": "population growth", "C": "education policies", "D": "agricultural seasons"}, "answer": "A"},
    {"stem": "Utility in economics refers to ______.", "options": {"A": "usefulness of a product in satisfying human wants", "B": "price of a commodity", "C": "production of goods", "D": "cost of transportation"}, "answer": "A"},
    {"stem": "Total utility refers to ______.", "options": {"A": "additional satisfaction from consuming one more unit", "B": "sum of satisfaction from all units consumed", "C": "utility from substitutes", "D": "market price of goods"}, "answer": "B"},
    {"stem": "Marginal utility refers to ______.", "options": {"A": "total satisfaction obtained from consumption", "B": "additional satisfaction from consuming one more unit", "C": "satisfaction from the first unit only", "D": "reduction in satisfaction"}, "answer": "B"},
    {"stem": "The law of diminishing marginal utility states that ______.", "options": {"A": "satisfaction increases indefinitely", "B": "marginal utility decreases as more units are consumed", "C": "price remains constant", "D": "demand becomes unlimited"}, "answer": "B"},
    {"stem": "Utility curves are commonly represented using ______.", "options": {"A": "tables only", "B": "graphs", "C": "essays", "D": "photographs"}, "answer": "B"},
    {"stem": "Manufacturing industries are those that ______.", "options": {"A": "extract minerals from the earth", "B": "convert raw materials into finished goods", "C": "distribute goods to retailers", "D": "produce agricultural crops"}, "answer": "B"},
    {"stem": "Construction industry mainly deals with ______.", "options": {"A": "building infrastructure such as roads and houses", "B": "manufacturing textiles", "C": "selling imported goods", "D": "agricultural production"}, "answer": "A"},
    {"stem": "A characteristic of the Nigerian manufacturing sector is ______.", "options": {"A": "high dependence on imported raw materials", "B": "absence of labour", "C": "low capital requirement", "D": "no government regulation"}, "answer": "A"},
    {"stem": "Industries can be classified based on ______.", "options": {"A": "colour of products", "B": "stages of production", "C": "personal preferences", "D": "population size"}, "answer": "B"},
    {"stem": "Cottage industries are usually ______.", "options": {"A": "large-scale and capital intensive", "B": "small-scale and family owned", "C": "multinational industries", "D": "government owned industries"}, "answer": "B"},
    {"stem": "Local craft industries commonly produce ______.", "options": {"A": "handmade goods using simple tools", "B": "complex machinery", "C": "petroleum products", "D": "automobiles"}, "answer": "A"},
    {"stem": "Modern factories are characterized by ______.", "options": {"A": "advanced machinery and mass production", "B": "manual labour only", "C": "absence of capital", "D": "small-scale production"}, "answer": "A"},
    {"stem": "One contribution of the industrial sector to economic development is ______.", "options": {"A": "reduction in employment opportunities", "B": "creation of jobs", "C": "elimination of trade", "D": "decline in production"}, "answer": "B"},
    {"stem": "Industrialization promotes economic development through ______.", "options": {"A": "technological advancement", "B": "discouraging innovation", "C": "reducing productivity", "D": "eliminating exports"}, "answer": "A"},
    {"stem": "One major problem of the manufacturing sector in Nigeria is ______.", "options": {"A": "adequate infrastructure", "B": "irregular power supply", "C": "surplus capital", "D": "excess labour demand"}, "answer": "B"},
    {"stem": "Another challenge facing manufacturing industries is ______.", "options": {"A": "stable electricity supply", "B": "poor transportation network", "C": "efficient banking services", "D": "government subsidies"}, "answer": "B"},
    {"stem": "A possible solution to industrial problems is ______.", "options": {"A": "improving power supply", "B": "banning industrial production", "C": "reducing capital investment", "D": "discouraging entrepreneurship"}, "answer": "A"},
    {"stem": "Financial regulatory agencies are institutions that ______.", "options": {"A": "control financial activities and institutions", "B": "produce goods for export", "C": "regulate agriculture", "D": "manufacture equipment"}, "answer": "A"},
    {"stem": "The primary regulatory authority for banks in Nigeria is ______.", "options": {"A": "Central Bank of Nigeria", "B": "Ministry of Agriculture", "C": "Nigerian Railway Corporation", "D": "Nigerian Ports Authority"}, "answer": "A"},
    {"stem": "The Nigeria Deposit Insurance Corporation is responsible for ______.", "options": {"A": "insuring bank deposits", "B": "building roads", "C": "controlling imports", "D": "collecting taxes"}, "answer": "A"},
    {"stem": "The Securities and Exchange Commission regulates ______.", "options": {"A": "stock market activities", "B": "agricultural products", "C": "mining activities", "D": "labour unions"}, "answer": "A"},
    {"stem": "The National Insurance Commission regulates ______.", "options": {"A": "mining companies", "B": "insurance businesses", "C": "agricultural cooperatives", "D": "petroleum companies"}, "answer": "B"},
    {"stem": "Regulatory agencies ensure financial institutions operate with ______.", "options": {"A": "transparency and accountability", "B": "secrecy and monopoly", "C": "unlimited borrowing", "D": "price control only"}, "answer": "A"},
    {"stem": "Effective financial regulation helps to ______.", "options": {"A": "destabilize the economy", "B": "maintain stability in the financial system", "C": "reduce savings", "D": "discourage investment"}, "answer": "B"},
    {"stem": "One objective of financial regulation is to ______.", "options": {"A": "protect depositors and investors", "B": "eliminate banking services", "C": "reduce employment", "D": "discourage economic growth"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. (a) Explain five major reasons for wage rate variation.\n(b) Discuss three advantages and three disadvantages of each system.", "marks": Decimal('10.00')},
    {"stem": "2. (a) Define labour market and explain four factors affecting the demand for labour.\n(b) Discuss four determinants of wage rate in an economy.", "marks": Decimal('10.00')},
    {"stem": "3. (a) Explain the concept of unemployment.\n(b) In a tabular form, describe five types of unemployment and their causes.", "marks": Decimal('10.00')},
    {"stem": "4. (a) Explain the concept of utility and distinguish between total utility and marginal utility.\n(b) Explain five weapons used by labour union.", "marks": Decimal('10.00')},
    {"stem": "5. (a) Explain the meaning of the manufacturing and construction industries and describe the characteristics of the Nigerian manufacturing sector.\n(b) Discuss five differences between light and heavy industry.", "marks": Decimal('10.00')},
    {"stem": "6. (a) What do you understand by financial institution, and identify five functions of the central bank?\n(b) In tabular form, give five differences between commercial and central bank.", "marks": Decimal('10.00')},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="ECO")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="fadumo@ndgakuje.org",
        academic_class=academic_class,
        subject=subject,
        session=session,
        term=term,
        is_active=True,
    )
    teacher = assignment.teacher
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 25, 13, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 14, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Wednesday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 1:00 PM WAT.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts. Refusing to overwrite live content.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for Wednesday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 1:00 PM WAT."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    ExamQuestion.objects.filter(exam=exam).delete()
    bank.questions.all().delete()

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
            source_reference=f"SS2-ECO-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS2-ECO-20260325-TH-{index:02d}",
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
        "paper_code": "SS2-ECO-EXAM",
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
