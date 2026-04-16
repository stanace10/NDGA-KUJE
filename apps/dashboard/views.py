import base64
import binascii
import uuid
from collections import OrderedDict
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView


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
from apps.accounts.models import User
from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    Campus,
    FormTeacherAssignment,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)
from apps.audit.models import AuditCategory, AuditEvent, AuditStatus
from apps.audit.services import log_event, log_password_change, log_password_change_denied
from apps.cbt.models import CBTExamStatus, CBTSimulationWrapperStatus, Exam, QuestionBank, SimulationWrapper
from apps.elections.models import Election
from apps.notifications.models import Notification, NotificationCategory
from apps.accounts.forms import PolicyPasswordChangeForm
from apps.accounts.services import apply_self_service_password_change
from apps.accounts.security import privileged_login_target_email
from apps.accounts.permissions import has_any_role
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ResultSheet,
    ResultSheetStatus,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus
from apps.attendance.services import (
    get_form_teacher_assignments_for_current_session,
    get_current_student_attendance_snapshot,
    get_student_attendance_snapshot_for_window,
)
from apps.setup_wizard.services import get_setup_state, setup_is_ready
from apps.setup_wizard.feature_flags import FLAG_FIELD_MAP, get_runtime_feature_flags
from apps.setup_wizard.models import RuntimeFeatureFlags
from apps.tenancy.utils import (
    cloud_student_portal_limited_enabled,
    cloud_staff_operations_lan_only_enabled,
    current_portal_key,
    user_has_lan_only_operation_roles,
)
from apps.dashboard.forms import (
    PublicEventPostForm,
    PublicGalleryCategoryForm,
    PublicGalleryImageForm,
    PublicNewsPostForm,
    PublicSiteBrandingForm,
    PublicWebsiteSettingsForm,
    PrincipalSignatureForm,
    PrivilegedSecuritySettingsForm,
    StudentDisplaySettingsForm,
)
from apps.dashboard.intelligence import (
    build_school_intelligence,
    build_student_academic_analytics,
    build_teacher_performance_analytics,
)
from apps.results.analytics import active_result_pin_for_student
from apps.dashboard.models import (
    PrincipalSignature,
    PublicEventPost,
    PublicGalleryCategory,
    PublicGalleryImage,
    PublicNewsPost,
    PublicAdmissionPaymentStatus,
    PublicAdmissionWorkflowStatus,
    PublicSiteSubmission,
    PublicSubmissionType,
    PublicWebsiteSettings,
    SchoolProfile,
    StudentClubMembership,
)
from apps.dashboard.navigation import build_portal_navigation
from apps.dashboard.public_admission_utils import build_public_admission_snapshot
from apps.pdfs.services import build_term_report_payload


def _current_window():
    setup_state = get_setup_state()
    return setup_state.current_session, setup_state.current_term


def _admissions_dashboard_snapshot(*, limit=6):
    rows = list(
        PublicSiteSubmission.objects.filter(submission_type=PublicSubmissionType.ADMISSION)
        .order_by("-created_at")[:limit]
    )
    recent_rows = []
    for row in rows:
        snapshot = build_public_admission_snapshot(row)
        recent_rows.append(
            {
                "id": row.id,
                "applicant_name": row.applicant_name,
                "intended_class": row.intended_class,
                "application_code": row.application_fee_reference,
                "admissions_status": row.get_admissions_status_display(),
                "payment_status": row.get_payment_status_display(),
                "payment_mode": row.payment_mode_badge(),
                "created_at": row.created_at,
                "guardian_name": snapshot["parents"]["primary_guardian_name"] or row.guardian_name,
                "guardian_phone": snapshot["parents"]["primary_guardian_phone"] or row.guardian_phone,
            }
        )

    queryset = PublicSiteSubmission.objects.filter(submission_type=PublicSubmissionType.ADMISSION)
    return {
        "new": queryset.filter(admissions_status=PublicAdmissionWorkflowStatus.NEW).count(),
        "pending": queryset.filter(admissions_status=PublicAdmissionWorkflowStatus.PENDING).count(),
        "approved": queryset.filter(admissions_status=PublicAdmissionWorkflowStatus.APPROVED).count(),
        "paid": queryset.filter(payment_status=PublicAdmissionPaymentStatus.PAID).count(),
        "unpaid": queryset.filter(payment_status=PublicAdmissionPaymentStatus.UNPAID).count(),
        "recent_rows": recent_rows,
    }


def _active_class_levels_qs():
    return AcademicClass.objects.filter(is_active=True, base_class__isnull=True)


def _active_class_list_qs():
    return AcademicClass.objects.filter(is_active=True, base_class__isnull=False)


def _class_list_total():
    class_list_total = _active_class_list_qs().count()
    if class_list_total:
        return class_list_total
    return _active_class_levels_qs().count()


def _visible_notification_queryset(user):
    allow_payment = has_any_role(
        user,
        {ROLE_STUDENT, ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL},
    )
    queryset = Notification.objects.filter(recipient=user)
    if allow_payment:
        return queryset
    return queryset.exclude(category=NotificationCategory.PAYMENT)


def _calculate_age(date_of_birth):
    if not date_of_birth:
        return None
    today = timezone.localdate()
    years = today.year - date_of_birth.year
    if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
        years -= 1
    return max(years, 0)


def _has_display_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _time_based_student_greeting():
    hour = timezone.localtime().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def _compact_timestamp(value):
    if not value:
        return ""
    if hasattr(value, "hour"):
        return timezone.localtime(value).strftime("%d %b %Y")
    return value.strftime("%d %b %Y")


def _profile_row(label, value):
    if not _has_display_value(value):
        return None
    return {"label": label, "value": value}


def _build_student_result_overview(*, student, compilation):
    if compilation is None:
        return None

    payload = build_term_report_payload(student=student, compilation=compilation)
    subject_rows = list(payload.get("subject_rows", []))
    ranked_rows = sorted(subject_rows, key=lambda row: row.get("total") or 0, reverse=True)
    best_subject = ranked_rows[0] if ranked_rows else None
    worst_subject = ranked_rows[-1] if ranked_rows else None
    summary_rows = []
    for row in ranked_rows:
        score = row.get("total") or 0
        if score >= 70:
            status = "Strong"
        elif score >= 50:
            status = "Stable"
        else:
            status = "Needs attention"
        summary_rows.append(
            {
                "subject": row.get("subject"),
                "score": score,
                "grade": row.get("grade"),
                "status": status,
                "status_tone": (
                    "bg-emerald-50 text-emerald-700"
                    if score >= 70
                    else "bg-amber-50 text-amber-700"
                    if score >= 50
                    else "bg-rose-50 text-rose-700"
                ),
            }
        )

    return {
        "average": payload.get("average"),
        "class_position": payload.get("class_position"),
        "class_size": payload.get("class_size"),
        "subject_count": payload.get("subject_count"),
        "published_at": payload.get("published_at"),
        "term_name": payload.get("term_name"),
        "session_name": payload.get("session_name"),
        "best_subject": best_subject,
        "worst_subject": worst_subject,
        "subject_rows": summary_rows,
    }


def _cloud_staff_admin_lan_only(user):
    return cloud_staff_operations_lan_only_enabled() and user_has_lan_only_operation_roles(user)


def _cloud_student_portal_limited():
    return cloud_student_portal_limited_enabled()


def _portal_file_url(file_field):
    if not file_field:
        return ""
    name = (getattr(file_field, "name", "") or "").lstrip("/")
    if name:
        candidate = Path(settings.MEDIA_ROOT) / Path(name)
        if candidate.exists():
            version = int(candidate.stat().st_mtime)
            return f"/media/{name}?v={version}".replace("\\", "/")
    try:
        return file_field.url
    except Exception:
        return ""


def _term_sort_key(term: Term):
    order = {"FIRST": 1, "SECOND": 2, "THIRD": 3}
    return order.get(term.name, 99)


def _student_filter_window(request, *, include_sessions_queryset):
    setup_state = get_setup_state()
    sessions = list(include_sessions_queryset.order_by("-name"))
    selected_session = None
    requested_session_id = (request.GET.get("session_id") or "").strip()
    if requested_session_id.isdigit():
        selected_session = next(
            (session for session in sessions if session.id == int(requested_session_id)),
            None,
        )
    if selected_session is None:
        selected_session = next(
            (session for session in sessions if setup_state.current_session_id and session.id == setup_state.current_session_id),
            None,
        )
    if selected_session is None and sessions:
        selected_session = sessions[0]

    terms = []
    if selected_session:
        terms = list(Term.objects.filter(session=selected_session))
        terms.sort(key=_term_sort_key)
    selected_term = None
    requested_term_id = (request.GET.get("term_id") or "").strip()
    if requested_term_id.isdigit():
        selected_term = next((term for term in terms if term.id == int(requested_term_id)), None)
    if selected_term is None:
        if (
            selected_session
            and setup_state.current_session_id == selected_session.id
            and setup_state.current_term_id
        ):
            selected_term = next((term for term in terms if term.id == setup_state.current_term_id), None)
    if selected_term is None and terms:
        selected_term = terms[0]

    return {
        "available_sessions": sessions,
        "available_terms": terms,
        "selected_session": selected_session,
        "selected_term": selected_term,
    }


def _attendance_tone(snapshot):
    if not snapshot:
        return (
            "No Attendance Record",
            "border-slate-200 bg-slate-50 text-slate-700",
        )
    attendance_percentage = float(snapshot.get("percentage", 0) or 0)
    if attendance_percentage >= 75:
        return "Strong Attendance", "border-emerald-200 bg-emerald-50 text-emerald-800"
    if attendance_percentage >= 50:
        return "Average Attendance", "border-amber-200 bg-amber-50 text-amber-800"
    return "Low Attendance", "border-rose-200 bg-rose-50 text-rose-800"


def _portal_action_description(label: str):
    text = (label or "").strip().lower()
    if "attendance" in text:
        return "Open attendance workflow and class records."
    if "cumulative" in text or "compile" in text:
        return "Open cumulative grading and class compilation workflow."
    if "score" in text or "result" in text:
        return "Open score and result workflow page."
    if "question" in text or "cbt" in text or "exam" in text:
        return "Open CBT authoring and exam workflow page."
    if "dean" in text:
        return "Open dean review and approval queue."
    if "compile" in text or "comment" in text:
        return "Open class compilation and comment workflow."
    if "profile" in text or "student" in text or "staff" in text:
        return "Open profile and user record management page."
    if "academics" in text or "subject" in text:
        return "Open academics structure and class-subject page."
    if "finance" in text or "charge" in text or "payment" in text or "salary" in text or "expense" in text:
        return "Open finance operations page."
    if "calendar" in text or "session" in text or "term" in text:
        return "Open session, term, and calendar controls."
    if "notification" in text:
        return "Open notification center and message logs."
    if "audit" in text:
        return "Open audit logs and compliance events."
    if "sync" in text:
        return "Manual push and recovery actions are handled by IT when needed."
    if "election" in text or "vote" in text:
        return "Open election workflow and live analytics."
    if "challenge" in text or "teaser" in text:
        return "Open weekly brain teaser setup, submissions, and leaderboard."
    if "backup" in text:
        return "Open backup center and export tools."
    if "setting" in text:
        return "Open settings and governance controls."
    return "Open this workflow page."


def _portal_focus_notes(*, portal_key: str, role_codes: set[str]):
    if portal_key == "staff":
        return [
            "Subject-teacher portal is now limited to score entry, CBT authoring, lesson planning, and classroom work.",
            "Dean and form-teacher duties now live in their own dedicated portals to reduce workflow mistakes.",
        ]
    if portal_key == "dean":
        return [
            "Dean portal is limited to result vetting, question vetting, and approval decisions only.",
            "Use the normal staff login separately for subject teaching, CBT entry, and score entry.",
        ]
    if portal_key == "form":
        return [
            "Form-teacher portal is limited to class students, attendance, and result comments after dean approval.",
            "Use the normal staff or VP login separately for subject teaching and broader school duties.",
        ]
    if portal_key == "it":
        return [
            "Use this portal for provisioning, setup, toggles, and governance controls.",
            "CBT and Election visibility should be managed only through IT controls.",
        ]
    if portal_key == "bursar":
        return [
            "Start with charge setup, then continue with payments and expense tracking.",
            "Receipts and finance records must remain traceable and verifiable.",
        ]
    if portal_key == "vp":
        return [
            "Dashboard focuses on oversight, approvals, attendance, and performance for assigned classes.",
            "If VP is also a form teacher, the assigned base class covers all active class arms under that level.",
        ]
    if portal_key == "principal":
        return [
            "Principal uses the same approval and media workflow with added finance view.",
            "Election live analytics and finance visibility stay in this portal.",
        ]
    if portal_key == "cbt":
        return [
            "CBT session is isolated and requires focused exam operations.",
            "Use only relevant exam tools for your role and current workflow.",
        ]
    if portal_key == "election":
        return []
    return ["Open each workflow from the menu to continue operations."]


def _flatten_portal_action_items(*, portal_key: str, nav_items: list[dict]):
    skip_labels = {"dashboard", "logout"}
    if portal_key in {"cbt", "election"}:
        skip_labels.add("home")

    action_rows = []
    seen = set()

    for item in nav_items:
        if not isinstance(item, dict):
            continue

        label = (item.get("label") or "").strip()
        url = (item.get("url") or "").strip()
        icon = item.get("icon") or "home"
        if label and url and label.lower() not in skip_labels:
            key = (label.lower(), url)
            if key not in seen:
                seen.add(key)
                action_rows.append(
                    {
                        "label": label,
                        "url": url,
                        "icon": icon,
                        "description": _portal_action_description(label),
                    }
                )

        for child in item.get("children") or []:
            child_label = (child.get("label") or "").strip()
            child_url = (child.get("url") or "").strip()
            child_icon = child.get("icon") or icon
            if child_label and child_url and child_label.lower() not in skip_labels:
                key = (child_label.lower(), child_url)
                if key not in seen:
                    seen.add(key)
                    action_rows.append(
                        {
                            "label": child_label,
                            "url": child_url,
                            "icon": child_icon,
                            "description": _portal_action_description(child_label),
                        }
                    )

    return action_rows


