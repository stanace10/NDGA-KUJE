from django.conf import settings
from django.contrib import messages
from django.http import HttpResponseNotFound
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.accounts.constants import (
    PORTAL_ROLE_ACCESS,
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
from apps.accounts.services import resolve_role_home_url
from apps.audit.services import log_permission_denied_redirect
from apps.setup_wizard.feature_flags import get_feature_flag
from apps.setup_wizard.services import setup_is_ready
from apps.tenancy.utils import (
    build_portal_url,
    cloud_student_portal_limited_enabled,
    cloud_staff_operations_lan_only_enabled,
    current_term_staff_edit_lock,
    current_portal_key,
    lan_runtime_restrictions_enabled,
    path_is_cloud_lan_only_operation,
    path_is_cloud_student_portal_limited,
    path_is_future_term_staff_edit_operation,
    user_has_cloud_student_portal_role,
    user_has_lan_only_operation_roles,
)


class PortalAccessMiddleware:
    PROVISIONING_ROLE_CODES = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
    CLOUD_HIDDEN_PORTAL_KEYS = {"staff", "dean", "form", "it", "bursar", "vp", "principal", "cbt", "election"}
    PUBLIC_PATH_PREFIXES = ("/static/", "/media/", "/favicon.ico", "/robots.txt", "/sitemap.xml")
    AUTH_BYPASS_PREFIXES = (
        "/auth/login/",
        "/auth/logout/",
        "/auth/password/reset/",
        "/auth/mobile-capture/",
        "/ops/",
        "/sync/api/",
        "/pdfs/verify/",
        "/elections/verify/",
        "/finance/receipts/verify/",
        "/finance/gateway/callback/",
        "/finance/gateway/webhook/",
        "/health/",
    )
    LAN_ONLY_ALLOWED_PREFIXES = (
        "/",
        "/about/",
        "/about/leadership/",
        "/about/mission-vision-values/",
        "/about/school-life/",
        "/principal/",
        "/academics/",
        "/academics/junior-secondary/",
        "/academics/senior-secondary/",
        "/academics/curriculum/",
        "/academics/subjects-departments/",
        "/academics/ict-digital-learning/",
        "/academics/co-curricular-activities/",
        "/academics/learning-support/",
        "/academics/examinations-assessment/",
        "/admissions/",
        "/admissions/how-to-apply/",
        "/admissions/registration/",
        "/admissions/payment-information/",
        "/admissions/admission-faqs/",
        "/fees/",
        "/hostel-boarding/",
        "/life-at-ndga/",
        "/facilities/",
        "/gallery/",
        "/news/",
        "/events/",
        "/contact/",
        "/ops/",
        "/health/",
        "/sync/",
        "/attendance/",
        "/results/",
        "/pdfs/staff/",
        "/cbt/",
        "/cbt/it/",
        "/cbt/exams/",
        "/cbt/attempts/",
        "/elections/",
        "/portal/it/",
        "/portal/student/",
        "/portal/staff/",
        "/portal/principal/",
        "/portal/vp/",
        "/notifications/",
    )
    ROLE_GUARDED_PATH_PREFIXES = {
        "/audit/events/": PORTAL_ROLE_ACCESS["audit"],
        "/auth/it/reset-credentials/": PORTAL_ROLE_ACCESS["it"],
        "/auth/it/user-provisioning/": PROVISIONING_ROLE_CODES,
        "/auth/it/staff/": PROVISIONING_ROLE_CODES,
        "/auth/it/student/": PROVISIONING_ROLE_CODES,
        "/auth/it/user/": PROVISIONING_ROLE_CODES,
        "/setup/session-term/": {ROLE_IT_MANAGER, ROLE_BURSAR, ROLE_PRINCIPAL},
        "/setup/": PORTAL_ROLE_ACCESS["it"],
        "/academics/it/": PORTAL_ROLE_ACCESS["it"],
        "/attendance/calendar/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/attendance/form/": {ROLE_FORM_TEACHER},
        "/results/grade-entry/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_PRINCIPAL,
        },
        "/results/dean/": {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/form/": {ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/report/": {
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_VP,
            ROLE_PRINCIPAL,
            ROLE_BURSAR,
        },
        "/results/settings/": {ROLE_IT_MANAGER, ROLE_DEAN, ROLE_PRINCIPAL},
        "/results/vp/": {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/principal/": {ROLE_PRINCIPAL, ROLE_IT_MANAGER},
        "/results/timeline/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_PRINCIPAL,
        },
        "/cbt/authoring/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_PRINCIPAL,
        },
        "/cbt/dean/": {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/cbt/it/": {ROLE_IT_MANAGER},
        "/cbt/exams/": {ROLE_STUDENT},
        "/cbt/attempts/": {ROLE_STUDENT},
        "/cbt/marking/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_PRINCIPAL,
        },
        "/elections/it/manage/": {ROLE_IT_MANAGER},
        "/elections/vote/": PORTAL_ROLE_ACCESS["election"],
        "/elections/analytics/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/elections/results/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/finance/bursar/": {ROLE_BURSAR},
        "/finance/summary/": {ROLE_VP, ROLE_PRINCIPAL},
        "/finance/receipts/": {ROLE_BURSAR, ROLE_PRINCIPAL},
        "/notifications/": {
            ROLE_STUDENT,
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_BURSAR,
            ROLE_VP,
            ROLE_PRINCIPAL,
        },
        "/portal/vp/election-live/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/portal/vp/documents/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/pdfs/student/": PORTAL_ROLE_ACCESS["student"],
        "/pdfs/staff/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_VP,
            ROLE_PRINCIPAL,
        },
        "/portal/student/": PORTAL_ROLE_ACCESS["student"],
        "/portal/staff/": PORTAL_ROLE_ACCESS["staff"],
        "/portal/dean/": PORTAL_ROLE_ACCESS["dean"],
        "/portal/form/": PORTAL_ROLE_ACCESS["form"],
        "/portal/it/": PORTAL_ROLE_ACCESS["it"],
        "/portal/bursar/": PORTAL_ROLE_ACCESS["bursar"],
        "/portal/vp/": PORTAL_ROLE_ACCESS["vp"],
        "/portal/principal/": PORTAL_ROLE_ACCESS["principal"],
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.portal_key = current_portal_key(request)

        if request.path.startswith(self.PUBLIC_PATH_PREFIXES):
            return self.get_response(request)

        if self._is_feature_disabled_portal(request.portal_key):
            return self._render_unavailable(request)

        response = self._enforce_hidden_cloud_portals(request)
        if response is not None:
            return response

        if request.path.startswith(self.AUTH_BYPASS_PREFIXES):
            return self.get_response(request)

        response = self._enforce_cloud_operation_restrictions(request)
        if response is not None:
            return response

        response = self._enforce_cloud_student_portal_restrictions(request)
        if response is not None:
            return response

        response = self._enforce_lan_runtime_restrictions(request)
        if response is not None:
            return response

        response = self._enforce_setup_lockdown(request)
        if response is not None:
            return response

        response = self._enforce_future_term_staff_edit_lock(request)
        if response is not None:
            return response

        host_allowed_roles = PORTAL_ROLE_ACCESS.get(request.portal_key)
        if host_allowed_roles is not None:
            response = self._enforce_role_guard(
                request=request,
                allowed_roles=host_allowed_roles,
                denied_reason=f"Host role denied for portal {request.portal_key}",
            )
            if response is not None:
                return response

            response = self._enforce_fresh_login_for_sensitive_portals(request)
            if response is not None:
                return response

        for path_prefix, allowed_roles in self.ROLE_GUARDED_PATH_PREFIXES.items():
            if request.path.startswith(path_prefix):
                response = self._enforce_role_guard(
                    request=request,
                    allowed_roles=allowed_roles,
                    denied_reason=f"Path role denied for {request.path}",
                )
                if response is not None:
                    return response
                break

        return self.get_response(request)

    def _enforce_hidden_cloud_portals(self, request):
        if not cloud_staff_operations_lan_only_enabled():
            return None
        if request.portal_key in self.CLOUD_HIDDEN_PORTAL_KEYS:
            return HttpResponseNotFound("Not found")
        if request.path.startswith("/auth/login/"):
            audience = (request.GET.get("audience") or "").strip().lower()
            if audience in self.CLOUD_HIDDEN_PORTAL_KEYS:
                return HttpResponseNotFound("Not found")
        hidden_prefixes = (
            "/portal/staff/",
            "/portal/dean/",
            "/portal/form/",
            "/portal/it/",
            "/portal/bursar/",
            "/portal/vp/",
            "/portal/principal/",
            "/portal/cbt/",
            "/portal/election/",
            "/auth/it/",
            "/setup/",
            "/sync/",
        )
        if any(request.path.startswith(prefix) for prefix in hidden_prefixes):
            return HttpResponseNotFound("Not found")
        return None

    def _enforce_cloud_operation_restrictions(self, request):
        if not cloud_staff_operations_lan_only_enabled():
            return None
        if not getattr(request.user, "is_authenticated", False):
            return None
        if not user_has_lan_only_operation_roles(request.user):
            return None
        if not path_is_cloud_lan_only_operation(request.path):
            return None
        context = {
            "restriction_title": "School LAN Only",
            "restriction_heading": "This action can only be completed on the school LAN.",
            "restriction_message": (
                "Staff and admin operational work now runs from the school network so academics, "
                "attendance, finance records, admissions, CBT activity, elections, and approvals stay aligned on the school LAN."
            ),
            "allowed_summary": (
                "Still available here: public website access, student portal access, published result visibility, "
                "fee payment flows, and payment callbacks."
            ),
            "current_node_label": "Cloud",
        }
        return render(request, "dashboard/lan_restricted.html", context=context, status=403)

    def _enforce_lan_runtime_restrictions(self, request):
        if not lan_runtime_restrictions_enabled():
            return None
        if request.path.startswith(self.PUBLIC_PATH_PREFIXES):
            return None
        if request.path == "/":
            return None
        if request.path in {"/cbt", "/elections"}:
            return None
        if request.path.startswith(tuple(prefix for prefix in self.LAN_ONLY_ALLOWED_PREFIXES if prefix != "/")):
            return None
        context = {
            "restriction_title": "LAN Limited Mode",
            "restriction_heading": "This LAN is reserved for CBT and election operations.",
            "restriction_message": (
                "Other portals remain available on cloud while this LAN stays focused on local "
                "exam and election workloads."
            ),
            "allowed_summary": (
                "Allowed on this LAN: CBT runtime and activation, election runtime and setup, "
                "and the approved local workflows for this node."
            ),
            "current_node_label": "LAN",
        }
        return render(request, "dashboard/lan_restricted.html", context=context, status=403)

    def _enforce_cloud_student_portal_restrictions(self, request):
        if not cloud_student_portal_limited_enabled():
            return None
        if not getattr(request.user, "is_authenticated", False):
            return None
        if not user_has_cloud_student_portal_role(request.user):
            return None
        if not path_is_cloud_student_portal_limited(request.path):
            return None
        context = {
            "restriction_title": "Cloud Student View Limited",
            "restriction_heading": "This student feature is available on the school LAN only.",
            "restriction_message": (
                "Cloud student access is limited to profile, attendance, subjects, digital ID, weekly challenge, "
                "classroom/LMS, transcript, published results, notifications, and fee payment while internal authoring "
                "and school operations stay on the school LAN."
            ),
            "allowed_summary": (
                "Still available here: student profile, attendance view, subjects offered, digital ID, transcript, "
                "weekly challenge, classroom/LMS view, published result view, notifications, and payment pages."
            ),
            "current_node_label": "Cloud",
        }
        return render(request, "dashboard/lan_restricted.html", context=context, status=403)

    def _enforce_future_term_staff_edit_lock(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return None
        if not path_is_future_term_staff_edit_operation(request.path):
            return None
        role_codes = set(request.user.get_all_role_codes())
        if role_codes & {ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP, ROLE_BURSAR}:
            return None
        if not role_codes & {ROLE_SUBJECT_TEACHER, ROLE_FORM_TEACHER, ROLE_DEAN}:
            return None
        lock_state = current_term_staff_edit_lock()
        if not lock_state["locked"]:
            return None
        start_date = lock_state["start_date"]
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            request.term_edit_locked = True
            request.term_edit_lock_start_date = start_date
            request.term_edit_lock_message = ""
            return None
        context = {
            "restriction_title": "Term Entry Locked",
            "restriction_heading": "Staff editing is closed until the new term opens.",
            "restriction_message": (
                "Second term entry work is closed. Staff can continue to view earlier records, "
                "but entry, marking, and attendance actions remain locked until third term begins."
            ),
            "allowed_summary": (
                f"Third Term begins on {start_date.strftime('%B %d, %Y').replace(' 0', ' ')}. "
                "Management can still access oversight and setup controls."
            ),
            "current_node_label": "Academic Window",
        }
        return render(request, "dashboard/lan_restricted.html", context=context, status=403)

    def _is_feature_disabled_portal(self, portal_key):
        if portal_key == "cbt":
            return not get_feature_flag("CBT_ENABLED", settings.FEATURE_FLAGS.get("CBT_ENABLED", False))
        if portal_key == "election":
            return not get_feature_flag(
                "ELECTION_ENABLED",
                settings.FEATURE_FLAGS.get("ELECTION_ENABLED", False),
            )
        return False

    def _render_unavailable(self, request):
        portal_label = "CBT Portal" if request.portal_key == "cbt" else "Election Portal"
        context = {
            "portal_label": portal_label,
            "portal_key": request.portal_key,
            "portal_home_url": build_portal_url(request, "landing", "/"),
        }
        return render(request, "dashboard/portal_unavailable.html", context=context, status=200)

    def _login_url(self, request, *, fresh=False):
        query = {"next": request.path, "audience": request.portal_key}
        if fresh:
            query["fresh"] = "1"
        return build_portal_url(request, request.portal_key, reverse("accounts:login"), query)

    def _enforce_setup_lockdown(self, request):
        if setup_is_ready():
            return None
        if not request.user.is_authenticated:
            return None
        if has_any_role(request.user, {ROLE_IT_MANAGER}):
            return None

        allowed_when_unconfigured = (
            request.path == "/"
            or request.path.startswith("/portal/")
            or request.path.startswith("/audit/events/")
            or request.path.startswith("/auth/")
            or request.path.startswith("/pdfs/verify/")
            or request.path.startswith("/finance/receipts/verify/")
        )
        if allowed_when_unconfigured:
            return None

        destination = resolve_role_home_url(request.user, request=request)
        log_permission_denied_redirect(
            actor=request.user,
            request=request,
            destination=destination,
            reason="Blocked while setup wizard is incomplete.",
        )
        messages.warning(
            request,
            "System setup is incomplete. IT Manager must finalize setup first.",
        )
        return redirect(destination)

    def _enforce_role_guard(self, *, request, allowed_roles, denied_reason):
        if not request.user.is_authenticated:
            requires_fresh = self._portal_requires_fresh_login(request)
            return redirect(self._login_url(request, fresh=requires_fresh))

        if not has_any_role(request.user, allowed_roles):
            destination = resolve_role_home_url(request.user, request=request)
            log_permission_denied_redirect(
                actor=request.user,
                request=request,
                destination=destination,
                reason=denied_reason,
            )
            messages.error(
                request,
                "Access restricted for your role. Redirected to your portal.",
            )
            return redirect(destination)
        return None

    def _enforce_fresh_login_for_sensitive_portals(self, request):
        if not self._portal_requires_fresh_login(request):
            return None
        session_key = f"fresh_auth_{request.portal_key}"
        if not request.session.get(session_key):
            messages.info(
                request,
                "Fresh login required for this portal.",
            )
            return redirect(self._login_url(request, fresh=True))
        return None

    def _portal_requires_fresh_login(self, request):
        if request.portal_key not in settings.FRESH_LOGIN_REQUIRED_PORTALS:
            return False
        if request.portal_key == "cbt":
            exempt_prefixes = (
                "/cbt/authoring/",
                "/cbt/dean/",
                "/cbt/marking/",
                "/cbt/it/",
                "/cbt/simulator/",
            )
            if request.path.startswith(exempt_prefixes):
                return False
        return True
