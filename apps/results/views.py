import base64
import binascii
from decimal import Decimal
import secrets
from urllib.parse import urlencode
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Sum, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import RedirectView, TemplateView

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.permissions import has_any_role
from apps.accounts.models import User
from apps.academics.models import (
    AcademicClass,
    FormTeacherAssignment,
    GradeScale,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeacherSubjectAssignment,
)
from apps.attendance.models import SchoolCalendar
from apps.audit.services import log_results_approval, log_results_edit
from apps.cbt.models import (
    CBTSimulationWrapperStatus,
    CBTExamStatus,
    Exam,
    SimulationWrapper,
)
from apps.notifications.models import NotificationCategory
from apps.notifications.services import create_notification, extract_whatsapp_phones, notify_results_published, send_email_event, send_whatsapp_event
from apps.notifications.whatsapp_adapters import get_whatsapp_provider
from apps.pdfs.services import can_staff_download_term_report
from apps.results.entry_flow import (
    build_posted_score_bundle,
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
from apps.results.services import compute_grade_payload
from apps.results.utils import (
    RESULTS_STAGE7_ROLES,
    current_session_term,
    form_teacher_classes_for_user,
    principal_override_enabled,
    resolve_teacher_assignment_window,
    session_is_open_for_edits,
    sheet_is_editable_by_subject_owner,
)
from apps.setup_wizard.services import get_setup_state
from apps.results.workflow import (
    mark_compilation_published,
    mark_compilation_rejected_by_vp,
    mark_compilation_submitted_to_vp,
    transition_class_sheet_set,
    transition_result_sheet,
)
from apps.finance.models import FinanceInstitutionProfile
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
from apps.tenancy.utils import cloud_staff_operations_lan_only_enabled, user_has_lan_only_operation_roles
from apps.results.insights import build_result_comment_bundle
from apps.tenancy.utils import build_portal_url


def _get_or_create_sheet_from_assignment(assignment, actor):
    sheet, _ = ResultSheet.objects.get_or_create(
        academic_class=assignment.academic_class,
        subject=assignment.subject,
        session=assignment.session,
        term=assignment.term,
        defaults={"created_by": actor},
    )
    return sheet


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


def _cohort_class_ids(academic_class):
    if not academic_class:
        return []
    return academic_class.cohort_class_ids()


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
        "email_targets": _guardian_email_list(student),
        "pin_state": pin_state,
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
    }


def _average_to_decimal(total, count):
    if not count:
        return Decimal("0.00")
    return (Decimal(total) / Decimal(count)).quantize(Decimal("0.01"))


