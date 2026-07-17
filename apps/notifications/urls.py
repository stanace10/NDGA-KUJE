from django.urls import path

from apps.notifications.views import (
    BrevoInboundWebhookView,
    EmailReplyAttachmentDownloadView,
    EmailReplyThreadDetailView,
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
    path("replies/<uuid:thread_id>/", EmailReplyThreadDetailView.as_view(), name="reply-thread-detail"),
    path(
        "replies/<uuid:thread_id>/attachments/<uuid:message_id>/<str:download_token>/",
        EmailReplyAttachmentDownloadView.as_view(),
        name="reply-thread-attachment",
    ),
    path("webhooks/brevo/inbound/", BrevoInboundWebhookView.as_view(), name="brevo-inbound-webhook"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark-all-read"),
    path("read/<uuid:notification_id>/", NotificationMarkReadView.as_view(), name="mark-read"),
]
