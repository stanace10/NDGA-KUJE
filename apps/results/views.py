import csv
import base64
import binascii
from decimal import Decimal
from http.cookiejar import CookieJar
import secrets
from urllib import error as url_error
from urllib import parse as url_parse
from urllib.parse import urlencode
from urllib import request as url_request
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.generic import RedirectView, TemplateView

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_HOSTEL_SUPERVISOR,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.permissions import has_any_role
from apps.accounts.models import User
from apps.accounts.models import StudentProfile
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    FormTeacherAssignment,
    GradeScale,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    Term,
    TeacherSubjectAssignment,
)
from apps.academics.grade_scale import grade_metadata_for_score, is_failing_grade
from apps.academics.term_policy import class_is_external_exam_class_for_term, exclude_external_exam_classes_for_term
from apps.academics.subject_policy import NON_RESULT_SUBJECT_CODES, exclude_non_result_subjects, subject_is_excluded_from_results
from apps.attendance.models import AttendanceRecord, SchoolCalendar
from apps.audit.services import log_results_approval, log_results_edit
from apps.cbt.models import (
    CBTAttemptStatus,
    CBTSimulationWrapperStatus,
    CBTExamStatus,
    CBTWritebackTarget,
    Exam,
    ExamAttempt,
    SimulationWrapper,
)
from apps.notifications.models import NotificationCategory
from apps.notifications.services import create_notification, extract_whatsapp_phones, notify_results_published, send_email_event, send_whatsapp_event
from apps.notifications.whatsapp_adapters import get_whatsapp_provider
from apps.pdfs.services import can_staff_download_term_report, school_logo_data_uri, school_profile as pdf_school_profile
from apps.results.entry_flow import (
    build_posted_score_bundle,
    decimal_value,
    read_sheet_policies_from_post,
    row_component_state,
    sheet_policy_state,
)
from apps.results.forms import (
    RejectActionForm,
    ResultActionForm,
    StudentSubjectScoreForm,
)
from apps.results.models import (
    BehaviorMetricSetting,
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultAccessPin,
    ResultSheet,
    ResultSheetStatus,
    ResultSubmission,
    StudentResultManagementStatus,
    StudentSubjectScore,
)
from apps.results.services import compute_grade_payload, compute_special_language_grade_payload
from apps.results.annual_subjects import annual_subject_label, build_annual_subject_slots, generic_annual_subject_label
from apps.results.utils import (
    RESULTS_STAGE7_ROLES,
    academic_context_is_current,
    active_term_edit_message,
    current_session_term,
    form_teacher_classes_for_user,
    principal_override_enabled,
    resolve_teacher_assignment_window,
    session_is_open_for_edits,
    sheet_is_editable_by_subject_owner,
)
from apps.setup_wizard.models import AcademicOperationWindow
from apps.setup_wizard.services import get_academic_window_state, get_setup_state, require_academic_window
from apps.results.workflow import (
    mark_compilation_approved_by_dean_final,
    mark_compilation_approved_by_vp,
    mark_compilation_published,
    mark_compilation_rejected_by_dean_final,
    mark_compilation_rejected_by_vp,
    mark_compilation_submitted_to_dean_final,
    mark_compilation_submitted_to_vp,
    transition_class_sheet_set,
    transition_result_sheet,
)
from apps.finance.models import FinanceInstitutionProfile, StudentCharge
from apps.finance.services import student_finance_overview
from apps.dashboard.forms import PrincipalSignatureForm, SchoolProfileForm
from apps.dashboard.models import PrincipalSignature, SchoolProfile
from apps.dashboard.intelligence import build_student_academic_analytics
from apps.results.analytics import (
    active_result_pin_for_student,
    build_award_listing,
    build_class_performance_snapshot,
    build_result_upload_statistics,
    build_student_performance_report,
    build_teacher_ranking,
)
from apps.results.cbt_policy import normalize_result_cbt_policies
from apps.tenancy.utils import cloud_staff_operations_lan_only_enabled, user_has_lan_only_operation_roles
from apps.results.insights import (
    build_advanced_result_comment_bundle,
    build_result_comment_bundle,
)
from apps.tenancy.utils import build_portal_url
from apps.finance.services import finance_sync_payload_signature, finance_sync_transport_payload
from apps.sync.model_sync import serialize_generic_model_instance
from core.manual_updates import (
    decode_manual_update_response,
    manual_update_remote_url,
    manual_update_token_values,
)


def _results_window_state_for(user):
    return get_academic_window_state(
        window_type=AcademicOperationWindow.WindowType.RESULTS,
        user=user,
    )


def _require_results_window(*, user, action_label):
    return require_academic_window(
        window_type=AcademicOperationWindow.WindowType.RESULTS,
        user=user,
        action_label=action_label,
    )


def _component_review_window_is_open(*, user, sheet, component_key):
    state = _component_window_state(component_key, user, sheet)
    return bool(state["is_open"] or state.get("is_bypassed_for_user"))


def _aggregate_dean_component_window_state(user):
    states = {
        key: get_academic_window_state(window_type=config["window_type"], user=user)
        for key, config in RESULT_COMPONENTS.items()
    }
    open_labels = [
        RESULT_COMPONENTS[key]["label"]
        for key, state in states.items()
        if state["is_open"] or state.get("is_bypassed_for_user")
    ]
    return {
        "label": "Dean Result Review Window",
        "status": "OPEN" if open_labels else "CLOSED",
        "is_open": bool(open_labels),
        "summary": (
            "Open for: " + ", ".join(open_labels)
            if open_labels
            else "No CA/exam component review window is currently open."
        ),
        "note": (
            "The Dean reviews the submitted component for each subject. "
            "The score sheet still shows CA1 through Exam for context."
        ),
    }


def _student_result_fee_lock(student, *, session, term):
    charges_exist = StudentCharge.objects.filter(
        session=session,
        is_active=True,
        term__in=[term, None],
    ).exists()
    if not charges_exist:
        return {"locked": False, "outstanding": Decimal("0.00")}
    overview = student_finance_overview(student=student, session=session, term=term)
    outstanding = overview.get("total_outstanding") or Decimal("0.00")
    return {"locked": outstanding > Decimal("0.00"), "outstanding": outstanding}


def _uses_legacy_result_layout(term):
    return bool(term and term.name in {"FIRST", "SECOND"})


def _uses_special_language_layout(subject_or_sheet):
    subject = getattr(subject_or_sheet, "subject", subject_or_sheet)
    return subject_is_excluded_from_results(subject)


def _cbt_window_state_for(user):
    return get_academic_window_state(
        window_type=AcademicOperationWindow.WindowType.CBT,
        user=user,
    )


RESULT_COMPONENTS = {
    "ca1": {
        "label": "CA1 Submit to Dean",
        "window_type": AcademicOperationWindow.WindowType.RESULT_CA1,
        "fields": ("ca1",),
    },
    "ca23": {
        "label": "CA2/CA3 Submit to Dean",
        "window_type": AcademicOperationWindow.WindowType.RESULT_CA23,
        "fields": ("ca2", "ca3"),
    },
    "ca4": {
        "label": "Assignment / CA4 Submit to Dean",
        "window_type": AcademicOperationWindow.WindowType.RESULT_CA4,
        "fields": ("ca4",),
    },
    "exam": {
        "label": "Overall Result",
        "window_type": AcademicOperationWindow.WindowType.RESULT_EXAM,
        "fields": ("objective", "theory"),
    },
}
RESULT_COMPONENT_PRIORITY = ("exam", "ca4", "ca23", "ca1")
COMPONENT_DRAFT = "DRAFT"
COMPONENT_SUBMITTED = "SUBMITTED_TO_DEAN"
COMPONENT_APPROVED = "APPROVED_BY_DEAN"
COMPONENT_REJECTED = "REJECTED_BY_DEAN"


def _sheet_emergency_window_state(sheet, component_key, user, *, at_time=None):
    if sheet is None:
        return None
    raw = sheet.cbt_component_policies if isinstance(sheet.cbt_component_policies, dict) else {}
    windows = raw.get("emergency_entry_windows")
    row = windows.get(component_key) if isinstance(windows, dict) else None
    if not isinstance(row, dict) or not row.get("is_enabled"):
        return None

    start_at = parse_datetime(str(row.get("start_at") or ""))
    end_at = parse_datetime(str(row.get("end_at") or ""))
    if start_at is None or end_at is None:
        return None
    if timezone.is_naive(start_at):
        start_at = timezone.make_aware(start_at, timezone.get_current_timezone())
    if timezone.is_naive(end_at):
        end_at = timezone.make_aware(end_at, timezone.get_current_timezone())
    current_time = at_time or timezone.now()
    status = "SCHEDULED" if current_time < start_at else "EXPIRED"
    is_open = start_at <= current_time <= end_at
    if is_open:
        status = "OPEN"
    label = f"{RESULT_COMPONENTS[component_key]['label']} emergency subject window"
    return {
        "window": None,
        "window_type": RESULT_COMPONENTS[component_key]["window_type"],
        "label": label,
        "status": status,
        "is_open": is_open,
        "summary": (
            f"{label} is open until {timezone.localtime(end_at):%d %b %Y %H:%M}."
            if is_open
            else f"{label} opens at {timezone.localtime(start_at):%d %b %Y %H:%M}."
            if status == "SCHEDULED"
            else f"{label} closed at {timezone.localtime(end_at):%d %b %Y %H:%M}."
        ),
        "start_at": timezone.localtime(start_at),
        "end_at": timezone.localtime(end_at),
        "note": str(row.get("note") or ""),
        "requires_window": True,
        "can_manage": False,
        "is_bypassed_for_user": False,
        "is_subject_override": True,
    }


def _component_window_state(component_key, user, sheet=None):
    config = RESULT_COMPONENTS[component_key]
    global_state = get_academic_window_state(window_type=config["window_type"], user=user)
    if global_state["is_open"] or global_state["is_bypassed_for_user"]:
        return global_state
    return _sheet_emergency_window_state(sheet, component_key, user) or global_state


def _component_window_states(user, sheet=None):
    return {key: _component_window_state(key, user, sheet) for key in RESULT_COMPONENTS}


def _open_component_keys(user, sheet=None):
    return {
        key
        for key, state in _component_window_states(user, sheet).items()
        if state["is_open"] or state["is_bypassed_for_user"]
    }


def _display_component_keys(user):
    active = _active_submission_component_key(user)
    return {active} if active else set()


def _active_submission_component_key(user, sheet=None):
    states = _component_window_states(user, sheet)
    for key in RESULT_COMPONENT_PRIORITY:
        state = states[key]
        if state["is_open"] or state["is_bypassed_for_user"]:
            return key
    for key in RESULT_COMPONENT_PRIORITY:
        if states[key]["status"] == "SCHEDULED":
            return key
    return None


def _show_component_on_teacher_page(component_key, review, display_keys):
    return component_key in display_keys or review["status"] != COMPONENT_DRAFT


def _sheet_review_state(sheet):
    raw = getattr(sheet, "cbt_component_policies", {}) or {}
    review = raw.get("review")
    return review if isinstance(review, dict) else {}


def _component_review(sheet, component_key):
    row = _sheet_review_state(sheet).get(component_key)
    if not isinstance(row, dict):
        return {"status": COMPONENT_DRAFT, "comment": ""}
    status = row.get("status") or COMPONENT_DRAFT
    if status not in {COMPONENT_DRAFT, COMPONENT_SUBMITTED, COMPONENT_APPROVED, COMPONENT_REJECTED}:
        status = COMPONENT_DRAFT
    return {**row, "status": status}


def _component_status_label(status):
    return {
        COMPONENT_DRAFT: "Draft",
        COMPONENT_SUBMITTED: "Submitted To Dean",
        COMPONENT_APPROVED: "Approved By Dean",
        COMPONENT_REJECTED: "Rejected By Dean",
    }.get(status, "Draft")


def _set_component_review(sheet, component_key, *, status, actor=None, comment=""):
    policies = dict(getattr(sheet, "cbt_component_policies", {}) or {})
    review = dict(policies.get("review") or {})
    now_text = timezone.now().isoformat()
    row = dict(review.get(component_key) or {})
    row.update({
        "status": status,
        "comment": comment or "",
        "actor_id": str(actor.id) if actor else "",
        "at": now_text,
    })
    review[component_key] = row
    policies["review"] = review
    sheet.cbt_component_policies = policies
    sheet.save(update_fields=["cbt_component_policies", "updated_at"])


def _component_is_locked_for_teacher(sheet, component_key):
    overall_status = _component_review(sheet, "exam")["status"]
    if overall_status in {COMPONENT_SUBMITTED, COMPONENT_APPROVED}:
        return True
    return _component_review(sheet, component_key)["status"] in {COMPONENT_SUBMITTED, COMPONENT_APPROVED}


def _overall_submission_prerequisites_met(sheet):
    return True


def _component_has_required_scores(score, policies, component_key):
    if score is None:
        return False
    if component_key == "ca1":
        if policies["ca1"]["enabled"]:
            return score.breakdown_value("ca1_objective") > DECIMAL_ZERO and score.breakdown_value("ca1_theory") > DECIMAL_ZERO
        return decimal_value(score.ca1) > DECIMAL_ZERO
    if component_key == "ca23":
        if policies["ca23"]["enabled"]:
            return decimal_value(score.ca2) > DECIMAL_ZERO and decimal_value(score.ca3) > DECIMAL_ZERO
        return decimal_value(score.ca2) > DECIMAL_ZERO or decimal_value(score.ca3) > DECIMAL_ZERO
    if component_key == "ca4":
        if policies["ca4"]["enabled"] and score.breakdown_value("ca4_objective") > DECIMAL_ZERO:
            return score.breakdown_value("ca4_theory") > DECIMAL_ZERO
        return decimal_value(score.ca4) > DECIMAL_ZERO
    if component_key == "exam":
        if policies["exam"]["enabled"]:
            exam_ready = decimal_value(score.objective) > DECIMAL_ZERO and decimal_value(score.theory) > DECIMAL_ZERO
        else:
            exam_ready = decimal_value(score.objective) > DECIMAL_ZERO or decimal_value(score.theory) > DECIMAL_ZERO
        return (
            _component_has_required_scores(score, policies, "ca1")
            and _component_has_required_scores(score, policies, "ca23")
            and _component_has_required_scores(score, policies, "ca4")
            and exam_ready
        )
    return False


def _component_missing_rows(sheet, enrollments, policies, component_key):
    scores = {
        row.student_id: row
        for row in StudentSubjectScore.objects.filter(
            result_sheet=sheet,
            student_id__in=[row.student_id for row in enrollments],
        )
    }
    missing = []
    for enrollment in enrollments:
        score = scores.get(enrollment.student_id)
        if not _component_has_required_scores(score, policies, component_key):
            missing.append(enrollment)
    return missing


def _sync_sheet_status_from_component_reviews(sheet):
    review = _sheet_review_state(sheet)
    overall_status = (review.get("exam") or {}).get("status", COMPONENT_DRAFT)
    if overall_status == COMPONENT_APPROVED:
        target = ResultSheetStatus.APPROVED_BY_DEAN
    elif overall_status == COMPONENT_REJECTED:
        target = ResultSheetStatus.REJECTED_BY_DEAN
    elif overall_status == COMPONENT_SUBMITTED:
        target = ResultSheetStatus.SUBMITTED_TO_DEAN
    else:
        statuses = {key: (review.get(key) or {}).get("status", COMPONENT_DRAFT) for key in ("ca1", "ca23", "ca4")}
        if any(status == COMPONENT_REJECTED for status in statuses.values()):
            target = ResultSheetStatus.REJECTED_BY_DEAN
        elif any(status == COMPONENT_SUBMITTED for status in statuses.values()):
            target = ResultSheetStatus.SUBMITTED_TO_DEAN
        else:
            target = ResultSheetStatus.DRAFT
    if sheet.status != target:
        sheet.status = target
        sheet.save(update_fields=["status", "updated_at"])
    if overall_status == COMPONENT_APPROVED and not subject_is_excluded_from_results(sheet.subject):
        _send_dean_approved_sheet_to_form_teachers(sheet)


def _get_or_create_sheet_from_assignment(assignment, actor):
    sheet, _ = ResultSheet.objects.get_or_create(
        academic_class=assignment.academic_class,
        subject=assignment.subject,
        session=assignment.session,
        term=assignment.term,
        defaults={"created_by": actor},
    )
    return sheet


def _score_snapshot(score):
    if score is None:
        return {}
    return {
        "ca1": str(score.ca1),
        "ca2": str(score.ca2),
        "ca3": str(score.ca3),
        "ca4": str(score.ca4),
        "class_participation": str(score.class_participation),
        "objective": str(score.objective),
        "theory": str(score.theory),
        "total_ca": str(score.total_ca),
        "total_exam": str(score.total_exam),
        "grand_total": str(score.grand_total),
        "grade": score.grade,
        "has_override": bool(score.has_override),
        "override_reason": score.override_reason or "",
    }


def _log_score_change(*, actor, request, score, sheet, before_snapshot, violations=None):
    after_snapshot = _score_snapshot(score)
    changed_fields = [
        key
        for key, new_value in after_snapshot.items()
        if before_snapshot.get(key) != new_value
    ]
    log_results_edit(
        actor=actor,
        request=request,
        metadata={
            "sheet_id": str(sheet.id),
            "student_id": str(score.student_id),
            "changed_fields": changed_fields,
            "before": before_snapshot,
            "after": after_snapshot,
            "violations": violations or {},
        },
    )


def _subject_enrollments_for_assignment(assignment):
    base_qs = StudentClassEnrollment.objects.select_related("student").filter(
        academic_class_id__in=_cohort_class_ids(assignment.academic_class),
        session=assignment.session,
        is_active=True,
    )
    subject_enrollment_qs = StudentSubjectEnrollment.objects.filter(
        session=assignment.session,
        subject=assignment.subject,
        is_active=True,
    )
    if subject_enrollment_qs.exists():
        student_ids = subject_enrollment_qs.values_list("student_id", flat=True)
        return base_qs.filter(student_id__in=student_ids)
    return base_qs


def _assignment_enrollments_with_sheet_scores(assignment, sheet=None):
    """Return normal subject enrollments plus historical score-only students.

    Current-term editing must stay tied to active enrollments. For imported
    first/second-term PDF history, however, some students are no longer active
    but still have valid result rows on the subject sheet. Those rows must
    remain visible in teacher/admin/dean read-only views so the imported term
    behaves like a native NDGA result, not a detached archive.
    """
    enrollments = list(_subject_enrollments_for_assignment(assignment))
    if sheet is None or academic_context_is_current(assignment.session_id, assignment.term_id):
        return enrollments

    seen_student_ids = {row.student_id for row in enrollments}
    extra_student_ids = list(
        StudentSubjectScore.objects.filter(result_sheet=sheet)
        .exclude(student_id__in=seen_student_ids)
        .values_list("student_id", flat=True)
        .distinct()
    )
    if not extra_student_ids:
        return enrollments

    extra_enrollments = list(
        StudentClassEnrollment.objects.select_related("student", "student__student_profile")
        .filter(
            academic_class_id__in=_cohort_class_ids(assignment.academic_class),
            session=assignment.session,
            student_id__in=extra_student_ids,
        )
    )
    enrollments.extend(extra_enrollments)
    return sorted(
        enrollments,
        key=lambda row: (
            (row.student.first_name or "").casefold(),
            (row.student.last_name or "").casefold(),
            (getattr(getattr(row.student, "student_profile", None), "middle_name", "") or "").casefold(),
            getattr(getattr(row.student, "student_profile", None), "student_number", "") or "",
            row.student.username or "",
        ),
    )


def request_user_can_edit_session(user, session):
    if user.has_role(ROLE_IT_MANAGER):
        return True
    return session_is_open_for_edits(session)


def _admission_number_for_student(student):
    profile = getattr(student, "student_profile", None)
    if not profile:
        return "-"
    return profile.student_number or "-"


def _instructional_class(academic_class):
    return academic_class.instructional_class if academic_class else None


FIXED_CLASS_SUBJECT_COUNTS = {
    "JS1": 16,
    "JS2": 17,
    "SS1": 14,
    "SS2": 13,
}

HISTORICAL_TERM_CLASS_SUBJECT_COUNTS = {
    ("2025/2026", "FIRST", "JS1"): 18,
}


def _fixed_subject_count_for_class(academic_class, *, session=None, term=None):
    if academic_class is None:
        return None
    instructional = _instructional_class(academic_class)
    code = (getattr(instructional, "code", "") or "").strip().upper()
    session_name = (getattr(session, "name", "") or "").strip()
    term_name = (getattr(term, "name", "") or "").strip().upper()
    historical_count = HISTORICAL_TERM_CLASS_SUBJECT_COUNTS.get((session_name, term_name, code))
    if historical_count:
        return historical_count
    return FIXED_CLASS_SUBJECT_COUNTS.get(code)


def _cohort_class_ids(academic_class):
    if not academic_class:
        return []
    return academic_class.cohort_class_ids()


def _send_dean_approved_sheet_to_form_teachers(sheet):
    """Materialize the form-teacher queue automatically after Dean approval."""
    assignments = FormTeacherAssignment.objects.select_related("teacher", "academic_class").filter(
        session=sheet.session,
        academic_class_id__in=_cohort_class_ids(sheet.academic_class),
        is_active=True,
    )
    for assignment in assignments:
        compilation, _created = ClassResultCompilation.objects.get_or_create(
            academic_class=assignment.academic_class,
            session=sheet.session,
            term=sheet.term,
            defaults={
                "form_teacher": assignment.teacher,
                "status": ClassCompilationStatus.DRAFT,
            },
        )
        if compilation.form_teacher_id != assignment.teacher_id:
            compilation.form_teacher = assignment.teacher
            compilation.save(update_fields=["form_teacher", "updated_at"])


def _pending_dean_subject_names(compilation):
    instructional_class = _instructional_class(compilation.academic_class)
    assignments = TeacherSubjectAssignment.objects.filter(
        academic_class=instructional_class,
        session=compilation.session,
        term=compilation.term,
        is_active=True,
    ).select_related("subject")
    assignments = exclude_non_result_subjects(assignments, field_name="subject")
    sheet_statuses = dict(
        ResultSheet.objects.filter(
            academic_class=instructional_class,
            session=compilation.session,
            term=compilation.term,
        ).values_list("subject_id", "status")
    )
    return [
        row.subject.name
        for row in assignments
        if sheet_statuses.get(row.subject_id) != ResultSheetStatus.APPROVED_BY_DEAN
    ]


def _report_class_options():
    return AcademicClass.objects.filter(is_active=True).select_related("base_class").order_by("code")


def _selected_report_class(request):
    raw_class_id = (request.GET.get("class_id") or "").strip()
    if not raw_class_id.isdigit():
        return None
    return _report_class_options().filter(pk=int(raw_class_id)).first()


def _report_level_options():
    return AcademicClass.objects.filter(is_active=True, base_class__isnull=True).order_by("code")


def _report_arm_options():
    return AcademicClass.objects.filter(is_active=True, base_class__isnull=False).select_related("base_class").order_by(
        "base_class__code", "arm_name", "code"
    )


def _selected_report_level(request):
    raw_level_id = (request.GET.get("level_id") or "").strip()
    if not raw_level_id.isdigit():
        return None
    return _report_level_options().filter(pk=int(raw_level_id)).first()


def _selected_report_arm(request):
    raw_arm_id = (request.GET.get("arm_id") or "").strip()
    if not raw_arm_id.isdigit():
        return None
    return _report_arm_options().filter(pk=int(raw_arm_id)).first()


RESULT_SHARE_ROLES = {
    ROLE_IT_MANAGER,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_PRINCIPAL,
    ROLE_VP,
    ROLE_BURSAR,
}


RESULT_SHARE_OVERSIGHT_ROLES = {
    ROLE_IT_MANAGER,
    ROLE_DEAN,
    ROLE_PRINCIPAL,
    ROLE_VP,
    ROLE_BURSAR,
}


def _result_share_base_queryset(*, user, session=None, term=None):
    records = ClassResultStudentRecord.objects.select_related(
        "student",
        "student__student_profile",
        "compilation",
        "compilation__academic_class",
        "compilation__session",
        "compilation__term",
    ).filter(compilation__status=ClassCompilationStatus.PUBLISHED)
    if session is not None:
        records = records.filter(compilation__session=session)
    if term is not None:
        records = records.filter(compilation__term=term)
    if has_any_role(user, RESULT_SHARE_OVERSIGHT_ROLES):
        return records
    if user.has_role(ROLE_FORM_TEACHER):
        class_ids = list(
            form_teacher_classes_for_user(user, session=session).values_list("academic_class_id", flat=True)
        )
        if not class_ids:
            return records.none()
        return records.filter(compilation__academic_class_id__in=class_ids)
    return records.none()


def _result_share_class_options(*, user, session=None, term=None):
    class_ids = list(
        _result_share_base_queryset(user=user, session=session, term=term)
        .values_list("compilation__academic_class_id", flat=True)
        .distinct()
    )
    return _report_class_options().filter(id__in=class_ids)


def _selected_result_share_class(request, *, user, session=None, term=None):
    raw_class_id = (request.GET.get("class_id") or "").strip()
    if not raw_class_id.isdigit():
        return None
    return _result_share_class_options(user=user, session=session, term=term).filter(pk=int(raw_class_id)).first()


def _class_result_cloud_endpoint_configured():
    return bool(manual_update_remote_url("/ops/manual-import/updates/") and manual_update_token_values())


def _manual_update_csrf_context(endpoint):
    parsed_endpoint = url_parse.urlparse(endpoint)
    origin = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}" if parsed_endpoint.scheme and parsed_endpoint.netloc else ""
    cookie_jar = CookieJar()
    opener = url_request.build_opener(url_request.HTTPCookieProcessor(cookie_jar))
    csrf_token = ""
    if origin:
        try:
            with opener.open(f"{origin}/auth/login/", timeout=20) as response:
                response.read(2048)
        except Exception:
            pass
        for cookie in cookie_jar:
            if cookie.name == "csrftoken":
                csrf_token = cookie.value
                break
    return opener, csrf_token, origin


def _post_manual_update_payload(*, endpoint, token, payload, timeout=90, opener=None, csrf_token="", origin=""):
    raw_body = finance_sync_transport_payload(payload)
    request_obj = url_request.Request(endpoint, method="POST", data=raw_body)
    request_obj.add_header("Content-Type", "application/json")
    request_obj.add_header("X-NDGA-Manual-Update-Token", token)
    if not origin:
        parsed_endpoint = url_parse.urlparse(endpoint)
        origin = f"{parsed_endpoint.scheme}://{parsed_endpoint.netloc}" if parsed_endpoint.scheme and parsed_endpoint.netloc else ""
    if origin:
        request_obj.add_header("Origin", origin)
        request_obj.add_header("Referer", endpoint)
    if csrf_token:
        request_obj.add_header("X-CSRFToken", csrf_token)
    signature = finance_sync_payload_signature(raw_body)
    if signature:
        request_obj.add_header("X-NDGA-Payload-Signature", signature)
    transport = opener or url_request
    with transport.open(request_obj, timeout=timeout) as response:
        return raw_body, decode_manual_update_response(raw_body=response.read(), headers=response.headers)


def _chunk_manual_update_items(*, channels, items, max_raw_bytes=600_000):
    chunks = []
    current = []
    for item in items:
        candidate = [*current, item]
        payload = {
            "channels": channels,
            "count": len(candidate),
            "latest_timestamp": "",
            "generated_at": timezone.now().isoformat(),
            "items": candidate,
        }
        if current and len(finance_sync_transport_payload(payload)) > max_raw_bytes:
            chunks.append(current)
            current = [item]
            continue
        current = candidate
    if current:
        chunks.append(current)
    return chunks


def _push_manual_update_items_to_cloud(*, endpoint, token, channels, items, opener=None, csrf_token="", origin=""):
    imported = 0
    skipped = 0
    sent = 0
    request_count = 0
    for chunk in _chunk_manual_update_items(channels=channels, items=items):
        payload = {
            "channels": channels,
            "count": len(chunk),
            "latest_timestamp": "",
            "generated_at": timezone.now().isoformat(),
            "items": chunk,
        }
        _, result = _post_manual_update_payload(
            endpoint=endpoint,
            token=token,
            payload=payload,
            opener=opener,
            csrf_token=csrf_token,
            origin=origin,
        )
        errors = result.get("errors") or []
        if errors:
            raise ValidationError("Cloud accepted the request but reported errors: " + "; ".join(errors[:5]))
        request_count += 1
        sent += len(chunk)
        imported += int(result.get("count", 0) or 0)
        skipped += int(result.get("skipped", 0) or 0)
    return {
        "sent": sent,
        "imported": imported,
        "skipped": skipped,
        "requests": request_count,
    }


