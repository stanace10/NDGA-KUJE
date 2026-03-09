from django.urls import path

from apps.notifications.views import (
    MediaCenterView,
    NotificationCenterView,
    NotificationDetailView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
)

app_name = "notifications"

urlpatterns = [
    path("center/", NotificationCenterView.as_view(), name="center"),
    path("detail/<uuid:notification_id>/", NotificationDetailView.as_view(), name="detail"),
    path("media/", MediaCenterView.as_view(), name="media-center"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark-all-read"),
    path("read/<uuid:notification_id>/", NotificationMarkReadView.as_view(), name="mark-read"),
]
