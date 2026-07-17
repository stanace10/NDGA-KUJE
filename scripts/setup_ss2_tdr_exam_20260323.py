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

TITLE = "MON 1:15-2:15 SS2 Technical Drawing Second Term Exam"
DESCRIPTION = "TECHNICAL DRAWING SS2 SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Technical Drawing Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any two questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 50 minutes. Exam window closes at 2:15 PM WAT on Monday, March 23, 2026."
)

OBJECTIVES = [
    {"stem": "1. Perspective drawing is used to represent objects _____.", "options": {"A": "In true shape and size", "B": "As they appear to the eye", "C": "In orthographic projection", "D": "In sectional view"}, "answer": "B"},
    {"stem": "2. The point where all receding lines meet is called the _____.", "options": {"A": "Central point", "B": "Vanishing point", "C": "Horizon line", "D": "Reference point"}, "answer": "B"},
    {"stem": "3. A one-point perspective is also called _____.", "options": {"A": "Angular perspective", "B": "Linear perspective", "C": "Parallel perspective", "D": "Oblique perspective"}, "answer": "C"},
    {"stem": "4. The line where the sky appears to meet the ground is the _____.", "options": {"A": "Ground line", "B": "Horizon line", "C": "Base line", "D": "Picture line"}, "answer": "B"},
    {"stem": "5. In two-point perspective, the number of vanishing points is _____.", "options": {"A": "One", "B": "Two", "C": "Three", "D": "Four"}, "answer": "B"},
    {"stem": "6. Surfaces touching the picture plane retain their _____.", "options": {"A": "True shape", "B": "Hidden lines", "C": "Edges only", "D": "Thickness"}, "answer": "A"},
    {"stem": "7. The picture plane is drawn _____.", "options": {"A": "Between eye and object", "B": "Behind the observer", "C": "Beside the observer", "D": "In front of the observer"}, "answer": "A"},
    {"stem": "8. Three-point perspective is commonly used in drawing _____.", "options": {"A": "Interiors", "B": "Roofs", "C": "Tall buildings", "D": "Circles"}, "answer": "C"},
    {"stem": "9. The observer's eye in perspective drawing is represented by the _____.", "options": {"A": "Station point", "B": "Vanishing point", "C": "Measuring point", "D": "Centre point"}, "answer": "A"},
    {"stem": "10. Perspective drawings are mostly used in _____.", "options": {"A": "Engineering", "B": "Architecture", "C": "Welding", "D": "Machine fixing"}, "answer": "B"},
    {"stem": "11. An auxiliary view shows the _____.", "options": {"A": "Plan", "B": "Elevation", "C": "True shape of an inclined surface", "D": "Hidden edges only"}, "answer": "C"},
    {"stem": "12. Auxiliary views are necessary when a surface is _____.", "options": {"A": "Parallel to HP", "B": "Perpendicular to VP", "C": "Inclined to both HP and VP", "D": "Hidden from view"}, "answer": "C"},
    {"stem": "13. The line of rotation used to obtain an auxiliary view is called the _____.", "options": {"A": "Hinge line", "B": "Centre line", "C": "Extension line", "D": "Cutting plane"}, "answer": "A"},
    {"stem": "14. A surface shows true shape only when viewed _____.", "options": {"A": "At an angle", "B": "Perpendicularly", "C": "Obliquely", "D": "From above"}, "answer": "B"},
    {"stem": "15. The plane on which the auxiliary view is projected is called the _____.", "options": {"A": "Auxiliary plane", "B": "Primary plane", "C": "Cutting plane", "D": "Profile plane"}, "answer": "A"},
    {"stem": "16. The auxiliary view of a cylinder inclined to HP shows an _____.", "options": {"A": "Circle", "B": "Ellipse", "C": "Rectangle", "D": "Triangle"}, "answer": "B"},
    {"stem": "17. Auxiliary views help reduce _____.", "options": {"A": "Confusion in interpretation", "B": "Drafting accuracy", "C": "Materials", "D": "Lines"}, "answer": "A"},
    {"stem": "18. When a pyramid is inclined to one plane, its true base shape appears in the _____.", "options": {"A": "Plan", "B": "Side view", "C": "Auxiliary view", "D": "Elevation"}, "answer": "C"},
    {"stem": "19. Auxiliary projection lines are drawn _____.", "options": {"A": "Dark", "B": "Thick", "C": "Light", "D": "Freehand"}, "answer": "C"},
    {"stem": "20. True length of edges on inclined solids appears in the _____.", "options": {"A": "Orthographic view", "B": "Primary auxiliary view", "C": "Plan", "D": "Side view"}, "answer": "B"},
    {"stem": "21. CAD stands for _____.", "options": {"A": "Computer Added Drafting", "B": "Computer Aided Design", "C": "Central Assisted Design", "D": "Computer Application Design"}, "answer": "B"},
    {"stem": "22. Which is NOT CAD software?", "options": {"A": "AutoCAD", "B": "SolidWorks", "C": "Microsoft Word", "D": "Revit"}, "answer": "C"},
    {"stem": "23. The CAD command used to remove unwanted lines is _____.", "options": {"A": "Offset", "B": "Copy", "C": "Trim", "D": "Fillet"}, "answer": "C"},
    {"stem": "24. A major advantage of CAD is _____.", "options": {"A": "Slow editing", "B": "Loss of accuracy", "C": "Quick modification", "D": "Bulky equipment"}, "answer": "C"},
    {"stem": "25. CAD drawings are stored as _____.", "options": {"A": "DWG", "B": "TXT", "C": "AVI", "D": "PDF"}, "answer": "A"},
    {"stem": "26. The command used to create parallel lines is _____.", "options": {"A": "Mirror", "B": "Trim", "C": "Offset", "D": "Zoom"}, "answer": "C"},
    {"stem": "27. Layers in CAD help to _____.", "options": {"A": "Organise objects", "B": "Colour drawings only", "C": "Erase drawings", "D": "Zoom in"}, "answer": "A"},
    {"stem": "28. Device used to enter commands in CAD is the _____.", "options": {"A": "Plotter", "B": "Mouse", "C": "Scanner", "D": "Printer"}, "answer": "B"},
    {"stem": "29. A CAD plotter is used for _____.", "options": {"A": "Digitising", "B": "Printing large drawings", "C": "Editing", "D": "Rotating objects"}, "answer": "B"},
    {"stem": "30. CAD improves accuracy because it uses _____.", "options": {"A": "Rulers", "B": "Grids and coordinates", "C": "Freehand sketching", "D": "Paper sizes"}, "answer": "B"},
    {"stem": "31. The trace of a point is its _____.", "options": {"A": "Distance", "B": "Height", "C": "Projection on a reference plane", "D": "Midpoint"}, "answer": "C"},
    {"stem": "32. A line in space is inclined to _____.", "options": {"A": "One plane only", "B": "Both HP and VP", "C": "Neither plane", "D": "Picture plane"}, "answer": "B"},
    {"stem": "33. The horizontal trace of a line is its intersection with _____.", "options": {"A": "VP", "B": "HP", "C": "PP", "D": "Auxiliary plane"}, "answer": "B"},
    {"stem": "34. True length of a line is obtained when the line is viewed _____.", "options": {"A": "Parallel to the plane", "B": "Perpendicular to the plane", "C": "From above", "D": "From the side"}, "answer": "A"},
    {"stem": "35. When a line is inclined to both HP and VP, its true length appears after _____.", "options": {"A": "Trimming", "B": "Rotation or auxiliary view", "C": "Shading", "D": "Scaling"}, "answer": "B"},
    {"stem": "36. The angle a line makes with HP is called the _____.", "options": {"A": "Horizontal angle", "B": "Vertical angle", "C": "Angle of inclination", "D": "True angle"}, "answer": "C"},
    {"stem": "37. A line parallel to VP shows its true length in the _____.", "options": {"A": "Plan", "B": "Elevation", "C": "Side view", "D": "Auxiliary view"}, "answer": "B"},
    {"stem": "38. The vertical trace of a line lies on the _____.", "options": {"A": "XY line", "B": "Ground line", "C": "Vertical plane", "D": "Auxiliary plane"}, "answer": "C"},
    {"stem": "39. A line perpendicular to HP has its projection on HP as a _____.", "options": {"A": "Point", "B": "Long line", "C": "Curve", "D": "Arc"}, "answer": "A"},
    {"stem": "40. To find the true angle a line makes with VP, you must first find its _____.", "options": {"A": "Horizontal trace", "B": "Vertical trace", "C": "True length", "D": "Endpoints"}, "answer": "C"},
]

THEORY = [
    {"stem": "Question 1. (a) Define perspective drawing. (b) Describe one-point and two-point perspective with sketches. (c) State five uses of perspective drawing. (d) List four differences between perspective and orthographic drawings.", "marks": Decimal("20.00")},
    {"stem": "Question 2. (a) Define auxiliary view. (b) State three reasons for using auxiliary views. (c) Draw a labelled auxiliary view of a hexagonal prism resting on HP and inclined to VP.", "marks": Decimal("20.00")},
    {"stem": "Question 3. (a) Define CAD. (b) List and explain five advantages of CAD. (c) Describe three CAD commands and their uses.", "marks": Decimal("20.00")},
]

@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="TDR")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="okeh@ndgakuje.org",
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
            source_reference=f"SS2-TDR-20260323-OBJ-{index:02d}",
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
            source_reference=f"SS2-TDR-20260323-TH-{index:02d}",
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
        "paper_code": "SS2-TDR-EXAM",
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