def _push_class_result_to_cloud_once(*, compilation):
    endpoint = manual_update_remote_url("/ops/manual-import/updates/")
    if not endpoint:
        raise ValidationError("Cloud manual update endpoint is not configured.")
    token = next(iter(manual_update_token_values()), "")
    if not token:
        raise ValidationError("Cloud manual update token is not configured.")

    student_ids = list(
        ClassResultStudentRecord.objects.filter(compilation=compilation)
        .values_list("student_id", flat=True)
        .distinct()
    )
    if not student_ids:
        raise ValidationError("No student result records exist for this class result.")

    instructional_class = _instructional_class(compilation.academic_class)
    sheets_qs = ResultSheet.objects.filter(
        academic_class=instructional_class,
        session=compilation.session,
        term=compilation.term,
        status=ResultSheetStatus.PUBLISHED,
    )
    sheet_ids = list(sheets_qs.values_list("id", flat=True))
    subject_ids = list(sheets_qs.values_list("subject_id", flat=True).distinct())
    class_ids = {instructional_class.id, compilation.academic_class_id}
    calendar = SchoolCalendar.objects.filter(
        session=compilation.session,
        term=compilation.term,
    ).first()

    ordered_querysets = [
        AcademicSession.objects.filter(pk=compilation.session_id),
        Term.objects.filter(pk=compilation.term_id),
        AcademicClass.objects.filter(pk__in=class_ids),
        Subject.objects.filter(pk__in=subject_ids),
        User.objects.filter(id__in=student_ids),
        StudentProfile.objects.filter(user_id__in=student_ids),
        StudentClassEnrollment.objects.filter(session=compilation.session, student_id__in=student_ids),
        sheets_qs,
        StudentSubjectScore.objects.filter(result_sheet_id__in=sheet_ids, student_id__in=student_ids),
        ClassResultCompilation.objects.filter(pk=compilation.pk),
        ClassResultStudentRecord.objects.filter(compilation=compilation, student_id__in=student_ids),
        ResultAccessPin.objects.filter(session=compilation.session, term=compilation.term, student_id__in=student_ids),
    ]
    if calendar is not None:
        ordered_querysets.append(
            AttendanceRecord.objects.filter(calendar=calendar, student_id__in=student_ids)
        )

    items = []
    seen = set()
    latest_timestamp = None
    for queryset in ordered_querysets:
        for instance in queryset:
            model_label = instance._meta.label_lower
            key = (model_label, instance.pk)
            if key in seen:
                continue
            seen.add(key)
            item = serialize_generic_model_instance(instance)
            if model_label == "accounts.studentprofile":
                profile_photo = (item.get("fields") or {}).get("profile_photo")
                if isinstance(profile_photo, dict) and profile_photo.get("data_url"):
                    profile_photo["data_url"] = ""
            items.append(item)
            instance_updated_at = getattr(instance, "updated_at", None) or getattr(instance, "created_at", None)
            if instance_updated_at and (latest_timestamp is None or instance_updated_at > latest_timestamp):
                latest_timestamp = instance_updated_at

    final_models = {"results.classresultcompilation", "results.classresultstudentrecord"}
    pre_publish_items = [item for item in items if item.get("model") not in final_models]
    final_visibility_items = [item for item in items if item.get("model") in final_models]

    try:
        opener, csrf_token, origin = _manual_update_csrf_context(endpoint)
        pre_result = _push_manual_update_items_to_cloud(
            endpoint=endpoint,
            token=token,
            channels=["academics", "students", "results", "attendance"],
            items=pre_publish_items,
            opener=opener,
            csrf_token=csrf_token,
            origin=origin,
        )
        final_result = _push_manual_update_items_to_cloud(
            endpoint=endpoint,
            token=token,
            channels=["academics", "students", "results", "attendance"],
            items=final_visibility_items,
            opener=opener,
            csrf_token=csrf_token,
            origin=origin,
        )
    except (url_error.URLError, ValidationError, ValueError) as exc:
        raise ValidationError(f"Unable to push selected class result to cloud: {exc}") from exc
    return {
        "sent": len(items),
        "imported": pre_result["imported"] + final_result["imported"],
        "skipped": pre_result["skipped"] + final_result["skipped"],
        "requests": pre_result["requests"] + final_result["requests"],
        "student_count": len(student_ids),
    }


def _guardian_email_list(student):
    emails = []
    seen = set()
    profile = getattr(student, "student_profile", None)
    for value in [getattr(profile, "guardian_email", ""), student.email]:
        clean = (value or "").strip().lower()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        emails.append(clean)
    return emails


def _student_result_center_url(*, request, compilation):
    return build_portal_url(
        request,
        "student",
        reverse("pdfs:student-reports"),
        query={
            "session_id": compilation.session_id,
            "term_id": compilation.term_id,
        },
    )


def _result_pin_state(*, student, compilation):
    school_profile = SchoolProfile.load()
    if not school_profile.require_result_access_pin:
        return {"label": "Disabled", "is_active": True}
    active_pin = active_result_pin_for_student(
        student=student,
        session=compilation.session,
        term=compilation.term,
    )
    if active_pin is None:
        return {"label": "Missing", "is_active": False}
    return {"label": "Issued", "is_active": True}


def _build_result_share_message(*, student, compilation, portal_url, pin_state):
    school_profile = SchoolProfile.load()
    class_label = compilation.academic_class.display_name or compilation.academic_class.code
    student_name = student.get_full_name() or student.username
    login_url = "https://student.ndgakuje.org/auth/login/?audience=student"
    lines = [
        (
            f"The {compilation.term.get_name_display()} result for {student_name} "
            f"for the {compilation.session.name} academic session is now available."
        ),
        f"Ward Name: {student_name}",
        f"Class: {class_label}",
        f"Student portal login: {login_url}",
        f"Result link: {portal_url}",
        "Official report and performance PDFs are available in the portal.",
    ]
    if pin_state.get("label") == "Issued":
        lines.append("Please use the issued result access PIN if the portal prompts for it.")
    elif pin_state.get("label") == "Missing":
        lines.append("Result access PIN is enabled, but no PIN has been issued yet.")
    lines.append("Thank you for your continued support of your child's learning.")
    return "\n".join(lines)


def _build_result_share_row(*, request, record):
    student = record.student
    compilation = record.compilation
    profile = getattr(student, "student_profile", None)
    guardian_phone = getattr(profile, "guardian_phone", "") if profile else ""
    whatsapp_numbers = extract_whatsapp_phones(guardian_phone)
    whatsapp_phone = whatsapp_numbers[0] if whatsapp_numbers else ""
    pin_state = _result_pin_state(student=student, compilation=compilation)
    portal_url = _student_result_center_url(request=request, compilation=compilation)
    share_message = _build_result_share_message(
        student=student,
        compilation=compilation,
        portal_url=portal_url,
        pin_state=pin_state,
    )
    whatsapp_url = ""
    if whatsapp_phone:
        whatsapp_url = f"https://wa.me/{whatsapp_phone}?{urlencode({'text': share_message})}"
    fee_lock = _student_result_fee_lock(student, session=compilation.session, term=compilation.term)
    email_targets = [] if fee_lock["locked"] else _guardian_email_list(student)
    if fee_lock["locked"]:
        whatsapp_url = ""
        whatsapp_numbers = []
    return {
        "student": student,
        "compilation": compilation,
        "student_name": student.get_full_name() or student.username,
        "student_number": _admission_number_for_student(student),
        "class_name": compilation.academic_class.display_name or compilation.academic_class.code,
        "guardian_email": getattr(profile, "guardian_email", "") if profile else "",
        "guardian_phone": guardian_phone,
        "whatsapp_phone": whatsapp_phone,
        "whatsapp_numbers": whatsapp_numbers,
        "email_targets": email_targets,
        "pin_state": pin_state,
        "fee_locked": fee_lock["locked"],
        "fee_outstanding": fee_lock["outstanding"],
        "portal_url": portal_url,
        "whatsapp_url": whatsapp_url,
        "report_pdf_url": reverse(
            "pdfs:staff-term-report-download",
            kwargs={"compilation_id": compilation.id, "student_id": student.id},
        ),
        "performance_pdf_url": reverse(
            "pdfs:staff-performance-analysis-download",
            kwargs={"compilation_id": compilation.id, "student_id": student.id},
        ),
        "cumulative_pdf_url": cumulative_pdf_url,
    }


def _average_to_decimal(total, count):
    if not count:
        return Decimal("0.00")
    return (Decimal(total) / Decimal(count)).quantize(Decimal("0.01"))


