"""Publish every supplied, non-empty Third Term paper, preserving known defects.

Management has explicitly accepted incomplete source documents for publication.
This script never invents missing questions, options, theory, or answer keys.
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.db.models import Q

from apps.accounts.constants import ROLE_DEAN, ROLE_IT_MANAGER
from apps.accounts.models import User
from apps.academics.models import AcademicSession, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTExamStatus,
    CBTQuestionType,
    CBTWritebackTarget,
    Exam,
    ExamQuestion,
    Question,
)
from apps.cbt.workflow import (
    _activation_snapshot_hash,
    _activation_snapshot_payload,
    it_activate_exam,
)
from scripts.import_third_term_exams_20260629 import (
    IMPORT_TAG,
    SLOTS,
    SOURCES,
    SOURCE_ROOT,
    combined_source,
    configured_base,
)


EXISTING_ISSUES = {
    1043: "40 objective questions but only 39 source answer markers; one answer key cannot be independently verified.",
    1041: "Four repeated objective questions in the supplied Digital Technology source.",
    1045: "38 safe objective blocks from 39 source answer markers; one French question block is missing.",
    1038: "39 safe questions from 40 answer markers; extracted mathematical expressions and some stems are truncated.",
    1039: "39 safe questions from 40 source answer markers; one Music question is missing.",
    1048: "82 answer markers but 78 safe Yoruba questions; trailing/language blocks are malformed.",
    1057: "47 safe Basic Science questions from 50 source answer markers; three questions are missing.",
    1059: "39 safe French questions from 40 source answer markers; one question is missing.",
    1063: "61 parsed Igbo questions versus 78 answer markers, two duplicates, and malformed text around Question 23.",
    1049: "49 safe questions from 50 answer markers, three duplicate stems, and a truncated algebraic expression.",
    1051: "39 safe Music questions from 40 source answer markers; one question is missing and some endings are broken.",
    1077: "48 CRS questions but only 47 explicit answer markers; at least one answer key is unverified.",
    1078: "48 safe Economics questions from 50 source answer markers; two questions are missing.",
    1071: "49 safe Food & Nutrition questions from 50 markers; one is missing and Question 48 is truncated.",
    1081: "French numbering/answer blocks are ambiguous: 60 parsed questions and 67 answer markers.",
    1079: "Further Mathematics powers, roots, vectors and formulas are corrupted; 40 parsed rows versus 51 answer markers.",
    1064: "Mathematics powers, fractions and formulas are corrupted; 42 parsed rows versus 50 answer markers.",
    1095: "50 CRS questions but 49 explicit answer markers; one key is unverified and two stems are incomplete.",
    1085: "18 safe Civic Education questions from 47 answer markers; 29 source questions were merged or lost.",
    1096: "49 safe Economics questions from 50 source answer markers; one question is missing.",
    1088: "45 safe English questions from 50 source answer markers; five questions are missing.",
    1090: "47 safe Food & Nutrition questions from 50 source answer markers; three questions are missing.",
    1099: "54 safe French questions from 55 source answer markers; one question is missing.",
    1092: "The Physics paper repeats the electric-charge SI-unit question at Questions 12 and 21.",
    1083: "38 safe Visual Art questions from 40 source answer markers; two questions are missing.",
}

NEW_RECOVERABLE = {
    ("JS1", "SCS"): {
        "slot": "J2",
        "issue": "29 safe objective questions are present from 30 source answer markers; one question block is missing from the supplied paper.",
    },
    ("JS1", "HAU"): {
        "slot": "J20",
        "issue": "49 objective questions are present, but the supplied paper has no usable answer key; automatic objective marking is disabled.",
    },
    ("JS2", "BTE"): {
        "slot": "J7",
        "issue": "39 safe objective questions are present from 40 source answer markers; one question block is missing from the supplied paper.",
    },
    ("JS2", "HAU"): {
        "slot": "J20",
        "issue": "48 objective questions are present, but the supplied paper has no usable answer key; automatic objective marking is disabled.",
    },
    ("SS1", "AGR"): {
        "slot": "S2",
        "issue": "50 objective questions are present, but only 49 supplied answers are usable; one objective item cannot be automatically marked.",
    },
    ("SS1", "CHM"): {
        "slot": "S4",
        "issue": "47 safe objective questions are present from 50 source answer markers; three question blocks are missing from the supplied paper.",
    },
    ("SS2", "CHM"): {
        "slot": "S4",
        "issue": "43 safe objective questions are present from 50 source answer markers; seven question blocks are missing from the supplied paper.",
    },
    ("SS2", "LIT"): {
        "slot": "S10",
        "issue": "The objective section is present, but no usable theory section was supplied; students will see the objective section only.",
    },
}


def _role_user(role_code):
    return (
        User.objects.filter(
            Q(primary_role__code=role_code) | Q(secondary_roles__code=role_code),
            is_active=True,
        )
        .distinct()
        .order_by("id")
        .first()
    )


def _refresh_snapshot(exam):
    exam.activation_snapshot = _activation_snapshot_payload(exam)
    exam.activation_snapshot_hash = _activation_snapshot_hash(exam.activation_snapshot)
    exam.save(
        update_fields=[
            "activation_snapshot",
            "activation_snapshot_hash",
            "updated_at",
        ]
    )


def _configure_published_exam(exam, issue, *, no_automatic_objective=False, objective_only=False):
    blueprint = exam.blueprint
    config = dict(blueprint.section_config or {})
    config.update(
        {
            "flow_type": "OBJECTIVE" if objective_only else "OBJECTIVE_THEORY",
            "objective_target_max": "20.00",
            "theory_target_max": "0.00" if objective_only else "30.00",
            "theory_response_mode": "PAPER",
            "manual_score_split": True,
            "known_source_issue": issue,
        }
    )
    config.pop("ca_target", None)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.section_config = config
    blueprint.objective_writeback_target = (
        CBTWritebackTarget.NONE if no_automatic_objective else CBTWritebackTarget.OBJECTIVE
    )
    blueprint.theory_enabled = not objective_only
    blueprint.theory_writeback_target = (
        CBTWritebackTarget.NONE if objective_only else CBTWritebackTarget.THEORY
    )
    blueprint.auto_show_result_on_submit = False
    blueprint.allow_retake = False
    blueprint.save()
    exam.activation_comment = f"PUBLISHED WITH DECLARED SOURCE ISSUE - {issue}"
    exam.save(update_fields=["activation_comment", "updated_at"])
    Question.objects.filter(exam_links__exam=exam).update(topic="Third Term Examination")
    _refresh_snapshot(exam)


def _publish_existing(exam, it_actor, issue):
    exam.status = CBTExamStatus.APPROVED
    exam.open_now = False
    exam.activated_by = None
    exam.activated_at = None
    exam.activation_snapshot = {}
    exam.activation_snapshot_hash = ""
    exam.save(
        update_fields=[
            "status",
            "open_now",
            "activated_by",
            "activated_at",
            "activation_snapshot",
            "activation_snapshot_hash",
            "updated_at",
        ]
    )
    it_activate_exam(
        exam=exam,
        actor=it_actor,
        open_now=False,
        is_time_based=True,
        schedule_start=exam.schedule_start,
        schedule_end=exam.schedule_end,
        comment=f"PUBLISHED WITH DECLARED SOURCE ISSUE - {issue}",
    )
    _configure_published_exam(exam, issue)


def _zero_unkeyed_question_marks(exam):
    keyed_ids = set(
        exam.exam_questions.filter(
            question__question_type=CBTQuestionType.OBJECTIVE,
            question__correct_answer__is_finalized=True,
            question__correct_answer__correct_options__isnull=False,
        ).values_list("id", flat=True)
    )
    objective_links = list(
        exam.exam_questions.filter(question__question_type=CBTQuestionType.OBJECTIVE)
        .order_by("sort_order")
    )
    keyed_count = len([row for row in objective_links if row.id in keyed_ids])
    if not keyed_count:
        return
    total_cents = 2000
    base_cents, extra_count = divmod(total_cents, keyed_count)
    keyed_seen = 0
    for link in objective_links:
        if link.id not in keyed_ids:
            link.marks = Decimal("0.00")
        else:
            keyed_seen += 1
            cents = base_cents + (1 if keyed_seen <= extra_count else 0)
            link.marks = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"))
        ExamQuestion.objects.filter(pk=link.pk).update(marks=link.marks)


@transaction.atomic
def run():
    it_actor = _role_user(ROLE_IT_MANAGER)
    dean_actor = _role_user(ROLE_DEAN)
    if it_actor is None or dean_actor is None:
        raise RuntimeError("An active IT Manager and Dean account are required.")

    existing_published = []
    for exam_id, issue in EXISTING_ISSUES.items():
        exam = Exam.objects.select_related("blueprint").get(
            pk=exam_id,
            description__contains=IMPORT_TAG,
        )
        if exam.status == CBTExamStatus.DRAFT:
            _publish_existing(exam, it_actor, issue)
        elif exam.status != CBTExamStatus.ACTIVE:
            raise RuntimeError(f"Exam {exam_id} has unexpected status {exam.status}.")
        else:
            _configure_published_exam(exam, issue)
        existing_published.append((exam.academic_class.code, exam.subject.code, exam.id))

    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="THIRD")
    assignments = {
        (row.academic_class.code, row.subject.code): row
        for row in TeacherSubjectAssignment.objects.filter(
            session=session,
            term=term,
            is_active=True,
        ).select_related("teacher", "subject", "academic_class")
    }
    base = configured_base()
    new_published = []
    with tempfile.TemporaryDirectory(prefix="ndga-recoverable-exams-") as folder:
        temp_dir = Path(folder)
        for key, config in NEW_RECOVERABLE.items():
            assignment = assignments.get(key)
            if assignment is None:
                raise RuntimeError(f"No active assignment exists for {key}.")
            existing = (
                Exam.objects.select_related("blueprint")
                .filter(
                    academic_class=assignment.academic_class,
                    subject=assignment.subject,
                    description__contains=IMPORT_TAG,
                )
                .order_by("-id")
                .first()
            )
            if existing is not None:
                _configure_published_exam(
                    existing,
                    config["issue"],
                    no_automatic_objective=key[1] == "HAU",
                    objective_only=key == ("SS2", "LIT"),
                )
                new_published.append(
                    (
                        key[0],
                        key[1],
                        existing.id,
                        existing.exam_questions.filter(
                            question__question_type=CBTQuestionType.OBJECTIVE
                        ).count(),
                        existing.exam_questions.exclude(
                            question__question_type=CBTQuestionType.OBJECTIVE
                        ).count(),
                    )
                )
                continue
            rel_paths = SOURCES[key]
            paths = [SOURCE_ROOT / value for value in rel_paths]
            if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
                raise RuntimeError(f"Recoverable source is absent or empty for {key}.")
            source_path = combined_source(base, paths, temp_dir, key)
            date_text, slot_label = SLOTS[config["slot"]]
            result = base.import_exam(
                source_path=source_path,
                assignment=assignment,
                it_user=it_actor,
                dean_user=dean_actor,
                date_text=date_text,
                slot_label=slot_label,
                dry_run=False,
            )
            exam = Exam.objects.select_related("blueprint").get(pk=result["exam_id"])
            exam.description = (
                f"{IMPORT_TAG}: Imported from {', '.join(rel_paths)}. "
                f"KNOWN SOURCE ISSUE: {config['issue']}"
            )
            exam.save(update_fields=["description", "updated_at"])
            if key == ("SS1", "AGR"):
                _zero_unkeyed_question_marks(exam)
            _configure_published_exam(
                exam,
                config["issue"],
                no_automatic_objective=key[1] == "HAU",
                objective_only=key == ("SS2", "LIT"),
            )
            new_published.append(
                (
                    key[0],
                    key[1],
                    exam.id,
                    result["objective_count"],
                    result["theory_count"],
                )
            )

    imported = Exam.objects.filter(description__contains=IMPORT_TAG)
    print(
        {
            "existing_published": existing_published,
            "new_published": new_published,
            "active_total": imported.filter(status=CBTExamStatus.ACTIVE).count(),
            "draft_total": imported.filter(status=CBTExamStatus.DRAFT).count(),
        }
    )


run()