def _portal_action_icon_hint(*, label: str, description: str = "", fallback: str = "home"):
    text = f"{label} {description}".lower()
    if any(token in text for token in ["profile", "biodata", "account", "id card", "digital id"]):
        return "user"
    if "attendance" in text:
        return "attendance"
    if any(token in text for token in ["result", "report", "approval", "publish", "score", "grade"]):
        return "results"
    if any(token in text for token in ["transcript", "document", "vault", "certificate"]):
        return "transcript"
    if any(token in text for token in ["subject", "class", "learning", "challenge", "lesson"]):
        return "subjects"
    if any(token in text for token in ["fee", "finance", "payment", "salary", "expense", "receipt"]):
        return "finance"
    if any(token in text for token in ["notification", "message", "broadcast", "mail"]):
        return "notification"
    if any(token in text for token in ["setting", "toggle", "sync", "audit", "backup", "ops", "restore"]):
        return "settings"
    return fallback


def _build_portal_priority_actions(
    *,
    portal_key: str,
    portal_action_items: list[dict],
    role_panels: list[dict] | None = None,
    student_quick_links: list[dict] | None = None,
    student_next_action: dict | None = None,
):
    rows = []
    seen = set()

    def add_row(*, label, url, description="", icon="home", badge="", metric=None, kicker=""):
        label = (label or "").strip()
        url = (url or "").strip()
        if not label or not url:
            return
        key = (label.lower(), url)
        if key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "label": label,
                "url": url,
                "description": (description or "Open this workflow page.").strip(),
                "icon": icon or "home",
                "badge": (badge or "").strip(),
                "metric": metric,
                "kicker": (kicker or "").strip(),
            }
        )

    if portal_key == "student":
        if student_next_action and student_next_action.get("action_url"):
            add_row(
                label=student_next_action.get("action_label") or student_next_action.get("title") or "Continue",
                url=student_next_action.get("action_url"),
                description=student_next_action.get("message") or "Continue the next student workflow.",
                icon=_portal_action_icon_hint(
                    label=student_next_action.get("action_label") or student_next_action.get("title") or "Continue",
                    description=student_next_action.get("message") or "",
                    fallback="results",
                ),
                badge="Now",
                kicker=student_next_action.get("title") or "Student Workflow",
            )
        for row in student_quick_links or []:
            add_row(
                label=row.get("label"),
                url=row.get("url"),
                description=row.get("description") or "Open this student workflow.",
                icon=_portal_action_icon_hint(
                    label=row.get("label") or "",
                    description=row.get("description") or "",
                ),
                badge=row.get("badge") or "Open",
                kicker="Student Workflow",
            )
        return rows[:6]

    for panel in role_panels or []:
        panel_title = (panel.get("title") or "").strip()
        panel_subtitle = (panel.get("subtitle") or "").strip()
        for item in panel.get("items") or []:
            add_row(
                label=item.get("label"),
                url=item.get("url"),
                description=item.get("description") or panel_subtitle or "Open this workflow page.",
                icon=_portal_action_icon_hint(
                    label=item.get("label") or "",
                    description=item.get("description") or panel_subtitle,
                ),
                badge=panel_title or "Role",
                metric=item.get("metric"),
                kicker=panel_subtitle or panel_title,
            )

    for action in portal_action_items or []:
        add_row(
            label=action.get("label"),
            url=action.get("url"),
            description=action.get("description") or "Open this workflow page.",
            icon=action.get("icon") or _portal_action_icon_hint(
                label=action.get("label") or "",
                description=action.get("description") or "",
            ),
            badge="Menu",
            kicker="Dedicated Workflow",
        )

    return rows[:6]


def _student_dashboard_payload(request, user):
    from apps.finance.models import Payment
    from apps.finance.services import student_finance_overview

    current_session, current_term = _current_window()
    student_profile = getattr(user, "student_profile", None)
    attendance_snapshot = get_current_student_attendance_snapshot(user)

    enrollment_qs = (
        StudentClassEnrollment.objects.select_related("academic_class", "session")
        .filter(student=user, is_active=True)
        .order_by("-updated_at", "-id")
    )
    current_enrollment = None
    if current_session:
        current_enrollment = enrollment_qs.filter(session=current_session).first()
    if current_enrollment is None:
        current_enrollment = enrollment_qs.first()

    subject_session = current_session
    if subject_session is None and current_enrollment is not None:
        subject_session = current_enrollment.session
    elif (
        current_enrollment is not None
        and current_session is not None
        and current_enrollment.session_id != current_session.id
    ):
        subject_session = current_enrollment.session

    offered_subjects = []
    if subject_session:
        offered_subjects = list(
            StudentSubjectEnrollment.objects.filter(
                student=user,
                session=subject_session,
                is_active=True,
            )
            .select_related("subject")
            .order_by("subject__name")
        )

    published_qs = (
        ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=user,
        )
        .select_related("academic_class", "session", "term")
        .distinct()
    )
    current_compilation = None
    current_compilation_any_state = None
    if current_session and current_term:
        current_compilation_any_state = (
            ClassResultCompilation.objects.filter(
                student_records__student=user,
                session=current_session,
                term=current_term,
            )
            .select_related("academic_class", "session", "term")
            .distinct()
            .first()
        )
        current_compilation = published_qs.filter(
            session=current_session,
            term=current_term,
        ).first()

    latest_published = (
        published_qs.order_by("-published_at", "-updated_at").first()
        if published_qs.exists()
        else None
    )

    if current_compilation:
        result_status = {
            "state": "PUBLISHED",
            "label": "Published",
            "message": (
                f"{current_compilation.term.get_name_display()} result is available "
                f"for {current_compilation.session.name}."
            ),
            "tone_class": "border-emerald-200 bg-emerald-50 text-emerald-800",
            "term_report_view_url": reverse(
                "pdfs:student-term-report-view",
                kwargs={"compilation_id": current_compilation.id},
            ),
            "term_report_url": reverse(
                "pdfs:student-term-report-download",
                kwargs={"compilation_id": current_compilation.id},
            ),
        }
    elif current_compilation_any_state:
        result_status = {
            "state": current_compilation_any_state.status,
            "label": current_compilation_any_state.get_status_display(),
            "message": (
                f"{current_compilation_any_state.term.get_name_display()} workflow is "
                f"currently at {current_compilation_any_state.get_status_display()}."
            ),
            "tone_class": "border-amber-200 bg-amber-50 text-amber-800",
            "term_report_view_url": "",
            "term_report_url": "",
        }
    else:
        result_status = {
            "state": "NOT_AVAILABLE",
            "label": "Not Available",
            "message": "No published result found for the current term yet.",
            "tone_class": "border-slate-200 bg-slate-50 text-slate-700",
            "term_report_view_url": "",
            "term_report_url": "",
        }

    unread_notifications = _visible_notification_queryset(user).filter(
        read_at__isnull=True,
    ).count()
    student_age = _calculate_age(getattr(student_profile, "date_of_birth", None))
    current_class_code = (
        (current_enrollment.academic_class.display_name or current_enrollment.academic_class.code) if current_enrollment else "Not Assigned"
    )

    attendance_label, attendance_tone_class = _attendance_tone(attendance_snapshot)

    finance_summary = {
        "total_charged": 0,
        "total_paid_applied": 0,
        "total_outstanding": 0,
        "unallocated_credit": 0,
    }
    finance_session = current_session or getattr(current_enrollment, "session", None)
    finance_term = current_term if current_session and finance_session and current_session.id == finance_session.id else None
    if finance_session:
        finance_summary = student_finance_overview(
            student=user,
            session=finance_session,
            term=finance_term,
        )

    reports_center_url = reverse("pdfs:student-reports")
    transcript_url = reverse("dashboard:student-transcript")
    notifications_center_url = reverse("notifications:center")
    finance_url = reverse("finance:student-overview")
    attendance_url = reverse("dashboard:student-attendance")
    term_report_view_url = result_status.get("term_report_view_url", "")
    term_report_url = result_status.get("term_report_url", "")

    if result_status["state"] == "PUBLISHED" and (term_report_view_url or term_report_url):
        student_next_action = {
            "title": "View your current term result",
            "message": "Your result is already published. Open it now and download when needed.",
            "action_label": "View Current Result",
            "action_url": term_report_view_url or term_report_url,
            "tone_class": "border-emerald-200 bg-emerald-50 text-emerald-900",
        }
    elif result_status["state"] == "NOT_AVAILABLE":
        student_next_action = {
            "title": "Monitor updates from your class",
            "message": "No published result yet. Check notifications and reports center regularly.",
            "action_label": "Open Notifications",
            "action_url": notifications_center_url,
            "tone_class": "border-slate-200 bg-slate-50 text-slate-800",
        }
    else:
        student_next_action = {
            "title": "Result workflow is in progress",
            "message": result_status["message"],
            "action_label": "Open Reports Center",
            "action_url": reports_center_url,
            "tone_class": "border-amber-200 bg-amber-50 text-amber-900",
        }

    student_quick_links = [
        {
            "label": "Profile",
            "description": "View your biodata and guardian details.",
            "url": reverse("dashboard:student-profile"),
            "badge": "Bio",
        },
        {
            "label": "Attendance Metrics",
            "description": "Open attendance metrics and progress chart.",
            "url": reverse("dashboard:student-attendance"),
            "badge": "Track",
        },
        {
            "label": "Term Results",
            "description": "View all published term report PDFs.",
            "url": reports_center_url,
            "badge": "Reports",
        },
        {
            "label": "Transcript",
            "description": "Open transcript page and session downloads.",
            "url": reverse("dashboard:student-transcript"),
            "badge": "Official",
        },
        {
            "label": "Subjects Offered",
            "description": "View subjects assigned for current session.",
            "url": reverse("dashboard:student-subjects"),
            "badge": "Subjects",
        },
        {
            "label": "Classroom LMS",
            "description": "Open your subject classrooms, complete modules, and submit assignments.",
            "url": reverse("dashboard:student-lms"),
            "badge": "LMS",
        },
        {
            "label": "Weekly Challenge",
            "description": "Attempt the current brain teaser for your class and track reward points.",
            "url": reverse("dashboard:student-weekly-challenge"),
            "badge": "Challenge",
        },
        {
            "label": "Digital ID",
            "description": "Open your QR ID for attendance, gate, and library checks.",
            "url": reverse("dashboard:student-id-card"),
            "badge": "ID",
        },
        {
            "label": "Finance",
            "description": "Check fee categories, paid and outstanding balances.",
            "url": finance_url,
            "badge": "Fees",
        },
        {
            "label": "Notifications",
            "description": "Read updates from school and staff.",
            "url": notifications_center_url,
            "badge": f"{unread_notifications} unread" if unread_notifications else "Inbox",
        },
    ]
    if not _cloud_student_portal_limited():
        student_quick_links[8:8] = [
            {
                "label": "Learning Hub",
                "description": "Open assignments, study materials, past questions, and AI tutor help.",
                "url": reverse("dashboard:student-learning-hub"),
                "badge": "Learn",
            },
            {
                "label": "Settings",
                "description": "Manage dashboard display name and password.",
                "url": reverse("dashboard:student-settings"),
                "badge": "Account",
            },
        ]

    student_analytics = build_student_academic_analytics(
        student=user,
        current_session=current_session,
        current_term=current_term,
    )

    latest_payment = (
        Payment.objects.filter(student=user, is_void=False)
        .select_related("receipt", "session", "term")
        .order_by("-payment_date", "-created_at")
        .first()
    )
    latest_notification = _visible_notification_queryset(user).order_by("-created_at").first()

    recent_activity = []
    if latest_payment:
        recent_activity.append(
            {
                "label": "Last payment",
                "title": f"{latest_payment.amount} received",
                "meta": _compact_timestamp(latest_payment.payment_date or latest_payment.created_at),
                "description": (
                    latest_payment.receipt.receipt_number
                    if getattr(latest_payment, "receipt", None)
                    else "Payment recorded successfully."
                ),
                "url": finance_url,
            }
        )
    if latest_published:
        recent_activity.append(
            {
                "label": "Last result update",
                "title": f"{latest_published.term.get_name_display()} result published",
                "meta": _compact_timestamp(latest_published.published_at or latest_published.updated_at),
                "description": latest_published.session.name,
                "url": term_report_view_url or reports_center_url,
            }
        )
    if latest_notification:
        recent_activity.append(
            {
                "label": "Announcement",
                "title": latest_notification.title,
                "meta": _compact_timestamp(latest_notification.created_at),
                "description": (latest_notification.message or "")[:100],
                "url": latest_notification.action_url or notifications_center_url,
            }
        )

    student_dashboard_actions = [
        {
            "label": "View Results",
            "description": "Open current term reports and performance analysis.",
            "url": term_report_view_url or reports_center_url,
        },
        {
            "label": "Pay Fees",
            "description": "Review balance and continue to secure payment.",
            "url": finance_url,
        },
        {
            "label": "Open Learning Hub",
            "description": "Open published resources, assignments, and classroom links.",
            "url": reverse("dashboard:student-learning-hub"),
        },
    ]

    return {
        "current_session": current_session,
        "current_term": current_term,
        "student_portal_greeting": _time_based_student_greeting(),
        "student_portal_subtext": "Here's what you need today.",
        "student_age": student_age,
        "current_class_code": current_class_code,
        "attendance_snapshot": attendance_snapshot,
        "attendance_label": attendance_label,
        "attendance_tone_class": attendance_tone_class,
        "offered_subjects": offered_subjects,
        "offered_subject_count": len(offered_subjects),
        "student_profile": student_profile,
        "current_enrollment": current_enrollment,
        "result_status": result_status,
        "published_compilations": list(published_qs.order_by("-published_at", "-updated_at")[:5]),
        "latest_published_compilation": latest_published,
        "term_report_view_url": term_report_view_url,
        "term_report_url": term_report_url,
        "transcript_url": transcript_url,
        "reports_center_url": reports_center_url,
        "notifications_center_url": notifications_center_url,
        "unread_notifications": unread_notifications,
        "student_next_action": student_next_action,
        "student_quick_links": student_quick_links,
        "student_dashboard_actions": student_dashboard_actions,
        "student_recent_activity": recent_activity,
        "student_finance_summary": finance_summary,
        "student_analytics": student_analytics,
    }


