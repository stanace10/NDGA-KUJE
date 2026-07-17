import csv
import json
import logging
import random
import re
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import RedirectView, TemplateView

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.permissions import has_any_role
from apps.accounts.models import StudentProfile
from apps.academics.models import AcademicClass, AcademicSession, StudentClassEnrollment, StudentSubjectEnrollment, Subject, Term
from apps.academics.subject_policy import subject_is_excluded_from_results
from apps.academics.term_policy import class_is_external_exam_class_for_term
from apps.academics.term_policy import exclude_external_exam_classes_for_term
from apps.audit.models import AuditCategory, AuditEvent, AuditStatus
from apps.audit.services import log_cbt_config_edit, log_event
from apps.cbt.forms import (
    AIExamDraftForm,
    DeanExamDecisionForm,
    DeanSimulationDecisionForm,
    ExamAttachQuestionsForm,
    ExamAttachSimulationsForm,
    ExamCreateForm,
    ExamSubmitToDeanForm,
    ExamUploadImportForm,
    ITExamActivationForm,
    ITExamCloseForm,
    QuestionAuthoringForm,
    QuestionBankCreateForm,
    SimulationImportScoreForm,
    SimulationRubricScoringForm,
    SimulationSubmitToDeanForm,
    SimulationVerifyScoringForm,
    SimulationWrapperCreateForm,
    StudentSimulationEvidenceForm,
)
from apps.cbt.models import (
    CBTAttemptStatus,
    CBTExamType,
    CBTExamStatus,
    CBTQuestionType,
    CBTSimulationAttemptStatus,
    CBTSimulationScoreMode,
    CBTSimulationWrapperStatus,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamAttempt,
    ExamAttemptAnswer,
    ExamBlueprint,
    ExamDocumentImport,
    ExamQuestion,
    ExamReviewAction,
    ExamSimulation,
    Option,
    Question,
    QuestionBank,
    SimulationAttemptRecord,
    SimulationWrapper,
)
from apps.cbt.services import (
    apply_theory_scores,
    attempt_deadline,
    attempt_remaining_seconds,
    attempt_timer_is_paused,
    authoring_assignment_queryset,
    cbt_exam_is_current,
    authoring_exam_queryset,
    authoring_question_bank_queryset,
    build_exam_from_uploaded_document,
    build_exam_with_ai_draft,
    can_manage_all_cbt,
    capture_auto_simulation_score,
    close_expired_exams,
    exam_occurs_on_day,
    exam_schedule_anchor,
    get_or_start_attempt,
    import_simulation_score_to_results,
    it_unlock_attempt,
    lockdown_warning_count,
    ordered_attempt_simulation_records,
    option_list_for_attempt_answer,
    ordered_attempt_answer_refs,
    ordered_attempt_answers,
    simulation_marking_queryset_for_user,
    simulation_catalog_grouped_labels,
    recommended_simulation_queryset,
    simulation_registry_queryset,
    seed_curated_simulation_library,
    record_lockdown_violation,
    record_lockdown_warning,
    record_lockdown_evidence,
    recent_lockdown_activity,
    register_lockdown_heartbeat,
    save_attempt_answer,
    save_attempt_objective_answer_fast,
    submit_rubric_simulation_start,
    submit_verify_simulation_evidence,
    student_available_exams,
    submit_attempt,
    teacher_score_rubric_simulation,
    teacher_verify_simulation_score,
    theory_marking_queryset_for_user,
    ensure_simulation_records_for_attempt,
    _queue_attempt_snapshot,
    _save_attempt_integrity_bundle,
    pause_exam_timer,
    resume_exam_timer,
)
from apps.cbt.workflow import (
    dean_approve_simulation,
    dean_approve_exam,
    dean_reject_simulation,
    dean_reject_exam,
    it_activate_exam,
    it_close_exam,
    it_revoke_exam,
    submit_exam_to_it_manager,
    submit_simulation_to_dean,
    submit_exam_to_dean,
)
from apps.results.cbt_policy import normalize_result_cbt_policies
from apps.results.models import ResultSheet, StudentSubjectScore
from apps.setup_wizard.models import AcademicOperationWindow
from apps.setup_wizard.services import get_academic_window_state, get_setup_state, require_academic_window
from core.ai import ai_json_response

CBT_AUTHORING_ROLES = {
    ROLE_SUBJECT_TEACHER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
}
CBT_DEAN_ROLES = {ROLE_DEAN, ROLE_IT_MANAGER}
CBT_IT_ROLES = {ROLE_IT_MANAGER}
CBT_BLOCKED_LEADERSHIP_ROLES = {ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR}
CBT_MARKING_ROLES = {
    ROLE_SUBJECT_TEACHER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
}

OBJECTIVE_QUESTION_TYPES = {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}

logger = logging.getLogger(__name__)


def _has_cbt_workspace_access(user, allowed_roles):
    if (
        has_any_role(user, CBT_BLOCKED_LEADERSHIP_ROLES)
        and not getattr(user, "is_superuser", False)
        and not user.has_role(ROLE_IT_MANAGER)
    ):
        return False
    return has_any_role(user, allowed_roles)


def _cbt_window_state_for(user):
    return get_academic_window_state(
        window_type=AcademicOperationWindow.WindowType.CBT,
        user=user,
    )


def _require_cbt_window(*, user, action_label):
    return require_academic_window(
        window_type=AcademicOperationWindow.WindowType.CBT,
        user=user,
        action_label=action_label,
    )


JAMB_SECTION_ORDER = [
    "English",
    "Mathematics",
    "Physics",
    "Chemistry",
    "Biology",
    "Computer",
    "Literature",
    "Government",
    "CRS",
    "Economics",
    "Commerce",
    "Accounting",
    "Geography",
    "Agriculture",
]


def _question_section_label(question):
    topic = (getattr(question, "topic", "") or "").strip()
    if ":" in topic:
        return topic.split(":", 1)[0].strip()
    return ""


def _jamb_subject():
    return Subject.objects.filter(code="JAMB").first()


def _jamb_exams_queryset():
    jamb = _jamb_subject()
    if not jamb:
        return Exam.objects.none()
    return (
        Exam.objects.select_related("academic_class", "blueprint", "session", "term")
        .filter(subject=jamb, title__startswith="JAMB UTME Practice")
        .order_by("academic_class__code", "title")
    )


def _jamb_latest_attempts_by_exam():
    attempts = (
        ExamAttempt.objects.select_related("student", "student__student_profile", "exam")
        .filter(exam__in=_jamb_exams_queryset())
        .order_by("exam_id", "-submitted_at", "-created_at", "-id")
    )
    latest = {}
    for attempt in attempts:
        latest.setdefault(attempt.exam_id, attempt)
    return latest


def _jamb_candidate_rows():
    rows = []
    latest_attempts = _jamb_latest_attempts_by_exam()
    answers_by_attempt = {}
    latest_attempt_ids = [
        attempt.id
        for attempt in latest_attempts.values()
        if attempt is not None
    ]
    if latest_attempt_ids:
        answer_rows = (
            ExamAttemptAnswer.objects.filter(attempt_id__in=latest_attempt_ids)
            .values(
                "attempt_id",
                "exam_question__question__topic",
                "is_correct",
                "response_text",
            )
            .annotate(selected_count=Count("selected_options", distinct=True))
            .order_by("attempt_id")
        )
        for answer in answer_rows:
            answers_by_attempt.setdefault(answer["attempt_id"], []).append(answer)
    User = get_user_model()
    for exam in _jamb_exams_queryset():
        student = None
        allowed_ids = (exam.activation_snapshot or {}).get("emergency_allowed_student_ids") or []
        if allowed_ids:
            student = User.objects.filter(pk=allowed_ids[0]).select_related("student_profile").first()
        attempt = latest_attempts.get(exam.id)
        if attempt and attempt.student_id:
            student = attempt.student
        profile = getattr(student, "student_profile", None) if student else None
        section_config = (
            (getattr(exam, "blueprint", None).section_config or {}).get("sections")
            or {}
        )
        sections = list(section_config.keys())
        section_scores = {
            section: {
                "correct": 0,
                "answered": 0,
                "total": int(section_config.get(section) or 0),
                "score": Decimal("0.00"),
            }
            for section in sections
        }
        if attempt:
            for answer in answers_by_attempt.get(attempt.id, []):
                topic = (answer.get("exam_question__question__topic") or "").strip()
                section = (
                    topic.split(":", 1)[0].strip()
                    if ":" in topic
                    else exam.subject.name
                )
                data = section_scores.setdefault(
                    section,
                    {
                        "correct": 0,
                        "answered": 0,
                        "total": 0,
                        "score": Decimal("0.00"),
                    },
                )
                if int(answer.get("selected_count") or 0) or (
                    answer.get("response_text") or ""
                ).strip():
                    data["answered"] += 1
                if answer.get("is_correct") is True:
                    data["correct"] += 1
            for data in section_scores.values():
                if data["total"]:
                    data["score"] = (
                        Decimal(data["correct"]) / Decimal(data["total"]) * Decimal("100.00")
                    ).quantize(Decimal("0.01"))
        section_rows = [
            {
                "name": section,
                "correct": section_scores.get(section, {}).get("correct", 0),
                "answered": section_scores.get(section, {}).get("answered", 0),
                "total": section_scores.get(section, {}).get("total", 0),
                "score": section_scores.get(section, {}).get("score", Decimal("0.00")),
            }
            for section in sections
        ]
        live_total = sum(
            (row["score"] for row in section_scores.values()),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        total_score = (
            Decimal(attempt.total_score or 0)
            if attempt
            and attempt.status in {CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED}
            else live_total
        )
        answered_count = sum(row.get("answered", 0) for row in section_scores.values())
        question_count = sum(row.get("total", 0) for row in section_scores.values())
        percent = (total_score / Decimal("400.00") * Decimal("100.00")).quantize(Decimal("0.01"))
        rows.append(
            {
                "exam": exam,
                "attempt": attempt,
                "student": student,
                "profile": profile,
                "name": (student.get_full_name() if student else "") or "Unknown student",
                "admission_no": (getattr(profile, "student_number", "") or getattr(student, "admission_number", "")) if student else "",
                "sections": sections,
                "section_scores": section_scores,
                "section_rows": section_rows,
                "answered_count": answered_count,
                "question_count": question_count,
                "progress_percent": (
                    int((answered_count / question_count) * 100)
                    if question_count
                    else 0
                ),
                "total_score": total_score.quantize(Decimal("0.01")),
                "percent": percent,
                "submitted": bool(attempt and attempt.status in {CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED}),
                "locked": bool(attempt and attempt.is_locked),
                "writing": bool(
                    attempt
                    and attempt.status == CBTAttemptStatus.IN_PROGRESS
                    and not attempt.is_locked
                ),
                "status": attempt.get_status_display() if attempt else "Not started",
            }
        )
    rows.sort(key=lambda row: (row["submitted"], row["total_score"], row["name"]), reverse=True)
    return rows


def _jamb_bank_audit():
    cache_key = "cbt:jamb-bank-audit"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    jamb = _jamb_subject()
    if not jamb:
        return {"total": 0, "subject_counts": {}, "bad_options": 0, "missing_answers": 0, "missing_explanations": 0}
    questions = list(
        Question.objects.filter(subject=jamb, is_active=True)
        .annotate(
            option_count=Count("options", distinct=True),
            correct_count=Count(
                "correct_answer__correct_options",
                distinct=True,
            ),
        )
        .values(
            "topic",
            "option_count",
            "correct_count",
            "correct_answer__note",
        )
    )
    subject_counts = {section: 0 for section in JAMB_SECTION_ORDER}
    bad_options = missing_answers = missing_explanations = 0
    for question in questions:
        topic = (question.get("topic") or "").strip()
        section = topic.split(":", 1)[0].strip() if ":" in topic else ""
        if section:
            subject_counts[section] = subject_counts.get(section, 0) + 1
        if int(question.get("option_count") or 0) != 4:
            bad_options += 1
        if int(question.get("correct_count") or 0) != 1:
            missing_answers += 1
        if not (question.get("correct_answer__note") or "").strip():
            missing_explanations += 1
    result = {
        "total": len(questions),
        "subject_counts": subject_counts,
        "bad_options": bad_options,
        "missing_answers": missing_answers,
        "missing_explanations": missing_explanations,
    }
    cache.set(cache_key, result, timeout=300)
    return result


CBT_CURRENT_TERM_ONLY_MESSAGE = "Previous-term CBT records are not available in the CBT portal."


def _current_cbt_json_error():
    return JsonResponse(
        {"ok": False, "error": CBT_CURRENT_TERM_ONLY_MESSAGE},
        status=404,
    )


def _exam_is_editable_for_actor(*, actor, exam):
    setup_state = get_setup_state()
    role_codes = actor.get_all_role_codes() if getattr(actor, "is_authenticated", False) else set()
    current_term_start_date = None
    if exam.term_id and setup_state.current_term_id == exam.term_id:
        from apps.attendance.models import SchoolCalendar

        current_term_start_date = (
            SchoolCalendar.objects.filter(
                session=setup_state.current_session,
                term=setup_state.current_term,
            )
            .values_list("start_date", flat=True)
            .first()
        )
    if (
        exam.term_id
        and setup_state.current_term_id == exam.term_id
        and current_term_start_date
        and current_term_start_date > timezone.localdate()
        and role_codes & {ROLE_SUBJECT_TEACHER, ROLE_FORM_TEACHER, ROLE_DEAN}
    ):
        return False
    if can_manage_all_cbt(actor):
        return exam.status in {
            CBTExamStatus.DRAFT,
            CBTExamStatus.PENDING_DEAN,
            CBTExamStatus.PENDING_IT,
            CBTExamStatus.APPROVED,
            CBTExamStatus.ACTIVE,
            CBTExamStatus.CLOSED,
        }
    return exam.status == CBTExamStatus.DRAFT


def _exam_open_url(exam):
    if exam.status != CBTExamStatus.DRAFT:
        return reverse("cbt:exam-detail", kwargs={"exam_id": exam.id})
    blueprint = getattr(exam, "blueprint", None)
    section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
    if not isinstance(section_config, dict):
        section_config = {}
    if exam.exam_type == CBTExamType.SIM or section_config.get("flow_type") == ExamCreateForm.FLOW_SIMULATION:
        return reverse("cbt:exam-simulation-picker", kwargs={"exam_id": exam.id})
    return reverse("cbt:exam-builder", kwargs={"exam_id": exam.id})


def _simulation_preview_url(wrapper):
    path = (wrapper.offline_asset_path or "").strip()
    if path:
        if path.startswith("http://") or path.startswith("https://") or path.startswith("/"):
            return path
        if path.startswith("media/"):
            return f"/{path}"
        if path.startswith("static/"):
            return f"/{path}"
        return f"/media/{path}"
    return (wrapper.online_url or "").strip()


def _next_exam_sort_order(exam):
    max_order = (
        exam.exam_questions.order_by("-sort_order")
        .values_list("sort_order", flat=True)
        .first()
        or 0
    )
    return int(max_order) + 1


def _ensure_exam_question_bank(*, exam):
    if exam.question_bank_id:
        return exam.question_bank
    bank = QuestionBank.objects.create(
        name=f"{exam.title} Bank",
        description="Auto-created for CBT builder flow.",
        owner=exam.created_by,
        assignment=exam.assignment,
        subject=exam.subject,
        academic_class=exam.academic_class,
        session=exam.session,
        term=exam.term,
        is_active=True,
    )
    exam.question_bank = bank
    exam.save(update_fields=["question_bank", "updated_at"])
    return bank


def _builder_config(exam):
    blueprint = getattr(exam, "blueprint", None)
    section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
    if not isinstance(section_config, dict):
        section_config = {}
    objective_count = section_config.get("objective_count")
    theory_count = section_config.get("theory_count")
    existing_objective = exam.exam_questions.filter(
        question__question_type__in=OBJECTIVE_QUESTION_TYPES
    ).count()
    existing_theory = exam.exam_questions.exclude(
        question__question_type__in=OBJECTIVE_QUESTION_TYPES
    ).count()
    try:
        objective_count = int(objective_count)
    except (TypeError, ValueError):
        objective_count = existing_objective
    try:
        theory_count = int(theory_count)
    except (TypeError, ValueError):
        theory_count = existing_theory

    flow_type = section_config.get("flow_type")
    if not flow_type:
        if exam.exam_type == CBTExamType.SIM:
            flow_type = ExamCreateForm.FLOW_SIMULATION
        elif exam.exam_type == CBTExamType.FREE_TEST:
            flow_type = ExamCreateForm.FLOW_OBJECTIVE_ONLY
        elif theory_count and objective_count:
            flow_type = ExamCreateForm.FLOW_OBJECTIVE_THEORY
        else:
            flow_type = ExamCreateForm.FLOW_OBJECTIVE_THEORY

    default_objective_total, default_theory_total = ExamCreateForm._default_section_totals(
        exam_type=exam.exam_type,
        flow_type=flow_type,
    )

    def _as_decimal(raw_value, fallback):
        try:
            return Decimal(str(raw_value)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return fallback

    objective_target_max = _as_decimal(
        section_config.get("objective_target_max"),
        default_objective_total,
    )
    theory_target_max = _as_decimal(
        section_config.get("theory_target_max"),
        default_theory_total,
    )
    if objective_count <= 0:
        objective_target_max = Decimal("0.00")
    if theory_count <= 0:
        theory_target_max = Decimal("0.00")

    return {
        "flow_type": flow_type,
        "objective_count": max(int(objective_count or 0), 0),
        "theory_count": max(int(theory_count or 0), 0),
        "theory_response_mode": section_config.get("theory_response_mode")
        or ExamCreateForm.THEORY_RESPONSE_MODE_PAPER,
        "calculator_mode": (section_config.get("calculator_mode") or "NONE").upper(),
        "ca_target": section_config.get("ca_target") or "",
        "manual_score_split": bool(section_config.get("manual_score_split")),
        "objective_target_max": objective_target_max,
        "theory_target_max": theory_target_max,
    }


def _distributed_section_marks(*, target_total, question_count):
    if question_count <= 0:
        return []
    total = Decimal(str(target_total or 0)).quantize(Decimal("0.01"))
    if total <= 0:
        return [Decimal("1.00")] * question_count
    per_mark = (total / Decimal(question_count)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    if per_mark <= 0:
        per_mark = Decimal("0.01")
    distributed = [per_mark for _ in range(question_count)]
    remainder = (total - (per_mark * Decimal(question_count - 1))).quantize(Decimal("0.01"))
    if remainder > 0:
        distributed[-1] = remainder
    return distributed


def _apply_builder_auto_marks(exam, *, config=None):
    config = config or _builder_config(exam)
    objective_rows = list(
        exam.exam_questions.select_related("question")
        .filter(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order", "id")
    )
    theory_rows = list(
        exam.exam_questions.select_related("question")
        .exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order", "id")
    )
    objective_marks = _distributed_section_marks(
        target_total=config.get("objective_target_max") or Decimal("0.00"),
        question_count=len(objective_rows),
    )
    theory_marks = _distributed_section_marks(
        target_total=config.get("theory_target_max") or Decimal("0.00"),
        question_count=len(theory_rows),
    )
    for row, mark in zip(objective_rows, objective_marks):
        mark = mark.quantize(Decimal("0.01"))
        if row.marks != mark:
            row.marks = mark
            row.save(update_fields=["marks", "updated_at"])
        if row.question.marks != mark:
            row.question.marks = mark
            row.question.save(update_fields=["marks", "updated_at"])
    for row, mark in zip(theory_rows, theory_marks):
        mark = mark.quantize(Decimal("0.01"))
        if row.marks != mark:
            row.marks = mark
            row.save(update_fields=["marks", "updated_at"])
        if row.question.marks != mark:
            row.question.marks = mark
            row.question.save(update_fields=["marks", "updated_at"])


def _create_placeholder_objective_question(*, exam, bank):
    question_number = exam.exam_questions.filter(
        question__question_type__in=OBJECTIVE_QUESTION_TYPES
    ).count() + 1
    question = Question.objects.create(
        question_bank=bank,
        created_by=exam.created_by,
        subject=exam.subject,
        question_type=CBTQuestionType.OBJECTIVE,
        stem=f"Objective Question {question_number}",
        topic="",
        difficulty="MEDIUM",
        marks=1,
        source_type=Question.SourceType.MANUAL,
        source_reference="CBT_BUILDER",
        is_active=True,
    )
    for label, text, order in (
        ("A", "Option A", 1),
        ("B", "Option B", 2),
        ("C", "Option C", 3),
        ("D", "Option D", 4),
    ):
        Option.objects.create(
            question=question,
            label=label,
            option_text=text,
            sort_order=order,
        )
    answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
    answer.correct_options.set(question.options.filter(label="A"))
    ExamQuestion.objects.create(
        exam=exam,
        question=question,
        sort_order=_next_exam_sort_order(exam),
        marks=question.marks,
    )


def _create_placeholder_theory_question(*, exam, bank):
    question_number = (
        exam.exam_questions.exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES).count() + 1
    )
    question = Question.objects.create(
        question_bank=bank,
        created_by=exam.created_by,
        subject=exam.subject,
        question_type=CBTQuestionType.SHORT_ANSWER,
        stem=f"Theory Question {question_number}",
        topic="",
        difficulty="MEDIUM",
        marks=5,
        source_type=Question.SourceType.MANUAL,
        source_reference="THEORY_MODE:TYPING",
        is_active=True,
    )
    CorrectAnswer.objects.get_or_create(question=question, defaults={"is_finalized": False})
    ExamQuestion.objects.create(
        exam=exam,
        question=question,
        sort_order=_next_exam_sort_order(exam),
        marks=question.marks,
    )


def _resequence_exam_rows(exam):
    objective_rows = list(
        exam.exam_questions.select_related("question")
        .filter(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order", "id")
    )
    theory_rows = list(
        exam.exam_questions.select_related("question")
        .exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order", "id")
    )
    ordered_rows = objective_rows + theory_rows
    changed_rows = [
        (index, row)
        for index, row in enumerate(ordered_rows, start=1)
        if row.sort_order != index
    ]
    if not changed_rows:
        return

    # Use temporary sort orders first so the unique (exam_id, sort_order)
    # constraint cannot fail while rows are being re-arranged in-place.
    temp_base = len(ordered_rows) + 1000
    now = timezone.now()
    for temp_index, (_, row) in enumerate(changed_rows, start=1):
        ExamQuestion.objects.filter(pk=row.pk).update(
            sort_order=temp_base + temp_index,
            updated_at=now,
        )
    for index, row in changed_rows:
        ExamQuestion.objects.filter(pk=row.pk).update(
            sort_order=index,
            updated_at=now,
        )
        row.sort_order = index


def _ensure_builder_rows(exam):
    config = _builder_config(exam)
    objective_target = config["objective_count"]
    theory_target = config["theory_count"]
    if exam.exam_type != CBTExamType.SIM and objective_target + theory_target == 0:
        if exam.exam_questions.exists():
            objective_target = exam.exam_questions.filter(
                question__question_type__in=OBJECTIVE_QUESTION_TYPES
            ).count()
            theory_target = exam.exam_questions.exclude(
                question__question_type__in=OBJECTIVE_QUESTION_TYPES
            ).count()
        else:
            objective_target = 1

    bank = _ensure_exam_question_bank(exam=exam)
    while (
        exam.exam_questions.filter(question__question_type__in=OBJECTIVE_QUESTION_TYPES).count()
        < objective_target
    ):
        _create_placeholder_objective_question(exam=exam, bank=bank)
    while (
        exam.exam_questions.exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES).count()
        < theory_target
    ):
        _create_placeholder_theory_question(exam=exam, bank=bank)
    _resequence_exam_rows(exam)
    _apply_builder_auto_marks(exam, config=config)


def _builder_rows_payload(exam):
    objective_rows = list(
        exam.exam_questions.select_related("question")
        .prefetch_related("question__options", "question__correct_answer__correct_options")
        .filter(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order")
    )
    theory_rows = list(
        exam.exam_questions.select_related("question")
        .prefetch_related("question__options", "question__correct_answer__correct_options")
        .exclude(question__question_type__in=OBJECTIVE_QUESTION_TYPES)
        .order_by("sort_order")
    )
    rows = []
    for index, row in enumerate(objective_rows, start=1):
        rows.append(
            {
                "row": row,
                "section": "OBJECTIVE",
                "section_label": f"Objective {index}",
            }
        )
    for index, row in enumerate(theory_rows, start=1):
        rows.append(
            {
                "row": row,
                "section": "THEORY",
                "section_label": f"Theory {index}",
            }
        )
    return rows

class CBTAuthoringAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _has_cbt_workspace_access(self.request.user, CBT_AUTHORING_ROLES)


class CBTDeanAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _has_cbt_workspace_access(self.request.user, CBT_DEAN_ROLES)


class CBTITAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return has_any_role(self.request.user, CBT_IT_ROLES)


class JambPortalRedirectView(RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        user = self.request.user
        if not user.is_authenticated:
            query = urlencode({"audience": "cbt", "next": self.request.path})
            return f"{reverse('accounts:login')}?{query}"
        if user.has_role(ROLE_STUDENT):
            query = urlencode({"exam_type": CBTExamType.FREE_TEST})
            return f"{reverse('cbt:student-exam-list')}?{query}"
        if user.has_role(ROLE_IT_MANAGER) or user.is_superuser:
            return reverse("cbt:it-jamb-admin")
        return reverse("cbt:home")


class CBTHomeRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        user = self.request.user
        if user.has_role(ROLE_STUDENT):
            return reverse("cbt:student-exam-list")
        if user.has_role(ROLE_IT_MANAGER):
            return reverse("cbt:it-activation-list")
        if user.has_role(ROLE_DEAN):
            return reverse("cbt:dean-review-list")
        return reverse("cbt:authoring-home")


class CBTAuthoringHomeView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/authoring_home.html"

    @staticmethod
    def _resolve_window(*, request, assignment_qs):
        setup_state = get_setup_state()
        return {
            "available_sessions": [setup_state.current_session] if setup_state.current_session_id else [],
            "available_terms": [setup_state.current_term] if setup_state.current_term_id else [],
            "selected_session": setup_state.current_session,
            "selected_term": setup_state.current_term,
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_assignments = authoring_assignment_queryset(
            self.request.user,
            include_all_periods=True,
        )
        window = self._resolve_window(request=self.request, assignment_qs=all_assignments)
        selected_session = window["selected_session"]
        selected_term = window["selected_term"]
        filtered_assignments = all_assignments
        if selected_session:
            filtered_assignments = filtered_assignments.filter(session=selected_session)
        if selected_term:
            filtered_assignments = filtered_assignments.filter(term=selected_term)

        exams = authoring_exam_queryset(
            self.request.user,
            include_all_periods=True,
            selected_session=selected_session,
            selected_term=selected_term,
        )
        exam_rows = list(exams[:20])
        for row in exam_rows:
            row.open_url = _exam_open_url(row)

        question_banks = authoring_question_bank_queryset(
            self.request.user,
            selected_session=selected_session,
            selected_term=selected_term,
        )
        questions = Question.objects.select_related("question_bank", "subject", "created_by").filter(
            created_by=self.request.user
        )
        imports = ExamDocumentImport.objects.filter(uploaded_by=self.request.user)
        if selected_session and selected_term:
            questions = questions.filter(question_bank__session=selected_session, question_bank__term=selected_term)
            imports = imports.filter(assignment__session=selected_session, assignment__term=selected_term)

        context["assignments"] = filtered_assignments[:24]
        context["question_banks"] = question_banks[:12]
        context["questions"] = questions.order_by("-updated_at")[:20]
        context["exams"] = exam_rows
        context["imports"] = imports.order_by("-created_at")[:10]
        context["show_simulation_registry_cta"] = has_any_role(
            self.request.user,
            {ROLE_IT_MANAGER},
        )
        context["has_exams"] = bool(exam_rows)
        context["available_sessions"] = window["available_sessions"]
        context["available_terms"] = window["available_terms"]
        context["selected_session"] = selected_session
        context["selected_term"] = selected_term
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        context["can_manage_all_cbt"] = can_manage_all_cbt(self.request.user)
        return context


class CBTQuestionBankCreateView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/question_bank_form.html"

    def _form(self, data=None):
        return QuestionBankCreateForm(actor=self.request.user, data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="creating question banks")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        question_bank = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "QUESTION_BANK_CREATED",
                "question_bank_id": str(question_bank.id),
            },
        )
        messages.success(request, "Question bank created.")
        return redirect("cbt:authoring-home")


class CBTQuestionCreateView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/question_form.html"

    def _form(self, data=None):
        return QuestionAuthoringForm(actor=self.request.user, data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        context["page_title"] = "Create Question"
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="creating CBT questions")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        question = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "QUESTION_CREATED",
                "question_id": str(question.id),
                "question_bank_id": str(question.question_bank_id),
            },
        )
        messages.success(request, "Question created.")
        return redirect("cbt:question-edit", question_id=question.id)


class CBTQuestionEditView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/question_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.question = get_object_or_404(
            Question.objects.select_related("question_bank", "subject", "created_by"),
            pk=kwargs["question_id"],
        )
        setup_state = get_setup_state()
        question_bank = self.question.question_bank
        if (
            not can_manage_all_cbt(request.user)
            and setup_state.current_session_id
            and setup_state.current_term_id
        ):
            if (
                question_bank is None
                or question_bank.session_id != setup_state.current_session_id
                or question_bank.term_id != setup_state.current_term_id
            ):
                messages.error(request, CBT_CURRENT_TERM_ONLY_MESSAGE)
                return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and self.question.created_by_id != request.user.id:
            messages.error(request, "You cannot edit this question.")
            return redirect("cbt:authoring-home")
        return super().dispatch(request, *args, **kwargs)

    def _form(self, data=None):
        return QuestionAuthoringForm(
            actor=self.request.user,
            question=self.question,
            data=data,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        context["question"] = self.question
        context["page_title"] = "Edit Question"
        return context

    def post(self, request, *args, **kwargs):
        if not can_manage_all_cbt(request.user):
            try:
                _require_cbt_window(user=request.user, action_label="editing CBT questions")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:question-edit", question_id=self.question.id)
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        question = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "QUESTION_UPDATED",
                "question_id": str(question.id),
            },
        )
        messages.success(request, "Question updated.")
        return redirect("cbt:question-edit", question_id=question.id)


class CBTExamCreateView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/exam_form.html"

    def _form(self, data=None):
        return ExamCreateForm(actor=self.request.user, data=data)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="creating CBT drafts")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        authoring_mode = form.cleaned_data.get("authoring_mode", ExamCreateForm.AUTHORING_MODE_SCRATCH)
        assignment = form.cleaned_data["assignment"]
        query = {
            "assignment_id": assignment.id,
            "title": form.cleaned_data["title"].strip(),
            "exam_type": form.cleaned_data["exam_type"],
            "duration_minutes": form.cleaned_data.get("duration_minutes") or 60,
            "max_attempts": form.cleaned_data.get("max_attempts") or 1,
        }
        ca_target = (form.cleaned_data.get("ca_target") or "").strip()
        if ca_target:
            query["ca_target"] = ca_target
        if form.cleaned_data.get("schedule_start"):
            query["schedule_start"] = form.cleaned_data["schedule_start"].isoformat()
        if form.cleaned_data.get("schedule_end"):
            query["schedule_end"] = form.cleaned_data["schedule_end"].isoformat()
        if authoring_mode == ExamCreateForm.AUTHORING_MODE_UPLOAD:
            messages.info(request, "Continue with upload or paste to generate the CBT draft.")
            return redirect(f"{reverse('cbt:upload-import')}?{urlencode(query)}")
        if authoring_mode == ExamCreateForm.AUTHORING_MODE_AI:
            messages.info(request, "Continue with AI draft generation.")
            return redirect(f"{reverse('cbt:ai-draft')}?{urlencode(query)}")

        exam = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_CREATED",
                "exam_id": str(exam.id),
                "status": exam.status,
            },
        )
        next_url = _exam_open_url(exam)
        if "simulations" in next_url:
            messages.success(
                request,
                "CBT setup saved. Continue by selecting simulation cards for this class subject.",
            )
            return redirect(next_url)
        messages.success(
            request,
            "CBT setup saved. Continue to question builder and save each question step-by-step.",
        )
        return redirect(next_url)


