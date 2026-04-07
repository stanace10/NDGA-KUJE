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

TITLE = "MON 1:15-2:15 SS3 Geography Second Term Exam"
DESCRIPTION = "EXAMINATION QUESTIONS CLASS: SS3 SUBJECT: GEOGRAPHY"
BANK_NAME = "SS3 Geography Examination 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer all essay questions in Section B. "
    "Objective carries 40 marks after normalization. Theory carries 60 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Climate change refers to", "options": {"A": "Daily weather changes", "B": "Long-term change in climate pattern", "C": "Wind movement", "D": "Cloud formation"}, "answer": "B"},
    {"stem": "2. A major cause of climate change is", "options": {"A": "Rainfall", "B": "Greenhouse gases", "C": "Latitude", "D": "Humidity"}, "answer": "B"},
    {"stem": "3. Global warming results mainly from increase in", "options": {"A": "Oxygen", "B": "Nitrogen", "C": "Carbon dioxide", "D": "Hydrogen"}, "answer": "C"},
    {"stem": "4. One effect of climate change in Nigeria is", "options": {"A": "Earthquake", "B": "Snowfall", "C": "Desertification", "D": "Volcano"}, "answer": "C"},
    {"stem": "5. Which activity helps reduce climate change?", "options": {"A": "Bush burning", "B": "Deforestation", "C": "Tree planting", "D": "Gas flaring"}, "answer": "C"},
    {"stem": "6. Rising sea level is associated with", "options": {"A": "Cooling of earth", "B": "Melting of ice caps", "C": "Harmattan wind", "D": "Soil erosion"}, "answer": "B"},
    {"stem": "7. GIS stands for", "options": {"A": "Global Internet System", "B": "Geographical Information System", "C": "Graphic Imaging Service", "D": "General Information Source"}, "answer": "B"},
    {"stem": "8. GIS is mainly used for", "options": {"A": "Cooking", "B": "Map analysis and planning", "C": "Teaching sports", "D": "Mining only"}, "answer": "B"},
    {"stem": "9. Satellite imagery is an example of", "options": {"A": "Secondary data", "B": "Manual data", "C": "Spatial data", "D": "Written data"}, "answer": "C"},
    {"stem": "10. GPS is used to", "options": {"A": "Measure rainfall", "B": "Locate positions", "C": "Predict climate", "D": "Record temperature"}, "answer": "B"},
    {"stem": "11. Which is NOT a GIS component?", "options": {"A": "Hardware", "B": "Software", "C": "Data", "D": "Chalk"}, "answer": "D"},
    {"stem": "12. GIS is useful in", "options": {"A": "Urban planning", "B": "Tailoring", "C": "Fishing", "D": "Baking"}, "answer": "A"},
    {"stem": "13. ECOWAS means", "options": {"A": "Economic Council of West African States", "B": "Economic Community of West African States", "C": "Economic Commission of Western Africa States", "D": "Economic Cooperation of West Africa"}, "answer": "B"},
    {"stem": "14. ECOWAS was established in", "options": {"A": "1960", "B": "1975", "C": "1985", "D": "1995"}, "answer": "B"},
    {"stem": "15. The headquarters of ECOWAS is in", "options": {"A": "Accra", "B": "Lagos", "C": "Abuja", "D": "Dakar"}, "answer": "C"},
    {"stem": "16. One aim of ECOWAS is to promote", "options": {"A": "Conflict", "B": "Regional integration", "C": "Isolation", "D": "Colonization"}, "answer": "B"},
    {"stem": "17. A member of ECOWAS is", "options": {"A": "Kenya", "B": "Ghana", "C": "Egypt", "D": "South Africa"}, "answer": "B"},
    {"stem": "18. One benefit of ECOWAS is", "options": {"A": "Desertification", "B": "Free movement of people", "C": "Civil war", "D": "Overpopulation"}, "answer": "B"},
    {"stem": "19. Trade refers to", "options": {"A": "Farming", "B": "Buying and selling", "C": "Transportation", "D": "Communication"}, "answer": "B"},
    {"stem": "20. Trade within a country is called", "options": {"A": "Export trade", "B": "Import trade", "C": "Home trade", "D": "Transit trade"}, "answer": "C"},
    {"stem": "21. Selling goods to other countries is", "options": {"A": "Import", "B": "Retail", "C": "Export", "D": "Wholesale"}, "answer": "C"},
    {"stem": "22. Buying goods from other countries is", "options": {"A": "Export", "B": "Import", "C": "Home trade", "D": "Retail"}, "answer": "B"},
    {"stem": "23. Banking is an example of", "options": {"A": "Primary activity", "B": "Aid to trade", "C": "Manufacturing", "D": "Farming"}, "answer": "B"},
    {"stem": "24. Balance of trade is the difference between", "options": {"A": "Population and land", "B": "Import and export", "C": "Weather and climate", "D": "Buying and selling"}, "answer": "B"},
    {"stem": "25. Tourism involves", "options": {"A": "Mining", "B": "Travelling for leisure", "C": "Teaching", "D": "Fishing"}, "answer": "B"},
    {"stem": "26. Zuma Rock is a tourist centre in", "options": {"A": "Lagos", "B": "Niger State", "C": "Abuja", "D": "Enugu"}, "answer": "C"},
    {"stem": "27. One importance of tourism is", "options": {"A": "Pollution", "B": "Foreign exchange", "C": "Erosion", "D": "Deforestation"}, "answer": "B"},
    {"stem": "28. Which is NOT a tourist centre?", "options": {"A": "Yankari Game Reserve", "B": "Obudu Cattle Ranch", "C": "Oil refinery", "D": "Ikogosi Warm Spring"}, "answer": "C"},
    {"stem": "29. Ecotourism promotes", "options": {"A": "Environmental conservation", "B": "Bush burning", "C": "Mining", "D": "Urban congestion"}, "answer": "A"},
    {"stem": "30. One problem of tourism in Nigeria is", "options": {"A": "Good roads", "B": "Adequate security", "C": "Poor infrastructure", "D": "Stable power"}, "answer": "C"},
    {"stem": "31. Weather is the atmospheric condition over a", "options": {"A": "Long period", "B": "Short period", "C": "Year", "D": "Decade"}, "answer": "B"},
    {"stem": "32. Climate is average weather over", "options": {"A": "One week", "B": "One month", "C": "Many years", "D": "One day"}, "answer": "C"},
    {"stem": "33. Rainfall is measured with", "options": {"A": "Thermometer", "B": "Barometer", "C": "Rain gauge", "D": "Hygrometer"}, "answer": "C"},
    {"stem": "34. Wind speed is measured by", "options": {"A": "Wind vane", "B": "Anemometer", "C": "Barometer", "D": "Rain gauge"}, "answer": "B"},
    {"stem": "35. Humidity refers to", "options": {"A": "Air pressure", "B": "Amount of rainfall", "C": "Water vapour in air", "D": "Wind direction"}, "answer": "C"},
    {"stem": "36. Latitude is a factor affecting", "options": {"A": "Population", "B": "Climate", "C": "Language", "D": "Trade"}, "answer": "B"},
    {"stem": "37. Agriculture involves", "options": {"A": "Manufacturing", "B": "Crop production and animal rearing", "C": "Mining", "D": "Trading"}, "answer": "B"},
    {"stem": "38. A major cash crop in Nigeria is", "options": {"A": "Yam", "B": "Cocoa", "C": "Rice", "D": "Cassava"}, "answer": "B"},
    {"stem": "39. Subsistence farming is mainly for", "options": {"A": "Export", "B": "Industry", "C": "Family consumption", "D": "Government"}, "answer": "C"},
    {"stem": "40. Mechanized farming uses", "options": {"A": "Simple tools", "B": "Machines", "C": "Fire", "D": "Animals"}, "answer": "B"},
    {"stem": "41. One factor affecting agriculture is", "options": {"A": "Religion", "B": "Climate", "C": "Language", "D": "Tribe"}, "answer": "B"},
    {"stem": "42. Irrigation is common during the", "options": {"A": "Rainy season", "B": "Dry season", "C": "Harmattan", "D": "Cold season"}, "answer": "B"},
    {"stem": "43. Transportation is movement of", "options": {"A": "Wind", "B": "Soil", "C": "Goods and people", "D": "Water"}, "answer": "C"},
    {"stem": "44. The most common means of transport in Nigeria is", "options": {"A": "Rail", "B": "Air", "C": "Road", "D": "Water"}, "answer": "C"},
    {"stem": "45. An airport is associated with", "options": {"A": "Rail transport", "B": "Road transport", "C": "Air transport", "D": "Water transport"}, "answer": "C"},
    {"stem": "46. Which is NOT a means of transport?", "options": {"A": "Road", "B": "Rail", "C": "Radio", "D": "River"}, "answer": "C"},
    {"stem": "47. One advantage of transportation is", "options": {"A": "Poverty", "B": "Development", "C": "Isolation", "D": "Disease"}, "answer": "B"},
    {"stem": "48. Traffic congestion is a problem of", "options": {"A": "Tourism", "B": "Agriculture", "C": "Transportation", "D": "Trade"}, "answer": "C"},
    {"stem": "49. A map is a", "options": {"A": "Photograph", "B": "Drawing of the earth's surface on flat paper", "C": "Globe", "D": "Satellite"}, "answer": "B"},
    {"stem": "50. Scale on a map shows", "options": {"A": "Direction", "B": "Distance ratio", "C": "Height", "D": "Symbol"}, "answer": "B"},
    {"stem": "51. Contour lines join points of equal", "options": {"A": "Temperature", "B": "Rainfall", "C": "Height", "D": "Distance"}, "answer": "C"},
    {"stem": "52. North on a map is usually shown by", "options": {"A": "Blue line", "B": "Arrow", "C": "Key", "D": "Grid"}, "answer": "B"},
    {"stem": "53. The key or legend explains", "options": {"A": "Scale", "B": "Direction", "C": "Symbols", "D": "Distance"}, "answer": "C"},
    {"stem": "54. Grid reference is used to locate", "options": {"A": "Climate", "B": "Rivers", "C": "Places on a map", "D": "Mountains"}, "answer": "C"},
    {"stem": "55. A steep slope is shown by", "options": {"A": "Wide contours", "B": "Close contours", "C": "Broken lines", "D": "Dotted lines"}, "answer": "B"},
    {"stem": "56. Spot height shows", "options": {"A": "River depth", "B": "Exact height of a point", "C": "Distance", "D": "Temperature"}, "answer": "B"},
    {"stem": "57. Trade encourages", "options": {"A": "Isolation", "B": "Economic development", "C": "War", "D": "Illiteracy"}, "answer": "B"},
    {"stem": "58. GIS stores and analyses", "options": {"A": "Crops", "B": "Spatial data", "C": "Minerals", "D": "Animals"}, "answer": "B"},
    {"stem": "59. Climate change can lead to", "options": {"A": "Increased snowfall in Nigeria", "B": "Flooding", "C": "Earthquakes", "D": "Volcanoes"}, "answer": "B"},
    {"stem": "60. Rail transport is best for carrying", "options": {"A": "Letters", "B": "Heavy goods", "C": "Tourists only", "D": "Light loads"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Explain Climate Change and its Effects on Nigeria.\nMeaning.\nCauses.\nEffects.", "marks": Decimal("10.00")},
    {"stem": "2. Describe GIS Data and its Uses.\nDefinition of GIS.\nSources or types of data.\nUses.", "marks": Decimal("10.00")},
    {"stem": "3. Discuss ECOWAS and its Importance.\nMeaning.\nObjectives.\nBenefits.", "marks": Decimal("10.00")},
    {"stem": "4. Explain Trade and Tourism in Nigeria.\nMeaning of trade.\nTypes of trade.\nMeaning of tourism.\nImportance.", "marks": Decimal("10.00")},
    {"stem": "5. Describe Weather and Climate and their Elements.\nDefinitions.\nElements (any six).", "marks": Decimal("10.00")},
    {"stem": "6. Discuss Agriculture, Transportation and Map Reading.\nAgriculture (meaning and importance).\nTransportation (meaning and importance).\nMap reading meaning.", "marks": Decimal("10.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
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
            source_reference=f"SS3-GEO-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS3-GEO-20260323-TH-{index:02d}",
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
        "paper_code": "SS3-GEO-EXAM",
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

