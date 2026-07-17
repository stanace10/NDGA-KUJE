from django.urls import path

from apps.audit.views import AuditEventListView

app_name = "audit"

urlpatterns = [
    path("events/", AuditEventListView.as_view(), name="event-list"),
]

