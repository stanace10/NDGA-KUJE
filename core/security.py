from __future__ import annotations

import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import get_client_ip, log_event


class LocalNetworkHostCompatibilityMiddleware:
    """
    Keeps local/LAN HTTP access working even when production HTTPS settings are enabled.

    Public domains continue to use normal HTTPS enforcement, while private IPs and local
    hostnames can be served over plain HTTP for on-prem/LAN access.
    """

    LOCAL_HOSTNAMES = {
        "localhost",
        "127.0.0.1",
        "::1",
        "ndgak.local",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = (request.get_host() or "").split(":", 1)[0].strip("[]").lower()
        is_local_host = self._is_local_host(host)
        request._ndga_local_http_host = is_local_host
        if is_local_host:
            # Pretend the request is already secure so SecurityMiddleware does not
            # bounce local IP/HTTP users to a non-existent HTTPS listener.
            request.META["HTTP_X_FORWARDED_PROTO"] = "https"

        response = self.get_response(request)

        if is_local_host:
            response.headers.pop("Strict-Transport-Security", None)
            for morsel in response.cookies.values():
                morsel["secure"] = False

        return response

    def _is_local_host(self, host: str) -> bool:
        if not host:
            return False
        if host in self.LOCAL_HOSTNAMES or host.endswith(".local"):
            return True
        try:
            return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False


class RequestRateLimitMiddleware:
    """
    Global request throttling for sensitive POST routes.

    Rules are configured via settings.RATE_LIMIT_RULES.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "RATE_LIMIT_ENABLED", False):
            rule = self._match_rule(request)
            if rule is not None:
                allowed = self._consume_quota(request=request, rule=rule)
                if not allowed:
                    self._log_block(request=request, rule=rule)
                    return self._blocked_response(rule=rule)
        return self.get_response(request)

    def _match_rule(self, request):
        request_path = request.path or "/"
        method = (request.method or "GET").upper()
        for rule in getattr(settings, "RATE_LIMIT_RULES", []):
            path_prefix = (rule.get("path_prefix") or "").strip()
            methods = tuple(value.upper() for value in rule.get("methods", ("POST",)))
            if path_prefix and request_path.startswith(path_prefix) and method in methods:
                return rule
        return None

    def _identity_for_rule(self, *, request, rule):
        scope = (rule.get("scope") or "ip").lower()
        if scope in {"user", "user_or_ip"} and getattr(request.user, "is_authenticated", False):
            return f"user:{request.user.id}"
        ip_address = get_client_ip(request) or "unknown"
        return f"ip:{ip_address}"

    def _consume_quota(self, *, request, rule):
        identity = self._identity_for_rule(request=request, rule=rule)
        limit = int(rule.get("limit") or 0)
        window_seconds = int(rule.get("window_seconds") or 60)
        if limit <= 0:
            return True
        cache_key = f"ndga:ratelimit:{rule.get('name', 'rule')}:{identity}"
        created = cache.add(cache_key, 1, timeout=window_seconds)
        if created:
            return True
        try:
            request_count = cache.incr(cache_key)
        except Exception:
            # Cache backends without atomic incr support: fallback best-effort.
            value = cache.get(cache_key, 0) or 0
            request_count = int(value) + 1
            cache.set(cache_key, request_count, timeout=window_seconds)
        return request_count <= limit

    def _blocked_response(self, *, rule):
        retry_after = int(rule.get("window_seconds") or 60)
        response = HttpResponse(
            "Too many requests for this operation. Please retry shortly.",
            status=429,
        )
        response["Retry-After"] = str(retry_after)
        return response

    def _log_block(self, *, request, rule):
        rule_name = rule.get("name", "rate_limit")
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        actor_identifier = ""
        if actor is None:
            actor_identifier = request.POST.get("username", "") or request.POST.get("login_id", "")
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="RATE_LIMIT_BLOCKED",
            status=AuditStatus.DENIED,
            actor=actor,
            actor_identifier=actor_identifier,
            request=request,
            message=f"Rate limit blocked by rule {rule_name}.",
            metadata={
                "rule": rule_name,
                "scope": rule.get("scope", "ip"),
                "limit": rule.get("limit"),
                "window_seconds": rule.get("window_seconds"),
            },
        )


class StrictSecurityHeadersMiddleware:
    """
    Applies strict response headers consistently across portals.
    """

    NO_STORE_PREFIXES = (
        "/auth/",
        "/cbt/",
        "/setup/session-term/",
        "/setup/backup/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        headers = getattr(settings, "SECURITY_RESPONSE_HEADERS", {})
        for header_name, header_value in headers.items():
            if not header_value:
                continue
            if header_name not in response:
                response[header_name] = header_value

        if any(request.path.startswith(prefix) for prefix in self.NO_STORE_PREFIXES):
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"

        return response
