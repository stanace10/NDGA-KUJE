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

TITLE = "THU 8:00-9:30 JS2 Civic Education Second Term Exam"
DESCRIPTION = "JSS2 CIVIC EDUCATION SECOND TERM EXAMINATION"
BANK_NAME = "JS2 Civic Education Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer any four questions. "
    "Timer is 90 minutes. Exam window closes at 9:30 AM WAT on Thursday, March 26, 2026."
)

OBJECTIVES = [
    {"stem": "The rule of law means that _______.", "options": {"A": "leaders are above the law", "B": "only the rich obey the law", "C": "everyone is equal before the law", "D": "laws are not important"}, "answer": "C"},
    {"stem": "One benefit of the rule of law is _______.", "options": {"A": "oppression", "B": "orderliness in society", "C": "corruption", "D": "favoritism"}, "answer": "B"},
    {"stem": "When people break the law, they should be _______.", "options": {"A": "rewarded", "B": "ignored", "C": "punished according to the law", "D": "praised"}, "answer": "C"},
    {"stem": "The rule of law protects the _______ of citizens.", "options": {"A": "wealth", "B": "rights", "C": "religion", "D": "culture"}, "answer": "B"},
    {"stem": "Which of these enforces the rule of law?", "options": {"A": "Police", "B": "Market women", "C": "Farmers", "D": "Drivers"}, "answer": "A"},
    {"stem": "An example of punishment for breaking the law is _______.", "options": {"A": "promotion", "B": "fine", "C": "praise", "D": "holiday"}, "answer": "B"},
    {"stem": "The court is responsible for _______.", "options": {"A": "making laws", "B": "enforcing laws", "C": "interpreting laws", "D": "breaking laws"}, "answer": "C"},
    {"stem": "Human rights are _______.", "options": {"A": "given by government", "B": "privileges", "C": "fundamental rights of citizens", "D": "only for adults"}, "answer": "C"},
    {"stem": "One group that protects human rights is the _______.", "options": {"A": "Army", "B": "Police", "C": "Judiciary", "D": "Schools"}, "answer": "C"},
    {"stem": "The rule of law ensures _______.", "options": {"A": "injustice", "B": "equality", "C": "chaos", "D": "violence"}, "answer": "B"},
    {"stem": "Consumer rights are rights enjoyed by _______.", "options": {"A": "producers", "B": "sellers", "C": "buyers", "D": "farmers"}, "answer": "C"},
    {"stem": "A consumer has the right to _______.", "options": {"A": "unsafe goods", "B": "correct information", "C": "fake products", "D": "overpricing"}, "answer": "B"},
    {"stem": "Which is a responsibility of a consumer?", "options": {"A": "Cheating sellers", "B": "Reading product labels", "C": "Selling goods", "D": "Producing goods"}, "answer": "B"},
    {"stem": "The right to safety means goods should be _______.", "options": {"A": "cheap", "B": "attractive", "C": "harmful", "D": "safe to use"}, "answer": "D"},
    {"stem": "Consumers should report fake goods to _______.", "options": {"A": "friends", "B": "family", "C": "appropriate authorities", "D": "neighbors"}, "answer": "C"},
    {"stem": "Democracy means government of the _______.", "options": {"A": "rich", "B": "leaders", "C": "people", "D": "army"}, "answer": "C"},
    {"stem": "In democracy, leaders are chosen through _______.", "options": {"A": "force", "B": "inheritance", "C": "elections", "D": "war"}, "answer": "C"},
    {"stem": "One democratic institution is the _______.", "options": {"A": "market", "B": "legislature", "C": "school", "D": "family"}, "answer": "B"},
    {"stem": "The function of the legislature is to _______.", "options": {"A": "make laws", "B": "enforce laws", "C": "interpret laws", "D": "break laws"}, "answer": "A"},
    {"stem": "The executive arm of government _______.", "options": {"A": "makes laws", "B": "enforces laws", "C": "judges cases", "D": "interprets laws"}, "answer": "B"},
    {"stem": "The judiciary is responsible for _______.", "options": {"A": "law enforcement", "B": "law making", "C": "interpretation of laws", "D": "elections"}, "answer": "C"},
    {"stem": "One feature of democracy is _______.", "options": {"A": "dictatorship", "B": "rule of law", "C": "military rule", "D": "autocracy"}, "answer": "B"},
    {"stem": "Freedom of speech is a feature of _______.", "options": {"A": "monarchy", "B": "democracy", "C": "dictatorship", "D": "feudalism"}, "answer": "B"},
    {"stem": "Discipline means _______.", "options": {"A": "doing whatever you like", "B": "obeying rules and regulations", "C": "fighting authority", "D": "being stubborn"}, "answer": "B"},
    {"stem": "A disciplined student _______.", "options": {"A": "disobeys rules", "B": "respects authority", "C": "fights teachers", "D": "skips classes"}, "answer": "B"},
    {"stem": "Courage means _______.", "options": {"A": "fear", "B": "cowardice", "C": "bravery", "D": "laziness"}, "answer": "C"},
    {"stem": "A courageous person _______.", "options": {"A": "runs from danger always", "B": "stands for what is right", "C": "lies often", "D": "cheats others"}, "answer": "B"},
    {"stem": "Contentment means _______.", "options": {"A": "greed", "B": "satisfaction with what one has", "C": "jealousy", "D": "stealing"}, "answer": "B"},
    {"stem": "A contented person avoids _______.", "options": {"A": "honesty", "B": "gratitude", "C": "greed", "D": "discipline"}, "answer": "C"},
    {"stem": "Which of these promotes discipline?", "options": {"A": "corruption", "B": "lawlessness", "C": "obedience", "D": "violence"}, "answer": "C"},
    {"stem": "One benefit of democracy is _______.", "options": {"A": "oppression", "B": "participation of citizens", "C": "war", "D": "chaos"}, "answer": "B"},
    {"stem": "Consumers have the right to choose from _______.", "options": {"A": "one product", "B": "many options", "C": "fake goods", "D": "unsafe goods"}, "answer": "B"},
    {"stem": "The police help in _______.", "options": {"A": "making laws", "B": "enforcing laws", "C": "interpreting laws", "D": "breaking laws"}, "answer": "B"},
    {"stem": "Rule of law prevents _______.", "options": {"A": "justice", "B": "peace", "C": "abuse of power", "D": "equality"}, "answer": "C"},
    {"stem": "Democracy encourages _______.", "options": {"A": "dictatorship", "B": "participation", "C": "fear", "D": "violence"}, "answer": "B"},
    {"stem": "Discipline helps society to be _______.", "options": {"A": "chaotic", "B": "orderly", "C": "violent", "D": "corrupt"}, "answer": "B"},
    {"stem": "Which of these is a universal consumer right?", "options": {"A": "Right to cheat", "B": "Right to information", "C": "Right to fake goods", "D": "Right to violence"}, "answer": "B"},
    {"stem": "Courts protect citizens' _______.", "options": {"A": "wealth", "B": "rights", "C": "food", "D": "jobs"}, "answer": "B"},
    {"stem": "Courage helps citizens to _______.", "options": {"A": "remain silent", "B": "defend justice", "C": "support evil", "D": "avoid responsibility"}, "answer": "B"},
    {"stem": "Contentment promotes _______.", "options": {"A": "corruption", "B": "peace", "C": "greed", "D": "dishonesty"}, "answer": "B"},
]