def _score_decimal(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _grade_tone_for_score(score):
    meta = grade_metadata_for_score(score)
    color = str(meta.get("color") or "").strip().lower()
    hex_color = {
        "gold": "#b7791f",
        "silver": "#6b7280",
        "bronze": "#b45309",
        "black": "#111827",
        "green": "#047857",
        "blue": "#1d4ed8",
        "orange": "#ea580c",
        "red": "#b91c1c",
    }.get(color, "#111827")
    return {
        "grade_color": meta.get("color") or "Black",
        "grade_css_class": meta.get("css_class") or "legend-dark",
        "grade_hex_color": hex_color,
        "remark": meta.get("remark") or "",
    }


def _nullable_decimal_from_post(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.1"))
    except Exception:
        return None


def _publish_allowed_for_actor(*, actor, compilation):
    if not actor.has_role(ROLE_IT_MANAGER):
        return False
    if compilation.status == ClassCompilationStatus.PUBLISHED:
        return False
    if compilation.status != ClassCompilationStatus.APPROVED_BY_VP:
        return False
    student_ids = StudentClassEnrollment.objects.filter(
        academic_class_id__in=_cohort_class_ids(compilation.academic_class),
        session=compilation.session,
        is_active=True,
    ).values_list("student_id", flat=True)
    records = compilation.student_records.filter(student_id__in=student_ids)
    return bool(
        student_ids
        and records.count() == student_ids.count()
        and not records.exclude(management_status=StudentResultManagementStatus.REVIEWED).exists()
        and not records.filter(principal_comment="").exists()
    )


def _vp_approval_allowed(*, actor, compilation):
    if not actor.has_role(ROLE_VP):
        return False
    if compilation.status != ClassCompilationStatus.SUBMITTED_TO_VP:
        return False
    student_ids = StudentClassEnrollment.objects.filter(
        academic_class_id__in=_cohort_class_ids(compilation.academic_class),
        session=compilation.session,
        is_active=True,
    ).values_list("student_id", flat=True)
    records = compilation.student_records.filter(student_id__in=student_ids)
    return bool(
        student_ids
        and records.count() == student_ids.count()
        and not records.exclude(management_status=StudentResultManagementStatus.REVIEWED).exists()
        and not records.filter(principal_comment="").exists()
    )


def _reject_allowed_for_actor(*, actor, compilation):
    return actor.has_role(ROLE_VP) and compilation.status == ClassCompilationStatus.SUBMITTED_TO_VP


def _ensure_class_compilation_rows(*, session, term, class_qs):
    if not session or not term:
        return {}
    class_list = list(class_qs)
    if not class_list:
        return {}
    existing = {
        row.academic_class_id: row
        for row in ClassResultCompilation.objects.select_related(
            "academic_class",
            "session",
            "term",
            "form_teacher",
            "vp_actor",
            "principal_override_actor",
        ).filter(
            session=session,
            term=term,
            academic_class_id__in=[row.id for row in class_list],
        )
    }
    missing = [row for row in class_list if row.id not in existing]
    if missing:
        assignment_map = {
            row.academic_class_id: row
            for row in FormTeacherAssignment.objects.select_related("teacher").filter(
                session=session,
                is_active=True,
                academic_class_id__in=[row.id for row in missing],
            )
        }
        for academic_class in missing:
            assignment = assignment_map.get(academic_class.id)
            compilation, _created = ClassResultCompilation.objects.get_or_create(
                academic_class=academic_class,
                session=session,
                term=term,
                defaults={
                    "form_teacher": assignment.teacher if assignment else None,
                    "status": ClassCompilationStatus.DRAFT,
                },
            )
            existing[academic_class.id] = compilation
    return existing


def _subject_rows_for_student(*, compilation, student):
    legacy_layout = _uses_legacy_result_layout(compilation.term)
    sheet_queryset = ResultSheet.objects.filter(
        academic_class=_instructional_class(compilation.academic_class),
        session=compilation.session,
        term=compilation.term,
    )
    sheet_queryset = exclude_non_result_subjects(sheet_queryset, field_name="subject")
    sheets = list(
        sheet_queryset
        .select_related("subject")
        .order_by("subject__name")
    )
    score_map = {
        row.result_sheet_id: row
        for row in StudentSubjectScore.objects.filter(
            result_sheet_id__in=[sheet.id for sheet in sheets],
            student=student,
        )
    }
    rows = []
    for sheet in sheets:
        score = score_map.get(sheet.id)
        if not score:
            continue
        grade_tone = _grade_tone_for_score(score.grand_total)
        rows.append(
            {
                "subject": sheet.subject,
                "sheet_status": sheet.status,
                "use_legacy_result_layout": legacy_layout,
                "ca1": _score_decimal(score.ca1),
                "ca2": _score_decimal(score.ca2),
                "ca3": _score_decimal(score.ca3),
                "ca4": _score_decimal(score.ca4),
                "class_participation": _score_decimal(score.class_participation),
                "objective": _score_decimal(score.objective),
                "theory": _score_decimal(score.theory),
                "exam_total": _score_decimal(score.total_exam if legacy_layout else Decimal(score.objective or 0) + Decimal(score.theory or 0)),
                "grand_total": _score_decimal(score.grand_total),
                "grade": score.grade or "-",
                **grade_tone,
            }
        )
    return rows


def _student_result_payload_for_compilation(*, compilation, student):
    subject_rows = _subject_rows_for_student(compilation=compilation, student=student)
    actual_subject_count = len(subject_rows)
    subject_count = actual_subject_count
    cumulative_total = sum((row["grand_total"] for row in subject_rows), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    average_score = _average_to_decimal(cumulative_total, subject_count)
    record = ClassResultStudentRecord.objects.filter(
        compilation=compilation,
        student=student,
    ).first()
    profile = getattr(student, "student_profile", None)
    analytics = build_student_academic_analytics(
        student=student,
        current_session=compilation.session,
        current_term=compilation.term,
    )
    weak_subjects = [row["subject"] for row in analytics.get("weak_subjects", [])]
    comment_bundle = _build_comment_bundle(
        student_name=student.get_full_name() or student.username,
        average_score=average_score,
        fail_count=len([row for row in subject_rows if is_failing_grade(row.get("grade"))]),
        attendance_percentage=_score_decimal(record.attendance_percentage if record else 0),
        weak_subjects=weak_subjects,
        predicted_score=(analytics.get("prediction") or {}).get("score"),
        risk_label=(analytics.get("risk") or {}).get("label"),
    )
    principal_comment = (
        (getattr(record, "principal_comment", "") or "").strip()
        or (getattr(compilation, "decision_comment", "") or "").strip()
        or comment_bundle["principal_comment"]
    )
    return {
        "student": student,
        "student_number": profile.student_number if profile else student.username,
        "class_code": compilation.academic_class.display_name or compilation.academic_class.code,
        "session_name": compilation.session.name,
        "term_name": compilation.term.get_name_display(),
        "compilation_status": compilation.get_status_display(),
        "subject_rows": subject_rows,
        "use_legacy_result_layout": _uses_legacy_result_layout(compilation.term),
        "subject_count": subject_count,
        "actual_subject_count": actual_subject_count,
        "cumulative_total": cumulative_total,
        "average_score": average_score,
        "attendance_percentage": _score_decimal(record.attendance_percentage if record else 0),
        "behavior_rating": record.behavior_rating if record else 3,
        "behavior_rows": _behavior_metric_rows(record) if record else [],
        "teacher_comment": record.teacher_comment if record else "",
        "principal_comment": principal_comment,
        "management_status": record.get_management_status_display() if record else "Pending Review",
        "management_comment": getattr(record, "management_comment", "") if record else "",
        "analytics": analytics,
        "comment_bundle": comment_bundle,
    }


def _build_comment_bundle(*, student_name, average_score, fail_count, attendance_percentage, weak_subjects=None, predicted_score=None, risk_label=None, strongest_subjects=None, behavior_breakdown=None):
    fallback_risk = risk_label or ("High" if (float(attendance_percentage or 0) < 60 or int(fail_count or 0) >= 2) else "Low")
    return build_result_comment_bundle(
        student_name=student_name,
        average_score=average_score,
        attendance_percentage=attendance_percentage,
        fail_count=fail_count,
        weak_subjects=weak_subjects or [],
        strongest_subjects=strongest_subjects or [],
        predicted_score=predicted_score,
        risk_label=fallback_risk,
        behavior_breakdown=behavior_breakdown or {},
    )


def _generate_comment_suggestion(*, average_score, fail_count, attendance_percentage, student_name="This student", weak_subjects=None, predicted_score=None, risk_label=None):
    return _build_comment_bundle(
        student_name=student_name,
        average_score=average_score,
        fail_count=fail_count,
        attendance_percentage=attendance_percentage,
        weak_subjects=weak_subjects,
        predicted_score=predicted_score,
        risk_label=risk_label,
    )["teacher_comment"]


DEFAULT_BEHAVIOR_METRIC_FIELDS = (
    ("discipline", "Discipline"),
    ("punctuality", "Punctuality"),
    ("respect", "Respect & Courtesy"),
    ("leadership", "Leadership"),
    ("sports", "Sports & Teamwork"),
    ("neatness", "Neatness"),
    ("participation", "Class Participation"),
)


def _behavior_metric_fields():
    rows = list(
        BehaviorMetricSetting.objects.filter(is_active=True)
        .order_by("sort_order", "label")
        .values_list("code", "label")
    )
    return rows or list(DEFAULT_BEHAVIOR_METRIC_FIELDS)


def _behavior_metric_rows(record):
    breakdown = getattr(record, "behavior_breakdown", {}) or {}
    rows = []
    for code, label in _behavior_metric_fields():
        value = breakdown.get(code)
        rows.append(
            {
                "code": code,
                "label": label,
                "value": value if value not in (None, "") else "-",
            }
        )
    return rows


def _default_behavior_breakdown(*, seed=3):
    try:
        seed_value = int(seed)
    except (TypeError, ValueError):
        seed_value = 3
    seed_value = max(1, min(5, seed_value))
    return {code: seed_value for code, _ in _behavior_metric_fields()}


def _normalize_behavior_breakdown(payload, *, seed=3):
    normalized = _default_behavior_breakdown(seed=seed)
    if not isinstance(payload, dict):
        return normalized
    for code, _ in _behavior_metric_fields():
        try:
            value = int(payload.get(code, normalized[code]))
        except (TypeError, ValueError):
            value = normalized[code]
        normalized[code] = max(1, min(5, value))
    return normalized


def _behavior_average_rating(breakdown):
    if not breakdown:
        return 3
    total = sum(int(value) for value in breakdown.values())
    avg = total / len(breakdown)
    return max(1, min(5, int(round(avg))))


class ResultsAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = RESULTS_STAGE7_ROLES

    def test_func(self):
        return has_any_role(self.request.user, self.allowed_roles)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["role_codes"] = sorted(self.request.user.get_all_role_codes())
        context["result_window"] = _results_window_state_for(self.request.user)
        return context


class GradeEntryHomeView(ResultsAccessMixin, TemplateView):
    template_name = "results/grade_entry_home.html"

    def _window(self):
        return resolve_teacher_assignment_window(
            self.request.user,
            requested_session_id=(self.request.GET.get("session_id") or "").strip(),
            requested_term_id=(self.request.GET.get("term_id") or "").strip(),
        )

    @staticmethod
    def _build_filter_query(*, selected_session, selected_term):
        query = {}
        if selected_session:
            query["session_id"] = selected_session.id
        if selected_term:
            query["term_id"] = selected_term.id
        return urlencode(query)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        window = self._window()
        assignments = list(
            window["assignments"].order_by(
                "academic_class__code",
                "subject__name",
            )
        )
        filter_query = self._build_filter_query(
            selected_session=window["selected_session"],
            selected_term=window["selected_term"],
        )
        class_rows = []
        seen_class_ids = set()
        for assignment in assignments:
            class_id = assignment.academic_class_id
            if class_id in seen_class_ids:
                continue
            seen_class_ids.add(class_id)
            class_assignments = [row for row in assignments if row.academic_class_id == class_id]
            class_rows.append(
                {
                    "academic_class": assignment.academic_class,
                    "subject_count": len(class_assignments),
                    "url": (
                        reverse(
                        "results:grade-entry-class-subjects",
                        kwargs={"class_id": class_id},
                        )
                        + (f"?{filter_query}" if filter_query else "")
                    ),
                }
            )
        context["class_rows"] = class_rows
        context["current_session"] = window["selected_session"]
        context["current_term"] = window["selected_term"]
        context["available_sessions"] = window["available_sessions"]
        context["available_terms"] = window["available_terms"]
        context["selected_session"] = window["selected_session"]
        context["selected_term"] = window["selected_term"]
        context["filter_query"] = filter_query
        context["term_edit_locked"] = getattr(self.request, "term_edit_locked", False)
        context["term_edit_lock_message"] = getattr(self.request, "term_edit_lock_message", "")
        context["can_access_dean_term_review"] = has_any_role(self.request.user, {ROLE_DEAN, ROLE_IT_MANAGER})
        context["can_access_vp_publish"] = has_any_role(self.request.user, {ROLE_VP, ROLE_IT_MANAGER})
        context["can_access_performance_reports"] = has_any_role(
            self.request.user,
            {ROLE_DEAN, ROLE_VP, ROLE_PRINCIPAL, ROLE_IT_MANAGER},
        )
        return context


class GradeEntryClassSubjectsView(ResultsAccessMixin, TemplateView):
    template_name = "results/grade_entry_class_subjects.html"

    def _window(self):
        return resolve_teacher_assignment_window(
            self.request.user,
            requested_session_id=(self.request.GET.get("session_id") or "").strip(),
            requested_term_id=(self.request.GET.get("term_id") or "").strip(),
        )

    def _assignments(self):
        return list(
            self.window["assignments"]
            .filter(academic_class_id=self.kwargs["class_id"])
            .order_by("subject__name")
        )

    def _filter_query(self):
        query = {}
        if self.selected_session:
            query["session_id"] = self.selected_session.id
        if self.selected_term:
            query["term_id"] = self.selected_term.id
        return urlencode(query)

    def _current_url(self):
        base_url = reverse(
            "results:grade-entry-class-subjects",
            kwargs={"class_id": self.kwargs["class_id"]},
        )
        query = self._filter_query()
        return f"{base_url}?{query}" if query else base_url

    def _grade_entry_home_url(self):
        base_url = reverse("results:grade-entry-home")
        query = self._filter_query()
        return f"{base_url}?{query}" if query else base_url

    def dispatch(self, request, *args, **kwargs):
        self.window = self._window()
        self.selected_session = self.window["selected_session"]
        self.selected_term = self.window["selected_term"]
        self.assignments = self._assignments()
        if not self.assignments:
            messages.error(request, "No subjects found for this class.")
            return redirect(self._grade_entry_home_url())
        self.selected_class = self.assignments[0].academic_class
        return super().dispatch(request, *args, **kwargs)

    def _assignment_rows(self):
        rows = []
        term_edit_locked = getattr(self.request, "term_edit_locked", False)
        for assignment in self.assignments:
            sheet = _get_or_create_sheet_from_assignment(assignment, self.request.user)
            legacy_layout = _uses_legacy_result_layout(assignment.term)
            component_windows = _component_window_states(self.request.user, sheet)
            active_component_key = None if legacy_layout else _active_submission_component_key(self.request.user, sheet)
            display_component_keys = set() if legacy_layout else ({active_component_key} if active_component_key else set())
            enrollments = _assignment_enrollments_with_sheet_scores(assignment, sheet)
            enrolled_student_ids = [row.student_id for row in enrollments]
            score_count = StudentSubjectScore.objects.filter(
                result_sheet=sheet,
                student_id__in=enrolled_student_ids,
            ).count()
            base_can_submit = (
                academic_context_is_current(assignment.session_id, assignment.term_id)
                and request_user_can_edit_session(self.request.user, assignment.session)
                and sheet_is_editable_by_subject_owner(self.request.user, sheet)
                and not term_edit_locked
            )
            policies = sheet_policy_state(sheet)
            component_rows = []
            if legacy_layout:
                component_rows.append({
                    "key": "historical",
                    "label": "Historical Published Result",
                    "status": ResultSheetStatus.PUBLISHED,
                    "status_label": "Published / Approved",
                    "missing_count": 0,
                    "is_open": False,
                    "is_flagged": False,
                    "button_label": "Published / Approved",
                    "can_submit": False,
                    "blocked_reason": "",
                })
            else:
                for component_key, config in RESULT_COMPONENTS.items():
                    missing = _component_missing_rows(sheet, enrollments, policies, component_key)
                    review = _component_review(sheet, component_key)
                    if not _show_component_on_teacher_page(component_key, review, display_component_keys):
                        continue
                    window_state = component_windows[component_key]
                    is_submitted = review["status"] in {COMPONENT_SUBMITTED, COMPONENT_APPROVED}
                    component_rows.append({
                        "key": component_key,
                        "label": config["label"],
                        "status": review["status"],
                        "status_label": _component_status_label(review["status"]),
                        "missing_count": len(missing),
                        "is_open": window_state["is_open"],
                        "is_flagged": (
                            window_state["status"] == "EXPIRED"
                            and review["status"] not in {COMPONENT_SUBMITTED, COMPONENT_APPROVED}
                        ),
                        "button_label": (
                            "Approved"
                            if review["status"] == COMPONENT_APPROVED
                            else "Submitted"
                            if review["status"] == COMPONENT_SUBMITTED
                            else "Submit to Dean Overall"
                            if component_key == "exam"
                            else f"Submit {config['label']}"
                        ),
                        "can_submit": (
                            base_can_submit
                            and (window_state["is_open"] or window_state["is_bypassed_for_user"])
                            and review["status"] in {COMPONENT_DRAFT, COMPONENT_REJECTED}
                            and not missing
                            and not is_submitted
                        ),
                        "blocked_reason": "",
                    })
            rows.append(
                {
                    "assignment": assignment,
                    "result_sheet": sheet,
                    "score_count": score_count,
                    "enrollment_count": len(enrolled_student_ids),
                    "components": component_rows,
                }
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["selected_class"] = self.selected_class
        context["assignment_rows"] = self._assignment_rows()
        context["current_session"] = self.selected_session
        context["current_term"] = self.selected_term
        context["available_sessions"] = self.window["available_sessions"]
        context["available_terms"] = self.window["available_terms"]
        context["selected_session"] = self.selected_session
        context["selected_term"] = self.selected_term
        context["grade_entry_home_url"] = self._grade_entry_home_url()
        context["class_page_base_url"] = reverse(
            "results:grade-entry-class-subjects",
            kwargs={"class_id": self.kwargs["class_id"]},
        )
        context["class_page_url"] = self._current_url()
        context["filter_query"] = self._filter_query()
        context["term_edit_locked"] = getattr(self.request, "term_edit_locked", False)
        context["term_edit_lock_message"] = getattr(self.request, "term_edit_lock_message", "")
        return context

    def post(self, request, *args, **kwargs):
        assignment_id = (request.POST.get("assignment_id") or "").strip()
        component_key = (request.POST.get("component") or "").strip()
        if component_key not in RESULT_COMPONENTS:
            messages.error(request, "Choose a valid result component to submit.")
            return redirect(self._current_url())
        assignment = next(
            (row for row in self.assignments if str(row.id) == assignment_id),
            None,
        )
        if assignment is None:
            messages.error(request, "Invalid subject submission target.")
            return redirect(self._current_url())
        if not academic_context_is_current(assignment.session_id, assignment.term_id):
            messages.error(request, active_term_edit_message())
            return redirect(self._current_url())
        if not request_user_can_edit_session(request.user, assignment.session):
            messages.error(request, "This session is closed. Result sheets are read-only.")
            return redirect(self._current_url())
        if getattr(request, "term_edit_locked", False):
            messages.error(
                request,
                getattr(
                    request,
                    "term_edit_lock_message",
                    "Previous-term records remain visible through filters, but staff edit actions stay locked until the active term opens.",
                ),
            )
            return redirect(self._current_url())

        sheet = _get_or_create_sheet_from_assignment(assignment, request.user)
        active_component_key = _active_submission_component_key(request.user, sheet)
        if active_component_key and component_key != active_component_key:
            messages.error(
                request,
                f"Only {RESULT_COMPONENTS[active_component_key]['label']} is open for submission now.",
            )
            return redirect(self._current_url())
        window_state = _component_window_state(component_key, request.user, sheet)
        if not (window_state["is_open"] or window_state["is_bypassed_for_user"]):
            messages.error(request, window_state["summary"])
            return redirect(self._current_url())
        if not sheet_is_editable_by_subject_owner(request.user, sheet):
            messages.error(request, "This subject sheet is already locked for full-term review.")
            return redirect(self._current_url())

        review = _component_review(sheet, component_key)
        if review["status"] not in {COMPONENT_DRAFT, COMPONENT_REJECTED}:
            messages.error(request, f"{RESULT_COMPONENTS[component_key]['label']} is already submitted or approved.")
            return redirect(self._current_url())

        enrollments = list(_subject_enrollments_for_assignment(assignment))
        for enrollment in enrollments:
            StudentSubjectScore.objects.get_or_create(
                result_sheet=sheet,
                student=enrollment.student,
            )
        missing = _component_missing_rows(sheet, enrollments, sheet_policy_state(sheet), component_key)
        if missing:
            sample = missing[0].student.get_full_name() or missing[0].student.username
            messages.error(
                request,
                f"{RESULT_COMPONENTS[component_key]['label']} cannot be submitted yet. "
                f"{len(missing)} student(s) still have missing scores. Example: {sample}.",
            )
            return redirect(self._current_url())

        _set_component_review(
            sheet,
            component_key,
            status=COMPONENT_SUBMITTED,
            actor=request.user,
            comment="",
        )
        _sync_sheet_status_from_component_reviews(sheet)
        log_results_approval(
            actor=request.user,
            request=request,
            metadata={
                "action": "SUBMIT_COMPONENT_TO_DEAN",
                "sheet_id": str(sheet.id),
                "component": component_key,
            },
        )
        messages.success(request, f"{assignment.subject.name} {RESULT_COMPONENTS[component_key]['label']} submitted to Dean.")
        return redirect(self._current_url())


class AssignmentScoreListView(ResultsAccessMixin, TemplateView):
    template_name = "results/assignment_scores.html"

    def _filter_query(self):
        query = {}
        session_id = (self.request.GET.get("session_id") or "").strip()
        term_id = (self.request.GET.get("term_id") or "").strip()
        if session_id:
            query["session_id"] = session_id
        if term_id:
            query["term_id"] = term_id
        return urlencode(query)

    def _class_subjects_url(self, *, assignment):
        base_url = reverse(
            "results:grade-entry-class-subjects",
            kwargs={"class_id": assignment.academic_class_id},
        )
        query = self._filter_query()
        return f"{base_url}?{query}" if query else base_url

    def _grade_entry_home_url(self):
        base_url = reverse("results:grade-entry-home")
        query = self._filter_query()
        return f"{base_url}?{query}" if query else base_url

    def _assignment(self):
        assignment = get_object_or_404(
            TeacherSubjectAssignment.objects.select_related(
                "teacher",
                "subject",
                "academic_class",
                "session",
                "term",
            ),
            pk=self.kwargs["assignment_id"],
            is_active=True,
        )
        if not has_any_role(self.request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            if assignment.teacher_id != self.request.user.id:
                return None
        return assignment

    def get(self, request, *args, **kwargs):
        assignment = self._assignment()
        if assignment is None:
            messages.error(request, "Access restricted for this class subject.")
            return redirect(self._grade_entry_home_url())

        sheet = _get_or_create_sheet_from_assignment(assignment, request.user)
        legacy_layout = _uses_legacy_result_layout(assignment.term)
        special_language_layout = _uses_special_language_layout(sheet)
        enrollments = _assignment_enrollments_with_sheet_scores(assignment, sheet)
        student_ids = [row.student_id for row in enrollments]
        score_map = {
            row.student_id: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet=sheet,
                student_id__in=student_ids,
            )
        }
        policies = sheet_policy_state(sheet)
        active_component_key = None if (legacy_layout or special_language_layout) else _active_submission_component_key(request.user, sheet)
        open_components = set() if (legacy_layout or special_language_layout) else _open_component_keys(request.user, sheet)
        component_windows = _component_window_states(request.user, sheet)
        display_component_keys = set(open_components)
        if active_component_key:
            display_component_keys.add(active_component_key)
        component_reviews = {
            key: {
                **_component_review(sheet, key),
                "label": RESULT_COMPONENTS[key]["label"],
                "status_label": _component_status_label(_component_review(sheet, key)["status"]),
                "is_open": component_windows[key]["is_open"],
                "visible": False if legacy_layout else _show_component_on_teacher_page(
                    key,
                    _component_review(sheet, key),
                    display_component_keys,
                ),
                "locked": _component_is_locked_for_teacher(sheet, key),
            }
            for key in RESULT_COMPONENTS
        }
        editable_components = {
            key: (
                key in open_components
                and not component_reviews[key]["locked"]
                and sheet_is_editable_by_subject_owner(request.user, sheet)
            )
            for key in RESULT_COMPONENTS
        }
        base_can_edit = (
            academic_context_is_current(assignment.session_id, assignment.term_id)
            and request_user_can_edit_session(request.user, assignment.session)
            and sheet_is_editable_by_subject_owner(request.user, sheet)
            and not getattr(request, "term_edit_locked", False)
        )
        editable_components = {key: (base_can_edit and value) for key, value in editable_components.items()}
        special_language_can_edit = bool(base_can_edit and special_language_layout)
        rows = []
        for enrollment in enrollments:
            score = score_map.get(enrollment.student_id)
            rows.append(
                {
                    "enrollment": enrollment,
                    "score": score,
                    "locked_fields": score.normalized_locked_fields() if score else [],
                    "cbt": row_component_state(score, policies),
                    "objective_display": _score_decimal(score.objective) if score else DECIMAL_ZERO,
                    "legacy_exam_total": _score_decimal(score.total_exam) if score else DECIMAL_ZERO,
                    "class_participation": _score_decimal(score.class_participation) if score else DECIMAL_ZERO,
                }
            )
        return self.render_to_response(
            self.get_context_data(
                assignment=assignment,
                result_sheet=sheet,
                rows=rows,
                cbt_policies=policies,
                can_edit=special_language_can_edit or any(editable_components.values()),
                editable_components=editable_components,
                component_reviews=component_reviews,
                component_windows=component_windows,
                use_legacy_result_layout=legacy_layout,
                special_language_layout=special_language_layout,
                special_language_can_edit=special_language_can_edit,
                class_subjects_url=self._class_subjects_url(assignment=assignment),
                term_edit_locked=getattr(request, "term_edit_locked", False),
                term_edit_lock_message=getattr(request, "term_edit_lock_message", ""),
            )
        )

    def post(self, request, *args, **kwargs):
        is_autosave = (
            request.POST.get("_autosave") == "1"
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        assignment = self._assignment()
        if assignment is None:
            message = "Access restricted for this class subject."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            return redirect(self._grade_entry_home_url())
        if not academic_context_is_current(assignment.session_id, assignment.term_id):
            message = active_term_edit_message()
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
            query = self._filter_query()
            return redirect(f"{assignment_url}?{query}" if query else assignment_url)
        if not request_user_can_edit_session(request.user, assignment.session):
            message = "This session is closed. Result sheets are read-only."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return redirect(self._class_subjects_url(assignment=assignment))
        if getattr(request, "term_edit_locked", False):
            message = getattr(
                request,
                "term_edit_lock_message",
                "Previous-term records remain visible through filters, but staff edit actions stay locked until the active term opens.",
            )
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
            query = self._filter_query()
            return redirect(f"{assignment_url}?{query}" if query else assignment_url)

        sheet = _get_or_create_sheet_from_assignment(assignment, request.user)
        if not sheet_is_editable_by_subject_owner(request.user, sheet):
            message = "Sheet is locked. Awaiting dean review."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
            query = self._filter_query()
            return redirect(f"{assignment_url}?{query}" if query else assignment_url)

        if _uses_special_language_layout(sheet):
            enrollments = list(_subject_enrollments_for_assignment(assignment))
            existing_scores = {
                row.student_id: row
                for row in StudentSubjectScore.objects.filter(
                    result_sheet=sheet,
                    student_id__in=[row.student_id for row in enrollments],
                )
            }
            updates = []
            row_errors = []
            for enrollment in enrollments:
                student = enrollment.student
                current_score = existing_scores.get(student.id)
                try:
                    ca_score = decimal_value(
                        request.POST.get(f"special_ca_{student.id}"),
                        current_score.ca1 if current_score else DECIMAL_ZERO,
                    )
                    objective_score = decimal_value(
                        current_score.objective if current_score else DECIMAL_ZERO,
                        DECIMAL_ZERO,
                    )
                    theory_score = decimal_value(
                        request.POST.get(f"special_theory_{student.id}"),
                        current_score.theory if current_score else DECIMAL_ZERO,
                    )
                    payload = compute_special_language_grade_payload(
                        ca=ca_score,
                        objective=objective_score,
                        theory=theory_score,
                    )
                except ValidationError as exc:
                    if hasattr(exc, "message_dict"):
                        detail = "; ".join(
                            [f"{k}: {v if isinstance(v, str) else ', '.join(v)}" for k, v in exc.message_dict.items()]
                        )
                    else:
                        detail = "; ".join(exc.messages)
                    row_errors.append(f"{student.get_full_name() or student.username}: {detail}")
                    continue
                updates.append({"student": student, "payload": payload})

            if updates:
                with transaction.atomic():
                    for row in updates:
                        score, _ = StudentSubjectScore.objects.get_or_create(
                            result_sheet=sheet,
                            student=row["student"],
                        )
                        before_snapshot = _score_snapshot(score if score.pk else None)
                        payload = row["payload"]
                        score.ca1 = payload.ca1
                        score.ca2 = DECIMAL_ZERO
                        score.ca3 = DECIMAL_ZERO
                        score.ca4 = DECIMAL_ZERO
                        score.class_participation = DECIMAL_ZERO
                        score.objective = payload.objective
                        score.theory = payload.theory
                        score.total_ca = payload.total_ca
                        score.total_exam = payload.total_exam
                        score.grand_total = payload.grand_total
                        score.grade = payload.grade
                        score.has_override = False
                        score.override_reason = ""
                        score.override_by = None
                        score.set_breakdown_value("special_language_ca", payload.ca1)
                        score.set_breakdown_value("objective_auto", payload.objective)
                        score.set_breakdown_value("special_language_theory", payload.theory)
                        score.cbt_locked_fields = sorted(set(score.normalized_locked_fields()) | {"objective"})
                        score.save()
                        _log_score_change(
                            actor=request.user,
                            request=request,
                            score=score,
                            sheet=sheet,
                            before_snapshot=before_snapshot,
                            violations=payload.violations,
                        )
            if is_autosave:
                return JsonResponse(
                    {
                        "ok": len(row_errors) == 0,
                        "saved": len(updates),
                        "errors": row_errors[:3],
                    }
                )
            if updates:
                messages.success(request, f"Saved special language scores for {len(updates)} student(s).")
            if row_errors:
                messages.error(
                    request,
                    f"{len(row_errors)} row(s) failed validation. Example: {row_errors[0]}",
                )
            assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
            query = self._filter_query()
            return redirect(f"{assignment_url}?{query}" if query else assignment_url)

        active_component_key = _active_submission_component_key(request.user, sheet)
        open_now = _open_component_keys(request.user, sheet)
        allowed_components = {
            key
            for key in open_now
            if not _component_is_locked_for_teacher(sheet, key)
        }
        if not allowed_components:
            message = "No CA or exam entry window is open for this sheet."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
            query = self._filter_query()
            return redirect(f"{assignment_url}?{query}" if query else assignment_url)

        enrollments = list(_subject_enrollments_for_assignment(assignment))
        existing_scores = {
            row.student_id: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet=sheet,
                student_id__in=[row.student_id for row in enrollments],
            )
        }
        if any(key.startswith("policy_") for key in request.POST):
            policies, policy_warnings, policy_changed = read_sheet_policies_from_post(
                sheet,
                request.POST,
                list(existing_scores.values()),
            )
        else:
            policies = sheet_policy_state(sheet)
            policy_warnings = []
            policy_changed = False
        if policy_changed:
            sheet.cbt_component_policies = policies
            sheet.save(update_fields=["cbt_component_policies", "updated_at"])
        updates = []
        row_errors = list(policy_warnings)
        for enrollment in enrollments:
            student = enrollment.student
            student_id = student.id
            current_score = existing_scores.get(student_id)
            try:
                bundle = build_posted_score_bundle(
                    current_score=current_score,
                    post=request.POST,
                    student_id=student_id,
                    policies=policies,
                    actor=request.user,
                    allowed_components=allowed_components,
                )
            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    detail = "; ".join(
                        [f"{k}: {v if isinstance(v, str) else ', '.join(v)}" for k, v in exc.message_dict.items()]
                    )
                else:
                    detail = "; ".join(exc.messages)
                row_errors.append(f"{student.get_full_name() or student.username}: {detail}")
                continue
            updates.append(
                {
                    "student": student,
                    "payload": bundle["payload"],
                    "locked_fields": bundle["locked_fields"],
                    "breakdown_updates": bundle["breakdown_updates"],
                }
            )

        if updates:
            with transaction.atomic():
                for row in updates:
                    score, _ = StudentSubjectScore.objects.get_or_create(
                        result_sheet=sheet,
                        student=row["student"],
                    )
                    before_snapshot = _score_snapshot(score if score.pk else None)
                    payload = row["payload"]
                    score.ca1 = payload.ca1
                    score.ca2 = payload.ca2
                    score.ca3 = payload.ca3
                    score.ca4 = payload.ca4
                    score.class_participation = payload.class_participation
                    score.objective = payload.objective
                    score.theory = payload.theory
                    score.total_ca = payload.total_ca
                    score.total_exam = payload.total_exam
                    score.grand_total = payload.grand_total
                    score.grade = payload.grade
                    score.has_override = False
                    score.override_reason = ""
                    score.override_by = None
                    for breakdown_key, breakdown_value in row["breakdown_updates"].items():
                        score.set_breakdown_value(breakdown_key, breakdown_value)
                    if row["locked_fields"]:
                        score.cbt_locked_fields = sorted(set(score.normalized_locked_fields()) | set(row["locked_fields"]))
                    score.save()
                    _log_score_change(
                        actor=request.user,
                        request=request,
                        score=score,
                        sheet=sheet,
                        before_snapshot=before_snapshot,
                        violations=payload.violations,
                    )

        if is_autosave:
            return JsonResponse(
                {
                    "ok": len(row_errors) == 0,
                    "saved": len(updates),
                    "errors": row_errors[:3],
                }
            )

        if updates:
            messages.success(request, f"Saved scores for {len(updates)} student(s).")
        if row_errors:
            sample = row_errors[0]
            messages.error(
                request,
                f"{len(row_errors)} row(s) failed validation. Example: {sample}",
            )
        assignment_url = reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
        query = self._filter_query()
        return redirect(f"{assignment_url}?{query}" if query else assignment_url)


class StudentScoreEditView(ResultsAccessMixin, TemplateView):
    template_name = "results/student_score_edit.html"

    def dispatch(self, request, *args, **kwargs):
        self.assignment = get_object_or_404(
            TeacherSubjectAssignment.objects.select_related(
                "teacher",
                "subject",
                "academic_class",
                "session",
                "term",
            ),
            pk=self.kwargs["assignment_id"],
            is_active=True,
        )
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            if self.assignment.teacher_id != request.user.id:
                messages.error(request, "Access restricted for this class subject.")
                return redirect("results:grade-entry-home")
        if not academic_context_is_current(self.assignment.session_id, self.assignment.term_id):
            messages.error(request, active_term_edit_message())
            return redirect("results:assignment-scores", assignment_id=self.assignment.id)
        try:
            _require_results_window(user=request.user, action_label="editing student result records")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("results:assignment-scores", assignment_id=self.assignment.id)
        if not request_user_can_edit_session(request.user, self.assignment.session):
            messages.error(request, "This session is closed. Scores are read-only.")
            return redirect("results:grade-entry-home")
        self.sheet = _get_or_create_sheet_from_assignment(self.assignment, request.user)
        if not sheet_is_editable_by_subject_owner(request.user, self.sheet):
            messages.error(request, "Scores are locked for this sheet.")
            return redirect("results:assignment-scores", assignment_id=self.assignment.id)
        self.enrollment = get_object_or_404(
            _subject_enrollments_for_assignment(self.assignment).select_related("student"),
            student_id=self.kwargs["student_id"],
        )
        self.score, _ = StudentSubjectScore.objects.get_or_create(
            result_sheet=self.sheet,
            student=self.enrollment.student,
        )
        self.locked_fields = set(self.score.normalized_locked_fields())
        if any(sheet_policy_state(self.sheet)[key]["enabled"] for key in ("ca1", "ca23", "ca4", "exam")):
            messages.info(request, "Use the full result entry table for CBT split scores on this subject.")
            return redirect("results:assignment-scores", assignment_id=self.assignment.id)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["assignment"] = self.assignment
        context["student"] = self.enrollment.student
        context["score"] = self.score
        context["locked_fields"] = sorted(self.locked_fields)
        context["form"] = kwargs.get("form") or StudentSubjectScoreForm(
            instance=self.score,
            actor=self.request.user,
            request=self.request,
            locked_fields=self.locked_fields,
        )
        return context

    def post(self, request, *args, **kwargs):
        form = StudentSubjectScoreForm(
            request.POST,
            instance=self.score,
            actor=request.user,
            request=request,
            locked_fields=self.locked_fields,
        )
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        before_snapshot = _score_snapshot(self.score if self.score.pk else None)
        score = form.save()
        payload = getattr(form, "computed_payload", None)
        _log_score_change(
            actor=request.user,
            request=request,
            score=score,
            sheet=self.sheet,
            before_snapshot=before_snapshot,
            violations=payload.violations if payload else {},
        )
        messages.success(request, "Student score saved.")
        return redirect("results:assignment-scores", assignment_id=self.assignment.id)


class DeanReviewBaseView(ResultsAccessMixin, TemplateView):
    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Dean approval access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def _is_read_only(self, session):
        return not request_user_can_edit_session(self.request.user, session)

    def _filtered_sheets_queryset(self, *, session, term):
        qs = ResultSheet.objects.select_related(
            "subject", "academic_class", "session", "term"
        ).filter(
            session=session,
            term=term,
            status__in=[
                ResultSheetStatus.SUBMITTED_TO_DEAN,
                ResultSheetStatus.APPROVED_BY_DEAN,
                ResultSheetStatus.REJECTED_BY_DEAN,
            ],
        )
        qs = exclude_external_exam_classes_for_term(qs, term, field_name="academic_class")
        qs = exclude_non_result_subjects(qs, field_name="subject")
        class_id = (self.request.GET.get("class_id") or "").strip()
        subject_id = (self.request.GET.get("subject_id") or "").strip()
        if class_id.isdigit():
            qs = qs.filter(academic_class_id=int(class_id))
        if subject_id.isdigit():
            qs = qs.filter(subject_id=int(subject_id))
        return qs.order_by("academic_class__code", "subject__name")

    def _filtered_exam_queryset(self, *, session, term):
        qs = (
            Exam.objects.select_related(
                "created_by",
                "subject",
                "academic_class",
                "session",
                "term",
            )
            .filter(status__in=[CBTExamStatus.PENDING_DEAN, CBTExamStatus.APPROVED])
            .order_by("-updated_at")
        )
        if session and term:
            qs = qs.filter(session=session, term=term)
            qs = exclude_external_exam_classes_for_term(qs, term, field_name="academic_class")
            qs = exclude_non_result_subjects(qs, field_name="subject")
        class_id = (self.request.GET.get("class_id") or "").strip()
        subject_id = (self.request.GET.get("subject_id") or "").strip()
        if class_id.isdigit():
            qs = qs.filter(academic_class_id=int(class_id))
        if subject_id.isdigit():
            qs = qs.filter(subject_id=int(subject_id))
        return qs

    def _simulation_wrapper_queryset(self):
        return (
            SimulationWrapper.objects.select_related("created_by", "dean_reviewed_by")
            .filter(
                status__in=[
                    CBTSimulationWrapperStatus.PENDING_DEAN,
                    CBTSimulationWrapperStatus.APPROVED,
                    CBTSimulationWrapperStatus.REJECTED,
                ]
            )
            .order_by("tool_name", "-updated_at")
        )

    def _shared_filters_context(self, *, session, term):
        assignment_qs = TeacherSubjectAssignment.objects.filter(
            session=session,
            term=term,
            is_active=True,
        )
        assignment_qs = exclude_external_exam_classes_for_term(assignment_qs, term, field_name="academic_class")
        assignment_qs = exclude_non_result_subjects(assignment_qs, field_name="subject")
        return {
            "filter_class_id": (self.request.GET.get("class_id") or "").strip(),
            "filter_subject_id": (self.request.GET.get("subject_id") or "").strip(),
            "filter_teacher_id": (self.request.GET.get("teacher_id") or "").strip(),
            "available_classes": (
                assignment_qs
                .values("academic_class_id", "academic_class__code")
                .distinct()
                .order_by("academic_class__code")
            ),
            "available_subjects": (
                assignment_qs
                .values("subject_id", "subject__name")
                .distinct()
                .order_by("subject__name")
            ),
            "available_teachers": (
                assignment_qs
                .values("teacher_id", "teacher__first_name", "teacher__last_name", "teacher__username")
                .distinct()
                .order_by("teacher__first_name", "teacher__last_name", "teacher__username")
            ),
        }


class DeanReviewListView(LoginRequiredMixin, RedirectView):
    permanent = False

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Dean approval access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("results:dean-result-review-list")


class DeanResultReviewListView(DeanReviewBaseView):
    template_name = "results/dean_result_review_list.html"

    def post(self, request, *args, **kwargs):
        session, term = current_session_term()
        if session is None or term is None:
            messages.error(request, "Current session/term is not configured.")
            return redirect("results:dean-result-review-list")
        if self._is_read_only(session):
            messages.error(request, "This session is closed. Dean actions are read-only.")
            return redirect("results:dean-result-review-list")

        action = (request.POST.get("bulk_action") or "").strip().lower()
        sheet_tokens = request.POST.getlist("sheet_ids")
        class_id = (request.POST.get("class_id") or "").strip()
        component_key = (request.POST.get("component") or "").strip()
        comment = (request.POST.get("comment") or "").strip()

        target_qs = ResultSheet.objects.filter(
            session=session,
            term=term,
        )
        target_qs = exclude_external_exam_classes_for_term(target_qs, term, field_name="academic_class")
        target_qs = exclude_non_result_subjects(target_qs, field_name="subject")
        token_pairs = []
        if sheet_tokens:
            for token in sheet_tokens:
                sheet_id, _, key = str(token).partition(":")
                if sheet_id.isdigit() and key in RESULT_COMPONENTS:
                    token_pairs.append((int(sheet_id), key))
            target_qs = target_qs.filter(id__in=[sheet_id for sheet_id, _key in token_pairs])
        elif class_id.isdigit():
            target_qs = target_qs.filter(academic_class_id=int(class_id))
            if component_key not in RESULT_COMPONENTS:
                messages.error(request, "Choose the submitted CA/exam component for the class action.")
                return redirect("results:dean-result-review-list")
        else:
            messages.error(request, "Select at least one submitted result component or class.")
            return redirect("results:dean-result-review-list")

        sheets = list(target_qs.select_related("academic_class", "subject"))
        submitted_targets = []
        closed_targets = []
        missing_targets = []
        token_lookup = set(token_pairs)
        for sheet in sheets:
            keys = [key for sheet_id, key in token_lookup if sheet_id == sheet.id] if token_pairs else [component_key]
            for key in keys:
                if _component_review(sheet, key)["status"] == COMPONENT_SUBMITTED:
                    if _component_review_window_is_open(user=request.user, sheet=sheet, component_key=key):
                        if action in {"approve_selected", "approve_class"}:
                            assignment = TeacherSubjectAssignment.objects.filter(
                                session=sheet.session,
                                term=sheet.term,
                                academic_class=sheet.academic_class,
                                subject=sheet.subject,
                                is_active=True,
                            ).select_related("academic_class", "subject").first()
                            if assignment is not None:
                                enrollments = list(_subject_enrollments_for_assignment(assignment))
                                missing = _component_missing_rows(
                                    sheet,
                                    enrollments,
                                    sheet_policy_state(sheet),
                                    key,
                                )
                                if missing:
                                    missing_targets.append((sheet, key, missing[0], len(missing)))
                                    continue
                        submitted_targets.append((sheet, key))
                    else:
                        closed_targets.append((sheet, key))
        if missing_targets:
            sheet, key, sample_enrollment, total_missing = missing_targets[0]
            sample_name = sample_enrollment.student.get_full_name() or sample_enrollment.student.username
            sample_number = getattr(getattr(sample_enrollment.student, "student_profile", None), "student_number", "")
            messages.error(
                request,
                f"{sheet.academic_class.code} {sheet.subject.name} {RESULT_COMPONENTS[key]['label']} cannot be approved. "
                f"{total_missing} student(s) still have missing or zero scores. Example: {sample_name} {sample_number}.",
            )
            return redirect("results:dean-result-review-list")
        if not submitted_targets:
            if closed_targets:
                messages.error(request, "The selected submitted component is not inside an open CA/exam review window.")
                return redirect("results:dean-result-review-list")
            messages.error(request, "No submitted result component found for this action.")
            return redirect("results:dean-result-review-list")

        if action in {"reject_selected", "reject_class"} and not comment:
            messages.error(request, "Provide rejection reason.")
            return redirect("results:dean-result-review-list")

        to_status = None
        action_code = ""
        if action in {"approve_selected", "approve_class"}:
            to_status = ResultSheetStatus.APPROVED_BY_DEAN
            action_code = "DEAN_BULK_APPROVE"
        elif action in {"reject_selected", "reject_class"}:
            to_status = ResultSheetStatus.REJECTED_BY_DEAN
            action_code = "DEAN_BULK_REJECT"
        else:
            messages.error(request, "Invalid dean bulk action.")
            return redirect("results:dean-result-review-list")

        with transaction.atomic():
            for sheet, key in submitted_targets:
                _set_component_review(
                    sheet,
                    key,
                    status=COMPONENT_APPROVED if to_status == ResultSheetStatus.APPROVED_BY_DEAN else COMPONENT_REJECTED,
                    actor=request.user,
                    comment=comment,
                )
                _sync_sheet_status_from_component_reviews(sheet)
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": action_code,
                        "sheet_id": str(sheet.id),
                        "component": key,
                        "class_id": str(sheet.academic_class_id),
                        "subject_id": str(sheet.subject_id),
                    },
                )

        messages.success(request, f"{len(submitted_targets)} result component(s) updated.")
        return redirect("results:dean-result-review-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        sheets_qs = self._filtered_sheets_queryset(session=session, term=term)
        all_sheets = list(
            exclude_non_result_subjects(
                exclude_external_exam_classes_for_term(
                    ResultSheet.objects.select_related("subject", "academic_class", "session", "term")
                    .filter(session=session, term=term),
                    term,
                    field_name="academic_class",
                ),
                field_name="subject",
            )
            .order_by("academic_class__code", "subject__name")
        )
        filter_class_id = (self.request.GET.get("class_id") or "").strip()
        filter_subject_id = (self.request.GET.get("subject_id") or "").strip()
        filter_teacher_id = (self.request.GET.get("teacher_id") or "").strip()
        assignment_lookup_qs = TeacherSubjectAssignment.objects.select_related(
            "teacher", "academic_class", "subject"
        ).filter(session=session, term=term, is_active=True)
        assignment_lookup_qs = exclude_external_exam_classes_for_term(
            assignment_lookup_qs,
            term,
            field_name="academic_class",
        )
        assignment_lookup_qs = exclude_non_result_subjects(assignment_lookup_qs, field_name="subject")
        sheet_teacher_map = {
            (assignment.academic_class_id, assignment.subject_id): assignment
            for assignment in assignment_lookup_qs
        }
        if filter_class_id.isdigit():
            all_sheets = [sheet for sheet in all_sheets if sheet.academic_class_id == int(filter_class_id)]
        if filter_subject_id.isdigit():
            all_sheets = [sheet for sheet in all_sheets if sheet.subject_id == int(filter_subject_id)]
        if filter_teacher_id.isdigit():
            teacher_id = int(filter_teacher_id)
            all_sheets = [
                sheet for sheet in all_sheets
                if (
                    sheet_teacher_map.get((sheet.academic_class_id, sheet.subject_id))
                    and sheet_teacher_map[(sheet.academic_class_id, sheet.subject_id)].teacher_id == teacher_id
                )
            ]
        component_rows = []
        for sheet in all_sheets:
            teacher_assignment = sheet_teacher_map.get((sheet.academic_class_id, sheet.subject_id))
            for key, config in RESULT_COMPONENTS.items():
                review = _component_review(sheet, key)
                if review["status"] == COMPONENT_DRAFT:
                    continue
                component_rows.append({
                    "sheet": sheet,
                    "component": key,
                    "component_label": config["label"],
                    "teacher_assignment": teacher_assignment,
                    "status": review["status"],
                    "status_label": _component_status_label(review["status"]),
                    "window_open": _component_review_window_is_open(
                        user=self.request.user,
                        sheet=sheet,
                        component_key=key,
                    ),
                })
        all_component_rows = component_rows
        result_status_filter = (self.request.GET.get("result_status") or "pending").strip().lower()
        result_status_map = {
            "pending": COMPONENT_SUBMITTED,
            "approved": COMPONENT_APPROVED,
            "rejected": COMPONENT_REJECTED,
        }
        if result_status_filter in result_status_map:
            component_rows = [
                row for row in all_component_rows
                if row["status"] == result_status_map[result_status_filter]
            ]
        elif result_status_filter != "all":
            result_status_filter = "pending"
            component_rows = [
                row for row in all_component_rows
                if row["status"] == COMPONENT_SUBMITTED
            ]
        assignment_qs = TeacherSubjectAssignment.objects.select_related(
            "teacher", "teacher__staff_profile", "academic_class", "subject"
        ).filter(session=session, term=term, is_active=True)
        assignment_qs = exclude_external_exam_classes_for_term(assignment_qs, term, field_name="academic_class")
        assignment_qs = exclude_non_result_subjects(assignment_qs, field_name="subject")
        if filter_class_id.isdigit():
            assignment_qs = assignment_qs.filter(academic_class_id=int(filter_class_id))
        if filter_subject_id.isdigit():
            assignment_qs = assignment_qs.filter(subject_id=int(filter_subject_id))
        if filter_teacher_id.isdigit():
            assignment_qs = assignment_qs.filter(teacher_id=int(filter_teacher_id))
        assignment_qs = assignment_qs.order_by(
            "teacher__first_name", "teacher__last_name", "academic_class__code", "subject__name"
        )
        sheet_map = {(sheet.academic_class_id, sheet.subject_id): sheet for sheet in all_sheets}
        global_windows = {key: get_academic_window_state(window_type=config["window_type"]) for key, config in RESULT_COMPONENTS.items()}
        staff_entry_rows = []
        entry_counts = {
            "total": 0,
            "finished": 0,
            "awaiting": 0,
            "in_progress": 0,
            "not_started": 0,
            "late": 0,
        }
        for assignment in assignment_qs:
            sheet = sheet_map.get((assignment.academic_class_id, assignment.subject_id))
            enrollments = list(_subject_enrollments_for_assignment(assignment))
            policies = sheet_policy_state(sheet) if sheet else normalize_result_cbt_policies({})
            saved_count = sheet.student_scores.count() if sheet else 0
            component_states = []
            active_key = _active_submission_component_key(self.request.user, sheet)
            display_keys = {active_key} if active_key else {"exam"}
            display_keys.update(
                key
                for key in RESULT_COMPONENTS
                if sheet and _component_review(sheet, key)["status"] != COMPONENT_DRAFT
            )
            for key in [key for key in RESULT_COMPONENTS if key in display_keys]:
                review = _component_review(sheet, key) if sheet else {"status": COMPONENT_DRAFT}
                missing_count = (
                    len(_component_missing_rows(sheet, enrollments, policies, key))
                    if sheet else len(enrollments)
                )
                if review["status"] == COMPONENT_APPROVED:
                    state, status_label = "finished", "Dean Approved"
                elif review["status"] == COMPONENT_SUBMITTED:
                    state, status_label = "awaiting", "Awaiting Dean"
                elif review["status"] == COMPONENT_REJECTED:
                    state, status_label = "in_progress", "Rejected"
                elif global_windows[key]["status"] == "EXPIRED":
                    state, status_label = "late", "Late"
                elif saved_count == 0:
                    state, status_label = "not_started", "Not Started"
                else:
                    state, status_label = "in_progress", "In Progress"
                entry_counts["total"] += 1
                entry_counts[state] += 1
                component_states.append({
                    "key": key,
                    "short_label": {
                        "ca1": "CA1",
                        "ca23": "CA2/3",
                        "ca4": "CA4",
                        "exam": "Overall",
                    }[key],
                    "state": state,
                    "status_label": status_label,
                    "missing_count": missing_count,
                    "deadline": global_windows[key]["end_at"],
                    "review_url": (
                        f"{reverse('results:dean-review-detail', kwargs={'sheet_id': sheet.id})}?component={key}"
                        if sheet else ""
                    ),
                })
            staff_entry_rows.append({
                "assignment": assignment,
                "sheet": sheet,
                "saved_count": saved_count,
                "enrollment_count": len(enrollments),
                "components": component_states,
            })
        context["current_session"] = session
        context["current_term"] = term
        context["result_window"] = _aggregate_dean_component_window_state(self.request.user)
        context["sheets"] = sheets_qs
        queue_paginator = Paginator(component_rows, 5)
        queue_page_obj = queue_paginator.get_page(self.request.GET.get("queue_page") or 1)
        staff_paginator = Paginator(staff_entry_rows, 8)
        staff_page_obj = staff_paginator.get_page(self.request.GET.get("staff_page") or 1)
        queue_params = self.request.GET.copy()
        queue_params.pop("queue_page", None)
        staff_params = self.request.GET.copy()
        staff_params.pop("staff_page", None)
        context["component_rows"] = list(queue_page_obj.object_list)
        context["queue_page_obj"] = queue_page_obj
        context["queue_page_querystring"] = queue_params.urlencode()
        context["component_row_count"] = len(component_rows)
        context["result_status_filter"] = result_status_filter
        context["result_pending_count"] = len([row for row in all_component_rows if row["status"] == COMPONENT_SUBMITTED])
        context["result_approved_count"] = len([row for row in all_component_rows if row["status"] == COMPONENT_APPROVED])
        context["result_rejected_count"] = len([row for row in all_component_rows if row["status"] == COMPONENT_REJECTED])
        context["staff_entry_rows"] = list(staff_page_obj.object_list)
        context["staff_page_obj"] = staff_page_obj
        context["staff_page_querystring"] = staff_params.urlencode()
        context["staff_entry_row_count"] = len(staff_entry_rows)
        context["entry_counts"] = entry_counts
        class_counts = {}
        for row in component_rows:
            if row["status"] != COMPONENT_SUBMITTED:
                continue
            key = (row["sheet"].academic_class_id, row["sheet"].academic_class.code, row["component"])
            class_counts[key] = class_counts.get(key, 0) + 1
        context["result_class_rows"] = [
            {
                "academic_class_id": class_id,
                "academic_class__code": code,
                "component": component,
                "component_label": RESULT_COMPONENTS[component]["label"],
                "total": total,
                "window_open": (
                    lambda state: state["is_open"] or state.get("is_bypassed_for_user")
                )(
                    get_academic_window_state(
                        window_type=RESULT_COMPONENTS[component]["window_type"],
                        user=self.request.user,
                    )
                ),
            }
            for (class_id, code, component), total in sorted(class_counts.items(), key=lambda item: (item[0][1], item[0][2]))
        ]
        context["is_read_only"] = self._is_read_only(session) if session else True
        context.update(self._shared_filters_context(session=session, term=term))
        return context


class DeanExamReviewListView(DeanReviewBaseView):
    template_name = "results/dean_exam_review_list.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        exam_qs = self._filtered_exam_queryset(session=session, term=term)
        wrapper_qs = self._simulation_wrapper_queryset()

        context["current_session"] = session
        context["current_term"] = term
        context["cbt_exams"] = exam_qs
        context["cbt_pending_count"] = exam_qs.filter(
            status=CBTExamStatus.PENDING_DEAN
        ).count()
        context["cbt_approved_count"] = exam_qs.filter(
            status=CBTExamStatus.APPROVED
        ).count()
        context["simulation_wrappers"] = wrapper_qs
        context["sim_pending_count"] = wrapper_qs.filter(
            status=CBTSimulationWrapperStatus.PENDING_DEAN
        ).count()
        context["sim_approved_count"] = wrapper_qs.filter(
            status=CBTSimulationWrapperStatus.APPROVED
        ).count()
        context["cbt_window"] = _cbt_window_state_for(self.request.user)
        context["sim_rejected_count"] = wrapper_qs.filter(
            status=CBTSimulationWrapperStatus.REJECTED
        ).count()
        context.update(self._shared_filters_context(session=session, term=term))
        return context


class DeanReviewDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/dean_review_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Dean approval access required.")
            return redirect("results:grade-entry-home")
        self.sheet = get_object_or_404(
            ResultSheet.objects.select_related("subject", "academic_class", "session", "term"),
            pk=self.kwargs["sheet_id"],
        )
        if class_is_external_exam_class_for_term(self.sheet.academic_class, self.sheet.term):
            messages.error(request, "JS3 and SS3 are excluded from Third Term Dean result review.")
            return redirect("results:dean-result-review-list")
        if subject_is_excluded_from_results(self.sheet.subject):
            messages.error(request, "Chinese, German and Sign Language are not part of Dean result review.")
            return redirect("results:dean-result-review-list")
        self.component_key = (request.GET.get("component") or request.POST.get("component") or "exam").strip()
        if self.component_key not in RESULT_COMPONENTS:
            messages.error(request, "Invalid result component.")
            return redirect("results:dean-result-review-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sheet"] = self.sheet
        context["component_key"] = self.component_key
        context["component_label"] = RESULT_COMPONENTS[self.component_key]["label"]
        context["component_status"] = _component_review(self.sheet, self.component_key)["status"]
        context["component_status_label"] = _component_status_label(context["component_status"])
        context["result_window"] = _component_window_state(
            self.component_key,
            self.request.user,
            self.sheet,
        )
        context["use_legacy_result_layout"] = _uses_legacy_result_layout(self.sheet.term)
        context["can_dean_decide"] = (
            context["component_status"] == COMPONENT_SUBMITTED
            and (
                context["result_window"]["is_open"]
                or context["result_window"].get("is_bypassed_for_user")
            )
        )
        context["scores"] = self.sheet.student_scores.select_related("student", "student__student_profile").order_by(
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )
        context["approve_form"] = ResultActionForm()
        context["reject_form"] = RejectActionForm()
        return context

    def post(self, request, *args, **kwargs):
        if not _component_review_window_is_open(
            user=request.user,
            sheet=self.sheet,
            component_key=self.component_key,
        ):
            messages.error(request, "This CA/exam component review window is closed.")
            return redirect(f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}")
        if not academic_context_is_current(self.sheet.session_id, self.sheet.term_id):
            messages.error(request, active_term_edit_message())
            return redirect(f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}")
        if not request_user_can_edit_session(request.user, self.sheet.session):
            messages.error(request, "This session is closed. Dean decisions are read-only.")
            return redirect(f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}")
        if _component_review(self.sheet, self.component_key)["status"] != COMPONENT_SUBMITTED:
            messages.error(
                request,
                "This result component is no longer in Dean review queue.",
            )
            return redirect(f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}")
        action = request.POST.get("action")
        if action == "approve":
            form = ResultActionForm(request.POST)
            if form.is_valid():
                assignment = TeacherSubjectAssignment.objects.filter(
                    session=self.sheet.session,
                    term=self.sheet.term,
                    academic_class=self.sheet.academic_class,
                    subject=self.sheet.subject,
                    is_active=True,
                ).select_related("academic_class", "subject").first()
                if assignment is not None:
                    enrollments = list(_subject_enrollments_for_assignment(assignment))
                    missing = _component_missing_rows(
                        self.sheet,
                        enrollments,
                        sheet_policy_state(self.sheet),
                        self.component_key,
                    )
                    if missing:
                        sample_name = missing[0].student.get_full_name() or missing[0].student.username
                        sample_number = getattr(getattr(missing[0].student, "student_profile", None), "student_number", "")
                        messages.error(
                            request,
                            f"{RESULT_COMPONENTS[self.component_key]['label']} cannot be approved. "
                            f"{len(missing)} student(s) still have missing or zero scores. Example: {sample_name} {sample_number}.",
                        )
                        return redirect(
                            f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}"
                        )
                _set_component_review(
                    self.sheet,
                    self.component_key,
                    status=COMPONENT_APPROVED,
                    actor=request.user,
                    comment=form.cleaned_data.get("comment", ""),
                )
                _sync_sheet_status_from_component_reviews(self.sheet)
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={"action": "DEAN_APPROVE_COMPONENT", "sheet_id": str(self.sheet.id), "component": self.component_key},
                )
                messages.success(request, f"{RESULT_COMPONENTS[self.component_key]['label']} approved by Dean.")
                return redirect("results:dean-result-review-list")
        elif action == "reject":
            form = RejectActionForm(request.POST)
            if form.is_valid():
                _set_component_review(
                    self.sheet,
                    self.component_key,
                    status=COMPONENT_REJECTED,
                    actor=request.user,
                    comment=form.cleaned_data["comment"],
                )
                _sync_sheet_status_from_component_reviews(self.sheet)
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={"action": "DEAN_REJECT_COMPONENT", "sheet_id": str(self.sheet.id), "component": self.component_key},
                )
                messages.success(request, f"{RESULT_COMPONENTS[self.component_key]['label']} rejected back to subject teacher.")
                return redirect("results:dean-result-review-list")
        messages.error(request, "Invalid Dean decision payload.")
        return redirect(f"{reverse('results:dean-review-detail', kwargs={'sheet_id': self.sheet.id})}?component={self.component_key}")


