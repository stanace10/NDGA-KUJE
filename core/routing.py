from apps.elections.routing import websocket_urlpatterns as election_ws_patterns

# WebSocket routes are introduced as each real-time module is implemented.
websocket_urlpatterns = [
    *election_ws_patterns,
]