THEORY = [
    {"stem": "1. Define the rule of law.\n(b) State five benefits of the rule of law.\n(c) Mention three disadvantages.", "marks": Decimal("10.00")},
    {"stem": "2. Explain consumer rights.\n(b) State four responsibilities of a consumer and four rights of a consumer.", "marks": Decimal("10.00")},
    {"stem": "3. Define democracy and mention four democratic institutions and their four functions.", "marks": Decimal("10.00")},
    {"stem": "4. Explain the following: (i) discipline (ii) courage (iii) contentment (iv) integrity (v) power.", "marks": Decimal("10.00")},
    {"stem": "5. State five features of democracy and five pillars of democracy.", "marks": Decimal("10.00")},
    {"stem": "6. Define Nigeria as federation, explain the term Civic Education, and mention six importance of learning Civic Education.", "marks": Decimal("10.00")},
]


def main():
    lagos = ZoneInfo("Africa/Lagos")
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.filter(name="SECOND").order_by("id").first()
    academic_class = AcademicClass.objects.get(code="JS2")
    subject = Subject.objects.get(code="CVC")
    assignment = TeacherSubjectAssignment.objects.filter(
        subject=subject,
        academic_class=academic_class,
        session=session,
        is_active=True,
    ).order_by("id").first()
    if assignment is None:
        raise RuntimeError("No active JS2 Civic assignment found")
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
                source_reference=f"JS2-CVC-20260326-OBJ-{index:02d}",
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
                source_reference=f"JS2-CVC-20260326-TH-{index:02d}",
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
            "paper_code": "JS2-CVC-EXAM",
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