def _staff_dashboard_payload(user):
    current_session, current_term = _current_window()
    role_codes = user.get_all_role_codes()
    cloud_staff_admin_lan_only = _cloud_staff_admin_lan_only(user)
    visible_class_total = _class_list_total()

    assignment_qs = TeacherSubjectAssignment.objects.filter(teacher=user, is_active=True)
    if current_session:
        assignment_qs = assignment_qs.filter(session=current_session)
    if current_term:
        assignment_qs = assignment_qs.filter(term=current_term)
    assignment_pairs = list(assignment_qs.values_list("academic_class_id", "subject_id"))
    assignment_count = len(assignment_pairs)

    own_sheet_qs = ResultSheet.objects.none()
    if current_session and current_term and assignment_pairs:
        from django.db.models import Q

        pair_filter = Q()
        for class_id, subject_id in assignment_pairs:
            pair_filter |= Q(academic_class_id=class_id, subject_id=subject_id)
        own_sheet_qs = ResultSheet.objects.filter(
            pair_filter,
            session=current_session,
            term=current_term,
        )

    own_submit_ready_count = own_sheet_qs.filter(
        status__in=[ResultSheetStatus.DRAFT, ResultSheetStatus.REJECTED_BY_DEAN]
    ).count()
    own_submitted_count = own_sheet_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_DEAN).count()

    exam_qs = Exam.objects.filter(created_by=user)
    if current_session:
        exam_qs = exam_qs.filter(session=current_session)
    if current_term:
        exam_qs = exam_qs.filter(term=current_term)
    cbt_draft_count = exam_qs.filter(
        status__in=[CBTExamStatus.DRAFT, CBTExamStatus.PENDING_DEAN]
    ).count()

    form_assignment_qs = FormTeacherAssignment.objects.filter(teacher=user, is_active=True)
    if current_session:
        form_assignment_qs = form_assignment_qs.filter(session=current_session)
    form_class_count = form_assignment_qs.count()
    form_class_ids = list(form_assignment_qs.values_list("academic_class_id", flat=True))
    form_compile_ready_count = 0
    if current_session and current_term and form_class_ids:
        form_compile_ready_count = ClassResultCompilation.objects.filter(
            academic_class_id__in=form_class_ids,
            session=current_session,
            term=current_term,
            status__in=[ClassCompilationStatus.DRAFT, ClassCompilationStatus.REJECTED_BY_VP],
        ).count()

    dean_result_pending = 0
    dean_cbt_pending = 0
    dean_sim_pending = 0
    if current_session and current_term:
        dean_result_pending = ResultSheet.objects.filter(
            session=current_session,
            term=current_term,
            status=ResultSheetStatus.SUBMITTED_TO_DEAN,
        ).count()
        dean_cbt_pending = Exam.objects.filter(
            session=current_session,
            term=current_term,
            status=CBTExamStatus.PENDING_DEAN,
        ).count()
    dean_sim_pending = SimulationWrapper.objects.filter(
        status=CBTSimulationWrapperStatus.PENDING_DEAN,
        is_active=True,
    ).count()

    vp_pending_publish = 0
    vp_published_count = 0
    if current_session and current_term:
        vp_pending_publish = ClassResultCompilation.objects.filter(
            session=current_session,
            term=current_term,
            status=ClassCompilationStatus.SUBMITTED_TO_VP,
        ).count()
        vp_published_count = ClassResultCompilation.objects.filter(
            session=current_session,
            term=current_term,
            status=ClassCompilationStatus.PUBLISHED,
        ).count()

    election_active_count = Election.objects.filter(is_active=True, status="OPEN").count()
    unread_notifications = _visible_notification_queryset(user).filter(read_at__isnull=True).count()
    audit_last_day_count = AuditEvent.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=24)
    ).count()

    role_panels = []
    if not cloud_staff_admin_lan_only and role_codes & {ROLE_SUBJECT_TEACHER, ROLE_DEAN, ROLE_FORM_TEACHER}:
        role_panels.append(
            {
                "title": "Subject Teacher",
                "subtitle": "Result entry and CBT entry for assigned class subjects.",
                "items": [
                    {
                        "label": "CBT Entry",
                        "url": "/cbt/authoring/",
                        "description": "Create, review, and manage CBT drafts for assigned classes.",
                        "metric": cbt_draft_count or QuestionBank.objects.filter(owner=user).count(),
                    },
                    {
                        "label": "Result Entry",
                        "url": "/results/grade-entry/",
                        "description": "Enter CA and exam scores for assigned classes/subjects.",
                        "metric": assignment_count,
                    },
                    {
                        "label": "Classroom LMS",
                        "url": "/portal/staff/lms/",
                        "description": "Create classrooms, publish lessons, set assignments, and grade submissions.",
                        "metric": assignment_count,
                    },
                    {
                        "label": "Lesson Planner",
                        "url": "/portal/staff/lesson-planner/",
                        "description": "Draft lesson flow, class activity, and assignments before publishing.",
                        "metric": assignment_count,
                    },
                ],
            }
        )

    if not cloud_staff_admin_lan_only and ROLE_FORM_TEACHER in role_codes:
        role_panels.append(
            {
                "title": "Form Teacher",
                "subtitle": "Attendance ownership, class performance, and your assigned teaching workflow.",
                "items": [
                    {
                        "label": "Attendance",
                        "url": "/attendance/form/mark/",
                        "description": "Mark daily/weekly class attendance and monitor percentages.",
                        "metric": form_class_count,
                    },
                    {
                        "label": "Own Subjects",
                        "url": "/results/grade-entry/",
                        "description": "Enter scores only for subjects directly assigned to you.",
                        "metric": own_submit_ready_count + own_submitted_count,
                    },
                    {
                        "label": "Performance Report",
                        "url": "/results/report/performance/",
                        "description": "Review class performance and filter down to subjects you teach.",
                        "metric": form_class_count,
                    },
                ],
            }
        )

    if not cloud_staff_admin_lan_only and ROLE_DEAN in role_codes:
        role_panels.append(
            {
                "title": "Academic Approval",
                "subtitle": "Separate review pages for results and exams.",
                "items": [
                    {
                        "label": "Result Review",
                        "url": "/results/dean/review/results/",
                        "description": "Review submitted class-subject result sheets.",
                        "metric": dean_result_pending,
                    },
                    {
                        "label": "Exam Review",
                        "url": "/results/dean/review/exams/",
                        "description": "Review CBT exams and simulation tools.",
                        "metric": dean_cbt_pending + dean_sim_pending,
                    },
                ],
            }
        )

    if not cloud_staff_admin_lan_only and ROLE_VP in role_codes:
        role_panels.append(
            {
                "title": "Vice Principal",
                "subtitle": "Final approvals, publication control, and outbound messaging.",
                "items": [
                    {
                        "label": "Approvals & Publish",
                        "url": "/results/vp/review/",
                        "description": "Approve class compilations and publish to students.",
                        "metric": vp_pending_publish,
                    },
                    {
                        "label": "Published This Term",
                        "url": "/results/vp/review/",
                        "description": "Compilations already published for active term.",
                        "metric": vp_published_count,
                    },
                    {
                        "label": "Notifications",
                        "url": "/notifications/center/",
                        "description": "Broadcast and monitor communication delivery logs.",
                        "metric": unread_notifications,
                    },
                ],
            }
        )

    if not cloud_staff_admin_lan_only and ROLE_PRINCIPAL in role_codes:
        role_panels.append(
            {
                "title": "Principal",
                "subtitle": "Institution oversight dashboards and audit-level visibility.",
                "items": [
                    {
                        "label": "Oversight Dashboard",
                        "url": "/results/principal/oversight/",
                        "description": "Track approvals, publications, and top metrics.",
                        "metric": vp_pending_publish + vp_published_count,
                    },
                    {
                        "label": "Audit Summary",
                        "url": "/audit/events/",
                        "description": "Inspect operational and security events across modules.",
                        "metric": audit_last_day_count,
                    },
                    {
                        "label": "Election Analytics",
                        "url": "/elections/",
                        "description": "View live election turnout and candidate performance.",
                        "metric": election_active_count,
                    },
                ],
            }
        )

    teacher_analytics = build_teacher_performance_analytics(
        teacher=user,
        current_session=current_session,
        current_term=current_term,
    )
    leadership_snapshot = None
    if ROLE_DEAN in role_codes:
        leadership_snapshot = {
            "classes_total": visible_class_total,
            "class_levels_total": _active_class_levels_qs().count(),
            "students_total": User.objects.filter(primary_role__code=ROLE_STUDENT, is_active=True).count(),
            "staff_total": User.objects.filter(staff_profile__isnull=False, is_active=True).exclude(
                username=settings.ANONYMOUS_USER_NAME
            ).count(),
            "results_pending": dean_result_pending,
        }

    return {
        "current_session": current_session,
        "current_term": current_term,
        "role_panels": role_panels,
        "teacher_analytics": teacher_analytics,
        "leadership_snapshot": leadership_snapshot,
    }


def _staff_results_readonly_payload(user):
    current_session, current_term = _current_window()
    assignment_qs = TeacherSubjectAssignment.objects.filter(teacher=user, is_active=True).select_related(
        "academic_class",
        "subject",
        "session",
        "term",
    )
    if current_session:
        assignment_qs = assignment_qs.filter(session=current_session)
    if current_term:
        assignment_qs = assignment_qs.filter(term=current_term)

    rows = []
    for assignment in assignment_qs.order_by("academic_class__code", "subject__name"):
        sheet = ResultSheet.objects.filter(
            academic_class=assignment.academic_class,
            subject=assignment.subject,
            session=assignment.session,
            term=assignment.term,
        ).first()
        rows.append(
            {
                "class_code": assignment.academic_class.code,
                "subject_name": assignment.subject.name,
                "status_label": sheet.get_status_display() if sheet else "Not Started",
                "status_code": sheet.status if sheet else "",
                "updated_at": getattr(sheet, "updated_at", None),
            }
        )

    published_count = ResultSheet.objects.filter(
        created_by=user,
        status=ResultSheetStatus.PUBLISHED,
    ).count()
    return {
        "current_session": current_session,
        "current_term": current_term,
        "result_rows": rows,
        "result_counts": {
            "assigned": len(rows),
            "draft": len([row for row in rows if row["status_code"] == ResultSheetStatus.DRAFT]),
            "submitted": len([row for row in rows if row["status_code"] == ResultSheetStatus.SUBMITTED_TO_DEAN]),
            "published": published_count,
        },
    }


def _dean_portal_payload(user):
    current_session, current_term = _current_window()
    pending_results = 0
    pending_questions = 0
    if current_session and current_term:
        pending_results = ResultSheet.objects.filter(
            session=current_session,
            term=current_term,
            status=ResultSheetStatus.SUBMITTED_TO_DEAN,
        ).count()
        pending_questions = Exam.objects.filter(
            session=current_session,
            term=current_term,
            status=CBTExamStatus.PENDING_DEAN,
        ).count()
    pending_simulations = SimulationWrapper.objects.filter(
        status=CBTSimulationWrapperStatus.PENDING_DEAN,
        is_active=True,
    ).count()
    return {
        "portal_stat_cards": [
            {
                "label": "Pending Results",
                "value": pending_results,
                "meta": "Submitted score sheets waiting for dean review.",
            },
            {
                "label": "Pending Questions",
                "value": pending_questions,
                "meta": "CBT exams waiting for vetting.",
            },
            {
                "label": "Pending Simulations",
                "value": pending_simulations,
                "meta": "Simulation bundles still awaiting approval.",
            },
        ],
    }


def _form_teacher_portal_payload(user):
    current_session, current_term = _current_window()
    assignment_qs = FormTeacherAssignment.objects.filter(teacher=user, is_active=True).select_related(
        "academic_class",
        "session",
    )
    if current_session:
        assignment_qs = assignment_qs.filter(session=current_session)
    assignments = list(assignment_qs.order_by("academic_class__code"))
    class_ids = [row.academic_class_id for row in assignments]
    student_count = 0
    attendance_days = 0
    ready_comment_sheets = 0
    if current_session and class_ids:
        student_count = StudentClassEnrollment.objects.filter(
            academic_class_id__in=class_ids,
            session=current_session,
            is_active=True,
        ).values("student_id").distinct().count()
        attendance_days = AttendanceRecord.objects.filter(
            academic_class_id__in=class_ids,
            calendar__session=current_session,
        ).values("date").distinct().count()
    if current_session and current_term and class_ids:
        ready_comment_sheets = ResultSheet.objects.filter(
            academic_class_id__in=class_ids,
            session=current_session,
            term=current_term,
            status=ResultSheetStatus.APPROVED_BY_DEAN,
        ).count()
    class_label = ""
    if len(assignments) == 1:
        assigned_class = assignments[0].academic_class
        class_label = assigned_class.display_name or assigned_class.code
    return {
        "assigned_form_classes": assignments,
        "form_attendance_days": attendance_days,
        "form_portal_description_override": (
            f"Manage students, attendance, and result comments for {class_label}."
            if class_label
            else ""
        ),
        "portal_stat_cards": [
            {
                "label": "Assigned Class",
                "value": class_label or len(assignments),
                "meta": "The class currently under your form-teacher care.",
            },
            {
                "label": "Students",
                "value": student_count,
                "meta": "Students currently enrolled in your assigned class.",
            },
            {
                "label": "Attendance Days",
                "value": attendance_days,
                "meta": "School days with attendance already marked.",
            },
            {
                "label": "Dean-Approved Subjects",
                "value": ready_comment_sheets,
                "meta": "Subject sheets now ready for form comments.",
            },
        ],
    }