class FormCompilationView(ResultsAccessMixin, TemplateView):
    template_name = "results/form_compilation.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Form teacher compilation access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def _selected_assignment(self, classes_qs):
        class_id = self.request.GET.get("class_id") or self.request.POST.get("class_id")
        selected = classes_qs.filter(academic_class_id=class_id).first()
        return selected or classes_qs.first()

    def _current_term(self):
        _, term = current_session_term()
        return term

    def _build_context(self, classes_qs, selected_assignment):
        context = self.get_context_data()
        result_window = _results_window_state_for(self.request.user)
        context["class_assignments"] = classes_qs
        context["selected_assignment"] = selected_assignment
        context["current_session"] = selected_assignment.session if selected_assignment else None
        context["current_term"] = None
        context["compilation"] = None
        context["rows"] = []
        context["can_submit"] = False
        context["form_stage_open"] = False
        context["result_window_open"] = result_window["is_open"]
        context["pending_subjects"] = []
        context["required_subject_count"] = 0
        context["search_query"] = (self.request.GET.get("q") or "").strip()

        if not selected_assignment:
            return context

        term = self._current_term()
        if term is None:
            return context
        context["current_term"] = term

        compilation, _ = ClassResultCompilation.objects.get_or_create(
            academic_class=selected_assignment.academic_class,
            session=selected_assignment.session,
            term=term,
            defaults={"form_teacher": selected_assignment.teacher},
        )
        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(selected_assignment.academic_class),
            session=selected_assignment.session,
            term=term,
        ).select_related("subject")
        sheets_qs = exclude_non_result_subjects(sheets_qs, field_name="subject")
        approved_sheets_qs = sheets_qs.filter(status=ResultSheetStatus.APPROVED_BY_DEAN)
        subject_assignments = TeacherSubjectAssignment.objects.filter(
            academic_class=_instructional_class(selected_assignment.academic_class),
            session=selected_assignment.session,
            term=term,
            is_active=True,
        ).select_related("subject")
        subject_assignments = exclude_non_result_subjects(subject_assignments, field_name="subject")
        required_subject_count = subject_assignments.count()
        context["required_subject_count"] = required_subject_count
        sheet_map = {sheet.subject_id: sheet for sheet in sheets_qs}
        pending_subjects = []
        for subject_assignment in subject_assignments:
            sheet = sheet_map.get(subject_assignment.subject_id)
            if not sheet or sheet.status != ResultSheetStatus.APPROVED_BY_DEAN:
                pending_subjects.append(subject_assignment.subject.name)

        enrollments = StudentClassEnrollment.objects.select_related("student", "student__student_profile").filter(
            academic_class_id__in=_cohort_class_ids(selected_assignment.academic_class),
            session=selected_assignment.session,
            is_active=True,
        )
        cohort_student_ids = list(enrollments.values_list("student_id", flat=True))
        search_query = context["search_query"]
        if search_query:
            enrollments = enrollments.filter(
                Q(student__first_name__icontains=search_query)
                | Q(student__last_name__icontains=search_query)
                | Q(student__username__icontains=search_query)
                | Q(student__student_profile__student_number__icontains=search_query)
            )
        enrollments = enrollments.order_by(
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )

        record_map = {
            row.student_id: row
            for row in ClassResultStudentRecord.objects.filter(compilation=compilation).select_related("student")
        }
        calendar = SchoolCalendar.objects.filter(
            session=selected_assignment.session,
            term=term,
        ).first()

        score_queryset = StudentSubjectScore.objects.filter(
                result_sheet__in=approved_sheets_qs,
                student_id__in=enrollments.values_list("student_id", flat=True),
            )
        score_queryset = exclude_non_result_subjects(score_queryset, field_name="result_sheet__subject")
        score_rows = (
            score_queryset
            .values("student_id")
            .annotate(
                total=Sum("grand_total"),
                avg=Avg("grand_total"),
                subjects=Count("id"),
            )
        )
        score_map = {row["student_id"]: row for row in score_rows}

        rows = []
        for enrollment in enrollments:
            student = enrollment.student
            record = record_map.get(student.id)
            if record is None:
                record = ClassResultStudentRecord(
                    compilation=compilation,
                    student=student,
                    behavior_rating=3,
                )
            attendance_percentage = record.attendance_percentage
            if calendar:
                record.refresh_attendance(calendar, selected_assignment.academic_class)
                attendance_percentage = record.attendance_percentage
            score_info = score_map.get(student.id) or {}
            cumulative_total = Decimal(score_info.get("total") or 0).quantize(Decimal("0.01"))
            actual_subject_count = int(score_info.get("subjects") or 0)
            subject_count = actual_subject_count
            average_score = _average_to_decimal(cumulative_total, subject_count)
            rows.append(
                {
                    "enrollment": enrollment,
                    "record": record,
                    "admission_number": _admission_number_for_student(student),
                    "approved_subject_count": subject_count,
                    "actual_approved_subject_count": actual_subject_count,
                    "progress_label": f"{actual_subject_count}/{required_subject_count} approved",
                    "cumulative_total": cumulative_total,
                    "average_score": average_score,
                    "attendance_percentage": attendance_percentage,
                    "management_status": (
                        record.get_management_status_display()
                        if getattr(record, "pk", None)
                        else StudentResultManagementStatus.PENDING.label
                    ),
                    "detail_url": reverse(
                        "results:form-compilation-student-detail",
                        kwargs={
                            "class_id": selected_assignment.academic_class_id,
                            "student_id": student.id,
                        },
                    ),
                }
            )

        context["compilation"] = compilation
        context["rows"] = rows
        context["pending_subjects"] = pending_subjects
        context["form_stage_open"] = len(pending_subjects) == 0
        completed_student_count = (
            ClassResultStudentRecord.objects.filter(
                compilation=compilation,
                student_id__in=cohort_student_ids,
                form_teacher_completed_at__isnull=False,
            )
            .exclude(teacher_comment="")
            .values("student_id")
            .distinct()
            .count()
        )
        incomplete_student_count = max(len(cohort_student_ids) - completed_student_count, 0)
        context["incomplete_student_count"] = incomplete_student_count
        context["can_submit"] = (
            len(pending_subjects) == 0
            and incomplete_student_count == 0
            and bool(cohort_student_ids)
            and compilation.status in {
            ClassCompilationStatus.DRAFT,
            ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
            ClassCompilationStatus.REJECTED_BY_VP,
            }
        )
        context["is_locked"] = (
            compilation.status == ClassCompilationStatus.PUBLISHED
            or (
                compilation.session.is_closed
                and not self.request.user.has_role(ROLE_IT_MANAGER)
            )
        )
        return context

    def get(self, request, *args, **kwargs):
        classes_qs = form_teacher_classes_for_user(request.user)
        _, term = current_session_term()
        classes_qs = exclude_external_exam_classes_for_term(classes_qs, term, field_name="academic_class")
        selected = self._selected_assignment(classes_qs)
        return self.render_to_response(self._build_context(classes_qs, selected))

    def post(self, request, *args, **kwargs):
        classes_qs = form_teacher_classes_for_user(request.user)
        _, term = current_session_term()
        classes_qs = exclude_external_exam_classes_for_term(classes_qs, term, field_name="academic_class")
        selected = self._selected_assignment(classes_qs)
        if not selected:
            messages.error(request, "No form class found.")
            return redirect("results:form-compilation")

        context = self._build_context(classes_qs, selected)
        compilation = context["compilation"]
        if not compilation:
            messages.error(request, "Unable to initialize class compilation.")
            return redirect("results:form-compilation")
        if context["pending_subjects"] and not request.user.has_role(ROLE_IT_MANAGER):
            messages.error(
                request,
                "Form-teacher entry opens automatically only after every subject is approved by the Dean.",
            )
            return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")
        if not academic_context_is_current(compilation.session_id, compilation.term_id):
            messages.error(request, active_term_edit_message())
            return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")
        if not request_user_can_edit_session(request.user, compilation.session):
            messages.error(request, "This session is closed. Compilation is read-only.")
            return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")
        if compilation.status not in {
            ClassCompilationStatus.DRAFT,
            ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
            ClassCompilationStatus.REJECTED_BY_VP,
        }:
            messages.error(
                request,
                "This compilation is locked and cannot be edited by form teacher.",
            )
            return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")

        with transaction.atomic():
            for row in context["rows"]:
                enrollment = row["enrollment"]
                behavior_key = f"behavior_{enrollment.student_id}"
                comment_key = f"comment_{enrollment.student_id}"
                record, created = ClassResultStudentRecord.objects.get_or_create(
                    compilation=compilation,
                    student=enrollment.student,
                )
                if created and not record.behavior_breakdown:
                    record.behavior_breakdown = _default_behavior_breakdown(seed=record.behavior_rating)
                if behavior_key in request.POST:
                    try:
                        behavior = int(request.POST.get(behavior_key, record.behavior_rating or 3))
                    except (TypeError, ValueError):
                        behavior = record.behavior_rating or 3
                    behavior = max(1, min(5, behavior))
                    record.behavior_rating = behavior
                    record.behavior_breakdown = _default_behavior_breakdown(seed=behavior)
                if comment_key in request.POST:
                    record.teacher_comment = request.POST.get(comment_key, "").strip()
                record.attendance_percentage = row["record"].attendance_percentage
                record.save()

            action = request.POST.get("action")
            if action == "submit":
                if not context["can_submit"]:
                    messages.error(
                        request,
                        "Cannot submit to Dean term review until every subject is Dean-approved and every student has a completed form-teacher comment/remark.",
                    )
                    return self.render_to_response(self._build_context(classes_qs, selected))
                if compilation.status not in {
                    ClassCompilationStatus.DRAFT,
                    ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
                    ClassCompilationStatus.REJECTED_BY_VP,
                }:
                    messages.error(
                        request,
                        "Compilation is not in a submittable state.",
                    )
                    return self.render_to_response(self._build_context(classes_qs, selected))
                mark_compilation_submitted_to_dean_final(
                    compilation,
                    request.user,
                    form_teacher=selected.teacher,
                )
                sheets_qs = ResultSheet.objects.filter(
                    academic_class=_instructional_class(selected.academic_class),
                    session=selected.session,
                    term=compilation.term,
                )
                transition_class_sheet_set(
                    sheets_qs=sheets_qs.filter(status=ResultSheetStatus.APPROVED_BY_DEAN),
                    to_status=ResultSheetStatus.SUBMITTED_TO_VP,
                    actor=request.user,
                    action="FORM_SUBMIT_TO_DEAN_TERM_REVIEW",
                    comment="Compiled by form teacher and submitted to Dean term review.",
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "FORM_SUBMIT_TO_DEAN_TERM_REVIEW",
                        "compilation_id": str(compilation.id),
                        "class_id": str(compilation.academic_class_id),
                    },
                )
                messages.success(request, "Class compilation submitted to Dean term review.")
            else:
                messages.success(request, "Class compilation draft saved.")

        return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")


class FormCompilationStudentDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/form_compilation_student_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Form teacher compilation access required.")
            return redirect("results:grade-entry-home")
        self.class_assignment = form_teacher_classes_for_user(request.user).filter(
            academic_class_id=kwargs["class_id"]
        ).first()
        if not self.class_assignment:
            messages.error(request, "No form class found.")
            return redirect("results:form-compilation")
        _, term = current_session_term()
        if term is None:
            messages.error(request, "Current term is not configured.")
            return redirect("results:form-compilation")
        self.term = term
        if class_is_external_exam_class_for_term(self.class_assignment.academic_class, self.term):
            messages.error(request, "JS3 and SS3 are excluded from Third Term form-teacher result compilation.")
            return redirect("results:form-compilation")
        self.compilation, _ = ClassResultCompilation.objects.get_or_create(
            academic_class=self.class_assignment.academic_class,
            session=self.class_assignment.session,
            term=self.term,
            defaults={"form_teacher": self.class_assignment.teacher},
        )
        self.pending_subjects = _pending_dean_subject_names(self.compilation)
        self.enrollment = get_object_or_404(
            StudentClassEnrollment.objects.select_related("student", "student__student_profile"),
            academic_class_id__in=_cohort_class_ids(self.class_assignment.academic_class),
            session=self.class_assignment.session,
            student_id=kwargs["student_id"],
            is_active=True,
        )
        self.student = self.enrollment.student
        self.record, _ = ClassResultStudentRecord.objects.get_or_create(
            compilation=self.compilation,
            student=self.student,
            defaults={
                "behavior_rating": 3,
                "behavior_breakdown": _default_behavior_breakdown(seed=3),
            },
        )
        if not self.record.behavior_breakdown:
            self.record.behavior_breakdown = _default_behavior_breakdown(
                seed=self.record.behavior_rating
            )
            self.record.save(update_fields=["behavior_breakdown", "updated_at"])
        return super().dispatch(request, *args, **kwargs)

    def _subject_rows(self):
        subject_assignments = list(
            TeacherSubjectAssignment.objects.select_related("subject", "teacher")
            .filter(
                academic_class=_instructional_class(self.class_assignment.academic_class),
                session=self.class_assignment.session,
                term=self.term,
                is_active=True,
            )
            .order_by("subject__name")
        )
        subject_assignments = [
            row for row in subject_assignments
            if row.subject.code not in NON_RESULT_SUBJECT_CODES
        ]
        offered_subject_ids = set(
            StudentSubjectEnrollment.objects.filter(
                student=self.student,
                session=self.class_assignment.session,
                is_active=True,
            ).values_list("subject_id", flat=True)
        )
        if offered_subject_ids:
            subject_assignments = [
                row for row in subject_assignments if row.subject_id in offered_subject_ids
            ]
        sheet_queryset = ResultSheet.objects.filter(
                academic_class=_instructional_class(self.class_assignment.academic_class),
                session=self.class_assignment.session,
                term=self.term,
            )
        sheet_queryset = exclude_non_result_subjects(sheet_queryset, field_name="subject")
        sheets = list(sheet_queryset.select_related("subject"))
        sheet_map = {sheet.subject_id: sheet for sheet in sheets}
        score_map = {
            row.result_sheet_id: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet_id__in=[sheet.id for sheet in sheets],
                student=self.student,
            )
        }
        rows = []
        for subject_assignment in subject_assignments:
            sheet = sheet_map.get(subject_assignment.subject_id)
            score = score_map.get(sheet.id) if sheet else None
            is_dean_approved = bool(
                sheet and sheet.status == ResultSheetStatus.APPROVED_BY_DEAN
            )
            rows.append(
                {
                    "subject_name": subject_assignment.subject.name,
                    "subject_assignment": subject_assignment,
                    "sheet": sheet,
                    "score": score,
                    "is_dean_approved": is_dean_approved,
                    "can_edit_subject": False,
                    "edit_url": "",
                }
            )
        if offered_subject_ids:
            assigned_subject_ids = {row.subject_id for row in subject_assignments}
            missing_subject_ids = offered_subject_ids - assigned_subject_ids
            if missing_subject_ids:
                for subject in Subject.objects.filter(id__in=missing_subject_ids).order_by("name"):
                    if subject_is_excluded_from_results(subject):
                        continue
                    rows.append(
                        {
                            "subject_name": subject.name,
                            "subject_assignment": None,
                            "sheet": None,
                            "score": None,
                            "is_dean_approved": False,
                            "can_edit_subject": False,
                            "edit_url": "",
                        }
                    )
                rows.sort(key=lambda row: (row.get("subject_name") or "").lower())
        return rows

    def _summary(self, subject_rows):
        actual_subject_count = len(subject_rows)
        subject_count = actual_subject_count
        cumulative_total = sum(
            (
                row["score"].grand_total
                if row["is_dean_approved"] and row["score"] is not None
                else Decimal("0.00")
                for row in subject_rows
            ),
            Decimal("0.00"),
        )
        average_score = _average_to_decimal(cumulative_total, subject_count)
        fail_count = len(
            [
                row
                for row in subject_rows
                if row["is_dean_approved"]
                and row["score"] is not None
                and is_failing_grade(row["score"].grade)
            ]
        )
        return {
            "subject_count": subject_count,
            "actual_subject_count": actual_subject_count,
            "cumulative_total": cumulative_total.quantize(Decimal("0.01")),
            "average_score": average_score,
            "fail_count": fail_count,
        }

    def _attendance_percentage(self):
        calendar = SchoolCalendar.objects.filter(
            session=self.class_assignment.session,
            term=self.term,
        ).first()
        if calendar:
            self.record.refresh_attendance(calendar, self.class_assignment.academic_class)
            self.record.save(update_fields=["attendance_percentage", "updated_at"])
        return self.record.attendance_percentage

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        subject_rows = self._subject_rows()
        summary = self._summary(subject_rows)
        attendance_percentage = self._attendance_percentage()
        behavior_breakdown = _normalize_behavior_breakdown(
            self.record.behavior_breakdown,
            seed=self.record.behavior_rating,
        )
        context["class_assignment"] = self.class_assignment
        context["compilation"] = self.compilation
        context["student"] = self.student
        context["record"] = self.record
        context["subject_rows"] = subject_rows
        context["summary"] = summary
        context["attendance_percentage"] = attendance_percentage
        context["admission_number"] = _admission_number_for_student(self.student)
        student_analytics = build_student_academic_analytics(
            student=self.student,
            current_session=self.compilation.session,
            current_term=self.compilation.term,
        )
        weak_subjects = [row["subject"] for row in student_analytics.get("weak_subjects", [])]
        strongest_subjects = [
            row["subject"] for row in student_analytics.get("strongest_subjects", [])
        ]
        comment_bundle = _build_comment_bundle(
            student_name=self.student.get_full_name() or self.student.username,
            average_score=summary["average_score"],
            fail_count=summary["fail_count"],
            attendance_percentage=attendance_percentage,
            weak_subjects=weak_subjects,
            strongest_subjects=strongest_subjects,
            predicted_score=(student_analytics.get("prediction") or {}).get("score"),
            risk_label=(student_analytics.get("risk") or {}).get("label"),
            behavior_breakdown=behavior_breakdown,
        )
        context["student_analytics"] = student_analytics
        context["comment_bundle"] = comment_bundle
        context["suggested_comment"] = comment_bundle["teacher_comment"]
        context["teacher_suggestions"] = comment_bundle.get("teacher_suggestions", [])
        context["behavior_metrics"] = [
            {"code": code, "label": label, "value": behavior_breakdown.get(code, 3)}
            for code, label in _behavior_metric_fields()
        ]
        context["behavior_rating"] = _behavior_average_rating(behavior_breakdown)
        context["pending_subjects"] = self.pending_subjects
        context["form_stage_open"] = not self.pending_subjects
        context["back_url"] = f"{reverse('results:form-compilation')}?class_id={self.class_assignment.academic_class_id}"
        lock_reasons = []
        if (
            self.compilation.status not in {
                ClassCompilationStatus.DRAFT,
                ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
                ClassCompilationStatus.REJECTED_BY_VP,
            }
            and not self.request.user.has_role(ROLE_IT_MANAGER)
        ):
            lock_reasons.append("This class result has already moved beyond the form-teacher correction stage.")
        if not academic_context_is_current(self.compilation.session_id, self.compilation.term_id):
            lock_reasons.append(active_term_edit_message())
        if not request_user_can_edit_session(self.request.user, self.compilation.session):
            lock_reasons.append("This session is closed. Record is read-only.")
        if bool(self.pending_subjects) and not self.request.user.has_role(ROLE_IT_MANAGER):
            lock_reasons.append(
                "Form-teacher entry opens after the Dean approves every result subject: "
                + ", ".join(self.pending_subjects)
            )
        context["read_only_reasons"] = lock_reasons
        context["read_only_reason"] = lock_reasons[0] if lock_reasons else ""
        context["is_read_only"] = bool(lock_reasons)
        return context

    def post(self, request, *args, **kwargs):
        is_autosave = (
            request.POST.get("_autosave") == "1"
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        if not academic_context_is_current(self.compilation.session_id, self.compilation.term_id):
            message = active_term_edit_message()
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            return redirect(
                "results:form-compilation-student-detail",
                class_id=self.class_assignment.academic_class_id,
                student_id=self.student.id,
            )
        if self.pending_subjects and not request.user.has_role(ROLE_IT_MANAGER):
            message = (
                "Form-teacher entry is locked until the Dean approves every subject: "
                + ", ".join(self.pending_subjects)
            )
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=403)
            messages.error(request, message)
            return redirect(
                "results:form-compilation-student-detail",
                class_id=self.class_assignment.academic_class_id,
                student_id=self.student.id,
            )
        if (
            self.compilation.status not in {
                ClassCompilationStatus.DRAFT,
                ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
                ClassCompilationStatus.REJECTED_BY_VP,
            }
            and not request.user.has_role(ROLE_IT_MANAGER)
        ):
            message = "This compilation was submitted and is locked until management rejects it for correction."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return redirect(
                "results:form-compilation-student-detail",
                class_id=self.class_assignment.academic_class_id,
                student_id=self.student.id,
            )
        if not request_user_can_edit_session(request.user, self.compilation.session):
            message = "This session is closed. Record is read-only."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return redirect(
                "results:form-compilation-student-detail",
                class_id=self.class_assignment.academic_class_id,
                student_id=self.student.id,
            )

        action = (request.POST.get("action") or "").strip().lower()
        has_metric_inputs = any(
            f"behavior_{code}" in request.POST for code, _ in _behavior_metric_fields()
        )
        if has_metric_inputs:
            behavior_breakdown = _normalize_behavior_breakdown(
                {
                    code: request.POST.get(f"behavior_{code}")
                    for code, _ in _behavior_metric_fields()
                },
                seed=self.record.behavior_rating,
            )
            behavior = _behavior_average_rating(behavior_breakdown)
        else:
            try:
                behavior = int(request.POST.get("behavior_rating", self.record.behavior_rating or 3))
            except (TypeError, ValueError):
                behavior = self.record.behavior_rating or 3
            behavior = max(1, min(5, behavior))
            behavior_breakdown = _default_behavior_breakdown(seed=behavior)
        comment = (request.POST.get("teacher_comment") or "").strip()
        if action == "use_suggestion":
            selected_suggestion = (request.POST.get("selected_suggestion") or "").strip()
            if selected_suggestion:
                comment = selected_suggestion
            else:
                summary = self._summary(self._subject_rows())
                student_analytics = build_student_academic_analytics(
                    student=self.student,
                    current_session=self.compilation.session,
                    current_term=self.compilation.term,
                )
                advanced_bundle = build_advanced_result_comment_bundle(
                    average_score=summary["average_score"],
                    fail_count=summary["fail_count"],
                    attendance_percentage=self.record.attendance_percentage,
                    student_name=self.student.get_full_name() or self.student.username,
                    weak_subjects=[row["subject"] for row in student_analytics.get("weak_subjects", [])],
                    strongest_subjects=[
                        row["subject"] for row in student_analytics.get("strongest_subjects", [])
                    ],
                    predicted_score=(student_analytics.get("prediction") or {}).get("score"),
                    risk_label=(student_analytics.get("risk") or {}).get("label"),
                    behavior_breakdown=behavior_breakdown,
                )
                comment = advanced_bundle["teacher_comment"]
        elif action == "apply_teacher_suggestion":
            comment = (request.POST.get("selected_suggestion") or "").strip() or comment

        self.record.behavior_rating = behavior
        self.record.behavior_breakdown = behavior_breakdown
        self.record.teacher_comment = comment
        self.record.form_teacher_completed_at = timezone.now() if comment else None
        self.record.term_weight_kg = _nullable_decimal_from_post(request.POST.get("term_weight_kg"))
        if self.record.management_status == StudentResultManagementStatus.REJECTED:
            self.record.management_status = StudentResultManagementStatus.PENDING
            self.record.management_comment = ""
            self.record.management_actor = None
        self.record.club_membership = (request.POST.get("club_membership") or "").strip()
        self.record.office_held = (request.POST.get("office_held") or "").strip()
        self.record.notable_contribution = (request.POST.get("notable_contribution") or "").strip()
        self.record.doctor_remark = (request.POST.get("doctor_remark") or "").strip()
        self.record.height_start_cm = _nullable_decimal_from_post(request.POST.get("height_start_cm"))
        self.record.height_end_cm = _nullable_decimal_from_post(request.POST.get("height_end_cm"))
        self.record.weight_start_kg = _nullable_decimal_from_post(request.POST.get("weight_start_kg"))
        self.record.weight_end_kg = _nullable_decimal_from_post(request.POST.get("weight_end_kg"))
        try:
            medical_incidents = int((request.POST.get("medical_incidents") or "0").strip() or "0")
        except ValueError:
            medical_incidents = 0
        self.record.medical_incidents = max(medical_incidents, 0)
        self.record.save()
        profile = getattr(self.student, "student_profile", None)
        if profile is not None:
            profile.house = (request.POST.get("student_house") or "").strip()
            profile.community = (request.POST.get("student_community") or "").strip()
            profile.society = (request.POST.get("student_society") or "").strip()
            profile.save(update_fields=["house", "community", "society", "updated_at"])
        if is_autosave:
            return JsonResponse(
                {
                    "ok": True,
                    "behavior_rating": self.record.behavior_rating,
                    "comment_length": len(self.record.teacher_comment or ""),
                }
            )
        messages.success(request, "Cumulative record saved.")
        return redirect(
            "results:form-compilation-student-detail",
            class_id=self.class_assignment.academic_class_id,
            student_id=self.student.id,
        )


