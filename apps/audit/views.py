from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.views.generic import ListView

from apps.accounts.permissions import SCOPE_VIEW_AUDIT, has_scope
from apps.audit.models import AuditEvent


class AuditEventListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    template_name = "audit/event_list.html"
    context_object_name = "events"
    paginate_by = 50

    def test_func(self):
        return has_scope(self.request.user, SCOPE_VIEW_AUDIT)

    def get_queryset(self):
        queryset = AuditEvent.objects.select_related("actor").all()
        category = self.request.GET.get("category", "").strip()
        status = self.request.GET.get("status", "").strip()
        q = self.request.GET.get("q", "").strip()
        if category:
            queryset = queryset.filter(category=category)
        if status:
            queryset = queryset.filter(status=status)
        if q:
            queryset = queryset.filter(
                Q(event_type__icontains=q)
                | Q(message__icontains=q)
                | Q(actor_identifier__icontains=q)
                | Q(actor__username__icontains=q)
            )
        return queryset