def _staff_attendance_readonly_payload(user):
    current_session, current_term = _current_window()
    assignment_qs = get_form_teacher_assignments_for_current_session(user)
    rows = []
    for assignment in assignment_qs:
        instructional_class = assignment.academic_class.instructional_class
        records = AttendanceRecord.objects.filter(
            academic_class=instructional_class,
            calendar__session=assignment.session,
        )
        if current_term:
            records = records.filter(calendar__term=current_term)
        rows.append(
            {
                "class_code": assignment.academic_class.display_name or assignment.academic_class.code,
                "present_count": records.filter(status=AttendanceStatus.PRESENT).count(),
                "absent_count": records.filter(status=AttendanceStatus.ABSENT).count(),
                "marked_days": records.values("date").distinct().count(),
                "latest_marked": records.order_by("-date").values_list("date", flat=True).first(),
            }
        )
    return {
        "current_session": current_session,
        "current_term": current_term,
        "attendance_rows": rows,
        "attendance_counts": {
            "classes": len(rows),
            "marked_classes": len([row for row in rows if row["marked_days"] > 0]),
            "total_present": sum(row["present_count"] for row in rows),
            "total_absent": sum(row["absent_count"] for row in rows),
        },
    }


def _leadership_school_payload(request):
    current_session, current_term = _current_window()
    search_query = (request.GET.get("q") or "").strip()
    class_filter = (request.GET.get("class_code") or "").strip()

    enrollment_base_qs = StudentClassEnrollment.objects.select_related("academic_class").filter(is_active=True)
    if current_session:
        enrollment_base_qs = enrollment_base_qs.filter(session=current_session)
    class_options = list(
        enrollment_base_qs.values_list("academic_class__code", flat=True).distinct().order_by("academic_class__code")
    )

    student_enrollment_qs = enrollment_base_qs
    if class_filter:
        student_enrollment_qs = student_enrollment_qs.filter(academic_class__code=class_filter)
    class_map = {}
    for row in student_enrollment_qs.order_by("-updated_at", "-id"):
        class_map.setdefault(row.student_id, row.academic_class.display_name or row.academic_class.code)
    class_filtered_student_ids = set(class_map.keys()) if class_filter else None

    club_count_map = {}
    club_qs = StudentClubMembership.objects.filter(is_active=True)
    if current_session:
        club_qs = club_qs.filter(session=current_session)
    for row in club_qs.values("student_id").annotate(total=Count("id")):
        club_count_map[row["student_id"]] = row["total"]

    result_count_map = {}
    published_result_qs = ClassResultCompilation.objects.filter(
        status=ClassCompilationStatus.PUBLISHED,
        student_records__student__isnull=False,
    )
    if current_session:
        published_result_qs = published_result_qs.filter(session=current_session)
    if current_term:
        published_result_qs = published_result_qs.filter(term=current_term)
    for row in published_result_qs.values("student_records__student_id").annotate(total=Count("id")):
        result_count_map[row["student_records__student_id"]] = row["total"]

    student_qs = User.objects.select_related("student_profile").filter(
        primary_role__code=ROLE_STUDENT,
        is_active=True,
    )
    if search_query:
        student_qs = student_qs.filter(
            Q(username__icontains=search_query)
            | Q(display_name__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(student_profile__student_number__icontains=search_query)
            | Q(student_profile__guardian_name__icontains=search_query)
            | Q(student_profile__guardian_email__icontains=search_query)
        )
    if class_filtered_student_ids is not None:
        student_qs = student_qs.filter(id__in=class_filtered_student_ids)
    student_qs = student_qs.order_by("student_profile__student_number", "username")

    students = []
    for student in student_qs:
        profile = getattr(student, "student_profile", None)
        students.append(
            {
                "id": student.id,
                "name": student.get_full_name() or student.display_name or student.username,
                "username": student.username,
                "student_number": profile.student_number if profile else "-",
                "class_code": class_map.get(student.id, "-"),
                "date_of_birth": profile.date_of_birth if profile else None,
                "age": _calculate_age(profile.date_of_birth) if profile else None,
                "gender": profile.get_gender_display() if profile and profile.gender else "-",
                "guardian_name": profile.guardian_name if profile else "",
                "guardian_phone": profile.guardian_phone if profile else "",
                "guardian_email": profile.guardian_email if profile else "",
                "lifecycle": profile.get_lifecycle_state_display() if profile else "-",
                "club_count": club_count_map.get(student.id, 0),
                "result_count": result_count_map.get(student.id, 0),
                "medical_flag": bool((profile.medical_notes or "").strip()) if profile else False,
                "discipline_flag": bool((profile.disciplinary_notes or "").strip()) if profile else False,
            }
        )

    assignment_qs = TeacherSubjectAssignment.objects.filter(is_active=True)
    if current_session:
        assignment_qs = assignment_qs.filter(session=current_session)
    if current_term:
        assignment_qs = assignment_qs.filter(term=current_term)
    assignments = list(assignment_qs.select_related("academic_class", "subject"))
    sheet_qs = ResultSheet.objects.none()
    if current_session and current_term:
        sheet_qs = ResultSheet.objects.filter(session=current_session, term=current_term).select_related("academic_class", "subject")
    sheet_map = {(row.academic_class_id, row.subject_id): row for row in sheet_qs}
    form_count_map = {}
    form_qs = FormTeacherAssignment.objects.filter(is_active=True)
    if current_session:
        form_qs = form_qs.filter(session=current_session)
    for row in form_qs.values("teacher_id").annotate(total=Count("id")):
        form_count_map[row["teacher_id"]] = row["total"]
    staff_metric_map = {}
    for assignment in assignments:
        metric_row = staff_metric_map.setdefault(
            assignment.teacher_id,
            {
                "subject_workload": 0,
                "submitted_count": 0,
                "published_count": 0,
                "levels": set(),
            },
        )
        metric_row["subject_workload"] += 1
        metric_row["levels"].add(assignment.academic_class.level_display_name)
        sheet = sheet_map.get((assignment.academic_class_id, assignment.subject_id))
        if sheet and sheet.status != ResultSheetStatus.DRAFT:
            metric_row["submitted_count"] += 1
        if sheet and sheet.status == ResultSheetStatus.PUBLISHED:
            metric_row["published_count"] += 1

    staff_qs = (
        User.objects.select_related("staff_profile", "primary_role")
        .filter(staff_profile__isnull=False, is_active=True)
        .exclude(username=settings.ANONYMOUS_USER_NAME)
    )
    if search_query:
        staff_qs = staff_qs.filter(
            Q(username__icontains=search_query)
            | Q(display_name__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(staff_profile__staff_id__icontains=search_query)
            | Q(staff_profile__designation__icontains=search_query)
        )
    staff_qs = staff_qs.order_by("staff_profile__staff_id", "username")

    staff_members = []
    for staff in staff_qs:
        profile = getattr(staff, "staff_profile", None)
        metrics = staff_metric_map.get(staff.id, {"subject_workload": 0, "submitted_count": 0, "published_count": 0, "levels": set()})
        workload = metrics["subject_workload"] or 0
        completion_rate = round((metrics["submitted_count"] / workload) * 100, 2) if workload else 0
        staff_members.append(
            {
                "id": staff.id,
                "name": staff.get_full_name() or staff.display_name or staff.username,
                "username": staff.username,
                "staff_id": profile.staff_id if profile else "-",
                "role": staff.primary_role.name if staff.primary_role else "-",
                "designation": profile.designation if profile else "",
                "phone": profile.phone_number if profile else "",
                "email": staff.email or "",
                "employment_status": profile.get_employment_status_display() if profile else "-",
                "subject_workload": workload,
                "form_class_count": form_count_map.get(staff.id, 0),
                "submitted_count": metrics["submitted_count"],
                "published_count": metrics["published_count"],
                "completion_rate": completion_rate,
                "levels": sorted(metrics["levels"]),
            }
        )

    open_elections = Election.objects.filter(is_active=True, status="OPEN").order_by("-updated_at")
    election_rows = []
    from apps.elections.services import election_turnout_counts

    for election in open_elections[:8]:
        eligible, voted, turnout = election_turnout_counts(election)
        election_rows.append(
            {
                "id": election.id,
                "title": election.title,
                "eligible_voters": eligible,
                "votes_cast": voted,
                "turnout_percent": turnout,
                "analytics_url": reverse("elections:analytics", kwargs={"election_id": election.id}),
            }
        )

    payload = {
        "current_session": current_session,
        "current_term": current_term,
        "search_query": search_query,
        "class_filter": class_filter,
        "class_options": class_options,
        "students": students,
        "staff_members": staff_members,
        "total_students": len(students),
        "total_staff": len(staff_members),
        "open_elections": election_rows,
    }
    return payload


def _campus_summary_rows(*, current_session, current_term):
    rows = []
    campus_qs = Campus.objects.filter(is_active=True).order_by("code")
    for campus in campus_qs:
        class_qs = AcademicClass.objects.filter(campus=campus, is_active=True, base_class__isnull=False)
        if not class_qs.exists():
            class_qs = AcademicClass.objects.filter(campus=campus, is_active=True, base_class__isnull=True)
        class_ids = list(class_qs.values_list("id", flat=True))
        enrollment_qs = StudentClassEnrollment.objects.filter(is_active=True, academic_class_id__in=class_ids)
        if current_session:
            enrollment_qs = enrollment_qs.filter(session=current_session)
        subject_assignment_qs = TeacherSubjectAssignment.objects.filter(is_active=True, academic_class_id__in=class_ids)
        if current_session:
            subject_assignment_qs = subject_assignment_qs.filter(session=current_session)
        if current_term:
            subject_assignment_qs = subject_assignment_qs.filter(term=current_term)
        form_assignment_qs = FormTeacherAssignment.objects.filter(is_active=True, academic_class_id__in=class_ids)
        if current_session:
            form_assignment_qs = form_assignment_qs.filter(session=current_session)
        staff_ids = set(subject_assignment_qs.values_list("teacher_id", flat=True))
        staff_ids.update(form_assignment_qs.values_list("teacher_id", flat=True))
        rows.append(
            {
                "code": campus.code,
                "name": campus.name,
                "class_count": len(class_ids),
                "student_count": enrollment_qs.values("student_id").distinct().count(),
                "staff_count": len(staff_ids),
            }
        )
    return rows


def _it_enrollment_snapshot(*, current_session=None):
    enrollment_qs = StudentClassEnrollment.objects.filter(is_active=True)
    if current_session is not None:
        enrollment_qs = enrollment_qs.filter(session=current_session)
    student_ids = list(enrollment_qs.values_list("student_id", flat=True).distinct())
    female_count = User.objects.filter(id__in=student_ids, student_profile__gender="F").count()
    male_count = User.objects.filter(id__in=student_ids, student_profile__gender="M").count()
    other_count = max(len(student_ids) - female_count - male_count, 0)

    class_rows = []
    for academic_class in AcademicClass.objects.filter(is_active=True, base_class__isnull=True).order_by("code"):
        count = enrollment_qs.filter(
            academic_class_id__in=academic_class.cohort_class_ids()
        ).values("student_id").distinct().count()
        class_rows.append(
            {
                "label": academic_class.display_name or academic_class.code,
                "count": count,
            }
        )
    max_count = max((row["count"] for row in class_rows), default=1)
    for row in class_rows:
        row["bar_percent"] = round((row["count"] / max_count) * 100, 2) if max_count else 0

    return {
        "female_count": female_count,
        "male_count": male_count,
        "other_count": other_count,
        "class_rows": class_rows,
    }


def _leadership_dashboard_payload(request):
    payload = _leadership_school_payload(request)
    current_session = payload.get("current_session")
    current_term = payload.get("current_term")
    payload["students_preview"] = payload.get("students", [])[:8]
    payload["staff_preview"] = payload.get("staff_members", [])[:8]
    payload["school_intelligence"] = build_school_intelligence(
        current_session=current_session,
        current_term=current_term,
    )
    payload["campus_rows"] = _campus_summary_rows(
        current_session=current_session,
        current_term=current_term,
    )
    return payload


class LandingPageView(TemplateView):
    template_name = "dashboard/landing.html"


class PortalPageView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/portal_home.html"
    portal_name = ""
    portal_description = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        role_codes = user.get_all_role_codes()
        portal_key = current_portal_key(self.request)
        setup_ready = setup_is_ready()
        user_display_name = (user.display_name or "").strip() or user.get_full_name() or user.username
        user_identifier = user.username
        portal_profile_photo_url = ""

        student_profile = getattr(user, "student_profile", None)
        staff_profile = getattr(user, "staff_profile", None)
        if student_profile and student_profile.student_number:
            user_identifier = student_profile.student_number
        elif staff_profile and staff_profile.staff_id:
            user_identifier = staff_profile.staff_id

        if student_profile and student_profile.profile_photo:
            portal_profile_photo_url = _portal_file_url(student_profile.profile_photo)
        elif staff_profile and staff_profile.profile_photo:
            portal_profile_photo_url = _portal_file_url(staff_profile.profile_photo)

        nav_items_for_actions = build_portal_navigation(
            portal_key=portal_key,
            role_codes=role_codes,
            request_path=self.request.path,
            setup_is_ready=setup_ready,
        )

        context["portal_name"] = self.portal_name
        context["portal_description"] = self.portal_description
        context["role_codes"] = sorted(role_codes)
        context["portal_key"] = portal_key
        context["user_display_name"] = user_display_name
        context["user_identifier"] = user_identifier
        context["portal_profile_photo_url"] = portal_profile_photo_url
        context["portal_action_items"] = _flatten_portal_action_items(
            portal_key=portal_key,
            nav_items=nav_items_for_actions,
        )
        context["portal_focus_notes"] = _portal_focus_notes(
            portal_key=portal_key,
            role_codes=role_codes,
        )
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=portal_key,
            portal_action_items=context["portal_action_items"],
        )
        return context


class StudentPortalView(PortalPageView):
    portal_name = "Student Portal"
    portal_description = "Academic records, attendance, and published results."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))
        latest_published_compilation = context.get("latest_published_compilation")
        pin_locked = bool(
            latest_published_compilation
            and SchoolProfile.load().require_result_access_pin
            and active_result_pin_for_student(
                student=self.request.user,
                session=latest_published_compilation.session,
                term=latest_published_compilation.term,
            )
        )
        result_overview = (
            None
            if pin_locked
            else _build_student_result_overview(
                student=self.request.user,
                compilation=latest_published_compilation,
            )
        )
        finance_summary = context.get("student_finance_summary") or {}
        outstanding_total = finance_summary.get("total_outstanding") or 0
        attendance_snapshot = context.get("attendance_snapshot")
        attendance_value = (
            f"{attendance_snapshot.get('percentage', 0)}%"
            if attendance_snapshot
            else "No record yet"
        )
        result_value = (
            f"{result_overview['average']}%"
            if result_overview
            else "Published"
            if latest_published_compilation
            else "No result yet"
        )
        result_meta = (
            f"{result_overview['term_name']} | {result_overview['session_name']}"
            if result_overview
            else f"{latest_published_compilation.term.get_name_display()} | Open results to view details"
            if latest_published_compilation
            else "Results will appear here when published."
        )
        context["dashboard_summary_cards"] = [
            {
                "label": "Attendance",
                "value": attendance_value,
                "meta": context.get("attendance_label") or "No record yet",
                "tone": "text-slate-900",
            },
            {
                "label": "Outstanding Fees",
                "value": outstanding_total,
                "meta": "Payment needed" if outstanding_total else "No outstanding balance",
                "tone": "text-rose-700" if outstanding_total else "text-emerald-700",
            },
            {
                "label": "Latest Result",
                "value": result_value,
                "meta": result_meta,
                "tone": "text-slate-900",
            },
            {
                "label": "Subjects",
                "value": context.get("offered_subject_count") or 0,
                "meta": "Mapped to your current enrollment",
                "tone": "text-slate-900",
            },
        ]
        context["student_result_overview"] = result_overview
        if _cloud_student_portal_limited():
            context["portal_description"] = (
                "Cloud access shows profile, attendance, subjects, transcript, digital ID, weekly challenge, "
                "classroom/LMS, published results, notifications, and payments. Internal school operations stay on the school LAN."
            )
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=context["portal_key"],
            portal_action_items=context.get("portal_action_items", []),
            student_quick_links=context.get("student_quick_links", []),
            student_next_action=context.get("student_next_action"),
        )
        return context


