from urllib.parse import urlencode

from django.contrib import messages
from django.shortcuts import redirect
from django.views.csrf import csrf_failure as django_csrf_failure


def csrf_failure_view(request, reason="", template_name="403_csrf.html"):
    """Handle CSRF failures gracefully for login while preserving strict 403 elsewhere."""
    if request.path.startswith("/auth/login/"):
        params = {}
        audience = (request.GET.get("audience") or "").strip()
        next_url = (request.GET.get("next") or "").strip()
        if audience:
            params["audience"] = audience
        if next_url:
            params["next"] = next_url
        login_url = "/auth/login/"
        if params:
            login_url = f"{login_url}?{urlencode(params)}"
        messages.error(
            request,
            "Security token expired. Reloaded login page. Please sign in again.",
        )
        return redirect(login_url)
    return django_csrf_failure(request, reason=reason, template_name=template_name)

