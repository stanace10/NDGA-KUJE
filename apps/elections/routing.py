from django.urls import re_path

from apps.elections.consumers import ElectionAnalyticsConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/elections/(?P<election_id>\d+)/analytics/$",
        ElectionAnalyticsConsumer.as_asgi(),
    ),
]
