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

TITLE = "MON 1:15-2:15 SS1 Geography Second Term Exam"
DESCRIPTION = "GEOGRAPHY SS1 EXAMINATION QUESTIONS"
BANK_NAME = "SS1 Geography Examination 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. Answer four essay questions in Section B. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Lowland refers to land area that is", "options": {"A": "Above 1000 m", "B": "Below 300 m", "C": "Above sea level", "D": "Covered by forest"}, "answer": "B"},
    {"stem": "2. An example of lowland in Nigeria is", "options": {"A": "Jos Plateau", "B": "Mambilla Plateau", "C": "Niger Delta", "D": "Adamawa Plateau"}, "answer": "C"},
    {"stem": "3. One characteristic of lowland is that it is", "options": {"A": "Rocky", "B": "Steep", "C": "Flat", "D": "Snowy"}, "answer": "C"},
    {"stem": "4. Lowlands are mainly suitable for", "options": {"A": "Mining", "B": "Farming", "C": "Tourism", "D": "Mountain climbing"}, "answer": "B"},
    {"stem": "5. Flooding is common in lowlands because they are", "options": {"A": "Windy", "B": "High", "C": "Flat", "D": "Rocky"}, "answer": "C"},
    {"stem": "6. The environment refers to everything that", "options": {"A": "Lives in water", "B": "Surrounds man", "C": "Is artificial", "D": "Is underground"}, "answer": "B"},
    {"stem": "7. Which of these is NOT an environmental resource?", "options": {"A": "Soil", "B": "Water", "C": "Plastic", "D": "Forest"}, "answer": "C"},
    {"stem": "8. One importance of the environment is that it provides", "options": {"A": "Pollution", "B": "Shelter", "C": "Diseases", "D": "Waste"}, "answer": "B"},
    {"stem": "9. Resources that can be replaced naturally are called", "options": {"A": "Exhaustible", "B": "Non-renewable", "C": "Renewable", "D": "Mineral"}, "answer": "C"},
    {"stem": "10. Which is a non-renewable resource?", "options": {"A": "Forest", "B": "Wind", "C": "Crude oil", "D": "Fish"}, "answer": "C"},
    {"stem": "11. Weather is the condition of the atmosphere over a", "options": {"A": "Long period", "B": "Short period", "C": "Century", "D": "Decade"}, "answer": "B"},
    {"stem": "12. Climate refers to the average weather condition of a place over", "options": {"A": "One week", "B": "One month", "C": "Many years", "D": "One day"}, "answer": "C"},
    {"stem": "13. An instrument used to measure rainfall is", "options": {"A": "Thermometer", "B": "Barometer", "C": "Rain gauge", "D": "Hygrometer"}, "answer": "C"},
    {"stem": "14. Temperature is measured using", "options": {"A": "Anemometer", "B": "Wind vane", "C": "Thermometer", "D": "Rain gauge"}, "answer": "C"},
    {"stem": "15. Which element of weather measures air pressure?", "options": {"A": "Rainfall", "B": "Temperature", "C": "Humidity", "D": "Pressure"}, "answer": "D"},
    {"stem": "16. Nigeria is located in", "options": {"A": "Southern Africa", "B": "Eastern Africa", "C": "Western Africa", "D": "Northern Africa"}, "answer": "C"},
    {"stem": "17. Nigeria lies between latitudes", "options": {"A": "4 deg N and 14 deg N", "B": "10 deg N and 20 deg N", "C": "0 deg and 10 deg N", "D": "14 deg N and 25 deg N"}, "answer": "A"},
    {"stem": "18. Nigeria is bordered in the west by", "options": {"A": "Chad", "B": "Niger", "C": "Benin", "D": "Cameroon"}, "answer": "C"},
    {"stem": "19. The Gulf of Guinea lies to the", "options": {"A": "North of Nigeria", "B": "South of Nigeria", "C": "East of Nigeria", "D": "West of Nigeria"}, "answer": "B"},
    {"stem": "20. Nigeria operates on the", "options": {"A": "GMT", "B": "WAT", "C": "EST", "D": "PST"}, "answer": "B"},
    {"stem": "21. Relief means", "options": {"A": "Soil type", "B": "Height of land", "C": "Climate", "D": "Vegetation"}, "answer": "B"},
    {"stem": "22. Which is NOT a highland area in Nigeria?", "options": {"A": "Jos Plateau", "B": "Adamawa Plateau", "C": "Mambilla Plateau", "D": "Niger Delta"}, "answer": "D"},
    {"stem": "23. The two major rivers in Nigeria are", "options": {"A": "Benue and Kaduna", "B": "Niger and Benue", "C": "Cross and Ogun", "D": "Sokoto and Hadejia"}, "answer": "B"},
    {"stem": "24. River Niger empties into the", "options": {"A": "Atlantic Ocean", "B": "Indian Ocean", "C": "Mediterranean Sea", "D": "Red Sea"}, "answer": "A"},
    {"stem": "25. Drainage refers to the", "options": {"A": "Movement of soil", "B": "Flow of rivers", "C": "Direction of wind", "D": "Formation of clouds"}, "answer": "B"},
    {"stem": "26. Mangrove vegetation is found mainly in the", "options": {"A": "Sahel", "B": "Sudan", "C": "Guinea", "D": "Niger Delta"}, "answer": "D"},
    {"stem": "27. The tropical rainforest zone has", "options": {"A": "Sparse trees", "B": "Tall dense trees", "C": "Short grasses", "D": "Desert shrubs"}, "answer": "B"},
    {"stem": "28. Which vegetation belt is found in northern Nigeria?", "options": {"A": "Rainforest", "B": "Mangrove", "C": "Sahel Savanna", "D": "Swamp"}, "answer": "C"},
    {"stem": "29. One climatic factor affecting Nigeria is", "options": {"A": "Soil", "B": "Population", "C": "Latitude", "D": "Mining"}, "answer": "C"},
    {"stem": "30. Harmattan occurs during the", "options": {"A": "Rainy season", "B": "Dry season", "C": "Planting season", "D": "Harvest season"}, "answer": "B"},
    {"stem": "31. Population refers to the", "options": {"A": "Number of houses", "B": "Number of schools", "C": "Number of people", "D": "Number of rivers"}, "answer": "C"},
    {"stem": "32. A census is the", "options": {"A": "Counting of animals", "B": "Counting of buildings", "C": "Counting of people", "D": "Counting of roads"}, "answer": "C"},
    {"stem": "33. A densely populated area means", "options": {"A": "Few people", "B": "No people", "C": "Many people", "D": "Rich people"}, "answer": "C"},
    {"stem": "34. One factor influencing population distribution is", "options": {"A": "Climate", "B": "Colour", "C": "Religion", "D": "Language"}, "answer": "A"},
    {"stem": "35. Rural-urban migration means movement of people from", "options": {"A": "City to village", "B": "Village to city", "C": "Country to country", "D": "Town to town"}, "answer": "B"},
    {"stem": "36. High population can lead to", "options": {"A": "Peace", "B": "Overcrowding", "C": "Development", "D": "More land"}, "answer": "B"},
    {"stem": "37. One advantage of large population is", "options": {"A": "Pollution", "B": "Unemployment", "C": "Large labour force", "D": "Disease"}, "answer": "C"},
    {"stem": "38. Which is a method of population control?", "options": {"A": "Early marriage", "B": "Polygamy", "C": "Family planning", "D": "Immigration"}, "answer": "C"},
    {"stem": "39. Birth rate refers to", "options": {"A": "Number of deaths", "B": "Number of births", "C": "Number of migrants", "D": "Total population"}, "answer": "B"},
    {"stem": "40. Death rate means", "options": {"A": "Number of marriages", "B": "Number of hospitals", "C": "Number of deaths", "D": "Number of schools"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Describe Lowland and state its importance. Definition. Characteristics. Importance.", "marks": Decimal("6.67")},
    {"stem": "2. Explain the Environment and Its Resources. Meaning of environment. Types of resources. Importance.", "marks": Decimal("6.67")},
    {"stem": "3. Differentiate between Weather and Climate. Definition of weather. Definition of climate. Differences (any four).", "marks": Decimal("6.67")},
    {"stem": "4. Describe the Location and Position of Nigeria with the aid of a well labelled diagram. Latitudes and longitudes. Boundaries. Time zone.", "marks": Decimal("6.67")},
    {"stem": "5. Explain the Relief and Drainage of Nigeria. Meaning of relief and drainage. Major relief features. Major rivers.", "marks": Decimal("6.66")},
    {"stem": "6. Write notes on Population of Nigeria. Meaning of population. Factors affecting distribution. Effects of high population.", "marks": Decimal("6.66")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS1")
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
            source_reference=f"SS1-GEO-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS1-GEO-20260323-TH-{index:02d}",
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
        "paper_code": "SS1-GEO-EXAM",
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

