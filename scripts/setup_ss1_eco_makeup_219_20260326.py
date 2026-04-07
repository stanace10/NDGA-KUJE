from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, Subject, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTAttemptStatus,
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamAttempt,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)


TITLE = "THU 11:30-12:30 SS1 Economics Make-Up Exam"
DESCRIPTION = "SS1 ECONOMICS SECOND TERM MAKE-UP EXAM FOR MISSED CANDIDATE"
BANK_NAME = "SS1 Economics Make-Up Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer the essay questions as instructed. "
    "Timer is 20 minutes. Exam window closes at 12:30 PM WAT on Thursday, March 26, 2026."
)
TARGET_STUDENT_NUMBER = "NDGAK/22/219"

OBJECTIVES = [
    {"stem": "Which of the following best describes an economic system?", "options": {"A": "The method by which a country distributes political power", "B": "The way a society organizes the production, distribution and consumption of goods and services", "C": "The process of importing and exporting goods", "D": "The system of electing government officials"}, "answer": "B"},
    {"stem": "In which economic system are most resources owned and controlled by private individuals?", "options": {"A": "Traditional economy", "B": "Command economy", "C": "Market economy", "D": "Socialist economy"}, "answer": "C"},
    {"stem": "A major feature of a traditional economic system is that production decisions are mainly based on", "options": {"A": "government directives", "B": "customs and traditions", "C": "international trade agreements", "D": "technological innovations"}, "answer": "B"},
    {"stem": "Which of the following countries has historically practiced a command economy?", "options": {"A": "United States of America", "B": "Cuba", "C": "United Kingdom", "D": "Canada"}, "answer": "B"},
    {"stem": "The economic problem arises mainly because", "options": {"A": "resources are unlimited", "B": "human wants are limited", "C": "resources are scarce while human wants are unlimited", "D": "production techniques are inefficient"}, "answer": "C"},
    {"stem": "Which of the following is not one of the basic economic problems?", "options": {"A": "What to produce", "B": "How to produce", "C": "Where to produce", "D": "For whom to produce"}, "answer": "C"},
    {"stem": "The decision about how to produce relates mainly to", "options": {"A": "distribution of income", "B": "allocation of resources", "C": "choice of production techniques", "D": "marketing of goods"}, "answer": "C"},
    {"stem": "Opportunity cost refers to", "options": {"A": "the value of the best alternative forgone", "B": "the cost of producing goods in factories", "C": "the money spent on advertising", "D": "the price consumers are willing to pay"}, "answer": "A"},
    {"stem": "A firm can best be described as", "options": {"A": "a government agency regulating trade", "B": "an organization engaged in producing goods or services for sale", "C": "a group of consumers purchasing goods", "D": "a financial institution lending money"}, "answer": "B"},
    {"stem": "An industry consists of", "options": {"A": "one large firm only", "B": "a group of firms producing similar products", "C": "government-owned companies only", "D": "firms that sell imported goods only"}, "answer": "B"},
    {"stem": "Which of the following is an example of a primary industry?", "options": {"A": "Textile manufacturing", "B": "Oil refining", "C": "Mining of coal", "D": "Automobile assembly"}, "answer": "C"},
    {"stem": "A major characteristic of a sole proprietorship is that", "options": {"A": "ownership is shared by many shareholders", "B": "the business is owned and controlled by one person", "C": "profits are shared by partners", "D": "management is appointed by government"}, "answer": "B"},
    {"stem": "One advantage of sole proprietorship is", "options": {"A": "unlimited capital", "B": "quick decision-making", "C": "limited liability", "D": "separation of ownership from management"}, "answer": "B"},
    {"stem": "A government-owned business enterprise established to provide essential services is known as", "options": {"A": "cooperative society", "B": "public corporation", "C": "partnership firm", "D": "private company"}, "answer": "B"},
    {"stem": "One major objective of public enterprises is to", "options": {"A": "maximize profits only", "B": "provide essential services to the public", "C": "eliminate employment opportunities", "D": "promote private monopolies"}, "answer": "B"},
    {"stem": "A cooperative society is best described as", "options": {"A": "a business owned by a single entrepreneur", "B": "a voluntary association formed to promote the economic interests of members", "C": "a government department", "D": "a multinational corporation"}, "answer": "B"},
    {"stem": "Which of the following minerals is predominantly found in Enugu State of Nigeria?", "options": {"A": "Tin", "B": "Coal", "C": "Limestone", "D": "Gold"}, "answer": "B"},
    {"stem": "Tin mining in Nigeria is mainly associated with", "options": {"A": "Plateau State", "B": "Lagos State", "C": "Delta State", "D": "Ogun State"}, "answer": "A"},
    {"stem": "Petroleum is mainly produced in the", "options": {"A": "North-East region of Nigeria", "B": "Middle Belt", "C": "Niger Delta region", "D": "Western Highlands"}, "answer": "C"},
    {"stem": "Limestone used in cement production is largely found in", "options": {"A": "Ebonyi and Kogi States", "B": "Kano and Jigawa States", "C": "Zamfara and Sokoto States", "D": "Adamawa and Taraba States"}, "answer": "A"},
    {"stem": "One major characteristic of the mining industry is that it", "options": {"A": "requires little capital", "B": "is labour-intensive only", "C": "involves extraction of mineral resources from the earth", "D": "depends solely on rainfall"}, "answer": "C"},
    {"stem": "A major importance of mining to the Nigerian economy is that it", "options": {"A": "discourages industrial growth", "B": "provides raw materials for industries", "C": "eliminates international trade", "D": "reduces employment opportunities"}, "answer": "B"},
    {"stem": "Environmental degradation associated with mining can lead to", "options": {"A": "improved soil fertility", "B": "land pollution and erosion", "C": "increased rainfall", "D": "reduction in population"}, "answer": "B"},
    {"stem": "Which of the following is not a problem of the mining sector in Nigeria?", "options": {"A": "Inadequate capital", "B": "Poor infrastructure", "C": "Abundance of skilled labour", "D": "Environmental hazards"}, "answer": "C"},
    {"stem": "Which of the following measures can improve mining activities in Nigeria?", "options": {"A": "Discouraging foreign investment", "B": "Improving transport infrastructure", "C": "Closing mining industries", "D": "Reducing geological surveys"}, "answer": "B"},
    {"stem": "Agriculture can be defined as", "options": {"A": "the extraction of minerals from the earth", "B": "the cultivation of crops and rearing of animals for human use", "C": "the manufacturing of goods in factories", "D": "the distribution of goods and services"}, "answer": "B"},
    {"stem": "Subsistence farming is characterized by", "options": {"A": "large-scale mechanized production", "B": "production mainly for family consumption", "C": "heavy use of modern technology", "D": "export-oriented farming"}, "answer": "B"},
    {"stem": "Plantation agriculture usually involves", "options": {"A": "growing a single crop on a large scale", "B": "cultivating many crops on small plots", "C": "raising animals only", "D": "using only family labour"}, "answer": "A"},
    {"stem": "Which of the following is an example of a cash crop in Nigeria?", "options": {"A": "Yam", "B": "Cassava", "C": "Cocoa", "D": "Millet"}, "answer": "C"},
    {"stem": "Mixed farming involves", "options": {"A": "cultivation of crops only", "B": "rearing of animals only", "C": "both crop cultivation and animal rearing", "D": "forestry practices only"}, "answer": "C"},
    {"stem": "One importance of agriculture is that it", "options": {"A": "provides food for the population", "B": "eliminates unemployment", "C": "discourages industrial development", "D": "reduces export earnings"}, "answer": "A"},
    {"stem": "A major problem facing agriculture in Nigeria is", "options": {"A": "excess mechanization", "B": "inadequate storage facilities", "C": "too much rainfall everywhere", "D": "surplus labour in rural areas"}, "answer": "B"},
    {"stem": "Which of the following measures can improve agricultural production in Nigeria?", "options": {"A": "Provision of credit facilities to farmers", "B": "Reduction in agricultural research", "C": "Abandonment of irrigation projects", "D": "Limiting access to farm inputs"}, "answer": "A"},
    {"stem": "Financial institutions are organizations that", "options": {"A": "produce consumer goods", "B": "regulate agricultural activities", "C": "facilitate savings and provide loans", "D": "manufacture industrial equipment"}, "answer": "C"},
    {"stem": "Which of the following is an example of a formal financial institution in Nigeria?", "options": {"A": "Commercial bank", "B": "Esusu group", "C": "Daily contribution collector", "D": "Rotational savings club"}, "answer": "A"},
    {"stem": "Informal financial institutions are characterized mainly by", "options": {"A": "strict government regulation", "B": "complex legal procedures", "C": "simple and flexible operations", "D": "international ownership"}, "answer": "C"},
    {"stem": "The Central Bank of Nigeria is responsible for", "options": {"A": "selling agricultural products", "B": "regulating the banking system", "C": "producing petroleum", "D": "managing mining companies"}, "answer": "B"},
    {"stem": "The practice where members contribute money periodically and take turns collecting the lump sum is known as", "options": {"A": "mortgage banking", "B": "cooperative insurance", "C": "esusu or rotating savings", "D": "central banking"}, "answer": "C"},
    {"stem": "One advantage of informal financial institutions is that they", "options": {"A": "require complicated documentation", "B": "operate without trust among members", "C": "provide quick access to small loans", "D": "charge extremely high taxes"}, "answer": "C"},
    {"stem": "A major limitation of informal financial institutions is that they", "options": {"A": "provide unlimited credit", "B": "lack strong legal protection and regulation", "C": "have large capital base", "D": "operate internationally"}, "answer": "B"},
]

