from django.urls import path

from apps.sync.views import (
    SyncAPIStatusView,
    SyncCBTContentFeedAPIView,
    SyncOutboxFeedAPIView,
    SyncOutboxIngestAPIView,
)

app_name = "sync"

urlpatterns = [
    path("api/", SyncAPIStatusView.as_view(), name="api-status"),
    path("api/outbox/", SyncOutboxIngestAPIView.as_view(), name="api-outbox-ingest"),
    path("api/outbox/feed/", SyncOutboxFeedAPIView.as_view(), name="api-outbox-feed"),
    path("api/content/cbt/", SyncCBTContentFeedAPIView.as_view(), name="api-content-cbt"),
]