class StudentPortalBaseView(PortalPageView):
    portal_name = "Student Portal"
    portal_description = "Student records and academic progress."

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_STUDENT):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)


class StudentProfileView(StudentPortalBaseView):
    template_name = "dashboard/student_profile.html"
    portal_description = "Student biodata and guardian information."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_dashboard_payload(self.request, self.request.user)
        context.update(payload)
        student_profile = context.get("student_profile")
        lifecycle_label = (
            student_profile.get_lifecycle_state_display()
            if student_profile and getattr(student_profile, "lifecycle_state", "")
            else "Active"
        )
        lifecycle_tone = (
            "bg-emerald-50 text-emerald-700"
            if str(lifecycle_label).strip().lower() in {"active", "enrolled", "continuing"}
            else "bg-amber-50 text-amber-700"
        )
        student_age = _calculate_age(getattr(student_profile, "date_of_birth", None))
        identity_rows = [
            _profile_row("Full name", self.request.user.get_full_name() or self.request.user.display_name or self.request.user.username),
            _profile_row("First name", self.request.user.first_name),
            _profile_row("Last name", self.request.user.last_name),
            _profile_row("Middle name", getattr(student_profile, "middle_name", "")),
            _profile_row("Student ID", context.get("user_identifier")),
            _profile_row("Portal username", self.request.user.username),
            _profile_row("Status", lifecycle_label),
            _profile_row("Gender", student_profile.get_gender_display() if student_profile and student_profile.gender else ""),
            _profile_row("Date of birth", getattr(student_profile, "date_of_birth", None)),
            _profile_row("Age", f"{student_age} years" if student_age is not None else ""),
        ]
        academic_rows = [
            _profile_row("Class", context.get("current_class_code")),
            _profile_row("Session", getattr(context.get("current_session"), "name", "")),
            _profile_row("Term", context.get("current_term").get_name_display() if context.get("current_term") else ""),
            _profile_row("Admission date", getattr(student_profile, "admission_date", None)),
            _profile_row("Nationality", getattr(student_profile, "nationality", "")),
            _profile_row("State of origin", getattr(student_profile, "state_of_origin", "")),
        ]
        contact_rows = [
            _profile_row("Student email", self.request.user.email),
            _profile_row("Home address", getattr(student_profile, "address", "")),
        ]
        guardian_rows = [
            _profile_row("Parent / Guardian", getattr(student_profile, "guardian_name", "")),
            _profile_row("Parent phone", getattr(student_profile, "guardian_phone", "")),
            _profile_row("Parent email", getattr(student_profile, "guardian_email", "")),
        ]
        secondary_sections = []
        for title, value in [
            ("Student note", getattr(student_profile, "lifecycle_note", "")),
            ("Medical notes", getattr(student_profile, "medical_notes", "")),
            ("Disciplinary notes", getattr(student_profile, "disciplinary_notes", "")),
        ]:
            if _has_display_value(value):
                secondary_sections.append({"title": title, "value": value})
        context["student_status_badge"] = {"label": lifecycle_label, "tone": lifecycle_tone}
        context["profile_identity_rows"] = [row for row in identity_rows if row]
        context["profile_academic_rows"] = [row for row in academic_rows if row]
        context["profile_contact_rows"] = [row for row in contact_rows if row]
        context["profile_guardian_rows"] = [row for row in guardian_rows if row]
        context["profile_secondary_sections"] = secondary_sections
        return context


class StudentAttendanceView(StudentPortalBaseView):
    template_name = "dashboard/student_attendance.html"
    portal_description = "Attendance metrics and trend overview."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))

        session_source_qs = AcademicSession.objects.filter(
            id__in=StudentClassEnrollment.objects.filter(student=self.request.user).values("session_id")
        ).distinct()
        filter_window = _student_filter_window(
            self.request,
            include_sessions_queryset=session_source_qs,
        )
        selected_session = filter_window["selected_session"]
        selected_term = filter_window["selected_term"]

        snapshot = None
        attendance_records = []
        if selected_session and selected_term:
            snapshot = get_student_attendance_snapshot_for_window(
                self.request.user,
                session=selected_session,
                term=selected_term,
            )
            if snapshot:
                attendance_records = list(
                    AttendanceRecord.objects.filter(
                        calendar=snapshot["calendar"],
                        academic_class=snapshot["academic_class"],
                        student=self.request.user,
                    )
                    .order_by("date")
                    .values("date", "status")
                )

        attendance_label, attendance_tone_class = _attendance_tone(snapshot)
        present_days = int(snapshot.get("present_days", 0) or 0) if snapshot else 0
        absent_days = int(snapshot.get("absent_days", 0) or 0) if snapshot else 0
        unmarked_days = int(snapshot.get("unmarked_days", 0) or 0) if snapshot else 0
        bar_rows = [
            {"label": "Present", "count": present_days, "color_class": "bg-emerald-500"},
            {"label": "Absent", "count": absent_days, "color_class": "bg-rose-500"},
            {"label": "Unmarked", "count": unmarked_days, "color_class": "bg-slate-400"},
        ]
        max_count = max([row["count"] for row in bar_rows] + [1])
        for row in bar_rows:
            row["bar_percent"] = round((row["count"] / max_count) * 100, 2)

        trend_map = OrderedDict()
        for row in attendance_records:
            label = row["date"].strftime("%b")
            bucket = trend_map.setdefault(label, {"label": label, "present": 0, "marked": 0, "status_counts": {}})
            bucket["status_counts"][row["status"]] = bucket["status_counts"].get(row["status"], 0) + 1
            bucket["marked"] += 1
            if row["status"] == AttendanceStatus.PRESENT:
                bucket["present"] += 1
        trend_rows = []
        for bucket in trend_map.values():
            marked = bucket["marked"]
            percentage = round((bucket["present"] / marked) * 100, 1) if marked else 0
            trend_rows.append(
                {
                    "label": bucket["label"],
                    "percentage": percentage,
                    "present": bucket["present"],
                    "marked": marked,
                }
            )
        trend_max = max([row["percentage"] for row in trend_rows] + [1])
        for row in trend_rows:
            row["bar_percent"] = round((row["percentage"] / trend_max) * 100, 2) if trend_max else 0

        attendance_log_rows = []
        for row in reversed(attendance_records[-40:]):
            status = (row["status"] or "").upper()
            attendance_log_rows.append(
                {
                    "date": row["date"],
                    "status": status.title(),
                    "tone": (
                        "bg-emerald-50 text-emerald-700"
                        if status == AttendanceStatus.PRESENT
                        else "bg-rose-50 text-rose-700"
                        if status == AttendanceStatus.ABSENT
                        else "bg-slate-100 text-slate-600"
                    ),
                }
            )

        context.update(
            {
                "attendance_snapshot": snapshot,
                "attendance_label": attendance_label,
                "attendance_tone_class": attendance_tone_class,
                "attendance_absent_days": absent_days,
                "attendance_records": attendance_records,
                "attendance_bar_rows": bar_rows,
                "attendance_trend_rows": trend_rows,
                "attendance_log_rows": attendance_log_rows,
                **filter_window,
            }
        )
        return context


class StudentSubjectsView(StudentPortalBaseView):
    template_name = "dashboard/student_subjects.html"
    portal_description = "Subjects mapped to your current enrollment."

    def get_context_data(self, **kwargs):
        from apps.dashboard.models import LMSClassroom

        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))

        session_source_qs = AcademicSession.objects.filter(
            id__in=StudentSubjectEnrollment.objects.filter(student=self.request.user).values("session_id")
        ).distinct()
        filter_window = _student_filter_window(
            self.request,
            include_sessions_queryset=session_source_qs,
        )
        selected_session = filter_window["selected_session"]
        selected_term = filter_window["selected_term"]

        offered_subjects = []
        if selected_session:
            enrollment_qs = StudentSubjectEnrollment.objects.filter(
                student=self.request.user,
                session=selected_session,
                is_active=True,
            ).select_related("subject")

            term_subject_ids = set()
            class_enrollment = None
            if selected_term:
                class_enrollment = (
                    StudentClassEnrollment.objects.select_related("academic_class")
                    .filter(
                        student=self.request.user,
                        session=selected_session,
                        is_active=True,
                    )
                    .first()
                )
                if class_enrollment:
                    term_subject_ids = set(
                        TeacherSubjectAssignment.objects.filter(
                            session=selected_session,
                            term=selected_term,
                            academic_class=class_enrollment.academic_class.instructional_class,
                            is_active=True,
                        ).values_list("subject_id", flat=True)
                    )

            if term_subject_ids:
                enrollment_qs = enrollment_qs.filter(subject_id__in=term_subject_ids)

            enrollments = list(enrollment_qs.order_by("subject__name"))
            assignment_map = {}
            classroom_map = {}
            if class_enrollment and selected_term:
                assignment_rows = list(
                    TeacherSubjectAssignment.objects.filter(
                        session=selected_session,
                        term=selected_term,
                        academic_class=class_enrollment.academic_class.instructional_class,
                        is_active=True,
                        subject_id__in=[row.subject_id for row in enrollments],
                    ).select_related("teacher", "subject")
                )
                assignment_map = {row.subject_id: row for row in assignment_rows}
                classroom_rows = list(
                    LMSClassroom.objects.filter(
                        teacher_assignment_id__in=[row.id for row in assignment_rows],
                        is_published=True,
                    ).select_related("teacher_assignment", "teacher_assignment__subject").annotate(
                        module_total=Count("modules", distinct=True),
                        assignment_total=Count("assignments", distinct=True),
                    )
                )
                classroom_map = {row.teacher_assignment.subject_id: row for row in classroom_rows}

            for enrollment in enrollments:
                assignment = assignment_map.get(enrollment.subject_id)
                classroom = classroom_map.get(enrollment.subject_id)
                offered_subjects.append(
                    {
                        "name": enrollment.subject.name,
                        "code": enrollment.subject.code,
                        "teacher_name": (
                            assignment.teacher.get_full_name()
                            or assignment.teacher.display_name
                            or assignment.teacher.username
                        )
                        if assignment
                        else "",
                        "classroom_title": classroom.title if classroom else "",
                        "classroom_url": (
                            f"{reverse('dashboard:student-lms')}?classroom={classroom.id}"
                            if classroom
                            else ""
                        ),
                        "overview": classroom.overview if classroom and classroom.overview else "",
                        "module_total": classroom.module_total if classroom else 0,
                        "assignment_total": classroom.assignment_total if classroom else 0,
                        "term_name": selected_term.get_name_display() if selected_term else "",
                        "session_name": selected_session.name if selected_session else "",
                    }
                )

        context.update(
            {
                "offered_subjects": offered_subjects,
                "offered_subject_count": len(offered_subjects),
                **filter_window,
            }
        )
        return context