THEORY = [
    {"stem": "1a. Explain what you understand by financial institution\n(i) In a tabular form, give two differences between formal and informal financial institutions\n(ii) Give two examples of formal financial institutions and two examples of non-financial institutions.\nb. Explain any 5 functions of the Central Bank of Nigeria", "marks": Decimal("10.00")},
    {"stem": "2a. Explain the basic economic problems faced by every society.\nb. Discuss two factors that influence how these economic problems are solved.", "marks": Decimal("10.00")},
    {"stem": "3. What is money?\nb. Explain the evolution of money from its earliest form to its present.", "marks": Decimal("10.00")},
    {"stem": "4a. Discuss the importance of mining to the Nigerian economy.\nb. Examine five problems facing the mining sector in Nigeria and suggest possible solutions.", "marks": Decimal("10.00")},
    {"stem": "5a. Explain the importance of agriculture to economic development in Nigeria.\nb. Discuss five problems facing agriculture in Nigeria and suggest possible solutions.", "marks": Decimal("10.00")},
    {"stem": "6. What is cryptocurrency?\nb. Identify 2 examples of cryptocurrency\nc. Differentiate between banknotes and bank money", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
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
    target_student = User.objects.get(student_profile__student_number=TARGET_STUDENT_NUMBER)

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 26, 11, 30, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 26, 12, 30, tzinfo=lagos)

    original_exam = Exam.objects.get(id=248)
    original_attempts = original_exam.attempts.count()

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
            "dean_review_comment": "Approved for single-student make-up paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Activated for one missed SS1 Economics candidate.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.filter(is_locked=False).exclude(student=target_student).exists():
        raise RuntimeError(f"Exam {exam.id} already has unlocked non-target attempts.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for single-student make-up paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Activated for one missed SS1 Economics candidate."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    if not exam.attempts.exists():
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
                source_reference=f"SS1-ECO-MAKEUP-20260326-OBJ-{index:02d}",
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
                source_reference=f"SS1-ECO-MAKEUP-20260326-TH-{index:02d}",
                is_active=True,
            )
            CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
            sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 20
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS1-ECO-MAKEUP-EXAM",
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

    ss1_student_ids = list(
        StudentClassEnrollment.objects.filter(
            session=session,
            academic_class_id__in=academic_class.cohort_class_ids(),
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    locked_count = 0
    for student_id in ss1_student_ids:
        if student_id == target_student.id:
            continue
        attempt, attempt_created = ExamAttempt.objects.get_or_create(
            exam=exam,
            student_id=student_id,
            attempt_number=1,
            defaults={
                "status": CBTAttemptStatus.IN_PROGRESS,
                "is_locked": True,
                "lock_reason": "MAKEUP_ONLY",
                "locked_at": timezone.now(),
                "allow_resume_by_it": False,
            },
        )
        fields = []
        if not attempt.is_locked:
            attempt.is_locked = True
            fields.append("is_locked")
        if attempt.lock_reason != "MAKEUP_ONLY":
            attempt.lock_reason = "MAKEUP_ONLY"
            fields.append("lock_reason")
        if attempt.locked_at is None:
            attempt.locked_at = timezone.now()
            fields.append("locked_at")
        if attempt.allow_resume_by_it:
            attempt.allow_resume_by_it = False
            fields.append("allow_resume_by_it")
        if fields:
            fields.append("updated_at")
            attempt.save(update_fields=fields)
        if attempt_created or fields:
            locked_count += 1

    print(
        {
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "target_student": TARGET_STUDENT_NUMBER,
            "target_user_id": target_student.id,
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
            "locked_other_students": ExamAttempt.objects.filter(exam=exam, is_locked=True).exclude(student=target_student).count(),
            "original_exam_id": original_exam.id,
            "original_exam_attempts_before": original_attempts,
            "original_exam_attempts_after": original_exam.attempts.count(),
        }
    )


if __name__ == "__main__":
    main()
