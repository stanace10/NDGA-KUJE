import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.sync.content_sync import build_cbt_content_feed
from apps.sync.inbound_sync import ingest_remote_outbox_event
from apps.sync.models import SyncQueue, SyncQueueStatus
from apps.sync.services import (
    build_outbox_feed,
    build_runtime_status_payload,
)
from core.ops import collect_ops_runtime_snapshot

class SyncAPITokenMixin:
    def _expected_token(self):
        return (getattr(settings, "SYNC_ENDPOINT_AUTH_TOKEN", "") or "").strip()

    def _authorize(self, request):
        expected = self._expected_token()
        if not expected:
            return True
        header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
        prefix = "Bearer "
        if not header.startswith(prefix):
            return False
        provided = header[len(prefix):].strip()
        return bool(provided) and provided == expected

    def _unauthorized(self):
        return JsonResponse(
            {"ok": False, "detail": "Unauthorized sync token."},
            status=401,
        )


@method_decorator(csrf_exempt, name="dispatch")
class SyncAPIBaseView(SyncAPITokenMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not self._authorize(request):
            return self._unauthorized()
        return super().dispatch(request, *args, **kwargs)


class SyncAPIStatusView(SyncAPIBaseView):
    def head(self, request, *args, **kwargs):
        return HttpResponse(status=204)

    def get(self, request, *args, **kwargs):
        runtime_status = build_runtime_status_payload()
        status_counts = {
            row["status"]: row["count"]
            for row in SyncQueue.objects.values("status").annotate(count=Count("id"))
        }
        ops_snapshot = collect_ops_runtime_snapshot()
        return JsonResponse(
            {
                "ok": True,
                "service": "ndga-sync-api",
                "timestamp": timezone.now().isoformat(),
                "runtime_status": runtime_status,
                "status_counts": {
                    "PENDING": status_counts.get(SyncQueueStatus.PENDING, 0),
                    "RETRY": status_counts.get(SyncQueueStatus.RETRY, 0),
                    "FAILED": status_counts.get(SyncQueueStatus.FAILED, 0),
                    "SYNCED": status_counts.get(SyncQueueStatus.SYNCED, 0),
                    "CONFLICT": status_counts.get(SyncQueueStatus.CONFLICT, 0),
                },
                "ops_snapshot": {
                    "status": ops_snapshot.get("status"),
                    "sync": ops_snapshot.get("sync", {}),
                    "celery": ops_snapshot.get("celery", {}),
                    "cbt": ops_snapshot.get("cbt", {}),
                },
            }
        )


class SyncOutboxIngestAPIView(SyncAPIBaseView):
    def post(self, request, *args, **kwargs):
        try:
            body = request.body.decode("utf-8")
            payload = json.loads(body) if body else {}
        except Exception:
            return JsonResponse(
                {"ok": False, "detail": "Invalid JSON body."},
                status=400,
            )
        if not isinstance(payload, dict):
            return JsonResponse(
                {"ok": False, "detail": "Invalid JSON payload."},
                status=400,
            )
        try:
            summary = ingest_remote_outbox_event(envelope=payload)
        except ValidationError as exc:
            detail = "; ".join(exc.messages) or "Unable to ingest outbox payload."
            status_code = 422
            if "Dependency unavailable" in detail:
                status_code = 503
            return JsonResponse({"ok": False, "detail": detail}, status=status_code)
        return JsonResponse({"ok": True, **summary})


class SyncOutboxFeedAPIView(SyncAPIBaseView):
    def get(self, request, *args, **kwargs):
        after_id = request.GET.get("after_id", "0")
        limit = request.GET.get("limit", "200")
        exclude_origin_node_id = request.GET.get("exclude_origin_node_id", "")
        payload = build_outbox_feed(
            after_id=after_id,
            limit=limit,
            exclude_origin_node_id=exclude_origin_node_id,
        )
        payload["ok"] = True
        return JsonResponse(payload)


class SyncCBTContentFeedAPIView(SyncAPIBaseView):
    def get(self, request, *args, **kwargs):
        after_id = request.GET.get("after_id", "0")
        limit = request.GET.get("limit", "200")
        payload = build_cbt_content_feed(after_id=after_id, limit=limit)
        payload["ok"] = True
        return JsonResponse(payload)
