from __future__ import annotations

import os
import re
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionDifficulty,
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
from apps.results.models import StudentSubjectScore


SOURCE_PATH = Path("/tmp/ss2_tdr_ca23.txt")


def parse_rows(text: str) -> list[dict]:
    text = text.replace("Ã—", "x").replace("Â", "")
    question_start = re.compile(r"(?m)^\s*(\d+)\.\s+")
    option_re = re.compile(r"(?m)^\s*([A-D])\.\s*(.+?)\s*$")
    answer_re = re.compile(r"(?im)^\s*Answer\s*:\s*([A-D])\s*$")
    starts = list(question_start.finditer(text))
    rows = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunk = text[match.start() : end].strip()
        answer_match = answer_re.search(chunk)
        if not answer_match:
            raise RuntimeError(f"Question {match.group(1)} has no answer.")
        answer = answer_match.group(1).upper()
        body = chunk[: answer_match.start()].rstrip()
        option_matches = list(option_re.finditer(body))
        if len(option_matches) != 4:
            raise RuntimeError(f"Question {match.group(1)} has {len(option_matches)} options.")
        stem = body[: option_matches[0].start()].strip()
        stem = re.sub(r"^\s*\d+\.\s*", "", stem)
        stem = re.sub(r"\s+", " ", stem).strip()
        options = {}
        for option_match in option_matches:
            options[option_match.group(1).upper()] = re.sub(r"\s+", " ", option_match.group(2)).strip()
        if set(options) != set("ABCD") or answer not in options:
            raise RuntimeError(f"Question {match.group(1)} has invalid options or answer.")
        rows.append({"number": int(match.group(1)), "stem": stem, "options": options, "answer": answer})
    if len(rows) != 40:
        raise RuntimeError(f"Expected 40 questions, parsed {len(rows)}.")
    return rows


