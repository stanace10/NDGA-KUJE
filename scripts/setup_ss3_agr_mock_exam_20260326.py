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

TITLE = "THU 9:30-11:00 SS3 Agricultural Science Second Term Mock Exam"
DESCRIPTION = "SS 3 AGRICULTURAL SCIENCE SECOND TERM MOCK EXAMINATION"
BANK_NAME = "SS3 Agricultural Science Mock Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 11:00 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "The process of moving farm produce from producers to consumers is called ______.", "options": {"A": "Warehousing", "B": "Marketing", "C": "Advertising", "D": "Production"}, "answer": "B"},
    {"stem": "Which of the following is a function of marketing?", "options": {"A": "Soil testing", "B": "Transportation", "C": "Irrigation", "D": "Pruning"}, "answer": "B"},
    {"stem": "Middlemen in agricultural marketing are also known as ______.", "options": {"A": "Wholesalers", "B": "Intermediaries", "C": "Retailers", "D": "Consumers"}, "answer": "B"},
    {"stem": "Standardization in marketing refers to ______.", "options": {"A": "Grading produce", "B": "Advertising", "C": "Packaging", "D": "Fixing prices"}, "answer": "A"},
    {"stem": "The main aim of a marketing board is to ______.", "options": {"A": "Destroy surplus", "B": "Sell farmers' produce", "C": "Fix land rent", "D": "Train farmers"}, "answer": "B"},
    {"stem": "A major factor affecting agricultural marketing is ______.", "options": {"A": "Climate", "B": "Social media", "C": "Good road network", "D": "School fees"}, "answer": "C"},
    {"stem": "Farm gate marketing means selling farm produce ______.", "options": {"A": "in the town", "B": "at the farm", "C": "through an agent", "D": "through the internet"}, "answer": "B"},
    {"stem": "Which of the following does NOT affect price of agricultural produce?", "options": {"A": "Demand", "B": "Supply", "C": "Weather", "D": "Colour of farmer's clothes"}, "answer": "D"},
    {"stem": "A well-organized marketing system encourages farmers to ______.", "options": {"A": "stop farming", "B": "produce more", "C": "hoard food", "D": "increase prices unnecessarily"}, "answer": "B"},
    {"stem": "The location where buyers and sellers meet to exchange goods is called ______.", "options": {"A": "Market", "B": "Warehouse", "C": "Bank", "D": "Agency"}, "answer": "A"},
    {"stem": "Perishable farm produce requires ______.", "options": {"A": "Cold storage", "B": "Subsidy", "C": "Training", "D": "Water pumps"}, "answer": "A"},
    {"stem": "Agricultural extension is mainly concerned with ______.", "options": {"A": "Loan repayment", "B": "Educating farmers", "C": "Road construction", "D": "Importing food"}, "answer": "B"},
    {"stem": "A good extension agent should possess ______.", "options": {"A": "Poor communication skills", "B": "Technical knowledge", "C": "Dishonesty", "D": "Laziness"}, "answer": "B"},
    {"stem": "The main tool of agricultural extension is ______.", "options": {"A": "Law making", "B": "Teaching", "C": "Tax collection", "D": "Subsidy removal"}, "answer": "B"},
    {"stem": "Demonstration plots are used to ______.", "options": {"A": "showcase proven technologies", "B": "sell land", "C": "build classrooms", "D": "train soldiers"}, "answer": "A"},
    {"stem": "One-to-one contact method is called ______.", "options": {"A": "Office call", "B": "Individual method", "C": "Group method", "D": "Mass method"}, "answer": "B"},
    {"stem": "Radio and television belong to ______ methods.", "options": {"A": "Mass", "B": "Group", "C": "Individual", "D": "Manual"}, "answer": "A"},
    {"stem": "Which is NOT a function of extension service?", "options": {"A": "Dissemination of information", "B": "Helping farmers adopt innovations", "C": "Community leadership training", "D": "Construction of roads"}, "answer": "D"},
    {"stem": "Which of the following is an extension teaching method?", "options": {"A": "Litigation", "B": "Farm visits", "C": "Surgery", "D": "Auditing"}, "answer": "B"},
    {"stem": "The adoption of innovation means ______.", "options": {"A": "rejection of technology", "B": "modification of tools", "C": "acceptance and use of technology", "D": "abandonment of tools"}, "answer": "C"},
    {"stem": "Short-term loans are repaid within ______.", "options": {"A": "1 year", "B": "5 years", "C": "10 years", "D": "20 years"}, "answer": "A"},
    {"stem": "One of the sources of agricultural finance is ______.", "options": {"A": "Weather", "B": "Commercial banks", "C": "Soil erosion", "D": "Pest attack"}, "answer": "B"},
    {"stem": "Collateral is ______.", "options": {"A": "Farm record", "B": "Item used to secure a loan", "C": "Farm tool", "D": "Labour type"}, "answer": "B"},
    {"stem": "Interest on loan is ______.", "options": {"A": "Money borrowed", "B": "Cost of borrowing", "C": "Free credit", "D": "Loan refusal"}, "answer": "B"},
    {"stem": "A farmer who borrows money must sign a ______.", "options": {"A": "Bill of lading", "B": "Loan agreement", "C": "Rent receipt", "D": "Salary voucher"}, "answer": "B"},
    {"stem": "Working capital includes ______.", "options": {"A": "Land", "B": "Fertilizers", "C": "Buildings", "D": "Tractors"}, "answer": "B"},
    {"stem": "The major limitation of informal credit sources is ______.", "options": {"A": "No collateral", "B": "Low interest", "C": "Limited funds", "D": "Easy access"}, "answer": "C"},
    {"stem": "The record used to summarize daily farm activities is ______.", "options": {"A": "Inventory", "B": "Diary", "C": "Sales book", "D": "Journal"}, "answer": "B"},
    {"stem": "Assets minus liabilities equal ______.", "options": {"A": "Profit", "B": "Capital", "C": "Loss", "D": "Budget"}, "answer": "B"},
    {"stem": "The record showing all farm expenses is ______.", "options": {"A": "Expenditure record", "B": "Sales record", "C": "Inventory", "D": "Profit and loss"}, "answer": "A"},
    {"stem": "Fixed assets include ______.", "options": {"A": "Seedlings", "B": "Fertilizer", "C": "Buildings", "D": "Pesticides"}, "answer": "C"},
    {"stem": "Depreciation means ______.", "options": {"A": "Increase in value", "B": "Decrease in value", "C": "Loan repayment", "D": "Labour cost"}, "answer": "B"},
    {"stem": "A balance sheet shows ______.", "options": {"A": "Profit only", "B": "Loss only", "C": "Financial position", "D": "Future plans"}, "answer": "C"},
    {"stem": "The record of goods bought on credit is ______.", "options": {"A": "Sales book", "B": "Purchases book", "C": "Ledger", "D": "Invoice"}, "answer": "B"},
    {"stem": "Farm inventory includes ______.", "options": {"A": "Crop yield", "B": "List of farm properties", "C": "Soil type", "D": "Rainfall amount"}, "answer": "B"},
    {"stem": "Variable cost includes ______.", "options": {"A": "Rent", "B": "Tractor", "C": "Seeds", "D": "Land"}, "answer": "C"},
    {"stem": "The document issued to a buyer after payment is ______.", "options": {"A": "Invoice", "B": "Receipt", "C": "Quotation", "D": "Statement"}, "answer": "B"},
    {"stem": "A ledger is used to ______.", "options": {"A": "record weather", "B": "keep accounts", "C": "store seeds", "D": "rear animals"}, "answer": "B"},
    {"stem": "A farm budget helps in ______.", "options": {"A": "predicting future income", "B": "increasing diseases", "C": "reducing soil fertility", "D": "buying land alone"}, "answer": "A"},
    {"stem": "Another name for the source document is ______.", "options": {"A": "Evidence of transaction", "B": "Crop yield", "C": "Soil test", "D": "Weather data"}, "answer": "A"},
    {"stem": "The closing inventory is the value of goods ______.", "options": {"A": "at the beginning", "B": "still remaining", "C": "sold", "D": "lost"}, "answer": "B"},
    {"stem": "Agricultural insurance protects farmers against ______.", "options": {"A": "Profit", "B": "Loss", "C": "High yield", "D": "Good weather"}, "answer": "B"},
    {"stem": "The amount paid regularly to an insurance company is ______.", "options": {"A": "Premium", "B": "Claim", "C": "Bonus", "D": "Interest"}, "answer": "A"},
    {"stem": "The person who receives compensation is called ______.", "options": {"A": "Insurer", "B": "Adjuster", "C": "Policyholder", "D": "Broker"}, "answer": "C"},
    {"stem": "The insurance company is the ______.", "options": {"A": "Insurer", "B": "Beneficiary", "C": "Debtor", "D": "Trader"}, "answer": "A"},
    {"stem": "Which of these is NOT insurable in agriculture?", "options": {"A": "Crops", "B": "Livestock", "C": "Weather disaster", "D": "Farmer's personal quarrel"}, "answer": "D"},
    {"stem": "The study of animal diseases is called ______.", "options": {"A": "Pathology", "B": "Parasitology", "C": "Virology", "D": "Entomology"}, "answer": "A"},
    {"stem": "A disease that spreads rapidly is called ______.", "options": {"A": "Sporadic", "B": "Epidemic", "C": "Endemic", "D": "Chronic"}, "answer": "B"},
    {"stem": "Vaccination is used mainly for ______.", "options": {"A": "Treatment", "B": "Prevention", "C": "Surgery", "D": "Feeding"}, "answer": "B"},
    {"stem": "Which is NOT a sign of a sick animal?", "options": {"A": "Dullness", "B": "Loss of appetite", "C": "Shiny eyes", "D": "Rough coat"}, "answer": "C"},
    {"stem": "A parasite living inside an animal is known as ______.", "options": {"A": "External parasite", "B": "Internal parasite", "C": "Scavenger", "D": "Predator"}, "answer": "B"},
    {"stem": "Foot-and-mouth disease affects mainly ______.", "options": {"A": "Poultry", "B": "Dogs", "C": "Cattle", "D": "Fish"}, "answer": "C"},
    {"stem": "Quarantine is used to ______.", "options": {"A": "slaughter animals", "B": "isolate sick animals", "C": "feed animals", "D": "increase milk"}, "answer": "B"},
    {"stem": "Tick-borne diseases are spread by ______.", "options": {"A": "Ticks", "B": "Rabbits", "C": "Birds", "D": "Fish"}, "answer": "A"},
    {"stem": "An example of a deficiency disease is ______.", "options": {"A": "Tuberculosis", "B": "Rabies", "C": "Rickets", "D": "Newcastle"}, "answer": "C"},
    {"stem": "Antibiotics are used to treat ______.", "options": {"A": "Viral diseases", "B": "Bacterial diseases", "C": "Genetic diseases", "D": "Nutritional disorders"}, "answer": "B"},
    {"stem": "Honey-producing bees are called ______.", "options": {"A": "Drones", "B": "Workers", "C": "Queens", "D": "Soldiers"}, "answer": "B"},
    {"stem": "The male bee in a colony is the ______.", "options": {"A": "Worker", "B": "Drone", "C": "Queen", "D": "Guard"}, "answer": "B"},
    {"stem": "A structure used for keeping bees is the ______.", "options": {"A": "Pond", "B": "Hive", "C": "Sty", "D": "Coop"}, "answer": "B"},
    {"stem": "The primary product of bees is ______.", "options": {"A": "Leather", "B": "Wool", "C": "Honey", "D": "Fur"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. (a) Explain five problems of marketing agricultural produce.\n(b) Suggest five solutions.", "marks": Decimal("15.00")},
    {"stem": "2. Describe seven functions of agricultural extension service.", "marks": Decimal("15.00")},
    {"stem": "3. (a) Define agricultural finance.\n(b) Discuss five sources of farm finance.", "marks": Decimal("15.00")},
    {"stem": "4. Explain six types of farm records and their uses.", "marks": Decimal("15.00")},
    {"stem": "5. (a) What is agricultural insurance?\n(b) State five benefits of agricultural insurance.", "marks": Decimal("15.00")},
    {"stem": "6. Discuss six signs of ill-health in farm animals.", "marks": Decimal("15.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="AGR")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS3 Agricultural Science assignment found")
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
                source_reference=f"SS3-AGR-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS3-AGR-20260326-TH-{index:02d}",
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
            "paper_code": "SS3-AGR-MOCK",
            "flow_type": "OBJECTIVE_THEORY",
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "objective_target_max": "40.00",
            "theory_target_max": "60.00",
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
