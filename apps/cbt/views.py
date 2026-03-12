import json
import logging
import random
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

from django.contrib import messages
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils import timezone
from django.views import View
from django.views.generic import RedirectView, TemplateView

from apps.accounts.constants import (
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.permissions import has_any_role
from apps.academics.models import AcademicSession, StudentClassEnrollment, Subject, Term
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
    ExamBlueprint,
    ExamDocumentImport,
    ExamQuestion,
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
    ordered_attempt_simulation_records,
    option_list_for_attempt_answer,
    ordered_attempt_answers,
    simulation_marking_queryset_for_user,
    simulation_catalog_grouped_labels,
    recommended_simulation_queryset,
    simulation_registry_queryset,
    seed_curated_simulation_library,
    record_lockdown_violation,
    record_lockdown_warning,
    register_lockdown_heartbeat,
    save_attempt_answer,
    submit_rubric_simulation_start,
    submit_verify_simulation_evidence,
    student_available_exams,
    submit_attempt,
    teacher_score_rubric_simulation,
    teacher_verify_simulation_score,
    theory_marking_queryset_for_user,
    ensure_simulation_records_for_attempt,
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
from apps.notifications.services import notify_cbt_schedule_published
from apps.setup_wizard.services import get_setup_state

CBT_AUTHORING_ROLES = {
    ROLE_SUBJECT_TEACHER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
}
CBT_DEAN_ROLES = {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL}
CBT_IT_ROLES = {ROLE_IT_MANAGER}
CBT_MARKING_ROLES = {
    ROLE_SUBJECT_TEACHER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_VP,
}

OBJECTIVE_QUESTION_TYPES = {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}

logger = logging.getLogger(__name__)


def _exam_is_editable_for_actor(*, actor, exam):
    if can_manage_all_cbt(actor):
        return exam.status in {
            CBTExamStatus.DRAFT,
            CBTExamStatus.PENDING_DEAN,
            CBTExamStatus.PENDING_IT,
            CBTExamStatus.APPROVED,
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
    for index, row in enumerate(ordered_rows, start=1):
        if row.sort_order != index:
            row.sort_order = index
            row.save(update_fields=["sort_order", "updated_at"])


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
        return has_any_role(self.request.user, CBT_AUTHORING_ROLES)


class CBTDeanAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return has_any_role(self.request.user, CBT_DEAN_ROLES)


class CBTITAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return has_any_role(self.request.user, CBT_IT_ROLES)


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
        session_ids = list(assignment_qs.values_list("session_id", flat=True).distinct())
        available_sessions = list(
            AcademicSession.objects.filter(id__in=session_ids).order_by("-name")
        )

        selected_session = None
        requested_session_id = (request.GET.get("session_id") or "").strip()
        if requested_session_id:
            selected_session = next(
                (
                    row
                    for row in available_sessions
                    if str(row.id) == requested_session_id
                ),
                None,
            )
        if selected_session is None:
            selected_session = next(
                (
                    row
                    for row in available_sessions
                    if setup_state.current_session_id and row.id == setup_state.current_session_id
                ),
                None,
            )
        if selected_session is None and available_sessions:
            selected_session = available_sessions[0]

        available_terms = []
        if selected_session:
            term_ids = list(
                assignment_qs.filter(session=selected_session).values_list("term_id", flat=True).distinct()
            )
            available_terms = list(Term.objects.filter(id__in=term_ids).order_by("name"))

        selected_term = None
        requested_term_id = (request.GET.get("term_id") or "").strip()
        if requested_term_id:
            selected_term = next(
                (
                    row
                    for row in available_terms
                    if str(row.id) == requested_term_id
                ),
                None,
            )
        if selected_term is None:
            selected_term = next(
                (
                    row
                    for row in available_terms
                    if setup_state.current_term_id and row.id == setup_state.current_term_id
                ),
                None,
            )
        if selected_term is None and available_terms:
            selected_term = available_terms[0]
        return {
            "available_sessions": available_sessions,
            "available_terms": available_terms,
            "selected_session": selected_session,
            "selected_term": selected_term,
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

        exams = authoring_exam_queryset(self.request.user)
        if selected_session:
            exams = exams.filter(session=selected_session)
        if selected_term:
            exams = exams.filter(term=selected_term)
        exam_rows = list(exams[:20])
        for row in exam_rows:
            row.open_url = _exam_open_url(row)

        context["assignments"] = filtered_assignments[:24]
        context["question_banks"] = authoring_question_bank_queryset(self.request.user)[:12]
        context["questions"] = (
            Question.objects.select_related("question_bank", "subject", "created_by")
            .filter(created_by=self.request.user)
            .order_by("-updated_at")[:20]
        )
        context["exams"] = exam_rows
        context["imports"] = ExamDocumentImport.objects.filter(
            uploaded_by=self.request.user
        ).order_by("-created_at")[:10]
        context["show_simulation_registry_cta"] = has_any_role(
            self.request.user,
            {ROLE_IT_MANAGER},
        )
        context["has_exams"] = bool(exam_rows)
        context["available_sessions"] = window["available_sessions"]
        context["available_terms"] = window["available_terms"]
        context["selected_session"] = selected_session
        context["selected_term"] = selected_term
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
        if not can_manage_all_cbt(request.user) and self.exam.created_by_id != request.user.id:
            messages.error(request, "You cannot access this exam.")
            return redirect("cbt:authoring-home")
        config = _builder_config(self.exam)
        if self.exam.exam_type == CBTExamType.SIM or config.get("flow_type") == ExamCreateForm.FLOW_SIMULATION:
            return redirect("cbt:exam-simulation-picker", exam_id=self.exam.id)

        self.can_edit = _exam_is_editable_for_actor(actor=request.user, exam=self.exam)
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
            }
            provided_labels = [label for label, text in option_map.items() if text]
            if len(provided_labels) < 2:
                raise ValidationError("Provide at least two options for objective question.")
            sort_map = {"A": 1, "B": 2, "C": 3, "D": 4}
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

    def _resolved_prefill_assignment(self):
        assignment_id = (self.request.GET.get("assignment_id") or "").strip()
        if not assignment_id.isdigit():
            return None
        return authoring_assignment_queryset(
            self.request.user,
            include_all_periods=True,
        ).filter(id=int(assignment_id)).first()

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
        context["form"] = kwargs.get("form") or self._form()
        context["setup_prefill"] = setup_prefill
        context["prefill_assignment"] = assignment_obj
        context["imports"] = ExamDocumentImport.objects.filter(
            uploaded_by=self.request.user
        ).select_related("exam").order_by("-created_at")[:20]
        return context

    def post(self, request, *args, **kwargs):
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

        duration_minutes = setup_prefill.get("duration_minutes")
        max_attempts = setup_prefill.get("max_attempts")
        schedule_start = setup_prefill.get("schedule_start")
        schedule_end = setup_prefill.get("schedule_end")
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
            try:
                parsed = datetime.fromisoformat(schedule_start)
                exam.schedule_start = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
            except ValueError:
                exam.schedule_start = None
            updated_exam_fields.append("schedule_start")
        if schedule_end:
            try:
                parsed = datetime.fromisoformat(schedule_end)
                exam.schedule_end = timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
            except ValueError:
                exam.schedule_end = None
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
        return context

    def post(self, request, *args, **kwargs):
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
        return context

    def post(self, request, *args, **kwargs):
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
        return context

    def post(self, request, *args, **kwargs):
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


class CBTITActivationListView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_activation_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_day = _parse_schedule_day(self.request.GET.get("day"))
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
        filtered_exams = _apply_it_exam_filters(
            exams,
            class_id=selected_class_id,
            subject_id=selected_subject_id,
            teacher_id=selected_teacher_id,
        )

        context["approved_exams"] = sorted(
            [exam for exam in filtered_exams if exam.status in {CBTExamStatus.APPROVED, CBTExamStatus.PENDING_IT}],
            key=lambda exam: exam.updated_at,
            reverse=True,
        )
        context["active_exams"] = sorted(
            [exam for exam in filtered_exams if exam.status == CBTExamStatus.ACTIVE and exam_occurs_on_day(exam, selected_day)],
            key=_exam_schedule_sort_key,
        )
        context["closed_exams"] = sorted(
            [exam for exam in filtered_exams if exam.status == CBTExamStatus.CLOSED and exam_occurs_on_day(exam, selected_day)],
            key=_exam_schedule_sort_key,
            reverse=True,
        )[:50]
        context["class_options"] = _unique_exam_options(exams, "academic_class")
        context["subject_options"] = _unique_exam_options(exams, "subject")
        context["teacher_options"] = _unique_exam_options(exams, "created_by")
        context["selected_day"] = selected_day
        context["selected_day_value"] = selected_day.isoformat() if selected_day else ""
        context["selected_class_id"] = selected_class_id
        context["selected_subject_id"] = selected_subject_id
        context["selected_teacher_id"] = selected_teacher_id
        return context


class CBTITActivationDetailView(CBTITAccessMixin, TemplateView):
    template_name = "cbt/it_activation_detail.html"

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
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        total_attempt_count = self.exam.attempts.count()
        context["exam"] = self.exam
        context["exam_blueprint"] = getattr(self.exam, "blueprint", None)
        context["can_activate"] = self.exam.status == CBTExamStatus.APPROVED or (
            self.exam.is_free_test and self.exam.status == CBTExamStatus.PENDING_IT
        )
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
        context["builder_url"] = reverse("cbt:exam-builder", kwargs={"exam_id": self.exam.id})
        context["detail_url"] = reverse("cbt:exam-detail", kwargs={"exam_id": self.exam.id})
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        if action == "activate":
            form = ITExamActivationForm(exam=self.exam, data=request.POST)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(activation_form=form))
            form.save_blueprint()
            try:
                it_activate_exam(
                    exam=self.exam,
                    actor=request.user,
                    open_now=form.cleaned_data["open_now"],
                    is_time_based=form.cleaned_data["is_time_based"],
                    schedule_start=form.cleaned_data.get("schedule_start"),
                    schedule_end=form.cleaned_data.get("schedule_end"),
                    comment=form.cleaned_data.get("activation_comment", ""),
                )
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
            notify_cbt_schedule_published(exam=self.exam, actor=request.user, request=request)
            messages.success(request, "Exam activated successfully.")
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
        return has_any_role(self.request.user, CBT_MARKING_ROLES)


class CBTStudentExamListView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_exam_list.html"
    RECENT_WINDOW_HOURS = 24

    def _filter_value(self, key):
        return (self.request.GET.get(key) or "").strip()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject_id = self._filter_value("subject_id")
        exam_type = self._filter_value("exam_type")
        schedule_status = self._filter_value("status")
        recent_status = self._filter_value("recent_status")
        student = self.request.user
        student_profile = getattr(student, "student_profile", None)

        all_exam_rows = student_available_exams(self.request.user)
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
        recent_attempts = (
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class")
            .filter(student=self.request.user, updated_at__gte=recent_since)
            .order_by("-updated_at")
        )
        if subject_id.isdigit():
            recent_attempts = recent_attempts.filter(exam__subject_id=int(subject_id))
        if exam_type:
            recent_attempts = recent_attempts.filter(exam__exam_type=exam_type)
        if recent_status:
            recent_attempts = recent_attempts.filter(status=recent_status)

        subject_options = {}
        for row in all_exam_rows:
            subject_options[row["exam"].subject_id] = row["exam"].subject
        for attempt in recent_attempts[:20]:
            subject_options[attempt.exam.subject_id] = attempt.exam.subject

        setup_state = get_setup_state()
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


class CBTStudentAttemptRunView(CBTStudentAccessMixin, TemplateView):
    template_name = "cbt/student_attempt_run.html"

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        self.simulation_records = ensure_simulation_records_for_attempt(self.attempt)
        self.answers = ordered_attempt_answers(self.attempt)
        if not self.answers and not self.simulation_records:
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
        return bool(self.request.session.get(self._theory_stage_session_key(), False))

    def _active_index(self):
        if not self.answers:
            return 1
        raw_index = self.request.GET.get("q") or self.request.POST.get("q") or "1"
        try:
            value = int(raw_index)
        except (TypeError, ValueError):
            value = 1
        index = max(1, min(value, len(self.answers)))
        objective_count, theory_count = self._section_split_counts()
        if theory_count <= 0 or objective_count <= 0:
            return index
        if self._is_theory_stage_unlocked():
            return index
        if index > objective_count:
            if self.request.method == "POST":
                self.request.session[self._theory_stage_session_key()] = True
                return index
            return max(1, objective_count)
        return max(1, min(index, objective_count or index))

    def _answer_for_index(self, index):
        if not self.answers:
            return None
        return self.answers[index - 1]

    def _is_answered(self, answer):
        question = answer.exam_question.question
        if question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
            return answer.selected_options.exists()
        return bool((answer.response_text or "").strip() or answer.response_payload)

    def _option_entries(self, answer):
        if answer is None:
            return []
        selected_ids = set(answer.selected_options.values_list("id", flat=True))
        entries = []
        for option in option_list_for_attempt_answer(answer):
            entries.append(
                {
                    "id": option.id,
                    "label": option.label,
                    "text": option.option_text,
                    "selected": option.id in selected_ids,
                }
            )
        return entries

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

    def _save_current_answer(self, request, answer):
        if answer is None:
            return
        question = answer.exam_question.question
        blueprint = getattr(self.attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        theory_response_mode = (
            (section_config.get("theory_response_mode") or ExamCreateForm.THEORY_RESPONSE_MODE_PAPER)
            .strip()
            .upper()
        )
        if question.question_type in {CBTQuestionType.OBJECTIVE, CBTQuestionType.MULTI_SELECT}:
            selected_option_ids = request.POST.getlist("selected_options")
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
        stimulus_question = self._resolve_stimulus_question(active_question)
        active_question_text = (
            (getattr(active_question, "rich_stem", "") or getattr(active_question, "stem", ""))
            if active_question
            else ""
        )
        ordering_items = self._ordering_items(
            active_question,
            attempt_id=self.attempt.id,
            exam_question_id=active_answer.exam_question_id if active_answer else 0,
        )
        blueprint = getattr(self.attempt.exam, "blueprint", None)
        section_config = getattr(blueprint, "section_config", {}) if blueprint else {}
        if not isinstance(section_config, dict):
            section_config = {}
        calculator_mode = (section_config.get("calculator_mode") or "NONE").upper()
        theory_response_mode = (
            (section_config.get("theory_response_mode") or ExamCreateForm.THEORY_RESPONSE_MODE_PAPER)
            .strip()
            .upper()
        )
        objective_count, theory_count = self._section_split_counts()
        theory_stage_unlocked = self._is_theory_stage_unlocked()
        is_theory_page = index > objective_count if objective_count else False
        navigator = []
        for idx, answer in enumerate(self.answers, start=1):
            navigator.append(
                {
                    "index": idx,
                    "question_id": answer.exam_question_id,
                    "answered": self._is_answered(answer),
                    "flagged": answer.is_flagged,
                    "is_active": idx == index,
                }
            )
        question_panels = []
        for idx, answer in enumerate(self.answers, start=1):
            question = answer.exam_question.question
            question_text = (getattr(question, "rich_stem", "") or getattr(question, "stem", ""))
            question_stimulus = self._resolve_stimulus_question(question)
            question_panels.append(
                {
                    "index": idx,
                    "answer": answer,
                    "question": question,
                    "question_text": question_text,
                    "stimulus_question": question_stimulus,
                    "option_entries": self._option_entries(answer),
                    "ordering_items": self._ordering_items(
                        question,
                        attempt_id=self.attempt.id,
                        exam_question_id=answer.exam_question_id,
                    ),
                    "is_theory_page": bool(objective_count and idx > objective_count),
                    "is_active": idx == index,
                }
            )
        student_photo_url = ""
        try:
            student_profile = getattr(self.request.user, "student_profile", None)
            if student_profile and getattr(student_profile, "profile_photo", None):
                student_photo_url = student_profile.profile_photo.url
        except Exception:
            student_photo_url = ""
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
                "stimulus_question": stimulus_question,
                "ordering_items": ordering_items,
                "option_entries": self._option_entries(active_answer),
                "navigator": navigator,
                "remaining_seconds": self._remaining_seconds(),
                "question_count": len(self.answers),
                "objective_count": objective_count,
                "theory_count": theory_count,
                "theory_stage_unlocked": theory_stage_unlocked,
                "is_theory_page": is_theory_page,
                "is_last_objective_page": bool(objective_count and index == objective_count),
                "theory_response_mode": theory_response_mode,
                "calculator_mode": calculator_mode,
                "calculator_enabled": calculator_mode != "NONE",
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
                "has_question_flow": bool(self.answers),
                "show_simulation_tasks": bool(self.simulation_records) and not bool(self.answers),
                "lockdown_enabled": settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False),
                "lockdown_heartbeat_interval_seconds": settings.LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS,
                "lockdown_inactivity_timeout_seconds": settings.LOCKDOWN_INACTIVITY_TIMEOUT_SECONDS,
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "")
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        index = self._active_index()
        answer = self._answer_for_index(index)
        objective_count, theory_count = self._section_split_counts()

        if action in {"save_next", "save_prev", "save_stay", "submit", "move_to_theory", "jump"}:
            try:
                self._save_current_answer(request, answer)
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
            self.request.session[self._theory_stage_session_key()] = True
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
            save_attempt_answer(
                attempt=self.attempt,
                exam_question_id=answer.exam_question_id,
                is_flagged=not answer.is_flagged,
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
            jump_index = max(1, min(jump_index, len(self.answers)))
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
            next_index = min(len(self.answers), index + 1) if self.answers else 1
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
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
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

    def dispatch(self, request, *args, **kwargs):
        self.attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__subject", "exam__academic_class", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
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
        context.update(
            {
                "attempt": self.attempt,
                "exam": self.attempt.exam,
                "objective_rows": objective_rows,
                "theory_rows": theory_rows,
                "simulation_records": simulation_records,
                "has_question_results": has_question_results,
                "show_simulation_summary": bool(simulation_records) and not has_question_results,
            }
        )
        return context


class CBTTheoryMarkingListView(CBTMarkingAccessMixin, TemplateView):
    template_name = "cbt/theory_marking_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempts"] = theory_marking_queryset_for_user(self.request.user)[:120]
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
        return context

    def post(self, request, *args, **kwargs):
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
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        wrapper = self.record.exam_simulation.simulation_wrapper

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
        if not self.attempt.is_locked:
            if self.attempt.status == CBTAttemptStatus.IN_PROGRESS:
                return redirect("cbt:student-attempt-run", attempt_id=self.attempt.id)
            return redirect("cbt:student-attempt-result", attempt_id=self.attempt.id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["attempt"] = self.attempt
        context["exam"] = self.attempt.exam
        return context


class CBTAttemptHeartbeatView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return JsonResponse({"ok": True, "lockdown_enabled": False})
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
                    "redirect_url": reverse("cbt:student-attempt-locked", args=[attempt.id]),
                }
            )
        return JsonResponse({"ok": True, **result})


