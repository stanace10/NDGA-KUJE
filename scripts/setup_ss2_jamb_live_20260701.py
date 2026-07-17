"""Create personalized SS2 JAMB CBTs for 1 July 2026, 19:00-20:40 WAT."""

from __future__ import annotations

import hashlib
import os
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django

django.setup()

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    Term,
)
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Question,
    QuestionBank,
)


SECTION_COUNTS = {"English": 60}
BANK_BY_SCHOOL_CODE = {
    "MTH": "Mathematics",
    "PHY": "Physics",
    "CHM": "Chemistry",
    "BIO": "Biology",
    "GOV": "Government",
    "COM": "Commerce",
    "ECO": "Economics",
    "ACC": "Accounting",
    "CRS": "CRS",
    "LIT": "Literature",
    "CPS": "Computer",
    "DIT": "Computer",
    "DAP": "Computer",
    "GEO": "Geography",
    "AGR": "Agriculture",
}
APPROVED_LITERATURE_TOPIC_TERMS = (
    "GENERAL LITERARY PRINCIPLES",
    "LITERARY APPRECIATION",
    "ANTONY AND CLEOPATRA",
    "ONCE UPON AN ELEPHANT",
    "MARRIAGE OF ANANSEWA",
    "AN INSPECTOR CALLS",
    "A MAN OF ALL SEASONS",
    "ONCE UPON A TIME",
    "NEW TONGUE",
    "NIGHT BY WOLE SOYINKA",
    "NOT MY BUSINESS",
    "HEARTY GARLANDS",
    "THE BREAST OF THE SEA",
    "SHE WALKS IN BEAUTY",
    "THE STONE",
    "NUN'S PRIEST'S TALE",
    "NUNS PRIEST TALE",
    "DIGGING",
    "STILL I RISE",
    "TELEPHONE CALL",
    "SO THE PATH DOES NOT DIE",
    "REDEMPTION ROAD",
    "TO KILL A MOCKINGBIRD",
    "PATH OF LUCAS",
)


def _current_period():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    return session, term


def _it_actor():
    actor = (
        User.objects.filter(
            Q(primary_role__code=ROLE_IT_MANAGER)
            | Q(secondary_roles__code=ROLE_IT_MANAGER),
            is_active=True,
        )
        .distinct()
        .order_by("id")
        .first()
    )
    if actor is None:
        actor = User.objects.filter(is_superuser=True, is_active=True).order_by("id").first()
    if actor is None:
        raise RuntimeError("No active IT Manager or superuser exists.")
    return actor


def infer_choices(student, session):
    enrolled = set(
        StudentSubjectEnrollment.objects.filter(
            student=student,
            session=session,
            is_active=True,
        ).values_list("subject__code", flat=True)
    )
    if {"LIT", "GOV"}.issubset(enrolled):
        return ["English", "Literature", "Government", "CRS"]
    if enrolled & {"ACC", "COM"}:
        commercial = "Accounting" if "ACC" in enrolled else "Commerce"
        return ["English", "Mathematics", "Economics", commercial]
    if {"PHY", "CHM"}.issubset(enrolled):
        fourth = "Biology" if "BIO" in enrolled else "Mathematics"
        return ["English", "Physics", "Chemistry", fourth]
    mapped = []
    for code in (
        "MTH", "BIO", "GOV", "ECO", "CRS", "LIT", "GEO", "AGR",
        "COM", "ACC", "CPS", "DAP", "PHY", "CHM",
    ):
        label = BANK_BY_SCHOOL_CODE.get(code)
        if code in enrolled and label and label not in mapped:
            mapped.append(label)
    return ["English", *(mapped[:3])]


def _safe_questions(section):
    bank = QuestionBank.objects.get(name=f"JAMB Review Bank {section} 2026", is_active=True)
    questions = (
        Question.objects.filter(
            question_bank=bank,
            is_active=True,
            question_type=CBTQuestionType.OBJECTIVE,
            topic__istartswith=f"{section}:",
            correct_answer__is_finalized=True,
        )
        .annotate(
            option_count=Count("options", distinct=True),
            correct_count=Count("correct_answer__correct_options", distinct=True),
        )
        .filter(option_count=4, correct_count=1)
    )
    if section == "Literature":
        topic_filter = Q(pk__in=[])
        for term in APPROVED_LITERATURE_TOPIC_TERMS:
            topic_filter |= Q(topic__icontains=term)
        questions = questions.filter(topic_filter)
    return list(questions.order_by("id"))


def _stable_pick(rows, count, seed):
    ranked = sorted(
        rows,
        key=lambda row: hashlib.sha256(f"{seed}:{row.id}".encode("utf-8")).hexdigest(),
    )
    if len(ranked) < count:
        raise RuntimeError(f"Only {len(ranked)} safe questions are available; {count} required.")
    return ranked[:count]


