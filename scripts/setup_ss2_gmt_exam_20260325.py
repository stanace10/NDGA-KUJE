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


TITLE = "WED 8:00-9:30 SS2 Garment Making Second Term Exam"
DESCRIPTION = "SS2 GARMENT MAKING SECOND TERM EXAMINATION"
BANK_NAME = "SS2 Garment Making Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 50 minutes. Exam window closes at 9:30 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVES = [
    {"stem": "The basic skirt block is drafted using mainly ______ measurements.", "options": {"A": "Shoulder and bust", "B": "Waist and hip", "C": "Bust and sleeve", "D": "Neck and armhole"}, "answer": "B"},
    {"stem": "Which of the following measurements determines the width of a skirt block?", "options": {"A": "Waist depth", "B": "Hip measurement", "C": "Skirt length", "D": "Dart depth"}, "answer": "B"},
    {"stem": "The standard length of a skirt block is measured from the ______.", "options": {"A": "Waist to knee", "B": "Waist to floor", "C": "Hip to knee", "D": "Bust to waist"}, "answer": "A"},
    {"stem": "Which line is drawn first when drafting a skirt block?", "options": {"A": "Hip line", "B": "Hem line", "C": "Waist line", "D": "Dart line"}, "answer": "C"},
    {"stem": "Darts in skirt blocks are used mainly to ______.", "options": {"A": "Increase fullness", "B": "Reduce fabric", "C": "Shape the garment", "D": "Decorate the skirt"}, "answer": "C"},
    {"stem": "The back skirt block usually contains ______ darts.", "options": {"A": "No dart", "B": "One dart", "C": "Two darts", "D": "Three darts"}, "answer": "C"},
    {"stem": "The front skirt block generally has ______ dart(s).", "options": {"A": "One", "B": "Two", "C": "Three", "D": "None"}, "answer": "A"},
    {"stem": "The back skirt block is wider than the front because of the ______.", "options": {"A": "Waist measurement", "B": "Seat allowance", "C": "Hemline", "D": "Length"}, "answer": "B"},
    {"stem": "Which allowance is added to the back skirt for comfort?", "options": {"A": "Dart allowance", "B": "Seam allowance", "C": "Ease allowance", "D": "Turn-up allowance"}, "answer": "C"},
    {"stem": "Which tool is used for taking body measurements?", "options": {"A": "Set square", "B": "Tape rule", "C": "French curve", "D": "Compass"}, "answer": "B"},
    {"stem": "Adaptation of skirt blocks involves ______.", "options": {"A": "Sewing the skirt", "B": "Altering the basic block", "C": "Cutting fabric", "D": "Adding seams"}, "answer": "B"},
    {"stem": "Which of the following is used to hold pattern pieces on fabric?", "options": {"A": "Needle", "B": "Pins", "C": "Thread", "D": "Thimble"}, "answer": "B"},
    {"stem": "Which of the following is a type of skirt style?", "options": {"A": "Collar", "B": "Sleeve", "C": "Pencil skirt", "D": "Cuff"}, "answer": "C"},
    {"stem": "Pleats are mainly used to ______.", "options": {"A": "Reduce size", "B": "Add decoration only", "C": "Control fullness", "D": "Strengthen seams"}, "answer": "C"},
    {"stem": "Which of the following tools is used for cutting fabric?", "options": {"A": "Tape rule", "B": "Needle", "C": "Scissors", "D": "Pins"}, "answer": "C"},
    {"stem": "Circular skirts have ______ seams.", "options": {"A": "Many", "B": "Two", "C": "One or none", "D": "Four"}, "answer": "C"},
    {"stem": "Which skirt style gives the greatest fullness?", "options": {"A": "Gored skirt", "B": "Pleated skirt", "C": "Yoked skirt", "D": "Circular skirt"}, "answer": "D"},
    {"stem": "The sleeve block is drafted based on the ______ measurement.", "options": {"A": "Neck", "B": "Armhole", "C": "Bust", "D": "Waist"}, "answer": "B"},
    {"stem": "The sleeve cap controls the ______ of the sleeve.", "options": {"A": "Length", "B": "Fit at armhole", "C": "Wrist size", "D": "Hem"}, "answer": "B"},
    {"stem": "A well-fitting sleeve cap must match the ______.", "options": {"A": "Neck opening", "B": "Shoulder seam", "C": "Armhole circumference", "D": "Bust line"}, "answer": "C"},
    {"stem": "Sleeves are adapted mainly to change the ______.", "options": {"A": "Fabric type", "B": "Style and fullness", "C": "Garment length", "D": "Seam finish"}, "answer": "B"},
    {"stem": "Puff sleeves are created by increasing ______.", "options": {"A": "Sleeve length", "B": "Sleeve width", "C": "Armhole depth", "D": "Dart length"}, "answer": "B"},
    {"stem": "Sleeves are grouped into ______ main classes.", "options": {"A": "Two", "B": "Three", "C": "Four", "D": "Five"}, "answer": "B"},
    {"stem": "A set-in sleeve is attached ______.", "options": {"A": "In one piece with the bodice", "B": "At the armhole", "C": "At the neckline", "D": "At the waist"}, "answer": "B"},
    {"stem": "The raglan sleeve extends from the ______.", "options": {"A": "Neckline to underarm", "B": "Shoulder point only", "C": "Bust to waist", "D": "Armhole to hem"}, "answer": "A"},
    {"stem": "Which part of the sewing machine holds the thread?", "options": {"A": "Needle", "B": "Bobbin", "C": "Fabric", "D": "Foot pedal"}, "answer": "B"},
    {"stem": "Which sleeve gives a casual appearance?", "options": {"A": "Set-in", "B": "Raglan", "C": "Kimono", "D": "Bishop"}, "answer": "C"},
    {"stem": "Collars are attached mainly at the ______.", "options": {"A": "Armhole", "B": "Neckline", "C": "Shoulder", "D": "Bust line"}, "answer": "B"},
    {"stem": "Which of the following is a flat collar?", "options": {"A": "Shirt collar", "B": "Waist collar", "C": "Peter Pan collar", "D": "Stand collar"}, "answer": "C"},
    {"stem": "A stand collar lies ______ the neckline.", "options": {"A": "Flat on", "B": "Below", "C": "Above", "D": "Across"}, "answer": "C"},
    {"stem": "Collars are classified based on ______.", "options": {"A": "Fabric used", "B": "Method of attachment", "C": "Colour", "D": "Seam finish"}, "answer": "B"},
    {"stem": "The basic collar draft begins from the ______ measurement.", "options": {"A": "Bust", "B": "Shoulder", "C": "Neck", "D": "Armhole"}, "answer": "C"},
    {"stem": "A shirt collar consists of ______.", "options": {"A": "One part", "B": "Two parts", "C": "Three parts", "D": "Four parts"}, "answer": "B"},
    {"stem": "Which collar has no stand?", "options": {"A": "Shawl collar", "B": "Flat collar", "C": "Stand collar", "D": "Roll collar"}, "answer": "B"},
    {"stem": "The purpose of a collar is to ______.", "options": {"A": "Shorten the garment", "B": "Decorate only", "C": "Finish the neckline", "D": "Hold the sleeves"}, "answer": "C"},
    {"stem": "Accuracy in drafting is ensured by correct ______.", "options": {"A": "Sewing", "B": "Pressing", "C": "Measurement", "D": "Decoration"}, "answer": "C"},
    {"stem": "Which tool is best for shaping curves in drafting?", "options": {"A": "Ruler", "B": "French curve", "C": "Tape rule", "D": "Chalk"}, "answer": "B"},
    {"stem": "Ease is added mainly for ______.", "options": {"A": "Beauty", "B": "Comfort and movement", "C": "Decoration", "D": "Strength"}, "answer": "B"},
    {"stem": "Patterns are transferred to fabric using ______.", "options": {"A": "Pins only", "B": "Carbon paper", "C": "Tailor's chalk", "D": "Scissors"}, "answer": "C"},
    {"stem": "Proper drafting leads to ______ garment fit.", "options": {"A": "Poor", "B": "Average", "C": "Excellent", "D": "Loose"}, "answer": "C"},
]

THEORY = [
    {"stem": "1. Define a skirt block.\n(b) Explain four measurements required for drafting it.", "marks": Decimal("10.00")},
    {"stem": "2. Explain what is meant by adaptation of skirt blocks.\n(b) Describe two skirt styles formed through adaptation.", "marks": Decimal("10.00")},
    {"stem": "3. Describe gored, yoked, pleated and circular skirts.\n(b) Highlight one feature of any one of them.", "marks": Decimal("10.00")},
    {"stem": "4. Define collars.\n(b) Explain the three classification of collars with suitable examples of any two of them.", "marks": Decimal("10.00")},
    {"stem": "5. Define flat collar.", "marks": Decimal("10.00")},
]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="GMT")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="nwachukwu@ndgakuje.org",
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
    schedule_start = datetime(2026, 3, 25, 20, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 21, 30, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Wednesday night paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 8:00 PM WAT.",
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
    exam.dean_review_comment = "Approved for Wednesday night paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 8:00 PM WAT."
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
            source_reference=f"SS2-GMT-20260325-OBJ-{index:02d}",
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
            source_reference=f"SS2-GMT-20260325-TH-{index:02d}",
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
        "paper_code": "SS2-GMT-EXAM",
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