class StudentTranscriptView(StudentPortalBaseView):
    template_name = "dashboard/student_transcript.html"
    portal_description = "Full transcript and session transcript downloads."

    def get_context_data(self, **kwargs):
        from apps.finance.models import TranscriptRequest
        from apps.finance.services import finance_profile, gateway_is_enabled, gateway_provider_label

        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))
        current_session, current_term = _current_window()
        finance_settings = finance_profile()
        transcript_request = (
            TranscriptRequest.objects.filter(student=self.request.user)
            .select_related("gateway_transaction", "payment", "approved_by", "session")
            .order_by("-created_at")
            .first()
        )

        published_rows = (
            ClassResultCompilation.objects.filter(
                status=ClassCompilationStatus.PUBLISHED,
                student_records__student=self.request.user,
            )
            .select_related("session", "term")
            .order_by("-session__name", "-published_at", "-updated_at")
            .distinct()
        )
        requested_session_id = (self.request.GET.get("session_id") or "").strip()
        if requested_session_id.isdigit():
            published_rows = published_rows.filter(session_id=int(requested_session_id))

        sessions_seen = set()
        session_transcript_rows = []
        for row in published_rows:
            if row.session_id in sessions_seen:
                continue
            sessions_seen.add(row.session_id)
            session_transcript_rows.append(row)

        available_sessions = list(
            AcademicSession.objects.filter(
                id__in=ClassResultCompilation.objects.filter(
                    status=ClassCompilationStatus.PUBLISHED,
                    student_records__student=self.request.user,
                ).values("session_id")
            )
            .distinct()
            .order_by("-name")
        )
        selected_session = None
        if requested_session_id.isdigit():
            selected_session = next(
                (session for session in available_sessions if session.id == int(requested_session_id)),
                None,
            )

        context["session_transcript_rows"] = session_transcript_rows
        context["available_sessions"] = available_sessions
        context["selected_session"] = selected_session
        context["current_session"] = current_session
        context["current_term"] = current_term
        context["transcript_request"] = transcript_request
        context["transcript_access_granted"] = bool(transcript_request and transcript_request.is_access_granted)
        context["transcript_fee_amount"] = finance_settings.transcript_fee_amount
        context["transcript_fee_note"] = finance_settings.transcript_fee_note
        context["gateway_enabled"] = gateway_is_enabled()
        context["gateway_provider_label"] = gateway_provider_label()
        context["transcript_download_url"] = reverse("pdfs:student-transcript-download")
        return context

    def post(self, request, *args, **kwargs):
        from apps.finance.models import (
            TranscriptRequest,
            TranscriptRequestApprovalStatus,
            TranscriptRequestPaymentStatus,
        )
        from apps.finance.services import finance_profile, initialize_gateway_payment_transaction

        action = (request.POST.get("action") or "").strip().lower()
        if action != "init_transcript_payment":
            messages.error(request, "Invalid transcript action.")
            return redirect("dashboard:student-transcript")

        session, term = _current_window()
        if session is None:
            messages.error(request, "Transcript requests require an active school session.")
            return redirect("dashboard:student-transcript")

        profile = finance_profile()
        if profile.transcript_fee_amount <= 0:
            messages.error(request, "Transcript fee has not been configured yet. Please contact management.")
            return redirect("dashboard:student-transcript")

        latest_request = (
            TranscriptRequest.objects.filter(student=request.user)
            .order_by("-created_at")
            .first()
        )
        if latest_request and latest_request.is_access_granted:
            messages.success(request, "Your transcript is already available for download.")
            return redirect("dashboard:student-transcript")

        transcript_request = latest_request
        if transcript_request is None or transcript_request.approval_status == TranscriptRequestApprovalStatus.REJECTED:
            transcript_request = TranscriptRequest.objects.create(
                student=request.user,
                session=session,
                requested_by=request.user,
                amount=profile.transcript_fee_amount,
                note="Student transcript request created from the portal.",
            )
        else:
            transcript_request.session = session
            transcript_request.amount = profile.transcript_fee_amount
            transcript_request.response_message = ""
            transcript_request.save(update_fields=["session", "amount", "response_message", "updated_at"])

        try:
            transaction_row = initialize_gateway_payment_transaction(
                student=request.user,
                session=session,
                term=term,
                amount=profile.transcript_fee_amount,
                initiated_by=request.user,
                request=request,
                auto_email_link=False,
            )
        except Exception as exc:
            messages.error(request, "; ".join(getattr(exc, "messages", []) or [str(exc)]))
            return redirect("dashboard:student-transcript")

        metadata = dict(transaction_row.metadata or {})
        metadata.update(
            {
                "service_kind": "TRANSCRIPT",
                "transcript_request_id": transcript_request.id,
                "redirect_path": reverse("dashboard:student-transcript"),
            }
        )
        transaction_row.metadata = metadata
        transaction_row.save(update_fields=["metadata", "updated_at"])

        transcript_request.gateway_transaction = transaction_row
        transcript_request.payment_status = TranscriptRequestPaymentStatus.INITIALIZED
        transcript_request.response_message = (
            "Transcript payment has been initialized. Complete payment to continue to management review."
        )
        transcript_request.save(
            update_fields=["gateway_transaction", "payment_status", "response_message", "updated_at"]
        )

        if transaction_row.authorization_url:
            return redirect(transaction_row.authorization_url)
        messages.success(request, f"Transcript payment reference {transaction_row.reference} has been created.")
        return redirect("dashboard:student-transcript")


class TranscriptRequestManagementView(PortalPageView):
    template_name = "dashboard/transcript_requests.html"
    portal_name = "Transcript Requests"
    portal_description = "Review paid transcript requests and release transcript access."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from apps.finance.models import TranscriptRequest

        context = super().get_context_data(**kwargs)
        status_filter = (self.request.GET.get("status") or "all").strip().lower()
        rows = TranscriptRequest.objects.select_related(
            "student",
            "student__student_profile",
            "payment",
            "gateway_transaction",
            "approved_by",
            "session",
        ).order_by("-created_at")
        if status_filter == "pending":
            rows = rows.filter(approval_status="PENDING")
        elif status_filter == "approved":
            rows = rows.filter(approval_status="APPROVED")
        elif status_filter == "paid":
            rows = rows.filter(payment_status="PAID")
        context["transcript_requests"] = rows[:150]
        context["status_filter"] = status_filter
        return context

    def post(self, request, *args, **kwargs):
        from apps.finance.models import (
            TranscriptRequest,
            TranscriptRequestApprovalStatus,
            TranscriptRequestPaymentStatus,
        )
        from apps.notifications.models import NotificationCategory
        from apps.notifications.services import create_notification, send_email_event

        transcript_request = get_object_or_404(TranscriptRequest, pk=request.POST.get("request_id"))
        action = (request.POST.get("action") or "").strip().lower()
        note = (request.POST.get("response_message") or "").strip()

        if action == "approve":
            if transcript_request.payment_status != TranscriptRequestPaymentStatus.PAID:
                messages.error(request, "Transcript can only be released after payment is confirmed.")
                return redirect("dashboard:transcript-requests")
            transcript_request.approval_status = TranscriptRequestApprovalStatus.APPROVED
            transcript_request.approved_by = request.user
            transcript_request.approved_at = timezone.now()
            transcript_request.released_at = timezone.now()
            transcript_request.response_message = note or (
                "Your transcript request has been approved. You can now access your transcript from the student portal."
            )
            transcript_request.save(
                update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "released_at",
                    "response_message",
                    "updated_at",
                ]
            )
            create_notification(
                recipient=transcript_request.student,
                category=NotificationCategory.SYSTEM,
                title="Transcript request approved",
                message=transcript_request.response_message,
                created_by=request.user,
                action_url=reverse("dashboard:student-transcript"),
                metadata={"transcript_request_id": transcript_request.id},
            )
            student_email = (transcript_request.student.email or "").strip()
            if student_email:
                send_email_event(
                    to_emails=[student_email],
                    subject="NDGA Transcript Request Approved",
                    body_text=transcript_request.response_message,
                    actor=request.user,
                    request=request,
                    metadata={"event": "TRANSCRIPT_REQUEST_APPROVED", "transcript_request_id": transcript_request.id},
                )
            messages.success(request, "Transcript access released to the student.")
            return redirect("dashboard:transcript-requests")

        if action == "reject":
            transcript_request.approval_status = TranscriptRequestApprovalStatus.REJECTED
            transcript_request.approved_by = request.user
            transcript_request.approved_at = timezone.now()
            transcript_request.response_message = note or "Transcript request was reviewed and needs follow-up with management."
            transcript_request.save(
                update_fields=[
                    "approval_status",
                    "approved_by",
                    "approved_at",
                    "response_message",
                    "updated_at",
                ]
            )
            messages.success(request, "Transcript request updated.")
            return redirect("dashboard:transcript-requests")

        messages.error(request, "Invalid transcript management action.")
        return redirect("dashboard:transcript-requests")


class StudentSettingsView(StudentPortalBaseView):
    template_name = "dashboard/student_settings.html"
    portal_description = "Account settings and password control."

    def _display_form(self):
        return StudentDisplaySettingsForm(instance=self.request.user)

    def _password_form(self):
        return PolicyPasswordChangeForm(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))
        context["display_form"] = kwargs.get("display_form") or self._display_form()
        context["password_form"] = kwargs.get("password_form") or self._password_form()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "update_display":
            display_form = StudentDisplaySettingsForm(request.POST, instance=request.user)
            if display_form.is_valid():
                display_form.save()
                messages.success(request, "Display settings updated.")
                return redirect("dashboard:student-settings")
            return self.render_to_response(
                self.get_context_data(
                    display_form=display_form,
                    password_form=self._password_form(),
                )
            )

        if action == "change_password":
            password_form = PolicyPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                apply_self_service_password_change(
                    request.user,
                    password_form.cleaned_data["new_password1"],
                )
                update_session_auth_hash(request, request.user)
                log_password_change(actor=request.user, request=request)
                messages.success(request, "Password updated successfully.")
                return redirect("dashboard:student-settings")
            if password_form.non_field_errors():
                log_password_change_denied(
                    actor=request.user,
                    request=request,
                    reason="; ".join(password_form.non_field_errors()),
                )
            return self.render_to_response(
                self.get_context_data(
                    display_form=self._display_form(),
                    password_form=password_form,
                )
            )

        messages.error(request, "Invalid settings action.")
        return redirect("dashboard:student-settings")


class StaffPortalView(PortalPageView):
    portal_name = "Staff Portal"
    portal_description = "Teaching workflows, approvals, and class operations."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_staff_dashboard_payload(self.request.user))
        if _cloud_staff_admin_lan_only(self.request.user):
            context["portal_description"] = (
                "Cloud access remains available for profile updates and viewing school information. "
                "Operational work runs on the school LAN."
            )
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=context["portal_key"],
            portal_action_items=context.get("portal_action_items", []),
            role_panels=context.get("role_panels", []),
        )
        return context


class StaffPortalBaseView(PortalPageView):
    portal_name = "Staff Portal"
    portal_description = "Staff records and workflow settings."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(
            request.user,
            {ROLE_SUBJECT_TEACHER},
        ):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)


class DeanPortalBaseView(PortalPageView):
    portal_name = "Dean Portal"
    portal_description = "Vet questions, review submitted results, and approve or reject academic work."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_DEAN}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)


class DeanPortalView(DeanPortalBaseView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_dean_portal_payload(self.request.user))
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=context["portal_key"],
            portal_action_items=context.get("portal_action_items", []),
        )
        return context


class FormTeacherPortalBaseView(PortalPageView):
    portal_name = "Form Teacher Portal"
    portal_description = "Manage assigned students, attendance, and class result comments."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_FORM_TEACHER}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)


class FormTeacherPortalView(FormTeacherPortalBaseView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_form_teacher_portal_payload(self.request.user))
        if context.get("form_portal_description_override"):
            context["portal_description"] = context["form_portal_description_override"]
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=context["portal_key"],
            portal_action_items=context.get("portal_action_items", []),
        )
        return context


class StaffProfileView(StaffPortalBaseView):
    template_name = "dashboard/staff_profile.html"
    portal_description = "Staff biodata and role profile."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_staff_dashboard_payload(self.request.user))
        staff_profile = getattr(self.request.user, "staff_profile", None)
        assignment_qs = TeacherSubjectAssignment.objects.filter(
            teacher=self.request.user,
            is_active=True,
        )
        form_assignment_qs = FormTeacherAssignment.objects.filter(teacher=self.request.user, is_active=True).select_related("academic_class", "session")
        current_session, current_term = _current_window()
        window_assignments = TeacherSubjectAssignment.objects.none()
        result_sheet_qs = ResultSheet.objects.none()
        if current_session and current_term:
            window_assignments = assignment_qs.filter(session=current_session, term=current_term).select_related("academic_class", "subject")
            pair_filter = Q(pk__in=[])
            for row in window_assignments:
                pair_filter |= Q(academic_class_id=row.academic_class_id, subject_id=row.subject_id)
            result_sheet_qs = ResultSheet.objects.filter(pair_filter, session=current_session, term=current_term)
        context["staff_profile"] = staff_profile
        context["teaching_assignment_count"] = assignment_qs.count()
        context["teaching_classes"] = sorted(
            set((row.display_name or row.code) for row in AcademicClass.objects.filter(id__in=assignment_qs.values_list("academic_class_id", flat=True).distinct()))
        )
        context["current_subjects"] = sorted(set(window_assignments.values_list("subject__name", flat=True))) if current_session and current_term else []
        context["current_levels"] = sorted(set(row.academic_class.level_display_name for row in window_assignments)) if current_session and current_term else []
        context["result_status_counts"] = {
            "draft": result_sheet_qs.filter(status=ResultSheetStatus.DRAFT).count(),
            "submitted": result_sheet_qs.exclude(status=ResultSheetStatus.DRAFT).count(),
            "published": result_sheet_qs.filter(status=ResultSheetStatus.PUBLISHED).count(),
        }
        context["form_assignments"] = form_assignment_qs.order_by("-session__name", "academic_class__code")
        return context


class StaffResultsOverviewView(StaffPortalBaseView):
    template_name = "dashboard/staff_results_overview.html"
    portal_description = "Read-only result visibility for cloud access."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_staff_results_readonly_payload(self.request.user))
        context["readonly_notice"] = (
            "This page is read-only on cloud. Use the school LAN for score entry, dean review, "
            "and any result updates."
        )
        return context


class StaffAttendanceOverviewView(StaffPortalBaseView):
    template_name = "dashboard/staff_attendance_overview.html"
    portal_description = "Read-only attendance visibility for cloud access."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_staff_attendance_readonly_payload(self.request.user))
        context["readonly_notice"] = (
            "This page is read-only on cloud. Use the school LAN for attendance marking "
            "and attendance corrections."
        )
        return context