class CBTExamDeleteView(CBTAuthoringAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(
            Exam.objects.select_related("session", "term", "academic_class", "subject"),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        try:
            _require_cbt_window(user=request.user, action_label="deleting CBT drafts")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and exam.created_by_id != request.user.id:
            messages.error(request, "You cannot delete this CBT draft.")
            return redirect("cbt:authoring-home")
        if exam.status != CBTExamStatus.DRAFT:
            messages.error(request, "Only draft CBT entries can be deleted.")
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and not _exam_is_editable_for_actor(
            actor=request.user,
            exam=exam,
        ):
            messages.error(
                request,
                "Only draft CBT entries can be edited or deleted by teachers.",
            )
            return redirect("cbt:authoring-home")

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_DRAFT_DELETED",
                "exam_id": str(exam.id),
                "title": exam.title,
                "class_code": exam.academic_class.code,
                "subject": exam.subject.name,
                "session": exam.session.name,
                "term": exam.term.name,
            },
        )
        exam.delete()
        messages.success(request, "Draft CBT deleted.")
        return redirect("cbt:authoring-home")


class CBTExamBuilderView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/exam_builder.html"

    def dispatch(self, request, *args, **kwargs):
        close_expired_exams(exam_ids=[kwargs["exam_id"]])
        self.exam = get_object_or_404(
            Exam.objects.select_related(
                "created_by",
                "subject",
                "academic_class",
                "session",
                "term",
                "question_bank",
                "blueprint",
            ),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(self.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and self.exam.created_by_id != request.user.id:
            messages.error(request, "You cannot access this exam.")
            return redirect("cbt:authoring-home")
        config = _builder_config(self.exam)
        if self.exam.exam_type == CBTExamType.SIM or config.get("flow_type") == ExamCreateForm.FLOW_SIMULATION:
            return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)

        self.can_edit = can_manage_all_cbt(request.user) or _exam_is_editable_for_actor(
            actor=request.user,
            exam=self.exam,
        )
        if self.can_edit:
            _ensure_builder_rows(self.exam)
        self.builder_rows = _builder_rows_payload(self.exam)
        return super().dispatch(request, *args, **kwargs)

    def _builder_url(self, index):
        return f"{reverse('cbt:exam-builder', kwargs={'exam_id': self.exam.id})}?q={index}"

    def _current_index(self):
        raw = (self.request.POST.get("q") or self.request.GET.get("q") or "1").strip()
        try:
            value = int(raw)
        except ValueError:
            value = 1
        if not self.builder_rows:
            return 1
        return max(1, min(value, len(self.builder_rows)))

    @staticmethod
    def _objective_initial(question):
        option_map = {row.label: row.option_text for row in question.options.all()}
        correct_label = ""
        correct_labels = []
        answer = getattr(question, "correct_answer", None)
        if answer is not None:
            correct_options = list(answer.correct_options.order_by("sort_order", "label"))
            if correct_options:
                correct_label = correct_options[0].label
                correct_labels = [row.label for row in correct_options]
        objective_mode = (
            CBTQuestionType.MULTI_SELECT
            if question.question_type == CBTQuestionType.MULTI_SELECT
            else CBTQuestionType.OBJECTIVE
        )
        return {
            "option_a": option_map.get("A", ""),
            "option_b": option_map.get("B", ""),
            "option_c": option_map.get("C", ""),
            "option_d": option_map.get("D", ""),
            "option_e": option_map.get("E", ""),
            "correct_label": correct_label or "A",
            "correct_labels": correct_labels or ([correct_label] if correct_label else ["A"]),
            "objective_mode": objective_mode,
        }

    def _apply_stimulus_to_span(
        self,
        *,
        start_index,
        span,
        shared_key,
        caption,
        clear_image=False,
        clear_video=False,
    ):
        end_index = min(len(self.builder_rows), start_index + max(span, 1) - 1)
        for idx in range(start_index, end_index + 1):
            question = self.builder_rows[idx - 1]["row"].question
            updates = []
            if shared_key:
                question.shared_stimulus_key = shared_key
                updates.append("shared_stimulus_key")
            if caption:
                question.stimulus_caption = caption
                updates.append("stimulus_caption")
            if clear_image and question.stimulus_image:
                question.stimulus_image.delete(save=False)
                question.stimulus_image = None
                updates.append("stimulus_image")
            if clear_video and question.stimulus_video:
                question.stimulus_video.delete(save=False)
                question.stimulus_video = None
                updates.append("stimulus_video")
            if updates:
                updates.extend(["updated_at"])
                question.save(update_fields=sorted(set(updates)))

    def _save_bundle(self, *, bundle, payload, files, index):
        question = bundle["row"].question
        section = bundle["section"]
        stem = (payload.get("stem") or "").strip()
        if not stem:
            raise ValidationError("Question text is required.")
        marks = bundle["row"].marks

        question.rich_stem = stem
        plain_stem = strip_tags(stem).strip()
        question.stem = plain_stem or stem
        question.marks = marks
        question.is_active = True

        if section == "OBJECTIVE":
            objective_mode = (payload.get("objective_mode") or CBTQuestionType.OBJECTIVE).strip().upper()
            if objective_mode not in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
                objective_mode = CBTQuestionType.OBJECTIVE
            question.question_type = objective_mode
            option_map = {
                "A": (payload.get("option_a") or "").strip(),
                "B": (payload.get("option_b") or "").strip(),
                "C": (payload.get("option_c") or "").strip(),
                "D": (payload.get("option_d") or "").strip(),
                "E": (payload.get("option_e") or "").strip(),
            }
            provided_labels = [label for label, text in option_map.items() if text]
            if len(provided_labels) < 2:
                raise ValidationError("Provide at least two options for objective question.")
            sort_map = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
            for label, text in option_map.items():
                if text:
                    Option.objects.update_or_create(
                        question=question,
                        label=label,
                        defaults={"option_text": text, "sort_order": sort_map[label]},
                    )
                else:
                    Option.objects.filter(question=question, label=label).delete()
            correct_label = (payload.get("correct_label") or "").strip().upper() or provided_labels[0]
            correct_labels = [
                str(label).strip().upper()
                for label in payload.getlist("correct_labels")
                if str(label).strip().upper() in provided_labels
            ]
            if objective_mode == CBTQuestionType.OBJECTIVE:
                if correct_label not in provided_labels:
                    correct_label = provided_labels[0]
                final_labels = [correct_label]
            else:
                final_labels = correct_labels or [provided_labels[0]]
            answer, _ = CorrectAnswer.objects.get_or_create(question=question)
            answer.is_finalized = True
            answer.note = ""
            answer.save(update_fields=["is_finalized", "note", "updated_at"])
            answer.correct_options.set(question.options.filter(label__in=final_labels))
        else:
            theory_mode = (payload.get("theory_response_mode") or "PAPER").strip().upper()
            if theory_mode not in {ExamCreateForm.THEORY_RESPONSE_MODE_TYPING, ExamCreateForm.THEORY_RESPONSE_MODE_PAPER}:
                theory_mode = ExamCreateForm.THEORY_RESPONSE_MODE_PAPER
            selected_type = (payload.get("theory_question_type") or CBTQuestionType.SHORT_ANSWER).strip().upper()
            if selected_type not in {
                CBTQuestionType.SHORT_ANSWER,
                CBTQuestionType.LABELING,
                CBTQuestionType.ORDERING,
                CBTQuestionType.MATCHING,
            }:
                selected_type = CBTQuestionType.SHORT_ANSWER
            if theory_mode == ExamCreateForm.THEORY_RESPONSE_MODE_PAPER:
                selected_type = CBTQuestionType.SHORT_ANSWER
            question.question_type = selected_type
            question.source_reference = f"THEORY_MODE:{theory_mode}"
            question.options.all().delete()
            answer, _ = CorrectAnswer.objects.get_or_create(question=question)
            structured_answer_key = (payload.get("structured_answer_key") or "").strip()
            answer.note = structured_answer_key
            answer.is_finalized = bool(structured_answer_key) and selected_type in {
                CBTQuestionType.LABELING,
                CBTQuestionType.ORDERING,
                CBTQuestionType.MATCHING,
            }
            answer.save(update_fields=["is_finalized", "note", "updated_at"])
            answer.correct_options.clear()

        clear_image = payload.get("clear_stimulus_image") in {"1", "on", "true", "True"}
        clear_video = payload.get("clear_stimulus_video") in {"1", "on", "true", "True"}
        stimulus_caption = (payload.get("stimulus_caption") or "").strip()
        new_image = files.get("stimulus_image")
        new_video = files.get("stimulus_video")
        span_raw = (payload.get("apply_media_span") or "1").strip()
        try:
            apply_media_span = max(1, min(int(span_raw), 30))
        except (TypeError, ValueError):
            apply_media_span = 1

        if clear_image and question.stimulus_image:
            question.stimulus_image.delete(save=False)
            question.stimulus_image = None
        if clear_video and question.stimulus_video:
            question.stimulus_video.delete(save=False)
            question.stimulus_video = None
        if new_image is not None:
            question.stimulus_image = new_image
        if new_video is not None:
            question.stimulus_video = new_video
        if stimulus_caption:
            question.stimulus_caption = stimulus_caption
        shared_key = (question.shared_stimulus_key or "").strip()
        if apply_media_span > 1 and (new_image is not None or new_video is not None or stimulus_caption):
            shared_key = f"{self.exam.id}-stim-{uuid.uuid4().hex[:10]}"
            question.shared_stimulus_key = shared_key

        question.full_clean()
        question.save()
        if shared_key and apply_media_span > 1:
            self._apply_stimulus_to_span(
                start_index=index,
                span=apply_media_span,
                shared_key=shared_key,
                caption=stimulus_caption,
                clear_image=clear_image,
                clear_video=clear_video,
            )
        bundle["row"].marks = marks
        bundle["row"].save(update_fields=["marks", "updated_at"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        index = kwargs.get("index") or self._current_index()
        bundle = self.builder_rows[index - 1] if self.builder_rows else None
        question = bundle["row"].question if bundle else None
        objective_defaults = self._objective_initial(question) if bundle and bundle["section"] == "OBJECTIVE" else {}
        structured_answer_key = ""
        if question is not None:
            answer = getattr(question, "correct_answer", None)
            structured_answer_key = (getattr(answer, "note", "") or "").strip()
        current_stem = (getattr(question, "rich_stem", "") or getattr(question, "stem", "")) if question else ""

        posted = kwargs.get("draft_inputs")
        if posted:
            objective_defaults = {
                "option_a": posted.get("option_a", objective_defaults.get("option_a", "")),
                "option_b": posted.get("option_b", objective_defaults.get("option_b", "")),
                "option_c": posted.get("option_c", objective_defaults.get("option_c", "")),
                "option_d": posted.get("option_d", objective_defaults.get("option_d", "")),
                "option_e": posted.get("option_e", objective_defaults.get("option_e", "")),
                "correct_label": posted.get("correct_label", objective_defaults.get("correct_label", "A")),
                "correct_labels": posted.getlist("correct_labels") if hasattr(posted, "getlist") else objective_defaults.get("correct_labels", ["A"]),
                "objective_mode": posted.get("objective_mode", objective_defaults.get("objective_mode", CBTQuestionType.OBJECTIVE)),
            }
            current_stem = posted.get("stem", current_stem)
            structured_answer_key = posted.get("structured_answer_key", structured_answer_key)

        config = _builder_config(self.exam)
        context["exam"] = self.exam
        context["can_edit"] = self.can_edit
        context["builder_rows"] = self.builder_rows
        context["current_index"] = index
        context["current_bundle"] = bundle
        context["current_question"] = question
        context["current_stem"] = current_stem
        context["objective_defaults"] = objective_defaults
        context["theory_question_type"] = (
            posted.get("theory_question_type")
            if posted
            else (
                question.question_type
                if question and bundle and bundle["section"] == "THEORY"
                else CBTQuestionType.SHORT_ANSWER
            )
        )
        context["structured_answer_key"] = structured_answer_key
        context["theory_response_mode"] = (
            posted.get("theory_response_mode")
            if posted
                else (
                    (question.source_reference or "").replace("THEORY_MODE:", "")
                    if question and bundle and bundle["section"] == "THEORY"
                    else config.get("theory_response_mode", ExamCreateForm.THEORY_RESPONSE_MODE_PAPER)
                )
            )
        context["draft_inputs"] = posted or {}
        context["builder_config"] = config
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        context["can_manage_all_cbt"] = can_manage_all_cbt(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        if not self.builder_rows:
            messages.error(request, "No questions configured for this CBT.")
            return redirect("cbt:authoring-home")

        is_autosave = (
            request.POST.get("_autosave") == "1"
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        index = self._current_index()
        bundle = self.builder_rows[index - 1]
        action = (request.POST.get("action") or "save").strip().lower()

        if not self.can_edit:
            message = "Only draft CBT entries can be edited by teachers."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return redirect(self._builder_url(index))
        if not can_manage_all_cbt(request.user):
            try:
                _require_cbt_window(user=request.user, action_label="editing CBT exam questions")
            except ValidationError as exc:
                message = "; ".join(exc.messages)
                if is_autosave:
                    return JsonResponse({"ok": False, "error": message}, status=403)
                messages.error(request, message)
                return redirect(self._builder_url(index))

        if can_manage_all_cbt(request.user) and action in {"add_objective", "add_theory", "delete_current"}:
            bank = _ensure_exam_question_bank(exam=self.exam)
            if action == "add_objective":
                _create_placeholder_objective_question(exam=self.exam, bank=bank)
                _resequence_exam_rows(self.exam)
                _apply_builder_auto_marks(self.exam, config=_builder_config(self.exam))
                messages.success(request, "Objective question added. Edit it now.")
                return redirect(self._builder_url(len(_builder_rows_payload(self.exam))))
            if action == "add_theory":
                _create_placeholder_theory_question(exam=self.exam, bank=bank)
                _resequence_exam_rows(self.exam)
                _apply_builder_auto_marks(self.exam, config=_builder_config(self.exam))
                messages.success(request, "Theory question added. Edit it now.")
                return redirect(self._builder_url(len(_builder_rows_payload(self.exam))))
            if action == "delete_current":
                row = bundle["row"]
                question = row.question
                blueprint = getattr(self.exam, "blueprint", None)
                if blueprint is not None:
                    raw_section_config = blueprint.section_config or {}
                    section_config = (
                        dict(raw_section_config)
                        if isinstance(raw_section_config, dict)
                        else {}
                    )
                    count_key = (
                        "objective_count"
                        if bundle["section"] == "OBJECTIVE"
                        else "theory_count"
                    )
                    current_count = self.exam.exam_questions.filter(
                        question__question_type__in=OBJECTIVE_QUESTION_TYPES
                    ).count()
                    if count_key == "theory_count":
                        current_count = self.exam.exam_questions.exclude(
                            question__question_type__in=OBJECTIVE_QUESTION_TYPES
                        ).count()
                    section_config[count_key] = max(current_count - 1, 0)
                    section_config["question_count"] = max(
                        int(section_config.get("question_count") or self.exam.exam_questions.count()) - 1,
                        0,
                    )
                    blueprint.section_config = section_config
                    blueprint.save(update_fields=["section_config", "updated_at"])
                row.delete()
                if not ExamQuestion.objects.filter(question=question).exists():
                    question.delete()
                _resequence_exam_rows(self.exam)
                _apply_builder_auto_marks(self.exam, config=_builder_config(self.exam))
                next_index = min(index, max(len(_builder_rows_payload(self.exam)), 1))
                messages.success(request, "Question removed from this CBT.")
                return redirect(self._builder_url(next_index))

        try:
            self._save_bundle(
                bundle=bundle,
                payload=request.POST,
                files=request.FILES,
                index=index,
            )
        except ValidationError as exc:
            message = "; ".join(exc.messages)
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return self.render_to_response(
                self.get_context_data(index=index, draft_inputs=request.POST)
            )

        if is_autosave:
            return JsonResponse({"ok": True, "index": index})

        if action == "prev":
            return redirect(self._builder_url(max(index - 1, 1)))
        if action == "next":
            return redirect(self._builder_url(min(index + 1, len(self.builder_rows))))
        if action == "submit_to_dean":
            comment = (request.POST.get("dean_comment") or "").strip()
            try:
                if self.exam.is_free_test:
                    submit_exam_to_it_manager(
                        exam=self.exam,
                        actor=request.user,
                        comment=comment,
                    )
                else:
                    submit_exam_to_dean(
                        exam=self.exam,
                        actor=request.user,
                        comment=comment,
                    )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect(self._builder_url(index))
            if self.exam.is_free_test:
                messages.success(request, "Free Test submitted to IT Manager for publishing.")
            else:
                messages.success(request, "CBT submitted to Dean for review.")
            return redirect("cbt:authoring-home")
        if action == "finish":
            messages.success(request, "Question saved.")
            return redirect("cbt:authoring-home")

        messages.success(request, "Question saved.")
        return redirect(self._builder_url(index))


class CBTExamSimulationPickerView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/exam_simulation_picker.html"

    def dispatch(self, request, *args, **kwargs):
        close_expired_exams(exam_ids=[kwargs["exam_id"]])
        self.exam = get_object_or_404(
            Exam.objects.select_related(
                "created_by",
                "subject",
                "academic_class",
                "session",
                "term",
                "blueprint",
            ),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(self.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and self.exam.created_by_id != request.user.id:
            messages.error(request, "You cannot access this exam.")
            return redirect("cbt:authoring-home")

        config = _builder_config(self.exam)
        if self.exam.exam_type != CBTExamType.SIM and config.get("flow_type") != ExamCreateForm.FLOW_SIMULATION:
            return redirect("cbt:exam-builder", exam_id=self.exam.id)

        self.can_edit = _exam_is_editable_for_actor(actor=request.user, exam=self.exam)
        self.recommended_wrappers = list(recommended_simulation_queryset(self.exam.subject))
        for wrapper in self.recommended_wrappers:
            wrapper.preview_url = _simulation_preview_url(wrapper)
        selected_ids = list(
            self.exam.exam_simulations.values_list("simulation_wrapper_id", flat=True)
        )
        self.selected_ids = [int(value) for value in selected_ids]
        self.default_writeback_target = config.get("ca_target") or CBTWritebackTarget.CA3
        if self.exam.exam_type == CBTExamType.EXAM:
            self.default_writeback_target = CBTWritebackTarget.OBJECTIVE
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_ids = kwargs.get("selected_ids", self.selected_ids)
        context["exam"] = self.exam
        context["can_edit"] = self.can_edit
        context["selected_ids"] = set(int(value) for value in selected_ids)
        context["wrappers"] = self.recommended_wrappers
        context["writeback_target"] = kwargs.get("writeback_target", self.default_writeback_target)
        context["required_for_submission"] = kwargs.get("required_for_submission", True)
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "save").strip().lower()
        selected_ids = [value for value in request.POST.getlist("simulation_ids") if str(value).strip()]
        writeback_target = (request.POST.get("writeback_target") or self.default_writeback_target).strip()
        required_for_submission = (
            bool(request.POST.get("required_for_submission"))
            if "required_for_submission" in request.POST
            else True
        )

        if not self.can_edit:
            messages.error(
                request,
                "Only draft CBT entries can be edited by teachers.",
            )
            return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)
        try:
            _require_cbt_window(user=request.user, action_label="updating CBT simulation selections")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)

        allowed_targets = {
            CBTWritebackTarget.CA1,
            CBTWritebackTarget.CA2,
            CBTWritebackTarget.CA3,
            CBTWritebackTarget.CA4,
            CBTWritebackTarget.OBJECTIVE,
            CBTWritebackTarget.THEORY,
            CBTWritebackTarget.NONE,
        }
        if writeback_target not in allowed_targets:
            writeback_target = self.default_writeback_target

        selected_wrappers = []
        for raw_id in selected_ids:
            try:
                wrapper_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            wrapper = next((row for row in self.recommended_wrappers if row.id == wrapper_id), None)
            if wrapper is not None:
                selected_wrappers.append(wrapper)

        if action == "submit_to_dean" and not selected_wrappers:
            messages.error(request, "Select at least one simulation before submitting to Dean.")
            return self.render_to_response(
                self.get_context_data(
                    selected_ids=selected_ids,
                    writeback_target=writeback_target,
                    required_for_submission=required_for_submission,
                )
            )

        with transaction.atomic():
            self.exam.exam_simulations.all().delete()
            for index, wrapper in enumerate(selected_wrappers, start=1):
                ExamSimulation.objects.create(
                    exam=self.exam,
                    simulation_wrapper=wrapper,
                    sort_order=index,
                    writeback_target=writeback_target,
                    is_required=required_for_submission,
                )

        if action == "submit_to_dean":
            comment = (request.POST.get("dean_comment") or "").strip()
            try:
                submit_exam_to_dean(exam=self.exam, actor=request.user, comment=comment)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)
            messages.success(
                request,
                "Simulation CBT submitted for review. IT Manager can post it after Dean approval.",
            )
            return redirect("cbt:authoring-home")

        messages.success(request, "Simulation selection saved.")
        return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)


class CBTSimulationLibraryAPIView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        subject = None
        subject_id = (request.GET.get("subject_id") or "").strip()
        if subject_id.isdigit():
            subject = Subject.objects.filter(id=int(subject_id)).first()

        rows = recommended_simulation_queryset(subject)
        q = (request.GET.get("q") or "").strip()
        if q:
            rows = rows.filter(
                Q(tool_name__icontains=q)
                | Q(description__icontains=q)
                | Q(tool_type__icontains=q)
            )

        provider = (request.GET.get("provider") or "").strip()
        if provider:
            provider_upper = provider.upper()
            provider_map = dict(SimulationWrapper._meta.get_field("source_provider").choices)
            if provider_upper in provider_map:
                rows = rows.filter(source_provider=provider_upper)
            else:
                rows = rows.filter(source_provider__iexact=provider)

        category = (request.GET.get("category") or "").strip()
        if category:
            category_upper = category.upper()
            category_map = dict(SimulationWrapper._meta.get_field("tool_category").choices)
            if category_upper in category_map:
                rows = rows.filter(tool_category=category_upper)
            else:
                rows = rows.filter(tool_category__iexact=category)

        payload = []
        for wrapper in rows:
            payload.append(
                {
                    "id": wrapper.id,
                    "title": wrapper.tool_name,
                    "category": wrapper.get_tool_category_display(),
                    "provider": wrapper.get_source_provider_display(),
                    "score_mode": wrapper.get_score_mode_display(),
                    "preview_url": _simulation_preview_url(wrapper),
                }
            )
        return JsonResponse({"count": len(payload), "results": payload})


class CBTSimulationLaunchView(LoginRequiredMixin, TemplateView):
    template_name = "cbt/simulation_launch.html"

    def dispatch(self, request, *args, **kwargs):
        self.wrapper = get_object_or_404(SimulationWrapper, pk=kwargs["wrapper_id"], is_active=True)
        if (
            self.wrapper.status != CBTSimulationWrapperStatus.APPROVED
            and not can_manage_all_cbt(request.user)
        ):
            messages.error(request, "Simulation is not available for launch yet.")
            return redirect("cbt:authoring-home")
        self.simulation_url = _simulation_preview_url(self.wrapper)
        if not self.simulation_url:
            messages.error(request, "Simulation launch file is not configured.")
            return redirect("cbt:authoring-home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wrapper"] = self.wrapper
        context["simulation_url"] = self.simulation_url
        return context


class CBTExamDetailView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/exam_detail.html"

    def dispatch(self, request, *args, **kwargs):
        close_expired_exams(exam_ids=[kwargs["exam_id"]])
        self.exam = get_object_or_404(
            Exam.objects.select_related(
                "created_by",
                "subject",
                "academic_class",
                "session",
                "term",
                "question_bank",
                "blueprint",
            ),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(self.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and self.exam.created_by_id != request.user.id:
            messages.error(request, "You cannot access this exam.")
            return redirect("cbt:authoring-home")
        if self.exam.status == CBTExamStatus.DRAFT:
            if self.exam.exam_type == CBTExamType.SIM:
                return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)
            return redirect("cbt:exam-builder", exam_id=self.exam.id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section_config = {}
        blueprint = getattr(self.exam, "blueprint", None)
        if blueprint and isinstance(blueprint.section_config, dict):
            section_config = blueprint.section_config
        show_simulation_section = (
            self.exam.exam_type == CBTExamType.SIM
            or section_config.get("flow_type") == ExamCreateForm.FLOW_SIMULATION
        )
        context["exam"] = self.exam
        context["exam_blueprint"] = blueprint
        context["show_simulation_section"] = show_simulation_section
        context["exam_questions"] = (
            self.exam.exam_questions.select_related("question")
            .prefetch_related(
                "question__options",
                "question__correct_answer__correct_options",
            )
            .order_by("sort_order")
        )
        context["exam_simulations"] = self.exam.exam_simulations.select_related(
            "simulation_wrapper"
        ).order_by("sort_order")
        context["review_actions"] = self.exam.review_actions.select_related("actor").order_by("created_at")
        context["timer_is_paused"] = bool(self.exam.timer_is_paused)
        context["timer_pause_reason"] = self.exam.timer_pause_reason
        context["active_attempt_count"] = self.exam.attempts.filter(status=CBTAttemptStatus.IN_PROGRESS).count()
        return context


class CBTExamQuestionAttachView(CBTAuthoringAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs["exam_id"])
        if not cbt_exam_is_current(exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        try:
            _require_cbt_window(user=request.user, action_label="attaching CBT questions")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not can_manage_all_cbt(request.user) and exam.created_by_id != request.user.id:
            messages.error(request, "You cannot update this exam.")
            return redirect("cbt:authoring-home")
        if exam.status != CBTExamStatus.DRAFT:
            messages.error(request, "Only draft exams can be edited.")
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not _exam_is_editable_for_actor(actor=request.user, exam=exam):
            messages.error(
                request,
                "Only draft CBT entries can be edited by teachers.",
            )
            return redirect("cbt:exam-detail", exam_id=exam.id)
        post_data = request.POST.copy()
        # Backward-compat for older payloads that post `questions` instead of `question_ids`.
        if not post_data.getlist("question_ids"):
            legacy_question_ids = post_data.getlist("questions")
            if legacy_question_ids:
                post_data.setlist("question_ids", legacy_question_ids)
        form = ExamAttachQuestionsForm(actor=request.user, exam=exam, data=post_data)
        if not form.is_valid():
            for error in form.non_field_errors():
                messages.error(request, error)
            return redirect("cbt:exam-detail", exam_id=exam.id)
        selected_count = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_QUESTIONS_ATTACHED",
                "exam_id": str(exam.id),
                "question_count": selected_count,
            },
        )
        messages.success(request, "Exam questions updated.")
        return redirect("cbt:exam-detail", exam_id=exam.id)


class CBTExamSimulationAttachView(CBTAuthoringAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs["exam_id"])
        if not cbt_exam_is_current(exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        try:
            _require_cbt_window(user=request.user, action_label="attaching CBT simulations")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not can_manage_all_cbt(request.user) and exam.created_by_id != request.user.id:
            messages.error(request, "You cannot update this exam.")
            return redirect("cbt:authoring-home")
        if exam.status != CBTExamStatus.DRAFT:
            messages.error(request, "Only draft exams can be edited.")
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not _exam_is_editable_for_actor(actor=request.user, exam=exam):
            messages.error(
                request,
                "Only draft CBT entries can be edited by teachers.",
            )
            return redirect("cbt:exam-detail", exam_id=exam.id)
        form = ExamAttachSimulationsForm(exam=exam, data=request.POST)
        if not form.is_valid():
            for error in form.non_field_errors():
                messages.error(request, error)
            return redirect("cbt:exam-detail", exam_id=exam.id)
        selected_count = form.save()
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_SIMULATIONS_ATTACHED",
                "exam_id": str(exam.id),
                "simulation_count": selected_count,
            },
        )
        messages.success(request, "Exam simulations updated.")
        return redirect("cbt:exam-detail", exam_id=exam.id)


class CBTExamSubmitToDeanView(CBTAuthoringAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs["exam_id"])
        if not cbt_exam_is_current(exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:authoring-home")
        try:
            _require_cbt_window(user=request.user, action_label="submitting CBT exams to dean")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not can_manage_all_cbt(request.user) and exam.created_by_id != request.user.id:
            messages.error(request, "You cannot submit this exam.")
            return redirect("cbt:authoring-home")
        if not _exam_is_editable_for_actor(actor=request.user, exam=exam):
            messages.error(
                request,
                "Only draft CBT entries can be submitted by teachers.",
            )
            return redirect("cbt:exam-detail", exam_id=exam.id)
        form = ExamSubmitToDeanForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Invalid submission payload.")
            return redirect("cbt:exam-detail", exam_id=exam.id)
        try:
            submit_exam_to_dean(
                exam=exam,
                actor=request.user,
                comment=form.cleaned_data.get("comment", ""),
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:exam-detail", exam_id=exam.id)

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_SUBMITTED_TO_DEAN",
                "exam_id": str(exam.id),
                "status": exam.status,
            },
        )
        messages.success(request, "Exam submitted to Dean for vetting.")
        return redirect("cbt:exam-detail", exam_id=exam.id)


class CBTUploadImportView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/upload_import.html"

    @staticmethod
    def _exam_type_for_form(form):
        if form.is_bound:
            return (form.data.get("exam_type") or "").strip()
        return str(form.initial.get("exam_type") or "").strip()

    def _show_ca_target_field(self, form):
        return self._exam_type_for_form(form) in {
            CBTExamType.CA,
            CBTExamType.PRACTICAL,
        }

    def _resolved_prefill_assignment(self):
        assignment_id = (self.request.GET.get("assignment_id") or "").strip()
        if not assignment_id.isdigit():
            return None
        return authoring_assignment_queryset(self.request.user).filter(id=int(assignment_id)).first()

    def _initial(self):
        title = (self.request.GET.get("title") or "").strip()
        exam_type = (self.request.GET.get("exam_type") or "").strip()
        if exam_type == CBTExamType.SIM:
            exam_type = CBTExamType.PRACTICAL
        ca_target = (self.request.GET.get("ca_target") or "").strip()
        flow_type = (self.request.GET.get("flow_type") or "").strip()
        duration_minutes = (self.request.GET.get("duration_minutes") or "").strip()
        max_attempts = (self.request.GET.get("max_attempts") or "").strip()
        schedule_start = (self.request.GET.get("schedule_start") or "").strip()
        schedule_end = (self.request.GET.get("schedule_end") or "").strip()
        initial = {}
        prefill_assignment = self._resolved_prefill_assignment()
        if prefill_assignment is not None:
            initial["assignment"] = prefill_assignment.id
        if title:
            initial["title"] = title
        if exam_type:
            initial["exam_type"] = exam_type
        if ca_target:
            initial["ca_target"] = ca_target
        if flow_type:
            initial["flow_type"] = flow_type
        if duration_minutes.isdigit():
            initial["duration_minutes"] = int(duration_minutes)
        if max_attempts.isdigit():
            initial["max_attempts"] = int(max_attempts)
        if schedule_start:
            initial["schedule_start"] = schedule_start
        if schedule_end:
            initial["schedule_end"] = schedule_end
        return initial

    def _form(self, data=None, files=None):
        return ExamUploadImportForm(
            actor=self.request.user,
            data=data,
            files=files,
            initial=self._initial() if data is None else None,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        setup_prefill = self._initial()
        assignment_obj = self._resolved_prefill_assignment()
        form = kwargs.get("form") or self._form()
        context["form"] = form
        context["setup_prefill"] = setup_prefill
        context["prefill_assignment"] = assignment_obj
        context["show_ca_target_field"] = self._show_ca_target_field(form)
        context["imports"] = ExamDocumentImport.objects.filter(
            uploaded_by=self.request.user
        ).select_related("exam").order_by("-created_at")[:20]
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="importing CBT drafts")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        post_data = request.POST.copy()
        setup_prefill = self._initial()
        if setup_prefill.get("assignment") and not post_data.get("assignment"):
            post_data["assignment"] = str(setup_prefill["assignment"])
        if setup_prefill.get("title") and not post_data.get("title"):
            post_data["title"] = setup_prefill["title"]
        if setup_prefill.get("exam_type") and not post_data.get("exam_type"):
            post_data["exam_type"] = setup_prefill["exam_type"]
        if setup_prefill.get("ca_target") and not post_data.get("ca_target"):
            post_data["ca_target"] = setup_prefill["ca_target"]

        form = self._form(post_data, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        source_file = form.cleaned_data.get("source_file")
        if source_file is None:
            pasted_text = (form.cleaned_data.get("pasted_text") or "").strip()
            source_file = SimpleUploadedFile(
                "pasted_questions.txt",
                pasted_text.encode("utf-8"),
                content_type="text/plain",
            )
        try:
            exam, import_row, question_count = build_exam_from_uploaded_document(
                actor=request.user,
                assignment=form.cleaned_data["assignment"],
                title=form.cleaned_data["title"].strip(),
                exam_type=form.cleaned_data["exam_type"],
                flow_type=form.cleaned_data.get("flow_type", ""),
                ca_target=form.cleaned_data.get("ca_target", ""),
                source_file=source_file,
            )
        except ValidationError as exc:
            error_text = "; ".join(exc.messages)
            form.add_error(None, error_text)
            messages.error(request, error_text)
            return self.render_to_response(self.get_context_data(form=form))
        except Exception:
            logger.exception("CBT upload import failed")
            form.add_error(
                None,
                "Could not create draft from upload. Check file format/content and try again.",
            )
            messages.error(
                request,
                "Could not create draft from upload. Check file format/content and try again.",
            )
            return self.render_to_response(self.get_context_data(form=form))

        duration_minutes = (
            form.cleaned_data.get("duration_minutes")
            or setup_prefill.get("duration_minutes")
        )
        max_attempts = setup_prefill.get("max_attempts")
        schedule_start = (
            form.cleaned_data.get("schedule_start")
            or setup_prefill.get("schedule_start")
        )
        schedule_end = (
            form.cleaned_data.get("schedule_end")
            or setup_prefill.get("schedule_end")
        )
        blueprint = getattr(exam, "blueprint", None) or ExamBlueprint.objects.create(exam=exam)
        updated_blueprint_fields = []
        if duration_minutes:
            blueprint.duration_minutes = duration_minutes
            updated_blueprint_fields.append("duration_minutes")
        if max_attempts:
            blueprint.max_attempts = max_attempts
            updated_blueprint_fields.append("max_attempts")
        if updated_blueprint_fields:
            updated_blueprint_fields.append("updated_at")
            blueprint.save(update_fields=updated_blueprint_fields)

        updated_exam_fields = []
        if schedule_start:
            if isinstance(schedule_start, str):
                try:
                    parsed = datetime.fromisoformat(schedule_start)
                    exam.schedule_start = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
                except ValueError:
                    exam.schedule_start = None
            else:
                exam.schedule_start = schedule_start
            updated_exam_fields.append("schedule_start")
        if schedule_end:
            if isinstance(schedule_end, str):
                try:
                    parsed = datetime.fromisoformat(schedule_end)
                    exam.schedule_end = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
                except ValueError:
                    exam.schedule_end = None
            else:
                exam.schedule_end = schedule_end
            updated_exam_fields.append("schedule_end")
        if updated_exam_fields:
            updated_exam_fields.append("updated_at")
            exam.save(update_fields=updated_exam_fields)

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_IMPORTED_FROM_DOCUMENT",
                "exam_id": str(exam.id),
                "import_id": str(import_row.id),
                "question_count": question_count,
            },
        )
        messages.success(
            request,
            f"Upload parsed successfully. Draft exam created with {question_count} questions.",
        )
        flagged_blocks = int((import_row.parse_summary or {}).get("flagged_block_count") or 0)
        if flagged_blocks > 0:
            messages.warning(
                request,
                f"{flagged_blocks} block(s) needed AI repair. Review all questions before submitting to Dean.",
            )
        return redirect(_exam_open_url(exam))


class CBTAIExamDraftView(CBTAuthoringAccessMixin, TemplateView):
    template_name = "cbt/ai_draft_form.html"

    def _initial(self):
        assignment_id = (self.request.GET.get("assignment_id") or "").strip()
        title = (self.request.GET.get("title") or "").strip()
        exam_type = (self.request.GET.get("exam_type") or "").strip()
        if exam_type == CBTExamType.SIM:
            exam_type = CBTExamType.PRACTICAL
        ca_target = (self.request.GET.get("ca_target") or "").strip()
        flow_type = (self.request.GET.get("flow_type") or "").strip()
        initial = {}
        if assignment_id.isdigit():
            initial["assignment"] = int(assignment_id)
        if title:
            initial["title"] = title
        if exam_type:
            initial["exam_type"] = exam_type
        if ca_target:
            initial["ca_target"] = ca_target
        if flow_type:
            initial["flow_type"] = flow_type
        return initial

    def _form(self, data=None, files=None):
        return AIExamDraftForm(
            actor=self.request.user,
            data=data,
            files=files,
            initial=self._initial() if data is None else None,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="generating AI CBT drafts")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:authoring-home")
        form = self._form(request.POST, request.FILES)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        try:
            exam, question_count = build_exam_with_ai_draft(
                actor=request.user,
                assignment=form.cleaned_data["assignment"],
                title=form.cleaned_data["title"].strip(),
                topic=form.cleaned_data["topic"].strip(),
                question_count=form.cleaned_data["question_count"],
                exam_type=form.cleaned_data["exam_type"],
                flow_type=form.cleaned_data.get("flow_type", ""),
                ca_target=form.cleaned_data.get("ca_target", ""),
                difficulty=form.cleaned_data["difficulty"],
                lesson_note_text=form.cleaned_data.get("lesson_note_text", ""),
                lesson_note_file=form.cleaned_data.get("lesson_note_file"),
            )
        except ValidationError as exc:
            error_text = "; ".join(exc.messages)
            form.add_error(None, error_text)
            messages.error(request, error_text)
            return self.render_to_response(self.get_context_data(form=form))
        except Exception:
            logger.exception("AI draft generation failed")
            form.add_error(
                None,
                "Could not generate AI draft right now. Check inputs and try again.",
            )
            messages.error(
                request,
                "Could not generate AI draft right now. Check inputs and try again.",
            )
            return self.render_to_response(self.get_context_data(form=form))
        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_AI_DRAFT_GENERATED",
                "exam_id": str(exam.id),
                "question_count": question_count,
                "topic": form.cleaned_data["topic"].strip(),
            },
        )
        messages.success(
            request,
            f"AI draft generated {question_count} objective questions. Review and edit before submitting to Dean.",
        )
        return redirect(_exam_open_url(exam))


