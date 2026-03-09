from __future__ import annotations

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def healthz(request):
    return JsonResponse({"status": "ok"}, status=200)


def readyz(request):
    checks = {
        "database": False,
        "cache": False,
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception:  # pragma: no cover - runtime dependency check
        checks["database"] = False

    try:
        cache.set("ndga_readyz_ping", "ok", timeout=10)
        checks["cache"] = cache.get("ndga_readyz_ping") == "ok"
    except Exception:  # pragma: no cover - runtime dependency check
        checks["cache"] = False

    healthy = all(checks.values())
    status = 200 if healthy else 503
    payload = {
        "status": "ready" if healthy else "degraded",
        "checks": checks,
    }
    return JsonResponse(payload, status=status)