class StaffSettingsView(StaffPortalBaseView):
    template_name = "dashboard/staff_settings.html"
    portal_description = "Display settings and password control."

    def _display_form(self):
        return StudentDisplaySettingsForm(instance=self.request.user)

    def _password_form(self):
        return PolicyPasswordChangeForm(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_staff_dashboard_payload(self.request.user))
        context["display_form"] = kwargs.get("display_form") or self._display_form()
        context["password_form"] = kwargs.get("password_form") or self._password_form()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "update_display":
            display_form = StudentDisplaySettingsForm(request.POST, instance=request.user)
            if display_form.is_valid():
                display_form.save()
                messages.success(request, "Display settings updated.")
                return redirect("dashboard:staff-settings")
            return self.render_to_response(
                self.get_context_data(
                    display_form=display_form,
                    password_form=self._password_form(),
                )
            )

        if action == "change_password":
            password_form = PolicyPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                apply_self_service_password_change(
                    request.user,
                    password_form.cleaned_data["new_password1"],
                )
                update_session_auth_hash(request, request.user)
                log_password_change(actor=request.user, request=request)
                messages.success(request, "Password updated successfully.")
                return redirect("dashboard:staff-settings")
            if password_form.non_field_errors():
                log_password_change_denied(
                    actor=request.user,
                    request=request,
                    reason="; ".join(password_form.non_field_errors()),
                )
            return self.render_to_response(
                self.get_context_data(
                    display_form=self._display_form(),
                    password_form=password_form,
                )
            )

        messages.error(request, "Invalid settings action.")
        return redirect("dashboard:staff-settings")


class AccountSecuritySettingsView(PortalPageView):
    template_name = "dashboard/account_security_settings.html"
    portal_name = "Account Security"
    portal_description = "Optional email verification for privileged portal sign-ins."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL}):
            messages.error(request, "Account security settings are available only to privileged portal roles.")
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _security_form(self):
        return PrivilegedSecuritySettingsForm(instance=self.request.user, user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["security_form"] = kwargs.get("security_form") or self._security_form()
        context["effective_two_factor_email"] = privileged_login_target_email(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action != "update_security":
            messages.error(request, "Invalid security settings action.")
            return redirect("dashboard:account-security-settings")

        security_form = PrivilegedSecuritySettingsForm(request.POST, instance=request.user, user=request.user)
        if security_form.is_valid():
            security_form.save()
            log_event(
                category=AuditCategory.AUTH,
                event_type="LOGIN_2FA_SETTINGS_UPDATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "two_factor_enabled": bool(request.user.two_factor_enabled),
                    "two_factor_email": request.user.two_factor_email or request.user.email or "",
                },
            )
            messages.success(request, "Account security settings updated.")
            return redirect("dashboard:account-security-settings")

        return self.render_to_response(self.get_context_data(security_form=security_form))


class ITPortalView(PortalPageView):
    portal_name = "IT Manager Portal"
    portal_description = "System governance, provisioning, and credential operations."

    def get(self, request, *args, **kwargs):
        if not setup_is_ready():
            return redirect("setup_wizard:wizard")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        runtime_flags = get_runtime_feature_flags()
        school_profile = SchoolProfile.load()
        current_session, _current_term = _current_window()
        visible_class_total = _class_list_total()
        admissions_snapshot = _admissions_dashboard_snapshot()
        context["it_metrics"] = {
            "campuses_total": Campus.objects.filter(is_active=True).count(),
            "classes_total": visible_class_total,
            "main_levels_total": _active_class_levels_qs().count(),
            "arm_classes_total": _active_class_list_qs().count(),
            "subjects_total": Subject.objects.filter(is_active=True).count(),
            "students_total": User.objects.filter(primary_role__code="STUDENT").count(),
            "staff_total": User.objects.filter(staff_profile__isnull=False).exclude(
                username=settings.ANONYMOUS_USER_NAME
            ).count(),
            "result_pin_required": school_profile.require_result_access_pin,
            "notifications_unread": _visible_notification_queryset(self.request.user).filter(read_at__isnull=True).count(),
        }
        context["admissions_snapshot"] = admissions_snapshot
        context["portal_stat_cards"] = [
            {
                "label": "New Applicants",
                "value": admissions_snapshot["new"],
                "meta": "Fresh online registrations awaiting review.",
            },
            {
                "label": "Pending Review",
                "value": admissions_snapshot["pending"],
                "meta": "Applicants already moved into admissions workflow.",
            },
            {
                "label": "Paid Forms",
                "value": admissions_snapshot["paid"],
                "meta": "Applicants with confirmed application form payment.",
            },
            {
                "label": "Unpaid Forms",
                "value": admissions_snapshot["unpaid"],
                "meta": "Applicants still awaiting payment confirmation.",
            },
        ]
        context["it_enrollment_snapshot"] = _it_enrollment_snapshot(current_session=current_session)
        context["runtime_flags"] = runtime_flags
        if _cloud_staff_admin_lan_only(self.request.user):
            context["portal_description"] = (
                "Cloud access is limited to viewing system information, audit visibility, and account security. "
                "Provisioning, CBT, elections, records, and setup run on the school LAN."
            )
        context["portal_priority_actions"] = _build_portal_priority_actions(
            portal_key=context["portal_key"],
            portal_action_items=context.get("portal_action_items", []),
        )
        return context


class BursarPortalView(PortalPageView):
    portal_name = "Bursar Portal"
    portal_description = "Finance operations and receipt controls."

    def get(self, request, *args, **kwargs):
        return redirect("dashboard:bursar-finance")


class VPPortalView(PortalPageView):
    template_name = "dashboard/leadership_dashboard.html"
    portal_name = "Vice Principal Portal"
    portal_description = "School oversight for staff and student management, media broadcasts, and final result publishing."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_dashboard_payload(self.request))
        context["admissions_snapshot"] = _admissions_dashboard_snapshot()
        context["admissions_page_url"] = reverse("dashboard:vp-admissions-workflow")
        cloud_staff_admin_lan_only = _cloud_staff_admin_lan_only(self.request.user)
        context["show_finance_summary"] = False
        context["show_election_summary"] = False
        context["finance_metrics"] = None
        context["students_page_url"] = reverse("dashboard:vp-students-biodata")
        context["staff_page_url"] = reverse("dashboard:vp-staff-biodata")
        context["election_page_url"] = ""
        context["results_approval_url"] = "" if cloud_staff_admin_lan_only else reverse("results:approval-class-list")
        context["staff_management_url"] = "" if cloud_staff_admin_lan_only else reverse("accounts:it-staff-directory")
        context["student_management_url"] = "" if cloud_staff_admin_lan_only else reverse("accounts:it-student-directory")
        context["media_center_url"] = "" if cloud_staff_admin_lan_only else reverse("notifications:media-center")
        if cloud_staff_admin_lan_only:
            context["portal_description"] = (
                "Cloud access remains available for oversight review and profile updates. "
                "Operational management runs on the school LAN."
            )
        return context


class PrincipalPortalView(PortalPageView):
    template_name = "dashboard/leadership_dashboard.html"
    portal_name = "Principal Portal"
    portal_description = "School overview and quick links to dedicated biodata, approvals, media, and election pages."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_dashboard_payload(self.request))
        context["admissions_snapshot"] = _admissions_dashboard_snapshot()
        context["admissions_page_url"] = reverse("dashboard:principal-admissions-workflow")
        cloud_staff_admin_lan_only = _cloud_staff_admin_lan_only(self.request.user)
        current_session, current_term = _current_window()
        context["show_finance_summary"] = bool(current_session) and not cloud_staff_admin_lan_only
        context["show_election_summary"] = not cloud_staff_admin_lan_only
        if current_session and not cloud_staff_admin_lan_only:
            from apps.finance.services import finance_summary_metrics

            context["finance_metrics"] = finance_summary_metrics(
                session=current_session,
                term=current_term,
            )
        else:
            context["finance_metrics"] = None
        context["students_page_url"] = reverse("dashboard:principal-students-biodata")
        context["staff_page_url"] = reverse("dashboard:principal-staff-biodata")
        context["election_page_url"] = "" if cloud_staff_admin_lan_only else reverse("dashboard:principal-election-live")
        context["results_approval_url"] = "" if cloud_staff_admin_lan_only else reverse("results:approval-class-list")
        context["staff_management_url"] = "" if cloud_staff_admin_lan_only else reverse("accounts:it-staff-directory")
        context["student_management_url"] = "" if cloud_staff_admin_lan_only else reverse("accounts:it-student-directory")
        context["finance_summary_url"] = "" if cloud_staff_admin_lan_only else reverse("finance:summary")
        context["media_center_url"] = "" if cloud_staff_admin_lan_only else reverse("notifications:media-center")
        if cloud_staff_admin_lan_only:
            context["portal_description"] = (
                "Cloud access remains available for oversight review and profile updates. "
                "Operational management runs on the school LAN."
            )
        return context


