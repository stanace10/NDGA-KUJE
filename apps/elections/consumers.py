from channels.generic.websocket import AsyncJsonWebsocketConsumer

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_PRINCIPAL
from apps.elections.models import Election
from apps.elections.services import (
    build_election_analytics_payload,
    election_ws_group_name,
)


class ElectionAnalyticsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not getattr(user, "is_authenticated", False):
            await self.close(code=4401)
            return
        allowed = user.has_role(ROLE_IT_MANAGER) or user.has_role(ROLE_PRINCIPAL)
        if not allowed:
            await self.close(code=4403)
            return
        election_id_raw = self.scope["url_route"]["kwargs"].get("election_id")
        try:
            self.election_id = int(election_id_raw)
        except (TypeError, ValueError):
            await self.close(code=4400)
            return
        exists = await Election.objects.filter(id=self.election_id, is_active=True).aexists()
        if not exists:
            await self.close(code=4404)
            return
        self.group_name = election_ws_group_name(self.election_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        payload = await self._analytics_payload()
        await self.send_json({"type": "analytics.snapshot", "payload": payload})

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = (content or {}).get("action")
        if action == "refresh":
            payload = await self._analytics_payload()
            await self.send_json({"type": "analytics.snapshot", "payload": payload})

    async def election_analytics_update(self, event):
        payload = event.get("payload") or {}
        await self.send_json({"type": "analytics.update", "payload": payload})

    async def _analytics_payload(self):
        election = await Election.objects.aget(id=self.election_id)
        return build_election_analytics_payload(election)