class HostelSupervisorPortalView(ResultsAccessMixin, TemplateView):
    template_name = "results/hostel_supervisor_portal.html"
    allowed_roles = {ROLE_HOSTEL_SUPERVISOR, ROLE_IT_MANAGER, ROLE_PRINCIPAL}

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, self.allowed_roles):
            messages.error(request, "Hostel supervisor access is restricted.")
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _window(self):
        return current_session_term()

    def _enrollments(self):
        session, term = self._window()
        if not session or not term:
            return StudentClassEnrollment.objects.none()
        return (
            StudentClassEnrollment.objects.select_related(
                "student",
                "student__student_profile",
                "academic_class",
                "academic_class__base_class",
            )
            .filter(session=session, is_active=True, student__is_active=True)
            .order_by(
                "student__student_profile__house",
                "student__student_profile__community",
                "academic_class__code",
                "student__last_name",
                "student__first_name",
                "student__student_profile__student_number",
            )
        )

    def _filtered_enrollments(self):
        rows = self._enrollments()
        house = (self.request.GET.get("house") or "").strip()
        community = (self.request.GET.get("community") or "").strip()
        query = (self.request.GET.get("q") or "").strip()
        class_id = (self.request.GET.get("class_id") or "").strip()
        if house:
            rows = rows.filter(student__student_profile__house__iexact=house)
        if community:
            rows = rows.filter(student__student_profile__community__iexact=community)
        if class_id:
            rows = rows.filter(academic_class_id=class_id)
        if query:
            rows = rows.filter(
                Q(student__first_name__icontains=query)
                | Q(student__last_name__icontains=query)
                | Q(student__student_profile__middle_name__icontains=query)
                | Q(student__student_profile__student_number__icontains=query)
            )
        return rows

    def _compilation_for_class(self, academic_class, *, create=False):
        session, term = self._window()
        if not session or not term or not academic_class:
            return None
        target_class = getattr(academic_class, "instructional_class", academic_class) or academic_class
        if create:
            form_assignment = (
                FormTeacherAssignment.objects.filter(
                    academic_class=target_class,
                    session=session,
                    is_active=True,
                )
                .select_related("teacher")
                .first()
            )
            compilation, _ = ClassResultCompilation.objects.get_or_create(
                academic_class=target_class,
                session=session,
                term=term,
                defaults={
                    "form_teacher": form_assignment.teacher if form_assignment else None,
                    "status": ClassCompilationStatus.DRAFT,
                },
            )
            return compilation
        return ClassResultCompilation.objects.filter(
            academic_class=target_class,
            session=session,
            term=term,
        ).first()

    def _record_for_student(self, *, student, academic_class, create=False):
        compilation = self._compilation_for_class(academic_class, create=create)
        if not compilation:
            return None
        if create:
            record, _ = ClassResultStudentRecord.objects.get_or_create(
                compilation=compilation,
                student=student,
                defaults={
                    "attendance_percentage": Decimal("100.00"),
                    "behavior_rating": 3,
                    "behavior_breakdown": _default_behavior_breakdown(seed=3),
                },
            )
            return record
        return ClassResultStudentRecord.objects.filter(compilation=compilation, student=student).first()

    def _choice_lists(self):
        session, term = self._window()
        enrollments = self._enrollments()
        houses = sorted(
            {
                (getattr(getattr(enrollment.student, "student_profile", None), "house", "") or "").strip()
                for enrollment in enrollments
            }
            - {""}
        )
        communities = sorted(
            {
                (getattr(getattr(enrollment.student, "student_profile", None), "community", "") or "").strip()
                for enrollment in enrollments
            }
            - {""}
        )
        classes = AcademicClass.objects.filter(
            student_enrollments__session=session,
            student_enrollments__is_active=True,
        ).distinct().order_by("code") if session else AcademicClass.objects.none()
        return houses, communities, classes

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        rows = []
        for enrollment in self._filtered_enrollments():
            student = enrollment.student
            profile = getattr(student, "student_profile", None)
            record = self._record_for_student(
                student=student,
                academic_class=enrollment.academic_class,
                create=False,
            )
            rows.append(
                {
                    "student": student,
                    "profile": profile,
                    "academic_class": enrollment.academic_class,
                    "record": record,
                    "house": (getattr(profile, "house", "") or "").strip() or "Unassigned",
                    "community": (getattr(profile, "community", "") or "").strip() or "Unassigned",
                    "society": (getattr(profile, "society", "") or "").strip() or "-",
                    "comment": getattr(record, "hostel_supervisor_comment", "") if record else "",
                }
            )
        houses, communities, classes = self._choice_lists()
        context.update(
            {
                "session": session,
                "term": term,
                "rows": rows,
                "houses": houses,
                "communities": communities,
                "classes": classes,
                "selected_house": (self.request.GET.get("house") or "").strip(),
                "selected_community": (self.request.GET.get("community") or "").strip(),
                "selected_class_id": (self.request.GET.get("class_id") or "").strip(),
                "query": (self.request.GET.get("q") or "").strip(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        student = get_object_or_404(User, pk=request.POST.get("student_id"), is_active=True)
        academic_class = get_object_or_404(AcademicClass, pk=request.POST.get("class_id"))
        record = self._record_for_student(student=student, academic_class=academic_class, create=True)
        record.hostel_supervisor_comment = (request.POST.get("hostel_supervisor_comment") or "").strip()
        record.save(update_fields=["hostel_supervisor_comment", "updated_at"])
        messages.success(request, "Hostel supervisor comment saved.")
        query = request.GET.urlencode()
        url = reverse("results:hostel-supervisor")
        return redirect(f"{url}?{query}" if query else url)


class ResultApprovalClassListView(ResultsAccessMixin, TemplateView):
    template_name = "results/approval_class_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER}):
            messages.error(request, "Results approval access is restricted to VP or IT Manager.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def _window(self):
        session, term = current_session_term()
        return session, term

    def _compilation_queryset(self):
        session, term = self._window()
        if not session or not term:
            return ClassResultCompilation.objects.none()
        return ClassResultCompilation.objects.select_related(
            "academic_class",
            "session",
            "term",
            "form_teacher",
            "vp_actor",
            "principal_override_actor",
        ).filter(
            session=session,
            term=term,
        )

    def _class_rows(self):
        session, term = self._window()
        if not session or not term:
            return []
        search_query = (self.request.GET.get("q") or "").strip()
        class_qs = AcademicClass.objects.filter(
            is_active=True,
            base_class__isnull=True,
        ).order_by("code")
        if search_query:
            class_qs = class_qs.filter(
                Q(code__icontains=search_query) | Q(display_name__icontains=search_query)
            )
        class_rows = list(class_qs)
        compilations = _ensure_class_compilation_rows(
            session=session,
            term=term,
            class_qs=class_rows,
        )
        rows = []
        for academic_class in class_rows:
            compilation = compilations.get(academic_class.id)
            student_count = StudentClassEnrollment.objects.filter(
                session=session,
                is_active=True,
                academic_class_id__in=academic_class.cohort_class_ids(),
            ).count()
            rows.append(
                {
                    "academic_class": academic_class,
                    "compilation": compilation,
                    "student_count": student_count,
                    "status_label": (
                        compilation.get_status_display() if compilation else "Not Submitted"
                    ),
                    "detail_url": (
                        reverse(
                            "results:approval-class-detail",
                            kwargs={"compilation_id": compilation.id},
                        )
                        if compilation
                        else ""
                    ),
                }
            )
        return rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        context["current_session"] = session
        context["current_term"] = term
        context["class_rows"] = self._class_rows()
        context["search_query"] = (self.request.GET.get("q") or "").strip()
        context["principal_override_enabled"] = False
        return context

    def post(self, request, *args, **kwargs):
        session, term = self._window()
        if not session or not term:
            messages.error(request, "Current session/term is not configured.")
            return redirect("results:approval-class-list")
        if not session_is_open_for_edits(session):
            messages.error(request, "This session is closed. Approval actions are read-only.")
            return redirect("results:approval-class-list")

        action = (request.POST.get("action") or "").strip().lower()
        if action not in {"publish_selected", "reject_selected"}:
            messages.error(request, "Invalid approval action.")
            return redirect("results:approval-class-list")

        selected_ids = []
        for raw_id in request.POST.getlist("compilation_ids"):
            try:
                selected_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue
        if not selected_ids:
            messages.error(request, "Select at least one class compilation.")
            return redirect("results:approval-class-list")

        selected_rows = list(
            self._compilation_queryset().filter(id__in=selected_ids)
        )
        if not selected_rows:
            messages.error(request, "No valid class compilation selected.")
            return redirect("results:approval-class-list")

        processed = 0
        skipped = 0
        reject_comment = (
            (request.POST.get("reject_comment") or "").strip()
            or "Returned for correction from approval queue."
        )

        for compilation in selected_rows:
            sheets_qs = ResultSheet.objects.filter(
                academic_class=_instructional_class(compilation.academic_class),
                session=compilation.session,
                term=compilation.term,
            )
            if action == "publish_selected":
                if not _publish_allowed_for_actor(actor=request.user, compilation=compilation):
                    skipped += 1
                    continue
                with transaction.atomic():
                    mark_compilation_published(
                        compilation,
                        request.user,
                        principal_override=False,
                    )
                    publish_sheet_qs = sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED)
                    action_code = "IT_FINAL_PUBLISH"
                    action_comment = "Bulk final publication by IT Manager."
                    transition_class_sheet_set(
                        sheets_qs=publish_sheet_qs,
                        to_status=ResultSheetStatus.PUBLISHED,
                        actor=request.user,
                        action=action_code,
                        comment=action_comment,
                    )
                    log_results_approval(
                        actor=request.user,
                        request=request,
                        metadata={
                            "action": action_code,
                            "compilation_id": str(compilation.id),
                            "class_id": str(compilation.academic_class_id),
                            "bulk": True,
                        },
                    )
                    notify_results_published(
                        compilation=compilation,
                        actor=request.user,
                        request=request,
                    )
                processed += 1
                continue

            if not _reject_allowed_for_actor(actor=request.user, compilation=compilation):
                skipped += 1
                continue
            with transaction.atomic():
                mark_compilation_rejected_by_vp(
                    compilation,
                    request.user,
                    reject_comment,
                    principal_override=False,
                )
                reject_sheet_qs = sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP)
                action_code = "VP_REJECT"
                transition_class_sheet_set(
                    sheets_qs=reject_sheet_qs,
                    to_status=ResultSheetStatus.REJECTED_BY_VP,
                    actor=request.user,
                    action=action_code,
                    comment=reject_comment,
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": action_code,
                        "compilation_id": str(compilation.id),
                        "class_id": str(compilation.academic_class_id),
                        "bulk": True,
                    },
                )
            processed += 1

        action_label = "published" if action == "publish_selected" else "rejected"
        if processed:
            messages.success(request, f"{processed} class compilation(s) {action_label}.")
        if skipped:
            messages.warning(
                request,
                f"{skipped} class compilation(s) skipped because current status does not allow this action.",
            )
        return redirect("results:approval-class-list")


class ResultApprovalClassDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/approval_class_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER}):
            messages.error(request, "Results approval access is restricted to VP or IT Manager.")
            return redirect("results:grade-entry-home")
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related(
                "academic_class",
                "session",
                "term",
                "form_teacher",
                "vp_actor",
                "principal_override_actor",
            ),
            pk=kwargs["compilation_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        search_query = (self.request.GET.get("q") or "").strip()
        enrollments = StudentClassEnrollment.objects.select_related(
            "student",
            "student__student_profile",
        ).filter(
            academic_class_id__in=_cohort_class_ids(self.compilation.academic_class),
            session=self.compilation.session,
            is_active=True,
        )
        if search_query:
            enrollments = enrollments.filter(
                Q(student__first_name__icontains=search_query)
                | Q(student__last_name__icontains=search_query)
                | Q(student__username__icontains=search_query)
                | Q(student__student_profile__student_number__icontains=search_query)
            )
        enrollments = list(enrollments.order_by(
            "student__last_name",
            "student__first_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        ))
        student_ids = [row.student_id for row in enrollments]
        approval_score_queryset = StudentSubjectScore.objects.filter(
            result_sheet__academic_class=_instructional_class(self.compilation.academic_class),
            result_sheet__session=self.compilation.session,
            result_sheet__term=self.compilation.term,
            student_id__in=student_ids,
        )
        approval_score_queryset = exclude_non_result_subjects(
            approval_score_queryset,
            field_name="result_sheet__subject",
        )
        score_map = {
            row["student_id"]: row
            for row in approval_score_queryset
            .values("student_id")
            .annotate(subject_count=Count("id"), total_score=Sum("grand_total"))
        }
        record_map = {
            row.student_id: row
            for row in self.compilation.student_records.select_related("student")
        }
        ca23_matrix = _class_ca_matrix(
            session=self.compilation.session,
            term=self.compilation.term,
            academic_class=self.compilation.academic_class,
            component_key="ca23",
        )
        ca23_row_map = {
            row["student"].id: row for row in ca23_matrix.get("rows", [])
        }
        student_rows = []
        for enrollment in enrollments:
            student = enrollment.student
            score_info = score_map.get(student.id) or {}
            actual_subject_count = int(score_info.get("subject_count") or 0)
            subject_count = actual_subject_count
            total_score = _score_decimal(score_info.get("total_score") or 0)
            record = record_map.get(student.id)
            ca23_row = ca23_row_map.get(student.id) or {}
            student_rows.append(
                {
                    "student": student,
                    "admission_number": _admission_number_for_student(student),
                    "subject_count": subject_count,
                    "actual_subject_count": actual_subject_count,
                    "average_score": _average_to_decimal(total_score, subject_count),
                    "ca23_total": ca23_row.get("total", DECIMAL_ZERO),
                    "ca23_average": ca23_row.get("average", DECIMAL_ZERO),
                    "ca23_position": ca23_row.get("position", "-"),
                    "attendance_percentage": _score_decimal(record.attendance_percentage if record else 0),
                    "behavior_rating": record.behavior_rating if record else 3,
                    "management_status": (
                        record.get_management_status_display()
                        if record
                        else StudentResultManagementStatus.PENDING.label
                    ),
                    "detail_url": reverse(
                        "results:approval-student-detail",
                        kwargs={
                            "compilation_id": self.compilation.id,
                            "student_id": student.id,
                        },
                    ),
                }
            )

        context["compilation"] = self.compilation
        context["student_rows"] = student_rows
        context["ca23_missing_count"] = len(ca23_matrix.get("missing_cells", []))
        context["search_query"] = search_query
        context["back_url"] = reverse("results:approval-class-list")
        context["can_publish"] = _publish_allowed_for_actor(actor=self.request.user, compilation=self.compilation)
        context["can_approve_for_it"] = _vp_approval_allowed(actor=self.request.user, compilation=self.compilation)
        context["is_it_manager"] = self.request.user.has_role(ROLE_IT_MANAGER)
        context["can_reject"] = _reject_allowed_for_actor(actor=self.request.user, compilation=self.compilation)
        context["rejected_student_count"] = self.compilation.student_records.filter(
            management_status=StudentResultManagementStatus.REJECTED
        ).count()
        context["reviewed_student_count"] = self.compilation.student_records.filter(
            management_status=StudentResultManagementStatus.REVIEWED
        ).count()
        return context

    def post(self, request, *args, **kwargs):
        if not session_is_open_for_edits(self.compilation.session):
            messages.error(request, "This session is closed. Result management is read-only.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

        action = (request.POST.get("action") or "").strip().lower()
        if action not in {"approve_for_it", "publish_class", "reject_class"}:
            messages.error(request, "Invalid class management action.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        )

        if action == "approve_for_it":
            if not _vp_approval_allowed(actor=request.user, compilation=self.compilation):
                messages.error(
                    request,
                    "VP approval requires every student record to be reviewed with a principal comment.",
                )
                return redirect("results:approval-class-detail", compilation_id=self.compilation.id)
            approval_comment = (request.POST.get("publish_comment") or "").strip()
            mark_compilation_approved_by_vp(
                self.compilation,
                request.user,
                comment=approval_comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "VP_APPROVE_FOR_IT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            messages.success(request, "Class approved and forwarded to IT Manager for final publishing.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

        if action == "publish_class":
            if not _publish_allowed_for_actor(actor=request.user, compilation=self.compilation):
                messages.error(request, "IT publication opens only after VP has saved principal comments and forwarded the class.")
                return redirect("results:approval-class-detail", compilation_id=self.compilation.id)
            if self.compilation.student_records.filter(
                management_status=StudentResultManagementStatus.REJECTED
            ).exists():
                messages.error(request, "Resolve rejected student records before publishing this class.")
                return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

            publish_comment = (request.POST.get("publish_comment") or "").strip()
            with transaction.atomic():
                mark_compilation_published(
                    self.compilation,
                    request.user,
                    principal_override=False,
                    comment=publish_comment,
                )
                transition_class_sheet_set(
                    sheets_qs=sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED),
                    to_status=ResultSheetStatus.PUBLISHED,
                    actor=request.user,
                    action="IT_FINAL_PUBLISH",
                    comment=publish_comment or "Final publication by IT Manager.",
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "IT_FINAL_PUBLISH",
                        "compilation_id": str(self.compilation.id),
                        "class_id": str(self.compilation.academic_class_id),
                    },
                )
                notify_results_published(
                    compilation=self.compilation,
                    actor=request.user,
                    request=request,
                )
            messages.success(request, "Class results published.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

        if not _reject_allowed_for_actor(actor=request.user, compilation=self.compilation):
            messages.error(request, "This class cannot be rejected in its current state.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)
        reject_comment = (
            (request.POST.get("reject_comment") or "").strip()
            or "Returned for correction from result management."
        )
        with transaction.atomic():
            mark_compilation_rejected_by_vp(
                self.compilation,
                request.user,
                reject_comment,
                principal_override=False,
            )
            transition_class_sheet_set(
                sheets_qs=sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP),
                to_status=ResultSheetStatus.REJECTED_BY_VP,
                actor=request.user,
                action="VP_REJECT",
                comment=reject_comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "IT_OVERRIDE_REJECT" if is_it_manager else "VP_REJECT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
        messages.success(request, "Class returned for correction.")
        return redirect("results:approval-class-detail", compilation_id=self.compilation.id)


class ResultApprovalStudentDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/approval_student_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER}):
            messages.error(request, "Results approval access is restricted to VP or IT Manager.")
            return redirect("results:grade-entry-home")
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related(
                "academic_class",
                "session",
                "term",
            ),
            pk=kwargs["compilation_id"],
        )
        enrollment = StudentClassEnrollment.objects.select_related(
            "student",
            "student__student_profile",
        ).filter(
            academic_class_id__in=_cohort_class_ids(self.compilation.academic_class),
            session=self.compilation.session,
            student_id=kwargs["student_id"],
            is_active=True,
        ).first()
        if enrollment:
            self.student = enrollment.student
        else:
            record = ClassResultStudentRecord.objects.select_related(
                "student",
                "student__student_profile",
            ).filter(
                compilation=self.compilation,
                student_id=kwargs["student_id"],
            ).first()
            if not record:
                messages.error(request, "Student not found in this class compilation.")
                return redirect(
                    "results:approval-class-detail",
                    compilation_id=self.compilation.id,
                )
            self.student = record.student
        self.record, _ = ClassResultStudentRecord.objects.get_or_create(
            compilation=self.compilation,
            student=self.student,
            defaults={
                "behavior_rating": 3,
                "behavior_breakdown": _default_behavior_breakdown(seed=3),
            },
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_result_payload_for_compilation(
            compilation=self.compilation,
            student=self.student,
        )
        context["compilation"] = self.compilation
        context["payload"] = payload
        context["record"] = self.record
        context["principal_suggestion"] = payload["comment_bundle"]["principal_comment"]
        context["principal_suggestions"] = payload["comment_bundle"].get("principal_suggestions", [])
        context["can_manage_principal_comment"] = (
            self.request.user.has_role(ROLE_VP)
            and self.compilation.status == ClassCompilationStatus.SUBMITTED_TO_VP
            and session_is_open_for_edits(self.compilation.session)
        )
        context["back_url"] = reverse(
            "results:approval-class-detail",
            kwargs={"compilation_id": self.compilation.id},
        )
        return context

    def post(self, request, *args, **kwargs):
        if not session_is_open_for_edits(self.compilation.session):
            messages.error(request, "This session is closed. Result management is read-only.")
            return redirect(
                "results:approval-student-detail",
                compilation_id=self.compilation.id,
                student_id=self.student.id,
            )

        action = (request.POST.get("action") or "").strip().lower()
        if not (
            request.user.has_role(ROLE_VP)
            and self.compilation.status == ClassCompilationStatus.SUBMITTED_TO_VP
        ):
            messages.error(request, "Only the VP can enter principal comments while the class is awaiting VP review.")
            return redirect(
                "results:approval-student-detail",
                compilation_id=self.compilation.id,
                student_id=self.student.id,
            )
        principal_comment = (request.POST.get("principal_comment") or "").strip()
        review_comment = (request.POST.get("review_comment") or "").strip()
        payload = _student_result_payload_for_compilation(
            compilation=self.compilation,
            student=self.student,
        )
        if action == "use_principal_suggestion":
            principal_comment = (
                (request.POST.get("selected_principal_suggestion") or "").strip()
                or payload["comment_bundle"]["principal_comment"]
            )
            action = "save_principal_comment"
        elif action == "apply_principal_suggestion":
            principal_comment = (request.POST.get("selected_principal_suggestion") or "").strip() or principal_comment
            action = "save_principal_comment"

        if action == "save_principal_comment":
            if (
                (self.record.principal_comment or "").strip()
                and self.record.management_actor_id
                and self.record.management_actor_id != request.user.id
            ):
                messages.error(
                    request,
                    "Principal comment is already saved by another authorized reviewer and cannot be changed here.",
                )
                return redirect(
                    "results:approval-student-detail",
                    compilation_id=self.compilation.id,
                    student_id=self.student.id,
                )
            self.record.principal_comment = principal_comment
            self.record.management_status = StudentResultManagementStatus.REVIEWED
            self.record.management_comment = ""
            self.record.management_actor = request.user
            self.record.save(
                update_fields=[
                    "principal_comment",
                    "management_status",
                    "management_comment",
                    "management_actor",
                    "updated_at",
                ]
            )
            messages.success(request, "Principal comment saved.")
        elif action == "reject_student":
            if not review_comment:
                messages.error(request, "Rejection note is required before returning this student record.")
                return redirect(
                    "results:approval-student-detail",
                    compilation_id=self.compilation.id,
                    student_id=self.student.id,
                )
            self.record.principal_comment = principal_comment
            self.record.management_status = StudentResultManagementStatus.REJECTED
            self.record.management_comment = review_comment
            self.record.management_actor = request.user
            self.record.save(
                update_fields=[
                    "principal_comment",
                    "management_status",
                    "management_comment",
                    "management_actor",
                    "updated_at",
                ]
            )
            messages.success(request, "Student result returned for correction.")
        else:
            messages.error(request, "Invalid student management action.")

        return redirect(
            "results:approval-student-detail",
            compilation_id=self.compilation.id,
            student_id=self.student.id,
        )


class DeanTermReviewListView(ResultsAccessMixin, TemplateView):
    template_name = "results/dean_term_review_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN, ROLE_IT_MANAGER}):
            messages.error(request, "Dean term review access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        compilations = ClassResultCompilation.objects.select_related(
            "academic_class", "session", "term", "form_teacher", "vp_actor"
        ).filter(
            session=session,
            term=term,
            status__in=[
                ClassCompilationStatus.SUBMITTED_TO_DEAN_FINAL,
                ClassCompilationStatus.APPROVED_BY_DEAN_FINAL,
                ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
            ],
        )
        compilations = exclude_external_exam_classes_for_term(compilations, term, field_name="academic_class")
        status_filter = (self.request.GET.get("status") or "submitted").strip().lower()
        class_filter = (self.request.GET.get("class_id") or "").strip()
        status_map = {
            "submitted": ClassCompilationStatus.SUBMITTED_TO_DEAN_FINAL,
            "approved": ClassCompilationStatus.APPROVED_BY_DEAN_FINAL,
            "rejected": ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
        }
        if status_filter in status_map:
            compilations = compilations.filter(status=status_map[status_filter])
        elif status_filter != "all":
            status_filter = "submitted"
            compilations = compilations.filter(status=ClassCompilationStatus.SUBMITTED_TO_DEAN_FINAL)
        if class_filter.isdigit():
            compilations = compilations.filter(academic_class_id=int(class_filter))
        available_classes = exclude_external_exam_classes_for_term(
            ClassResultCompilation.objects.filter(
                session=session,
                term=term,
                status__in=[
                    ClassCompilationStatus.SUBMITTED_TO_DEAN_FINAL,
                    ClassCompilationStatus.APPROVED_BY_DEAN_FINAL,
                    ClassCompilationStatus.REJECTED_BY_DEAN_FINAL,
                ],
            ),
            term,
            field_name="academic_class",
        ).values("academic_class_id", "academic_class__code").distinct().order_by("academic_class__code")
        context["filter_status"] = status_filter
        context["filter_class_id"] = class_filter
        context["available_classes"] = available_classes
        context["compilation_count"] = compilations.count()
        context["compilations"] = compilations.order_by("-updated_at", "academic_class__code")[:5]
        context["current_session"] = session
        context["current_term"] = term
        return context


class DeanTermReviewDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/dean_term_review_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN, ROLE_IT_MANAGER}):
            messages.error(request, "Dean term review access required.")
            return redirect("results:grade-entry-home")
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related(
                "academic_class", "session", "term", "form_teacher"
            ),
            pk=self.kwargs["compilation_id"],
        )
        if class_is_external_exam_class_for_term(self.compilation.academic_class, self.compilation.term):
            messages.error(request, "JS3 and SS3 are excluded from Third Term Dean term review.")
            return redirect("results:dean-term-review-list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        records = list(
            self.compilation.student_records.select_related(
                "student", "student__student_profile"
            ).order_by(
                "student__last_name",
                "student__first_name",
                "student__student_profile__middle_name",
                "student__student_profile__student_number",
                "student__username",
            )
        )
        score_queryset = StudentSubjectScore.objects.filter(
            result_sheet__academic_class=_instructional_class(self.compilation.academic_class),
            result_sheet__session=self.compilation.session,
            result_sheet__term=self.compilation.term,
            student_id__in=[record.student_id for record in records],
        )
        score_queryset = exclude_non_result_subjects(score_queryset, field_name="result_sheet__subject")
        score_summary = {
            row["student_id"]: row
            for row in score_queryset.values("student_id").annotate(
                subject_count=Count("id"),
                total_score=Sum("grand_total"),
            )
        }
        context["compilation"] = self.compilation
        context["records"] = [
            {
                "record": record,
                "student": record.student,
                "admission_number": _admission_number_for_student(record.student),
                "summary": score_summary.get(record.student_id) or {},
                "term_pdf_url": reverse(
                    "pdfs:staff-term-report-download",
                    kwargs={
                        "compilation_id": self.compilation.id,
                        "student_id": record.student_id,
                    },
                ),
            }
            for record in records
        ]
        context["sheets"] = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        ).select_related("subject").order_by("subject__name")
        context["action_form"] = ResultActionForm()
        context["reject_form"] = RejectActionForm()
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_DEAN):
            messages.error(request, "Only the Dean can approve or reject the Dean term review.")
            return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)
        if not session_is_open_for_edits(self.compilation.session):
            messages.error(request, "This session is closed. Dean term review is read-only.")
            return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)
        action = (request.POST.get("action") or "").strip().lower()
        if self.compilation.status != ClassCompilationStatus.SUBMITTED_TO_DEAN_FINAL:
            messages.error(request, "Only compilations submitted to Dean term review can be actioned here.")
            return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)
        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        )
        if action == "approve":
            form = ResultActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Unable to read approval comment.")
                return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)
            with transaction.atomic():
                mark_compilation_approved_by_dean_final(
                    self.compilation,
                    request.user,
                    comment=form.cleaned_data["comment"],
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "DEAN_TERM_REVIEW_APPROVE",
                        "compilation_id": str(self.compilation.id),
                        "class_id": str(self.compilation.academic_class_id),
                    },
                )
            messages.success(request, "Dean term review approved. Class forwarded to VP for principal comments.")
        elif action == "reject":
            form = RejectActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Rejection reason is required.")
                return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)
            comment = form.cleaned_data["comment"]
            with transaction.atomic():
                mark_compilation_rejected_by_dean_final(self.compilation, request.user, comment)
                transition_class_sheet_set(
                    sheets_qs=sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP),
                    to_status=ResultSheetStatus.APPROVED_BY_DEAN,
                    actor=request.user,
                    action="DEAN_TERM_REVIEW_REJECT",
                    comment=comment,
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "DEAN_TERM_REVIEW_REJECT",
                        "compilation_id": str(self.compilation.id),
                        "class_id": str(self.compilation.academic_class_id),
                    },
                )
            messages.success(request, "Compilation rejected back to form teacher.")
        else:
            messages.error(request, "Invalid Dean term review action.")
        return redirect("results:dean-term-review-detail", compilation_id=self.compilation.id)