class CBTExamSimulationToolCreateView(CBTITAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(Exam, pk=kwargs["exam_id"])
        if not cbt_exam_is_current(exam):
            messages.error(request, CBT_CURRENT_TERM_ONLY_MESSAGE)
            return redirect("cbt:authoring-home")
        if not can_manage_all_cbt(request.user) and exam.created_by_id != request.user.id:
            messages.error(request, "You cannot update this exam.")
            return redirect("cbt:authoring-home")
        if exam.status != CBTExamStatus.DRAFT:
            messages.error(request, "Only draft exams can be edited.")
            return redirect("cbt:exam-detail", exam_id=exam.id)
        if not _exam_is_editable_for_actor(actor=request.user, exam=exam):
            messages.error(
                request,
                "Only draft CBT entries can be edited by teachers.",
            )
            return redirect("cbt:exam-detail", exam_id=exam.id)

        form = SimulationWrapperCreateForm(request.POST, request.FILES)
        if not form.is_valid():
            for error in form.non_field_errors():
                messages.error(request, error)
            return redirect("cbt:exam-detail", exam_id=exam.id)

        wrapper = form.save(actor=request.user)
        auto_submit = bool(request.POST.get("auto_submit_to_dean"))
        comment = (request.POST.get("dean_comment") or "").strip()
        if auto_submit:
            try:
                submit_simulation_to_dean(
                    wrapper=wrapper,
                    actor=request.user,
                    comment=comment,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:exam-detail", exam_id=exam.id)

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": "EXAM_SIMULATION_TOOL_CREATED",
                "exam_id": str(exam.id),
                "wrapper_id": str(wrapper.id),
                "wrapper_status": wrapper.status,
            },
        )
        if auto_submit:
            messages.success(
                request,
                "Simulation tool created and submitted to Dean. It becomes attachable after approval.",
            )
        else:
            messages.success(
                request,
                "Simulation tool created in draft. Submit it to Dean when ready.",
            )
        return redirect("cbt:exam-detail", exam_id=exam.id)


