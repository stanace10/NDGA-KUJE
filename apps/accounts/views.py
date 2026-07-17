import logging
import json

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.sessions.models import Session
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import RequestDataTooBig, ValidationError
from django.core import signing
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.db.utils import OperationalError, ProgrammingError
from django.db.models import Prefetch, Q
from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.generic import FormView, RedirectView, TemplateView, View

import base64
import hashlib
import secrets
from urllib.parse import urlsplit

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_HOME_PORTAL,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_VP,
)
from apps.accounts.forms import (
    ITCredentialResetForm,
    ITStaffRegistrationForm,
    ITStaffUpdateForm,
    ITStudentRegistrationForm,
    ITStudentUpdateForm,
    NDGALoginForm,
    PasswordResetCodeForm,
    PrivilegedTwoFactorForm,
    PasswordResetRequestForm,
    PolicyPasswordChangeForm,
    set_user_password_from_login_id,
)
from apps.accounts.models import StaffProfile, StudentProfile, User
from apps.accounts.permissions import (
    SCOPE_ISSUE_LOGIN_CODES,
    SCOPE_MANAGE_USERS,
    has_portal_access,
    has_scope,
    requires_two_factor,
)
from apps.accounts.security import (
    clear_privileged_login_challenge,
    issue_privileged_login_challenge,
    verify_privileged_login_challenge,
)
from apps.accounts.services import (
    apply_self_service_password_change,
    issue_login_code,
    reset_password_by_it_manager,
    resolve_role_home_url,
)
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import (
    log_credentials_reset,
    log_event,
    log_password_change,
    log_password_change_denied,
)
from apps.cbt.services import finalize_cbt_attempts_on_logout
from apps.pdfs.services import qr_code_data_uri
from apps.sync.services import queue_student_registration_sync
from apps.tenancy.utils import build_portal_url, cloud_staff_operations_lan_only_enabled
from core.upload_scan import validate_image_upload


CBT_MICROPHONE_SESSION_KEY = "cbt_microphone_permission"
CBT_MICROPHONE_PERMISSION_MAX_AGE_SECONDS = 5 * 60
CBT_LOGIN_COOLDOWN_SECONDS = 60


def _cbt_active_session_cache_key(user_id):
    return f"cbt:active-login-session:{int(user_id)}"


def _cbt_login_cooldown_cache_key(user_id):
    return f"cbt:login-cooldown-until:{int(user_id)}"


def _cbt_lock_cooldown_served_cache_key(attempt_id):
    return f"cbt:lock-cooldown-served:{int(attempt_id)}"


def _cbt_login_cooldown_remaining(user_id):
    value = cache.get(_cbt_login_cooldown_cache_key(user_id))
    try:
        return max(int(float(value) - timezone.now().timestamp()), 0)
    except (TypeError, ValueError):
        return 0


def _register_exclusive_cbt_session(request, user):
    if not request.session.session_key:
        request.session.save()
    current_session_key = request.session.session_key or ""
    cache_key = _cbt_active_session_cache_key(user.id)
    existing_session_key = (cache.get(cache_key) or "").strip()
    if (
        existing_session_key
        and existing_session_key != current_session_key
        and not Session.objects.filter(
            session_key=existing_session_key,
            expire_date__gt=timezone.now(),
        ).exists()
    ):
        cache.delete(cache_key)
        existing_session_key = ""
    if existing_session_key and existing_session_key != current_session_key:
        from apps.cbt.models import CBTAttemptStatus, ExamAttempt
        from apps.cbt.services import record_lockdown_evidence

        now = timezone.now()
        active_attempts = ExamAttempt.objects.select_related("exam", "student").filter(
            student=user,
            status=CBTAttemptStatus.IN_PROGRESS,
            is_locked=False,
            exam__status="ACTIVE",
        ).filter(
            Q(exam__open_now=True, exam__schedule_end__isnull=True)
            | Q(exam__open_now=True, exam__schedule_end__gte=now)
            | Q(exam__schedule_start__lte=now, exam__schedule_end__gte=now)
        )
        for attempt in active_attempts:
            record_lockdown_evidence(
                attempt=attempt,
                event_type="MULTIPLE_LOGIN_ATTEMPT",
                request=request,
                details={
                    "cooldown_only": True,
                    "reason": "Student account opened in two CBT sessions.",
                },
            )
        cooldown_until = timezone.now().timestamp() + CBT_LOGIN_COOLDOWN_SECONDS
        cache.set(
            _cbt_login_cooldown_cache_key(user.id),
            cooldown_until,
            timeout=CBT_LOGIN_COOLDOWN_SECONDS,
        )
        Session.objects.filter(session_key=existing_session_key).delete()
        cache.delete(cache_key)
        logout(request)
        return render(
            request,
            "accounts/cbt_login_cooldown.html",
            {
                "remaining_seconds": CBT_LOGIN_COOLDOWN_SECONDS,
                "login_url": request.get_full_path(),
            },
            status=429,
        )
    cache.set(cache_key, current_session_key, timeout=12 * 60 * 60)
    return None


def _cbt_microphone_user_agent_hash(request):
    user_agent = (request.META.get("HTTP_USER_AGENT") or "").encode("utf-8")
    return hashlib.sha256(user_agent).hexdigest()


def _has_fresh_cbt_microphone_permission(request):
    marker = request.session.get(CBT_MICROPHONE_SESSION_KEY)
    if not isinstance(marker, dict):
        return False
    try:
        granted_at = float(marker.get("granted_at") or 0)
    except (TypeError, ValueError):
        return False
    age = timezone.now().timestamp() - granted_at
    return (
        0 <= age <= CBT_MICROPHONE_PERMISSION_MAX_AGE_SECONDS
        and marker.get("user_agent_hash") == _cbt_microphone_user_agent_hash(request)
    )


@method_decorator(never_cache, name="dispatch")
class CBTMicrophonePermissionView(View):
    """Record a short-lived browser microphone check before CBT student login."""

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if (
            payload.get("granted") is not True
            or payload.get("secure_context") is not True
            or not request.is_secure()
        ):
            request.session.pop(CBT_MICROPHONE_SESSION_KEY, None)
            request.session.modified = True
            return JsonResponse(
                {
                    "ok": False,
                    "message": "CBT access requires HTTPS and an allowed microphone.",
                },
                status=403,
            )
        request.session[CBT_MICROPHONE_SESSION_KEY] = {
            "granted_at": timezone.now().timestamp(),
            "user_agent_hash": _cbt_microphone_user_agent_hash(request),
        }
        request.session.modified = True
        return JsonResponse({"ok": True})

logger = logging.getLogger(__name__)


PROVISIONING_ALLOWED_ROLES = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
MOBILE_CAPTURE_TOKEN_MAX_AGE_SECONDS = 15 * 60
MOBILE_CAPTURE_CACHE_TTL_SECONDS = 20 * 60
PRIVILEGED_LOGIN_SESSION_KEY = "pending_privileged_login_2fa"


def _can_manage_school_users(user):
    return has_scope(user, SCOPE_MANAGE_USERS)


def _mobile_capture_cache_key(token: str):
    digest = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
    return f"accounts.mobile_capture.{digest}"


def _build_mobile_capture_token(*, actor_id: int):
    payload = {
        "actor_id": int(actor_id),
        "nonce": secrets.token_urlsafe(16),
        "purpose": "student_registration_capture",
    }
    return signing.dumps(payload, salt="accounts.mobile_capture")


