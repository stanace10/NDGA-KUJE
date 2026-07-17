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

TITLE = "THU 9:30-11:30 SS1 Agricultural Science Second Term Exam"
DESCRIPTION = "SS1 AGRICULTURAL SCIENCE SECOND TERM EXAMINATION"
BANK_NAME = "SS1 Agricultural Science Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 55 minutes. Exam window closes at 11:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "Anatomy means the ______ of the body.", "options": {"A": "Function of form and part", "B": "Functions", "C": "Form and structure", "D": "Part"}, "answer": "C"},
    {"stem": "A system where animals are allowed to roam about in search of food for themselves is known as ______ system.", "options": {"A": "Semi-intensive", "B": "Intensive", "C": "Extensive", "D": "None of the above"}, "answer": "C"},
    {"stem": "Which of these is not a breed of cattle?", "options": {"A": "Kuri", "B": "Ndama", "C": "Yankasa", "D": "Muturu"}, "answer": "C"},
    {"stem": "The major feed of ruminant animal is ______.", "options": {"A": "Roughages", "B": "Concentrates", "C": "Additive", "D": "Supplement"}, "answer": "A"},
    {"stem": "Which of the following part of the digestive tract of poultry serves the same function as rumen in ruminant animals?", "options": {"A": "Gizzard", "B": "Crop", "C": "Gall bladder", "D": "Caecum"}, "answer": "B"},
    {"stem": "All farm animals are classified into the following group except ______.", "options": {"A": "Ruminant", "B": "Monogastric", "C": "Biennial", "D": "Mammal"}, "answer": "C"},
    {"stem": "The act of giving birth in cattle is called ______.", "options": {"A": "Farrowing", "B": "Calving", "C": "Kidding", "D": "Lambing"}, "answer": "B"},
    {"stem": "Libido means ______ in animal reproduction.", "options": {"A": "Sexual drive", "B": "Heat period", "C": "Weaning", "D": "Propagation"}, "answer": "A"},
    {"stem": "The signs of approaching parturition include the following except ______.", "options": {"A": "Preparation of nest by the dam", "B": "Swelling of the vulva", "C": "Enlargement of the udder", "D": "Mounting of other animals"}, "answer": "D"},
    {"stem": "The testes of livestock are usually located outside their body because ______.", "options": {"A": "Their high body temperature will destroy the sperm cells", "B": "The animal will not ejaculate", "C": "The animal will have an erection", "D": "The sperm produced will be digested by enzymes"}, "answer": "A"},
    {"stem": "The act of giving birth to young ones in animal is called ______.", "options": {"A": "Gestation", "B": "Parturition", "C": "Mating", "D": "Lactation"}, "answer": "B"},
    {"stem": "The release of milk from the mammary gland of an animal is called ______.", "options": {"A": "Lactation", "B": "Heat period", "C": "Gestation", "D": "Insemination"}, "answer": "A"},
    {"stem": "The gestation period of cattle ranges from ______ to ______.", "options": {"A": "150-155", "B": "263-305", "C": "145-155", "D": "114-118"}, "answer": "B"},
    {"stem": "The period between fertilization of an ovum to the birth of the young ones is called ______.", "options": {"A": "Ovulation", "B": "Lactation", "C": "Gestation", "D": "Parturition"}, "answer": "C"},
    {"stem": "Chalaza is formed in which part of the reproductive tract of hen?", "options": {"A": "Sphincter", "B": "Oviduct", "C": "Magnum", "D": "Cloaca"}, "answer": "C"},
    {"stem": "The signs of heat period include the following except ______.", "options": {"A": "Attempting to mount other animals", "B": "Preparation of nest by the dam", "C": "Undue noise", "D": "Restlessness"}, "answer": "B"},
    {"stem": "Which of the following is not the function of Testosterone?", "options": {"A": "It stimulates the development of male secondary sex characteristics", "B": "Increases libido", "C": "Prevents the ripening of more follicles", "D": "Production of sperm"}, "answer": "C"},
    {"stem": "The period from the beginning of one oestrus to the beginning of another is called ______.", "options": {"A": "Gestation cycle", "B": "Oestrus cycle", "C": "Lactation cycle", "D": "Oestrogen"}, "answer": "B"},
    {"stem": "Another name for artificial mating is ______.", "options": {"A": "Insemination", "B": "Stud", "C": "Hand mating", "D": "None of the above"}, "answer": "A"},
    {"stem": "When a male animal is kept separately and is only brought in to mate with the female when on heat is called ______ mating.", "options": {"A": "Flock", "B": "Pen", "C": "Stud", "D": "Artificial"}, "answer": "C"},
    {"stem": "In the male reproductive system, the sperm is stored in ______.", "options": {"A": "Epididymis", "B": "Scrotum", "C": "Cowper's gland", "D": "All of the above"}, "answer": "A"},
    {"stem": "Which of the following is the male reproductive hormone?", "options": {"A": "Progesterone", "B": "Oestrogen", "C": "Testosterone", "D": "Oxytocin"}, "answer": "C"},
    {"stem": "The liquid portion of the blood is called ______.", "options": {"A": "Plasma", "B": "Blood cell", "C": "Erythrocytes", "D": "Leucocytes"}, "answer": "A"},
    {"stem": "Which of the following blood cells prevents foreign body from contaminating the animal body?", "options": {"A": "Red blood cell", "B": "White blood cell", "C": "Blood platelets", "D": "None of the above"}, "answer": "B"},
    {"stem": "Which of the following systems in the animal is responsible for the exchange of gases between the animal and its environment?", "options": {"A": "Digestive system", "B": "Reproductive system", "C": "Secretory system", "D": "Respiratory system"}, "answer": "D"},
    {"stem": "Which of these is similar to the testes in male animal?", "options": {"A": "Ovary", "B": "Cervix", "C": "Oviduct", "D": "Vulva"}, "answer": "A"},
    {"stem": "The adult male cattle is called ______.", "options": {"A": "Cow", "B": "Calf", "C": "Bull", "D": "Buck"}, "answer": "C"},
    {"stem": "Farmers rear animals due to the following reasons except to ______.", "options": {"A": "be gainfully employed", "B": "control climate change", "C": "generate income", "D": "engage in sports and games"}, "answer": "B"},
    {"stem": "These are all pre-planting operations.", "options": {"A": "clearing, planting, ploughing, weeding", "B": "weeding, staking, stumping, clearing", "C": "manuring, planting, weeding, clearing", "D": "clearing, stumping, ploughing, harrowing"}, "answer": "D"},
    {"stem": "A soil under bush fallow will regain its fertility through ______.", "options": {"A": "rain water", "B": "leaf fall", "C": "weathering rock", "D": "nitrogen fixing bacteria"}, "answer": "B"},
    {"stem": "The removal of weak and excess seedlings after germination is known as ______.", "options": {"A": "thinning", "B": "weeding", "C": "liming", "D": "dressing"}, "answer": "A"},
    {"stem": "Hutch is house meant for ______.", "options": {"A": "goat", "B": "layer", "C": "rabbit", "D": "cattle"}, "answer": "C"},
    {"stem": "Disease causing organism include the following except ______.", "options": {"A": "fungi", "B": "vector", "C": "bacteria", "D": "virus"}, "answer": "B"},
    {"stem": "When a farmer engages in both plant and animal husbandry, he is said to be practicing ______.", "options": {"A": "Land farming", "B": "Crop rotation", "C": "Mixed farming", "D": "Mixed cropping"}, "answer": "C"},
    {"stem": "Poultry droppings, cattle dung, human faeces, are collectively called ______ manure.", "options": {"A": "Pure", "B": "Inorganic", "C": "Fertilizer", "D": "Organic"}, "answer": "D"},
    {"stem": "In the male reproductive system the testis produces ______.", "options": {"A": "Spermatogenesis", "B": "Spermatozoa", "C": "Zygote", "D": "Ovum"}, "answer": "B"},
    {"stem": "Which of the following will lead to loss of nutrients from the soil?", "options": {"A": "Leaching", "B": "Mulching", "C": "Cover cropping", "D": "Crop rotation"}, "answer": "A"},
    {"stem": "Insect that damage farm crops are referred to as ______.", "options": {"A": "Pest", "B": "Cricket", "C": "Host", "D": "Parasite"}, "answer": "A"},
    {"stem": "The milk secreting organ in cattle is known as ______.", "options": {"A": "Comb", "B": "Nuzzle", "C": "Dew lap", "D": "Udder"}, "answer": "D"},
    {"stem": "The incubation or gestation period for hen is ______.", "options": {"A": "21 days", "B": "208 days", "C": "19 days", "D": "10 days"}, "answer": "A"},
]

