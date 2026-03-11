from __future__ import annotations

from datetime import timedelta
import shutil

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone


def _database_ready():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except Exception:  # pragma: no cover - runtime dependency check
        return False


def _cache_ready():
    try:
        cache.set("ndga_readyz_ping", "ok", timeout=10)
        return cache.get("ndga_readyz_ping") == "ok"
    except Exception:  # pragma: no cover - runtime dependency check
        return False


def collect_ops_runtime_snapshot():
    checks = {
        "database": _database_ready(),
        "cache": _cache_ready(),
    }
    healthy = all(checks.values())
    snapshot = {
        "status": "ready" if healthy else "degraded",
        "checks": checks,
        "generated_at": timezone.now().isoformat(),
    }

    try:
        total_bytes, used_bytes, free_bytes = shutil.disk_usage(settings.BASE_DIR)
        used_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0.0
        snapshot["disk"] = {
            "path": str(settings.BASE_DIR),
            "total_gb": round(total_bytes / (1024 ** 3), 2),
            "free_gb": round(free_bytes / (1024 ** 3), 2),
            "used_percent": used_percent,
        }
    except Exception:  # pragma: no cover - platform/runtime dependent
        snapshot["disk"] = {
            "path": str(getattr(settings, "BASE_DIR", "")),
            "total_gb": None,
            "free_gb": None,
            "used_percent": None,
        }

    try:
        from apps.sync.models import SyncQueue, SyncQueueStatus
        from apps.sync.services import (
            active_session_authority_enforced,
            current_local_node_id,
            current_sync_node_role,
            sync_policy_rows,
        )

        latest_synced_at = (
            SyncQueue.objects.exclude(synced_at__isnull=True)
            .order_by("-synced_at")
            .values_list("synced_at", flat=True)
            .first()
        )
        latest_problem_at = (
            SyncQueue.objects.filter(status__in=[SyncQueueStatus.FAILED, SyncQueueStatus.CONFLICT])
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        pending_count = SyncQueue.objects.filter(status=SyncQueueStatus.PENDING).count()
        retry_count = SyncQueue.objects.filter(status=SyncQueueStatus.RETRY).count()
        failed_count = SyncQueue.objects.filter(status=SyncQueueStatus.FAILED).count()
        conflict_count = SyncQueue.objects.filter(status=SyncQueueStatus.CONFLICT).count()
        snapshot["sync"] = {
            "node_role": current_sync_node_role(),
            "node_id": current_local_node_id(),
            "pull_enabled": bool(getattr(settings, "SYNC_PULL_ENABLED", True)),
            "authority_enforced": active_session_authority_enforced(),
            "pending": pending_count,
            "retry": retry_count,
            "failed": failed_count,
            "conflict": conflict_count,
            "backlog": pending_count + retry_count + failed_count + conflict_count,
            "latest_synced_at": latest_synced_at.isoformat() if latest_synced_at else "",
            "latest_problem_at": latest_problem_at.isoformat() if latest_problem_at else "",
            "policy_rows": sync_policy_rows(),
        }
    except Exception:  # pragma: no cover - runtime dependency check
        snapshot["sync"] = {
            "node_role": (getattr(settings, "SYNC_NODE_ROLE", "CLOUD") or "CLOUD").strip().upper(),
            "node_id": (getattr(settings, "SYNC_LOCAL_NODE_ID", "") or "").strip(),
            "pull_enabled": bool(getattr(settings, "SYNC_PULL_ENABLED", True)),
            "authority_enforced": bool(getattr(settings, "SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY", True)),
            "pending": None,
            "retry": None,
            "failed": None,
            "conflict": None,
            "backlog": None,
            "latest_synced_at": "",
            "latest_problem_at": "",
            "policy_rows": [],
        }

    try:
        from apps.audit.models import AuditEvent

        since = timezone.now() - timedelta(hours=24)
        latest_event_at = AuditEvent.objects.order_by("-created_at").values_list("created_at", flat=True).first()
        blank_hash_count = AuditEvent.objects.filter(Q(event_hash="") | Q(event_hash__isnull=True)).count()
        snapshot["audit"] = {
            "events_last_day": AuditEvent.objects.filter(created_at__gte=since).count(),
            "missing_hash_count": blank_hash_count,
            "latest_event_at": latest_event_at.isoformat() if latest_event_at else "",
        }
    except Exception:  # pragma: no cover - runtime dependency check
        snapshot["audit"] = {
            "events_last_day": None,
            "missing_hash_count": None,
            "latest_event_at": "",
        }

    return snapshot


def healthz(request):
    return JsonResponse({"status": "ok"}, status=200)


def readyz(request):
    snapshot = collect_ops_runtime_snapshot()
    status = 200 if snapshot["status"] == "ready" else 503
    return JsonResponse(snapshot, status=status)