def _read_mobile_capture_token(token: str):
    return signing.loads(
        token,
        max_age=MOBILE_CAPTURE_TOKEN_MAX_AGE_SECONDS,
        salt="accounts.mobile_capture",
    )


def _mobile_capture_public_url(request, *, portal_key: str, capture_path: str):
    public_base = (getattr(settings, "MOBILE_CAPTURE_PUBLIC_BASE_URL", "") or "").strip()
    if public_base:
        if not public_base.startswith(("http://", "https://")):
            public_base = f"https://{public_base}"
        try:
            configured_host = (urlsplit(public_base).hostname or "").strip().lower()
        except Exception:
            configured_host = ""
        request_host = (request.get_host() or "").split(":")[0].strip().lower()
        if configured_host in {"localhost", "127.0.0.1", "::1"} and request_host not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            public_base = ""
    if public_base:
        return f"{public_base.rstrip('/')}{capture_path}"
    return build_portal_url(request, portal_key, capture_path)


def _friendly_upload_limit_message():
    max_size_mb = settings.UPLOAD_SECURITY.get("MAX_IMAGE_MB", 8)
    return (
        f"Image upload failed because the file was too large for the request. "
        f"Use an image under {max_size_mb}MB, or capture a smaller photo."
    )


def _same_host_url(left_url, right_url):
    try:
        return urlsplit(left_url).netloc.lower() == urlsplit(right_url).netloc.lower()
    except Exception:
        return False


def _portal_redirect_response(request, target_url):
    current_url = request.build_absolute_uri(request.get_full_path())
    if _same_host_url(current_url, target_url):
        return HttpResponseRedirect(target_url)
    response = render(
        request,
        "accounts/login_redirect_bridge.html",
        {
            "target_url": target_url,
            "target_host": urlsplit(target_url).netloc or target_url,
        },
    )
    response["Cache-Control"] = "no-store, no-cache, max-age=0"
    return response


def _next_url_matches_primary_portal(*, user, request, next_url, portal_key_override=""):
    if not next_url:
        return False
    primary_role = getattr(user, "primary_role", None)
    primary_code = primary_role.code if primary_role is not None else ""
    portal_key = portal_key_override or ROLE_HOME_PORTAL.get(primary_code, "staff")

    parsed = urlsplit(next_url)
    path = parsed.path or "/"
    host = (parsed.netloc or request.get_host() or "").split(":")[0].strip().lower()
    expected_host = urlsplit(build_portal_url(request, portal_key, "/")).netloc.split(":")[0].strip().lower()

    allowed_prefixes = {
        "student": ("/portal/student/",),
        "staff": (
            "/portal/staff/",
            "/results/grade-entry/",
            "/cbt/authoring/",
            "/portal/staff/lesson-planner/",
            "/portal/staff/lms/",
        ),
        "dean": (
            "/portal/dean/",
            "/results/dean/",
            "/cbt/dean/",
        ),
        "form": (
            "/portal/form/",
            "/attendance/form/",
            "/results/form/",
        ),
        "vp": (
            "/portal/vp/",
            "/results/vp/",
            "/results/approval/",
            "/results/report/",
            "/attendance/form/",
            "/notifications/",
            "/portal/staff/profile/",
            "/portal/staff/settings/",
        ),
        "principal": (
            "/portal/principal/",
            "/results/principal/",
            "/results/report/",
            "/notifications/",
            "/portal/staff/profile/",
            "/portal/principal/settings/",
        ),
        "it": (
            "/portal/it/",
            "/auth/it/",
            "/academics/it/",
            "/results/approval/",
            "/results/report/",
            "/attendance/",
            "/setup/",
            "/sync/",
            "/audit/",
            "/cbt/it/",
            "/elections/it/",
            "/notifications/",
        ),
        "bursar": (
            "/portal/bursar/",
            "/finance/bursar/",
            "/notifications/",
            "/portal/staff/profile/",
        ),
        "cbt": ("/portal/cbt/", "/cbt/"),
        "election": ("/portal/election/", "/elections/"),
    }.get(portal_key, (f"/portal/{portal_key}/",))

    if parsed.netloc and host != expected_host:
        return False
    return any(path.startswith(prefix) for prefix in allowed_prefixes)


def _clear_pending_privileged_login(request):
    challenge = request.session.pop(PRIVILEGED_LOGIN_SESSION_KEY, None) or {}
    clear_privileged_login_challenge(challenge.get("challenge_id"))
    return challenge


def _complete_login_response(
    request,
    *,
    user,
    portal_hint,
    next_url="",
    clear_login_code=False,
    backend="",
):
    if clear_login_code:
        user.clear_login_code()
        user.save(update_fields=["login_code_hash", "login_code_expires_at"])
    if backend:
        login(request, user, backend=backend)
    else:
        login(request, user)
    request.session["last_authenticated_portal"] = portal_hint
    if portal_hint == "cbt" and user.has_role(ROLE_STUDENT):
        conflict_response = _register_exclusive_cbt_session(request, user)
        if conflict_response is not None:
            return conflict_response
    if portal_hint in settings.FRESH_LOGIN_REQUIRED_PORTALS:
        request.session[f"fresh_auth_{portal_hint}"] = timezone.now().isoformat()
    if user.must_change_password:
        messages.info(request, "Password change required before continuing.")
        return redirect("accounts:password-change")
    portal_override = portal_hint if portal_hint in settings.FRESH_LOGIN_REQUIRED_PORTALS else ""
    if (
        next_url
        and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
        and _next_url_matches_primary_portal(
            user=user,
            request=request,
            next_url=next_url,
            portal_key_override=portal_override,
        )
    ):
        return redirect(next_url)
    return _portal_redirect_response(
        request,
        resolve_role_home_url(user, request=request),
    )


def _portal_hint_home_response(request, *, user, portal_hint):
    special_portal_paths = {
        "cbt": reverse("cbt:home"),
        "election": reverse("elections:home"),
    }
    if portal_hint in special_portal_paths and has_portal_access(user, portal_hint):
        return _portal_redirect_response(
            request,
            build_portal_url(request, portal_hint, special_portal_paths[portal_hint]),
        )
    return _portal_redirect_response(
        request,
        resolve_role_home_url(user, request=request),
    )


def _begin_privileged_login_challenge(request, *, user, portal_hint, next_url, clear_login_code):
    challenge = issue_privileged_login_challenge(user=user)
    request.session[PRIVILEGED_LOGIN_SESSION_KEY] = {
        "challenge_id": challenge["challenge_id"],
        "user_id": int(user.id),
        "portal_hint": portal_hint,
        "next_url": next_url or "",
        "clear_login_code": bool(clear_login_code),
        "backend": getattr(user, "backend", ""),
        "masked_email": challenge["masked_email"],
        "expires_at": challenge["expires_at"].isoformat(),
    }
    request.session.modified = True
    return challenge