class VPReviewListView(ResultsAccessMixin, TemplateView):
    template_name = "results/vp_review_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "VP review access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        context["compilations"] = ClassResultCompilation.objects.select_related(
            "academic_class", "session", "term", "form_teacher"
        ).filter(
            session=session,
            term=term,
            status=ClassCompilationStatus.SUBMITTED_TO_VP,
        ).order_by("-updated_at")
        return context


class VPReviewDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/vp_review_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_VP):
            messages.error(request, "VP review access required.")
            return redirect("results:grade-entry-home")
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=self.kwargs["compilation_id"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["compilation"] = self.compilation
        records = list(
            self.compilation.student_records.select_related("student", "student__student_profile").order_by(
                "student__first_name",
                "student__last_name",
                "student__student_profile__middle_name",
                "student__student_profile__student_number",
                "student__username",
            )
        )
        for record in records:
            record.principal_comment_url = reverse(
                "results:approval-student-detail",
                kwargs={
                    "compilation_id": self.compilation.id,
                    "student_id": record.student_id,
                },
            )
        context["records"] = records
        context["can_export_pdfs"] = can_staff_download_term_report(
            user=self.request.user,
            compilation=self.compilation,
        )
        context["sheets"] = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        ).select_related("subject").order_by("subject__name")
        context["action_form"] = ResultActionForm()
        context["reject_form"] = RejectActionForm()
        return context

    def post(self, request, *args, **kwargs):
        if not session_is_open_for_edits(self.compilation.session):
            messages.error(request, "This session is closed. VP actions are read-only.")
            return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
        action = request.POST.get("action")
        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        )
        if action in {"approve", "publish"}:
            if self.compilation.status != ClassCompilationStatus.SUBMITTED_TO_VP:
                messages.error(request, "Only submitted compilations can be approved.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            form = ResultActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Unable to read approval comment.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            if not _vp_approval_allowed(actor=request.user, compilation=self.compilation):
                messages.error(
                    request,
                    "Review every student and enter a principal comment before VP approval.",
                )
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            approval_comment = form.cleaned_data["comment"]
            mark_compilation_approved_by_vp(
                self.compilation,
                request.user,
                comment=approval_comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "VP_APPROVE_FOR_IT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            messages.success(request, "Results approved and forwarded to IT Manager for final publishing.")
        elif action == "reject":
            if self.compilation.status != ClassCompilationStatus.SUBMITTED_TO_VP:
                messages.error(request, "Only submitted compilations can be rejected.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            form = RejectActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Rejection reason is required.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            comment = form.cleaned_data["comment"]
            mark_compilation_rejected_by_vp(self.compilation, request.user, comment)
            transition_class_sheet_set(
                sheets_qs=sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP),
                to_status=ResultSheetStatus.REJECTED_BY_VP,
                actor=request.user,
                action="VP_REJECT",
                comment=comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "VP_REJECT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            messages.success(request, "Compilation rejected back to form teacher.")
        else:
            messages.error(request, "Invalid VP action.")
        return redirect("results:vp-review-detail", compilation_id=self.compilation.id)


class PrincipalOversightView(ResultsAccessMixin, TemplateView):
    template_name = "results/principal_oversight.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_IT_MANAGER):
            messages.error(request, "IT Manager override access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        context["compilations"] = ClassResultCompilation.objects.select_related(
            "academic_class", "session", "term", "form_teacher", "vp_actor"
        ).filter(session=session, term=term).order_by("-updated_at")
        context["override_enabled"] = principal_override_enabled()
        return context


class PrincipalOverrideView(ResultsAccessMixin, TemplateView):
    template_name = "results/principal_override.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_IT_MANAGER):
            messages.error(request, "IT Manager override access required.")
            return redirect("results:grade-entry-home")
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=self.kwargs["compilation_id"],
        )
        if not principal_override_enabled():
            messages.error(request, "Principal override is disabled by policy.")
            return redirect("results:principal-oversight")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["compilation"] = self.compilation
        context["action_form"] = ResultActionForm()
        context["reject_form"] = RejectActionForm()
        return context

    def post(self, request, *args, **kwargs):
        if not session_is_open_for_edits(self.compilation.session):
            messages.error(request, "This session is closed. Override actions are read-only.")
            return redirect("results:principal-override", compilation_id=self.compilation.id)
        action = request.POST.get("action")
        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        )
        if action == "override_publish":
            if self.compilation.status == ClassCompilationStatus.PUBLISHED:
                messages.error(
                    request,
                    "This compilation is already published.",
                )
                return redirect("results:principal-override", compilation_id=self.compilation.id)
            form = ResultActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Unable to read publish comment.")
                return redirect("results:principal-override", compilation_id=self.compilation.id)
            publish_comment = form.cleaned_data["comment"]
            mark_compilation_published(
                self.compilation,
                request.user,
                principal_override=True,
                comment=publish_comment,
            )
            transition_class_sheet_set(
                sheets_qs=sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED),
                to_status=ResultSheetStatus.PUBLISHED,
                actor=request.user,
                action="IT_OVERRIDE_PUBLISH",
                comment=publish_comment or "IT Manager override publish.",
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "IT_OVERRIDE_PUBLISH",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            notify_results_published(
                compilation=self.compilation,
                actor=request.user,
                request=request,
            )
            messages.success(request, "IT Manager override publish completed.")
        elif action == "override_reject":
            if self.compilation.status not in {
                ClassCompilationStatus.SUBMITTED_TO_VP,
                ClassCompilationStatus.APPROVED_BY_VP,
                ClassCompilationStatus.PUBLISHED,
            }:
                messages.error(
                    request,
                    "Override reject requires submitted or published compilation state.",
                )
                return redirect("results:principal-override", compilation_id=self.compilation.id)
            form = RejectActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Rejection reason is required.")
                return redirect("results:principal-override", compilation_id=self.compilation.id)
            comment = form.cleaned_data["comment"]
            mark_compilation_rejected_by_vp(
                self.compilation,
                request.user,
                comment,
                principal_override=True,
            )
            transition_class_sheet_set(
                sheets_qs=sheets_qs.exclude(status=ResultSheetStatus.REJECTED_BY_VP),
                to_status=ResultSheetStatus.REJECTED_BY_VP,
                actor=request.user,
                action="IT_OVERRIDE_REJECT",
                comment=comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "IT_OVERRIDE_REJECT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            messages.success(request, "Principal override reject completed.")
        else:
            messages.error(request, "Invalid principal override action.")
        return redirect("results:principal-override", compilation_id=self.compilation.id)


class ResultSettingsView(ResultsAccessMixin, TemplateView):
    template_name = "results/result_settings.html"
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL}

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, self.allowed_roles):
            messages.error(request, "Result settings access is restricted.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _finance_profile():
        profile = FinanceInstitutionProfile.objects.first()
        if profile:
            return profile
        return FinanceInstitutionProfile.objects.create(updated_by=None)

    @staticmethod
    def _school_profile():
        return SchoolProfile.load()

    @staticmethod
    def _principal_user():
        return (
            User.objects.filter(Q(primary_role__code=ROLE_PRINCIPAL) | Q(secondary_roles__code=ROLE_PRINCIPAL))
            .distinct()
            .order_by("username")
            .first()
        )

    def _principal_signature_record(self, principal_user=None):
        principal_user = principal_user or self._principal_user()
        if principal_user is None:
            return None
        return PrincipalSignature.objects.filter(user=principal_user).first()

    @staticmethod
    def _signature_file_from_data_url(data_url: str):
        header, encoded = data_url.split(",", 1)
        extension = "png"
        if "image/jpeg" in header or "image/jpg" in header:
            extension = "jpg"
        try:
            decoded = base64.b64decode(encoded)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Invalid signature image encoding.") from exc
        if not decoded:
            raise ValueError("Signature drawing is empty.")
        return ContentFile(decoded, name=f"principal-signature-{uuid.uuid4().hex}.{extension}")

    def _can_manage(self):
        return self.request.user.has_role(ROLE_IT_MANAGER)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metric_rows = list(BehaviorMetricSetting.objects.order_by("sort_order", "label"))
        finance_profile = self._finance_profile()
        school_profile = self._school_profile()
        principal_user = self._principal_user()
        principal_signature_record = self._principal_signature_record(principal_user)
        setup_state = get_setup_state()
        context["metric_rows"] = metric_rows
        context["active_metric_count"] = len([row for row in metric_rows if row.is_active])
        context["next_sort_order"] = (metric_rows[-1].sort_order + 10) if metric_rows else 10
        context["finance_profile"] = finance_profile
        context["school_profile"] = school_profile
        context["school_profile_form"] = kwargs.get("school_profile_form") or SchoolProfileForm(instance=school_profile)
        context["principal_signature_form"] = kwargs.get("principal_signature_form") or PrincipalSignatureForm()
        context["principal_signature_record"] = principal_signature_record
        context["principal_signature_owner"] = principal_user
        context["can_manage_result_settings"] = self._can_manage()
        grade_scale_rows = list(GradeScale.objects.filter(is_default=True).order_by("sort_order", "grade"))
        context["grade_scale_rows"] = grade_scale_rows
        context["grade_scale_next_sort_order"] = (grade_scale_rows[-1].sort_order + 1) if grade_scale_rows else 1
        context["setup_state"] = setup_state
        context["setup_summary"] = {
            "main_levels": AcademicClass.objects.filter(is_active=True, base_class__isnull=True).count(),
            "arm_classes": AcademicClass.objects.filter(is_active=True, base_class__isnull=False).count(),
            "subjects": Subject.objects.filter(is_active=True).count(),
            "grade_bands": len(grade_scale_rows),
        }
        context["setup_shortcuts"] = [
            {"label": "Session & Calendar", "url": reverse("setup_wizard:session-term-manage")},
            {"label": "Classes", "url": reverse("academics:it-classes")},
            {"label": "Subjects", "url": reverse("academics:it-subjects")},
            {"label": "Class-Subject Mapping", "url": reverse("academics:it-class-subjects")},
            {"label": "Teacher Assignments", "url": reverse("academics:it-teacher-subject-assignments")},
            {"label": "Form Teachers", "url": reverse("academics:it-form-teacher-assignments")},
        ]
        return context

    def post(self, request, *args, **kwargs):
        if not self._can_manage():
            messages.error(request, "Only the IT Manager can change result settings.")
            return redirect("results:result-settings")

        action = (request.POST.get("action") or "").strip().lower()
        if action == "create_metric":
            raw_code = (request.POST.get("code") or "").strip().lower()
            code = "".join(ch if ch.isalnum() else "_" for ch in raw_code).strip("_")
            label = (request.POST.get("label") or "").strip()
            try:
                sort_order = int((request.POST.get("sort_order") or "10").strip())
            except ValueError:
                sort_order = 10
            if not code or not label:
                messages.error(request, "Metric code and label are required.")
                return redirect("results:result-settings")
            if BehaviorMetricSetting.objects.filter(code=code).exists():
                messages.error(request, f"Metric code '{code}' already exists.")
                return redirect("results:result-settings")
            metric = BehaviorMetricSetting(
                code=code,
                label=label,
                sort_order=max(sort_order, 1),
                is_active=True,
                created_by=request.user,
            )
            metric.full_clean()
            metric.save()
            messages.success(request, "Behavior metric added.")
            return redirect("results:result-settings")

        if action == "update_metric":
            metric = get_object_or_404(BehaviorMetricSetting, pk=request.POST.get("metric_id"))
            label = (request.POST.get("label") or "").strip()
            if not label:
                messages.error(request, "Metric label cannot be empty.")
                return redirect("results:result-settings")
            try:
                sort_order = int((request.POST.get("sort_order") or str(metric.sort_order)).strip())
            except ValueError:
                sort_order = metric.sort_order
            metric.label = label
            metric.sort_order = max(sort_order, 1)
            metric.is_active = bool(request.POST.get("is_active"))
            metric.full_clean()
            metric.save(update_fields=["label", "sort_order", "is_active", "updated_at"])
            messages.success(request, "Behavior metric updated.")
            return redirect("results:result-settings")

        if action == "delete_metric":
            metric = get_object_or_404(BehaviorMetricSetting, pk=request.POST.get("metric_id"))
            metric.delete()
            messages.success(request, "Behavior metric deleted.")
            return redirect("results:result-settings")

        if action == "toggle_result_pdf_bank":
            profile = self._finance_profile()
            profile.show_on_result_pdf = bool(request.POST.get("show_on_result_pdf"))
            profile.updated_by = request.user
            profile.save(update_fields=["show_on_result_pdf", "updated_by", "updated_at"])
            state = "enabled" if profile.show_on_result_pdf else "disabled"
            messages.success(request, f"Bank details on result PDF {state}.")
            return redirect("results:result-settings")

        if action == "create_grade_scale":
            grade = (request.POST.get("grade") or "").strip().upper()
            try:
                min_score = int((request.POST.get("min_score") or "0").strip())
                max_score = int((request.POST.get("max_score") or "0").strip())
                sort_order = int((request.POST.get("sort_order") or "1").strip())
            except ValueError:
                messages.error(request, "Grade scale values must be valid numbers.")
                return redirect("results:result-settings")
            if not grade:
                messages.error(request, "Grade label is required.")
                return redirect("results:result-settings")
            row = GradeScale(
                grade=grade,
                min_score=min_score,
                max_score=max_score,
                sort_order=max(sort_order, 1),
                is_default=True,
            )
            try:
                row.full_clean()
            except ValidationError as exc:
                messages.error(request, exc.message_dict.get("__all__", exc.messages)[0])
                return redirect("results:result-settings")
            row.save()
            messages.success(request, "Grade scale band added.")
            return redirect("results:result-settings")

        if action == "update_grade_scale":
            row = get_object_or_404(GradeScale, pk=request.POST.get("grade_scale_id"), is_default=True)
            grade = (request.POST.get("grade") or row.grade).strip().upper()
            try:
                min_score = int((request.POST.get("min_score") or str(row.min_score)).strip())
                max_score = int((request.POST.get("max_score") or str(row.max_score)).strip())
                sort_order = int((request.POST.get("sort_order") or str(row.sort_order)).strip())
            except ValueError:
                messages.error(request, "Grade scale values must be valid numbers.")
                return redirect("results:result-settings")
            row.grade = grade
            row.min_score = min_score
            row.max_score = max_score
            row.sort_order = max(sort_order, 1)
            try:
                row.full_clean()
            except ValidationError as exc:
                messages.error(request, exc.message_dict.get("__all__", exc.messages)[0])
                return redirect("results:result-settings")
            row.save(update_fields=["grade", "min_score", "max_score", "sort_order", "updated_at"])
            messages.success(request, "Grade scale band updated.")
            return redirect("results:result-settings")

        if action == "delete_grade_scale":
            row = get_object_or_404(GradeScale, pk=request.POST.get("grade_scale_id"), is_default=True)
            row.delete()
            messages.success(request, "Grade scale band deleted.")
            return redirect("results:result-settings")

        if action == "save_school_profile":
            school_profile = self._school_profile()
            form = SchoolProfileForm(request.POST, request.FILES, instance=school_profile)
            if form.is_valid():
                row = form.save(commit=False)
                row.updated_by = request.user
                row.save()
                messages.success(request, "School profile updated.")
                return redirect("results:result-settings")
            return self.render_to_response(self.get_context_data(school_profile_form=form))

        if action == "save_principal_signature":
            principal_user = self._principal_user()
            if principal_user is None:
                messages.error(request, "Create the principal account before saving a principal signature.")
                return redirect("results:result-settings")
            signature_form = PrincipalSignatureForm(request.POST, request.FILES)
            if signature_form.is_valid():
                signature_record, _created = PrincipalSignature.objects.get_or_create(user=principal_user)
                uploaded_image = signature_form.cleaned_data.get("signature_image")
                signature_data = signature_form.cleaned_data.get("signature_data")
                if uploaded_image:
                    signature_record.signature_image = uploaded_image
                    signature_record.save(update_fields=["signature_image", "updated_at"])
                    messages.success(request, "Principal signature updated.")
                    return redirect("results:result-settings")
                if signature_data:
                    try:
                        signature_file = self._signature_file_from_data_url(signature_data)
                    except ValueError as exc:
                        signature_form.add_error("signature_data", str(exc))
                    else:
                        signature_record.signature_image.save(signature_file.name, signature_file, save=True)
                        messages.success(request, "Principal signature updated.")
                        return redirect("results:result-settings")
                if not signature_form.errors:
                    signature_form.add_error("signature_image", "Upload a signature image or draw on the signature pad.")
            return self.render_to_response(self.get_context_data(principal_signature_form=signature_form))

        if action == "clear_principal_signature":
            principal_user = self._principal_user()
            signature_record = self._principal_signature_record(principal_user)
            if signature_record and signature_record.signature_image:
                signature_record.signature_image.delete(save=False)
                signature_record.signature_image = None
                signature_record.save(update_fields=["signature_image", "updated_at"])
                messages.success(request, "Principal signature removed.")
            else:
                messages.info(request, "No principal signature is saved yet.")
            return redirect("results:result-settings")

        messages.error(request, "Invalid settings action.")
        return redirect("results:result-settings")


class ResultReportAccessMixin(ResultsAccessMixin):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, self.allowed_roles):
            messages.error(request, "Report analytics access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def _window(self):
        current_session, current_term = current_session_term()
        sessions = list(AcademicSession.objects.order_by("-name"))
        requested_session_id = (self.request.GET.get("session_id") or "").strip()
        requested_term_id = (self.request.GET.get("term_id") or "").strip()
        selected_session = None
        if requested_session_id:
            selected_session = next((row for row in sessions if str(row.id) == requested_session_id), None)
        if selected_session is None:
            selected_session = current_session or (sessions[0] if sessions else None)
        terms = list(Term.objects.filter(session=selected_session).order_by("name")) if selected_session else []
        selected_term = None
        if requested_term_id:
            selected_term = next((row for row in terms if str(row.id) == requested_term_id), None)
        if selected_term is None and current_term and selected_session and current_term.session_id == selected_session.id:
            selected_term = current_term
        if selected_term is None and terms:
            selected_term = terms[0]
        self.report_available_sessions = sessions
        self.report_available_terms = terms
        return selected_session, selected_term


DECIMAL_ZERO = Decimal("0.00")
DECIMAL_ONE = Decimal("1.00")
ACADEMIC_PERFORMANCE_COMPONENT_OPTIONS = (
    ("ca1", "CA1"),
    ("ca23", "CA2 / CA3 Combined"),
    ("ca4", "Assignment / Projects / Practical"),
    ("class_participation", "Class Participation"),
    ("exam", "Exam"),
    ("overall", "Overall"),
    ("cumulative", "Cumulative"),
)


def _academic_performance_component_options_for_term(term):
    if _uses_legacy_result_layout(term):
        return tuple(
            (key, label)
            for key, label in ACADEMIC_PERFORMANCE_COMPONENT_OPTIONS
            if key != "class_participation"
        )
    return ACADEMIC_PERFORMANCE_COMPONENT_OPTIONS


def _q2(value):
    return decimal_value(value).quantize(Decimal("0.01"))


def _student_label(student):
    return student.get_full_name() or student.username


def _score_has_any_value(score):
    if score is None:
        return False
    fields = ("ca1", "ca2", "ca3", "ca4", "class_participation", "objective", "theory")
    if any(_q2(getattr(score, field, DECIMAL_ZERO)) > DECIMAL_ZERO for field in fields):
        return True
    return any(_q2(value) > DECIMAL_ZERO for value in score.normalized_breakdown().values())


def _selected_academic_performance_component(request, term=None):
    requested = (request.GET.get("ca") or "ca1").strip().lower()
    options = _academic_performance_component_options_for_term(term)
    allowed = {key for key, _label in options}
    if requested in allowed:
        return requested
    return "ca23" if _uses_legacy_result_layout(term) else "ca1"


def _selected_ca_component(request, term=None):
    return _selected_academic_performance_component(request, term=term)


def _academic_performance_class_options(component_key, term=None):
    options = _report_level_options()
    return exclude_external_exam_classes_for_term(options, term, field_name="self") if term is not None else options


def _ca_report_class_options(component_key="ca1", term=None):
    return _academic_performance_class_options(component_key, term=term)


def _selected_ca_report_class(request, component_key="ca1", term=None):
    raw_class_id = (request.GET.get("class_id") or "").strip()
    if not raw_class_id.isdigit():
        return None
    selected = _academic_performance_class_options(component_key, term=term).filter(pk=int(raw_class_id)).first()
    if selected is None:
        return None
    return _instructional_class(selected)


def _ca_component_label(component_key):
    return dict(ACADEMIC_PERFORMANCE_COMPONENT_OPTIONS).get(component_key, "CA1")


def _term_filter_query(session, term, **extra):
    query = {}
    if session is not None:
        query["session_id"] = session.id
    if term is not None:
        query["term_id"] = term.id
    for key, value in extra.items():
        if value is not None and value != "":
            query[key] = value
    return urlencode(query)


def _class_level_label(academic_class):
    if academic_class is None:
        return ""
    level = _instructional_class(academic_class)
    return (getattr(level, "display_name", "") or getattr(level, "code", "") or academic_class.code).strip()


def _ca_component_parts(score, component_key="ca1"):
    if score is None:
        return {
            "objective": DECIMAL_ZERO,
            "theory": DECIMAL_ZERO,
            "total": DECIMAL_ZERO,
            "ca1_compact": "—",
            "ca2_compact": "—",
            "ca3_compact": "—",
            "exam_compact": "—",
            "total_compact": "—",
            "has_score": False,
            "locked": False,
        }
    breakdown = score.normalized_breakdown()
    component_key = component_key if component_key in {"ca1", "ca23", "ca4", "class_participation", "exam", "overall", "cumulative"} else "ca1"
    if component_key == "exam":
        objective = _q2(score.objective)
        theory = _q2(score.theory)
        total = _q2(score.total_exam or (objective + theory))
        return {
            "objective": objective,
            "theory": theory,
            "total": total,
            "has_score": total > DECIMAL_ZERO or objective > DECIMAL_ZERO or theory > DECIMAL_ZERO,
            "locked": score.is_component_locked("objective") or score.is_component_locked("theory"),
        }
    if component_key == "overall":
        ca1 = _q2(score.ca1)
        ca2 = _q2(score.ca2)
        ca3 = _q2(score.ca3)
        exam = _q2(score.total_exam)
        total = _q2(score.grand_total)
        return {
            "objective": _q2(score.total_ca),
            "theory": exam,
            "total": total,
            "ca1": ca1,
            "ca2": ca2,
            "ca3": ca3,
            "exam": exam,
            "ca1_compact": _compact_term_score_display(ca1, has_record=True),
            "ca2_compact": _compact_term_score_display(ca2, has_record=True),
            "ca3_compact": _compact_term_score_display(ca3, has_record=True),
            "exam_compact": _compact_term_score_display(exam, has_record=True),
            "total_compact": _compact_term_score_display(total, has_record=True),
            "has_score": total > DECIMAL_ZERO,
            "locked": False,
        }
    if component_key == "ca23":
        objective = (
            _q2(score.breakdown_value("ca2_objective"))
            if "ca2_objective" in breakdown
            else _q2(score.ca2)
        )
        theory = (
            _q2(score.breakdown_value("ca3_theory"))
            if "ca3_theory" in breakdown
            else _q2(score.ca3)
        )
        total = _q2(objective + theory)
        return {
            "objective": objective,
            "theory": theory,
            "total": total,
            "has_score": total > DECIMAL_ZERO,
            "locked": (
                score.is_component_locked("ca2")
                or score.is_component_locked("ca3")
                or "ca2_objective" in breakdown
                or "ca3_theory" in breakdown
            ),
        }
    if component_key == "class_participation":
        total = _q2(score.class_participation)
        return {
            "objective": DECIMAL_ZERO,
            "theory": DECIMAL_ZERO,
            "total": total,
            "has_score": total > DECIMAL_ZERO,
            "locked": True,
        }
    total = _q2(getattr(score, component_key, DECIMAL_ZERO))
    objective_key = f"{component_key}_objective"
    theory_key = f"{component_key}_theory"
    if component_key == "ca3":
        objective_key = ""
        theory_key = "ca3_theory"
    objective = _q2(score.breakdown_value(objective_key)) if objective_key and objective_key in breakdown else DECIMAL_ZERO
    theory = _q2(score.breakdown_value(theory_key)) if theory_key in breakdown else DECIMAL_ZERO
    if theory == DECIMAL_ZERO and objective > DECIMAL_ZERO and total >= objective:
        theory = _q2(total - objective)
    if objective == DECIMAL_ZERO and theory == DECIMAL_ZERO and total > DECIMAL_ZERO:
        theory = total
    return {
        "objective": objective,
        "theory": theory,
        "total": total,
        "has_score": total > DECIMAL_ZERO or objective > DECIMAL_ZERO or theory > DECIMAL_ZERO,
        "locked": score.is_component_locked(component_key) or bool(objective_key and objective_key in breakdown),
    }


def _ca1_parts(score):
    return _ca_component_parts(score, "ca1")


def _ca1_evidence_subject_ids(*, student_ids, session, term):
    evidence = set()
    score_rows = StudentSubjectScore.objects.filter(
        student_id__in=student_ids,
        result_sheet__session=session,
        result_sheet__term=term,
    ).select_related("result_sheet")
    for score in score_rows:
        if _score_has_any_value(score):
            evidence.add((score.student_id, score.result_sheet.subject_id))
    attempt_rows = ExamAttempt.objects.filter(
        student_id__in=student_ids,
        exam__session=session,
        exam__term=term,
    ).select_related("exam")
    for attempt in attempt_rows:
        if attempt.status in {CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED, CBTAttemptStatus.IN_PROGRESS}:
            evidence.add((attempt.student_id, attempt.exam.subject_id))
    return evidence


def _annual_subject_label(subject_name):
    return annual_subject_label(subject_name)


def _annual_term_average(values):
    numeric_values = [_q2(value) for value in values if value not in (None, "")]
    if not numeric_values:
        return None
    return (sum(numeric_values, DECIMAL_ZERO) / Decimal(len(numeric_values))).quantize(Decimal("0.01"))


ANNUAL_NO_SCORE_LABEL = "N/O"


SUBJECT_CODE_ALIASES = {
    "ACCOUNTING": "ACC",
    "AGRICULTURAL SCIENCE": "AGRIC",
    "AGRICULTURE": "AGRIC",
    "AGRIC": "AGRIC",
    "BIOLOGY": "BIO",
    "BUSINESS STUDIES": "BSTUD",
    "CCA": "CCA",
    "CHEMISTRY": "CHEM",
    "CHRISTIAN RELIGIOUS STUDIES": "CRS",
    "CRS": "CRS",
    "CIVIC EDUCATION": "CIVIC",
    "COMMERCE": "COMM",
    "COMPUTER SCIENCE": "DTECH",
    "COMPUTER STUDIES": "DTECH",
    "DATA PROCESSING": "DATA",
    "DIGITAL TECHNOLOGY": "DTECH",
    "ECONOMICS": "ECONS",
    "ENGLISH LANGUAGE": "ENG",
    "ENGLISH LITERATURE": "LIT",
    "FASHION": "FASH",
    "FISHERY": "FISH",
    "FOOD AND NUTRITION": "F&N",
    "FRENCH": "FREN",
    "FURTHER MATHEMATICS": "FMATH",
    "GARMENT MAKING": "GMT",
    "GARMENT MAKING THEORY": "GMT",
    "GEOGRAPHY": "GEO",
    "GOVERNMENT": "GOVT",
    "HAUSA LANGUAGE": "HAUSA",
    "HISTORY": "HIST",
    "IGBO LANGUAGE": "IGBO",
    "INTERMEDIATE SCIENCE": "ISCI",
    "LITERATURE": "LIT",
    "LITERATURE IN ENGLISH": "LIT",
    "LIVESTOCK": "LSTK",
    "MATHEMATICS": "MATH",
    "MUSIC": "MUS",
    "PHYSICAL AND HEALTH EDUCATION": "PHE",
    "PHYSICS": "PHY",
    "SOCIAL AND CITIZENSHIP STUDIES": "SCS",
    "TECHNICAL DRAWING": "TD",
    "VISUAL ART": "VA",
    "YORUBA LANGUAGE": "YOR",
}


def _subject_report_name(subject):
    if isinstance(subject, dict):
        return subject.get("name") or subject.get("code") or ""
    return getattr(subject, "name", None) or getattr(subject, "code", None) or str(subject or "")


def _subject_report_code(subject):
    name = _subject_report_name(subject).strip()
    if not name:
        return "SUBJ"
    normalized = " ".join(name.upper().replace("&", " AND ").split())
    if normalized in SUBJECT_CODE_ALIASES:
        return SUBJECT_CODE_ALIASES[normalized]
    code = "".join(word[0] for word in normalized.split() if word and word[0].isalnum())
    return (code or normalized[:6]).upper()[:6]


def _annual_score_display(value, *, has_record=False, fallback=ANNUAL_NO_SCORE_LABEL):
    if not has_record or value in (None, ""):
        return fallback
    return str(_q2(value))


def _compact_term_score_display(value, *, has_record=False, fallback="—"):
    if not has_record or value in (None, ""):
        return fallback
    score = _q2(value)
    return f"{score:.2f}".rstrip("0").rstrip(".")


def _compact_annual_score_display(value, *, has_record=False, fallback="—"):
    if not has_record or value in (None, ""):
        return fallback
    return f"{_q2(value):.2f}"


def _annual_cell_display(term_values, annual_value):
    term_map = {row.get("term"): row for row in term_values}
    display = {}
    lines = []
    for term_name, key, label in (
        ("FIRST", "t1", "T1"),
        ("SECOND", "t2", "T2"),
        ("THIRD", "t3", "T3"),
    ):
        term_row = term_map.get(term_name, {})
        value = _annual_score_display(
            term_row.get("score"),
            has_record=term_row.get("record") is not None,
        )
        display[key] = value
        display[f"{key}_compact"] = _compact_term_score_display(
            term_row.get("score"),
            has_record=term_row.get("record") is not None,
        )
        lines.append({"label": label, "value": value})
    display["avg"] = _annual_score_display(annual_value, has_record=annual_value is not None)
    display["avg_compact"] = _compact_annual_score_display(annual_value, has_record=annual_value is not None)
    lines.append({"label": "AVG", "value": display["avg"]})
    display["lines"] = lines
    display["labelled"] = "; ".join(f'{row["label"]}: {row["value"]}' for row in lines)
    return display


def _matrix_print_layout(subject_count):
    subject_count = max(1, int(subject_count or 1))
    effective_count = min(max(subject_count, 13), 18)
    student_width = 40 if effective_count <= 14 else 38 if effective_count <= 16 else 36
    fixed_width = 6 + student_width + 8 + 13 + 12 + 7
    subject_width = (Decimal("289") - Decimal(str(fixed_width))) / Decimal(subject_count)

    if effective_count <= 14:
        typography = {
            "subject_code_font": "6.0pt",
            "score_font": "6.2pt",
            "student_font": "6.8pt",
            "annual_code_font": "5.0pt",
            "annual_key_font": "4.7pt",
            "annual_score_font": "4.9pt",
            "annual_student_font": "6.6pt",
            "annual_row_min": "10.4mm",
        }
    elif effective_count <= 16:
        typography = {
            "subject_code_font": "5.6pt",
            "score_font": "5.8pt",
            "student_font": "6.4pt",
            "annual_code_font": "4.7pt",
            "annual_key_font": "4.4pt",
            "annual_score_font": "4.6pt",
            "annual_student_font": "6.2pt",
            "annual_row_min": "10.0mm",
        }
    else:
        typography = {
            "subject_code_font": "5.1pt",
            "score_font": "5.3pt",
            "student_font": "6.0pt",
            "annual_code_font": "4.25pt",
            "annual_key_font": "4.1pt",
            "annual_score_font": "4.25pt",
            "annual_student_font": "5.9pt",
            "annual_row_min": "9.6mm",
        }

    return {
        "sn": "6",
        "student": str(student_width),
        "subject": f"{subject_width.quantize(Decimal('0.001'))}",
        "subjects_offered": "8",
        "total": "13",
        "average": "12",
        "position": "7",
        "typography": typography,
    }


def _matrix_print_subjects(subjects):
    return [
        {
            "name": _subject_report_name(subject),
            "code": _subject_report_code(subject),
            "source": subject,
        }
        for subject in subjects
    ]


def _with_print_layout(matrix):
    subjects = list(matrix.get("subjects", []))
    matrix["print_subjects"] = _matrix_print_subjects(subjects)
    matrix["print_widths"] = _matrix_print_layout(len(subjects))
    return matrix


def _apply_competition_positions(rows):
    previous_value = None
    previous_position = 0
    for index, row in enumerate(rows, start=1):
        value = row.get("ranking_average", row.get("average", DECIMAL_ZERO))
        if previous_value is not None and value == previous_value:
            row["position"] = previous_position
        else:
            row["position"] = index
            previous_position = index
            previous_value = value


def _pure_term_averages_from_rows(term_rows_by_name):
    """Return exact per-term averages from raw term totals.

    Annual/cumulative overall averages must be the average of each term's
    own average, not pooled raw marks across uneven subject counts.  Example:
    (Term1 total / Term1 subjects + Term2 total / Term2 subjects + Term3
    total / Term3 subjects) / number of available terms.
    """

    term_averages = []
    for term_name in ("FIRST", "SECOND", "THIRD"):
        rows = term_rows_by_name.get(term_name, [])
        values = []
        for _subject_name, score in rows:
            value = getattr(score, "grand_total", None)
            if value not in (None, ""):
                values.append(Decimal(value))
        if values:
            term_averages.append(sum(values, DECIMAL_ZERO) / Decimal(len(values)))
    return term_averages


def _class_cumulative_matrix(*, session, term, academic_class):
    if not session or not term or not academic_class:
        return {"available": False, "rows": [], "subjects": [], "top_three": [], "missing_cells": []}

    class_ids = _cohort_class_ids(academic_class)
    enrollments = list(
        StudentClassEnrollment.objects.filter(
            academic_class_id__in=class_ids,
            session=session,
            is_active=True,
        )
        .select_related("student", "student__student_profile", "academic_class")
        .order_by(
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )
    )
    student_ids = [row.student_id for row in enrollments]
    if not student_ids:
        return {"available": True, "rows": [], "subjects": [], "top_three": [], "missing_cells": []}

    third_term = Term.objects.filter(session=session, name="THIRD").first()
    third_term_student_ids = set()
    if third_term is not None:
        third_term_student_ids = set(
            StudentSubjectScore.objects.filter(
                student_id__in=student_ids,
                result_sheet__session=session,
                result_sheet__term=third_term,
                result_sheet__academic_class=_instructional_class(academic_class),
            )
            .exclude(result_sheet__subject__code__in=NON_RESULT_SUBJECT_CODES)
            .values_list("student_id", flat=True)
            .distinct()
        )
    enrollments = [row for row in enrollments if row.student_id in third_term_student_ids]
    student_ids = [row.student_id for row in enrollments]
    if not student_ids:
        return {"available": True, "rows": [], "subjects": [], "top_three": [], "missing_cells": []}

    active_pairs = set(
        StudentSubjectEnrollment.objects.filter(
            student_id__in=student_ids,
            session=session,
            is_active=True,
        )
        .exclude(subject__code__in=NON_RESULT_SUBJECT_CODES)
        .values_list("student_id", "subject_id")
    )
    subjects = []
    terms = {
        row.name: row
        for row in Term.objects.filter(session=session, name__in=["FIRST", "SECOND", "THIRD"])
    }
    term_order = ("FIRST", "SECOND", "THIRD")
    term_ids = [terms[name].id for name in term_order if name in terms]
    score_qs = StudentSubjectScore.objects.filter(
        student_id__in=student_ids,
        result_sheet__session=session,
        result_sheet__term_id__in=term_ids,
        result_sheet__academic_class=_instructional_class(academic_class),
    ).exclude(
        result_sheet__status__in=[
            ResultSheetStatus.DRAFT,
            ResultSheetStatus.REJECTED_BY_DEAN,
            ResultSheetStatus.REJECTED_BY_VP,
        ]
    )
    score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")
    score_qs = score_qs.select_related(
        "student",
        "student__student_profile",
        "result_sheet",
        "result_sheet__term",
        "result_sheet__subject",
    ).order_by("-updated_at")
    term_subject_rows_by_student = {}
    subject_labels = {}
    for score in score_qs:
        if score.result_sheet.term.name in {"FIRST", "SECOND"} and not _score_has_any_value(score):
            # Historical PDF imports sometimes contain placeholder score rows
            # for subjects a student did not offer.  Those zero rows must not
            # appear in cumulative reports or inflate the annual subject list.
            continue
        term_subject_rows_by_student.setdefault(score.student_id, {}).setdefault(score.result_sheet.term.name, []).append(
            (score.result_sheet.subject.name, score)
        )
    annual_slots_by_student = {}
    display_sources_by_student = {}
    target_merge_sources_by_student = {}
    class_term_subject_labels = {term_name: set() for term_name in term_order}
    for enrollment in enrollments:
        slots, _diagnostics = build_annual_subject_slots(
            term_subject_rows_by_student.get(enrollment.student_id, {}),
            student=enrollment.student,
        )
        annual_slots_by_student[enrollment.student_id] = slots
        display_sources = {}
        target_merge_sources = {}
        for subject_label, term_map in slots.items():
            subject_labels[subject_label] = subject_label
            for term_name in term_order:
                if term_map.get(term_name):
                    class_term_subject_labels.setdefault(term_name, set()).add(subject_label)
        display_sources_by_student[enrollment.student_id] = display_sources
        target_merge_sources_by_student[enrollment.student_id] = target_merge_sources
    subjects = [{"name": label} for label in sorted(subject_labels)]

    rows = []
    missing_cells = []
    for enrollment in enrollments:
        subject_cells = []
        annual_total = DECIMAL_ZERO
        offered_count = 0
        missing_count = 0
        for subject in subjects:
            subject_label = subject["name"]
            student_term_rows = term_subject_rows_by_student.get(enrollment.student_id, {})
            current_slots = annual_slots_by_student.get(enrollment.student_id, {})
            display_sources = display_sources_by_student.get(enrollment.student_id, {})
            display_info = display_sources.get(subject_label)
            is_current_subject = subject_label in current_slots

            if display_info and not is_current_subject:
                merged_to = display_info["merged_to"]
                term_values = []
                display_total = DECIMAL_ZERO
                has_any_display_score = False
                for term_name in term_order:
                    scores = display_info["terms"].get(term_name, [])
                    value = _annual_term_average([score.grand_total for score in scores])
                    if value is not None:
                        has_any_display_score = True
                        display_total += value
                        display_label = str(value)
                        term_status = "historical_source"
                    elif current_slots.get(merged_to, {}).get(term_name):
                        display_label = f"Merged with {merged_to}"
                        value = DECIMAL_ZERO
                        term_status = "merged_with_current"
                    elif not student_term_rows.get(term_name):
                        display_label = ANNUAL_NO_SCORE_LABEL
                        value = DECIMAL_ZERO
                        term_status = "not_a_student"
                    elif subject_label not in class_term_subject_labels.get(term_name, set()):
                        display_label = ANNUAL_NO_SCORE_LABEL
                        value = DECIMAL_ZERO
                        term_status = "not_offered"
                    else:
                        display_label = ANNUAL_NO_SCORE_LABEL
                        value = DECIMAL_ZERO
                        term_status = "not_offered_by_student"
                    term_values.append({
                        "term": term_name,
                        "score": value,
                        "record": scores[0] if scores else None,
                        "status": term_status,
                        "display": display_label,
                    })
                annual_display = _annual_cell_display(term_values, display_total if has_any_display_score else None)
                subject_cells.append({
                    "subject": subject,
                    "offered": True,
                    "display_only": True,
                    "merged_to": merged_to,
                    "score": None,
                    "term_values": term_values,
                    "ca": {
                        "objective": annual_display["t1"],
                        "theory": annual_display["t2"],
                        "third": annual_display["t3"],
                        "t1": annual_display["t1"],
                        "t2": annual_display["t2"],
                        "t3": annual_display["t3"],
                        "t1_compact": annual_display["t1_compact"],
                        "t2_compact": annual_display["t2_compact"],
                        "t3_compact": annual_display["t3_compact"],
                        "total": "Merged",
                        "annual": annual_display["avg"],
                        "avg": annual_display["avg"],
                        "avg_compact": annual_display["avg_compact"],
                        "lines": annual_display["lines"],
                        "labelled": annual_display["labelled"],
                        "has_score": has_any_display_score,
                        "locked": False,
                    },
                    "ca1": {
                        "objective": term_values[0]["display"] if term_values else "-",
                        "theory": term_values[1]["display"] if len(term_values) > 1 else "-",
                        "total": "Merged",
                        "has_score": has_any_display_score,
                        "locked": False,
                    },
                })
                continue

            term_values = []
            has_any_score = False
            subject_total = DECIMAL_ZERO
            missing_terms = []
            for term_name in term_order:
                scores = current_slots.get(subject_label, {}).get(term_name, [])
                value = _annual_term_average([score.grand_total for score in scores])
                term_status = "ok"
                if value is None:
                    value = DECIMAL_ZERO
                    term_status = "not_applicable"
                    if not student_term_rows.get(term_name):
                        display_label = ANNUAL_NO_SCORE_LABEL
                    elif subject_label not in class_term_subject_labels.get(term_name, set()):
                        display_label = ANNUAL_NO_SCORE_LABEL
                    else:
                        display_label = ANNUAL_NO_SCORE_LABEL
                else:
                    has_any_score = True
                    merged_from = target_merge_sources_by_student.get(enrollment.student_id, {}).get(subject_label, {}).get(term_name)
                    display_label = f"Merged from {merged_from}" if merged_from else str(value)
                subject_total += value
                term_values.append({
                    "term": term_name,
                    "score": value,
                    "record": scores[0] if scores else None,
                    "status": term_status,
                    "display": display_label,
                })
            available_count = sum(1 for row in term_values if row["record"] is not None)
            offered = available_count > 0
            annual = (subject_total / Decimal(available_count)).quantize(Decimal("0.01")) if available_count else None
            annual_display = _annual_cell_display(term_values, annual)
            if offered:
                offered_count += 1
                annual_total += annual
                if missing_terms:
                    missing_count += 1
                    missing_cells.append({
                        "student": enrollment.student,
                        "subject": subject,
                        "class_name": _class_level_label(enrollment.academic_class),
                        "missing_terms": ", ".join(missing_terms),
                    })
            subject_cells.append({
                "subject": subject,
                "offered": offered,
                "display_only": False,
                "score": None,
                "term_values": term_values,
                "ca": {
                    "objective": annual_display["t1"],
                    "theory": annual_display["t2"],
                    "third": annual_display["t3"],
                    "t1": annual_display["t1"],
                    "t2": annual_display["t2"],
                    "t3": annual_display["t3"],
                    "t1_compact": annual_display["t1_compact"],
                    "t2_compact": annual_display["t2_compact"],
                    "t3_compact": annual_display["t3_compact"],
                    "total": subject_total.quantize(Decimal("0.01")),
                    "annual": annual_display["avg"],
                    "avg": annual_display["avg"],
                    "avg_compact": annual_display["avg_compact"],
                    "lines": annual_display["lines"],
                    "labelled": annual_display["labelled"],
                    "has_score": offered and has_any_score,
                    "locked": False,
                },
                "ca1": {
                    "objective": _q2(term_values[0]["score"]) if term_values else DECIMAL_ZERO,
                    "theory": _q2(term_values[1]["score"]) if len(term_values) > 1 else DECIMAL_ZERO,
                    "total": subject_total.quantize(Decimal("0.01")),
                    "has_score": offered and has_any_score,
                    "locked": False,
                },
            })
        denominator = offered_count
        term_averages = _pure_term_averages_from_rows(student_term_rows)
        if term_averages:
            ranking_average = sum(term_averages, DECIMAL_ZERO) / Decimal(len(term_averages))
        elif denominator:
            ranking_average = annual_total / Decimal(denominator)
        else:
            ranking_average = DECIMAL_ZERO
        average = ranking_average.quantize(Decimal("0.01"))
        rows.append({
            "student": enrollment.student,
            "student_number": _admission_number_for_student(enrollment.student),
            "class_name": _class_level_label(enrollment.academic_class),
            "subjects": subject_cells,
            "total": annual_total.quantize(Decimal("0.01")),
            "average": average,
            "ranking_average": ranking_average,
            "offered_count": denominator,
            "actual_offered_count": offered_count,
            "missing_count": missing_count,
        })
    ranked = sorted(
        rows,
        key=lambda row: (
            -row.get("ranking_average", row["average"]),
            -row["total"],
            _student_label(row["student"]).lower(),
            row["student_number"],
        ),
    )
    _apply_competition_positions(ranked)
    return _with_print_layout({
        "available": True,
        "rows": rows,
        "subjects": subjects,
        "top_three": ranked[:3],
        "missing_cells": missing_cells,
        "student_count": len(rows),
        "subject_count": max((row["offered_count"] for row in rows), default=len(subjects)),
        "actual_subject_count": len(subjects),
        "component_key": "cumulative",
        "component_label": _ca_component_label("cumulative"),
        "no_score_label": ANNUAL_NO_SCORE_LABEL,
    })


def _class_ca_matrix(*, session, term, academic_class, component_key="ca1"):
    if component_key == "cumulative":
        return _class_cumulative_matrix(session=session, term=term, academic_class=academic_class)
    if not session or not term or not academic_class:
        return {"available": False, "rows": [], "subjects": [], "top_three": [], "missing_cells": []}

    class_ids = _cohort_class_ids(academic_class)
    enrollments = list(
        StudentClassEnrollment.objects.filter(
            academic_class_id__in=class_ids,
            session=session,
            is_active=True,
        )
        .select_related("student", "student__student_profile", "academic_class")
        .order_by(
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )
    )
    student_ids = [row.student_id for row in enrollments]
    if not student_ids:
        return {"available": True, "rows": [], "subjects": [], "top_three": [], "missing_cells": []}

    score_map = {}
    score_qs = StudentSubjectScore.objects.filter(
            student_id__in=student_ids,
            result_sheet__session=session,
            result_sheet__term=term,
            result_sheet__academic_class=_instructional_class(academic_class),
        )
    score_qs = exclude_non_result_subjects(score_qs, field_name="result_sheet__subject")
    score_qs = (
        score_qs
        .select_related("student", "result_sheet", "result_sheet__subject")
        .order_by("result_sheet__subject__name", "-updated_at")
    )
    legacy_layout = _uses_legacy_result_layout(term)
    if legacy_layout:
        # First/Second Term historical imports must display the subjects that
        # actually existed in that term. Current enrollments now contain renamed
        # subjects such as Intermediate Science, so using current enrollment
        # would incorrectly mark non-existing legacy subjects as missing and
        # hide Basic Science / Basic Technology from First Term.
        offered_pairs = {
            (score.student_id, score.result_sheet.subject_id)
            for score in score_qs
            if _score_has_any_value(score)
        }
    else:
        active_pairs = set(
            StudentSubjectEnrollment.objects.filter(
                student_id__in=student_ids,
                session=session,
                is_active=True,
            )
            .exclude(subject__code__in=NON_RESULT_SUBJECT_CODES)
            .values_list("student_id", "subject_id")
        )
        # Current-term academic performance is based on current offered subjects.
        # Evidence-only rows from old/removed subjects are intentionally kept out
        # so they cannot distort totals, averages, or positions.
        offered_pairs = active_pairs
    subject_ids = sorted({subject_id for _student_id, subject_id in offered_pairs})
    subjects = list(Subject.objects.filter(id__in=subject_ids).order_by("name", "code"))
    subject_map = {subject.id: subject for subject in subjects}

    for score in score_qs:
        if legacy_layout and not _score_has_any_value(score):
            continue
        score_map.setdefault((score.student_id, score.result_sheet.subject_id), score)

    rows = []
    missing_cells = []
    for enrollment in enrollments:
        subject_cells = []
        total = DECIMAL_ZERO
        offered_count = 0
        missing_count = 0
        for subject in subjects:
            offered = (enrollment.student_id, subject.id) in offered_pairs
            score = score_map.get((enrollment.student_id, subject.id))
            ca = _ca_component_parts(score, component_key)
            if offered:
                offered_count += 1
                total += ca["total"]
                if not ca["has_score"]:
                    missing_count += 1
                    missing_cells.append({
                        "student": enrollment.student,
                        "subject": subject,
                        "class_name": _class_level_label(enrollment.academic_class),
                    })
            subject_cells.append({
                "subject": subject,
                "offered": offered,
                "score": score,
                "ca": ca,
                "ca1": ca,
            })
        denominator = offered_count
        average = (total / Decimal(denominator)).quantize(Decimal("0.01")) if denominator else DECIMAL_ZERO
        rows.append({
            "student": enrollment.student,
            "student_number": _admission_number_for_student(enrollment.student),
            "class_name": _class_level_label(enrollment.academic_class),
            "subjects": subject_cells,
            "total": total.quantize(Decimal("0.01")),
            "average": average,
            "offered_count": denominator,
            "actual_offered_count": offered_count,
            "missing_count": missing_count,
        })
    ranked = sorted(
        rows,
        key=lambda row: (
            -row["average"],
            -row["total"],
            _student_label(row["student"]).lower(),
            row["student_number"],
        ),
    )
    _apply_competition_positions(ranked)
    return _with_print_layout({
        "available": True,
        "rows": rows,
        "subjects": subjects,
        "top_three": ranked[:3],
        "missing_cells": missing_cells,
        "student_count": len(rows),
        "subject_count": max((row["offered_count"] for row in rows), default=len(subjects)),
        "actual_subject_count": len(subjects),
        "component_key": component_key,
        "component_label": _ca_component_label(component_key),
        "no_score_label": ANNUAL_NO_SCORE_LABEL,
    })


def _class_ca1_matrix(*, session, term, academic_class):
    return _class_ca_matrix(session=session, term=term, academic_class=academic_class, component_key="ca1")


def _component_subject_leaders_from_matrix(matrix, *, component_key):
    leaders = []
    required_terms_by_subject_index = {}
    if component_key == "cumulative":
        for subject_index, _subject in enumerate(matrix.get("subjects", [])):
            required_terms = set()
            for row in matrix.get("rows", []):
                cells = row.get("subjects", [])
                if subject_index >= len(cells):
                    continue
                cell = cells[subject_index]
                if not cell.get("offered") or cell.get("display_only"):
                    continue
                for term_value in cell.get("term_values", []):
                    if term_value.get("record") is not None:
                        required_terms.add(term_value.get("term"))
            required_terms_by_subject_index[subject_index] = required_terms

    for subject_index, subject in enumerate(matrix.get("subjects", [])):
        subject_name = subject.get("name") if isinstance(subject, dict) else subject.name
        candidates = []
        required_terms = required_terms_by_subject_index.get(subject_index, set())
        if component_key == "cumulative" and len(required_terms) < 2:
            # Annual subject awards are not issued from one-term-only evidence.
            continue
        for row in matrix.get("rows", []):
            cells = row.get("subjects", [])
            if subject_index >= len(cells):
                continue
            cell = cells[subject_index]
            if not cell.get("offered") or cell.get("display_only"):
                continue
            score_value = cell.get("ca", {}).get("annual") if component_key == "cumulative" else cell.get("ca", {}).get("total")
            if score_value in (None, "", ANNUAL_NO_SCORE_LABEL):
                continue
            try:
                score_decimal = _q2(score_value)
            except Exception:
                continue
            term_count = None
            if component_key == "cumulative":
                candidate_terms = {
                    term_value.get("term")
                    for term_value in cell.get("term_values", [])
                    if term_value.get("record") is not None
                }
                term_count = len(candidate_terms)
                # Highest-in-subject annual prizes use the official term span
                # of that subject in the class.  Full-year subjects require
                # all three terms.  Subjects offered only in two terms (for
                # example Music, Basic Technology, or Livestock in this
                # session) require those two terms.  One-term-only historical
                # subjects remain visible but cannot win the annual award.
                if not required_terms.issubset(candidate_terms):
                    continue
            candidates.append(
                {
                    "subject": subject_name,
                    "student_number": row.get("student_number", ""),
                    "student_name": _student_label(row["student"]),
                    "class_name": row.get("class_name", ""),
                    "score": score_decimal,
                    "term_count": term_count,
                }
            )
        if not candidates:
            continue
        candidates.sort(key=lambda item: (-item["score"], item["student_name"].lower(), item["student_number"]))
        leaders.append(candidates[0])
    return leaders


def _subject_leader_score_label(component_key, term=None):
    if component_key == "cumulative":
        return "Annual Subject Score"
    if component_key == "overall" and getattr(term, "name", "") == "THIRD":
        return "Third-Term Subject Score"
    return f"{_ca_component_label(component_key)} Subject Score"


def _ca1_missing_cbt_audit(*, session, term, academic_class=None):
    attempts = ExamAttempt.objects.filter(
        exam__session=session,
        exam__term=term,
        exam__blueprint__objective_writeback_target=CBTWritebackTarget.CA1,
        status__in=[CBTAttemptStatus.SUBMITTED, CBTAttemptStatus.FINALIZED],
    ).select_related(
        "student",
        "student__student_profile",
        "exam",
        "exam__subject",
        "exam__academic_class",
    )
    if academic_class is not None:
        student_ids = StudentClassEnrollment.objects.filter(
            academic_class_id__in=_cohort_class_ids(academic_class),
            session=session,
            is_active=True,
        ).values_list("student_id", flat=True)
        attempts = attempts.filter(
            student_id__in=student_ids,
            exam__academic_class=_instructional_class(academic_class),
        )

    sheet_map = {
        (sheet.academic_class_id, sheet.subject_id): sheet
        for sheet in ResultSheet.objects.filter(session=session, term=term).select_related("subject", "academic_class")
    }
    score_map = {
        (score.result_sheet_id, score.student_id): score
        for score in StudentSubjectScore.objects.filter(
            result_sheet__session=session,
            result_sheet__term=term,
        ).select_related("result_sheet")
    }
    rows = []
    seen = set()
    for attempt in attempts.order_by(
        "exam__academic_class__code",
        "exam__subject__name",
        "student__last_name",
        "student__first_name",
    ):
        key = (attempt.student_id, attempt.exam_id)
        if key in seen:
            continue
        seen.add(key)
        sheet = sheet_map.get((attempt.exam.academic_class_id, attempt.exam.subject_id))
        score = score_map.get((sheet.id, attempt.student_id)) if sheet else None
        parts = _ca1_parts(score)
        incoming = _q2(attempt.objective_score)
        missing = sheet is None or score is None or (incoming > DECIMAL_ZERO and parts["objective"] <= DECIMAL_ZERO)
        if missing:
            rows.append({
                "student": attempt.student,
                "student_number": _admission_number_for_student(attempt.student),
                "class_name": _class_level_label(attempt.exam.academic_class),
                "subject": attempt.exam.subject,
                "attempt_score": incoming,
                "result_objective": parts["objective"],
                "result_total": parts["total"],
                "writeback_completed": attempt.writeback_completed,
                "reason": "No result sheet" if sheet is None else "No result row" if score is None else "Score mismatch or pending writeback",
            })
    return rows


def _cleanup_non_offered_ca1_rows(*, session, term):
    attempts_pairs = set(
        ExamAttempt.objects.filter(exam__session=session, exam__term=term)
        .values_list("student_id", "exam__subject_id")
    )
    second_term = (
        term.__class__.objects.filter(session=session, name="SECOND").first()
        or term.__class__.objects.filter(session=session, name__icontains="Second").first()
    )
    second_term_pairs = set()
    if second_term is not None:
        for second_score in StudentSubjectScore.objects.filter(
            result_sheet__session=session,
            result_sheet__term=second_term,
        ).select_related("result_sheet"):
            if _score_has_any_value(second_score):
                second_term_pairs.add((second_score.student_id, second_score.result_sheet.subject_id))
    updated_enrollments = 0
    deleted_scores = 0
    kept = 0
    candidate_scores = StudentSubjectScore.objects.filter(
        result_sheet__session=session,
        result_sheet__term=term,
    ).select_related("result_sheet", "student")
    with transaction.atomic():
        for score in candidate_scores:
            pair = (score.student_id, score.result_sheet.subject_id)
            if pair in attempts_pairs or pair in second_term_pairs or _score_has_any_value(score):
                kept += 1
                continue
            enrollment = StudentSubjectEnrollment.objects.filter(
                student_id=score.student_id,
                subject_id=score.result_sheet.subject_id,
                session=session,
                is_active=True,
            ).first()
            if enrollment is not None:
                enrollment.is_active = False
                enrollment.save(update_fields=["is_active", "updated_at"])
                updated_enrollments += 1
            score.delete()
            deleted_scores += 1
    return {
        "updated_enrollments": updated_enrollments,
        "deleted_scores": deleted_scores,
        "kept": kept,
    }


class CA1ManagementDashboardView(ResultReportAccessMixin, TemplateView):
    template_name = "results/ca1_management_dashboard.html"
    allowed_roles = {ROLE_IT_MANAGER}

    def post(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_IT_MANAGER):
            messages.error(request, "Only the IT Manager can run CA1 cleanup actions.")
            return redirect("results:academic-performance")
        session, term = self._window()
        result = _cleanup_non_offered_ca1_rows(session=session, term=term)
        messages.success(
            request,
            "CA1 cleanup finished: "
            f"{result['updated_enrollments']} enrollments deactivated, "
            f"{result['deleted_scores']} empty score rows removed, "
            f"{result['kept']} evidence-backed rows kept.",
        )
        return redirect("results:academic-performance")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        component_options = _academic_performance_component_options_for_term(term)
        component_key = _selected_ca_component(self.request, term=term)
        selected_class = _selected_ca_report_class(self.request, component_key, term=term)
        if selected_class is None:
            selected_class = _ca_report_class_options(component_key, term=term).first()
        matrix = _class_ca_matrix(
            session=session,
            term=term,
            academic_class=selected_class,
            component_key=component_key,
        )
        subject_leaders = _component_subject_leaders_from_matrix(matrix, component_key=component_key)
        context.update({
            "current_session": session,
            "current_term": term,
            "available_sessions": getattr(self, "report_available_sessions", []),
            "available_terms": getattr(self, "report_available_terms", []),
            "selected_session": session,
            "selected_term": term,
            "use_legacy_result_layout": _uses_legacy_result_layout(term),
            "ca_component_options": component_options,
            "selected_ca_component": component_key,
            "selected_ca_label": _ca_component_label(component_key),
            "term_filter_query": _term_filter_query(session, term),
            "selected_ca_query": _term_filter_query(session, term, ca=component_key),
            "class_options": _ca_report_class_options(component_key, term=term),
            "selected_class": selected_class,
            "matrix": matrix,
            "subject_leaders": subject_leaders,
            "school_profile": pdf_school_profile(),
            "logo_data_uri": school_logo_data_uri(),
            "watermark_data_uri": school_logo_data_uri(),
            "missing_cbt_rows": (
                _ca1_missing_cbt_audit(session=session, term=term, academic_class=selected_class)
                if component_key == "ca1"
                else []
            ),
            "can_edit_objective": self.request.user.has_role(ROLE_IT_MANAGER),
            "is_overall_component": component_key == "overall",
        })
        return context


class CA1ClassReportView(CA1ManagementDashboardView):
    template_name = "results/ca1_class_report.html"

    def get_context_data(self, **kwargs):
        context = TemplateView.get_context_data(self, **kwargs)
        session, term = self._window()
        component_options = _academic_performance_component_options_for_term(term)
        component_key = _selected_ca_component(self.request, term=term)
        selected_class = get_object_or_404(_academic_performance_class_options(component_key, term=term), pk=self.kwargs["class_id"])
        matrix = _class_ca_matrix(
            session=session,
            term=term,
            academic_class=selected_class,
            component_key=component_key,
        )
        subject_leaders = _component_subject_leaders_from_matrix(matrix, component_key=component_key)
        context.update({
            "current_session": session,
            "current_term": term,
            "ca_component_options": component_options,
            "selected_ca_component": component_key,
            "selected_ca_label": _ca_component_label(component_key),
            "term_filter_query": _term_filter_query(session, term),
            "selected_ca_query": _term_filter_query(session, term, ca=component_key),
            "class_options": _academic_performance_class_options(component_key, term=term),
            "selected_class": selected_class,
            "matrix": matrix,
            "subject_leaders": subject_leaders,
            "school_profile": pdf_school_profile(),
            "logo_data_uri": school_logo_data_uri(),
            "watermark_data_uri": school_logo_data_uri(),
            "missing_cbt_rows": (
                _ca1_missing_cbt_audit(session=session, term=term, academic_class=selected_class)
                if component_key == "ca1"
                else []
            ),
            "can_edit_objective": self.request.user.has_role(ROLE_IT_MANAGER),
            "is_overall_component": component_key == "overall",
        })
        return context

    def post(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_IT_MANAGER):
            messages.error(request, "Only the IT Manager can edit objective scores.")
            return redirect(request.path)
        action = (request.POST.get("action") or "").strip()
        if action != "update_objective":
            return super().post(request, *args, **kwargs)
        score = get_object_or_404(
            StudentSubjectScore.objects.select_related("result_sheet", "student"),
            pk=request.POST.get("score_id"),
            result_sheet__session=self._window()[0],
            result_sheet__term=self._window()[1],
        )
        policies = normalize_result_cbt_policies(score.result_sheet.cbt_component_policies)
        objective_max = _q2(policies["ca1"]["objective_max"])
        try:
            objective = _q2(request.POST.get("objective_score"))
        except Exception:
            messages.error(request, "Enter a valid CA1 objective score.")
            return redirect(request.path)
        if objective < DECIMAL_ZERO or objective > objective_max:
            messages.error(request, f"CA1 objective must be between 0 and {objective_max}.")
            return redirect(request.path)

        before = _score_snapshot(score)
        theory = score.breakdown_value("ca1_theory")
        if theory == DECIMAL_ZERO and score.ca1 >= score.breakdown_value("ca1_objective"):
            theory = _q2(score.ca1 - score.breakdown_value("ca1_objective"))
        score.set_breakdown_value("ca1_objective", objective)
        score.set_breakdown_value("ca1_theory", theory)
        score.ca1 = _q2(objective + theory)
        score.lock_components("ca1")
        score.save()
        _log_score_change(
            actor=request.user,
            request=request,
            score=score,
            sheet=score.result_sheet,
            before_snapshot=before,
            violations={"it_ca1_objective_edit": True},
        )
        messages.success(request, f"Updated CA1 objective for {_student_label(score.student)}.")
        ca_query = _selected_ca_component(request, term=score.result_sheet.term)
        return redirect(f"{request.path}?{_term_filter_query(score.result_sheet.session, score.result_sheet.term, ca=ca_query)}")


class CA1ClassReportCSVView(ResultReportAccessMixin, TemplateView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def get(self, request, *args, **kwargs):
        session, term = self._window()
        component_key = _selected_ca_component(request, term=term)
        selected_class = get_object_or_404(_academic_performance_class_options(component_key, term=term), pk=kwargs["class_id"])
        matrix = _class_ca_matrix(
            session=session,
            term=term,
            academic_class=selected_class,
            component_key=component_key,
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{component_key}-{selected_class.code}.csv"'
        writer = csv.writer(response)
        header = ["S/N", "Admission No", "Student Name", "Class"]
        header.extend([subject.get("name") if isinstance(subject, dict) else subject.name for subject in matrix["subjects"]])
        header.extend(["Offered Subjects", f"{_ca_component_label(component_key)} Total", "Average", "Position"])
        writer.writerow(header)
        for index, row in enumerate(matrix["rows"], start=1):
            csv_row = [index, row["student_number"], _student_label(row["student"]), row["class_name"]]
            for cell in row["subjects"]:
                if component_key == "cumulative":
                    csv_row.append(cell["ca"].get("labelled", ANNUAL_NO_SCORE_LABEL) if cell.get("offered") else ANNUAL_NO_SCORE_LABEL)
                else:
                    csv_row.append(str(cell["ca"]["total"]) if cell["offered"] else ANNUAL_NO_SCORE_LABEL)
            csv_row.extend([row["offered_count"], str(row["total"]), str(row["average"]), row.get("position", "")])
            writer.writerow(csv_row)
        return response


class CA1ClassSubjectLeadersCSVView(ResultReportAccessMixin, TemplateView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def get(self, request, *args, **kwargs):
        session, term = self._window()
        component_key = _selected_ca_component(request, term=term)
        selected_class = get_object_or_404(_academic_performance_class_options(component_key, term=term), pk=kwargs["class_id"])
        matrix = _class_ca_matrix(
            session=session,
            term=term,
            academic_class=selected_class,
            component_key=component_key,
        )
        leaders = _component_subject_leaders_from_matrix(matrix, component_key=component_key)

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{component_key}-{selected_class.code}-subject-best.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "S/N",
            "Subject",
            "Best Student",
            "Admission No",
            "Class",
            _subject_leader_score_label(component_key, term),
        ])
        for index, row in enumerate(leaders, start=1):
            writer.writerow([
                index,
                row["subject"],
                row["student_name"],
                row["student_number"],
                row["class_name"],
                row["score"],
            ])
        return response


class CA1ClassSubjectLeadersPDFView(ResultReportAccessMixin, TemplateView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def get(self, request, *args, **kwargs):
        from weasyprint import HTML

        session, term = self._window()
        component_key = _selected_ca_component(request, term=term)
        selected_class = get_object_or_404(
            _academic_performance_class_options(component_key, term=term),
            pk=kwargs["class_id"],
        )
        matrix = _class_ca_matrix(
            session=session,
            term=term,
            academic_class=selected_class,
            component_key=component_key,
        )
        context = {
            "current_session": session,
            "current_term": term,
            "selected_class": selected_class,
            "selected_ca_component": component_key,
            "selected_ca_label": _ca_component_label(component_key),
            "school_profile": pdf_school_profile(),
            "logo_data_uri": school_logo_data_uri(),
            "watermark_data_uri": school_logo_data_uri(),
            "matrix": matrix,
            "leaders": _component_subject_leaders_from_matrix(matrix, component_key=component_key),
            "score_label": _subject_leader_score_label(component_key, term),
            "generated_at": timezone.now(),
        }
        html = render_to_string("results/subject_best_report_pdf.html", context, request=request)
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{component_key}-{selected_class.code}-subject-best.pdf"'
        response.write(HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf())
        return response


class CA1ClassReportExcelView(ResultReportAccessMixin, TemplateView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def get(self, request, *args, **kwargs):
        session, term = self._window()
        component_key = _selected_ca_component(request, term=term)
        selected_class = get_object_or_404(_academic_performance_class_options(component_key, term=term), pk=kwargs["class_id"])
        page_size = str(request.GET.get("page_size") or request.GET.get("paper") or "a4").strip().lower()
        pdf_page_size = "tabloid" if page_size in {"tabloid", "11x17", "ledger"} else "a4"
        context = {
            "current_session": session,
            "current_term": term,
            "selected_class": selected_class,
            "selected_ca_component": component_key,
            "selected_ca_label": _ca_component_label(component_key),
            "pdf_page_size": pdf_page_size,
            "school_profile": pdf_school_profile(),
            "logo_data_uri": school_logo_data_uri(),
            "watermark_data_uri": school_logo_data_uri(),
            "matrix": _class_ca_matrix(
                session=session,
                term=term,
                academic_class=selected_class,
                component_key=component_key,
            ),
        }
        html = render_to_string("results/ca1_class_report_excel.html", context, request=request)
        response = HttpResponse(html, content_type="application/vnd.ms-excel; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{component_key}-{selected_class.code}.xls"'
        return response


class CA1ClassReportPDFView(ResultReportAccessMixin, TemplateView):
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR, ROLE_FORM_TEACHER}

    def get(self, request, *args, **kwargs):
        from weasyprint import HTML

        session, term = self._window()
        component_key = _selected_ca_component(request, term=term)
        selected_class = get_object_or_404(_academic_performance_class_options(component_key, term=term), pk=kwargs["class_id"])
        context = {
            "current_session": session,
            "current_term": term,
            "selected_class": selected_class,
            "selected_ca_component": component_key,
            "selected_ca_label": _ca_component_label(component_key),
            "school_profile": pdf_school_profile(),
            "logo_data_uri": school_logo_data_uri(),
            "watermark_data_uri": school_logo_data_uri(),
            "matrix": _class_ca_matrix(
                session=session,
                term=term,
                academic_class=selected_class,
                component_key=component_key,
            ),
        }
        html = render_to_string("results/ca1_class_report_pdf.html", context, request=request)
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{component_key}-{selected_class.code}.pdf"'
        response.write(HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf())
        return response


class AwardListingView(ResultReportAccessMixin, TemplateView):
    template_name = "results/award_listing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        selected_class = _selected_report_class(self.request)
        context["current_session"] = session
        context["current_term"] = term
        context["class_options"] = _report_class_options()
        context["selected_class"] = selected_class
        context["awards"] = build_award_listing(
            session=session,
            term=term,
            academic_class=selected_class,
        )
        return context


class ResultUploadStatisticsView(ResultReportAccessMixin, TemplateView):
    template_name = "results/result_upload_statistics.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        selected_class = _selected_report_class(self.request)
        context["current_session"] = session
        context["current_term"] = term
        context["class_options"] = _report_class_options()
        context["selected_class"] = selected_class
        context["stats"] = build_result_upload_statistics(
            session=session,
            term=term,
            academic_class=selected_class,
        )
        return context


class TeacherRankingView(ResultReportAccessMixin, TemplateView):
    template_name = "results/teacher_ranking.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        query = (self.request.GET.get("q") or "").strip().lower()
        ranking = build_teacher_ranking(session=session, term=term)
        if query:
            ranking["rows"] = [
                row for row in ranking.get("rows", [])
                if query in row["staff_name"].lower() or query in row["staff_id"].lower()
            ]
            for index, row in enumerate(ranking["rows"], start=1):
                row["rank"] = index
        context["current_session"] = session
        context["current_term"] = term
        context["query"] = query
        context["ranking"] = ranking
        return context


class PerformanceReportView(ResultReportAccessMixin, TemplateView):
    template_name = "results/performance_report.html"
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_FORM_TEACHER, ROLE_BURSAR}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        component_options = _academic_performance_component_options_for_term(term)
        student_query = (self.request.GET.get("q") or "").strip()
        student_id = (self.request.GET.get("student_id") or "").strip()

        leadership_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_VP, ROLE_PRINCIPAL, ROLE_BURSAR}
        if has_any_role(self.request.user, leadership_roles):
            allowed_classes = list(_report_class_options())
        else:
            class_ids_qs = form_teacher_classes_for_user(self.request.user, session=session).values_list(
                "academic_class_id", flat=True
            ) if session else []
            allowed_classes = list(_report_class_options().filter(id__in=class_ids_qs))
        allowed_class_ids = {row.id for row in allowed_classes}

        level_options = [row for row in allowed_classes if not row.base_class_id]
        arm_options = [row for row in allowed_classes if row.base_class_id]
        accessible_level_ids = {row.id for row in level_options}
        accessible_arm_ids = {row.id for row in arm_options}

        selected_level = _selected_report_level(self.request)
        if selected_level is not None and accessible_level_ids and selected_level.id not in accessible_level_ids:
            selected_level = None

        selected_arm = _selected_report_arm(self.request)
        if selected_arm is not None and accessible_arm_ids and selected_arm.id not in accessible_arm_ids:
            selected_arm = None

        if selected_level is None and selected_arm is None:
            if level_options:
                selected_level = level_options[0]
            elif arm_options:
                selected_arm = arm_options[0]

        if selected_arm is not None:
            selected_level = selected_arm.base_class

        filtered_arm_options = [
            row for row in arm_options if selected_level is None or row.base_class_id == selected_level.id
        ]
        selected_class = selected_arm or selected_level

        student_qs = User.objects.select_related("student_profile").filter(primary_role__code="STUDENT")
        if student_query:
            student_qs = student_qs.filter(
                Q(first_name__icontains=student_query)
                | Q(last_name__icontains=student_query)
                | Q(username__icontains=student_query)
                | Q(student_profile__student_number__icontains=student_query)
            )
        if session is not None and term is not None:
            student_qs = student_qs.filter(
                student_subject_scores__result_sheet__session=session,
                student_subject_scores__result_sheet__term=term,
            ).distinct()
        if selected_arm is not None:
            student_qs = student_qs.filter(
                class_enrollments__session=session,
                class_enrollments__academic_class_id=selected_arm.id,
                class_enrollments__is_active=True,
            ).distinct()
        elif selected_level is not None:
            student_qs = student_qs.filter(
                class_enrollments__session=session,
                class_enrollments__academic_class_id__in=selected_level.cohort_class_ids(),
                class_enrollments__is_active=True,
            ).distinct()
        elif allowed_class_ids and not has_any_role(self.request.user, leadership_roles):
            student_qs = student_qs.filter(
                class_enrollments__session=session,
                class_enrollments__academic_class_id__in=allowed_class_ids,
                class_enrollments__is_active=True,
            ).distinct()

        selected_student = None
        if student_id.isdigit():
            selected_student = student_qs.filter(id=int(student_id)).first()
        report = (
            build_student_performance_report(student=selected_student, session=session, term=term)
            if selected_student is not None
            else {"available": False}
        )
        class_performance = build_class_performance_snapshot(
            session=session,
            term=term,
            academic_class=selected_class,
        )
        selected_component = (
            _selected_academic_performance_component(self.request, term=term)
            if (self.request.GET.get("ca") or "").strip()
            else "ca23"
        )
        component_matrix = (
            _class_ca_matrix(
                session=session,
                term=term,
                academic_class=selected_class,
                component_key=selected_component,
            )
            if selected_class is not None
            else {"available": False, "rows": [], "top_three": [], "missing_cells": []}
        )
        component_subject_leaders = (
            _component_subject_leaders_from_matrix(component_matrix, component_key=selected_component)
            if component_matrix.get("available")
            else []
        )

        context["current_session"] = session
        context["current_term"] = term
        context["available_sessions"] = getattr(self, "report_available_sessions", [])
        context["available_terms"] = getattr(self, "report_available_terms", [])
        context["selected_session"] = session
        context["selected_term"] = term
        context["use_legacy_result_layout"] = _uses_legacy_result_layout(term)
        context["student_query"] = student_query
        context["level_options"] = level_options
        context["arm_options"] = filtered_arm_options
        context["selected_level"] = selected_level
        context["selected_arm"] = selected_arm
        context["selected_class"] = selected_class
        context["student_rows"] = list(student_qs.order_by(
            "first_name",
            "last_name",
            "student_profile__middle_name",
            "student_profile__student_number",
            "username",
        )[:50])
        context["selected_student"] = selected_student
        context["report"] = report
        context["class_performance"] = class_performance
        context["performance_component_options"] = component_options
        context["selected_performance_component"] = selected_component
        context["selected_performance_component_label"] = _ca_component_label(selected_component)
        context["term_filter_query"] = _term_filter_query(session, term)
        context["selected_component_query"] = _term_filter_query(session, term, ca=selected_component)
        context["component_matrix"] = component_matrix
        context["component_subject_leaders"] = component_subject_leaders
        context["component_class_csv_url"] = (
            reverse("results:academic-performance-class-csv", kwargs={"class_id": selected_class.id})
            if selected_class is not None
            else ""
        )
        context["component_subject_best_csv_url"] = (
            reverse("results:academic-performance-class-subject-best-csv", kwargs={"class_id": selected_class.id})
            if selected_class is not None
            else ""
        )
        context["component_subject_best_pdf_url"] = (
            reverse("results:academic-performance-class-subject-best-pdf", kwargs={"class_id": selected_class.id})
            if selected_class is not None
            else ""
        )
        context["component_class_print_url"] = (
            reverse("results:academic-performance-class", kwargs={"class_id": selected_class.id})
            if selected_class is not None
            else ""
        )
        context["term_report_pdf_url"] = ""
        context["performance_pdf_url"] = ""
        context["send_results_url"] = reverse("results:send-results") if not self.request.user.has_role(ROLE_DEAN) else ""
        if cloud_staff_operations_lan_only_enabled() and user_has_lan_only_operation_roles(self.request.user):
            context["send_results_url"] = ""
        compilation = report.get("compilation")
        if (
            report.get("available")
            and compilation is not None
            and getattr(compilation, "pk", None)
            and can_staff_download_term_report(user=self.request.user, compilation=compilation)
        ):
            if compilation.status == ClassCompilationStatus.PUBLISHED:
                context["term_report_pdf_url"] = reverse(
                    "pdfs:staff-term-report-download",
                    kwargs={"compilation_id": compilation.id, "student_id": selected_student.id},
                )
            context["performance_pdf_url"] = reverse(
                "pdfs:staff-performance-analysis-download",
                kwargs={"compilation_id": compilation.id, "student_id": selected_student.id},
            )
        return context


class SendResultsView(ResultReportAccessMixin, TemplateView):
    template_name = "results/send_results.html"
    allowed_roles = RESULT_SHARE_ROLES - {ROLE_DEAN}

    @staticmethod
    def _filtered_redirect(request):
        params = {}
        for key in ("q", "class_id", "session_id", "term_id"):
            value = (request.POST.get(key) or "").strip()
            if value:
                params[key] = value
        url = reverse("results:send-results")
        if params:
            url = f"{url}?{urlencode(params)}"
        return redirect(url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        query = (self.request.GET.get("q") or "").strip()
        selected_class = _selected_result_share_class(
            self.request,
            user=self.request.user,
            session=session,
            term=term,
        )
        class_options = list(
            _result_share_class_options(
                user=self.request.user,
                session=session,
                term=term,
            )
        )
        records = _result_share_base_queryset(
            user=self.request.user,
            session=session,
            term=term,
        )
        if selected_class is not None:
            records = records.filter(compilation__academic_class_id__in=selected_class.cohort_class_ids())
        if query:
            records = records.filter(
                Q(student__first_name__icontains=query)
                | Q(student__last_name__icontains=query)
                | Q(student__username__icontains=query)
                | Q(student__student_profile__student_number__icontains=query)
                | Q(compilation__academic_class__code__icontains=query)
                | Q(compilation__academic_class__display_name__icontains=query)
            )
        records = records.order_by(
            "compilation__academic_class__code",
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )[:80]
        share_rows = [
            _build_result_share_row(request=self.request, record=record)
            for record in records
        ]
        compilation_qs = ClassResultCompilation.objects.select_related(
            "academic_class", "session", "term", "form_teacher"
        ).filter(session=session, term=term)
        if selected_class is not None:
            compilation_qs = compilation_qs.filter(academic_class_id__in=selected_class.cohort_class_ids())
        elif not has_any_role(self.request.user, RESULT_SHARE_OVERSIGHT_ROLES):
            compilation_qs = compilation_qs.none()
        class_publish_rows = []
        for compilation in compilation_qs.order_by("academic_class__code"):
            filter_query = urlencode({
                "session_id": session.id if session else "",
                "term_id": term.id if term else "",
                "class_id": compilation.academic_class_id,
            })
            class_publish_rows.append({
                "compilation": compilation,
                "student_count": ClassResultStudentRecord.objects.filter(compilation=compilation).count(),
                "is_published": compilation.status == ClassCompilationStatus.PUBLISHED,
                "academic_performance_url": (
                    f"{reverse('results:academic-performance-class', kwargs={'class_id': compilation.academic_class_id})}?{filter_query}"
                ),
                "performance_url": f"{reverse('results:performance-report')}?{filter_query}",
            })
        context["current_session"] = session
        context["current_term"] = term
        context["available_sessions"] = getattr(self, "report_available_sessions", [])
        context["available_terms"] = getattr(self, "report_available_terms", [])
        context["selected_session"] = session
        context["selected_term"] = term
        context["query"] = query
        context["class_options"] = class_options
        context["selected_class"] = selected_class
        context["share_rows"] = share_rows
        context["class_publish_rows"] = class_publish_rows
        context["students_ready_count"] = len(share_rows)
        context["email_ready_count"] = sum(1 for row in share_rows if row["email_targets"])
        context["whatsapp_ready_count"] = sum(1 for row in share_rows if row["whatsapp_url"])
        context["pin_ready_count"] = sum(1 for row in share_rows if row["pin_state"]["label"] == "Issued")
        context["can_manage_pins"] = has_any_role(self.request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL})
        context["whatsapp_provider_enabled"] = get_whatsapp_provider().provider_name != "disabled"
        context["cloud_sync_configured"] = _class_result_cloud_endpoint_configured()
        context["can_push_cloud_results"] = self.request.user.has_role(ROLE_IT_MANAGER)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "email_notice").strip().lower()
        if action == "publish_lan_cloud_class":
            if not request.user.has_role(ROLE_IT_MANAGER):
                messages.error(request, "Only IT Manager can push results to cloud.")
                return self._filtered_redirect(request)
            if not _class_result_cloud_endpoint_configured():
                messages.error(
                    request,
                    "Cloud result push is not configured. Set MANUAL_UPDATE_REMOTE_BASE_URL and MANUAL_UPDATE_TOKEN before pushing.",
                )
                return self._filtered_redirect(request)
            compilation = get_object_or_404(
                ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
                pk=request.POST.get("compilation_id"),
            )
            try:
                with transaction.atomic():
                    if compilation.status != ClassCompilationStatus.PUBLISHED:
                        mark_compilation_published(
                            compilation,
                            request.user,
                            principal_override=True,
                            comment="Published from class result cloud push page.",
                        )
                    sheets_qs = ResultSheet.objects.filter(
                        academic_class=_instructional_class(compilation.academic_class),
                        session=compilation.session,
                        term=compilation.term,
                    )
                    transition_class_sheet_set(
                        sheets_qs=sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED),
                        to_status=ResultSheetStatus.PUBLISHED,
                        actor=request.user,
                        action="IT_CLASS_RESULT_PUBLISH",
                        comment="Class result published from Send Results page.",
                    )
                    log_results_approval(
                        actor=request.user,
                        request=request,
                        metadata={
                            "action": "IT_CLASS_RESULT_PUBLISH",
                            "compilation_id": str(compilation.id),
                            "class_id": str(compilation.academic_class_id),
                        },
                    )
                result = _push_class_result_to_cloud_once(compilation=compilation)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return self._filtered_redirect(request)
            messages.success(
                request,
                (
                    f"{compilation.academic_class.code} {compilation.term.get_name_display()} result "
                    f"published on LAN and pushed to cloud: {result['student_count']} student(s), "
                    f"{result['imported']} imported, {result['skipped']} skipped."
                ),
            )
            return self._filtered_redirect(request)

        if action not in {"email_notice", "whatsapp_notice"}:
            messages.error(request, "Invalid result communication action.")
            return self._filtered_redirect(request)
        session, term = self._window()
        if session is None or term is None:
            messages.error(request, "Current session and term must be set before sending result notices.")
            return self._filtered_redirect(request)
        record = get_object_or_404(
            _result_share_base_queryset(user=request.user, session=session, term=term),
            compilation_id=request.POST.get("compilation_id"),
            student_id=request.POST.get("student_id"),
        )
        row = _build_result_share_row(request=request, record=record)
        if row.get("fee_locked"):
            messages.error(
                request,
                f"Result notice blocked for {row['student_name']}. Outstanding school-fee balance: {row['fee_outstanding']}.",
            )
            return self._filtered_redirect(request)
        school_profile = SchoolProfile.load()
        title = f"{school_profile.school_name or 'NDGA'} {record.compilation.term.get_name_display()} Result Notice"
        body_text = _build_result_share_message(
            student=record.student,
            compilation=record.compilation,
            portal_url=row["portal_url"],
            pin_state=row["pin_state"],
        )
        if action == "email_notice":
            if not row["email_targets"]:
                messages.error(request, "No student or guardian email is available for this record.")
                return self._filtered_redirect(request)
            result = send_email_event(
                to_emails=row["email_targets"],
                subject=title,
                body_text=body_text,
                actor=request.user,
                request=request,
                metadata={
                    "event": "RESULT_SHARE_NOTICE",
                    "channel": "email",
                    "student_id": str(record.student_id),
                    "compilation_id": str(record.compilation_id),
                },
            )
            if result is None or not result.success:
                messages.error(request, f"Email dispatch failed for {row['student_name']}.")
                return self._filtered_redirect(request)
        else:
            if not row["whatsapp_numbers"]:
                messages.error(request, "No guardian WhatsApp number is available for this record.")
                return self._filtered_redirect(request)
            result = send_whatsapp_event(
                to_numbers=row["whatsapp_numbers"],
                body_text=body_text,
                actor=request.user,
                request=request,
                metadata={
                    "event": "RESULT_SHARE_NOTICE",
                    "channel": "whatsapp",
                    "student_id": str(record.student_id),
                    "compilation_id": str(record.compilation_id),
                },
            )
            if not result.success and result.sent_count <= 0:
                messages.error(request, f"WhatsApp dispatch failed for {row['student_name']}.")
                return self._filtered_redirect(request)
        create_notification(
            recipient=record.student,
            category=NotificationCategory.RESULTS,
            title="Result Notice Sent",
            message=(
                f"A result access notice was sent for {record.compilation.term.get_name_display()} "
                f"{record.compilation.session.name}."
            ),
            created_by=request.user,
            action_url=reverse("pdfs:student-reports"),
            metadata={
                "compilation_id": str(record.compilation_id),
                "shared_by": str(request.user.id),
            },
        )
        messages.success(
            request,
            (
                f"Result notice emailed to {len(row['email_targets'])} contact(s) for {row['student_name']}."
                if action == "email_notice"
                else f"Result notice sent by WhatsApp for {row['student_name']}."
            )
        )
        return self._filtered_redirect(request)