class ITPublicWebsiteSettingsView(PortalPageView):
    template_name = "dashboard/public_website_settings.html"
    portal_name = "IT Manager Portal"
    portal_description = "Manage public website content, contact details, gallery, news, and events."
    SECTION_META = {
        "overview": {"label": "Overview", "description": "Open the public website control pages."},
        "branding": {"label": "Branding", "description": "School name, principal name, and logo."},
        "contact": {"label": "Contact Details", "description": "Phone, email, address, and website."},
        "homepage": {"label": "Homepage Hero", "description": "Main heading and red support line on the homepage."},
        "principal": {"label": "Principal Message", "description": "Principal welcome heading and message blocks."},
        "support-chat": {"label": "Support & Footer", "description": "Footer statement and chatbot copy."},
        "gallery-categories": {"label": "Gallery Categories", "description": "Create and manage gallery sections."},
        "gallery-images": {"label": "Gallery Images", "description": "Upload and update images for each section."},
        "news": {"label": "News & Blog", "description": "Publish school updates and blog entries."},
        "events": {"label": "Events", "description": "Manage upcoming and past school events."},
    }

    def dispatch(self, request, *args, **kwargs):
        if not any(request.user.has_role(code) for code in {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}):
            messages.error(request, "Public website settings are restricted to management.")
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _site_profile(self):
        return SchoolProfile.load()

    def _public_site_settings(self):
        return PublicWebsiteSettings.load()

    def _active_section(self):
        section = (self.kwargs.get("section") or "overview").strip().lower()
        if section not in self.SECTION_META:
            section = "overview"
        return section

    def _section_url(self, section):
        if section == "overview":
            return reverse("dashboard:it-public-website-settings")
        return reverse("dashboard:it-public-website-section", kwargs={"section": section})

    def _redirect_to_section(self, section):
        return redirect(self._section_url(section or "overview"))

    def _profile_form_payload(self, request, profile):
        return {
            "school_name": request.POST.get("school_name", profile.school_name),
            "address": request.POST.get("address", profile.address),
            "contact_email": request.POST.get("contact_email", profile.contact_email),
            "contact_phone": request.POST.get("contact_phone", profile.contact_phone),
            "website": request.POST.get("website", profile.website),
            "principal_name": request.POST.get("principal_name", profile.principal_name),
        }

    def _site_settings_form_payload(self, request, settings_row):
        return {
            "hero_eyebrow": request.POST.get("hero_eyebrow", settings_row.hero_eyebrow),
            "hero_title": request.POST.get("hero_title", settings_row.hero_title),
            "hero_subtitle": request.POST.get("hero_subtitle", settings_row.hero_subtitle),
            "principal_welcome_title": request.POST.get(
                "principal_welcome_title", settings_row.principal_welcome_title
            ),
            "principal_welcome_message": request.POST.get(
                "principal_welcome_message", settings_row.principal_welcome_message
            ),
            "principal_welcome_support": request.POST.get(
                "principal_welcome_support", settings_row.principal_welcome_support
            ),
            "footer_statement": request.POST.get("footer_statement", settings_row.footer_statement),
            "chat_welcome_text": request.POST.get("chat_welcome_text", settings_row.chat_welcome_text),
            "chat_management_wait_text": request.POST.get(
                "chat_management_wait_text", settings_row.chat_management_wait_text
            ),
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_section = kwargs.get("active_section") or self._active_section()
        context["active_section"] = active_section
        context["website_sections"] = [
            {
                "slug": slug,
                "label": meta["label"],
                "description": meta["description"],
                "url": self._section_url(slug),
                "is_active": slug == active_section,
            }
            for slug, meta in self.SECTION_META.items()
        ]
        context["branding_form"] = kwargs.get("branding_form") or PublicSiteBrandingForm(instance=self._site_profile())
        context["site_settings_form"] = kwargs.get("site_settings_form") or PublicWebsiteSettingsForm(
            instance=self._public_site_settings()
        )
        context["gallery_category_form"] = kwargs.get("gallery_category_form") or PublicGalleryCategoryForm()
        context["gallery_image_form"] = kwargs.get("gallery_image_form") or PublicGalleryImageForm()
        context["news_form"] = kwargs.get("news_form") or PublicNewsPostForm()
        context["event_form"] = kwargs.get("event_form") or PublicEventPostForm()
        context["gallery_categories"] = PublicGalleryCategory.objects.prefetch_related("images").order_by("sort_order", "title")
        context["gallery_images"] = PublicGalleryImage.objects.select_related("category").order_by(
            "category__sort_order", "sort_order", "id"
        )[:120]
        context["news_posts"] = PublicNewsPost.objects.order_by("sort_order", "-published_on", "-created_at")[:40]
        context["event_posts"] = PublicEventPost.objects.order_by("sort_order", "event_date", "title")[:40]
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        active_section = (request.POST.get("return_section") or self._active_section()).strip().lower()

        if action == "save_branding":
            profile = self._site_profile()
            form = PublicSiteBrandingForm(
                self._profile_form_payload(request, profile),
                request.FILES,
                instance=profile,
            )
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(branding_form=form, active_section="branding"))
            profile = form.save(commit=False)
            profile.updated_by = request.user
            profile.save()
            messages.success(request, "Public contact and branding details updated.")
            return self._redirect_to_section("branding")

        if action == "save_contact":
            profile = self._site_profile()
            form = PublicSiteBrandingForm(
                self._profile_form_payload(request, profile),
                request.FILES,
                instance=profile,
            )
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(branding_form=form, active_section="contact"))
            profile = form.save(commit=False)
            profile.updated_by = request.user
            profile.save()
            messages.success(request, "Public contact details updated.")
            return self._redirect_to_section("contact")

        if action == "save_site_settings":
            settings_row = self._public_site_settings()
            form = PublicWebsiteSettingsForm(
                self._site_settings_form_payload(request, settings_row),
                instance=settings_row,
            )
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(site_settings_form=form, active_section="homepage"))
            settings_row = form.save(commit=False)
            settings_row.updated_by = request.user
            settings_row.save()
            messages.success(request, "Public homepage and support text updated.")
            return self._redirect_to_section("homepage")

        if action == "save_principal_message":
            settings_row = self._public_site_settings()
            form = PublicWebsiteSettingsForm(
                self._site_settings_form_payload(request, settings_row),
                instance=settings_row,
            )
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(site_settings_form=form, active_section="principal"))
            settings_row = form.save(commit=False)
            settings_row.updated_by = request.user
            settings_row.save()
            messages.success(request, "Principal message updated.")
            return self._redirect_to_section("principal")

        if action == "save_support_settings":
            settings_row = self._public_site_settings()
            form = PublicWebsiteSettingsForm(
                self._site_settings_form_payload(request, settings_row),
                instance=settings_row,
            )
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(site_settings_form=form, active_section="support-chat")
                )
            settings_row = form.save(commit=False)
            settings_row.updated_by = request.user
            settings_row.save()
            messages.success(request, "Support and footer text updated.")
            return self._redirect_to_section("support-chat")

        if action == "create_gallery_category":
            form = PublicGalleryCategoryForm(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(gallery_category_form=form, active_section="gallery-categories")
                )
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Gallery category saved.")
            return self._redirect_to_section("gallery-categories")

        if action == "update_gallery_category":
            row = get_object_or_404(PublicGalleryCategory, pk=request.POST.get("row_id"))
            form = PublicGalleryCategoryForm(request.POST, request.FILES, instance=row)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(gallery_category_form=form, active_section="gallery-categories")
                )
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Gallery category updated.")
            return self._redirect_to_section("gallery-categories")

        if action == "delete_gallery_category":
            row = get_object_or_404(PublicGalleryCategory, pk=request.POST.get("row_id"))
            row.delete()
            messages.success(request, "Gallery category deleted.")
            return self._redirect_to_section("gallery-categories")

        if action == "create_gallery_image":
            form = PublicGalleryImageForm(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(gallery_image_form=form, active_section="gallery-images")
                )
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Gallery image saved.")
            return self._redirect_to_section("gallery-images")

        if action == "update_gallery_image":
            row = get_object_or_404(PublicGalleryImage, pk=request.POST.get("row_id"))
            form = PublicGalleryImageForm(request.POST, request.FILES, instance=row)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(gallery_image_form=form, active_section="gallery-images")
                )
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Gallery image updated.")
            return self._redirect_to_section("gallery-images")

        if action == "delete_gallery_image":
            row = get_object_or_404(PublicGalleryImage, pk=request.POST.get("row_id"))
            row.delete()
            messages.success(request, "Gallery image deleted.")
            return self._redirect_to_section("gallery-images")

        if action == "create_news_post":
            form = PublicNewsPostForm(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(news_form=form, active_section="news"))
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "News item saved.")
            return self._redirect_to_section("news")

        if action == "update_news_post":
            row = get_object_or_404(PublicNewsPost, pk=request.POST.get("row_id"))
            form = PublicNewsPostForm(request.POST, request.FILES, instance=row)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(news_form=form, active_section="news"))
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "News item updated.")
            return self._redirect_to_section("news")

        if action == "delete_news_post":
            row = get_object_or_404(PublicNewsPost, pk=request.POST.get("row_id"))
            row.delete()
            messages.success(request, "News item deleted.")
            return self._redirect_to_section("news")

        if action == "create_event_post":
            form = PublicEventPostForm(request.POST, request.FILES)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(event_form=form, active_section="events"))
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Event saved.")
            return self._redirect_to_section("events")

        if action == "update_event_post":
            row = get_object_or_404(PublicEventPost, pk=request.POST.get("row_id"))
            form = PublicEventPostForm(request.POST, request.FILES, instance=row)
            if not form.is_valid():
                return self.render_to_response(self.get_context_data(event_form=form, active_section="events"))
            row = form.save(commit=False)
            row.updated_by = request.user
            row.save()
            messages.success(request, "Event updated.")
            return self._redirect_to_section("events")

        if action == "delete_event_post":
            row = get_object_or_404(PublicEventPost, pk=request.POST.get("row_id"))
            row.delete()
            messages.success(request, "Event deleted.")
            return self._redirect_to_section("events")

        messages.error(request, "Invalid public website action.")
        return self._redirect_to_section(active_section)


class PrincipalSettingsView(PortalPageView):
    template_name = "dashboard/principal_settings.html"
    portal_name = "Principal Portal"
    portal_description = "Principal account settings and signature controls."

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_PRINCIPAL):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _display_form(self):
        return StudentDisplaySettingsForm(instance=self.request.user)

    def _password_form(self):
        return PolicyPasswordChangeForm(user=self.request.user)

    def _signature_form(self):
        return PrincipalSignatureForm()

    def _signature_record(self):
        return PrincipalSignature.objects.filter(user=self.request.user).first()

    def _signature_file_from_data_url(self, data_url: str):
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
        return ContentFile(
            decoded,
            name=f"principal-signature-{uuid.uuid4().hex}.{extension}",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["display_form"] = kwargs.get("display_form") or self._display_form()
        context["password_form"] = kwargs.get("password_form") or self._password_form()
        context["signature_form"] = kwargs.get("signature_form") or self._signature_form()
        context["signature_record"] = self._signature_record()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "update_display":
            display_form = StudentDisplaySettingsForm(request.POST, instance=request.user)
            if display_form.is_valid():
                display_form.save()
                messages.success(request, "Display settings updated.")
                return redirect("dashboard:principal-settings")
            return self.render_to_response(
                self.get_context_data(
                    display_form=display_form,
                    password_form=self._password_form(),
                    signature_form=self._signature_form(),
                )
            )

        if action == "change_password":
            password_form = PolicyPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                apply_self_service_password_change(
                    request.user,
                    password_form.cleaned_data["new_password1"],
                )
                update_session_auth_hash(request, request.user)
                log_password_change(actor=request.user, request=request)
                messages.success(request, "Password updated successfully.")
                return redirect("dashboard:principal-settings")
            if password_form.non_field_errors():
                log_password_change_denied(
                    actor=request.user,
                    request=request,
                    reason="; ".join(password_form.non_field_errors()),
                )
            return self.render_to_response(
                self.get_context_data(
                    display_form=self._display_form(),
                    password_form=password_form,
                    signature_form=self._signature_form(),
                )
            )

        if action == "save_signature":
            signature_form = PrincipalSignatureForm(request.POST, request.FILES)
            if signature_form.is_valid():
                signature_record, _created = PrincipalSignature.objects.get_or_create(user=request.user)
                uploaded_image = signature_form.cleaned_data.get("signature_image")
                signature_data = signature_form.cleaned_data.get("signature_data")

                if uploaded_image:
                    signature_record.signature_image = uploaded_image
                    signature_record.save(update_fields=["signature_image", "updated_at"])
                    messages.success(request, "Principal signature uploaded successfully.")
                    return redirect("dashboard:principal-settings")

                if signature_data:
                    try:
                        signature_file = self._signature_file_from_data_url(signature_data)
                    except ValueError as exc:
                        signature_form.add_error("signature_data", str(exc))
                    else:
                        signature_record.signature_image.save(signature_file.name, signature_file, save=True)
                        messages.success(request, "Principal signature saved from signature pad.")
                        return redirect("dashboard:principal-settings")

                if not signature_form.errors:
                    signature_form.add_error("signature_image", "Upload a signature image or draw on the signature pad.")
            return self.render_to_response(
                self.get_context_data(
                    display_form=self._display_form(),
                    password_form=self._password_form(),
                    signature_form=signature_form,
                )
            )

        if action == "clear_signature":
            signature_record = PrincipalSignature.objects.filter(user=request.user).first()
            if signature_record and signature_record.signature_image:
                signature_record.signature_image.delete(save=False)
                signature_record.signature_image = None
                signature_record.save(update_fields=["signature_image", "updated_at"])
                messages.success(request, "Principal signature removed.")
            else:
                messages.info(request, "No saved signature to remove.")
            return redirect("dashboard:principal-settings")

        messages.error(request, "Invalid settings action.")
        return redirect("dashboard:principal-settings")


class VPStudentsBiodataView(PortalPageView):
    template_name = "dashboard/leadership_students.html"
    portal_name = "Vice Principal Portal"
    portal_description = "Students biodata page."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:vp-portal")
        return context


class VPStaffBiodataView(PortalPageView):
    template_name = "dashboard/leadership_staff.html"
    portal_name = "Vice Principal Portal"
    portal_description = "Staff biodata page."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:vp-portal")
        return context


class VPElectionLiveView(PortalPageView):
    template_name = "dashboard/leadership_elections.html"
    portal_name = "Vice Principal Portal"
    portal_description = "Election live snapshot page."

    def dispatch(self, request, *args, **kwargs):
        messages.error(request, "Election live monitoring is not part of the VP workflow.")
        return redirect("dashboard:vp-portal")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:vp-portal")
        return context


class PrincipalStudentsBiodataView(PortalPageView):
    template_name = "dashboard/leadership_students.html"
    portal_name = "Principal Portal"
    portal_description = "Students biodata page."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:principal-portal")
        return context


class PrincipalStaffBiodataView(PortalPageView):
    template_name = "dashboard/leadership_staff.html"
    portal_name = "Principal Portal"
    portal_description = "Staff biodata page."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:principal-portal")
        return context


class PrincipalElectionLiveView(PortalPageView):
    template_name = "dashboard/leadership_elections.html"
    portal_name = "Principal Portal"
    portal_description = "Election live snapshot page."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_leadership_school_payload(self.request))
        context["back_url"] = reverse("dashboard:principal-portal")
        return context


class CBTPortalView(PortalPageView):
    portal_name = "CBT Portal"
    portal_description = "Computer-based testing environment."

    def get(self, request, *args, **kwargs):
        return redirect("cbt:home")


class ElectionPortalView(PortalPageView):
    portal_name = "Election Portal"
    portal_description = "Election voting and monitoring environment."

    def get(self, request, *args, **kwargs):
        return redirect("elections:home")


class PortalSummaryFragmentView(LoginRequiredMixin, TemplateView):
    def get_template_names(self):
        portal_key = current_portal_key(self.request)
        if portal_key == "student":
            return ["dashboard/partials/student_live_cards.html"]
        if portal_key in {"staff", "dean", "form", "vp", "principal"}:
            return ["dashboard/partials/staff_live_cards.html"]
        return ["dashboard/partials/empty_live_cards.html"]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        portal_key = current_portal_key(self.request)
        if portal_key == "student":
            context.update(_student_dashboard_payload(self.request, self.request.user))
        elif portal_key in {"staff", "dean", "form", "vp", "principal"}:
            context.update(_staff_dashboard_payload(self.request.user))
        return context


class PortalRootView(View):
    def get(self, request, *args, **kwargs):
        portal_key = getattr(request, "portal_key", "landing")
        if portal_key == "landing":
            from apps.dashboard.public_site import public_site_enabled

            if public_site_enabled():
                from apps.dashboard.public_views import PublicHomeView

                return PublicHomeView.as_view()(request, *args, **kwargs)
        host_root_map = {
            "landing": LandingPageView.as_view(),
            "portal": LandingPageView.as_view(),
            "student": StudentPortalView.as_view(),
            "staff": StaffPortalView.as_view(),
            "dean": DeanPortalView.as_view(),
            "form": FormTeacherPortalView.as_view(),
            "it": ITPortalView.as_view(),
            "bursar": BursarPortalView.as_view(),
            "vp": VPPortalView.as_view(),
            "principal": PrincipalPortalView.as_view(),
            "cbt": CBTPortalView.as_view(),
            "election": ElectionPortalView.as_view(),
        }
        view = host_root_map.get(portal_key, LandingPageView.as_view())
        return view(request, *args, **kwargs)


class LegacyCalendarRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if any(request.user.has_role(code) for code in {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}):
            return redirect("attendance:calendar-manage")
        return redirect("dashboard:landing")


class LegacyNoticeRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        if any(request.user.has_role(code) for code in {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL, ROLE_DEAN}):
            return redirect("notifications:media-center")
        return redirect("notifications:center")


def health_check(_request):
    return JsonResponse({"status": "ok", "service": "ndga-core"})


class ITFeatureToggleView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        if not request.user.has_role(ROLE_IT_MANAGER):
            return redirect("dashboard:landing")

        feature_key = (request.POST.get("feature_key") or "").strip().upper()
        requested_state = (request.POST.get("state") or "").strip().lower()
        field_name = FLAG_FIELD_MAP.get(feature_key)
        if not field_name:
            return redirect("dashboard:it-portal")
        if requested_state not in {"on", "off"}:
            return redirect("dashboard:it-portal")

        flags = RuntimeFeatureFlags.get_solo()
        setattr(flags, field_name, requested_state == "on")
        flags.last_updated_by = request.user
        flags.save(update_fields=[field_name, "last_updated_by", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="RUNTIME_FEATURE_TOGGLE_UPDATED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "feature_key": feature_key,
                "state": "ON" if requested_state == "on" else "OFF",
            },
        )
        return redirect("dashboard:it-portal")