class CBTITSimulationRegistryView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_simulation_registry.html"

    def _form(self, data=None, files=None):
        return SimulationWrapperCreateForm(data=data, files=files)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or self._form()
        context["wrappers"] = simulation_registry_queryset()
        context["submit_form"] = SimulationSubmitToDeanForm()
        context["catalog"] = simulation_catalog_grouped_labels()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "seed_free_library":
            result = seed_curated_simulation_library(actor=request.user)
            log_cbt_config_edit(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SIMULATION_LIBRARY_SEEDED",
                    "created_count": result["created"],
                    "updated_count": result["updated"],
                    "skipped_count": result["skipped"],
                    "catalog_total": result["total_seed_rows"],
                },
            )
            messages.success(
                request,
                (
                    "Free simulation library synced. "
                    f"Created {result['created']}, updated {result['updated']}, "
                    f"unchanged {result['skipped']}."
                ),
            )
            return redirect("cbt:it-simulation-registry")

        if action == "create":
            form = self._form(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(form=form))
            wrapper = form.save(actor=request.user)
            log_cbt_config_edit(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SIMULATION_WRAPPER_CREATED",
                    "wrapper_id": str(wrapper.id),
                    "tool_name": wrapper.tool_name,
                    "score_mode": wrapper.score_mode,
                },
            )
            messages.success(request, "Simulation wrapper saved.")
            return redirect("cbt:it-simulation-registry")

        if action == "submit_to_dean":
            wrapper_id = request.POST.get("wrapper_id")
            wrapper = get_object_or_404(SimulationWrapper, pk=wrapper_id)
            form = SimulationSubmitToDeanForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Invalid submission payload.")
                return redirect("cbt:it-simulation-registry")
            try:
                submit_simulation_to_dean(
                    wrapper=wrapper,
                    actor=request.user,
                    comment=form.cleaned_data.get("comment", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-simulation-registry")
            log_cbt_config_edit(
                actor=request.user,
                request=request,
                metadata={
                    "action": "SIMULATION_WRAPPER_SUBMITTED_TO_DEAN",
                    "wrapper_id": str(wrapper.id),
                    "status": wrapper.status,
                },
            )
            messages.success(request, "Simulation submitted to Dean for review.")
            return redirect("cbt:it-simulation-registry")

        messages.error(request, "Invalid simulation registry action.")
        return redirect("cbt:it-simulation-registry")


class CBTITJambAdminView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_jamb_admin.html"
    live_cache_key = "cbt:it-jamb-live-payload"

    def _parse_local_datetime(self, value):
        value = (value or "").strip()
        if not value:
            return None
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        return timezone.make_aware(parsed, timezone.get_current_timezone())

    def _download_pdf(self):
        try:
            from apps.pdfs.services import render_pdf_bytes, school_logo_data_uri
        except Exception as exc:
            raise RuntimeError("PDF service is not available.") from exc
        rows = [row for row in _jamb_candidate_rows() if row["submitted"]]
        top_rows = rows[:3]
        pdf_bytes = render_pdf_bytes(
            template_name="cbt/it_jamb_performance_pdf.html",
            context={
                "rows": rows,
                "top_rows": top_rows,
                "generated_at": timezone.now(),
                "school_logo_data_uri": school_logo_data_uri(),
            },
        )
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="NDGA-JAMB-Practice-Performance.pdf"'
        return response

    def _build_live_payload(self, rows):
        submitted = [row for row in rows if row["submitted"]]
        return {
            "ok": True,
            "summary": {
                "candidates": len(rows),
                "writing": len([row for row in rows if row["writing"]]),
                "submitted": len(submitted),
                "locked": len([row for row in rows if row["locked"]]),
                "not_started": len([row for row in rows if row["attempt"] is None]),
            },
            "top": [
                {
                    "name": row["name"],
                    "admission_no": row["admission_no"],
                    "score": str(row["total_score"]),
                }
                for row in submitted[:3]
            ],
            "rows": [
                {
                    "exam_id": row["exam"].id,
                    "name": row["name"],
                    "admission_no": row["admission_no"],
                    "sections": row["sections"],
                    "status": (
                        "Locked"
                        if row["locked"]
                        else "Writing"
                        if row["writing"]
                        else row["status"]
                    ),
                    "writing": row["writing"],
                    "locked": row["locked"],
                    "submitted": row["submitted"],
                    "answered": row["answered_count"],
                    "questions": row["question_count"],
                    "progress": row["progress_percent"],
                    "score": str(row["total_score"]),
                }
                for row in rows
            ],
        }

    def _live_payload(self):
        cached = cache.get(self.live_cache_key)
        if isinstance(cached, dict):
            return cached
        payload = self._build_live_payload(_jamb_candidate_rows())
        cache.set(self.live_cache_key, payload, timeout=8)
        return payload

    def get(self, request, *args, **kwargs):
        if request.GET.get("download") == "pdf":
            return self._download_pdf()
        if request.GET.get("format") == "json":
            return JsonResponse(self._live_payload())
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        exams = list(_jamb_exams_queryset())
        rows = _jamb_candidate_rows()
        cache.set(
            self.live_cache_key,
            self._build_live_payload(rows),
            timeout=8,
        )
        submitted_count = len([row for row in rows if row["submitted"]])
        locked_count = len([row for row in rows if row["locked"]])
        not_started_count = len([row for row in rows if row["attempt"] is None])
        in_progress_count = len(
            [row for row in rows if row["attempt"] and not row["submitted"]]
        )
        first_exam = exams[0] if exams else None
        first_sections = (
            (first_exam.blueprint.section_config or {}).get("sections") or {}
            if first_exam and getattr(first_exam, "blueprint", None)
            else {}
        )
        first_other_count = next(
            (
                int(value)
                for key, value in first_sections.items()
                if key != "English"
            ),
            40,
        )
        bank_audit = _jamb_bank_audit()
        context.update(
            {
                "jamb_exams": exams,
                "candidate_rows": rows,
                "top_rows": [row for row in rows if row["submitted"]][:3],
                "bank_audit": bank_audit,
                "submitted_count": submitted_count,
                "locked_count": locked_count,
                "not_started_count": not_started_count,
                "in_progress_count": in_progress_count,
                "attempt_count": ExamAttempt.objects.filter(exam__in=exams).count() if exams else 0,
                "first_exam": first_exam,
                "default_start_value": timezone.localtime(first_exam.schedule_start).strftime("%Y-%m-%dT%H:%M") if first_exam and first_exam.schedule_start else "",
                "default_end_value": timezone.localtime(first_exam.schedule_end).strftime("%Y-%m-%dT%H:%M") if first_exam and first_exam.schedule_end else "",
                "default_duration_minutes": (
                    first_exam.blueprint.duration_minutes
                    if first_exam and getattr(first_exam, "blueprint", None)
                    else 100
                ),
                "default_english_count": int(first_sections.get("English") or 60),
                "default_other_count": first_other_count,
                "jamb_subject_options": [
                    label
                    for label in JAMB_SECTION_ORDER
                    if label != "English"
                    and bank_audit["subject_counts"].get(label, 0) >= 40
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        cache.delete(self.live_cache_key)
        exams = list(_jamb_exams_queryset())
        if action == "update_choices":
            try:
                exam_id = int(request.POST.get("exam_id") or 0)
            except (TypeError, ValueError):
                exam_id = 0
            exam = next((row for row in exams if row.id == exam_id), None)
            selected = [
                value.strip()
                for value in request.POST.getlist("choices")
                if value.strip()
            ]
            choices = ["English", *list(dict.fromkeys(selected))]
            if exam is None or len(choices) != 4:
                messages.error(request, "Choose exactly three subjects in addition to English.")
                return redirect("cbt:it-jamb-admin")
            try:
                from scripts.setup_ss2_jamb_live_20260701 import rebuild_exam_questions

                if exam.attempts.exists():
                    raise RuntimeError(
                        "Reset this candidate's previous attempt before changing JAMB subjects."
                    )
                section_counts = (
                    (exam.blueprint.section_config or {}).get("sections") or {}
                )
                rebuild_exam_questions(
                    exam,
                    choices,
                    english_count=int(section_counts.get("English") or 60),
                    other_count=next(
                        (
                            int(value)
                            for key, value in section_counts.items()
                            if key != "English"
                        ),
                        40,
                    ),
                )
            except (RuntimeError, ValidationError) as exc:
                messages.error(request, str(exc))
                return redirect("cbt:it-jamb-admin")
            messages.success(request, f"Updated JAMB subjects for {exam.title}.")
            return redirect("cbt:it-jamb-admin")
        if action == "configure":
            try:
                duration = int(request.POST.get("duration_minutes") or 100)
                english_count = int(request.POST.get("english_count") or 60)
                other_count = int(request.POST.get("other_count") or 40)
                if not 10 <= duration <= 240:
                    raise ValueError
            except (TypeError, ValueError):
                messages.error(
                    request,
                    "Use 10–240 minutes, 10–60 English questions, and 10–40 questions for each other subject.",
                )
                return redirect("cbt:it-jamb-admin")
            if ExamAttempt.objects.filter(exam__in=exams).exists():
                messages.error(
                    request,
                    "Question counts cannot change while JAMB attempts exist. Download results, then reset attempts first.",
                )
                return redirect("cbt:it-jamb-admin")
            try:
                from scripts.setup_ss2_jamb_live_20260701 import rebuild_exam_questions

                with transaction.atomic():
                    for exam in exams:
                        choices = list(
                            ((exam.blueprint.section_config or {}).get("sections") or {}).keys()
                        )
                        rebuild_exam_questions(
                            exam,
                            choices,
                            english_count=english_count,
                            other_count=other_count,
                        )
                        exam.blueprint.duration_minutes = duration
                        exam.blueprint.save(
                            update_fields=["duration_minutes", "updated_at"]
                        )
            except (RuntimeError, ValidationError) as exc:
                messages.error(request, str(exc))
                return redirect("cbt:it-jamb-admin")
            messages.success(
                request,
                f"JAMB setup updated: {duration} minutes, {english_count} English and {other_count} questions per other subject.",
            )
            return redirect("cbt:it-jamb-admin")
        if action == "open":
            try:
                start = self._parse_local_datetime(request.POST.get("start_at"))
                end = self._parse_local_datetime(request.POST.get("end_at"))
                duration = int(request.POST.get("duration_minutes") or 100)
            except Exception:
                messages.error(request, "Enter a valid start time, end time, and duration.")
                return redirect("cbt:it-jamb-admin")
            if not start or not end or end <= start:
                messages.error(request, "The JAMB window must have a valid start and end time.")
                return redirect("cbt:it-jamb-admin")
            for exam in exams:
                exam.status = CBTExamStatus.ACTIVE
                exam.open_now = False
                exam.is_time_based = True
                exam.schedule_start = start
                exam.schedule_end = end
                exam.activated_by = request.user
                exam.activated_at = timezone.now()
                exam.save(update_fields=["status", "open_now", "is_time_based", "schedule_start", "schedule_end", "activated_by", "activated_at", "updated_at"])
                blueprint = getattr(exam, "blueprint", None)
                if blueprint:
                    blueprint.duration_minutes = duration
                    config = blueprint.section_config if isinstance(blueprint.section_config, dict) else {}
                    config["review_seconds"] = 1500
                    config["objective_target_max"] = "400.00"
                    blueprint.section_config = config
                    blueprint.save(update_fields=["duration_minutes", "section_config", "updated_at"])
            messages.success(request, f"JAMB practice opened for {len(exams)} student exams.")
        elif action == "close":
            for exam in exams:
                exam.status = CBTExamStatus.CLOSED
                exam.open_now = False
                exam.schedule_end = timezone.now()
                exam.save(update_fields=["status", "open_now", "schedule_end", "updated_at"])
            messages.success(request, f"Closed {len(exams)} JAMB practice exams.")
        elif action == "reset_attempts":
            deleted, _ = ExamAttempt.objects.filter(exam__in=exams).delete()
            messages.success(request, f"Deleted {deleted} JAMB attempt record(s).")
        elif action == "expand_bank":
            from scripts.expand_jamb_clean_bank_20260616 import run as expand_jamb_bank

            result = expand_jamb_bank()
            cache.delete("cbt:jamb-bank-audit")
            messages.success(request, f"Expanded JAMB bank. Total active questions now {sum(result['counts'].values())}.")
        elif action == "rebuild_bank":
            from scripts.reset_rebuild_jamb_clean_bank_20260615 import run as rebuild_jamb_bank
            from scripts.expand_jamb_clean_bank_20260616 import run as expand_jamb_bank

            rebuild_result = rebuild_jamb_bank()
            expand_result = expand_jamb_bank()
            cache.delete("cbt:jamb-bank-audit")
            messages.success(
                request,
                f"Rebuilt JAMB: {rebuild_result.get('ss2_exams_opened', 0)} exams, then expanded to {sum(expand_result['counts'].values())} active questions.",
            )
        else:
            messages.error(request, "Choose a valid JAMB admin action.")
        return redirect("cbt:it-jamb-admin")


class CBTDeanSimulationReviewListView(CBTDeanAccessMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("results:dean-exam-review-list")


class CBTDeanSimulationReviewDetailView(CBTDeanAccessMixin, TemplateView):
    template_name = "cbt/dean_simulation_review_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.wrapper = get_object_or_404(SimulationWrapper, pk=kwargs["wrapper_id"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["wrapper"] = self.wrapper
        context["decision_form"] = kwargs.get("decision_form") or DeanSimulationDecisionForm()
        context["linked_exams"] = (
            self.wrapper.exam_links.select_related("exam", "exam__subject", "exam__academic_class")
            .order_by("-updated_at")[:20]
        )
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="reviewing CBT simulation tools")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:dean-simulation-review-detail", wrapper_id=self.wrapper.id)
        form = DeanSimulationDecisionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(decision_form=form))

        action = form.cleaned_data["action"]
        comment = form.cleaned_data.get("comment", "")
        try:
            if action == DeanSimulationDecisionForm.ACTION_APPROVE:
                dean_approve_simulation(wrapper=self.wrapper, actor=request.user, comment=comment)
                action_name = "DEAN_APPROVE_SIMULATION"
                message = "Simulation wrapper approved."
            else:
                dean_reject_simulation(wrapper=self.wrapper, actor=request.user, comment=comment)
                action_name = "DEAN_REJECT_SIMULATION"
                message = "Simulation wrapper rejected."
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:dean-simulation-review-detail", wrapper_id=self.wrapper.id)

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": action_name,
                "wrapper_id": str(self.wrapper.id),
                "status": self.wrapper.status,
            },
        )
        messages.success(request, message)
        return redirect("cbt:dean-simulation-review-detail", wrapper_id=self.wrapper.id)


class CBTDeanReviewListView(CBTDeanAccessMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse("results:dean-exam-review-list")


class CBTDeanReviewDetailView(CBTDeanAccessMixin, TemplateView):
    template_name = "cbt/dean_review_detail.html"

    def dispatch(self, request, *args, **kwargs):
        close_expired_exams(exam_ids=[kwargs["exam_id"]])
        self.exam = get_object_or_404(
            Exam.objects.select_related(
                "created_by",
                "subject",
                "academic_class",
                "session",
                "term",
                "blueprint",
            ),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(self.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("results:dean-exam-review-list")
        if subject_is_excluded_from_results(self.exam.subject):
            messages.error(request, "Chinese, German and Sign Language are not part of Dean CBT review.")
            return redirect("results:dean-exam-review-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        section_config = {}
        blueprint = getattr(self.exam, "blueprint", None)
        if blueprint and isinstance(blueprint.section_config, dict):
            section_config = blueprint.section_config
        show_simulation_section = (
            self.exam.exam_type == CBTExamType.SIM
            or section_config.get("flow_type") == ExamCreateForm.FLOW_SIMULATION
        )
        context["exam"] = self.exam
        context["exam_blueprint"] = blueprint
        context["decision_form"] = kwargs.get("decision_form") or DeanExamDecisionForm()
        context["show_simulation_section"] = show_simulation_section
        context["exam_questions"] = (
            self.exam.exam_questions.select_related("question")
            .prefetch_related(
                "question__options",
                "question__correct_answer__correct_options",
            )
            .order_by("sort_order")
        )
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="reviewing CBT exams")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("results:dean-exam-review-list")
        form = DeanExamDecisionForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(decision_form=form))
        action = form.cleaned_data["action"]
        comment = form.cleaned_data.get("comment", "")
        if action == DeanExamDecisionForm.ACTION_APPROVE and self.exam.status == CBTExamStatus.APPROVED:
            messages.info(request, "Exam was already approved.")
            return redirect("results:dean-exam-review-list")
        if action == DeanExamDecisionForm.ACTION_REJECT and self.exam.status == CBTExamStatus.DRAFT:
            messages.info(request, "Exam was already returned to draft.")
            return redirect("results:dean-exam-review-list")
        try:
            if action == DeanExamDecisionForm.ACTION_APPROVE:
                dean_approve_exam(exam=self.exam, actor=request.user, comment=comment)
                action_name = "DEAN_APPROVE"
                message = "Exam approved by Dean."
            else:
                dean_reject_exam(exam=self.exam, actor=request.user, comment=comment)
                action_name = "DEAN_REJECT"
                message = "Exam rejected back to draft."
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("results:dean-exam-review-list")

        log_cbt_config_edit(
            actor=request.user,
            request=request,
            metadata={
                "action": action_name,
                "exam_id": str(self.exam.id),
                "status": self.exam.status,
            },
        )
        messages.success(request, message)
        return redirect("results:dean-exam-review-list")


def _parse_schedule_day(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_schedule_scope(raw_value):
    raw_value = (raw_value or "").strip().lower()
    if raw_value in {"weekly", "monthly"}:
        return raw_value
    return "daily"


def _schedule_period_bounds(anchor_day, scope):
    anchor_day = anchor_day or timezone.localdate()
    if scope == "monthly":
        period_start = anchor_day.replace(day=1)
        if period_start.month == 12:
            next_month = period_start.replace(year=period_start.year + 1, month=1, day=1)
        else:
            next_month = period_start.replace(month=period_start.month + 1, day=1)
        period_end = next_month - timedelta(days=1)
        return period_start, period_end
    if scope == "weekly":
        period_start = anchor_day - timedelta(days=anchor_day.weekday())
        period_end = period_start + timedelta(days=6)
        return period_start, period_end
    return anchor_day, anchor_day


def _exam_occurs_within_period(exam, period_start, period_end):
    current_day = period_start
    while current_day <= period_end:
        if exam_occurs_on_day(exam, current_day):
            return True
        current_day += timedelta(days=1)
    return False


def _schedule_period_label(period_start, period_end, scope):
    if scope == "monthly":
        return period_start.strftime("%B %Y")
    if scope == "weekly":
        return f"{period_start.strftime('%d %b %Y')} - {period_end.strftime('%d %b %Y')}"
    return period_start.strftime("%d %b %Y")



def _apply_it_exam_filters(exams, *, class_id="", subject_id="", teacher_id=""):
    filtered = exams
    if class_id.isdigit():
        filtered = [exam for exam in filtered if exam.academic_class_id == int(class_id)]
    if subject_id.isdigit():
        filtered = [exam for exam in filtered if exam.subject_id == int(subject_id)]
    if teacher_id.isdigit():
        filtered = [exam for exam in filtered if exam.created_by_id == int(teacher_id)]
    return filtered



def _unique_exam_options(exams, attr_name):
    options = []
    seen = set()
    for exam in exams:
        value = getattr(exam, attr_name, None)
        if value is None or value.pk in seen:
            continue
        seen.add(value.pk)
        options.append(value)
    return options



def _exam_schedule_sort_key(exam):
    anchor = exam_schedule_anchor(exam) or timezone.localtime(exam.created_at)
    return (anchor, exam.academic_class.code, exam.subject.name, exam.title)


EMERGENCY_CA_FILTERS = (
    ("ca1", "CA1"),
    ("ca23", "CA2 / CA3"),
    ("ca4", "Assignment / Project / Practical"),
    ("exam", "Exam"),
)


def _emergency_component_for_exam(exam):
    blueprint = getattr(exam, "blueprint", None)
    target = (getattr(blueprint, "objective_writeback_target", "") or "").strip().upper()
    if target == CBTWritebackTarget.CA1:
        return "ca1"
    if target in {CBTWritebackTarget.CA2, CBTWritebackTarget.CA3}:
        return "ca23"
    if target == CBTWritebackTarget.CA4 or exam.exam_type == CBTExamType.PRACTICAL:
        return "ca4"
    if target == CBTWritebackTarget.OBJECTIVE or exam.exam_type == CBTExamType.EXAM:
        return "exam"
    return ""


def _emergency_component_label(exam):
    labels = dict(EMERGENCY_CA_FILTERS)
    return labels.get(_emergency_component_for_exam(exam), exam.get_exam_type_display())


def _parse_emergency_datetime(raw_date, raw_time, *, fallback=None):
    raw_date = (raw_date or "").strip()
    raw_time = (raw_time or "").strip()
    if raw_date and raw_time:
        try:
            parsed = datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
            return timezone.make_aware(parsed, timezone.get_current_timezone())
        except ValueError:
            pass
    return fallback or timezone.now()


def _student_numbers_from_text(raw_value):
    tokens = re.split(r"[\s,;]+", raw_value or "")
    return [token.strip().upper() for token in tokens if token.strip()]


def _lock_existing_selected_options(attempt, *, reason):
    locked_answer_ids = list(
        attempt.answers.filter(selected_options__isnull=False)
        .distinct()
        .values_list("id", flat=True)
    )
    locked_exam_question_ids = list(
        attempt.answers.filter(selected_options__isnull=False)
        .distinct()
        .values_list("exam_question_id", flat=True)
    )
    metadata = attempt.writeback_metadata or {}
    metadata["locked_selected_answer_ids"] = locked_answer_ids
    metadata["locked_selected_exam_question_ids"] = locked_exam_question_ids
    metadata["locked_selected_options_reason"] = reason
    metadata["locked_selected_options_at"] = timezone.now().isoformat()
    attempt.writeback_metadata = metadata
    return len(locked_answer_ids)


def _reset_attempt_for_resume(attempt, *, start_at, extra_minutes=0, lock_existing=False, lock_reason=""):
    locked_count = 0
    if lock_existing:
        locked_count = _lock_existing_selected_options(attempt, reason=lock_reason)
    attempt.status = CBTAttemptStatus.IN_PROGRESS
    attempt.started_at = start_at
    attempt.submitted_at = None
    attempt.finalized_at = None
    attempt.is_locked = False
    attempt.lock_reason = ""
    attempt.locked_at = None
    attempt.allow_resume_by_it = True
    attempt.extra_time_minutes = max(int(extra_minutes or 0), 0)
    attempt.timer_pause_seconds = 0
    attempt.auto_marking_completed = False
    attempt.writeback_completed = False
    attempt.save(
        update_fields=[
            "writeback_metadata",
            "status",
            "started_at",
            "submitted_at",
            "finalized_at",
            "is_locked",
            "lock_reason",
            "locked_at",
            "allow_resume_by_it",
            "extra_time_minutes",
            "timer_pause_seconds",
            "auto_marking_completed",
            "writeback_completed",
            "updated_at",
        ]
    )
    return locked_count


class CBTITEmergencyControlView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_emergency_control.html"

    def _score_backup_dir(self):
        return settings.ROOT_DIR / "exports" / "emergency-clear-backups"

    def _base_exams(self):
        close_expired_exams()
        exams = Exam.objects.select_related(
            "academic_class",
            "subject",
            "session",
            "term",
            "blueprint",
        ).filter(status__in=[CBTExamStatus.APPROVED, CBTExamStatus.PENDING_IT, CBTExamStatus.ACTIVE, CBTExamStatus.CLOSED])
        setup_state = get_setup_state()
        if setup_state.current_session_id and setup_state.current_term_id:
            exams = exams.filter(session_id=setup_state.current_session_id, term_id=setup_state.current_term_id)
            exams = exclude_external_exam_classes_for_term(exams, setup_state.current_term, field_name="academic_class")
        return exams.order_by("academic_class__code", "schedule_start", "subject__name", "id")

    def _filtered_exams(self):
        exams = self._base_exams()
        class_id = (self.request.GET.get("class_id") or "").strip()
        subject_id = (self.request.GET.get("subject_id") or "").strip()
        ca_filter = (self.request.GET.get("ca_filter") or "").strip().lower()
        if class_id.isdigit():
            exams = exams.filter(academic_class_id=int(class_id))
        if subject_id.isdigit():
            exams = exams.filter(subject_id=int(subject_id))
        rows = list(exams[:500])
        if ca_filter:
            rows = [exam for exam in rows if _emergency_component_for_exam(exam) == ca_filter]
        return rows

    def _student_queryset(self):
        query = (self.request.GET.get("student_search") or "").strip()
        class_id = (self.request.GET.get("class_id") or "").strip()
        User = get_user_model()
        students = User.objects.select_related("student_profile").filter(student_profile__isnull=False)
        if class_id.isdigit():
            students = students.filter(class_enrollments__academic_class_id=int(class_id), class_enrollments__is_active=True)
        if query:
            students = students.filter(
                Q(student_profile__student_number__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(username__icontains=query)
            )
        return students.distinct().order_by("student_profile__student_number")[:80]

    def _result_sheet_queryset(self):
        sheets = ResultSheet.objects.select_related(
            "academic_class",
            "subject",
            "session",
            "term",
        )
        setup_state = get_setup_state()
        if setup_state.current_session_id and setup_state.current_term_id:
            sheets = sheets.filter(session_id=setup_state.current_session_id, term_id=setup_state.current_term_id)
            sheets = exclude_external_exam_classes_for_term(sheets, setup_state.current_term, field_name="academic_class")
        class_id = (self.request.GET.get("class_id") or "").strip()
        if class_id.isdigit():
            sheets = sheets.filter(academic_class_id=int(class_id))
        subject_id = (self.request.GET.get("subject_id") or "").strip()
        if subject_id.isdigit():
            sheets = sheets.filter(subject_id=int(subject_id))
        return sheets.order_by("academic_class__code", "subject__name")

    def _repair_zero_theory_policies(self, component):
        repair_defaults = {
            "ca1": ("5.00", "5.00"),
            "ca23": ("10.00", "10.00"),
            "exam": ("20.00", "30.00"),
        }
        if component not in repair_defaults:
            raise ValidationError("Choose CA1, CA2/CA3, or Exam for split repair.")
        target_objective, target_theory = repair_defaults[component]
        fixed = []
        skipped = []
        for sheet in self._result_sheet_queryset():
            policies = normalize_result_cbt_policies(sheet.cbt_component_policies)
            section = policies[component]
            if not section.get("enabled") or Decimal(str(section.get("theory_max") or "0")) != Decimal("0.00"):
                continue
            objective_max = Decimal(str(section.get("objective_max") or "0")).quantize(Decimal("0.01"))
            if objective_max <= Decimal(target_objective):
                policies[component] = {
                    **section,
                    "objective_max": target_objective,
                    "theory_max": target_theory,
                }
                raw = dict(sheet.cbt_component_policies or {})
                raw[component] = policies[component]
                sheet.cbt_component_policies = raw
                sheet.save(update_fields=["cbt_component_policies", "updated_at"])
                fixed.append(sheet)
            else:
                skipped.append(sheet)
        return fixed, skipped

    def _update_result_policy_from_post(self, request):
        sheet = get_object_or_404(ResultSheet.objects.select_related("academic_class", "subject"), id=request.POST.get("result_sheet_id"))
        policies = normalize_result_cbt_policies(sheet.cbt_component_policies)
        section = (request.POST.get("policy_section") or "ca1").strip()
        if section not in {"ca1", "ca23", "exam"}:
            raise ValidationError("Choose CA1, CA2/CA3, or Exam.")
        try:
            objective_max = Decimal(str(request.POST.get("objective_max") or "0")).quantize(Decimal("0.01"))
            theory_max = Decimal(str(request.POST.get("theory_max") or "0")).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            raise ValidationError("Enter valid objective/theory maximum marks.")
        if objective_max < 0 or theory_max < 0:
            raise ValidationError("Maximum marks cannot be negative.")
        section_limit = Decimal("60.00") if section == "exam" else Decimal("20.00") if section == "ca23" else Decimal("10.00")
        if objective_max + theory_max > section_limit:
            raise ValidationError(f"That split exceeds the {section_limit} mark limit.")
        policies[section] = {
            "enabled": request.POST.get("policy_enabled") == "on",
            "objective_max": str(objective_max),
            "theory_max": str(theory_max),
        }
        raw = dict(sheet.cbt_component_policies or {})
        raw[section] = policies[section]
        sheet.cbt_component_policies = raw
        sheet.save(update_fields=["cbt_component_policies", "updated_at"])
        return sheet, policies[section]

    def _set_result_entry_window_from_post(self, request):
        sheet = get_object_or_404(
            ResultSheet.objects.select_related("academic_class", "subject"),
            id=request.POST.get("result_sheet_id"),
        )
        component = (request.POST.get("entry_component") or "").strip().lower()
        if component not in dict(EMERGENCY_CA_FILTERS):
            raise ValidationError("Choose the CA or exam component to unlock.")
        try:
            start_at = timezone.make_aware(
                datetime.strptime(
                    f"{request.POST.get('entry_start_date', '')} {request.POST.get('entry_start_time', '')}",
                    "%Y-%m-%d %H:%M",
                ),
                timezone.get_current_timezone(),
            )
            end_at = timezone.make_aware(
                datetime.strptime(
                    f"{request.POST.get('entry_end_date', '')} {request.POST.get('entry_end_time', '')}",
                    "%Y-%m-%d %H:%M",
                ),
                timezone.get_current_timezone(),
            )
        except ValueError as exc:
            raise ValidationError("Enter valid opening and closing dates and times.") from exc
        if end_at <= start_at:
            raise ValidationError("The theory-entry deadline must be after its start time.")
        raw = dict(sheet.cbt_component_policies or {})
        windows = dict(raw.get("emergency_entry_windows") or {})
        windows[component] = {
            "is_enabled": True,
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "note": (request.POST.get("entry_note") or "").strip(),
            "updated_by_id": request.user.id,
            "updated_at": timezone.now().isoformat(),
        }
        raw["emergency_entry_windows"] = windows
        sheet.cbt_component_policies = raw
        sheet.save(update_fields=["cbt_component_policies", "updated_at"])
        return sheet, component, start_at, end_at

    def _close_result_entry_window_from_post(self, request):
        sheet = get_object_or_404(
            ResultSheet.objects.select_related("academic_class", "subject"),
            id=request.POST.get("result_sheet_id"),
        )
        component = (request.POST.get("entry_component") or "").strip().lower()
        raw = dict(sheet.cbt_component_policies or {})
        windows = dict(raw.get("emergency_entry_windows") or {})
        row = dict(windows.get(component) or {})
        row["is_enabled"] = False
        row["updated_by_id"] = request.user.id
        row["updated_at"] = timezone.now().isoformat()
        windows[component] = row
        raw["emergency_entry_windows"] = windows
        sheet.cbt_component_policies = raw
        sheet.save(update_fields=["cbt_component_policies", "updated_at"])
        return sheet, component

    def _override_objective_score_from_post(self, request):
        exam = get_object_or_404(
            Exam.objects.select_related(
                "blueprint",
                "academic_class",
                "subject",
                "session",
                "term",
            ),
            id=request.POST.get("exam_id"),
        )
        number = (request.POST.get("student_number") or "").strip().upper()
        student = get_object_or_404(
            get_user_model().objects.select_related("student_profile"),
            student_profile__student_number=number,
        )
        try:
            new_score = Decimal(str(request.POST.get("objective_score") or "")).quantize(
                Decimal("0.01")
            )
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("Enter a valid objective score.") from exc

        component = _emergency_component_for_exam(exam)
        policies = normalize_result_cbt_policies(
            ResultSheet.objects.filter(
                academic_class=exam.academic_class,
                subject=exam.subject,
                session=exam.session,
                term=exam.term,
            )
            .values_list("cbt_component_policies", flat=True)
            .first()
            or {}
        )
        if component not in policies:
            raise ValidationError("This paper has no supported result component.")
        objective_max = Decimal(str(policies[component]["objective_max"])).quantize(
            Decimal("0.01")
        )
        if new_score < Decimal("0.00") or new_score > objective_max:
            raise ValidationError(
                f"{dict(EMERGENCY_CA_FILTERS).get(component, component)} objective "
                f"must be between 0 and {objective_max}."
            )

        attempt = (
            ExamAttempt.objects.select_for_update()
            .filter(exam=exam, student=student)
            .order_by("-attempt_number", "-id")
            .first()
        )
        if attempt is None:
            raise ValidationError("That student has no attempt for the selected paper.")
        sheet = get_object_or_404(
            ResultSheet,
            academic_class=exam.academic_class,
            subject=exam.subject,
            session=exam.session,
            term=exam.term,
        )
        score, _created = StudentSubjectScore.objects.select_for_update().get_or_create(
            result_sheet=sheet,
            student=student,
        )
        previous_attempt_score = attempt.objective_score
        field_name = ""
        breakdown_key = ""
        if component == "ca1":
            field_name = "ca1"
            breakdown_key = "ca1_objective"
            previous_result_score = score.ca1
            theory_value = score.breakdown_value("ca1_theory")
            score.ca1 = (new_score + theory_value).quantize(Decimal("0.01"))
        elif component == "ca23":
            field_name = "ca2"
            breakdown_key = "ca2_objective"
            previous_result_score = score.ca2
            score.ca2 = new_score
        elif component == "ca4":
            field_name = "ca4"
            breakdown_key = "ca4_objective"
            previous_result_score = score.ca4
            theory_value = score.breakdown_value("ca4_theory")
            score.ca4 = (new_score + theory_value).quantize(Decimal("0.01"))
        elif component == "exam":
            field_name = "objective"
            breakdown_key = "objective_auto"
            previous_result_score = score.objective
            score.objective = new_score
            score.set_breakdown_value("objective_display_raw", new_score)
        else:
            raise ValidationError("This paper cannot write an objective result.")

        score.set_breakdown_value(breakdown_key, new_score)
        score.lock_components(field_name)
        score.has_override = True
        score.override_by = request.user
        score.override_at = timezone.now()
        reason = (request.POST.get("admin_reason") or "").strip()
        if not reason:
            raise ValidationError("Enter the reason for the score override.")
        score.override_reason = reason
        score.save()

        attempt.objective_score = new_score
        attempt.total_score = (
            new_score + Decimal(str(attempt.theory_score or "0.00"))
        ).quantize(Decimal("0.01"))
        metadata = dict(attempt.writeback_metadata or {})
        history = list(metadata.get("it_score_overrides") or [])
        history.append(
            {
                "component": component,
                "field": field_name,
                "previous_attempt_score": str(previous_attempt_score),
                "previous_result_score": str(previous_result_score),
                "new_objective_score": str(new_score),
                "reason": reason,
                "actor_id": request.user.id,
                "at": timezone.now().isoformat(),
            }
        )
        metadata["it_score_overrides"] = history[-50:]
        metadata["objective_writeback"] = {
            **dict(metadata.get("objective_writeback") or {}),
            "sheet_id": sheet.id,
            "field": field_name,
            "component": component,
            "after": str(new_score),
            "overridden_by_id": request.user.id,
            "overridden_at": timezone.now().isoformat(),
        }
        attempt.writeback_metadata = metadata
        attempt.save(
            update_fields=[
                "objective_score",
                "total_score",
                "writeback_metadata",
                "updated_at",
            ]
        )
        return exam, student, component, new_score

    def _set_exam_window(self, exam, *, start_at, end_at, duration_minutes=None, restrict_student_ids=None):
        snapshot = exam.activation_snapshot if isinstance(exam.activation_snapshot, dict) else {}
        if restrict_student_ids is not None:
            snapshot["emergency_allowed_student_ids"] = [int(value) for value in restrict_student_ids]
            snapshot["emergency_restrict_until"] = end_at.isoformat()
        elif "emergency_allowed_student_ids" in snapshot:
            snapshot.pop("emergency_allowed_student_ids", None)
            snapshot.pop("emergency_restrict_until", None)
        exam.activation_snapshot = snapshot
        exam.status = CBTExamStatus.ACTIVE
        exam.schedule_start = start_at
        exam.schedule_end = end_at
        exam.open_now = start_at <= timezone.now() <= end_at
        exam.timer_is_paused = False
        exam.timer_paused_at = None
        exam.timer_pause_reason = ""
        exam.save(
            update_fields=[
                "activation_snapshot",
                "status",
                "schedule_start",
                "schedule_end",
                "open_now",
                "timer_is_paused",
                "timer_paused_at",
                "timer_pause_reason",
                "updated_at",
            ]
        )
        if duration_minutes:
            exam.blueprint.duration_minutes = max(int(duration_minutes), 1)
            exam.blueprint.allow_retake = False
            exam.blueprint.save(update_fields=["duration_minutes", "allow_retake", "updated_at"])

    def _snapshot_result_scores(self, rows, *, exam, component):
        backup_dir = self._score_backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        filename = f"exam_{exam.id}_{component}_{timestamp}.csv"
        path = backup_dir / filename
        fieldnames = [
            "score_id",
            "exam_id",
            "component",
            "result_sheet_id",
            "student_id",
            "admission_no",
            "student_name",
            "ca1",
            "ca2",
            "ca3",
            "ca4",
            "class_participation",
            "objective",
            "theory",
            "cbt_locked_fields",
            "cbt_component_breakdown",
            "updated_at",
        ]
        count = 0
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for score in rows:
                profile = getattr(score.student, "student_profile", None)
                admission_no = getattr(profile, "student_number", "") or score.student.username
                student_name = score.student.get_full_name() or score.student.username
                writer.writerow(
                    {
                        "score_id": score.id,
                        "exam_id": exam.id,
                        "component": component,
                        "result_sheet_id": score.result_sheet_id,
                        "student_id": score.student_id,
                        "admission_no": admission_no,
                        "student_name": student_name,
                        "ca1": score.ca1,
                        "ca2": score.ca2,
                        "ca3": score.ca3,
                        "ca4": score.ca4,
                        "class_participation": score.class_participation,
                        "objective": score.objective,
                        "theory": score.theory,
                        "cbt_locked_fields": json.dumps(score.normalized_locked_fields()),
                        "cbt_component_breakdown": json.dumps(score.normalized_breakdown(), sort_keys=True),
                        "updated_at": score.updated_at.isoformat() if score.updated_at else "",
                    }
                )
                count += 1
        return path, count

    def _recent_score_backups(self):
        backup_dir = self._score_backup_dir()
        if not backup_dir.exists():
            return []
        backups = []
        for path in sorted(backup_dir.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)[:25]:
            backups.append(
                {
                    "name": path.name,
                    "label": f"{path.name} ({timezone.datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.get_current_timezone()):%d %b %H:%M})",
                }
            )
        return backups

    def _restore_result_score_snapshot(self, filename):
        backup_dir = self._score_backup_dir().resolve()
        path = (backup_dir / (filename or "")).resolve()
        if backup_dir not in path.parents or path.suffix.lower() != ".csv" or not path.exists():
            raise ValidationError("Choose a valid Emergency score backup.")
        restored = 0
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                score_id = str(row.get("score_id") or "").strip()
                if not score_id.isdigit():
                    continue
                score = StudentSubjectScore.objects.filter(id=int(score_id)).first()
                if score is None:
                    continue
                for field in ("ca1", "ca2", "ca3", "ca4", "class_participation", "objective", "theory"):
                    try:
                        setattr(score, field, Decimal(str(row.get(field) or "0.00")).quantize(Decimal("0.01")))
                    except (InvalidOperation, TypeError, ValueError):
                        setattr(score, field, Decimal("0.00"))
                try:
                    locked_fields = json.loads(row.get("cbt_locked_fields") or "[]")
                except json.JSONDecodeError:
                    locked_fields = []
                try:
                    breakdown = json.loads(row.get("cbt_component_breakdown") or "{}")
                except json.JSONDecodeError:
                    breakdown = {}
                score.cbt_locked_fields = locked_fields if isinstance(locked_fields, list) else []
                score.cbt_component_breakdown = breakdown if isinstance(breakdown, dict) else {}
                score.save()
                restored += 1
        return restored, path

    def _clear_result_scores(self, exam, students=None, *, component="ca1"):
        component = (component or "ca1").strip().lower()
        component_map = {
            "ca1": {
                "fields": ["ca1"],
                "breakdown": ["ca1_objective", "ca1_theory"],
            },
            "ca2": {
                "fields": ["ca2"],
                "breakdown": ["ca2_objective"],
            },
            "ca3": {
                "fields": ["ca3"],
                "breakdown": ["ca3_theory", "ca3_objective"],
            },
            "ca23": {
                "fields": ["ca2", "ca3"],
                "breakdown": ["ca2_objective", "ca3_theory", "ca3_objective"],
            },
            "ca4": {
                "fields": ["ca4"],
                "breakdown": ["ca4_objective", "ca4_theory"],
            },
            "exam": {
                "fields": ["objective", "theory"],
                "breakdown": ["objective_auto", "objective_display_raw", "theory_auto"],
            },
        }
        if component not in component_map:
            raise ValidationError("Choose the score component to clear.")
        clear_fields = component_map[component]["fields"]
        clear_breakdown = component_map[component]["breakdown"]
        rows = StudentSubjectScore.objects.filter(
            result_sheet__academic_class=exam.academic_class,
            result_sheet__subject=exam.subject,
            result_sheet__session=exam.session,
            result_sheet__term=exam.term,
        )
        if students is not None:
            rows = rows.filter(student__in=students)
        rows = list(rows.select_related("student", "student__student_profile", "result_sheet"))
        backup_path, _backup_count = self._snapshot_result_scores(rows, exam=exam, component=component)
        count = 0
        for score in rows:
            locked = [field for field in score.normalized_locked_fields() if field not in clear_fields]
            breakdown = score.normalized_breakdown()
            for key in clear_breakdown:
                breakdown.pop(key, None)
            for field in clear_fields:
                setattr(score, field, Decimal("0.00"))
            score.cbt_locked_fields = locked
            score.cbt_component_breakdown = breakdown
            score.save()
            count += 1
        return count, backup_path

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        base_exams = self._base_exams()
        exams = self._filtered_exams()
        selected_exam_id = (self.request.GET.get("exam_id") or "").strip()
        selected_class_id = (self.request.GET.get("class_id") or "").strip()
        selected_subject_id = (self.request.GET.get("subject_id") or "").strip()
        selected_ca_filter = (self.request.GET.get("ca_filter") or "").strip().lower()
        if selected_exam_id.isdigit():
            context["selected_exam"] = next((exam for exam in exams if exam.id == int(selected_exam_id)), None)
        context["exam_options"] = [
            {"exam": exam, "component_label": _emergency_component_label(exam)}
            for exam in exams[:200]
        ]
        context["class_options"] = list(AcademicClass.objects.filter(is_active=True).order_by("code"))
        subject_ids = base_exams.values_list("subject_id", flat=True).distinct()
        context["subject_options"] = list(Subject.objects.filter(id__in=subject_ids).order_by("name"))
        context["ca_filter_options"] = EMERGENCY_CA_FILTERS
        context["student_rows"] = list(self._student_queryset())
        result_sheets = list(self._result_sheet_queryset()[:250])
        context["result_sheet_options"] = result_sheets
        context["score_backup_options"] = self._recent_score_backups()
        repair_component = selected_ca_filter if selected_ca_filter in {"ca1", "ca23", "exam"} else "ca1"
        context["repair_component"] = repair_component
        context["zero_theory_policy_rows"] = [
            sheet
            for sheet in result_sheets
            if normalize_result_cbt_policies(sheet.cbt_component_policies)[repair_component].get("enabled")
            and normalize_result_cbt_policies(sheet.cbt_component_policies)[repair_component].get("theory_max") == "0.00"
        ]
        context["selected_exam_id"] = selected_exam_id
        context["selected_class_id"] = selected_class_id
        context["selected_subject_id"] = selected_subject_id
        context["selected_ca_filter"] = selected_ca_filter
        context["today_value"] = timezone.localdate().isoformat()
        context["now_time_value"] = timezone.localtime().strftime("%H:%M")
        context["default_deadline_time"] = "18:00"
        active_entry_windows = []
        now = timezone.now()
        for sheet in result_sheets:
            raw = sheet.cbt_component_policies if isinstance(sheet.cbt_component_policies, dict) else {}
            windows = raw.get("emergency_entry_windows")
            if not isinstance(windows, dict):
                continue
            for component, row in windows.items():
                if component not in dict(EMERGENCY_CA_FILTERS) or not isinstance(row, dict) or not row.get("is_enabled"):
                    continue
                try:
                    start_at = datetime.fromisoformat(str(row.get("start_at") or ""))
                    end_at = datetime.fromisoformat(str(row.get("end_at") or ""))
                except ValueError:
                    continue
                if timezone.is_naive(start_at):
                    start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
                if timezone.is_naive(end_at):
                    end_at = timezone.make_aware(end_at, timezone.get_current_timezone())
                active_entry_windows.append({
                    "sheet": sheet,
                    "component": component,
                    "component_label": dict(EMERGENCY_CA_FILTERS)[component],
                    "start_at": start_at,
                    "end_at": end_at,
                    "is_open": start_at <= now <= end_at,
                    "is_expired": now > end_at,
                })
        context["active_entry_windows"] = active_entry_windows
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        try:
            with transaction.atomic():
                if action == "deactivate_student":
                    number = (request.POST.get("student_number") or "").strip().upper()
                    student = get_object_or_404(get_user_model(), student_profile__student_number=number)
                    student.is_active = False
                    student.save(update_fields=["is_active"])
                    profile = student.student_profile
                    profile.lifecycle_state = StudentProfile.LifecycleState.DEACTIVATED
                    profile.lifecycle_note = (request.POST.get("note") or "Deactivated by IT Emergency CBT Control.").strip()
                    profile.save(update_fields=["lifecycle_state", "lifecycle_note", "updated_at"])
                    class_count = StudentClassEnrollment.objects.filter(student=student, is_active=True).update(is_active=False, updated_at=timezone.now())
                    subject_count = StudentSubjectEnrollment.objects.filter(student=student, is_active=True).update(is_active=False, updated_at=timezone.now())
                    messages.success(request, f"{number} deactivated. Class enrollments disabled: {class_count}; subject enrollments disabled: {subject_count}.")

                elif action == "repair_zero_theory":
                    component = (request.POST.get("repair_component") or "").strip().lower()
                    fixed, skipped = self._repair_zero_theory_policies(component)
                    label = dict(EMERGENCY_CA_FILTERS)[component]
                    skipped_label = f" Skipped {len(skipped)} sheet(s) with a larger intentional objective-only split." if skipped else ""
                    messages.success(request, f"Repaired {label} theory limits on {len(fixed)} result sheet(s).{skipped_label}")

                elif action == "update_result_policy":
                    sheet, section_policy = self._update_result_policy_from_post(request)
                    enabled = "enabled" if section_policy["enabled"] else "disabled"
                    messages.success(
                        request,
                        f"{sheet.academic_class.code} {sheet.subject.name} policy updated: {enabled}, objective {section_policy['objective_max']}, theory {section_policy['theory_max']}.",
                    )

                elif action == "set_result_entry_window":
                    sheet, component, start_at, end_at = self._set_result_entry_window_from_post(request)
                    log_event(
                        category=AuditCategory.RESULTS,
                        event_type="RESULT_SUBJECT_WINDOW_SET",
                        status=AuditStatus.SUCCESS,
                        actor=request.user,
                        request=request,
                        metadata={
                            "sheet_id": str(sheet.id),
                            "component": component,
                            "start_at": start_at.isoformat(),
                            "end_at": end_at.isoformat(),
                        },
                    )
                    messages.success(
                        request,
                        f"{sheet.academic_class.code} {sheet.subject.name} {dict(EMERGENCY_CA_FILTERS)[component]} entry is open until {timezone.localtime(end_at):%d %b %H:%M}.",
                    )

                elif action == "close_result_entry_window":
                    sheet, component = self._close_result_entry_window_from_post(request)
                    messages.success(
                        request,
                        f"Closed the subject-specific {dict(EMERGENCY_CA_FILTERS).get(component, component)} entry window for {sheet.academic_class.code} {sheet.subject.name}.",
                    )

                elif action == "override_objective_score":
                    exam, student, component, new_score = self._override_objective_score_from_post(
                        request
                    )
                    log_event(
                        category=AuditCategory.RESULTS,
                        event_type="CBT_OBJECTIVE_SCORE_OVERRIDDEN",
                        status=AuditStatus.SUCCESS,
                        actor=request.user,
                        request=request,
                        metadata={
                            "exam_id": str(exam.id),
                            "student_id": str(student.id),
                            "student_number": student.student_profile.student_number,
                            "component": component,
                            "score": str(new_score),
                        },
                    )
                    messages.success(
                        request,
                        f"{student.student_profile.student_number} "
                        f"{exam.subject.name} objective is now {new_score}.",
                    )

                elif action == "restore_score_backup":
                    restored, backup_path = self._restore_result_score_snapshot(request.POST.get("backup_file"))
                    messages.success(request, f"Restored {restored} result row(s) from {backup_path.relative_to(settings.ROOT_DIR)}.")

                elif action in {"schedule_window", "clear_attempts", "reopen_selected"}:
                    exam = get_object_or_404(Exam.objects.select_related("blueprint", "academic_class", "subject", "session", "term"), id=request.POST.get("exam_id"))
                    start_at = _parse_emergency_datetime(request.POST.get("start_date"), request.POST.get("start_time"))
                    duration = int(request.POST.get("duration_minutes") or request.POST.get("minutes") or 30)
                    end_at = _parse_emergency_datetime(
                        request.POST.get("end_date"),
                        request.POST.get("end_time"),
                        fallback=start_at + timezone.timedelta(minutes=duration),
                    )
                    if end_at <= start_at:
                        end_at = start_at + timezone.timedelta(minutes=max(duration, 1))

                    if action == "schedule_window":
                        restrict_ids = None
                        numbers = _student_numbers_from_text(request.POST.get("student_numbers"))
                        if request.POST.get("restrict_to_students") == "on" and numbers:
                            restrict_ids = list(
                                get_user_model()
                                .objects.filter(student_profile__student_number__in=numbers)
                                .values_list("id", flat=True)
                            )
                        self._set_exam_window(exam, start_at=start_at, end_at=end_at, duration_minutes=duration, restrict_student_ids=restrict_ids)
                        messages.success(request, f"{exam.academic_class.code} {exam.subject.name} opened from {timezone.localtime(start_at):%H:%M} to {timezone.localtime(end_at):%H:%M}.")

                    elif action == "clear_attempts":
                        if request.POST.get("confirm_action") != "on":
                            raise ValidationError(
                                "Confirm that you reviewed the affected paper."
                            )
                        if (request.POST.get("typed_confirmation") or "").strip() != "CLEAR ATTEMPTS":
                            raise ValidationError(
                                "Type CLEAR ATTEMPTS exactly before clearing this paper."
                            )
                        if not (request.POST.get("admin_reason") or "").strip():
                            raise ValidationError(
                                "Enter the administrative reason for clearing this paper."
                            )
                        deleted = exam.attempts.all().delete()[0]
                        reset_count = 0
                        backup_path = None
                        if request.POST.get("clear_scores") == "on":
                            reset_count, backup_path = self._clear_result_scores(
                                exam,
                                component=_emergency_component_for_exam(exam),
                            )
                        backup_note = f" Backup: {backup_path.relative_to(settings.ROOT_DIR)}." if backup_path else ""
                        messages.success(request, f"Cleared {deleted} attempt record(s) for {exam.academic_class.code} {exam.subject.name}. Result rows reset: {reset_count}.{backup_note}")

                    elif action == "reopen_selected":
                        numbers = _student_numbers_from_text(request.POST.get("student_numbers"))
                        students = list(get_user_model().objects.select_related("student_profile").filter(student_profile__student_number__in=numbers))
                        if not students:
                            raise ValidationError("Enter at least one valid student admission number.")
                        restrict_ids = [student.id for student in students] if request.POST.get("restrict_to_students") == "on" else None
                        self._set_exam_window(exam, start_at=start_at, end_at=end_at, duration_minutes=duration, restrict_student_ids=restrict_ids)
                        if request.POST.get("clear_attempts") == "on":
                            exam.attempts.filter(student__in=students).delete()
                            if request.POST.get("clear_scores") == "on":
                                reset_count, backup_path = self._clear_result_scores(
                                    exam,
                                    students=students,
                                    component=_emergency_component_for_exam(exam),
                                )
                                messages.info(request, f"Result rows reset: {reset_count}. Backup: {backup_path.relative_to(settings.ROOT_DIR)}.")
                        resumed = 0
                        created = 0
                        locked = 0
                        for student in students:
                            attempt = exam.attempts.filter(student=student).order_by("-attempt_number", "-id").first()
                            if attempt is None:
                                attempt, was_created = get_or_start_attempt(student=student, exam=exam, request=request)
                                created += 1 if was_created else 0
                            locked += _reset_attempt_for_resume(
                                attempt,
                                start_at=start_at,
                                extra_minutes=int(request.POST.get("extra_time_minutes") or 0),
                                lock_existing=request.POST.get("lock_existing") == "on",
                                lock_reason="Emergency reopen: previous selected answers cannot be changed.",
                            )
                            resumed += 1
                        messages.success(request, f"Reopened {resumed} selected attempt(s), created {created}, locked {locked} existing picked answer(s).")

                else:
                    messages.error(request, "Unknown emergency CBT action.")
        except (ValidationError, ValueError) as exc:
            message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, message)
        query = {}
        if request.POST.get("exam_id"):
            query["exam_id"] = request.POST.get("exam_id")
        if request.POST.get("class_id"):
            query["class_id"] = request.POST.get("class_id")
        if request.POST.get("subject_id"):
            query["subject_id"] = request.POST.get("subject_id")
        if request.POST.get("ca_filter"):
            query["ca_filter"] = request.POST.get("ca_filter")
        suffix = f"?{urlencode(query)}" if query else ""
        return redirect(f"{reverse('cbt:it-emergency-control')}{suffix}")


class CBTITActivationListView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_activation_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Student CBT subjects, scores and reviews are visible only on the
        # calendar day of the examination. Historical access belongs to IT.
        selected_day = _parse_schedule_day(self.request.GET.get("day")) or timezone.localdate()
        selected_scope = _parse_schedule_scope(self.request.GET.get("scope"))
        period_start, period_end = _schedule_period_bounds(selected_day, selected_scope)
        selected_class_id = (self.request.GET.get("class_id") or "").strip()
        selected_subject_id = (self.request.GET.get("subject_id") or "").strip()
        selected_teacher_id = (self.request.GET.get("teacher_id") or "").strip()

        close_expired_exams()
        exams = list(
            Exam.objects.select_related(
                "subject",
                "academic_class",
                "session",
                "term",
                "created_by",
                "activated_by",
            )
            .filter(status__in=[CBTExamStatus.APPROVED, CBTExamStatus.PENDING_IT, CBTExamStatus.ACTIVE, CBTExamStatus.CLOSED])
            .order_by("academic_class__code", "subject__name", "title")
        )
        setup_state = get_setup_state()
        if setup_state.current_session_id and setup_state.current_term_id:
            exams = [
                exam
                for exam in exams
                if exam.session_id == setup_state.current_session_id
                and exam.term_id == setup_state.current_term_id
                and not class_is_external_exam_class_for_term(exam.academic_class, exam.term)
            ]
        filtered_exams = _apply_it_exam_filters(
            exams,
            class_id=selected_class_id,
            subject_id=selected_subject_id,
            teacher_id=selected_teacher_id,
        )
        if period_start is not None and period_end is not None:
            filtered_exams = [
                exam
                for exam in filtered_exams
                if _exam_occurs_within_period(exam, period_start, period_end)
            ]

        context["approved_exams"] = sorted(
            [
                exam
                for exam in filtered_exams
                if exam.status in {CBTExamStatus.APPROVED, CBTExamStatus.PENDING_IT}
            ],
            key=_exam_schedule_sort_key,
        )
        context["active_exams"] = sorted(
            [
                exam
                for exam in filtered_exams
                if exam.status == CBTExamStatus.ACTIVE
            ],
            key=_exam_schedule_sort_key,
        )
        context["closed_exams"] = sorted(
            [
                exam
                for exam in filtered_exams
                if exam.status == CBTExamStatus.CLOSED
            ],
            key=_exam_schedule_sort_key,
            reverse=True,
        )
        context["class_options"] = _unique_exam_options(exams, "academic_class")
        context["subject_options"] = _unique_exam_options(exams, "subject")
        context["teacher_options"] = _unique_exam_options(exams, "created_by")
        context["selected_day"] = selected_day
        context["selected_day_value"] = selected_day.isoformat() if selected_day else ""
        context["selected_scope"] = selected_scope
        context["selected_scope_label"] = selected_scope.capitalize()
        context["period_start"] = period_start
        context["period_end"] = period_end
        context["period_label"] = _schedule_period_label(period_start, period_end, selected_scope)
        context["selected_class_id"] = selected_class_id
        context["selected_subject_id"] = selected_subject_id
        context["selected_teacher_id"] = selected_teacher_id
        context["flagged_exam_count"] = (
            ExamAttempt.objects.filter(
                exam__in=exams,
                is_locked=True,
            )
            .values("exam_id")
            .distinct()
            .count()
        )
        # ``writeback_completed=False`` normally means that a paper theory
        # component is awaiting a teacher mark; it is not a writeback failure.
        # Show only genuine inconsistent/error states in the incident counter.
        context["writeback_issue_count"] = ExamAttempt.objects.filter(
            exam__in=exams,
            status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED],
            writeback_completed=False,
        ).filter(
            Q(theory_marking_completed=True)
            | Q(writeback_metadata__objective_writeback__error__isnull=False)
            | Q(writeback_metadata__theory_writeback__error__isnull=False)
        ).count()
        return context


class CBTITActivationDetailView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_activation_detail.html"
    QUICK_WINDOW_MINUTES = (10, 15, 30)

    def dispatch(self, request, *args, **kwargs):
        close_expired_exams(exam_ids=[kwargs["exam_id"]])
        self.exam = get_object_or_404(
            Exam.objects.select_related(
                "subject",
                "academic_class",
                "session",
                "term",
                "created_by",
                "blueprint",
                "dean_reviewed_by",
                "activated_by",
            ),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(self.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:it-activation-list")
        return super().dispatch(request, *args, **kwargs)

    def _can_save_schedule(self):
        if self.exam.status in {CBTExamStatus.APPROVED, CBTExamStatus.ACTIVE, CBTExamStatus.CLOSED}:
            return True
        return bool(self.exam.is_free_test and self.exam.status == CBTExamStatus.PENDING_IT)

    def _save_schedule_adjustment(self, *, form, actor, action_label):
        now = timezone.now()
        from_status = self.exam.status
        previous_start = self.exam.schedule_start
        previous_end = self.exam.schedule_end
        previous_duration = getattr(self.exam.blueprint, "duration_minutes", None)

        self.exam.open_now = form.cleaned_data["open_now"]
        self.exam.is_time_based = form.cleaned_data["is_time_based"]
        self.exam.schedule_start = form.cleaned_data.get("schedule_start")
        self.exam.schedule_end = form.cleaned_data.get("schedule_end")
        self.exam.timer_is_paused = False
        self.exam.timer_paused_at = None
        self.exam.timer_paused_by = None
        self.exam.timer_pause_reason = ""
        if not self.exam.activated_by_id:
            self.exam.activated_by = actor
            self.exam.activated_at = now
        if self.exam.status != CBTExamStatus.ACTIVE:
            self.exam.status = CBTExamStatus.ACTIVE
        comment = form.cleaned_data.get("activation_comment", "")
        if comment:
            self.exam.activation_comment = comment
        self.exam.full_clean()
        self.exam.save(
            update_fields=[
                "open_now",
                "is_time_based",
                "schedule_start",
                "schedule_end",
                "timer_is_paused",
                "timer_paused_at",
                "timer_paused_by",
                "timer_pause_reason",
                "activated_by",
                "activated_at",
                "activation_comment",
                "status",
                "updated_at",
            ]
        )
        ExamReviewAction.objects.create(
            exam=self.exam,
            actor=actor,
            from_status=from_status,
            to_status=self.exam.status,
            action=action_label,
            comment=(
                f"Schedule changed from {previous_start} - {previous_end} "
                f"to {self.exam.schedule_start} - {self.exam.schedule_end}. "
                f"Duration changed from {previous_duration} to {self.exam.blueprint.duration_minutes} minutes."
            ),
        )

    def _extend_or_reopen_window(self, *, actor, minutes):
        minutes = int(minutes or 0)
        if minutes not in self.QUICK_WINDOW_MINUTES:
            raise ValidationError("Choose one of the quick window buttons.")
        if self.exam.status not in {CBTExamStatus.ACTIVE, CBTExamStatus.CLOSED}:
            raise ValidationError("Quick extend/reopen is available only for active or closed exams.")

        now = timezone.now()
        from_status = self.exam.status
        previous_end = self.exam.schedule_end
        if self.exam.status == CBTExamStatus.ACTIVE and self.exam.schedule_end and self.exam.schedule_end > now:
            target_end = self.exam.schedule_end + timezone.timedelta(minutes=minutes)
        else:
            target_end = now + timezone.timedelta(minutes=minutes)

        if not self.exam.schedule_start or self.exam.schedule_start > now:
            self.exam.schedule_start = now
        self.exam.schedule_end = target_end
        self.exam.open_now = False
        self.exam.is_time_based = True
        self.exam.status = CBTExamStatus.ACTIVE
        self.exam.timer_is_paused = False
        self.exam.timer_paused_at = None
        self.exam.timer_paused_by = None
        self.exam.timer_pause_reason = ""
        if not self.exam.activated_by_id:
            self.exam.activated_by = actor
            self.exam.activated_at = now
        self.exam.full_clean()
        self.exam.save(
            update_fields=[
                "schedule_start",
                "schedule_end",
                "open_now",
                "is_time_based",
                "status",
                "timer_is_paused",
                "timer_paused_at",
                "timer_paused_by",
                "timer_pause_reason",
                "activated_by",
                "activated_at",
                "updated_at",
            ]
        )

        blueprint = getattr(self.exam, "blueprint", None)
        duration_seconds = int(getattr(blueprint, "duration_minutes", 0) or 0) * 60
        resumed_count = 0
        attempts = list(
            self.exam.attempts.select_related("exam", "student")
            .filter(status__in=[CBTAttemptStatus.IN_PROGRESS, CBTAttemptStatus.SUBMITTED], is_locked=False)
            .order_by("id")
        )
        for attempt in attempts:
            needed_pause = 0
            if duration_seconds:
                needed_pause = max(
                    int((target_end - (attempt.started_at + timezone.timedelta(seconds=duration_seconds))).total_seconds()),
                    0,
                )
            attempt.status = CBTAttemptStatus.IN_PROGRESS
            attempt.submitted_at = None
            attempt.finalized_at = None
            attempt.allow_resume_by_it = True
            attempt.active_tab_token = ""
            attempt.timer_pause_seconds = max(int(attempt.timer_pause_seconds or 0), needed_pause)
            attempt.save(
                update_fields=[
                    "status",
                    "submitted_at",
                    "finalized_at",
                    "allow_resume_by_it",
                    "active_tab_token",
                    "timer_pause_seconds",
                    "updated_at",
                ]
            )
            _save_attempt_integrity_bundle(
                attempt,
                event_type="ATTEMPT_IT_WINDOW_EXTENDED",
                details={
                    "minutes": minutes,
                    "target_end": target_end.isoformat(),
                    "timer_pause_seconds": attempt.timer_pause_seconds,
                },
            )
            _queue_attempt_snapshot(attempt, event_type="ATTEMPT_IT_WINDOW_EXTENDED")
            resumed_count += 1

        ExamReviewAction.objects.create(
            exam=self.exam,
            actor=actor,
            from_status=from_status,
            to_status=CBTExamStatus.ACTIVE,
            action="IT_QUICK_EXTEND_REOPEN",
            comment=f"Window end changed from {previous_end} to {target_end}; {resumed_count} attempt(s) reopened or extended.",
        )
        return target_end, resumed_count

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_attempt_count = self.exam.attempts.count()
        result_sheet = ResultSheet.objects.filter(
            academic_class=self.exam.academic_class,
            subject=self.exam.subject,
            session=self.exam.session,
            term=self.exam.term,
        ).first()
        attempts = list(
            self.exam.attempts.select_related("student")
            .order_by("-updated_at", "-id")[:200]
        )
        score_rows_by_student = {}
        if result_sheet is not None and attempts:
            score_rows_by_student = {
                row.student_id: row
                for row in StudentSubjectScore.objects.filter(
                    result_sheet=result_sheet,
                    student_id__in=[attempt.student_id for attempt in attempts],
                ).select_related("student")
            }
        attempt_rows = []
        for attempt in attempts:
            metadata = attempt.writeback_metadata if isinstance(attempt.writeback_metadata, dict) else {}
            objective_writeback = metadata.get("objective_writeback") or {}
            theory_writeback = metadata.get("theory_writeback") or {}
            attempt_rows.append(
                {
                    "attempt": attempt,
                    "score_row": score_rows_by_student.get(attempt.student_id),
                    "objective_writeback": objective_writeback if isinstance(objective_writeback, dict) else {},
                    "theory_writeback": theory_writeback if isinstance(theory_writeback, dict) else {},
                }
            )
        context["exam"] = self.exam
        context["exam_blueprint"] = getattr(self.exam, "blueprint", None)
        context["can_activate"] = self._can_save_schedule()
        context["quick_window_minutes"] = self.QUICK_WINDOW_MINUTES
        context["can_revoke"] = self.exam.status == CBTExamStatus.ACTIVE and total_attempt_count == 0
        context["total_attempt_count"] = total_attempt_count
        context["activation_form"] = kwargs.get("activation_form") or ITExamActivationForm(exam=self.exam)
        context["close_form"] = kwargs.get("close_form") or ITExamCloseForm()
        context["revoke_form"] = kwargs.get("revoke_form") or ITExamCloseForm(prefix="revoke")
        context["exam_questions"] = self.exam.exam_questions.select_related("question").order_by("sort_order")
        context["exam_simulations"] = self.exam.exam_simulations.select_related(
            "simulation_wrapper"
        ).order_by("sort_order")
        context["review_actions"] = self.exam.review_actions.select_related("actor").order_by("created_at")
        context["timer_is_paused"] = bool(self.exam.timer_is_paused)
        context["timer_pause_reason"] = self.exam.timer_pause_reason
        context["active_attempt_count"] = self.exam.attempts.filter(status=CBTAttemptStatus.IN_PROGRESS).count()
        context["result_sheet"] = result_sheet
        context["attempt_rows"] = attempt_rows
        context["builder_url"] = reverse("cbt:exam-builder", kwargs={"exam_id": self.exam.id})
        context["detail_url"] = reverse("cbt:exam-detail", kwargs={"exam_id": self.exam.id})
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        if action == "activate":
            if not self._can_save_schedule():
                messages.error(request, "This CBT cannot be scheduled from the IT portal in its current state.")
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            form = ITExamActivationForm(exam=self.exam, data=request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(activation_form=form))
            form.save_blueprint()
            try:
                if self.exam.status == CBTExamStatus.APPROVED or (
                    self.exam.is_free_test and self.exam.status == CBTExamStatus.PENDING_IT
                ):
                    it_activate_exam(
                        exam=self.exam,
                        actor=request.user,
                        open_now=form.cleaned_data["open_now"],
                        is_time_based=form.cleaned_data["is_time_based"],
                        schedule_start=form.cleaned_data.get("schedule_start"),
                        schedule_end=form.cleaned_data.get("schedule_end"),
                        comment=form.cleaned_data.get("activation_comment", ""),
                    )
                    success_message = "Exam activated successfully."
                else:
                    self._save_schedule_adjustment(
                        form=form,
                        actor=request.user,
                        action_label="IT_RESCHEDULE_REOPEN",
                    )
                    success_message = "Exam schedule saved. Closed papers are reopened when the new window is active."
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            log_cbt_config_edit(
                actor=request.user,
                request=request,
                metadata={
                    "action": "IT_ACTIVATE_EXAM",
                    "exam_id": str(self.exam.id),
                    "status": self.exam.status,
                },
            )
            messages.success(request, success_message)
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        if action == "quick_extend":
            try:
                target_end, resumed_count = self._extend_or_reopen_window(
                    actor=request.user,
                    minutes=request.POST.get("minutes"),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="IT_QUICK_EXTEND_REOPEN",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "exam_id": str(self.exam.id),
                    "target_end": target_end.isoformat(),
                    "attempts_resumed": resumed_count,
                },
            )
            messages.success(
                request,
                f"Exam window now ends at {timezone.localtime(target_end):%H:%M}. {resumed_count} attempt(s) can continue.",
            )
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        if action == "close":
            close_form = ITExamCloseForm(request.POST)
            if not close_form.is_valid():
                return self.render_to_response(self.get_context_data(close_form=close_form))
            try:
                it_close_exam(
                    exam=self.exam,
                    actor=request.user,
                    comment=close_form.cleaned_data.get("comment", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="IT_CLOSE_EXAM",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"exam_id": str(self.exam.id)},
            )
            messages.success(request, "Exam closed.")
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        if action == "revoke":
            revoke_form = ITExamCloseForm(request.POST, prefix="revoke")
            if not revoke_form.is_valid():
                return self.render_to_response(self.get_context_data(revoke_form=revoke_form))
            try:
                it_revoke_exam(
                    exam=self.exam,
                    actor=request.user,
                    comment=revoke_form.cleaned_data.get("comment", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="IT_REVOKE_EXAM",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"exam_id": str(self.exam.id)},
            )
            messages.success(request, "Exam revoked from the CBT board and moved back to the approved queue.")
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        if action == "pause_timer":
            try:
                pause_exam_timer(
                    exam=self.exam,
                    actor=request.user,
                    reason=(request.POST.get("timer_pause_reason") or "").strip(),
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            messages.success(request, "Exam timer paused. Active candidates keep their remaining time until you resume.")
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        if action == "resume_timer":
            try:
                paused_seconds = resume_exam_timer(
                    exam=self.exam,
                    actor=request.user,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-activation-detail", exam_id=self.exam.id)
            messages.success(request, f"Exam timer resumed. {paused_seconds} second(s) were restored to active attempts.")
            return redirect("cbt:it-activation-detail", exam_id=self.exam.id)

        messages.error(request, "Invalid IT activation action.")
        return redirect("cbt:it-activation-detail", exam_id=self.exam.id)


class CBTStudentAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return has_any_role(self.request.user, {ROLE_STUDENT})


class CBTMarkingAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return _has_cbt_workspace_access(self.request.user, CBT_MARKING_ROLES)


class CBTStudentExamListView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_exam_list.html"
    RECENT_WINDOW_HOURS = 24

    def _filter_value(self, key):
        return (self.request.GET.get(key) or "").strip()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Candidate CBT history is deliberately day-scoped. IT retains the
        # historical views; students only see subjects, scores and reviews for
        # the current local examination day.
        selected_day = timezone.localdate()
        subject_id = self._filter_value("subject_id")
        exam_type = self._filter_value("exam_type")
        schedule_status = self._filter_value("status")
        recent_status = self._filter_value("recent_status")
        student = self.request.user
        student_profile = getattr(student, "student_profile", None)

        all_exam_rows = student_available_exams(self.request.user, target_day=selected_day)
        exam_rows = list(all_exam_rows)
        if subject_id.isdigit():
            exam_rows = [row for row in exam_rows if row["exam"].subject_id == int(subject_id)]
        if exam_type:
            exam_rows = [row for row in exam_rows if row["exam"].exam_type == exam_type]
        if schedule_status:
            status_map = {
                "open": {"Open"},
                "in_progress": {"In Progress"},
                "done": {"Done"},
                "not_yet": {"Not Yet"},
                "closed": {"Closed"},
            }
            allowed = status_map.get(schedule_status, set())
            if allowed:
                exam_rows = [row for row in exam_rows if row["status_label"] in allowed]

        recent_since = timezone.now() - timezone.timedelta(hours=self.RECENT_WINDOW_HOURS)
        recent_attempts_qs = (
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint")
            .filter(student=self.request.user)
            .order_by("-updated_at")
        )
        setup_state = get_setup_state()
        if setup_state.current_session_id and setup_state.current_term_id:
            recent_attempts_qs = recent_attempts_qs.filter(
                exam__session=setup_state.current_session,
                exam__term=setup_state.current_term,
            )
        if selected_day is not None:
            recent_attempts = [
                attempt for attempt in recent_attempts_qs if exam_occurs_on_day(attempt.exam, selected_day)
            ]
        else:
            recent_attempts = list(recent_attempts_qs.filter(updated_at__gte=recent_since))
        if subject_id.isdigit():
            recent_attempts = [attempt for attempt in recent_attempts if attempt.exam.subject_id == int(subject_id)]
        if exam_type:
            recent_attempts = [attempt for attempt in recent_attempts if attempt.exam.exam_type == exam_type]
        if recent_status:
            recent_attempts = [attempt for attempt in recent_attempts if attempt.status == recent_status]

        subject_options = {}
        for row in all_exam_rows:
            subject_options[row["exam"].subject_id] = row["exam"].subject
        for attempt in recent_attempts[:20]:
            subject_options[attempt.exam.subject_id] = attempt.exam.subject

        enrollment_qs = StudentClassEnrollment.objects.select_related("academic_class", "session").filter(
            student=student,
            is_active=True,
        )
        if getattr(setup_state, "current_session_id", None):
            current_enrollment = enrollment_qs.filter(session=setup_state.current_session).first()
        else:
            current_enrollment = None
        if current_enrollment is None:
            current_enrollment = enrollment_qs.order_by("-updated_at").first()

        student_photo_url = ""
        if student_profile and getattr(student_profile, "profile_photo", None):
            try:
                student_photo_url = student_profile.profile_photo.url
            except Exception:
                student_photo_url = ""
        student_display_name = (student.display_name or "").strip() or student.get_full_name() or student.username
        student_number = getattr(student_profile, "student_number", "") or student.username
        if current_enrollment:
            student_class_code = (
                current_enrollment.academic_class.display_name
                or current_enrollment.academic_class.code
            )
        else:
            student_class_code = "Not Assigned"
        mini_bio_parts = [student_number, student_class_code]
        if student_profile and student_profile.admission_date:
            mini_bio_parts.append(f"Admitted {student_profile.admission_date:%d %b %Y}")

        context.update({
            "exam_rows": exam_rows,
            "recent_attempts": list(recent_attempts[:12]),
            "subject_options": sorted(subject_options.values(), key=lambda subject: subject.name.lower()),
            "selected_subject_id": subject_id,
            "selected_exam_type": exam_type,
            "selected_status": schedule_status,
            "selected_recent_status": recent_status,
            "selected_day": selected_day,
            "selected_day_value": selected_day.isoformat() if selected_day else "",
            "recent_window_hours": self.RECENT_WINDOW_HOURS,
            "exam_type_options": CBTExamType.choices,
            "attempt_status_options": CBTAttemptStatus.choices,
            "student_display_name": student_display_name,
            "student_number": student_number,
            "student_class_code": student_class_code,
            "student_photo_url": student_photo_url,
            "student_mini_bio": " | ".join(part for part in mini_bio_parts if part),
        })
        return context


class CBTStudentExamStartView(CBTStudentAccessMixin, RedirectView):
    permanent = False

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        exam = get_object_or_404(
            Exam.objects.select_related("subject", "academic_class", "session", "term", "blueprint"),
            pk=kwargs["exam_id"],
        )
        if not cbt_exam_is_current(exam):
            messages.error(request, CBT_CURRENT_TERM_ONLY_MESSAGE)
            return redirect("cbt:student-exam-list")
        try:
            attempt, created = get_or_start_attempt(student=request.user, exam=exam, request=request)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:student-exam-list")

        log_event(
            category=AuditCategory.CBT,
            event_type="CBT_ATTEMPT_STARTED" if created else "CBT_ATTEMPT_RESUMED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "exam_id": str(exam.id),
                "attempt_id": str(attempt.id),
                "attempt_number": attempt.attempt_number,
            },
        )
        if created:
            request.session.pop(f"cbt_theory_stage_unlocked_{attempt.id}", None)
        return redirect("cbt:student-attempt-run", attempt_id=attempt.id)


@method_decorator(csrf_exempt, name="dispatch")
class CBTStudentAttemptRunView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_attempt_run.html"

    def dispatch(self, request, *args, **kwargs):
        self.attempt = (
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "exam__term",
                "exam__blueprint",
            )
            .filter(
                pk=kwargs["attempt_id"],
                student=request.user,
            )
            .first()
        )
        if self.attempt is None:
            messages.info(request, "That exam attempt is no longer active. Please start again from Available CBT.")
            return redirect("cbt:student-exam-list")
        if not cbt_exam_is_current(self.attempt.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:student-exam-list")
        if (
            self.attempt.exam.is_time_based
            and not self.attempt.exam.open_now
            and self.attempt.exam.schedule_start
            and timezone.now() < self.attempt.exam.schedule_start
        ):
            start_label = timezone.localtime(self.attempt.exam.schedule_start).strftime("%I:%M %p")
            messages.info(request, f"This CBT opens at {start_label}.")
            return redirect("cbt:student-exam-list")
        is_ajax_post = (
            request.method == "POST"
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        self.fast_ajax_navigation = is_ajax_post and request.POST.get("action", "") in {
            "save_next",
            "save_prev",
            "save_stay",
            "jump",
        }
        self.answer_count = 0
        if self.fast_ajax_navigation:
            self.simulation_records = []
            order = (self.attempt.writeback_metadata or {}).get("question_order") or []
            self.answer_count = len(order) or self.attempt.answers.count()
            self.answers = []
        else:
            self.simulation_records = [] if is_ajax_post else ensure_simulation_records_for_attempt(self.attempt)
            self.answers = (
                ordered_attempt_answer_refs(self.attempt)
                if is_ajax_post
                else ordered_attempt_answers(self.attempt)
            )
            self.answer_count = len(self.answers)
        if not self.answer_count and not self.simulation_records:
            messages.error(request, "This exam has no questions or simulations configured.")
            return redirect("cbt:student-exam-list")

        if self.attempt.status == CBTAttemptStatus.FINALIZED:
            if self.attempt.is_locked:
                return redirect("cbt:student-attempt-locked", attempt_id=self.attempt.id)
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)

        self.deadline = attempt_deadline(self.attempt)
        if timezone.now() >= self.deadline and self.attempt.status == CBTAttemptStatus.IN_PROGRESS:
            submit_attempt(attempt=self.attempt, request=request)
            messages.info(request, "Exam time expired. Attempt submitted automatically.")
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)

        if self.attempt.status == CBTAttemptStatus.SUBMITTED and not self.attempt.allow_resume_by_it:
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)
        if self.attempt.is_locked:
            return redirect("cbt:student-attempt-locked", attempt_id=self.attempt.id)
        return super().dispatch(request, *args, **kwargs)

    def _theory_stage_session_key(self):
        return f"cbt_theory_stage_unlocked_{self.attempt.id}"

    def _unlock_theory_stage(self):
        metadata = dict(self.attempt.writeback_metadata or {})
        if metadata.get("theory_stage_unlocked"):
            return
        metadata["theory_stage_unlocked"] = True
        self.attempt.writeback_metadata = metadata
        ExamAttempt.objects.filter(pk=self.attempt.pk).update(
            writeback_metadata=metadata,
            updated_at=timezone.now(),
        )

    def _is_theory_only_resume(self):
        metadata = self.attempt.writeback_metadata or {}
        return bool(metadata.get("resume_theory_only"))

    def _section_split_counts(self):
        objective_count = 0
        theory_count = 0
        for answer in self.answers:
            question_type = answer.exam_question.question.question_type
            if question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
                objective_count += 1
            else:
                theory_count += 1
        return objective_count, theory_count

    def _is_theory_stage_unlocked(self):
        if self._is_theory_only_resume():
            return True
        metadata = self.attempt.writeback_metadata or {}
        return bool(metadata.get("theory_stage_unlocked"))

    def _active_index(self):
        answer_count = getattr(self, "answer_count", 0) or len(self.answers)
        if not answer_count:
            return 1
        raw_index = self.request.GET.get("q") or self.request.POST.get("q") or "1"
        try:
            value = int(raw_index)
        except (TypeError, ValueError):
            value = 1
        index = max(1, min(value, answer_count))
        if getattr(self, "fast_ajax_navigation", False):
            return index
        objective_count, theory_count = self._section_split_counts()
        if self._is_theory_only_resume() and objective_count > 0 and theory_count > 0:
            return max(objective_count + 1, min(index, len(self.answers)))
        if theory_count <= 0 or objective_count <= 0:
            return index
        if self._is_theory_stage_unlocked():
            return index
        if index > objective_count:
            if self.request.method == "POST":
                self._unlock_theory_stage()
                return index
            return max(1, objective_count)
        return max(1, min(index, objective_count or index))

    def _answer_for_index(self, index):
        if self.answers:
            return self.answers[index - 1]
        if getattr(self, "fast_ajax_navigation", False):
            order = (self.attempt.writeback_metadata or {}).get("question_order") or []
            exam_question_id = None
            if order and 1 <= index <= len(order):
                try:
                    exam_question_id = int(order[index - 1])
                except (TypeError, ValueError):
                    exam_question_id = None
            query = ExamAttemptAnswer.objects.select_related(
                "exam_question",
                "exam_question__question",
            ).filter(attempt_id=self.attempt.id)
            if exam_question_id:
                return query.filter(exam_question_id=exam_question_id).first()
            return query.order_by("exam_question__sort_order", "id")[index - 1:index].first()
        if not self.answers:
            return None
        return None

    def _is_answered(self, answer):
        question = answer.exam_question.question
        if question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
            selected_ids = getattr(answer, "_selected_option_ids", None)
            if selected_ids is not None:
                return bool(selected_ids)
            return answer.selected_options.exists()
        return bool((answer.response_text or "").strip() or answer.response_payload)

    def _option_entries(self, answer):
        if answer is None:
            return []
        selected_ids = getattr(answer, "_selected_option_ids", None)
        if selected_ids is None:
            selected_ids = set(answer.selected_options.values_list("id", flat=True))
        entries = []
        for index, option in enumerate(option_list_for_attempt_answer(answer)):
            entries.append(
                {
                    "id": option.id,
                    "label": chr(65 + index),
                    "stored_label": option.label,
                    "text": option.option_text,
                    "selected": option.id in selected_ids,
                }
            )
        return entries

    def _practice_section_label(self, question):
        if question is None:
            return ""
        topic = (getattr(question, "topic", "") or "").strip()
        if ":" in topic:
            prefix = topic.split(":", 1)[0].strip()
            if prefix:
                return prefix
        stem = (getattr(question, "stem", "") or "").strip()
        match = re.match(r"^\[([^\]]+)\]", stem)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _display_question_text(question):
        if question is None:
            return "", False
        number_pattern = r"(?:question\s*)?\d+\s*(?:[\.\):\-]|[a-z]\.)\s*"
        rich_text = (getattr(question, "rich_stem", "") or "").strip()
        if rich_text:
            # Rich imported stems can still contain their source-document
            # number. The live runner supplies the shuffled display number, so
            # remove only that first visible prefix while preserving markup.
            rich_text = re.sub(
                rf"(?is)^(\s*(?:<(?:p|div|span|strong|b|em|h[1-6])\b[^>]*>\s*)*){number_pattern}",
                r"\1",
                rich_text,
                count=1,
            )
            return rich_text, True
        text = (getattr(question, "stem", "") or "").strip()
        if question.question_type not in {
            CBTQuestionType.OBJECTIVE,
            CBTQuestionType.MULTI_SELECT,
        }:
            lines = text.splitlines()
            while lines and re.match(
                r"^\s*(?:instructions?|section\s+[a-z]|theory(?:\s+section|\s+questions?)?|essay(?:\s+questions?)?)\b",
                lines[0],
                flags=re.IGNORECASE,
            ):
                lines.pop(0)
                while lines and not lines[0].strip():
                    lines.pop(0)
            text = "\n".join(lines).strip()
        # The candidate UI owns question numbering after shuffling. Remove only
        # a source-document number at the beginning; keep internal subparts.
        text = re.sub(
            rf"^\s*{number_pattern}",
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        )
        return text, False

    def _resolve_stimulus_question(self, question):
        if question is None:
            return None
        if question.stimulus_image or question.stimulus_video:
            return question
        shared_key = (question.shared_stimulus_key or "").strip()
        if not shared_key:
            return None
        linked = (
            ExamQuestion.objects.select_related("question")
            .filter(exam=self.attempt.exam, question__shared_stimulus_key=shared_key)
            .order_by("sort_order")
        )
        for row in linked:
            if row.question.stimulus_image or row.question.stimulus_video:
                return row.question
        return None

    @staticmethod
    def _ordering_items(question, *, attempt_id, exam_question_id):
        if question is None or question.question_type != CBTQuestionType.ORDERING:
            return []
        answer = getattr(question, "correct_answer", None)
        raw = (getattr(answer, "note", "") or "").strip()
        if not raw:
            return []
        items = [row.strip() for row in raw.split("|") if row.strip()]
        if len(items) < 2:
            return []
        rng = random.Random(f"{attempt_id}:{exam_question_id}")
        randomized = list(items)
        rng.shuffle(randomized)
        return randomized

    def _remaining_seconds(self):
        return attempt_remaining_seconds(self.attempt)

    def _save_current_answer(self, request, answer, *, fast_objective=False):
        if answer is None:
            return
        question = answer.exam_question.question
        blueprint = getattr(self.attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        # NDGA theory is answered physically. The CBT shows the full theory
        # paper but never accepts or stores a typed theory response.
        theory_response_mode = ExamCreateForm.THEORY_RESPONSE_MODE_PAPER
        if question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
            selected_option_ids = request.POST.getlist("selected_options")
            if fast_objective:
                save_attempt_objective_answer_fast(
                    attempt=self.attempt,
                    exam_question_id=answer.exam_question_id,
                    selected_option_ids=selected_option_ids,
                )
            else:
                save_attempt_answer(
                    attempt=self.attempt,
                    exam_question_id=answer.exam_question_id,
                    selected_option_ids=selected_option_ids,
                )
            return
        response_text = request.POST.get("response_text", "")
        if question.question_type == CBTQuestionType.ORDERING:
            response_text = request.POST.get("ordering_response", response_text)
        elif question.question_type == CBTQuestionType.LABELING:
            response_text = request.POST.get("labeling_response", response_text)
        response_payload = {}
        payload_text = (request.POST.get("response_payload") or "").strip()
        if payload_text:
            response_payload = {"raw": payload_text}
        if theory_response_mode == ExamCreateForm.THEORY_RESPONSE_MODE_PAPER:
            response_text = ""
            response_payload = {}
        save_attempt_answer(
            attempt=self.attempt,
            exam_question_id=answer.exam_question_id,
            response_text=response_text,
            response_payload=response_payload,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        index = kwargs.get("active_index") or self._active_index()
        active_answer = kwargs.get("active_answer") or self._answer_for_index(index)
        active_question = active_answer.exam_question.question if active_answer else None
        shared_stimulus_keys = {
            (answer.exam_question.question.shared_stimulus_key or "").strip()
            for answer in self.answers
            if (answer.exam_question.question.shared_stimulus_key or "").strip()
        }
        stimulus_by_key = {}
        if shared_stimulus_keys:
            stimulus_rows = (
                ExamQuestion.objects.select_related("question")
                .filter(exam_id=self.attempt.exam_id, question__shared_stimulus_key__in=shared_stimulus_keys)
                .filter(Q(question__stimulus_image__isnull=False) | Q(question__stimulus_video__isnull=False))
                .order_by("sort_order")
            )
            for row in stimulus_rows:
                key = (row.question.shared_stimulus_key or "").strip()
                if key and key not in stimulus_by_key and (row.question.stimulus_image or row.question.stimulus_video):
                    stimulus_by_key[key] = row.question

        def resolve_stimulus_fast(question):
            if question is None:
                return None
            if question.stimulus_image or question.stimulus_video:
                return question
            shared_key = (question.shared_stimulus_key or "").strip()
            if not shared_key:
                return None
            return stimulus_by_key.get(shared_key)

        stimulus_question = resolve_stimulus_fast(active_question)
        active_question_text, active_question_is_rich = self._display_question_text(active_question)
        ordering_items = self._ordering_items(
            active_question,
            attempt_id=self.attempt.id,
            exam_question_id=active_answer.exam_question_id if active_answer else 0,
        )
        blueprint = getattr(self.attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        paper_code = (section_config.get("paper_code") or "").strip().upper()
        is_jamb_practice = bool(
            self.attempt.exam.subject.code == "JAMB"
            or self.attempt.exam.title.startswith("JAMB UTME Practice")
            or paper_code == "JAMB-UTME-PRACTICE"
        )
        # The school-wide review policy is fixed: one minute for normal CBT
        # and twenty-five minutes for JAMB practice. Old paper snapshots may
        # still contain the former 30-second value, so do not inherit it.
        configured_review_seconds = 1500 if is_jamb_practice else 60
        review_key = f"cbt_review_deadline_{self.attempt.id}"
        now_ts = int(timezone.now().timestamp())
        try:
            review_deadline = int(self.request.session.get(review_key) or 0)
        except (TypeError, ValueError):
            review_deadline = 0
        if review_deadline <= 0:
            review_deadline = now_ts + configured_review_seconds
            self.request.session[review_key] = review_deadline
        review_seconds = max(review_deadline - now_ts, 0)
        calculator_mode = (section_config.get("calculator_mode") or "NONE").upper()
        paper_code = (section_config.get("paper_code") or "").strip().upper()
        is_mock_practice = bool(
            self.attempt.exam.subject.code in {"MCK", "JAMB"}
            or self.attempt.exam.title.startswith("InterswitchSPAK Private Practice")
            or self.attempt.exam.title.startswith("JAMB UTME Practice")
            or paper_code in {"INTERSWITCH-SPAK-PRACTICE", "JAMB-UTME-PRACTICE"}
        )
        use_jamb_interface = True
        if is_mock_practice and calculator_mode == "NONE":
            calculator_mode = "BASIC"
        theory_response_mode = ExamCreateForm.THEORY_RESPONSE_MODE_PAPER
        objective_count, theory_count = self._section_split_counts()
        objective_answered_count = sum(
            1
            for answer in self.answers
            if answer.exam_question.question.question_type
            in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
            and self._is_answered(answer)
        )
        theory_answered_count = sum(
            1
            for answer in self.answers
            if answer.exam_question.question.question_type
            not in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
            and self._is_answered(answer)
        )
        theory_stage_unlocked = self._is_theory_stage_unlocked()
        is_theory_page = bool(
            active_question
            and active_question.question_type
            not in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
        )
        navigator = []
        navigator_groups_map = {}
        active_section = ""
        for idx, answer in enumerate(self.answers, start=1):
            section_label = (
                self._practice_section_label(answer.exam_question.question)
                or (self.attempt.exam.subject.name if use_jamb_interface else "")
            )
            if idx == index:
                active_section = section_label
            if section_label:
                group = navigator_groups_map.setdefault(
                    section_label,
                    {
                        "label": section_label,
                        "first_index": idx,
                        "items": [],
                        "answered": 0,
                        "count": 0,
                    },
                )
                group["count"] += 1
                if self._is_answered(answer):
                    group["answered"] += 1
            navigator.append(
                {
                    "index": idx,
                    "question_id": answer.exam_question_id,
                    "answered": self._is_answered(answer),
                    "flagged": answer.is_flagged,
                    "is_active": idx == index,
                    "section": section_label,
                }
            )
            if section_label:
                navigator_groups_map[section_label]["items"].append(navigator[-1])
        question_panels = []
        subject_tab_map = {}
        configured_sections = section_config.get("sections") or {}
        configured_section_order = list(configured_sections.keys()) if isinstance(configured_sections, dict) else []
        if is_mock_practice:
            preferred_order = (
                ["English", "Mathematics", "Physics", "Chemistry", "Biology"]
                if paper_code == "JAMB-UTME-PRACTICE"
                else ["Mathematics", "Physics", "Chemistry", "Biology"]
            )
            configured_section_order = preferred_order + [
                label for label in configured_section_order if label not in preferred_order
            ]
        first_theory_seen = False
        for panel_index, panel_answer in enumerate(self.answers, start=1):
            panel_question = panel_answer.exam_question.question
            section_label = (
                self._practice_section_label(panel_question)
                or (self.attempt.exam.subject.name if use_jamb_interface else "")
            )
            if section_label:
                row = subject_tab_map.setdefault(
                    section_label,
                    {
                        "label": section_label,
                        "first_index": panel_index,
                        "count": 0,
                        "answered": 0,
                    },
                )
                row["count"] += 1
                if self._is_answered(panel_answer):
                    row["answered"] += 1
            panel_stimulus_question = resolve_stimulus_fast(panel_question)
            panel_question_text, panel_question_is_rich = self._display_question_text(panel_question)
            panel_ordering_items = self._ordering_items(
                panel_question,
                attempt_id=self.attempt.id,
                exam_question_id=panel_answer.exam_question_id,
            )
            panel_is_theory = panel_question.question_type not in {
                CBTQuestionType.OBJECTIVE,
                CBTQuestionType.MULTI_SELECT,
            }
            panel_is_first_theory = panel_is_theory and not first_theory_seen
            if panel_is_theory:
                first_theory_seen = True
            question_panels.append(
                {
                    "index": panel_index,
                    "answer": panel_answer,
                    "question": panel_question,
                    "question_text": panel_question_text,
                    "question_is_rich": panel_question_is_rich,
                    "section": section_label,
                    "stimulus_question": panel_stimulus_question,
                    "option_entries": self._option_entries(panel_answer),
                    "ordering_items": panel_ordering_items,
                    "is_theory_page": panel_is_theory,
                    "is_first_theory": panel_is_first_theory,
                    "is_active": panel_index == index,
                }
            )
        student_photo_url = ""
        try:
            student_profile = getattr(self.request.user, "student_profile", None)
            if student_profile and getattr(student_profile, "profile_photo", None):
                student_photo_url = student_profile.profile_photo.url
        except Exception:
            student_photo_url = ""
        subject_tabs = list(subject_tab_map.values())
        navigator_groups = list(navigator_groups_map.values())
        if configured_section_order:
            order_map = {label: idx for idx, label in enumerate(configured_section_order)}
            subject_tabs.sort(key=lambda row: (order_map.get(row["label"], 999), row["first_index"]))
            navigator_groups.sort(key=lambda row: (order_map.get(row["label"], 999), row["first_index"]))
        else:
            subject_tabs.sort(key=lambda row: row["first_index"])
            navigator_groups.sort(key=lambda row: row["first_index"])
        context.update(
            {
                "show_portal_shell": False,
                "attempt": self.attempt,
                "exam": self.attempt.exam,
                "blueprint": blueprint,
                "answers": self.answers,
                "active_index": index,
                "active_answer": active_answer,
                "active_question": active_question,
                "active_question_text": active_question_text,
                "active_question_is_rich": active_question_is_rich,
                "stimulus_question": stimulus_question,
                "ordering_items": ordering_items,
                "option_entries": self._option_entries(active_answer),
                "navigator": navigator,
                "remaining_seconds": self._remaining_seconds(),
                "question_count": len(self.answers),
                "answered_count": sum(1 for answer in self.answers if self._is_answered(answer)),
                "objective_count": objective_count,
                "theory_count": theory_count,
                "objective_answered_count": objective_answered_count,
                "theory_answered_count": theory_answered_count,
                "theory_stage_unlocked": theory_stage_unlocked,
                "is_theory_page": is_theory_page,
                "is_last_objective_page": bool(objective_count and index == objective_count),
                "theory_response_mode": theory_response_mode,
                "theory_instructions": (
                    (section_config.get("theory_instructions") or "").strip()
                    or (getattr(blueprint, "instructions", "") or "").strip()
                ),
                "calculator_mode": calculator_mode,
                "calculator_enabled": calculator_mode != "NONE",
                "is_mock_practice": is_mock_practice,
                "use_jamb_interface": use_jamb_interface,
                "simulation_records": self.simulation_records,
                "simulation_total_count": len(self.simulation_records),
                "simulation_completed_count": len(
                    [
                        row
                        for row in self.simulation_records
                        if row.status != CBTSimulationAttemptStatus.NOT_STARTED
                    ]
                ),
                "student_photo_url": student_photo_url,
                "timer_paused": attempt_timer_is_paused(self.attempt),
                "timer_pause_reason": self.attempt.exam.timer_pause_reason,
                "question_panels": question_panels,
                "subject_tabs": subject_tabs,
                "navigator_groups": navigator_groups,
                "active_section": active_section,
                "has_question_flow": bool(self.answers),
                "show_simulation_tasks": bool(self.simulation_records) and not bool(self.answers),
                "lockdown_enabled": settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False),
                "cbt_microphone_required": bool(
                    getattr(settings, "CBT_MICROPHONE_REQUIRED", False)
                ),
                # Safe Exam Browser owns tab/app/fullscreen enforcement. Only
                # an IT-issued microphone strike consumes warning chances.
                "cbt_browser_breach_detection_enabled": False,
                "manual_audio_warning_count": lockdown_warning_count(
                    self.attempt,
                    event_type="MANUAL_AUDIO_WARNING",
                ),
                "lockdown_heartbeat_interval_seconds": settings.LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS,
                "lockdown_inactivity_timeout_seconds": settings.LOCKDOWN_INACTIVITY_TIMEOUT_SECONDS,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        if self.attempt.status == CBTAttemptStatus.IN_PROGRESS and timezone.now() >= attempt_deadline(self.attempt):
            submit_attempt(attempt=self.attempt, request=request)
            result_url = reverse("cbt:student-attempt-result", args=[self.attempt.id])
            if is_ajax:
                return JsonResponse({"ok": True, "submitted": True, "redirect_url": result_url})
            messages.info(request, "Exam time expired. Attempt submitted automatically.")
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)
        index = self._active_index()
        answer = self._answer_for_index(index)
        objective_count, theory_count = self._section_split_counts()

        if action in {"save_next", "save_prev", "save_stay", "submit", "move_to_theory", "jump"}:
            try:
                self._save_current_answer(request, answer, fast_objective=True)
            except ValidationError as exc:
                message = "; ".join(exc.messages)
                if is_ajax:
                    return JsonResponse({"ok": False, "error": message}, status=400)
                messages.error(request, message)
                return self.render_to_response(
                    self.get_context_data(active_index=index, active_answer=answer)
                )

        if action == "move_to_theory":
            if theory_count <= 0:
                if is_ajax:
                    return JsonResponse({"ok": True, "next_index": index})
                return redirect(f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={index}")
            self._unlock_theory_stage()
            next_index = max(1, objective_count + 1)
            next_url = f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={next_index}"
            if is_ajax:
                return JsonResponse({"ok": True, "next_index": next_index, "redirect_url": next_url})
            return redirect(next_url)

        if action == "toggle_flag":
            if answer is None:
                if is_ajax:
                    return JsonResponse({"ok": False, "error": "No question selected to flag."}, status=400)
                messages.error(request, "No question selected to flag.")
                return redirect("cbt:student-attempt-run", attempt_id=self.attempt.id)
            now = timezone.now()
            ExamAttemptAnswer.objects.filter(pk=answer.pk).update(
                is_flagged=not answer.is_flagged,
                updated_at=now,
            )
            ExamAttempt.objects.filter(pk=self.attempt.pk).update(
                last_activity_at=now,
                updated_at=now,
            )
            if is_ajax:
                return JsonResponse({"ok": True, "flagged": not answer.is_flagged})
            return redirect(f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={index}")

        if action == "jump":
            jump_to = request.POST.get("jump_to", "")
            try:
                jump_index = int(jump_to)
            except (TypeError, ValueError):
                jump_index = index
            answer_count = getattr(self, "answer_count", 0) or len(self.answers)
            jump_index = max(1, min(jump_index, answer_count))
            if theory_count > 0 and objective_count > 0 and not self._is_theory_stage_unlocked():
                jump_index = min(jump_index, objective_count)
            if is_ajax:
                return JsonResponse(
                    {
                        "ok": True,
                        "next_index": jump_index,
                        "redirect_url": f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={jump_index}",
                    }
                )
            return redirect(f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={jump_index}")

        if action == "submit":
            force_submit = request.POST.get("force_submit") == "1"
            if theory_count > 0 and objective_count > 0 and not self._is_theory_stage_unlocked() and not force_submit:
                message = "Finish objective section and move to theory before final submission."
                if is_ajax:
                    return JsonResponse({"ok": False, "error": message}, status=400)
                messages.error(request, message)
                return redirect(
                    f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={objective_count}"
                )
            try:
                submit_attempt(attempt=self.attempt, request=request)
            except ValidationError as exc:
                message = "; ".join(exc.messages)
                if is_ajax:
                    return JsonResponse({"ok": False, "error": message}, status=400)
                messages.error(request, message)
                return redirect("cbt:student-attempt-run", attempt_id=self.attempt.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="CBT_ATTEMPT_SUBMITTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "attempt_id": str(self.attempt.id),
                    "exam_id": str(self.attempt.exam_id),
                    "objective_score": str(self.attempt.objective_score),
                },
            )
            result_url = reverse("cbt:student-attempt-result", args=[self.attempt.id])
            if is_ajax:
                return JsonResponse({"ok": True, "submitted": True, "redirect_url": result_url})
            messages.success(request, "Exam submitted successfully.")
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)

        if action == "save_prev":
            next_index = max(1, index - 1)
        elif action == "save_stay":
            next_index = index
        else:
            answer_count = getattr(self, "answer_count", 0) or len(self.answers)
            next_index = min(answer_count, index + 1) if answer_count else 1
        if theory_count > 0 and objective_count > 0 and not self._is_theory_stage_unlocked():
            next_index = min(next_index, objective_count)
        next_url = f"{reverse('cbt:student-attempt-run', args=[self.attempt.id])}?q={next_index}"
        if is_ajax:
            return JsonResponse({"ok": True, "next_index": next_index, "redirect_url": next_url})
        return redirect(next_url)


class CBTStudentSimulationSessionView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_simulation_session.html"

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "exam__term",
                "exam__blueprint",
            ),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(self.attempt.exam):
            messages.error(request, CBT_CURRENT_TERM_ONLY_MESSAGE)
            return redirect("cbt:student-exam-list")
        if self.attempt.is_locked:
            return redirect("cbt:student-attempt-locked", attempt_id=self.attempt.id)
        self.exam_simulation = get_object_or_404(
            ExamSimulation.objects.select_related("simulation_wrapper"),
            pk=kwargs["exam_simulation_id"],
            exam=self.attempt.exam,
        )
        ensure_simulation_records_for_attempt(self.attempt)
        self.record = get_object_or_404(
            SimulationAttemptRecord.objects.select_related("exam_simulation", "exam_simulation__simulation_wrapper"),
            attempt=self.attempt,
            exam_simulation=self.exam_simulation,
        )
        return super().dispatch(request, *args, **kwargs)

    def _resolve_simulation_url(self):
        wrapper = self.exam_simulation.simulation_wrapper
        path = (wrapper.offline_asset_path or "").strip()
        offline_mode = settings.FEATURE_FLAGS.get("OFFLINE_MODE_ENABLED", False)
        if offline_mode and path:
            if path.startswith("http://") or path.startswith("https://"):
                return path
            if path.startswith("/"):
                return path
            if path.startswith("media/"):
                return f"/{path}"
            if path.startswith("static/"):
                return f"/{path}"
            return f"/media/{path}"
        if wrapper.online_url:
            return wrapper.online_url
        if not path:
            return ""
        if path.startswith("http://") or path.startswith("https://") or path.startswith("/"):
            return path
        if path.startswith("media/"):
            return f"/{path}"
        if path.startswith("static/"):
            return f"/{path}"
        return f"/media/{path}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempt"] = self.attempt
        context["exam"] = self.attempt.exam
        context["exam_simulation"] = self.exam_simulation
        context["record"] = self.record
        context["wrapper"] = self.exam_simulation.simulation_wrapper
        context["simulation_url"] = self._resolve_simulation_url()
        context["evidence_form"] = kwargs.get("evidence_form") or StudentSimulationEvidenceForm()
        return context

    def post(self, request, *args, **kwargs):
        wrapper = self.exam_simulation.simulation_wrapper
        if wrapper.score_mode == CBTSimulationScoreMode.AUTO:
            score_value = request.POST.get("manual_auto_score", "")
            payload = {
                "score": score_value,
                "source": "manual_fallback",
            }
            try:
                capture_auto_simulation_score(
                    attempt=self.attempt,
                    exam_simulation=self.exam_simulation,
                    payload=payload,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect(
                    "cbt:student-simulation-session",
                    attempt_id=self.attempt.id,
                    exam_simulation_id=self.exam_simulation.id,
                )
            log_event(
                category=AuditCategory.CBT,
                event_type="SIMULATION_AUTO_SCORE_CAPTURED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "attempt_id": str(self.attempt.id),
                    "exam_simulation_id": str(self.exam_simulation.id),
                },
            )
            messages.success(request, "Simulation auto score captured.")
            return redirect(
                "cbt:student-simulation-session",
                attempt_id=self.attempt.id,
                exam_simulation_id=self.exam_simulation.id,
            )

        evidence_form = StudentSimulationEvidenceForm(request.POST, request.FILES)
        if not evidence_form.is_valid():
            return self.render_to_response(self.get_context_data(evidence_form=evidence_form))

        try:
            if wrapper.score_mode == CBTSimulationScoreMode.VERIFY:
                submit_verify_simulation_evidence(
                    attempt=self.attempt,
                    exam_simulation=self.exam_simulation,
                    evidence_file=evidence_form.cleaned_data.get("evidence_file"),
                    evidence_note=evidence_form.cleaned_data.get("evidence_note", ""),
                )
                event_type = "SIMULATION_VERIFY_SUBMITTED"
                success_message = "Evidence submitted. Awaiting teacher verification."
            else:
                submit_rubric_simulation_start(
                    attempt=self.attempt,
                    exam_simulation=self.exam_simulation,
                    evidence_file=evidence_form.cleaned_data.get("evidence_file"),
                    evidence_note=evidence_form.cleaned_data.get("evidence_note", ""),
                )
                event_type = "SIMULATION_RUBRIC_SUBMITTED"
                success_message = "Simulation submitted. Awaiting rubric scoring."
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return self.render_to_response(self.get_context_data(evidence_form=evidence_form))

        log_event(
            category=AuditCategory.CBT,
            event_type=event_type,
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "attempt_id": str(self.attempt.id),
                "exam_simulation_id": str(self.exam_simulation.id),
                "score_mode": wrapper.score_mode,
            },
        )
        messages.success(request, success_message)
        return redirect(
            "cbt:student-simulation-session",
            attempt_id=self.attempt.id,
            exam_simulation_id=self.exam_simulation.id,
        )


class CBTAttemptSimulationAutoScoreView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(attempt.exam):
            return _current_cbt_json_error()
        exam_simulation = get_object_or_404(
            ExamSimulation.objects.select_related("simulation_wrapper"),
            pk=kwargs["exam_simulation_id"],
            exam=attempt.exam,
        )
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        try:
            record = capture_auto_simulation_score(
                attempt=attempt,
                exam_simulation=exam_simulation,
                payload=payload,
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        return JsonResponse(
            {
                "ok": True,
                "status": record.status,
                "final_score": str(record.final_score or "0.00"),
            }
        )


class CBTStudentAttemptResultView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_attempt_result.html"

    @staticmethod
    def _practice_section_label(question):
        topic = (getattr(question, "topic", "") or "").strip()
        match = re.match(r"^([^:|/]+)\s*[:|/]", topic)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _is_mock_practice(attempt):
        blueprint = getattr(attempt.exam, "blueprint", None)
        config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(config, dict):
            config = {}
        paper_code = (config.get("paper_code") or "").strip().upper()
        return bool(
            attempt.exam.is_free_test
            or attempt.exam.exam_type == CBTExamType.FREE_TEST
            or attempt.exam.subject.code in {"MCK", "JAMB"}
            or attempt.exam.title.startswith("JAMB UTME Practice")
            or attempt.exam.title.startswith("InterswitchSPAK Private Practice")
            or paper_code in {"JAMB-UTME-PRACTICE", "INTERSWITCH-SPAK-PRACTICE"}
        )

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(self.attempt.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:student-exam-list")
        result_anchor = (
            self.attempt.submitted_at
            or self.attempt.finalized_at
            or self.attempt.exam.schedule_end
            or self.attempt.started_at
        )
        if (
            result_anchor
            and timezone.localtime(result_anchor).date() != timezone.localdate()
        ):
            messages.info(
                request,
                "CBT subjects, scores and answer review are available only on the examination day.",
            )
            return redirect("cbt:student-exam-list")
        if self.attempt.status == CBTAttemptStatus.IN_PROGRESS:
            return redirect("cbt:student-attempt-run", attempt_id=self.attempt.id)
        if self.attempt.is_locked:
            return redirect("cbt:student-attempt-locked", attempt_id=self.attempt.id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        answers = ordered_attempt_answers(self.attempt)
        objective_rows = [
            row
            for row in answers
            if row.exam_question.question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
        ]
        objective_review_rows = []
        section_review_groups_map = {}
        for row in objective_rows:
            question = row.exam_question.question
            section = self._practice_section_label(question) or self.attempt.exam.subject.name
            correct_answer = getattr(question, "correct_answer", None)
            correct_options = (
                list(correct_answer.correct_options.order_by("sort_order", "label"))
                if correct_answer
                else []
            )
            selected_option_ids = set(row.selected_options.values_list("id", flat=True))
            correct_option_ids = {option.id for option in correct_options}
            option_entries = []
            selected_options = []
            correct_display_options = []
            for index, option in enumerate(option_list_for_attempt_answer(row)):
                display_label = chr(65 + index)
                entry = {
                    "option": option,
                    "label": display_label,
                    "is_selected": option.id in selected_option_ids,
                    "is_correct": option.id in correct_option_ids,
                }
                option_entries.append(entry)
                if entry["is_selected"]:
                    selected_options.append(entry)
                if entry["is_correct"]:
                    correct_display_options.append(entry)
            review_row = {
                "answer": row,
                "exam_question": row.exam_question,
                "question": question,
                "section": section,
                "option_entries": option_entries,
                "selected_options": selected_options,
                "correct_options": correct_display_options,
                "explanation": (getattr(correct_answer, "note", "") or "").strip(),
            }
            objective_review_rows.append(review_row)
            group = section_review_groups_map.setdefault(
                section,
                {"label": section, "rows": [], "correct": 0, "total": 0},
            )
            group["rows"].append(review_row)
            group["total"] += 1
            if row.is_correct:
                group["correct"] += 1
        theory_rows = [
            row
            for row in answers
            if row.exam_question.question.question_type
            in {
                CBTQuestionType.SHORT_ANSWER,
                CBTQuestionType.LABELING,
                CBTQuestionType.MATCHING,
                CBTQuestionType.ORDERING,
            }
        ]
        simulation_records = ordered_attempt_simulation_records(self.attempt)
        has_question_results = bool(objective_rows or theory_rows)
        blueprint = getattr(self.attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        is_mock_practice = self._is_mock_practice(self.attempt)
        paper_code = (section_config.get("paper_code") or "").strip().upper()
        is_jamb_practice = bool(
            self.attempt.exam.subject.code == "JAMB"
            or self.attempt.exam.title.startswith("JAMB UTME Practice")
            or paper_code == "JAMB-UTME-PRACTICE"
        )
        configured_review_seconds = 1500 if is_jamb_practice else 60
        review_key = f"cbt_review_deadline_{self.attempt.id}"
        now_ts = int(timezone.now().timestamp())
        try:
            review_deadline = int(self.request.session.get(review_key) or 0)
        except (TypeError, ValueError):
            review_deadline = 0
        if review_deadline <= 0:
            review_deadline = now_ts + configured_review_seconds
            self.request.session[review_key] = review_deadline
        review_seconds = max(review_deadline - now_ts, 0)
        order_map = {
            label: idx
            for idx, label in enumerate(["English", "Mathematics", "Physics", "Chemistry", "Biology"])
        }
        section_review_groups = list(section_review_groups_map.values())
        section_review_groups.sort(key=lambda row: (order_map.get(row["label"], 999), objective_review_rows.index(row["rows"][0]) if row["rows"] else 999))
        objective_display_score = self.attempt.objective_score
        objective_display_max = section_config.get("objective_target_max") or self.attempt.objective_max_score
        class_code = (getattr(self.attempt.exam.academic_class, "code", "") or "").strip().upper()
        if self.attempt.exam.exam_type == CBTExamType.EXAM and not class_code.startswith("SS3"):
            objective_display_max = Decimal("20.00")
        context.update(
            {
                "attempt": self.attempt,
                "exam": self.attempt.exam,
                "objective_rows": objective_rows,
                "objective_review_rows": objective_review_rows,
                "section_review_groups": section_review_groups,
                "is_mock_practice": is_mock_practice,
                "review_seconds": review_seconds,
                "theory_rows": theory_rows,
                "simulation_records": simulation_records,
                "has_question_results": has_question_results,
                "show_simulation_summary": bool(simulation_records) and not has_question_results,
                "objective_display_score": objective_display_score,
                "objective_display_max": objective_display_max,
                "theory_pending": bool(
                    theory_rows and not self.attempt.theory_marking_completed
                ),
                "is_jamb_practice": is_jamb_practice,
                "ai_tutor_enabled": bool(
                    is_jamb_practice and class_code.startswith("SS2")
                ),
            }
        )
        return context


class CBTStudentAttemptAITutorView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "exam__blueprint",
            ),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        blueprint = getattr(attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        paper_code = (section_config.get("paper_code") or "").strip().upper()
        class_code = (getattr(attempt.exam.academic_class, "code", "") or "").strip().upper()
        is_jamb = bool(
            attempt.exam.subject.code == "JAMB"
            or attempt.exam.title.startswith("JAMB UTME Practice")
            or paper_code == "JAMB-UTME-PRACTICE"
        )
        if (
            attempt.status == CBTAttemptStatus.IN_PROGRESS
            or attempt.is_locked
            or not is_jamb
            or not class_code.startswith("SS2")
        ):
            return JsonResponse(
                {"ok": False, "error": "AI Tutor is available only after an SS2 JAMB practice submission."},
                status=403,
            )
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            answer_id = int(payload.get("answer_id") or 0)
        except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            answer_id = 0
        answer = get_object_or_404(
            ExamAttemptAnswer.objects.select_related(
                "exam_question",
                "exam_question__question",
                "exam_question__question__correct_answer",
            ).prefetch_related(
                "selected_options",
                "exam_question__question__options",
                "exam_question__question__correct_answer__correct_options",
            ),
            pk=answer_id,
            attempt=attempt,
        )
        question = answer.exam_question.question
        options = list(question.options.order_by("sort_order", "label"))
        correct_answer = getattr(question, "correct_answer", None)
        correct_ids = (
            {option.id for option in correct_answer.correct_options.all()}
            if correct_answer
            else set()
        )
        selected_ids = set(answer.selected_options.values_list("id", flat=True))
        option_lines = [
            (
                f"{option.label}. {strip_tags(option.option_text or '')}"
                f"{' [correct]' if option.id in correct_ids else ''}"
                f"{' [student selected]' if option.id in selected_ids else ''}"
            )
            for option in options
        ]
        ai_payload = ai_json_response(
            system_prompt=(
                "You are the NDGA SS2 JAMB review tutor. Explain the completed question "
                "clearly and briefly without inventing facts. Return JSON with keys "
                "answer, steps (an array), and practice_tip."
            ),
            user_prompt=(
                f"Subject section: {CBTStudentAttemptResultView._practice_section_label(question) or attempt.exam.subject.name}\n"
                f"Question: {strip_tags(question.rich_stem or question.stem or '')}\n"
                f"Options:\n" + "\n".join(option_lines)
            ),
        )
        if not isinstance(ai_payload, dict):
            return JsonResponse(
                {"ok": False, "error": "AI Tutor is temporarily unavailable. Try again shortly."},
                status=503,
            )
        return JsonResponse(
            {
                "ok": True,
                "answer": str(ai_payload.get("answer") or "").strip(),
                "steps": [
                    str(row).strip()
                    for row in (ai_payload.get("steps") or [])
                    if str(row).strip()
                ][:5],
                "practice_tip": str(ai_payload.get("practice_tip") or "").strip(),
                "provider": str(ai_payload.get("_ai_provider") or "ai").strip(),
            }
        )


class CBTStudentAttemptResultPDFView(CBTStudentAccessMixin, View):
    def get(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "exam__blueprint",
                "student",
                "student__student_profile",
            ),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if attempt.status == CBTAttemptStatus.IN_PROGRESS:
            messages.info(request, "Submit the attempt before downloading the result PDF.")
            return redirect("cbt:student-attempt-run", attempt_id=attempt.id)
        answers = ordered_attempt_answers(attempt)
        objective_rows = [
            row
            for row in answers
            if row.exam_question.question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}
        ]
        review_rows = []
        section_scores = {}
        for row in objective_rows:
            question = row.exam_question.question
            section = CBTStudentAttemptRunView()._practice_section_label(question) or attempt.exam.subject.name
            data = section_scores.setdefault(section, {"total": 0, "correct": 0})
            data["total"] += 1
            if row.is_correct:
                data["correct"] += 1
            correct_answer = getattr(question, "correct_answer", None)
            correct_options = (
                list(correct_answer.correct_options.order_by("sort_order", "label"))
                if correct_answer
                else []
            )
            selected_option_ids = set(row.selected_options.values_list("id", flat=True))
            correct_option_ids = {option.id for option in correct_options}
            selected_options = []
            correct_display_options = []
            for index, option in enumerate(option_list_for_attempt_answer(row)):
                entry = {
                    "option": option,
                    "label": chr(65 + index),
                    "is_selected": option.id in selected_option_ids,
                    "is_correct": option.id in correct_option_ids,
                }
                if entry["is_selected"]:
                    selected_options.append(entry)
                if entry["is_correct"]:
                    correct_display_options.append(entry)
            review_rows.append(
                {
                    "number": row.exam_question.sort_order,
                    "section": section,
                    "question": question,
                    "selected_options": selected_options,
                    "correct_options": correct_display_options,
                    "explanation": (getattr(correct_answer, "note", "") or "").strip(),
                    "is_correct": row.is_correct,
                }
            )
        try:
            from apps.pdfs.services import render_pdf_bytes, student_profile_photo_data_uri
        except Exception as exc:
            raise RuntimeError("PDF service is not available.") from exc
        pdf_bytes = render_pdf_bytes(
            template_name="cbt/student_attempt_result_pdf.html",
            context={
                "attempt": attempt,
                "exam": attempt.exam,
                "student": attempt.student,
                "student_profile": getattr(attempt.student, "student_profile", None),
                "generated_at": timezone.now(),
                "section_scores": section_scores,
                "review_rows": review_rows,
                "student_photo_data_uri": student_profile_photo_data_uri(attempt.student),
            },
        )
        student_number = getattr(getattr(attempt.student, "student_profile", None), "student_number", "student")
        safe_number = re.sub(r"[^A-Za-z0-9_-]+", "-", student_number).strip("-")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{safe_number}-{attempt.exam.subject.code}-result.pdf"'
        return response


class CBTTheoryMarkingListView(CBTMarkingAccessMixin, TemplateView):
    template_name = "cbt/theory_marking_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempts"] = theory_marking_queryset_for_user(self.request.user)[:120]
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context


class CBTTheoryMarkingDetailView(CBTMarkingAccessMixin, TemplateView):
    template_name = "cbt/theory_marking_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint", "student"),
            pk=kwargs["attempt_id"],
        )
        if not theory_marking_queryset_for_user(request.user).filter(id=self.attempt.id).exists():
            messages.error(request, "You are not authorized to mark this attempt.")
            return redirect("cbt:theory-marking-list")
        return super().dispatch(request, *args, **kwargs)

    def _theory_answers(self):
        return (
            self.attempt.answers.select_related("exam_question", "exam_question__question", "teacher_marked_by")
            .filter(
                exam_question__question__question_type__in=[
                    CBTQuestionType.SHORT_ANSWER,
                    CBTQuestionType.LABELING,
                    CBTQuestionType.MATCHING,
                    CBTQuestionType.ORDERING,
                ]
            )
            .order_by("exam_question__sort_order")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempt"] = self.attempt
        context["theory_answers"] = kwargs.get("theory_answers") or self._theory_answers()
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        try:
            _require_cbt_window(user=request.user, action_label="marking CBT theory responses")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:theory-marking-detail", attempt_id=self.attempt.id)
        score_payload = {}
        for answer in self._theory_answers():
            score_payload[str(answer.id)] = request.POST.get(f"score_{answer.id}", "")
        try:
            apply_theory_scores(
                attempt=self.attempt,
                actor=request.user,
                score_payload=score_payload,
            )
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return self.render_to_response(self.get_context_data())

        log_event(
            category=AuditCategory.CBT,
            event_type="CBT_THEORY_MARKED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "attempt_id": str(self.attempt.id),
                "exam_id": str(self.attempt.exam_id),
                "theory_score": str(self.attempt.theory_score),
            },
        )
        messages.success(request, "Theory scores saved.")
        return redirect("cbt:theory-marking-detail", attempt_id=self.attempt.id)


class CBTSimulationMarkingListView(CBTMarkingAccessMixin, TemplateView):
    template_name = "cbt/simulation_marking_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["records"] = simulation_marking_queryset_for_user(self.request.user)[:200]
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context


class CBTSimulationMarkingDetailView(CBTMarkingAccessMixin, TemplateView):
    template_name = "cbt/simulation_marking_detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.record = get_object_or_404(
            SimulationAttemptRecord.objects.select_related(
                "attempt",
                "attempt__student",
                "attempt__exam",
                "attempt__exam__subject",
                "attempt__exam__academic_class",
                "exam_simulation",
                "exam_simulation__simulation_wrapper",
            ),
            pk=kwargs["record_id"],
        )
        if not simulation_marking_queryset_for_user(request.user).filter(id=self.record.id).exists():
            messages.error(request, "You are not authorized to score this simulation.")
            return redirect("cbt:simulation-marking-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        wrapper = self.record.exam_simulation.simulation_wrapper
        rubric_breakdown = self.record.rubric_breakdown if isinstance(self.record.rubric_breakdown, dict) else {}
        rubric_criteria = rubric_breakdown.get("criteria_scores") or {}
        rubric_initial = {
            "criteria_accuracy": rubric_criteria.get("criteria_accuracy", "0"),
            "criteria_procedure": rubric_criteria.get("criteria_procedure", "0"),
            "criteria_analysis": rubric_criteria.get("criteria_analysis", "0"),
            "criteria_presentation": rubric_criteria.get("criteria_presentation", "0"),
            "comment": self.record.verify_comment or "",
        }
        context["record"] = self.record
        context["wrapper"] = wrapper
        context["verify_form"] = kwargs.get("verify_form") or SimulationVerifyScoringForm(
            initial={"verified_score": self.record.final_score}
        )
        context["rubric_form"] = kwargs.get("rubric_form") or SimulationRubricScoringForm(
            initial=rubric_initial
        )
        context["rubric_max_score"] = self.record.exam_simulation.effective_max_score
        context["rubric_average_percent"] = rubric_breakdown.get("average_percent", "0.00")
        context["import_form"] = kwargs.get("import_form") or SimulationImportScoreForm(
            initial={"writeback_target": self.record.exam_simulation.writeback_target}
        )
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        wrapper = self.record.exam_simulation.simulation_wrapper
        try:
            _require_cbt_window(user=request.user, action_label="scoring CBT simulations")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("cbt:simulation-marking-detail", record_id=self.record.id)

        if action == "verify_score":
            form = SimulationVerifyScoringForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(verify_form=form))
            try:
                teacher_verify_simulation_score(
                    record=self.record,
                    actor=request.user,
                    verified_score=form.cleaned_data["verified_score"],
                    comment=form.cleaned_data.get("comment", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:simulation-marking-detail", record_id=self.record.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="SIMULATION_VERIFY_SCORED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "record_id": str(self.record.id),
                    "score_mode": wrapper.score_mode,
                    "final_score": str(self.record.final_score or "0.00"),
                },
            )
            messages.success(request, "Simulation verification score saved.")
            return redirect("cbt:simulation-marking-detail", record_id=self.record.id)

        if action == "rubric_score":
            form = SimulationRubricScoringForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(rubric_form=form))
            try:
                teacher_score_rubric_simulation(
                    record=self.record,
                    actor=request.user,
                    rubric_scores=form.rubric_payload(),
                    comment=form.cleaned_data.get("comment", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:simulation-marking-detail", record_id=self.record.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="SIMULATION_RUBRIC_SCORED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "record_id": str(self.record.id),
                    "score_mode": wrapper.score_mode,
                    "final_score": str(self.record.final_score or "0.00"),
                },
            )
            messages.success(request, "Rubric score saved.")
            return redirect("cbt:simulation-marking-detail", record_id=self.record.id)

        if action == "import_score":
            form = SimulationImportScoreForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(import_form=form))
            try:
                writeback = import_simulation_score_to_results(
                    record=self.record,
                    actor=request.user,
                    writeback_target=form.cleaned_data.get("writeback_target", ""),
                    manual_score=form.cleaned_data.get("manual_raw_score"),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:simulation-marking-detail", record_id=self.record.id)
            log_event(
                category=AuditCategory.CBT,
                event_type="SIMULATION_SCORE_IMPORTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "record_id": str(self.record.id),
                    "writeback": writeback,
                },
            )
            messages.success(request, "Simulation score imported to gradebook.")
            return redirect("cbt:simulation-marking-detail", record_id=self.record.id)

        messages.error(request, "Invalid simulation marking action.")
        return redirect("cbt:simulation-marking-detail", record_id=self.record.id)


class CBTStudentAttemptLockedView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_attempt_locked.html"

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(self.attempt.exam):
            messages.error(request, "Previous-term CBT records are not available in the CBT portal.")
            return redirect("cbt:student-exam-list")
        if not self.attempt.is_locked:
            if self.attempt.status == CBTAttemptStatus.IN_PROGRESS:
                return redirect("cbt:student-attempt-run", attempt_id=self.attempt.id)
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempt"] = self.attempt
        context["exam"] = self.attempt.exam
        context["appeal"] = (
            (self.attempt.writeback_metadata or {}).get("lock_appeal") or {}
        )
        return context

    def post(self, request, *args, **kwargs):
        appeal_text = (request.POST.get("appeal_text") or "").strip()
        if not appeal_text:
            messages.error(request, "Enter a short reason for the appeal.")
            return redirect(
                "cbt:student-attempt-locked",
                attempt_id=self.attempt.id,
            )
        metadata = dict(self.attempt.writeback_metadata or {})
        metadata["lock_appeal"] = {
            "status": "PENDING",
            "message": appeal_text[:1000],
            "submitted_at": timezone.now().isoformat(),
        }
        self.attempt.writeback_metadata = metadata
        self.attempt.save(update_fields=["writeback_metadata", "updated_at"])
        log_event(
            category=AuditCategory.LOCKDOWN,
            event_type="LOCKDOWN_APPEAL_SUBMITTED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "attempt_id": str(self.attempt.id),
                "exam_id": str(self.attempt.exam_id),
            },
        )
        messages.success(request, "Appeal sent to IT Manager.")
        return redirect(
            "cbt:student-attempt-locked",
            attempt_id=self.attempt.id,
        )


@method_decorator(csrf_exempt, name="dispatch")
class CBTAttemptHeartbeatView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(attempt.exam):
            return _current_cbt_json_error()
        if attempt.is_locked:
            manual_audio_lock = attempt.lock_reason == "MALPRACTICE_MANUAL_AUDIO_WARNING"
            return JsonResponse(
                {
                    "locked": True,
                    "manual_audio_warning_count": 3 if manual_audio_lock else lockdown_warning_count(
                        attempt,
                        event_type="MANUAL_AUDIO_WARNING",
                    ),
                    "redirect_url": (
                        reverse("accounts:logout")
                        if manual_audio_lock
                        else reverse("cbt:student-attempt-locked", args=[attempt.id])
                    ),
                }
            )
        if attempt.status != CBTAttemptStatus.IN_PROGRESS:
            return JsonResponse(
                {
                    "ok": True,
                    "attempt_closed": True,
                    "redirect_url": reverse("cbt:student-attempt-result", args=[attempt.id]),
                    "remaining_seconds": attempt_remaining_seconds(attempt),
                }
            )
        remaining_seconds = attempt_remaining_seconds(attempt)
        if remaining_seconds <= 0:
            submit_attempt(attempt=attempt, request=request)
            return JsonResponse(
                {
                    "ok": True,
                    "attempt_closed": True,
                    "redirect_url": reverse("cbt:student-attempt-result", args=[attempt.id]),
                    "remaining_seconds": 0,
                }
            )
        if attempt_timer_is_paused(attempt):
            return JsonResponse(
                {
                    "ok": True,
                    "paused": True,
                    "remaining_seconds": remaining_seconds,
                    "pause_reason": attempt.exam.timer_pause_reason,
                    "manual_audio_warning_count": lockdown_warning_count(
                        attempt,
                        event_type="MANUAL_AUDIO_WARNING",
                    ),
                }
            )
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return JsonResponse(
                {
                    "ok": True,
                    "lockdown_enabled": False,
                    "remaining_seconds": remaining_seconds,
                }
            )
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        tab_token = (payload.get("tab_token") or "").strip()
        try:
            result = register_lockdown_heartbeat(
                attempt=attempt,
                tab_token=tab_token,
                request=request,
                client_state=payload,
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        if result.get("locked"):
            return JsonResponse(
                {
                    "locked": True,
                    "session_conflict": bool(result.get("session_conflict")),
                    "lock_reason": (
                        "Multiple login detected"
                        if result.get("session_conflict")
                        else "Exam security violation"
                    ),
                    "redirect_url": (
                        reverse("accounts:logout")
                        if result.get("session_conflict")
                        else reverse("cbt:student-attempt-locked", args=[attempt.id])
                    ),
                }
            )
        if result.get("attempt_closed"):
            return JsonResponse(
                {
                    "ok": True,
                    **result,
                    "redirect_url": reverse("cbt:student-attempt-result", args=[attempt.id]),
                }
            )
        return JsonResponse(
            {
                "ok": True,
                **result,
                "manual_audio_warning_count": lockdown_warning_count(
                    attempt,
                    event_type="MANUAL_AUDIO_WARNING",
                ),
                "warning_limit": 3,
            }
        )


class CBTAttemptWarningView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        event_type = (payload.get("event_type") or "").strip().upper()
        details = payload.get("details") or {}
        if event_type == "STUDENT_REPORT_ERROR":
            review_key = f"cbt_review_deadline_{attempt.id}"
            try:
                review_deadline = int(request.session.get(review_key) or 0)
            except (TypeError, ValueError):
                review_deadline = 0
            if review_deadline < int(timezone.now().timestamp()):
                return JsonResponse(
                    {"ok": False, "error": "The answer-review window has closed."},
                    status=400,
                )
            record_lockdown_evidence(
                attempt=attempt,
                event_type=event_type,
                request=request,
                details=details,
            )
            return JsonResponse({"ok": True, "report_recorded": True})
        if not cbt_exam_is_current(attempt.exam):
            return _current_cbt_json_error()
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return JsonResponse({"ok": True, "lockdown_enabled": False})
        if payload.get("evidence_only"):
            try:
                record_lockdown_evidence(
                    attempt=attempt,
                    event_type=event_type,
                    request=request,
                    details=details,
                )
            except ValidationError:
                # Browser enforcement events are intentionally ignored while
                # Safe Exam Browser is the active kiosk boundary.
                return JsonResponse({"ok": True, "evidence_ignored": True})
            return JsonResponse({"ok": True, "evidence_recorded": True})
        # Student/browser events never consume strikes. Microphone strikes are
        # issued only by an authenticated IT Manager from the live monitor.
        return JsonResponse(
            {
                "ok": True,
                "strike_disabled": True,
                "warning_count": lockdown_warning_count(
                    attempt,
                    event_type="MANUAL_AUDIO_WARNING",
                ),
                "warning_limit": 3,
            }
        )


class CBTAttemptViolationView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not cbt_exam_is_current(attempt.exam):
            return _current_cbt_json_error()
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return JsonResponse({"ok": True, "lockdown_enabled": False})
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        event_type = (payload.get("event_type") or "").strip().upper()
        details = payload.get("details") or {}
        try:
            record_lockdown_violation(
                attempt=attempt,
                event_type=event_type,
                request=request,
                details=details,
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        return JsonResponse(
            {
                "locked": True,
                "redirect_url": reverse("cbt:student-attempt-locked", args=[attempt.id]),
            }
        )


class CBTITLockdownDashboardView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_lockdown_dashboard.html"

    def _class_options(self, selected_view):
        now = timezone.now()
        attempts = ExamAttempt.objects.select_related("exam__academic_class")
        if selected_view == "history":
            attempts = attempts.filter(is_locked=True).filter(
                Q(exam__status=CBTExamStatus.CLOSED)
                | Q(exam__schedule_end__lt=now)
                | Q(status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED])
            )
        else:
            stale_after = max(
                int(getattr(settings, "LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS", 90)) * 2,
                30,
            )
            attempts = attempts.filter(
                status=CBTAttemptStatus.IN_PROGRESS,
                exam__status=CBTExamStatus.ACTIVE,
            ).filter(
                Q(exam__is_time_based=False)
                | Q(exam__schedule_start__lte=now, exam__schedule_end__gte=now)
                | Q(exam__open_now=True, exam__schedule_end__isnull=True)
            ).filter(
                Q(is_locked=True)
                | Q(last_heartbeat_at__gte=now - timedelta(seconds=stale_after))
                | Q(last_heartbeat_at__isnull=True, started_at__gte=now - timedelta(seconds=30))
            )
        setup_state = get_setup_state()
        if setup_state.current_session_id and setup_state.current_term_id:
            attempts = attempts.filter(
                exam__session=setup_state.current_session,
                exam__term=setup_state.current_term,
            )
        class_ids = attempts.values_list("exam__academic_class_id", flat=True).distinct()
        return list(
            AcademicClass.objects.filter(id__in=class_ids).order_by("code")
        )

    def _selected_class_id(self, selected_view):
        options = self._class_options(selected_view)
        raw = (self.request.GET.get("class_id") or "").strip()
        allowed_ids = {row.id for row in options}
        if raw.isdigit() and int(raw) in allowed_ids:
            return int(raw), options
        return (options[0].id if options else None), options

    def _live_rows(self):
        setup_state = get_setup_state()
        now = timezone.now()
        close_expired_exams(now=now)
        stale_after = max(
            int(getattr(settings, "LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS", 90)) * 2,
            30,
        )
        heartbeat_cutoff = now - timedelta(seconds=stale_after)
        new_attempt_cutoff = now - timedelta(seconds=30)
        live_attempts = ExamAttempt.objects.select_related(
            "exam",
            "exam__subject",
            "exam__academic_class",
            "student",
            "student__student_profile",
        ).filter(
            status=CBTAttemptStatus.IN_PROGRESS,
            exam__status=CBTExamStatus.ACTIVE,
        ).filter(
            Q(exam__is_time_based=False)
            | Q(
                exam__schedule_start__lte=now,
                exam__schedule_end__gte=now,
            )
            | Q(
                exam__open_now=True,
                exam__schedule_end__isnull=True,
            )
        ).filter(
            Q(is_locked=True)
            | Q(last_heartbeat_at__gte=heartbeat_cutoff)
            | Q(
                last_heartbeat_at__isnull=True,
                started_at__gte=new_attempt_cutoff,
            )
        )
        if setup_state.current_session_id and setup_state.current_term_id:
            live_attempts = live_attempts.filter(
                exam__session=setup_state.current_session,
                exam__term=setup_state.current_term,
        )
        selected_class_id, _ = self._selected_class_id("active")
        if selected_class_id:
            live_attempts = live_attempts.filter(
                exam__academic_class_id=selected_class_id
            )
        rows = []
        seen_student_ids = set()
        for attempt in live_attempts.order_by(
            "-last_heartbeat_at",
            "-started_at",
            "-id",
        )[:1000]:
            if attempt.student_id in seen_student_ids:
                continue
            seen_student_ids.add(attempt.student_id)
            profile = getattr(attempt.student, "student_profile", None)
            warning_count = lockdown_warning_count(
                attempt,
                event_type="MANUAL_AUDIO_WARNING",
            )
            heartbeat_age = (
                int((now - attempt.last_heartbeat_at).total_seconds())
                if attempt.last_heartbeat_at
                else None
            )
            flagged = bool(
                attempt.is_locked
                or ((attempt.writeback_metadata or {}).get("malpractice_flag") or {}).get("flagged")
            )
            rows.append(
                {
                    "attempt": attempt,
                    "attempt_id": attempt.id,
                    "student_name": attempt.student.get_full_name() or attempt.student.username,
                    "admission_no": (
                        getattr(profile, "student_number", "")
                        or attempt.student.username
                    ),
                    "class_code": attempt.exam.academic_class.code,
                    "subject": attempt.exam.subject.name,
                    "warning_count": min(warning_count, 2),
                    "flagged": flagged,
                    "state": (
                        "Flagged"
                        if flagged
                        else "Warning"
                        if warning_count
                        else "Active"
                    ),
                    "heartbeat_age": heartbeat_age,
                    "heartbeat_missing": (
                        heartbeat_age is None or heartbeat_age > stale_after
                    ),
                    "action_url": reverse(
                        "cbt:it-lockdown-action",
                        args=[attempt.id],
                    ),
                }
            )
        rows.sort(
            key=lambda row: (
                row["class_code"],
                row["student_name"].casefold(),
                row["admission_no"].casefold(),
            )
        )
        return rows, stale_after

    def _history_rows(self):
        setup_state = get_setup_state()
        now = timezone.now()
        close_expired_exams(now=now)
        attempts = (
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "student",
                "student__student_profile",
            )
            .filter(is_locked=True)
            .filter(
                Q(exam__status=CBTExamStatus.CLOSED)
                | Q(exam__schedule_end__lt=now)
                | Q(status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED])
            )
        )
        if setup_state.current_session_id and setup_state.current_term_id:
            attempts = attempts.filter(
                exam__session=setup_state.current_session,
                exam__term=setup_state.current_term,
            )
        selected_class_id, _ = self._selected_class_id("history")
        if selected_class_id:
            attempts = attempts.filter(exam__academic_class_id=selected_class_id)
        rows = []
        for attempt in attempts.order_by("-locked_at", "-id")[:500]:
            profile = getattr(attempt.student, "student_profile", None)
            metadata = attempt.writeback_metadata or {}
            appeal = dict(metadata.get("lock_appeal") or {})
            rows.append(
                {
                    "attempt": attempt,
                    "attempt_id": attempt.id,
                    "student_name": attempt.student.get_full_name() or attempt.student.username,
                    "admission_no": (
                        getattr(profile, "student_number", "")
                        or attempt.student.username
                    ),
                    "class_code": attempt.exam.academic_class.code,
                    "subject": attempt.exam.subject.name,
                    "warning_count": 3,
                    "flagged": True,
                    "state": "Appeal Pending" if appeal.get("status") == "PENDING" else "Flagged",
                    "appeal_status": appeal.get("status", ""),
                    "appeal_message": appeal.get("message", ""),
                    "window_ended": True,
                    "action_url": reverse(
                        "cbt:it-lockdown-action",
                        args=[attempt.id],
                    ),
                }
            )
        return rows

    def get(self, request, *args, **kwargs):
        selected_view = (request.GET.get("view") or "active").strip().lower()
        if selected_view not in {"active", "history"}:
            selected_view = "active"
        if request.GET.get("format") == "json":
            if selected_view == "history":
                rows = self._history_rows()
                stale_after = 0
            else:
                rows, stale_after = self._live_rows()
            return JsonResponse(
                {
                    "ok": True,
                    "view": selected_view,
                    "count": len(rows),
                    "stale_after": stale_after,
                    "selected_class_id": self._selected_class_id(selected_view)[0],
                    "classes": [
                        {"id": row.id, "code": row.code}
                        for row in self._selected_class_id(selected_view)[1]
                    ],
                    "rows": [
                        {
                            key: value
                            for key, value in row.items()
                            if key != "attempt"
                        }
                        for row in rows
                    ],
                }
            )
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_view = (self.request.GET.get("view") or "active").strip().lower()
        if selected_view not in {"active", "history"}:
            selected_view = "active"
        if selected_view == "history":
            monitor_rows = self._history_rows()
            stale_after = 0
        else:
            monitor_rows, stale_after = self._live_rows()
        context["selected_monitor_view"] = selected_view
        selected_class_id, class_options = self._selected_class_id(selected_view)
        context["selected_class_id"] = selected_class_id
        context["monitor_class_options"] = class_options
        context["monitor_rows"] = monitor_rows
        context["live_attempt_rows"] = monitor_rows
        context["heartbeat_stale_after"] = stale_after
        return context