THEORY = [
    {"stem": "1. (a) What are monogastric and ruminant animals? Give two examples each.\n(b) In tabular form, state four differences between monogastric and ruminant digestive system.", "marks": Decimal("10.00")},
    {"stem": "2. With the aid of a labeled diagram, describe digestion in a named ruminant.", "marks": Decimal("10.00")},
    {"stem": "3. Explain the following terms:\n(i) Heat period\n(ii) Oestrus cycle\n(iii) Gestation period\n(iv) Ovulation\n(v) Parturition", "marks": Decimal("10.00")},
    {"stem": "4. (a) State four signs of heat period.\n(b) State also four signs of approaching parturition in animals.", "marks": Decimal("10.00")},
    {"stem": "5. (a) Describe the functions of:\n(i) Scrotal sac\n(ii) Testes\n(iii) Epididymis\n(iv) Vas deferens\n(b) Briefly describe flock mating.", "marks": Decimal("10.00")},
    {"stem": "6. (a) Enumerate three major organs in each of the thoracic and abdominal cavities.\n(b) State functions of testosterone in reproduction.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="SS1")
    subject = Subject.objects.get(code="AGR")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active SS1 Agricultural Science assignment found")
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
                source_reference=f"SS1-AGR-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS1-AGR-20260326-TH-{index:02d}",
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
            "paper_code": "SS1-AGR-EXAM",
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