@method_decorator(never_cache, name="dispatch")
class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = NDGALoginForm

    def get(self, request, *args, **kwargs):
        portal_hint = (request.GET.get("audience", "") or "").strip().lower()
        if cloud_staff_operations_lan_only_enabled() and portal_hint in {
            "staff",
            "dean",
            "form",
            "it",
            "bursar",
            "vp",
            "principal",
            "cbt",
            "election",
        }:
            return HttpResponseBadRequest("This login audience is not available here.")
        fresh_requested = (request.GET.get("fresh", "") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        allow_fresh_login_page = (
            fresh_requested and portal_hint in settings.FRESH_LOGIN_REQUIRED_PORTALS
        )
        if request.user.is_authenticated and not allow_fresh_login_page:
            return _portal_hint_home_response(
                request,
                user=request.user,
                portal_hint=portal_hint,
            )
        _clear_pending_privileged_login(request)
        return super().get(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["audience"] = self._portal_hint()
        context["cbt_microphone_required"] = bool(
            getattr(settings, "CBT_MICROPHONE_REQUIRED", False)
        )
        return context

    def _portal_hint(self):
        hint = (
            self.request.GET.get("audience", "")
            or self.request.POST.get("audience", "")
        ).strip().lower()
        if hint:
            return hint
        next_url = (self.request.GET.get("next", "") or "").strip().lower()
        if not next_url:
            next_url = (self.request.POST.get("next", "") or "").strip().lower()
        referer = (self.request.META.get("HTTP_REFERER") or "").strip().lower()
        host = (self.request.get_host() or "").strip().lower()
        path = (self.request.path or "").strip().lower()
        if (
            "/portal/cbt" in next_url
            or "/cbt/" in next_url
            or "/portal/cbt" in referer
            or "/cbt/" in referer
            or "cbt." in host
            or path.startswith("/portal/cbt/")
        ):
            return "cbt"
        return getattr(self.request, "portal_key", "landing")

    def _staff_login_url(self):
        return build_portal_url(
            self.request,
            "staff",
            reverse("accounts:login"),
            query={"audience": "staff"},
        )

    def _student_login_url(self):
        return build_portal_url(
            self.request,
            "student",
            reverse("accounts:login"),
            query={"audience": "student"},
        )

    def form_valid(self, form):
        user = form.get_user()
        portal_hint = self._portal_hint()
        if portal_hint == "student" and not user.has_role(ROLE_STUDENT):
            messages.error(
                self.request,
                "Staff/Admin accounts must sign in from the Staff Portal.",
            )
            return redirect(self._staff_login_url())
        if portal_hint in {"staff", "dean", "form", "it", "vp", "principal", "bursar"} and user.has_role(ROLE_STUDENT):
            messages.error(
                self.request,
                "Student accounts must sign in from the Student Portal.",
            )
            return redirect(self._student_login_url())
        if (
            portal_hint == "cbt"
            and not user.has_role(ROLE_STUDENT)
            and not user.has_role(ROLE_IT_MANAGER)
            and not user.is_superuser
        ):
            messages.error(
                self.request,
                "Only students and IT Manager accounts can sign in from the CBT Portal. Staff must use the Staff Portal.",
            )
            return redirect(self._staff_login_url())
        if (
            portal_hint == "cbt"
            and user.has_role(ROLE_STUDENT)
            and getattr(settings, "CBT_MICROPHONE_REQUIRED", False)
            and not _has_fresh_cbt_microphone_permission(self.request)
        ):
            form.add_error(
                None,
                "Microphone permission is required before a student can enter the CBT portal. Allow the microphone and try again.",
            )
            return self.form_invalid(form)
        if portal_hint == "cbt" and user.has_role(ROLE_STUDENT):
            from apps.cbt.models import ExamAttempt

            cooldown_remaining = _cbt_login_cooldown_remaining(user.id)
            if cooldown_remaining > 0:
                return render(
                    self.request,
                    "accounts/cbt_login_cooldown.html",
                    {
                        "remaining_seconds": cooldown_remaining,
                        "login_url": self.request.get_full_path(),
                    },
                    status=429,
                )

            now = timezone.now()
            latest_locked = (
                ExamAttempt.objects.filter(
                    student=user,
                    is_locked=True,
                    status="IN_PROGRESS",
                    exam__status="ACTIVE",
                )
                .filter(
                    Q(exam__open_now=True, exam__schedule_end__isnull=True)
                    | Q(exam__open_now=True, exam__schedule_end__gte=now)
                    | Q(exam__schedule_start__lte=now, exam__schedule_end__gte=now)
                )
                .exclude(locked_at=None)
                .order_by("-locked_at")
                .first()
            )
            if latest_locked and latest_locked.locked_at:
                served_key = _cbt_lock_cooldown_served_cache_key(latest_locked.id)
                if not cache.get(served_key):
                    cache.set(served_key, True, timeout=12 * 60 * 60)
                    cooldown_until = timezone.now().timestamp() + CBT_LOGIN_COOLDOWN_SECONDS
                    cache.set(
                        _cbt_login_cooldown_cache_key(user.id),
                        cooldown_until,
                        timeout=CBT_LOGIN_COOLDOWN_SECONDS,
                    )
                    return render(
                        self.request,
                        "accounts/cbt_login_cooldown.html",
                        {
                            "remaining_seconds": CBT_LOGIN_COOLDOWN_SECONDS,
                            "login_url": self.request.get_full_path(),
                        },
                        status=429,
                    )

        next_url = self.request.POST.get("next") or self.request.GET.get("next", "")
        if requires_two_factor(user):
            try:
                challenge = _begin_privileged_login_challenge(
                    self.request,
                    user=user,
                    portal_hint=portal_hint,
                    next_url=next_url,
                    clear_login_code=form.used_login_code,
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
                return self.form_invalid(form)
            except Exception:
                logger.exception("Unable to issue privileged login challenge.")
                form.add_error(
                    None,
                    "Could not deliver the verification code right now. Try again shortly.",
                )
                return self.form_invalid(form)
            log_event(
                category=AuditCategory.AUTH,
                event_type="LOGIN_2FA_CHALLENGE_SENT",
                status=AuditStatus.SUCCESS,
                actor=user,
                request=self.request,
                metadata={
                    "portal_hint": portal_hint,
                    "delivery": challenge["masked_email"],
                },
            )
            messages.info(
                self.request,
                f"Verification code sent to {challenge['masked_email']}. Enter it to finish sign-in.",
            )
            return redirect("accounts:login-verify")

        return _complete_login_response(
            self.request,
            user=user,
            portal_hint=portal_hint,
            next_url=next_url,
            clear_login_code=form.used_login_code,
        )


@method_decorator(never_cache, name="dispatch")
class PrivilegedLoginVerifyView(FormView):
    template_name = "accounts/login_two_factor.html"
    form_class = PrivilegedTwoFactorForm
    pending_user = None
    pending_challenge = None

    def dispatch(self, request, *args, **kwargs):
        self.pending_challenge = request.session.get(PRIVILEGED_LOGIN_SESSION_KEY) or {}
        user_id = self.pending_challenge.get("user_id")
        challenge_id = self.pending_challenge.get("challenge_id")
        if not user_id or not challenge_id:
            messages.error(request, "Start sign-in again to continue.")
            return redirect("accounts:login")
        self.pending_user = User.objects.filter(id=user_id).first()
        if not self.pending_user:
            _clear_pending_privileged_login(request)
            messages.error(request, "Your verification step expired. Sign in again.")
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["masked_email"] = self.pending_challenge.get("masked_email", "")
        context["audience"] = self.pending_challenge.get("portal_hint", "")
        return context

    def post(self, request, *args, **kwargs):
        if (request.POST.get("action") or "").strip().lower() == "resend":
            return self._resend_code()
        return super().post(request, *args, **kwargs)

    def _resend_code(self):
        try:
            challenge = _begin_privileged_login_challenge(
                self.request,
                user=self.pending_user,
                portal_hint=self.pending_challenge.get("portal_hint", "staff"),
                next_url=self.pending_challenge.get("next_url", ""),
                clear_login_code=bool(self.pending_challenge.get("clear_login_code")),
            )
        except Exception:
            logger.exception("Unable to resend privileged login challenge.")
            messages.error(
                self.request,
                "Could not resend the verification code right now. Try again shortly.",
            )
            return redirect("accounts:login-verify")
        log_event(
            category=AuditCategory.AUTH,
            event_type="LOGIN_2FA_CHALLENGE_RESENT",
            status=AuditStatus.SUCCESS,
            actor=self.pending_user,
            request=self.request,
            metadata={"delivery": challenge["masked_email"]},
        )
        messages.success(
            self.request,
            f"A new verification code has been sent to {challenge['masked_email']}.",
        )
        return redirect("accounts:login-verify")

    def form_valid(self, form):
        code = form.cleaned_data["verification_code"]
        if not verify_privileged_login_challenge(
            challenge_id=self.pending_challenge.get("challenge_id"),
            user=self.pending_user,
            raw_code=code,
        ):
            log_event(
                category=AuditCategory.AUTH,
                event_type="LOGIN_2FA_FAILED",
                status=AuditStatus.DENIED,
                actor=self.pending_user,
                request=self.request,
            )
            form.add_error(None, "Invalid or expired verification code.")
            return self.form_invalid(form)

        challenge = _clear_pending_privileged_login(self.request)
        log_event(
            category=AuditCategory.AUTH,
            event_type="LOGIN_2FA_VERIFIED",
            status=AuditStatus.SUCCESS,
            actor=self.pending_user,
            request=self.request,
            metadata={"portal_hint": challenge.get("portal_hint", "")},
        )
        return _complete_login_response(
            self.request,
            user=self.pending_user,
            portal_hint=challenge.get("portal_hint", "staff"),
            next_url=challenge.get("next_url", ""),
            clear_login_code=bool(challenge.get("clear_login_code")),
            backend=challenge.get("backend", ""),
        )


class LogoutView(RedirectView):
    permanent = False

    def _default_login_audience(self):
        if self.request.user.is_authenticated:
            primary_role = getattr(self.request.user, "primary_role", None)
            if primary_role is not None and ROLE_HOME_PORTAL.get(primary_role.code) != "student":
                return "staff"
        return "student"

    def _redirect_target(self):
        portal_key = (
            self.request.session.get("last_authenticated_portal", "")
            or getattr(self.request, "portal_key", "")
        )
        portal_map = {
            "cbt": ("cbt", "cbt"),
            "election": ("election", "election"),
            "student": ("student", "student"),
            "staff": ("staff", "staff"),
            "dean": ("dean", "dean"),
            "form": ("form", "form"),
            "it": ("it", "staff"),
            "bursar": ("bursar", "staff"),
            "vp": ("vp", "staff"),
            "principal": ("principal", "staff"),
        }
        if portal_key in portal_map:
            target_portal, audience = portal_map[portal_key]
            return build_portal_url(
                self.request,
                target_portal,
                reverse("accounts:login"),
                query={"audience": audience},
            )
        return self.request.build_absolute_uri(
            f"{reverse('accounts:login')}?audience={self._default_login_audience()}"
        )

    def _perform_logout(self):
        if self.request.user.is_authenticated:
            session_key = self.request.session.session_key or ""
            active_session_key = _cbt_active_session_cache_key(self.request.user.id)
            if cache.get(active_session_key) == session_key:
                cache.delete(active_session_key)
            finalized_attempts = 0
            if getattr(self.request, "portal_key", "") == "cbt":
                finalized_attempts = finalize_cbt_attempts_on_logout(self.request.user)
                if finalized_attempts:
                    log_event(
                        category=AuditCategory.CBT,
                        event_type="CBT_ATTEMPTS_FINALIZED_ON_LOGOUT",
                        status=AuditStatus.SUCCESS,
                        actor=self.request.user,
                        request=self.request,
                        metadata={"attempts_finalized": finalized_attempts},
                    )
            log_event(
                category=AuditCategory.AUTH,
                event_type="LOGOUT_SUCCESS",
                status=AuditStatus.SUCCESS,
                actor=self.request.user,
                request=self.request,
            )
        logout(self.request)

    def get(self, request, *args, **kwargs):
        target = self._redirect_target()
        self._perform_logout()
        return redirect(target)

    def post(self, request, *args, **kwargs):
        target = self._redirect_target()
        self._perform_logout()
        return redirect(target)


class RoleRedirectView(LoginRequiredMixin, RedirectView):
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return resolve_role_home_url(self.request.user, request=self.request)


class PasswordChangeView(LoginRequiredMixin, FormView):
    template_name = "accounts/password_change.html"
    form_class = PolicyPasswordChangeForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        user = form.user
        apply_self_service_password_change(user, form.cleaned_data["new_password1"])
        update_session_auth_hash(self.request, user)
        log_password_change(actor=user, request=self.request)
        messages.success(self.request, "Password updated successfully.")
        return redirect("accounts:role-redirect")

    def form_invalid(self, form):
        if form.non_field_errors():
            log_password_change_denied(
                actor=self.request.user,
                request=self.request,
                reason="; ".join(form.non_field_errors()),
            )
        return super().form_invalid(form)


class PasswordResetRequestView(FormView):
    template_name = "accounts/password_reset_request.html"
    form_class = PasswordResetRequestForm
    session_key = "pending_password_reset_user_id"

    def form_valid(self, form):
        target_user = form.get_user()
        reset_code = target_user.set_login_code(ttl_hours=1)
        target_user.save(update_fields=["login_code_hash", "login_code_expires_at"])
        send_mail(
            subject="NDGA Password Reset Code",
            message=(
                f"Hello {target_user.get_full_name() or target_user.username},\n\n"
                f"Your NDGA password reset code is: {reset_code}\n"
                "This code expires in 1 hour."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@ndgakuje.org"),
            recipient_list=[target_user.email],
            fail_silently=False,
        )
        self.request.session[self.session_key] = str(target_user.id)
        log_event(
            category=AuditCategory.AUTH,
            event_type="PASSWORD_RESET_CODE_SENT",
            status=AuditStatus.SUCCESS,
            actor=target_user,
            request=self.request,
            metadata={"recovery_email": target_user.email},
        )
        messages.success(
            self.request,
            "Reset code sent to your recovery email.",
        )
        return redirect("accounts:password-reset-confirm")

    def form_invalid(self, form):
        login_id = form.data.get("login_id", "")
        log_event(
            category=AuditCategory.AUTH,
            event_type="PASSWORD_RESET_REQUEST_FAILED",
            status=AuditStatus.DENIED,
            actor_identifier=login_id,
            request=self.request,
            message="Password reset request failed.",
        )
        return super().form_invalid(form)


class PasswordResetConfirmView(FormView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = PasswordResetCodeForm
    session_key = "pending_password_reset_user_id"
    target_user = None

    def dispatch(self, request, *args, **kwargs):
        user_id = request.session.get(self.session_key)
        if not user_id:
            messages.error(request, "Start password reset request first.")
            return redirect("accounts:password-reset-request")
        self.target_user = User.objects.filter(id=user_id).first()
        if not self.target_user:
            request.session.pop(self.session_key, None)
            messages.error(request, "Password reset request expired. Start again.")
            return redirect("accounts:password-reset-request")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.target_user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_login_id"] = self.target_user.username
        return context

    def form_valid(self, form):
        user = form.save()
        self.request.session.pop(self.session_key, None)
        log_event(
            category=AuditCategory.AUTH,
            event_type="PASSWORD_RESET_COMPLETED",
            status=AuditStatus.SUCCESS,
            actor=user,
            request=self.request,
        )
        messages.success(self.request, "Password reset completed. You can now sign in.")
        return redirect("accounts:login")


class ITCredentialResetView(LoginRequiredMixin, UserPassesTestMixin, FormView):
    template_name = "accounts/it_reset_credentials.html"
    form_class = ITCredentialResetForm
    generated_code = None

    def test_func(self):
        return has_scope(self.request.user, SCOPE_ISSUE_LOGIN_CODES)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["actor"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["generated_code"] = self.generated_code
        return context

    def form_valid(self, form):
        target_user = form.cleaned_data["target_user"]
        reset_mode = form.cleaned_data["reset_mode"]
        if reset_mode == ITCredentialResetForm.RESET_MODE_LOGIN_CODE:
            self.generated_code = issue_login_code(self.request.user, target_user)
            messages.success(self.request, "One-time login code issued.")
        else:
            temporary_password = form.cleaned_data["temporary_password"]
            reset_password_by_it_manager(
                self.request.user,
                target_user,
                temporary_password,
            )
            messages.success(self.request, "Temporary password reset completed.")
        log_credentials_reset(
            actor=self.request.user,
            target_user=target_user,
            request=self.request,
            reset_mode=reset_mode,
        )
        return self.render_to_response(self.get_context_data(form=form))


class ITUserProvisioningView(LoginRequiredMixin, UserPassesTestMixin, RedirectView):
    permanent = False

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def get_redirect_url(self, *args, **kwargs):
        return reverse("accounts:it-staff-directory")


class ITMobileCaptureSessionView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if not self.test_func():
            return HttpResponseBadRequest("Permission denied.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        token = _build_mobile_capture_token(actor_id=request.user.id)
        capture_path = reverse("accounts:mobile-capture-start", kwargs={"token": token})
        capture_url = _mobile_capture_public_url(
            request,
            portal_key=getattr(request, "portal_key", "it"),
            capture_path=capture_path,
        )
        cache.delete(_mobile_capture_cache_key(token))
        try:
            qr_data_url = qr_code_data_uri(capture_url)
        except RuntimeError:
            qr_data_url = ""
        return JsonResponse(
            {
                "ok": True,
                "token": token,
                "capture_url": capture_url,
                "qr_data_url": qr_data_url,
                "expires_seconds": MOBILE_CAPTURE_TOKEN_MAX_AGE_SECONDS,
            }
        )


class ITMobileCaptureStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if not self.test_func():
            return HttpResponseBadRequest("Permission denied.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        token = (request.GET.get("token") or "").strip()
        if not token:
            return JsonResponse({"ok": False, "error": "Missing token."}, status=400)
        try:
            payload = _read_mobile_capture_token(token)
        except signing.BadSignature:
            return JsonResponse({"ok": False, "error": "Invalid capture token."}, status=400)
        except signing.SignatureExpired:
            return JsonResponse({"ok": False, "error": "Capture token expired."}, status=400)

        if int(payload.get("actor_id") or 0) != int(request.user.id):
            return JsonResponse({"ok": False, "error": "Token does not belong to this user."}, status=403)

        capture_payload = cache.get(_mobile_capture_cache_key(token)) or {}
        return JsonResponse(
            {
                "ok": True,
                "ready": bool(capture_payload.get("data_url")),
                "data_url": capture_payload.get("data_url", ""),
                "captured_at": capture_payload.get("captured_at", ""),
            }
        )


class MobileCaptureStartView(TemplateView):
    template_name = "accounts/mobile_capture_start.html"

    def dispatch(self, request, *args, **kwargs):
        token = kwargs.get("token", "")
        try:
            _read_mobile_capture_token(token)
        except signing.BadSignature:
            return HttpResponseBadRequest("Invalid capture link.")
        except signing.SignatureExpired:
            return HttpResponseBadRequest("Capture link has expired.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["token"] = kwargs.get("token", "")
        context["submit_url"] = reverse("accounts:mobile-capture-submit", kwargs={"token": context["token"]})
        return context


@method_decorator(csrf_exempt, name="dispatch")
class MobileCaptureSubmitView(View):
    def post(self, request, *args, **kwargs):
        token = kwargs.get("token", "")
        try:
            _read_mobile_capture_token(token)
        except signing.BadSignature:
            return HttpResponseBadRequest("Invalid capture link.")
        except signing.SignatureExpired:
            return HttpResponseBadRequest("Capture link has expired.")
        try:
            upload = request.FILES.get("photo")
        except RequestDataTooBig:
            return HttpResponseBadRequest(_friendly_upload_limit_message())
        if not upload:
            return HttpResponseBadRequest("No photo uploaded.")
        try:
            validate_image_upload(upload)
        except ValidationError as exc:
            return HttpResponseBadRequest("; ".join(exc.messages))

        content_type = (getattr(upload, "content_type", "") or "image/jpeg").lower()
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"

        upload.seek(0)
        image_bytes = upload.read()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{content_type};base64,{encoded}"

        cache.set(
            _mobile_capture_cache_key(token),
            {
                "data_url": data_url,
                "captured_at": timezone.now().isoformat(),
            },
            timeout=MOBILE_CAPTURE_CACHE_TTL_SECONDS,
        )

        return JsonResponse({"ok": True, "message": "Photo uploaded. You can return to laptop now."})


class ITProvisioningBaseView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    generated_session_key = ""
    PAGE_SIZE_OPTIONS = (5, 10, 25, 50)

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def _latest_staff(self):
        from apps.academics.models import TeacherSubjectAssignment

        query = (
            User.objects.select_related("primary_role", "staff_profile")
            .prefetch_related(
                Prefetch(
                    "subject_assignments",
                    queryset=TeacherSubjectAssignment.objects.filter(is_active=True).select_related(
                        "academic_class",
                        "subject",
                        "session",
                        "term",
                    ).order_by("academic_class__code", "subject__name"),
                    to_attr="active_subject_loads",
                )
            )
            .filter(staff_profile__isnull=False)
            .exclude(username=settings.ANONYMOUS_USER_NAME)
            .exclude(primary_role__code__in=[ROLE_BURSAR, ROLE_VP, ROLE_PRINCIPAL, ROLE_IT_MANAGER])
        )
        search = self.request.GET.get("q", "").strip()
        role_code = self.request.GET.get("role", "").strip()
        status = self.request.GET.get("status", "").strip()
        employment_status = self.request.GET.get("employment_status", "").strip().upper()
        if search:
            query = query.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(staff_profile__staff_id__icontains=search)
                | Q(subject_assignments__subject__name__icontains=search)
                | Q(subject_assignments__subject__code__icontains=search)
                | Q(subject_assignments__academic_class__code__icontains=search)
                | Q(subject_assignments__academic_class__display_name__icontains=search)
            )
        if role_code:
            query = query.filter(primary_role__code=role_code)
        if status == "active":
            query = query.filter(is_active=True)
        elif status == "inactive":
            query = query.filter(is_active=False)
        if employment_status:
            query = query.filter(staff_profile__employment_status=employment_status)
        return query.distinct().order_by("first_name", "last_name", "staff_profile__staff_id", "username")

    def _latest_students(self):
        query = (
            User.objects.select_related("primary_role", "student_profile")
            .prefetch_related("class_enrollments__academic_class")
            .filter(primary_role__code="STUDENT")
            .exclude(username=settings.ANONYMOUS_USER_NAME)
        )
        search = self.request.GET.get("q", "").strip()
        admission_no = self.request.GET.get("admission_no", "").strip()
        status = self.request.GET.get("status", "").strip()
        lifecycle = self.request.GET.get("lifecycle", "").strip().upper()
        class_id = self.request.GET.get("class_id", "").strip()
        if search:
            query = query.filter(
                Q(username__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(student_profile__student_number__icontains=search)
            )
        if admission_no:
            query = query.filter(student_profile__student_number__icontains=admission_no)
        if status == "active":
            query = query.filter(is_active=True)
        elif status == "inactive":
            query = query.filter(is_active=False)
        if lifecycle:
            query = query.filter(student_profile__lifecycle_state=lifecycle)
        if class_id.isdigit():
            query = query.filter(class_enrollments__academic_class_id=int(class_id), class_enrollments__is_active=True)
        return query.distinct().order_by(
            "first_name",
            "last_name",
            "student_profile__middle_name",
            "student_profile__student_number",
            "username",
        )

    def _pull_generated_credentials(self):
        if not self.generated_session_key:
            return None
        return self.request.session.pop(self.generated_session_key, None)

    def _resolve_page_size(self, raw_value):
        value = (raw_value or "").strip().lower()
        if value == "all":
            return "all"
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return self.PAGE_SIZE_OPTIONS[0]
        if parsed in self.PAGE_SIZE_OPTIONS:
            return parsed
        return self.PAGE_SIZE_OPTIONS[0]

    def _paginate_queryset(self, queryset, *, page_param="page", page_size_param="page_size"):
        page_size = self._resolve_page_size(self.request.GET.get(page_size_param))
        if page_size == "all":
            return {
                "rows": list(queryset),
                "page_obj": None,
                "paginator": None,
                "page_size": "all",
                "page_size_options": self.PAGE_SIZE_OPTIONS,
            }
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(self.request.GET.get(page_param) or 1)
        return {
            "rows": list(page_obj.object_list),
            "page_obj": page_obj,
            "paginator": paginator,
            "page_size": page_size,
            "page_size_options": self.PAGE_SIZE_OPTIONS,
        }

    def _query_string_without(self, *keys):
        query = self.request.GET.copy()
        for key in keys:
            if key in query:
                query.pop(key)
        return query.urlencode()


class ITStaffProvisioningView(ITProvisioningBaseView):
    template_name = "accounts/it_staff_registration.html"
    generated_session_key = "generated_staff_credentials"

    def _staff_form(self, data=None, files=None):
        return ITStaffRegistrationForm(actor=self.request.user, data=data, files=files)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["staff_form"] = kwargs.get("staff_form") or self._staff_form()
        context["generated_staff_credentials"] = self._pull_generated_credentials()
        context["staff_management_url"] = reverse("accounts:it-staff-directory")
        return context

    def post(self, request, *args, **kwargs):
        try:
            form = self._staff_form(request.POST, request.FILES)
        except RequestDataTooBig:
            messages.error(request, _friendly_upload_limit_message())
            return self.render_to_response(self.get_context_data(staff_form=self._staff_form()))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(staff_form=form))

        with transaction.atomic():
            user, password, staff_id = form.save()

        self.request.session[self.generated_session_key] = {
            "username": user.username,
            "staff_id": staff_id,
            "password": password,
        }
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="STAFF_USER_REGISTERED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "user_id": str(user.id),
                "username": user.username,
                "primary_role": user.primary_role.code if user.primary_role_id else "",
            },
        )
        messages.success(request, "Staff account created successfully.")
        return redirect("accounts:it-staff-provisioning")


class ITStaffDirectoryView(ITProvisioningBaseView):
    template_name = "accounts/it_staff_directory.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        paginated = self._paginate_queryset(self._latest_staff())
        context["latest_staff"] = paginated["rows"]
        context["total_staff"] = self._latest_staff().count()
        context["staff_page_obj"] = paginated["page_obj"]
        context["staff_page_size"] = paginated["page_size"]
        context["staff_page_size_options"] = paginated["page_size_options"]
        context["staff_list_base_query"] = self._query_string_without("page")
        context["role_filter_options"] = (
            self._latest_staff().values_list("primary_role__code", flat=True).distinct().order_by("primary_role__code")
        )
        context["search_query"] = self.request.GET.get("q", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["role_filter"] = self.request.GET.get("role", "")
        context["employment_status_filter"] = self.request.GET.get("employment_status", "")
        context["employment_status_options"] = StaffProfile.LifecycleState.choices
        context["staff_create_url"] = reverse("accounts:it-staff-provisioning")
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip()
        if action != "reset_staff_password":
            messages.error(request, "Unknown staff management action.")
            return redirect("accounts:it-staff-directory")
        target_user = get_object_or_404(
            User.objects.select_related("staff_profile", "primary_role"),
            pk=request.POST.get("user_id"),
            staff_profile__isnull=False,
        )
        if target_user.primary_role_id and target_user.primary_role.code in {ROLE_IT_MANAGER}:
            messages.error(request, "This account is managed by the bootstrap command.")
            return redirect(request.POST.get("next") or "accounts:it-staff-directory")
        login_hint = target_user.staff_profile.staff_id or target_user.username
        generated_password = set_user_password_from_login_id(target_user, login_hint)
        target_user.password_changed_count = 0
        target_user.must_change_password = False
        target_user.clear_login_code()
        target_user.save(
            update_fields=[
                "password",
                "password_changed_count",
                "must_change_password",
                "login_code_hash",
                "login_code_expires_at",
            ]
        )
        log_credentials_reset(
            actor=request.user,
            target_user=target_user,
            request=request,
            reset_mode="DIRECT_PASSWORD",
        )
        messages.success(
            request,
            f"Password reset for {target_user.get_full_name() or target_user.username}. New password: {generated_password}",
        )
        return redirect(request.POST.get("next") or "accounts:it-staff-directory")


class ITStudentProvisioningView(ITProvisioningBaseView):
    template_name = "accounts/it_student_registration.html"
    generated_session_key = "generated_student_credentials"

    def _student_form(self, data=None, files=None):
        return ITStudentRegistrationForm(actor=self.request.user, data=data, files=files)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student_form"] = kwargs.get("student_form") or self._student_form()
        context["generated_student_credentials"] = self._pull_generated_credentials()
        context["student_management_url"] = reverse("accounts:it-student-directory")
        return context

    def post(self, request, *args, **kwargs):
        try:
            form = self._student_form(request.POST, request.FILES)
        except RequestDataTooBig:
            messages.error(request, _friendly_upload_limit_message())
            return self.render_to_response(self.get_context_data(student_form=self._student_form()))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(student_form=form))

        with transaction.atomic():
            user, password, student_number = form.save()

        try:
            queue_student_registration_sync(user=user, raw_password=password)
        except (OperationalError, ProgrammingError, ValidationError) as exc:
            logger.warning("Skipped student registration sync queue: %s", exc)

        self.request.session[self.generated_session_key] = {
            "username": user.username,
            "student_number": student_number,
            "password": password,
        }
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="STUDENT_USER_REGISTERED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "user_id": str(user.id),
                "username": user.username,
            },
        )
        messages.success(request, "Student account created successfully.")
        return redirect("accounts:it-student-provisioning")


class ITStudentDirectoryView(ITProvisioningBaseView):
    template_name = "accounts/it_student_directory.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        paginated = self._paginate_queryset(self._latest_students())
        student_rows = []
        for user in paginated["rows"]:
            active_enrollment = next(
                (row for row in user.class_enrollments.all() if row.is_active),
                None,
            )
            student_rows.append(
                {
                    "user": user,
                    "class_code": (
                        active_enrollment.academic_class.code
                        if active_enrollment and active_enrollment.academic_class_id
                        else "-"
                    ),
                }
            )
        context["student_rows"] = student_rows
        context["total_students"] = self._latest_students().count()
        context["student_page_obj"] = paginated["page_obj"]
        context["student_page_size"] = paginated["page_size"]
        context["student_page_size_options"] = paginated["page_size_options"]
        context["student_list_base_query"] = self._query_string_without("page")
        context["search_query"] = self.request.GET.get("q", "")
        context["admission_no_filter"] = self.request.GET.get("admission_no", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["lifecycle_filter"] = self.request.GET.get("lifecycle", "")
        context["lifecycle_options"] = StudentProfile.LifecycleState.choices
        context["class_filter"] = self.request.GET.get("class_id", "")
        context["class_filter_options"] = (
            self._latest_students()
            .values_list(
                "class_enrollments__academic_class__id",
                "class_enrollments__academic_class__code",
            )
            .distinct()
            .order_by("class_enrollments__academic_class__code")
        )
        context["student_create_url"] = reverse("accounts:it-student-provisioning")
        return context


class ITStaffDetailView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/it_staff_detail.html"

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(
            User.objects.select_related("staff_profile", "primary_role"),
            pk=kwargs["user_id"],
            staff_profile__isnull=False,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from apps.academics.models import FormTeacherAssignment, TeacherSubjectAssignment
        from apps.dashboard.intelligence import build_teacher_performance_analytics
        from apps.results.analytics import build_teacher_ranking
        from apps.results.models import ResultSheet, ResultSheetStatus
        from apps.setup_wizard.services import get_setup_state

        context = super().get_context_data(**kwargs)
        setup_state = get_setup_state()
        subject_assignments = TeacherSubjectAssignment.objects.filter(teacher=self.target_user, is_active=True).select_related(
            "academic_class", "subject", "session", "term"
        )
        current_subject_assignments = subject_assignments
        if setup_state.current_session_id and setup_state.current_term_id:
            current_subject_assignments = current_subject_assignments.filter(
                session=setup_state.current_session,
                term=setup_state.current_term,
            )
        elif setup_state.current_session_id:
            current_subject_assignments = current_subject_assignments.filter(session=setup_state.current_session)
        else:
            current_subject_assignments = TeacherSubjectAssignment.objects.none()
        form_assignments = FormTeacherAssignment.objects.filter(teacher=self.target_user, is_active=True).select_related(
            "academic_class", "session"
        )
        current_form_assignments = form_assignments
        if setup_state.current_session_id:
            current_form_assignments = current_form_assignments.filter(session=setup_state.current_session)
        else:
            current_form_assignments = FormTeacherAssignment.objects.none()
        analytics = build_teacher_performance_analytics(
            teacher=self.target_user,
            current_session=setup_state.current_session,
            current_term=setup_state.current_term,
        )
        sheet_qs = ResultSheet.objects.none()
        if setup_state.current_session_id and setup_state.current_term_id:
            pair_filter = Q(pk__in=[])
            for row in current_subject_assignments:
                pair_filter |= Q(academic_class_id=row.academic_class_id, subject_id=row.subject_id)
            sheet_qs = ResultSheet.objects.filter(pair_filter, session=setup_state.current_session, term=setup_state.current_term)
        context["target_user"] = self.target_user
        context["subject_assignments"] = current_subject_assignments.order_by("academic_class__code", "subject__name")
        context["form_assignments"] = current_form_assignments.order_by("academic_class__code")
        context["teacher_analytics"] = analytics
        context["result_status_counts"] = {
            "draft": sheet_qs.filter(status=ResultSheetStatus.DRAFT).count(),
            "submitted": sheet_qs.filter(status=ResultSheetStatus.SUBMITTED_TO_DEAN).count(),
            "published": sheet_qs.filter(status=ResultSheetStatus.PUBLISHED).count(),
        }
        teacher_rank_row = None
        if setup_state.current_session_id and setup_state.current_term_id:
            for row in build_teacher_ranking(session=setup_state.current_session, term=setup_state.current_term).get("rows", []):
                if row["teacher"].id == self.target_user.id:
                    teacher_rank_row = row
                    break
        context["teacher_rank_row"] = teacher_rank_row
        context["result_sheet_rows"] = list(
            sheet_qs.select_related("academic_class", "subject").order_by("academic_class__code", "subject__name")
        )
        return context


class ITStudentDetailView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/it_student_detail.html"

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(
            User.objects.select_related("student_profile", "primary_role"),
            pk=kwargs["user_id"],
            primary_role__code=ROLE_STUDENT,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from decimal import Decimal
        from django.db.models import Sum

        from apps.academics.models import StudentClassEnrollment, StudentSubjectEnrollment
        from apps.attendance.services import get_current_student_attendance_snapshot
        from apps.dashboard.intelligence import build_student_academic_analytics
        from apps.dashboard.models import StudentClubMembership
        from apps.finance.models import ChargeTargetType, Payment, StudentCharge
        from apps.results.models import ClassCompilationStatus, ClassResultCompilation
        from apps.setup_wizard.services import get_setup_state

        context = super().get_context_data(**kwargs)
        setup_state = get_setup_state()
        current_enrollment = None
        if setup_state.current_session_id:
            current_enrollment = StudentClassEnrollment.objects.select_related("academic_class").filter(
                student=self.target_user,
                session=setup_state.current_session,
                is_active=True,
            ).first()
        offered_subjects = StudentSubjectEnrollment.objects.filter(
            student=self.target_user,
            session=setup_state.current_session,
            is_active=True,
        ).select_related("subject").order_by("subject__name") if setup_state.current_session_id else StudentSubjectEnrollment.objects.none()
        club_memberships = StudentClubMembership.objects.filter(student=self.target_user, is_active=True).select_related("club", "session").order_by("-session__name", "club__name")
        published_compilations = ClassResultCompilation.objects.filter(
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=self.target_user,
        ).select_related("academic_class", "session", "term").distinct().order_by("-session__name", "-published_at")
        attendance_snapshot = get_current_student_attendance_snapshot(self.target_user)

        charge_qs = StudentCharge.objects.filter(student=self.target_user, is_active=True)
        if current_enrollment is not None:
            charge_qs = charge_qs | StudentCharge.objects.filter(
                target_type=ChargeTargetType.CLASS,
                academic_class=current_enrollment.academic_class,
                is_active=True,
            )
        total_charged = charge_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        payment_qs = Payment.objects.filter(student=self.target_user, is_void=False)
        total_paid = payment_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        context["target_user"] = self.target_user
        context["current_enrollment"] = current_enrollment
        context["offered_subjects"] = offered_subjects
        context["club_memberships"] = club_memberships
        context["published_compilations"] = published_compilations[:8]
        context["attendance_snapshot"] = attendance_snapshot
        context["finance_snapshot"] = {
            "charged": total_charged,
            "paid": total_paid,
            "outstanding": max(total_charged - total_paid, Decimal("0.00")),
        }
        context["student_analytics"] = build_student_academic_analytics(
            student=self.target_user,
            current_session=setup_state.current_session,
            current_term=setup_state.current_term,
        )
        return context


class ITStudentPasswordResetView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/it_student_password_reset.html"

    def test_func(self):
        return has_scope(self.request.user, SCOPE_ISSUE_LOGIN_CODES)

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(
            User.objects.select_related("student_profile", "primary_role"),
            pk=kwargs["user_id"],
            primary_role__code=ROLE_STUDENT,
        )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["target_user"] = self.target_user
        return context

    def post(self, request, *args, **kwargs):
        new_password = request.POST.get("new_password") or ""
        confirm_password = request.POST.get("confirm_password") or ""
        if not new_password:
            messages.error(request, "Enter the student's new password.")
            return self.render_to_response(self.get_context_data())
        if new_password != confirm_password:
            messages.error(request, "The two password entries do not match.")
            return self.render_to_response(self.get_context_data())

        reset_password_by_it_manager(
            request.user,
            self.target_user,
            new_password,
        )
        log_credentials_reset(
            actor=request.user,
            target_user=self.target_user,
            request=request,
            reset_mode=ITCredentialResetForm.RESET_MODE_PASSWORD,
        )
        messages.success(
            request,
            f"Password changed for {self.target_user.student_profile.student_number}.",
        )
        return redirect("accounts:it-student-detail", user_id=self.target_user.id)



class ITStaffEditView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/it_staff_edit.html"

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(
            User.objects.select_related("staff_profile", "primary_role"),
            pk=kwargs["user_id"],
            staff_profile__isnull=False,
        )
        if (
            self.target_user.primary_role_id
            and self.target_user.primary_role.code == ROLE_IT_MANAGER
        ):
            messages.error(
                request,
                "IT Manager account is managed through the bootstrap command only.",
            )
            return redirect("accounts:it-staff-directory")
        return super().dispatch(request, *args, **kwargs)

    def _form(self, data=None, files=None):
        return ITStaffUpdateForm(
            actor=self.request.user,
            user_instance=self.target_user,
            data=data,
            files=files,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["staff_form"] = kwargs.get("staff_form") or self._form()
        context["target_user"] = self.target_user
        return context

    def post(self, request, *args, **kwargs):
        try:
            form = self._form(request.POST, request.FILES)
        except RequestDataTooBig:
            messages.error(request, _friendly_upload_limit_message())
            return self.render_to_response(self.get_context_data(staff_form=self._form()))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(staff_form=form))
        user = form.save()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="STAFF_USER_UPDATED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"user_id": str(user.id), "username": user.username},
        )
        if getattr(form, "generated_password", ""):
            messages.success(
                request,
                f"Staff record updated. Login password reset to {form.generated_password}.",
            )
        else:
            messages.success(request, "Staff record updated.")
        return redirect("accounts:it-staff-directory")


class ITStudentEditView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "accounts/it_student_edit.html"

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.target_user = get_object_or_404(
            User.objects.select_related("student_profile", "primary_role"),
            pk=kwargs["user_id"],
            primary_role__code="STUDENT",
        )
        return super().dispatch(request, *args, **kwargs)

    def _form(self, data=None, files=None):
        return ITStudentUpdateForm(
            actor=self.request.user,
            user_instance=self.target_user,
            data=data,
            files=files,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["student_form"] = kwargs.get("student_form") or self._form()
        context["target_user"] = self.target_user
        return context

    def post(self, request, *args, **kwargs):
        try:
            form = self._form(request.POST, request.FILES)
        except RequestDataTooBig:
            messages.error(request, _friendly_upload_limit_message())
            return self.render_to_response(self.get_context_data(student_form=self._form()))
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(student_form=form))
        user = form.save()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="STUDENT_USER_UPDATED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"user_id": str(user.id), "username": user.username},
        )
        if getattr(form, "generated_password", ""):
            messages.success(
                request,
                f"Student record updated. Login password reset to {form.generated_password}.",
            )
        else:
            messages.success(request, "Student record updated.")
        return redirect("accounts:it-student-directory")


class ITUserStatusToggleView(LoginRequiredMixin, UserPassesTestMixin, RedirectView):
    permanent = False

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def post(self, request, *args, **kwargs):
        target = get_object_or_404(User, pk=kwargs["user_id"])
        default_target = (
            "accounts:it-student-directory"
            if target.primary_role_id and target.primary_role.code == ROLE_STUDENT
            else "accounts:it-staff-directory"
        )
        redirect_target = request.POST.get("next") or default_target
        if target.username == settings.ANONYMOUS_USER_NAME:
            messages.error(request, "System account cannot be modified.")
            return redirect(redirect_target)
        if target.primary_role_id and target.primary_role.code == ROLE_IT_MANAGER:
            messages.error(request, "IT manager account status cannot be toggled from this action.")
            return redirect(redirect_target)
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        student_profile = getattr(target, "student_profile", None)
        if student_profile is not None:
            if target.is_active:
                if student_profile.lifecycle_state == student_profile.LifecycleState.DEACTIVATED:
                    student_profile.lifecycle_state = student_profile.LifecycleState.ACTIVE
            elif student_profile.lifecycle_state == student_profile.LifecycleState.ACTIVE:
                student_profile.lifecycle_state = student_profile.LifecycleState.DEACTIVATED
            student_profile.save(update_fields=["lifecycle_state", "updated_at"])
        staff_profile = getattr(target, "staff_profile", None)
        if staff_profile is not None:
            if target.is_active:
                if staff_profile.employment_status == staff_profile.LifecycleState.DEACTIVATED:
                    staff_profile.employment_status = staff_profile.LifecycleState.ACTIVE
            elif staff_profile.employment_status == staff_profile.LifecycleState.ACTIVE:
                staff_profile.employment_status = staff_profile.LifecycleState.DEACTIVATED
            staff_profile.save(update_fields=["employment_status", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="USER_STATUS_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"user_id": str(target.id), "is_active": target.is_active},
        )
        messages.success(request, "Account status updated.")
        return redirect(redirect_target)


class ITUserDeleteView(LoginRequiredMixin, UserPassesTestMixin, RedirectView):
    permanent = False

    def test_func(self):
        return _can_manage_school_users(self.request.user)

    def post(self, request, *args, **kwargs):
        target = get_object_or_404(User, pk=kwargs["user_id"])
        default_target = (
            "accounts:it-student-directory"
            if target.primary_role_id and target.primary_role.code == ROLE_STUDENT
            else "accounts:it-staff-directory"
        )
        redirect_target = request.POST.get("next") or default_target
        if target.username == settings.ANONYMOUS_USER_NAME:
            messages.error(request, "System account cannot be deleted.")
            return redirect(redirect_target)
        if target.primary_role_id and target.primary_role.code == ROLE_IT_MANAGER:
            messages.error(request, "IT manager account cannot be deleted.")
            return redirect(redirect_target)
        username = target.username
        target.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="USER_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"username": username},
        )
        messages.success(request, "Account deleted.")
        return redirect(redirect_target)
