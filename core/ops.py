from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import shutil
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

import redis


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


def _sync_status_counts():
    try:
        from django.db.models import Count

        from apps.sync.models import SyncQueue

        return {
            row["status"]: row["count"]
            for row in SyncQueue.objects.values("status").annotate(count=Count("id"))
        }
    except Exception:  # pragma: no cover - runtime dependency check
        return {}


def _celery_queue_snapshot():
    queue_names = list(getattr(settings, "MONITOR_CELERY_QUEUE_NAMES", []) or ["celery"])
    snapshot = {
        "broker_url": getattr(settings, "CELERY_BROKER_URL", ""),
        "reachable": False,
        "queues": [],
    }
    broker_url = snapshot["broker_url"]
    if not broker_url or not broker_url.startswith(("redis://", "rediss://")):
        return snapshot
    try:
        client = redis.Redis.from_url(broker_url)
        parsed = urlparse(broker_url)
        snapshot["host"] = parsed.hostname or ""
        snapshot["port"] = parsed.port or ""
        snapshot["db"] = parsed.path.lstrip("/") or "0"
        snapshot["reachable"] = bool(client.ping())
        for queue_name in queue_names:
            snapshot["queues"].append(
                {
                    "name": queue_name,
                    "depth": int(client.llen(queue_name)),
                }
            )
    except Exception:  # pragma: no cover - runtime dependency check
        snapshot["reachable"] = False
    return snapshot