def _score_decimal(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _nullable_decimal_from_post(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None
    try:
        return Decimal(value).quantize(Decimal("0.1"))
    except Exception:
        return None


def _publish_allowed_for_actor(*, actor, compilation):
    if actor.has_role(ROLE_PRINCIPAL):
        return compilation.status in {
            ClassCompilationStatus.SUBMITTED_TO_VP,
            ClassCompilationStatus.REJECTED_BY_VP,
        }
    return compilation.status == ClassCompilationStatus.SUBMITTED_TO_VP


def _reject_allowed_for_actor(*, actor, compilation):
    if actor.has_role(ROLE_PRINCIPAL):
        return compilation.status in {
            ClassCompilationStatus.SUBMITTED_TO_VP,
            ClassCompilationStatus.PUBLISHED,
        }
    return compilation.status == ClassCompilationStatus.SUBMITTED_TO_VP


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
    sheets = list(
        ResultSheet.objects.filter(
            academic_class=_instructional_class(compilation.academic_class),
            session=compilation.session,
            term=compilation.term,
        )
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
        rows.append(
            {
                "subject": sheet.subject,
                "sheet_status": sheet.status,
                "ca1": _score_decimal(score.ca1),
                "ca2": _score_decimal(score.ca2),
                "ca3": _score_decimal(score.ca3),
                "ca4": _score_decimal(score.ca4),
                "objective": _score_decimal(score.objective),
                "theory": _score_decimal(score.theory),
                "exam_total": _score_decimal(Decimal(score.objective or 0) + Decimal(score.theory or 0)),
                "grand_total": _score_decimal(score.grand_total),
                "grade": score.grade or "-",
            }
        )
    return rows


def _student_result_payload_for_compilation(*, compilation, student):
    subject_rows = _subject_rows_for_student(compilation=compilation, student=student)
    subject_count = len(subject_rows)
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
        fail_count=len([row for row in subject_rows if (row.get("grade") or "F") == "F"]),
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
        "subject_count": subject_count,
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


def _build_comment_bundle(*, student_name, average_score, fail_count, attendance_percentage, weak_subjects=None, predicted_score=None, risk_label=None):
    fallback_risk = risk_label or ("High" if (float(attendance_percentage or 0) < 60 or int(fail_count or 0) >= 2) else "Low")
    return build_result_comment_bundle(
        student_name=student_name,
        average_score=average_score,
        attendance_percentage=attendance_percentage,
        fail_count=fail_count,
        weak_subjects=weak_subjects or [],
        predicted_score=predicted_score,
        risk_label=fallback_risk,
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
        for assignment in self.assignments:
            sheet = _get_or_create_sheet_from_assignment(assignment, self.request.user)
            enrollment_qs = _subject_enrollments_for_assignment(assignment)
            enrolled_student_ids = list(enrollment_qs.values_list("student_id", flat=True))
            score_count = StudentSubjectScore.objects.filter(
                result_sheet=sheet,
                student_id__in=enrolled_student_ids,
            ).count()
            can_edit = (
                request_user_can_edit_session(self.request.user, assignment.session)
                and sheet_is_editable_by_subject_owner(self.request.user, sheet)
            )
            rows.append(
                {
                    "assignment": assignment,
                    "result_sheet": sheet,
                    "score_count": score_count,
                    "enrollment_count": len(enrolled_student_ids),
                    "can_submit": can_edit,
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
        return context

    def post(self, request, *args, **kwargs):
        assignment_id = (request.POST.get("assignment_id") or "").strip()
        assignment = next(
            (row for row in self.assignments if str(row.id) == assignment_id),
            None,
        )
        if assignment is None:
            messages.error(request, "Invalid subject submission target.")
            return redirect(self._current_url())

        if not request_user_can_edit_session(request.user, assignment.session):
            messages.error(request, "This session is closed. Result sheets are read-only.")
            return redirect(self._current_url())

        sheet = _get_or_create_sheet_from_assignment(assignment, request.user)
        if not sheet_is_editable_by_subject_owner(request.user, sheet):
            messages.error(request, "This subject sheet is already locked for review.")
            return redirect(self._current_url())

        enrollments = _subject_enrollments_for_assignment(assignment)
        for enrollment in enrollments:
            StudentSubjectScore.objects.get_or_create(
                result_sheet=sheet,
                student=enrollment.student,
            )

        transition_result_sheet(
            sheet=sheet,
            to_status=ResultSheetStatus.SUBMITTED_TO_DEAN,
            actor=request.user,
            action="SUBMIT_TO_DEAN",
            comment="",
        )
        log_results_approval(
            actor=request.user,
            request=request,
            metadata={
                "action": "SUBMIT_TO_DEAN",
                "sheet_id": str(sheet.id),
                "status": sheet.status,
            },
        )
        messages.success(request, f"{assignment.subject.name} submitted to Dean.")
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
        enrollments = _subject_enrollments_for_assignment(assignment).order_by(
            "student__username"
        )
        student_ids = [row.student_id for row in enrollments]
        score_map = {
            row.student_id: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet=sheet,
                student_id__in=student_ids,
            )
        }
        policies = sheet_policy_state(sheet)
        rows = []
        for enrollment in enrollments:
            score = score_map.get(enrollment.student_id)
            rows.append(
                {
                    "enrollment": enrollment,
                    "score": score,
                    "locked_fields": score.normalized_locked_fields() if score else [],
                    "cbt": row_component_state(score, policies),
                }
            )
        return self.render_to_response(
            self.get_context_data(
                assignment=assignment,
                result_sheet=sheet,
                rows=rows,
                cbt_policies=policies,
                can_edit=(
                    request_user_can_edit_session(request.user, assignment.session)
                    and sheet_is_editable_by_subject_owner(request.user, sheet)
                ),
                class_subjects_url=self._class_subjects_url(assignment=assignment),
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
        if not request_user_can_edit_session(request.user, assignment.session):
            message = "This session is closed. Result sheets are read-only."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return redirect(self._class_subjects_url(assignment=assignment))

        sheet = _get_or_create_sheet_from_assignment(assignment, request.user)
        if not sheet_is_editable_by_subject_owner(request.user, sheet):
            message = "Sheet is locked. Awaiting dean review."
            if is_autosave:
                return JsonResponse({"ok": False, "error": message}, status=400)
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
        policies, policy_warnings, policy_changed = read_sheet_policies_from_post(
            sheet,
            request.POST,
            list(existing_scores.values()),
        )
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
                    payload = row["payload"]
                    score.ca1 = payload.ca1
                    score.ca2 = payload.ca2
                    score.ca3 = payload.ca3
                    score.ca4 = payload.ca4
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
                    log_results_edit(
                        actor=request.user,
                        request=request,
                        metadata={
                            "sheet_id": str(sheet.id),
                            "student_id": str(score.student_id),
                            "violations": payload.violations,
                        },
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
        score = form.save()
        payload = getattr(form, "computed_payload", None)
        log_results_edit(
            actor=request.user,
            request=request,
            metadata={
                "sheet_id": str(self.sheet.id),
                "student_id": str(score.student_id),
                "violations": payload.violations if payload else {},
            },
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
        return {
            "filter_class_id": (self.request.GET.get("class_id") or "").strip(),
            "filter_subject_id": (self.request.GET.get("subject_id") or "").strip(),
            "available_classes": (
                TeacherSubjectAssignment.objects.filter(
                    session=session,
                    term=term,
                    is_active=True,
                )
                .values("academic_class_id", "academic_class__code")
                .distinct()
                .order_by("academic_class__code")
            ),
            "available_subjects": (
                TeacherSubjectAssignment.objects.filter(
                    session=session,
                    term=term,
                    is_active=True,
                )
                .values("subject_id", "subject__name")
                .distinct()
                .order_by("subject__name")
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
        sheet_ids = request.POST.getlist("sheet_ids")
        class_id = (request.POST.get("class_id") or "").strip()
        comment = (request.POST.get("comment") or "").strip()

        target_qs = ResultSheet.objects.filter(
            session=session,
            term=term,
            status=ResultSheetStatus.SUBMITTED_TO_DEAN,
        )
        if sheet_ids:
            target_qs = target_qs.filter(id__in=sheet_ids)
        elif class_id.isdigit():
            target_qs = target_qs.filter(academic_class_id=int(class_id))
        else:
            messages.error(request, "Select at least one result sheet or class.")
            return redirect("results:dean-result-review-list")

        sheets = list(target_qs.select_related("academic_class", "subject"))
        if not sheets:
            messages.error(request, "No submitted result sheet found for this action.")
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
            for sheet in sheets:
                transition_result_sheet(
                    sheet=sheet,
                    to_status=to_status,
                    actor=request.user,
                    action=action_code,
                    comment=comment,
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": action_code,
                        "sheet_id": str(sheet.id),
                        "class_id": str(sheet.academic_class_id),
                        "subject_id": str(sheet.subject_id),
                    },
                )

        messages.success(request, f"{len(sheets)} sheet(s) updated.")
        return redirect("results:dean-result-review-list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session, term = current_session_term()
        sheets_qs = self._filtered_sheets_queryset(session=session, term=term)
        context["current_session"] = session
        context["current_term"] = term
        context["sheets"] = sheets_qs
        context["result_pending_count"] = sheets_qs.filter(
            status=ResultSheetStatus.SUBMITTED_TO_DEAN
        ).count()
        context["result_approved_count"] = sheets_qs.filter(
            status=ResultSheetStatus.APPROVED_BY_DEAN
        ).count()
        context["result_rejected_count"] = sheets_qs.filter(
            status=ResultSheetStatus.REJECTED_BY_DEAN
        ).count()
        context["result_class_rows"] = (
            sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_DEAN)
            .values("academic_class_id", "academic_class__code")
            .annotate(total=Count("id"))
            .order_by("academic_class__code")
        )
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
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sheet"] = self.sheet
        context["scores"] = self.sheet.student_scores.select_related("student").order_by(
            "student__username"
        )
        context["approve_form"] = ResultActionForm()
        context["reject_form"] = RejectActionForm()
        return context

    def post(self, request, *args, **kwargs):
        if not request_user_can_edit_session(request.user, self.sheet.session):
            messages.error(request, "This session is closed. Dean decisions are read-only.")
            return redirect("results:dean-review-detail", sheet_id=self.sheet.id)
        if self.sheet.status != ResultSheetStatus.SUBMITTED_TO_DEAN:
            messages.error(
                request,
                "This sheet is no longer in Dean review queue.",
            )
            return redirect("results:dean-review-detail", sheet_id=self.sheet.id)
        action = request.POST.get("action")
        if action == "approve":
            form = ResultActionForm(request.POST)
            if form.is_valid():
                transition_result_sheet(
                    sheet=self.sheet,
                    to_status=ResultSheetStatus.APPROVED_BY_DEAN,
                    actor=request.user,
                    action="DEAN_APPROVE",
                    comment=form.cleaned_data.get("comment", ""),
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={"action": "DEAN_APPROVE", "sheet_id": str(self.sheet.id)},
                )
                messages.success(request, "Sheet approved by Dean.")
                return redirect("results:dean-result-review-list")
        elif action == "reject":
            form = RejectActionForm(request.POST)
            if form.is_valid():
                transition_result_sheet(
                    sheet=self.sheet,
                    to_status=ResultSheetStatus.REJECTED_BY_DEAN,
                    actor=request.user,
                    action="DEAN_REJECT",
                    comment=form.cleaned_data["comment"],
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={"action": "DEAN_REJECT", "sheet_id": str(self.sheet.id)},
                )
                messages.success(request, "Sheet rejected back to subject teacher.")
                return redirect("results:dean-result-review-list")
        messages.error(request, "Invalid Dean decision payload.")
        return redirect("results:dean-review-detail", sheet_id=self.sheet.id)


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
        context["class_assignments"] = classes_qs
        context["selected_assignment"] = selected_assignment
        context["current_session"] = selected_assignment.session if selected_assignment else None
        context["current_term"] = None
        context["compilation"] = None
        context["rows"] = []
        context["can_submit"] = False
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
        approved_sheets_qs = sheets_qs.filter(status=ResultSheetStatus.APPROVED_BY_DEAN)
        subject_assignments = TeacherSubjectAssignment.objects.filter(
            academic_class=_instructional_class(selected_assignment.academic_class),
            session=selected_assignment.session,
            term=term,
            is_active=True,
        ).select_related("subject")
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
        search_query = context["search_query"]
        if search_query:
            enrollments = enrollments.filter(
                Q(student__first_name__icontains=search_query)
                | Q(student__last_name__icontains=search_query)
                | Q(student__username__icontains=search_query)
                | Q(student__student_profile__student_number__icontains=search_query)
            )
        enrollments = enrollments.order_by("student__username")

        record_map = {
            row.student_id: row
            for row in ClassResultStudentRecord.objects.filter(compilation=compilation).select_related("student")
        }
        calendar = SchoolCalendar.objects.filter(
            session=selected_assignment.session,
            term=term,
        ).first()

        score_rows = (
            StudentSubjectScore.objects.filter(
                result_sheet__in=approved_sheets_qs,
                student_id__in=enrollments.values_list("student_id", flat=True),
            )
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
            subject_count = int(score_info.get("subjects") or 0)
            average_score = _average_to_decimal(cumulative_total, subject_count)
            rows.append(
                {
                    "enrollment": enrollment,
                    "record": record,
                    "admission_number": _admission_number_for_student(student),
                    "approved_subject_count": subject_count,
                    "progress_label": f"{subject_count}/{required_subject_count} approved",
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
        context["can_submit"] = len(pending_subjects) == 0 and compilation.status in {
            ClassCompilationStatus.DRAFT,
            ClassCompilationStatus.REJECTED_BY_VP,
        }
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
        selected = self._selected_assignment(classes_qs)
        return self.render_to_response(self._build_context(classes_qs, selected))

    def post(self, request, *args, **kwargs):
        classes_qs = form_teacher_classes_for_user(request.user)
        selected = self._selected_assignment(classes_qs)
        if not selected:
            messages.error(request, "No form class found.")
            return redirect("results:form-compilation")

        context = self._build_context(classes_qs, selected)
        compilation = context["compilation"]
        if not compilation:
            messages.error(request, "Unable to initialize class compilation.")
            return redirect("results:form-compilation")
        if not request_user_can_edit_session(request.user, compilation.session):
            messages.error(request, "This session is closed. Compilation is read-only.")
            return redirect(f"{reverse('results:form-compilation')}?class_id={selected.academic_class_id}")
        if compilation.status not in {
            ClassCompilationStatus.DRAFT,
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
                        "Cannot submit to VP until all subject sheets are Dean-approved.",
                    )
                    return self.render_to_response(self._build_context(classes_qs, selected))
                if compilation.status not in {
                    ClassCompilationStatus.DRAFT,
                    ClassCompilationStatus.REJECTED_BY_VP,
                }:
                    messages.error(
                        request,
                        "Compilation is not in a submittable state.",
                    )
                    return self.render_to_response(self._build_context(classes_qs, selected))
                mark_compilation_submitted_to_vp(
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
                    action="FORM_SUBMIT_TO_VP",
                    comment="Compiled and submitted to VP.",
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "FORM_SUBMIT_TO_VP",
                        "compilation_id": str(compilation.id),
                        "class_id": str(compilation.academic_class_id),
                    },
                )
                messages.success(request, "Class compilation submitted to VP.")
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
        self.compilation, _ = ClassResultCompilation.objects.get_or_create(
            academic_class=self.class_assignment.academic_class,
            session=self.class_assignment.session,
            term=self.term,
            defaults={"form_teacher": self.class_assignment.teacher},
        )
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
        sheets = list(
            ResultSheet.objects.filter(
                academic_class=_instructional_class(self.class_assignment.academic_class),
                session=self.class_assignment.session,
                term=self.term,
            ).select_related("subject")
        )
        sheet_map = {sheet.subject_id: sheet for sheet in sheets}
        score_map = {
            row.result_sheet_id: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet_id__in=[sheet.id for sheet in sheets],
                student=self.student,
            )
        }
        rows = []
        editable_assignments = {
            assignment.subject_id: assignment
            for assignment in TeacherSubjectAssignment.objects.filter(
                teacher=self.request.user,
                academic_class=_instructional_class(self.class_assignment.academic_class),
                session=self.class_assignment.session,
                term=self.term,
                is_active=True,
            ).select_related("subject")
        }
        for subject_assignment in subject_assignments:
            sheet = sheet_map.get(subject_assignment.subject_id)
            score = score_map.get(sheet.id) if sheet else None
            is_dean_approved = bool(
                sheet and sheet.status == ResultSheetStatus.APPROVED_BY_DEAN
            )
            assignment = editable_assignments.get(subject_assignment.subject_id)
            can_edit_subject = bool(
                sheet
                and assignment is not None
                and request_user_can_edit_session(self.request.user, sheet.session)
                and sheet_is_editable_by_subject_owner(self.request.user, sheet)
            )
            edit_url = ""
            if can_edit_subject and assignment:
                query = urlencode(
                    {
                        "session_id": self.class_assignment.session_id,
                        "term_id": self.term.id,
                    }
                )
                edit_url = (
                    reverse("results:assignment-scores", kwargs={"assignment_id": assignment.id})
                    + f"?{query}"
                )
            rows.append(
                {
                    "subject_name": subject_assignment.subject.name,
                    "subject_assignment": subject_assignment,
                    "sheet": sheet,
                    "score": score,
                    "is_dean_approved": is_dean_approved,
                    "can_edit_subject": can_edit_subject,
                    "edit_url": edit_url,
                }
            )
        if offered_subject_ids:
            assigned_subject_ids = {row.subject_id for row in subject_assignments}
            missing_subject_ids = offered_subject_ids - assigned_subject_ids
            if missing_subject_ids:
                for subject in Subject.objects.filter(id__in=missing_subject_ids).order_by("name"):
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
        subject_count = len(subject_rows)
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
                if (
                    row["score"].grade
                    if row["is_dean_approved"] and row["score"] is not None
                    else "F"
                )
                == "F"
            ]
        )
        return {
            "subject_count": subject_count,
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
        comment_bundle = _build_comment_bundle(
            student_name=self.student.get_full_name() or self.student.username,
            average_score=summary["average_score"],
            fail_count=summary["fail_count"],
            attendance_percentage=attendance_percentage,
            weak_subjects=weak_subjects,
            predicted_score=(student_analytics.get("prediction") or {}).get("score"),
            risk_label=(student_analytics.get("risk") or {}).get("label"),
        )
        context["student_analytics"] = student_analytics
        context["comment_bundle"] = comment_bundle
        context["suggested_comment"] = comment_bundle["teacher_comment"]
        context["teacher_suggestions"] = comment_bundle.get("teacher_suggestions", [])
        behavior_breakdown = _normalize_behavior_breakdown(
            self.record.behavior_breakdown,
            seed=self.record.behavior_rating,
        )
        context["behavior_metrics"] = [
            {"code": code, "label": label, "value": behavior_breakdown.get(code, 3)}
            for code, label in _behavior_metric_fields()
        ]
        context["behavior_rating"] = _behavior_average_rating(behavior_breakdown)
        context["back_url"] = f"{reverse('results:form-compilation')}?class_id={self.class_assignment.academic_class_id}"
        context["is_read_only"] = (
            self.compilation.status == ClassCompilationStatus.PUBLISHED
            or not request_user_can_edit_session(self.request.user, self.compilation.session)
        )
        return context

    def post(self, request, *args, **kwargs):
        is_autosave = (
            request.POST.get("_autosave") == "1"
            and request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )
        if self.compilation.status == ClassCompilationStatus.PUBLISHED:
            message = "This compilation is published and locked."
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
                comment = _generate_comment_suggestion(
                    average_score=summary["average_score"],
                    fail_count=summary["fail_count"],
                    attendance_percentage=self.record.attendance_percentage,
                    student_name=self.student.get_full_name() or self.student.username,
                    weak_subjects=[row["subject"] for row in student_analytics.get("weak_subjects", [])],
                    predicted_score=(student_analytics.get("prediction") or {}).get("score"),
                    risk_label=(student_analytics.get("risk") or {}).get("label"),
                )
        elif action == "apply_teacher_suggestion":
            comment = (request.POST.get("selected_suggestion") or "").strip() or comment

        self.record.behavior_rating = behavior
        self.record.behavior_breakdown = behavior_breakdown
        self.record.teacher_comment = comment
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


class ResultApprovalClassListView(ResultsAccessMixin, TemplateView):
    template_name = "results/approval_class_list.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Results approval access is restricted to VP, Principal, or IT Manager.")
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
        context["principal_override_enabled"] = self.request.user.has_role(ROLE_PRINCIPAL)
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
        principal_override = request.user.has_role(ROLE_PRINCIPAL)

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
                        principal_override=principal_override,
                    )
                    if principal_override:
                        publish_sheet_qs = sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED)
                        action_code = "PRINCIPAL_OVERRIDE_PUBLISH"
                        action_comment = "Bulk publish from class approval page."
                    else:
                        publish_sheet_qs = sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP)
                        action_code = "VP_PUBLISH"
                        action_comment = "Bulk publish from class approval page."
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
                    principal_override=principal_override,
                )
                if principal_override:
                    reject_sheet_qs = sheets_qs.exclude(status=ResultSheetStatus.REJECTED_BY_VP)
                    action_code = "PRINCIPAL_OVERRIDE_REJECT"
                else:
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
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Results approval access is restricted to VP, Principal, or IT Manager.")
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
        enrollments = list(enrollments.order_by("student__username"))
        student_ids = [row.student_id for row in enrollments]
        score_map = {
            row["student_id"]: row
            for row in StudentSubjectScore.objects.filter(
                result_sheet__academic_class=_instructional_class(self.compilation.academic_class),
                result_sheet__session=self.compilation.session,
                result_sheet__term=self.compilation.term,
                student_id__in=student_ids,
            )
            .values("student_id")
            .annotate(subject_count=Count("id"), total_score=Sum("grand_total"))
        }
        record_map = {
            row.student_id: row
            for row in self.compilation.student_records.select_related("student")
        }
        student_rows = []
        for enrollment in enrollments:
            student = enrollment.student
            score_info = score_map.get(student.id) or {}
            subject_count = int(score_info.get("subject_count") or 0)
            total_score = _score_decimal(score_info.get("total_score") or 0)
            record = record_map.get(student.id)
            student_rows.append(
                {
                    "student": student,
                    "admission_number": _admission_number_for_student(student),
                    "subject_count": subject_count,
                    "average_score": _average_to_decimal(total_score, subject_count),
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
        context["search_query"] = search_query
        context["back_url"] = reverse("results:approval-class-list")
        context["can_publish"] = _publish_allowed_for_actor(actor=self.request.user, compilation=self.compilation)
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
        if action not in {"publish_class", "reject_class"}:
            messages.error(request, "Invalid class management action.")
            return redirect("results:approval-class-detail", compilation_id=self.compilation.id)

        principal_override = request.user.has_role(ROLE_PRINCIPAL)
        sheets_qs = ResultSheet.objects.filter(
            academic_class=_instructional_class(self.compilation.academic_class),
            session=self.compilation.session,
            term=self.compilation.term,
        )

        if action == "publish_class":
            if not _publish_allowed_for_actor(actor=request.user, compilation=self.compilation):
                messages.error(request, "This class is not ready for publishing yet.")
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
                    principal_override=principal_override,
                    comment=publish_comment,
                )
                transition_class_sheet_set(
                    sheets_qs=(
                        sheets_qs.exclude(status=ResultSheetStatus.PUBLISHED)
                        if principal_override
                        else sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP)
                    ),
                    to_status=ResultSheetStatus.PUBLISHED,
                    actor=request.user,
                    action="PRINCIPAL_OVERRIDE_PUBLISH" if principal_override else "VP_PUBLISH",
                    comment=publish_comment or "Published from result management.",
                )
                log_results_approval(
                    actor=request.user,
                    request=request,
                    metadata={
                        "action": "PRINCIPAL_OVERRIDE_PUBLISH" if principal_override else "VP_PUBLISH",
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
                principal_override=principal_override,
            )
            transition_class_sheet_set(
                sheets_qs=(
                    sheets_qs.exclude(status=ResultSheetStatus.REJECTED_BY_VP)
                    if principal_override
                    else sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP)
                ),
                to_status=ResultSheetStatus.REJECTED_BY_VP,
                actor=request.user,
                action="PRINCIPAL_OVERRIDE_REJECT" if principal_override else "VP_REJECT",
                comment=reject_comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "PRINCIPAL_OVERRIDE_REJECT" if principal_override else "VP_REJECT",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
        messages.success(request, "Class returned for correction.")
        return redirect("results:approval-class-detail", compilation_id=self.compilation.id)


class ResultApprovalStudentDetailView(ResultsAccessMixin, TemplateView):
    template_name = "results/approval_student_detail.html"

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            messages.error(request, "Results approval access is restricted to VP, Principal, or IT Manager.")
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
        if not has_any_role(request.user, {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
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
        context["records"] = self.compilation.student_records.select_related("student").order_by(
            "student__username"
        )
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
        if action == "publish":
            if self.compilation.status != ClassCompilationStatus.SUBMITTED_TO_VP:
                messages.error(request, "Only submitted compilations can be published.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            form = ResultActionForm(request.POST)
            if not form.is_valid():
                messages.error(request, "Unable to read publish comment.")
                return redirect("results:vp-review-detail", compilation_id=self.compilation.id)
            publish_comment = form.cleaned_data["comment"]
            mark_compilation_published(self.compilation, request.user, comment=publish_comment)
            transition_class_sheet_set(
                sheets_qs=sheets_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_VP),
                to_status=ResultSheetStatus.PUBLISHED,
                actor=request.user,
                action="VP_PUBLISH",
                comment=publish_comment or "Published by VP.",
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "VP_PUBLISH",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            notify_results_published(
                compilation=self.compilation,
                actor=request.user,
                request=request,
            )
            messages.success(request, "Results published to student portal.")
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
        if not has_any_role(request.user, {ROLE_PRINCIPAL, ROLE_IT_MANAGER}):
            messages.error(request, "Principal oversight access required.")
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
        if not has_any_role(request.user, {ROLE_PRINCIPAL, ROLE_IT_MANAGER}):
            messages.error(request, "Principal override access required.")
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
            if self.compilation.status not in {
                ClassCompilationStatus.SUBMITTED_TO_VP,
                ClassCompilationStatus.REJECTED_BY_VP,
            }:
                messages.error(
                    request,
                    "Override publish requires submitted or rejected compilation state.",
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
                action="PRINCIPAL_OVERRIDE_PUBLISH",
                comment=publish_comment or "Principal override publish.",
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "PRINCIPAL_OVERRIDE_PUBLISH",
                    "compilation_id": str(self.compilation.id),
                    "class_id": str(self.compilation.academic_class_id),
                },
            )
            notify_results_published(
                compilation=self.compilation,
                actor=request.user,
                request=request,
            )
            messages.success(request, "Principal override publish completed.")
        elif action == "override_reject":
            if self.compilation.status not in {
                ClassCompilationStatus.SUBMITTED_TO_VP,
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
                action="PRINCIPAL_OVERRIDE_REJECT",
                comment=comment,
            )
            log_results_approval(
                actor=request.user,
                request=request,
                metadata={
                    "action": "PRINCIPAL_OVERRIDE_REJECT",
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
    allowed_roles = {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR}

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, self.allowed_roles):
            messages.error(request, "Report analytics access required.")
            return redirect("results:grade-entry-home")
        return super().dispatch(request, *args, **kwargs)

    def _window(self):
        return current_session_term()


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

        context["current_session"] = session
        context["current_term"] = term
        context["student_query"] = student_query
        context["level_options"] = level_options
        context["arm_options"] = filtered_arm_options
        context["selected_level"] = selected_level
        context["selected_arm"] = selected_arm
        context["selected_class"] = selected_class
        context["student_rows"] = list(student_qs.order_by("student_profile__student_number", "username")[:50])
        context["selected_student"] = selected_student
        context["report"] = report
        context["class_performance"] = class_performance
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
        for key in ("q", "class_id"):
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
            "student__student_profile__student_number",
            "student__username",
        )[:80]
        share_rows = [
            _build_result_share_row(request=self.request, record=record)
            for record in records
        ]
        context["current_session"] = session
        context["current_term"] = term
        context["query"] = query
        context["class_options"] = class_options
        context["selected_class"] = selected_class
        context["share_rows"] = share_rows
        context["students_ready_count"] = len(share_rows)
        context["email_ready_count"] = sum(1 for row in share_rows if row["email_targets"])
        context["whatsapp_ready_count"] = sum(1 for row in share_rows if row["whatsapp_url"])
        context["pin_ready_count"] = sum(1 for row in share_rows if row["pin_state"]["label"] == "Issued")
        context["can_manage_pins"] = has_any_role(self.request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL})
        context["whatsapp_provider_enabled"] = get_whatsapp_provider().provider_name != "disabled"
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "email_notice").strip().lower()
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
        context["pin_rows"] = pin_qs.order_by("student__student_profile__student_number", "student__username")[:80]
        context["student_rows"] = student_qs.order_by("student_profile__student_number", "username")[:80]
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
