import re

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from apps.cbt.models import ExamAttempt


class CBTLockdownMiddleware:
    ATTEMPT_RUN_PATTERN = re.compile(r"^/cbt/attempts/(?P<attempt_id>\d+)/run/$")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", False):
            return self.get_response(request)
        if not getattr(request.user, "is_authenticated", False):
            return self.get_response(request)

        match = self.ATTEMPT_RUN_PATTERN.match(request.path)
        if not match:
            return self.get_response(request)

        attempt_id = match.group("attempt_id")
        attempt = (
            ExamAttempt.objects.filter(id=attempt_id, student=request.user)
            .only("id", "is_locked")
            .first()
        )
        if attempt and attempt.is_locked:
            return redirect(reverse("cbt:student-attempt-locked", args=[attempt.id]))
        response = self.get_response(request)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        response["Pragma"] = "no-cache"
        response["X-Frame-Options"] = "DENY"
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "no-referrer"
        response["Permissions-Policy"] = (
            "camera=(), microphone=(self), geolocation=(), payment=(), usb=(), bluetooth=(), "
            "display-capture=(), window-management=()"
        )
        response["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'; "
            "img-src 'self' data: blob: https:; media-src 'self' blob: https:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; worker-src 'self' blob:"
        )
        return response
