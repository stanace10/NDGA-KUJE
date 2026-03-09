from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import RedirectView, TemplateView, UpdateView

from apps.academics.forms import CampusForm
from apps.academics.models import Campus
from apps.academics.views import ITManagerRequiredMixin, _related_usage_counts, _usage_summary_text
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event


class ITCampusListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_campuses.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or CampusForm()
        paginated = self._paginate_queryset(Campus.objects.order_by("code"))
        context["campuses"] = paginated["rows"]
        context["campuses_page_obj"] = paginated["page_obj"]
        context["campuses_page_size"] = paginated["page_size"]
        context["campuses_page_size_options"] = paginated["page_size_options"]
        context["campuses_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = CampusForm(request.POST)
        if form.is_valid():
            item = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CAMPUS_SAVED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"id": item.id, "code": item.code},
            )
            messages.success(request, "Campus saved successfully.")
            return redirect("academics:it-campuses")
        return self.render_to_response(self.get_context_data(form=form))


class ITCampusUpdateView(ITManagerRequiredMixin, UpdateView):
    model = Campus
    form_class = CampusForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-campuses")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit Campus: {self.object.code}"
        context["back_url"] = reverse("academics:it-campuses")
        return context


class ITCampusDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(Campus, pk=kwargs["pk"])
        code = row.code
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="CAMPUS_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"code": code, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Campus {code} {status_label}.")
        return redirect("academics:it-campuses")


class ITCampusHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(Campus, pk=kwargs["pk"])
        code = row.code
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CAMPUS_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"code": code, "usage": usage},
            )
            messages.error(
                request,
                (
                    f"Campus {code} cannot be deleted because records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-campuses")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="CAMPUS_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"code": code},
        )
        messages.success(request, f"Campus {code} deleted permanently.")
        return redirect("academics:it-campuses")