def rebuild_exam_questions(
    exam,
    choices,
    *,
    english_count=60,
    other_count=40,
):
    normalized = []
    for choice in choices:
        label = str(choice or "").strip()
        if label and label not in normalized:
            normalized.append(label)
    if len(normalized) != 4 or normalized[0] != "English":
        raise RuntimeError("Choose exactly four subjects with English first.")
    english_count = int(english_count)
    other_count = int(other_count)
    if not 10 <= english_count <= 60:
        raise RuntimeError("English question count must be between 10 and 60.")
    if not 10 <= other_count <= 40:
        raise RuntimeError("Other-subject question count must be between 10 and 40.")

    selected = []
    section_counts = {}
    for section in normalized:
        count = english_count if section == "English" else other_count
        rows = _safe_questions(section)
        picked = _stable_pick(rows, count, f"{exam.id}:{exam.activation_snapshot.get('student_id')}:{section}")
        selected.extend((section, question) for question in picked)
        section_counts[section] = count

    with transaction.atomic():
        exam.exam_questions.all().delete()
        ExamQuestion.objects.bulk_create(
            [
                ExamQuestion(
                    exam=exam,
                    question=question,
                    sort_order=index,
                    marks=Decimal("1.00"),
                )
                for index, (_section, question) in enumerate(selected, start=1)
            ],
            batch_size=500,
        )
        snapshot = dict(exam.activation_snapshot or {})
        snapshot["jamb_subject_choices"] = normalized
        snapshot["jamb_section_counts"] = section_counts
        exam.activation_snapshot = snapshot
        exam.save(update_fields=["activation_snapshot", "updated_at"])
        blueprint = exam.blueprint
        config = dict(blueprint.section_config or {})
        config.update(
            {
                "paper_code": "JAMB-UTME-PRACTICE",
                "sections": section_counts,
                "randomize_per_section": False,
                "objective_target_max": "400.00",
                "review_seconds": 1500,
                "ui_mode": "JAMB_LIGHT",
                "literature_focus": "2026-2030",
                "english_novel": "The Lekki Headmaster",
            }
        )
        blueprint.section_config = config
        blueprint.save(update_fields=["section_config", "updated_at"])
    return section_counts


def run():
    session, term = _current_period()
    actor = _it_actor()
    jamb = Subject.objects.get(code="JAMB")
    base_ss2 = AcademicClass.objects.get(code="SS2")
    student_ids = list(
        StudentClassEnrollment.objects.filter(
            academic_class__base_class=base_ss2,
            session=session,
            is_active=True,
        )
        .values_list("student_id", flat=True)
        .distinct()
    )
    students = list(
        User.objects.filter(id__in=student_ids, is_active=True)
        .select_related("student_profile")
        .order_by("student_profile__student_number")
    )
    local_tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        timezone.datetime(2026, 7, 1, 19, 0),
        local_tz,
    )
    end = timezone.make_aware(
        timezone.datetime(2026, 7, 1, 20, 40),
        local_tz,
    )
    english_bank = QuestionBank.objects.get(
        name="JAMB Review Bank English 2026",
        is_active=True,
    )
    results = []
    for student in students:
        profile = student.student_profile
        title = f"JAMB UTME Practice - {profile.student_number}"
        exam, _created = Exam.objects.update_or_create(
            title=title,
            session=session,
            term=term,
            defaults={
                "description": (
                    "Personalized SS2 JAMB CBT. English plus the candidate's three "
                    "selected UTME subjects. Practice-only; no school-result writeback."
                ),
                "exam_type": CBTExamType.FREE_TEST,
                "status": CBTExamStatus.ACTIVE,
                "created_by": actor,
                "assignment": None,
                "subject": jamb,
                "academic_class": base_ss2,
                "question_bank": english_bank,
                "dean_reviewed_by": None,
                "activated_by": actor,
                "activated_at": timezone.now(),
                "activation_comment": "Opened by IT for SS2 JAMB CBT on 1 July 2026.",
                "schedule_start": start,
                "schedule_end": end,
                "is_time_based": True,
                "open_now": False,
                "is_free_test": True,
                "activation_snapshot": {
                    "emergency_allowed_student_ids": [student.id],
                    "emergency_restrict_until": end.isoformat(),
                    "student_id": student.id,
                    "student_number": profile.student_number,
                },
            },
        )
        ExamBlueprint.objects.update_or_create(
            exam=exam,
            defaults={
                "duration_minutes": 100,
                "max_attempts": 1,
                "shuffle_questions": True,
                "shuffle_options": True,
                "instructions": (
                    "Answer Use of English and your three selected UTME subjects. "
                    "The timer is 1 hour 40 minutes. Review is available for 15 minutes after submission."
                ),
                "section_config": {},
                "passing_score": Decimal("0.00"),
                "objective_writeback_target": CBTWritebackTarget.NONE,
                "theory_enabled": False,
                "auto_show_result_on_submit": True,
                "finalize_on_logout": False,
                "allow_retake": False,
            },
        )
        choices = infer_choices(student, session)
        if len(choices) != 4:
            results.append((profile.student_number, "BLOCKED", choices))
            exam.status = CBTExamStatus.DRAFT
            exam.save(update_fields=["status", "updated_at"])
            continue
        counts = rebuild_exam_questions(exam, choices)
        results.append((profile.student_number, "READY", choices, sum(counts.values())))

    print(
        {
            "students": len(students),
            "ready": sum(1 for row in results if row[1] == "READY"),
            "blocked": sum(1 for row in results if row[1] != "READY"),
            "window": f"{timezone.localtime(start):%H:%M}-{timezone.localtime(end):%H:%M}",
            "duration_minutes": 100,
        }
    )
    for row in results:
        print(row)
    return results


if __name__ == "__main__":
    run()