class ResultAccessPinManagementView(ResultReportAccessMixin, TemplateView):
    template_name = "results/result_access_pins.html"
    allowed_roles = {ROLE_IT_MANAGER, ROLE_PRINCIPAL}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = self._window()
        query = (self.request.GET.get("q") or "").strip()
        pin_qs = ResultAccessPin.objects.select_related("student__student_profile", "generated_by", "session", "term")
        if session is not None and term is not None:
            pin_qs = pin_qs.filter(session=session, term=term)
        if query:
            pin_qs = pin_qs.filter(
                Q(student__first_name__icontains=query)
                | Q(student__last_name__icontains=query)
                | Q(student__username__icontains=query)
                | Q(student__student_profile__student_number__icontains=query)
                | Q(pin_code__icontains=query)
            )
        student_qs = User.objects.select_related("student_profile").filter(primary_role__code="STUDENT", is_active=True)
        if session is not None and term is not None:
            student_qs = student_qs.filter(class_result_records__compilation__session=session, class_result_records__compilation__term=term).distinct()
        context["current_session"] = session
        context["current_term"] = term
        context["query"] = query
        context["pin_rows"] = pin_qs.order_by(
            "student__first_name",
            "student__last_name",
            "student__student_profile__middle_name",
            "student__student_profile__student_number",
            "student__username",
        )[:80]
        context["student_rows"] = student_qs.order_by(
            "first_name",
            "last_name",
            "student_profile__middle_name",
            "student_profile__student_number",
            "username",
        )[:80]
        context["school_profile"] = SchoolProfile.load()
        return context

    def post(self, request, *args, **kwargs):
        session, term = self._window()
        if session is None or term is None:
            messages.error(request, "Current session and term are required before generating result PINs.")
            return redirect("results:result-access-pins")
        action = (request.POST.get("action") or "generate").strip().lower()
        student = get_object_or_404(User.objects.select_related("student_profile"), pk=request.POST.get("student_id"), primary_role__code="STUDENT")
        if action == "deactivate":
            ResultAccessPin.objects.filter(student=student, session=session, term=term).update(is_active=False)
            messages.success(request, "Result PIN deactivated.")
            return redirect("results:result-access-pins")
        pin_code = (request.POST.get("pin_code") or "").strip().upper()
        if not pin_code:
            pin_code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        row, _created = ResultAccessPin.objects.update_or_create(
            student=student,
            session=session,
            term=term,
            defaults={
                "pin_code": pin_code,
                "generated_by": request.user,
                "is_active": True,
            },
        )
        messages.success(request, f"Result PIN saved for {student.get_full_name() or student.username}: {row.pin_code}")
        return redirect("results:result-access-pins")



class ClassTimelineView(ResultsAccessMixin, TemplateView):
    template_name = "results/class_timeline.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        class_id = self.kwargs["class_id"]
        context["submissions"] = ResultSubmission.objects.select_related(
            "result_sheet__subject", "actor"
        ).filter(
            result_sheet__academic_class_id=class_id,
            result_sheet__session=session,
            result_sheet__term=term,
        ).order_by("created_at")
        context["compilation"] = ClassResultCompilation.objects.filter(
            academic_class_id=class_id,
            session=session,
            term=term,
        ).first()
        context["class_id"] = class_id
        return context