class CBTITLockdownActionView(CBTITAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "student"),
            pk=kwargs["attempt_id"],
        )
        if not cbt_exam_is_current(attempt.exam):
            messages.error(request, CBT_CURRENT_TERM_ONLY_MESSAGE)
            return redirect("cbt:it-lockdown-dashboard")
        action = (request.POST.get("action") or "").strip().lower()
        wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"

        if action == "mic_strike":
            with transaction.atomic():
                attempt = (
                    ExamAttempt.objects.select_for_update()
                    .select_related("exam", "student")
                    .get(pk=attempt.pk)
                )
                if attempt.status != CBTAttemptStatus.IN_PROGRESS:
                    payload = {
                        "ok": False,
                        "error": "This student is no longer writing the examination.",
                    }
                    if wants_json:
                        return JsonResponse(payload, status=409)
                    messages.error(request, payload["error"])
                    return redirect("cbt:it-lockdown-dashboard")
                now = timezone.now()
                window_is_open = bool(
                    attempt.exam.status == CBTExamStatus.ACTIVE
                    and (
                        not attempt.exam.is_time_based
                        or (
                            attempt.exam.schedule_start
                            and attempt.exam.schedule_end
                            and attempt.exam.schedule_start <= now <= attempt.exam.schedule_end
                        )
                        or (
                            attempt.exam.open_now
                            and (
                                attempt.exam.schedule_end is None
                                or now <= attempt.exam.schedule_end
                            )
                        )
                    )
                    and now < attempt_deadline(attempt)
                )
                if not window_is_open:
                    if attempt.status == CBTAttemptStatus.IN_PROGRESS:
                        submit_attempt(attempt=attempt, request=request)
                    payload = {
                        "ok": False,
                        "error": "This examination window has ended. The attempt was submitted automatically.",
                    }
                    if wants_json:
                        return JsonResponse(payload, status=409)
                    messages.error(request, payload["error"])
                    return redirect("cbt:it-lockdown-dashboard")
                if attempt.is_locked:
                    payload = {
                        "ok": False,
                        "error": "This attempt is already flagged and locked.",
                        "flagged": True,
                    }
                    if wants_json:
                        return JsonResponse(payload, status=409)
                    messages.error(request, payload["error"])
                    return redirect("cbt:it-lockdown-dashboard")
                prior_count = lockdown_warning_count(
                    attempt,
                    event_type="MANUAL_AUDIO_WARNING",
                )
                details = {
                    "issued_by_it": request.user.username,
                    "warning_count": prior_count + 1,
                    "warning_limit": 3,
                    "reason": "Microphone detected sound",
                }
                if prior_count >= 2:
                    record_lockdown_violation(
                        attempt=attempt,
                        event_type="MANUAL_AUDIO_WARNING",
                        request=request,
                        details={
                            **details,
                            "defer_submission_for_it": True,
                            "malpractice_flagged": True,
                        },
                    )
                    payload = {
                        "ok": True,
                        "warning_count": 3,
                        "flagged": True,
                        "state": "Flagged",
                        "message": "Third microphone strike issued. Student locked and logged out.",
                    }
                else:
                    record_lockdown_warning(
                        attempt=attempt,
                        event_type="MANUAL_AUDIO_WARNING",
                        request=request,
                        details=details,
                    )
                    warning_count = prior_count + 1
                    payload = {
                        "ok": True,
                        "warning_count": warning_count,
                        "flagged": False,
                        "state": "Warning",
                        "message": (
                            "Final warning issued. The next microphone strike logs the student out."
                            if warning_count == 2
                            else "Microphone warning issued. One warning remains."
                        ),
                    }
            if wants_json:
                return JsonResponse(payload)
            messages.success(request, payload["message"])
            return redirect("cbt:it-lockdown-dashboard")

        if action == "unflag":
            now = timezone.now()
            can_resume = bool(
                attempt.status == CBTAttemptStatus.IN_PROGRESS
                and attempt.exam.status == CBTExamStatus.ACTIVE
                and now < attempt_deadline(attempt)
                and (
                    not attempt.exam.is_time_based
                    or (
                        attempt.exam.schedule_start
                        and attempt.exam.schedule_end
                        and attempt.exam.schedule_start <= now <= attempt.exam.schedule_end
                    )
                    or (
                        attempt.exam.open_now
                        and (
                            attempt.exam.schedule_end is None
                            or now <= attempt.exam.schedule_end
                        )
                    )
                )
            )
            try:
                it_unlock_attempt(
                    attempt=attempt,
                    actor=request.user,
                    allow_resume=can_resume,
                    request=request,
                )
            except ValidationError as exc:
                payload = {"ok": False, "error": "; ".join(exc.messages)}
                if wants_json:
                    return JsonResponse(payload, status=400)
                messages.error(request, payload["error"])
                return redirect("cbt:it-lockdown-dashboard")
            payload = {
                "ok": True,
                "unflagged": True,
                "message": (
                    "Student unflagged and may resume this examination."
                    if can_resume
                    else "Student unflagged. The submitted score is now released."
                ),
            }
            if wants_json:
                return JsonResponse(payload)
            messages.success(request, payload["message"])
            return redirect(
                f"{reverse('cbt:it-lockdown-dashboard')}?view="
                f"{'active' if can_resume else 'history'}"
            )

        allow_resume = request.POST.get("allow_resume") == "on"
        extra_time_minutes = request.POST.get("extra_time_minutes") or "0"
        try:
            extra_time_value = int(extra_time_minutes)
        except (TypeError, ValueError):
            extra_time_value = 0

        if action in {"unlock", "resume", "submit"}:
            if action == "resume":
                allow_resume = True
            elif action == "submit":
                allow_resume = False
            try:
                it_unlock_attempt(
                    attempt=attempt,
                    actor=request.user,
                    allow_resume=allow_resume,
                    extra_time_minutes=extra_time_value,
                    request=request,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return redirect("cbt:it-lockdown-dashboard")
            messages.success(
                request,
                "Candidate may resume the CBT."
                if allow_resume
                else "Candidate answers were submitted and the flag was resolved by IT.",
            )
            return redirect("cbt:it-lockdown-dashboard")

        messages.error(request, "Invalid lockdown action.")
        return redirect("cbt:it-lockdown-dashboard")
