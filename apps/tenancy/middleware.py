from django.conf import settings
from django.contrib import messages
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
from apps.tenancy.utils import build_portal_url, current_portal_key


class PortalAccessMiddleware:
    PROVISIONING_ROLE_CODES = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
    PUBLIC_PATH_PREFIXES = ("/static/", "/media/", "/favicon.ico")
    AUTH_BYPASS_PREFIXES = (
        "/auth/login/",
        "/auth/logout/",
        "/auth/password/reset/",
        "/auth/mobile-capture/",
        "/sync/api/",
        "/pdfs/verify/",
        "/elections/verify/",
        "/finance/receipts/verify/",
        "/finance/gateway/callback/",
        "/finance/gateway/webhook/",
        "/health/",
    )
    ROLE_GUARDED_PATH_PREFIXES = {
        "/audit/events/": PORTAL_ROLE_ACCESS["audit"],
        "/auth/it/reset-credentials/": PORTAL_ROLE_ACCESS["it"],
        "/auth/it/user-provisioning/": PROVISIONING_ROLE_CODES,
        "/auth/it/staff/": PROVISIONING_ROLE_CODES,
        "/auth/it/student/": PROVISIONING_ROLE_CODES,
        "/auth/it/user/": PROVISIONING_ROLE_CODES,
        "/setup/session-term/": {ROLE_IT_MANAGER, ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL},
        "/setup/": PORTAL_ROLE_ACCESS["it"],
        "/academics/it/": PORTAL_ROLE_ACCESS["it"],
        "/attendance/calendar/": {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL},
        "/attendance/form/": {ROLE_FORM_TEACHER},
        "/results/grade-entry/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_VP,
            ROLE_PRINCIPAL,
        },
        "/results/dean/": {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/form/": {ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/vp/": {ROLE_VP, ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/results/principal/": {ROLE_PRINCIPAL, ROLE_IT_MANAGER},
        "/results/timeline/": {
            ROLE_SUBJECT_TEACHER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_IT_MANAGER,
            ROLE_VP,
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
            ROLE_VP,
        },
        "/sync/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/elections/it/manage/": {ROLE_IT_MANAGER},
        "/elections/vote/": PORTAL_ROLE_ACCESS["election"],
        "/elections/analytics/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP},
        "/elections/results/": {ROLE_IT_MANAGER, ROLE_PRINCIPAL},
        "/finance/bursar/": {ROLE_BURSAR},
        "/finance/summary/": {ROLE_VP, ROLE_PRINCIPAL},
        "/finance/receipts/": {ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL},
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

        if request.path.startswith(self.AUTH_BYPASS_PREFIXES):
            return self.get_response(request)

        response = self._enforce_setup_lockdown(request)
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
            requires_fresh = request.portal_key in settings.FRESH_LOGIN_REQUIRED_PORTALS
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
        if request.portal_key not in settings.FRESH_LOGIN_REQUIRED_PORTALS:
            return None
        session_key = f"fresh_auth_{request.portal_key}"
        if not request.session.get(session_key):
            messages.info(
                request,
                "Fresh login required for this portal.",
            )
            return redirect(self._login_url(request, fresh=True))
        return None