class CBTAttemptWarningView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return JsonResponse({"ok": True, "lockdown_enabled": False})
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            payload = {}
        event_type = (payload.get("event_type") or "").strip().upper()
        details = payload.get("details") or {}
        try:
            record_lockdown_warning(
                attempt=attempt,
                event_type=event_type,
                request=request,
                details=details,
            )
        except ValidationError as exc:
            return JsonResponse({"ok": False, "error": "; ".join(exc.messages)}, status=400)
        return JsonResponse({"ok": True, "warning_only": True})


class CBTAttemptViolationView(CBTStudentAccessMixin, View):
    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "exam__blueprint"),
            pk=kwargs["attempt_id"],
            student=request.user,
        )
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["locked_attempts"] = (
            ExamAttempt.objects.select_related(
                "exam",
                "exam__subject",
                "exam__academic_class",
                "student",
            )
            .filter(is_locked=True)
            .order_by("-locked_at")
        )
        context["lockdown_logs"] = (
            AuditEvent.objects.select_related("actor")
            .filter(category=AuditCategory.LOCKDOWN, event_type="LOCKDOWN_VIOLATION")
            .order_by("-created_at")[:200]
        )
        return context


class CBTITLockdownActionView(CBTITAccessMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam", "student"),
            pk=kwargs["attempt_id"],
        )
        action = (request.POST.get("action") or "").strip().lower()
        allow_resume = request.POST.get("allow_resume") == "on"
        extra_time_minutes = request.POST.get("extra_time_minutes") or "0"
        try:
            extra_time_value = int(extra_time_minutes)
        except (TypeError, ValueError):
            extra_time_value = 0

        if action == "unlock":
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
            messages.success(request, "Candidate lockdown updated.")
            return redirect("cbt:it-lockdown-dashboard")

        messages.error(request, "Invalid lockdown action.")
        return redirect("cbt:it-lockdown-dashboard")
