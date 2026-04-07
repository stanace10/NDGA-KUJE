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

TITLE = "MON 1:15-2:15 SS2 Geography Second Term Exam"
DESCRIPTION = "GEOGRAPHY SS2 EXAMINATION QUESTIONS"
BANK_NAME = "SS2 Geography Examination 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all essay questions in Section B. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Agriculture refers to the", "options": {"A": "Buying and selling of goods", "B": "Cultivation of crops and rearing of animals", "C": "Manufacturing of machines", "D": "Mining of minerals"}, "answer": "B"},
    {"stem": "2. Which of these is a food crop?", "options": {"A": "Cotton", "B": "Cocoa", "C": "Yam", "D": "Rubber"}, "answer": "C"},
    {"stem": "3. A major cash crop in Nigeria is", "options": {"A": "Rice", "B": "Maize", "C": "Cocoa", "D": "Cassava"}, "answer": "C"},
    {"stem": "4. Subsistence farming is mainly for", "options": {"A": "Export", "B": "Profit", "C": "Family consumption", "D": "Industrial use"}, "answer": "C"},
    {"stem": "5. One factor affecting agriculture in Nigeria is", "options": {"A": "Religion", "B": "Climate", "C": "Language", "D": "Tribe"}, "answer": "B"},
    {"stem": "6. The farming system where farmers move from place to place is", "options": {"A": "Mixed farming", "B": "Plantation farming", "C": "Shifting cultivation", "D": "Mechanized farming"}, "answer": "C"},
    {"stem": "7. Bush fallowing involves", "options": {"A": "Burning forest", "B": "Leaving land to regain fertility", "C": "Planting one crop only", "D": "Using machines"}, "answer": "B"},
    {"stem": "8. Mixed farming means", "options": {"A": "Growing one crop", "B": "Rearing animals only", "C": "Growing crops and rearing animals together", "D": "Farming with chemicals"}, "answer": "C"},
    {"stem": "9. Mechanized farming uses", "options": {"A": "Simple tools", "B": "Animals", "C": "Machines", "D": "Hand labour"}, "answer": "C"},
    {"stem": "10. Crop rotation is done to", "options": {"A": "Increase weeds", "B": "Reduce soil fertility", "C": "Maintain soil fertility", "D": "Destroy crops"}, "answer": "C"},
    {"stem": "11. Which of these is a modern farming method?", "options": {"A": "Hoe farming", "B": "Shifting cultivation", "C": "Irrigation", "D": "Bush burning"}, "answer": "C"},
    {"stem": "12. Irrigation is mainly practiced during the", "options": {"A": "Rainy season", "B": "Dry season", "C": "Harmattan", "D": "Cold season"}, "answer": "B"},
    {"stem": "13. Transportation refers to the movement of", "options": {"A": "Water", "B": "Goods and people", "C": "Soil", "D": "Money"}, "answer": "B"},
    {"stem": "14. Which is NOT a means of transportation?", "options": {"A": "Road", "B": "Rail", "C": "River", "D": "Television"}, "answer": "D"},
    {"stem": "15. The most widely used transport in Nigeria is", "options": {"A": "Air", "B": "Rail", "C": "Road", "D": "Water"}, "answer": "C"},
    {"stem": "16. An example of water transport terminal is", "options": {"A": "Airport", "B": "Garage", "C": "Seaport", "D": "Bus stop"}, "answer": "C"},
    {"stem": "17. Which transport is fastest?", "options": {"A": "Road", "B": "Rail", "C": "Water", "D": "Air"}, "answer": "D"},
    {"stem": "18. One problem of transportation in Nigeria is", "options": {"A": "Good roads", "B": "Traffic congestion", "C": "Efficient service", "D": "Cheap fares"}, "answer": "B"},
    {"stem": "19. Communication means", "options": {"A": "Exchange of information", "B": "Buying goods", "C": "Building houses", "D": "Growing crops"}, "answer": "A"},
    {"stem": "20. Which is a modern means of communication?", "options": {"A": "Town crier", "B": "Drum", "C": "Mobile phone", "D": "Bell"}, "answer": "C"},
    {"stem": "21. Nigerian Television Authority (NTA) is a", "options": {"A": "Transport company", "B": "Communication agency", "C": "Farming institution", "D": "Mining company"}, "answer": "B"},
    {"stem": "22. The Nigerian Postal Service (NIPOST) handles", "options": {"A": "Radio broadcast", "B": "Telephone calls", "C": "Letters and parcels", "D": "Internet services"}, "answer": "C"},
    {"stem": "23. Which is NOT a traditional means of communication?", "options": {"A": "Drum", "B": "Town crier", "C": "Radio", "D": "Smoke signals"}, "answer": "C"},
    {"stem": "24. One importance of communication is that it promotes", "options": {"A": "Isolation", "B": "Unity", "C": "Disease", "D": "Laziness"}, "answer": "B"},
    {"stem": "25. Manufacturing industries convert", "options": {"A": "Finished goods to raw materials", "B": "Raw materials to finished goods", "C": "Water to soil", "D": "Crops to animals"}, "answer": "B"},
    {"stem": "26. Which of these is a manufacturing industry?", "options": {"A": "Farming", "B": "Fishing", "C": "Cement factory", "D": "Trading"}, "answer": "C"},
    {"stem": "27. An example of agro-based industry is", "options": {"A": "Textile", "B": "Brewery", "C": "Oil refinery", "D": "Steel"}, "answer": "B"},
    {"stem": "28. A major industrial city in Nigeria is", "options": {"A": "Lokoja", "B": "Ibadan", "C": "Enugu", "D": "Lagos"}, "answer": "D"},
    {"stem": "29. Which factor encourages industrial location?", "options": {"A": "Scarcity of labour", "B": "Availability of raw materials", "C": "Poor roads", "D": "Lack of power"}, "answer": "B"},
    {"stem": "30. One problem facing industries in Nigeria is", "options": {"A": "Adequate capital", "B": "Stable electricity", "C": "Poor infrastructure", "D": "Large market"}, "answer": "C"},
    {"stem": "31. Commerce involves", "options": {"A": "Production only", "B": "Distribution only", "C": "Buying and selling", "D": "Mining"}, "answer": "C"},
    {"stem": "32. Trade within a country is called", "options": {"A": "Foreign trade", "B": "Home trade", "C": "Export trade", "D": "Import trade"}, "answer": "B"},
    {"stem": "33. Which is an aid to trade?", "options": {"A": "Farming", "B": "Banking", "C": "Fishing", "D": "Mining"}, "answer": "B"},
    {"stem": "34. Export trade means selling goods to", "options": {"A": "Local markets", "B": "Other towns", "C": "Other countries", "D": "Villages"}, "answer": "C"},
    {"stem": "35. Import trade refers to buying goods from", "options": {"A": "Same town", "B": "Same state", "C": "Other countries", "D": "Nearby village"}, "answer": "C"},
    {"stem": "36. One benefit of commerce is", "options": {"A": "Unemployment", "B": "Poverty", "C": "Revenue generation", "D": "Pollution"}, "answer": "C"},
    {"stem": "37. Market where goods are bought in large quantities is", "options": {"A": "Retail market", "B": "Local market", "C": "Wholesale market", "D": "Roadside market"}, "answer": "C"},
    {"stem": "38. Which of these is a commercial centre?", "options": {"A": "Farm", "B": "Factory", "C": "Onitsha", "D": "Forest"}, "answer": "C"},
    {"stem": "39. One problem of commerce in Nigeria is", "options": {"A": "Good transport", "B": "Adequate capital", "C": "Poor storage", "D": "Large population"}, "answer": "C"},
    {"stem": "40. Retailers sell goods mainly to", "options": {"A": "Wholesalers", "B": "Manufacturers", "C": "Consumers", "D": "Farmers"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Explain Agriculture in Nigeria. Definition. Types of agriculture. Importance.", "marks": Decimal("6.67")},
    {"stem": "2. Describe Agricultural Practices in Nigeria. Meaning of agricultural practices. Traditional practices. Modern practices.", "marks": Decimal("6.67")},
    {"stem": "3. Discuss Transportation in Nigeria. Meaning. Types. Problems.", "marks": Decimal("6.67")},
    {"stem": "4. Explain Communication in Nigeria. Meaning. Types. Importance.", "marks": Decimal("6.67")},
    {"stem": "5. Describe Manufacturing Industries in Nigeria. Meaning. Examples. Factors affecting location.", "marks": Decimal("6.66")},
    {"stem": "6. Explain Commercial Activities in Nigeria. Meaning. Types of trade. Importance.", "marks": Decimal("6.66")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="GEO")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="uwakwe@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 23, 13, 15, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 14, 15, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Monday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 1:15 PM WAT.",
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
    exam.dean_review_comment = "Approved for Monday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 1:15 PM WAT."
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
            marks=Decimal("1.00"),
            source_reference=f"SS2-GEO-20260323-OBJ-{index:02d}",
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
            marks=item["marks"],
            source_reference=f"SS2-GEO-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 50
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS2-GEO-EXAM",
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
        "status": exam.status,
        "schedule_start": exam.schedule_start.isoformat(),
        "schedule_end": exam.schedule_end.isoformat(),
        "duration_minutes": blueprint.duration_minutes,
        "objective_questions": len(OBJECTIVES),
        "theory_questions": len(THEORY),
    })

main()
