import json

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_PRINCIPAL
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event
from apps.sync.content_sync import build_cbt_content_feed
from apps.sync.forms import SyncDashboardFilterForm, SyncImportForm
from apps.sync.inbound_sync import ingest_remote_outbox_event
from apps.sync.models import SyncQueue, SyncQueueStatus, SyncTransferBatch
from apps.sync.services import (
    build_outbox_feed,
    build_runtime_status_payload,
    export_sync_queue_snapshot,
    import_sync_queue_snapshot,
    process_sync_queue_batch,
)


class SyncDashboardAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        user = self.request.user
        return user.has_role(ROLE_IT_MANAGER) or user.has_role(ROLE_PRINCIPAL)


class SyncDashboardView(SyncDashboardAccessMixin, TemplateView):
    template_name = "sync/dashboard.html"
    page_size = 25

    def _filter_form(self):
        return SyncDashboardFilterForm(
            data=self.request.GET or None,
            operation_choices=SyncQueue._meta.get_field("operation_type").choices,
            status_choices=SyncQueue._meta.get_field("status").choices,
        )

    def _queue_queryset(self):
        queryset = SyncQueue.objects.order_by("-created_at")
        form = self._filter_form()
        if form.is_valid():
            operation = (form.cleaned_data.get("operation_type") or "").strip()
            status = (form.cleaned_data.get("status") or "").strip()
            if operation:
                queryset = queryset.filter(operation_type=operation)
            if status:
                queryset = queryset.filter(status=status)
        return queryset, form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset, filter_form = self._queue_queryset()
        page_obj = Paginator(queryset, self.page_size).get_page(self.request.GET.get("page", 1))
        counts = {
            row["status"]: row["count"]
            for row in SyncQueue.objects.values("status").annotate(count=Count("id"))
        }
        context["runtime_status"] = build_runtime_status_payload()
        context["page_obj"] = page_obj
        context["filter_form"] = kwargs.get("filter_form") or filter_form
        context["import_form"] = kwargs.get("import_form") or SyncImportForm()
        context["status_counts"] = counts
        context["auto_sync_interval_seconds"] = int(
            getattr(settings, "SYNC_AUTO_MIN_INTERVAL_SECONDS", 1)
        )
        context["recent_batches"] = SyncTransferBatch.objects.select_related("performed_by").order_by(
            "-created_at"
        )[:20]
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()

        if action == "run_sync":
            summary = process_sync_queue_batch(limit=80)
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SYNC_QUEUE_RUN",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata=summary,
            )
            messages.success(
                request,
                (
                    "Sync cycle complete. "
                    f"Claimed {summary['claimed']} | Synced {summary['synced']} | "
                    f"Retry {summary['retry']} | Failed {summary['failed']} | Conflict {summary['conflict']}."
                ),
            )
            return redirect("sync:dashboard")

        if action == "retry_failed":
            updated = SyncQueue.objects.filter(status=SyncQueueStatus.FAILED).update(
                status=SyncQueueStatus.RETRY,
                next_retry_at=timezone.now(),
                last_error="",
            )
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SYNC_RETRY_FAILED_RESET",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"updated": updated},
            )
            if updated:
                messages.success(request, f"{updated} failed queue item(s) moved back to retry.")
            else:
                messages.info(request, "No failed queue items available to retry.")
            return redirect("sync:dashboard")

        if action == "export":
            export_payload = export_sync_queue_snapshot(actor=request.user)
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SYNC_EXPORT_CREATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "file_name": export_payload["file_name"],
                    "item_count": export_payload["item_count"],
                    "checksum": export_payload["checksum"],
                },
            )
            response = HttpResponse(
                export_payload["json_text"],
                content_type="application/json",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{export_payload["file_name"]}"'
            )
            return response

        if action == "import":
            import_form = SyncImportForm(request.POST, request.FILES)
            if not import_form.is_valid():
                flat_errors = []
                for errors in import_form.errors.values():
                    flat_errors.extend(errors)
                messages.error(
                    request,
                    "; ".join(flat_errors) if flat_errors else "Upload a valid file snapshot.",
                )
                return self.render_to_response(self.get_context_data(import_form=import_form))
            file_obj = import_form.cleaned_data["snapshot_file"]
            try:
                raw_json = file_obj.read().decode("utf-8")
            except Exception:
                messages.error(request, "Could not decode the uploaded file.")
                return self.render_to_response(self.get_context_data(import_form=import_form))
            try:
                summary = import_sync_queue_snapshot(raw_json=raw_json, actor=request.user)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
                return self.render_to_response(self.get_context_data(import_form=import_form))
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SYNC_IMPORT_COMPLETED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata=summary,
            )
            messages.success(
                request,
                f"Snapshot import complete. Imported {summary['imported']} and skipped {summary['skipped']}.",
            )
            return redirect("sync:dashboard")

        messages.error(request, "Invalid sync action.")
        return redirect("sync:dashboard")


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
        return JsonResponse(
            {
                "ok": True,
                "service": "ndga-sync-api",
                "timestamp": timezone.now().isoformat(),
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