def main():
    rows = parse_rows(SOURCE_PATH.read_text(encoding="utf-8", errors="replace"))
    User = get_user_model()
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    klass = AcademicClass.objects.get(code="SS2")
    subject = Subject.objects.get(code="TDR")
    admin = (
        User.objects.filter(is_superuser=True).order_by("id").first()
        or User.objects.filter(primary_role__code="IT_MANAGER").order_by("id").first()
        or User.objects.order_by("id").first()
    )
    assignment = TeacherSubjectAssignment.objects.filter(
        session=session,
        term=term,
        academic_class=klass,
        subject=subject,
        is_active=True,
    ).first()
    if assignment is None:
        assignment = TeacherSubjectAssignment.objects.filter(
            session=session,
            academic_class=klass,
            subject=subject,
        ).order_by("-id").first()

    now = timezone.now()
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(timezone.datetime(now.year, now.month, now.day, 15, 0), tz)
    end = timezone.make_aware(timezone.datetime(now.year, now.month, now.day, 16, 20), tz)

    with transaction.atomic():
        ClassSubject.objects.update_or_create(academic_class=klass, subject=subject, defaults={"is_active": True})
        all_student_ids = list(
            StudentClassEnrollment.objects.filter(
                academic_class_id__in=klass.cohort_class_ids(),
                session=session,
                is_active=True,
            ).values_list("student_id", flat=True)
        )
        tdr_student_ids = list(
            StudentSubjectScore.objects.filter(
                result_sheet__session=session,
                result_sheet__term=term,
                result_sheet__academic_class=klass,
                result_sheet__subject=subject,
            ).values_list("student_id", flat=True)
        )
        student_ids = [student_id for student_id in all_student_ids if student_id in set(tdr_student_ids)] or all_student_ids
        for student_id in student_ids:
            StudentSubjectEnrollment.objects.update_or_create(
                student_id=student_id,
                subject=subject,
                session=session,
                defaults={"is_active": True},
            )

        bank, _ = QuestionBank.objects.update_or_create(
            owner=admin,
            name="SS2 Technical Drawing Third Term CA2/CA3 2026",
            subject=subject,
            academic_class=klass,
            session=session,
            term=term,
            defaults={
                "description": "Imported from attached Technical Drawing CA2/CA3 text.",
                "assignment": assignment,
                "is_active": True,
            },
        )
        exam, _ = Exam.objects.update_or_create(
            title="SS2 Technical Drawing Third Term CA2/CA3 3:00-4:20",
            subject=subject,
            academic_class=klass,
            session=session,
            term=term,
            defaults={
                "description": "SS2 Technical Drawing CA2/CA3 objective paper.",
                "exam_type": CBTExamType.CA,
                "status": CBTExamStatus.ACTIVE,
                "created_by": admin,
                "assignment": assignment,
                "question_bank": bank,
                "dean_reviewed_by": admin,
                "dean_reviewed_at": now,
                "activated_by": admin,
                "activated_at": now,
                "activation_comment": "Urgent IT activation for SS2 Technical Drawing CA2/CA3.",
                "schedule_start": start,
                "schedule_end": end,
                "is_time_based": True,
                "open_now": False,
                "is_free_test": False,
                "timer_is_paused": False,
            },
        )
        ExamBlueprint.objects.update_or_create(
            exam=exam,
            defaults={
                "duration_minutes": 25,
                "max_attempts": 1,
                "shuffle_questions": False,
                "shuffle_options": False,
                "instructions": "Answer all questions. Each question carries 0.25 mark.",
                "section_config": {"objective_total": "10.00", "question_count": 40, "source": "SS2 Technical Drawing CA2/CA3"},
                "passing_score": Decimal("0.00"),
                "objective_writeback_target": CBTWritebackTarget.CA2,
                "theory_enabled": False,
                "theory_writeback_target": CBTWritebackTarget.NONE,
                "auto_show_result_on_submit": True,
                "finalize_on_logout": False,
                "allow_retake": False,
            },
        )
        attempt_count = ExamAttempt.objects.filter(exam=exam).count()
        if attempt_count:
            raise RuntimeError(f"Existing attempts found on this exact exam ({attempt_count}); refusing to replace live questions.")

        old_question_ids = list(ExamQuestion.objects.filter(exam=exam).values_list("question_id", flat=True))
        ExamQuestion.objects.filter(exam=exam).delete()
        Question.objects.filter(id__in=old_question_ids, question_bank=bank).delete()

        created = 0
        for row in rows:
            question = Question.objects.create(
                question_bank=bank,
                created_by=admin,
                subject=subject,
                question_type=CBTQuestionType.OBJECTIVE,
                stem=row["stem"],
                topic="Technical Drawing CA2/CA3",
                difficulty=CBTQuestionDifficulty.MEDIUM,
                marks=Decimal("0.25"),
                source_type=Question.SourceType.DOCUMENT,
                source_reference="attached Technical Drawing CA2/CA3 text",
                is_active=True,
            )
            option_objs = {}
            for order, label in enumerate("ABCD", start=1):
                option_objs[label] = Option.objects.create(
                    question=question,
                    label=label,
                    option_text=row["options"][label],
                    sort_order=order,
                )
            correct = CorrectAnswer.objects.create(question=question, is_finalized=True)
            correct.correct_options.set([option_objs[row["answer"]]])
            ExamQuestion.objects.create(exam=exam, question=question, sort_order=row["number"], marks=Decimal("0.25"))
            created += 1

        exam.activation_snapshot = {
            "source": "urgent_technical_drawing_import",
            "question_count": created,
            "duration_minutes": 25,
            "schedule_start": start.isoformat(),
            "schedule_end": end.isoformat(),
            "restricted_student_count": len(student_ids),
        }
        exam.save(update_fields=["activation_snapshot", "updated_at"])

    print(
        {
            "exam_id": exam.id,
            "bank_id": bank.id,
            "questions": created,
            "student_count": len(student_ids),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "duration": 25,
        }
    )


if __name__ == "__main__":
    main()