def _cbt_runner_failure_snapshot():
    try:
        from apps.audit.models import AuditCategory, AuditEvent, AuditStatus

        since = timezone.now() - timedelta(hours=24)
        return {
            "total": AuditEvent.objects.filter(
                category=AuditCategory.CBT,
                status=AuditStatus.FAILURE,
            ).count(),
            "last_24h": AuditEvent.objects.filter(
                category=AuditCategory.CBT,
                status=AuditStatus.FAILURE,
                created_at__gte=since,
            ).count(),
            "latest_failure_at": (
                AuditEvent.objects.filter(
                    category=AuditCategory.CBT,
                    status=AuditStatus.FAILURE,
                )
                .order_by("-created_at")
                .values_list("created_at", flat=True)
                .first()
            ),
        }
    except Exception:  # pragma: no cover - runtime dependency check
        return {"total": None, "last_24h": None, "latest_failure_at": None}


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
        runtime_root = Path(getattr(settings, "ROOT_DIR", ".")).resolve()
        total_bytes, used_bytes, free_bytes = shutil.disk_usage(runtime_root)
        used_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes else 0.0
        snapshot["disk"] = {
            "path": str(runtime_root),
            "total_gb": round(total_bytes / (1024 ** 3), 2),
            "free_gb": round(free_bytes / (1024 ** 3), 2),
            "used_percent": used_percent,
        }
    except Exception:  # pragma: no cover - platform/runtime dependent
        snapshot["disk"] = {
            "path": str(getattr(settings, "ROOT_DIR", "")),
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
            "manual_mode": bool(getattr(settings, "SYNC_MANUAL_MODE", False)),
            "process_beat_enabled": bool(getattr(settings, "SYNC_PROCESS_BEAT_ENABLED", True)),
            "pull_enabled": bool(getattr(settings, "SYNC_PULL_ENABLED", True)),
            "pull_beat_enabled": bool(getattr(settings, "SYNC_PULL_BEAT_ENABLED", True)),
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
            "manual_mode": bool(getattr(settings, "SYNC_MANUAL_MODE", False)),
            "process_beat_enabled": bool(getattr(settings, "SYNC_PROCESS_BEAT_ENABLED", True)),
            "pull_enabled": bool(getattr(settings, "SYNC_PULL_ENABLED", True)),
            "pull_beat_enabled": bool(getattr(settings, "SYNC_PULL_BEAT_ENABLED", True)),
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

    snapshot["celery"] = _celery_queue_snapshot()
    cbt_failures = _cbt_runner_failure_snapshot()
    snapshot["cbt"] = {
        "failure_total": cbt_failures["total"],
        "failure_last_24h": cbt_failures["last_24h"],
        "latest_failure_at": (
            cbt_failures["latest_failure_at"].isoformat()
            if cbt_failures["latest_failure_at"]
            else ""
        ),
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


def _metric_line(name, value, labels=None):
    if labels:
        rendered = ",".join(
            f'{key}="{str(val).replace("\\", "\\\\").replace(chr(34), r"\"")}"'
            for key, val in labels.items()
        )
        return f"{name}{{{rendered}}} {value}"
    return f"{name} {value}"


def metrics(request):
    snapshot = collect_ops_runtime_snapshot()
    sync = snapshot.get("sync", {})
    disk = snapshot.get("disk", {})
    celery = snapshot.get("celery", {})
    cbt = snapshot.get("cbt", {})
    status_counts = _sync_status_counts()

    lines = [
        "# HELP ndga_ready Runtime readiness state of the NDGA app.",
        "# TYPE ndga_ready gauge",
        _metric_line("ndga_ready", 1 if snapshot.get("status") == "ready" else 0),
        "# HELP ndga_database_ready Database connectivity health.",
        "# TYPE ndga_database_ready gauge",
        _metric_line("ndga_database_ready", 1 if snapshot.get("checks", {}).get("database") else 0),
        "# HELP ndga_cache_ready Cache connectivity health.",
        "# TYPE ndga_cache_ready gauge",
        _metric_line("ndga_cache_ready", 1 if snapshot.get("checks", {}).get("cache") else 0),
        "# HELP ndga_disk_free_gigabytes Free disk capacity in gigabytes.",
        "# TYPE ndga_disk_free_gigabytes gauge",
        _metric_line("ndga_disk_free_gigabytes", disk.get("free_gb") or 0),
        "# HELP ndga_disk_used_percent Used disk capacity percentage.",
        "# TYPE ndga_disk_used_percent gauge",
        _metric_line("ndga_disk_used_percent", disk.get("used_percent") or 0),
        "# HELP ndga_sync_queue_items Sync queue items by status.",
        "# TYPE ndga_sync_queue_items gauge",
    ]
    for status in ["PENDING", "RETRY", "FAILED", "SYNCED", "CONFLICT"]:
        lines.append(
            _metric_line(
                "ndga_sync_queue_items",
                status_counts.get(status, 0),
                {"status": status.lower()},
            )
        )
    lines.extend(
        [
            "# HELP ndga_sync_backlog Sync backlog excluding already-synced items.",
            "# TYPE ndga_sync_backlog gauge",
            _metric_line("ndga_sync_backlog", sync.get("backlog") or 0),
            "# HELP ndga_celery_queue_depth Celery Redis queue depth by queue.",
            "# TYPE ndga_celery_queue_depth gauge",
        ]
    )
    for queue_row in celery.get("queues", []):
        lines.append(
            _metric_line(
                "ndga_celery_queue_depth",
                queue_row.get("depth", 0),
                {"queue": queue_row.get("name", "celery")},
            )
        )
    lines.extend(
        [
            "# HELP ndga_celery_broker_reachable Celery broker connectivity state.",
            "# TYPE ndga_celery_broker_reachable gauge",
            _metric_line("ndga_celery_broker_reachable", 1 if celery.get("reachable") else 0),
            "# HELP ndga_cbt_runner_failures_total Total CBT runner failures recorded in audit.",
            "# TYPE ndga_cbt_runner_failures_total gauge",
            _metric_line("ndga_cbt_runner_failures_total", cbt.get("failure_total") or 0),
            "# HELP ndga_cbt_runner_failures_last_24h CBT runner failures recorded in the last 24 hours.",
            "# TYPE ndga_cbt_runner_failures_last_24h gauge",
            _metric_line("ndga_cbt_runner_failures_last_24h", cbt.get("failure_last_24h") or 0),
        ]
    )
    return HttpResponse(
        "\n".join(lines) + "\n",
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
