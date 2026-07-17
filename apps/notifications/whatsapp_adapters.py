from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


@dataclass
class WhatsAppSendResult:
    success: bool
    provider: str
    detail: str = ""
    message_id: str = ""


class WhatsAppProvider(Protocol):
    provider_name: str

    def send(self, *, to_number: str, body_text: str, preview_url: bool = True) -> WhatsAppSendResult:
        ...


class DisabledWhatsAppProvider:
    provider_name = "disabled"

    def send(self, *, to_number: str, body_text: str, preview_url: bool = True):
        return WhatsAppSendResult(
            success=False,
            provider=self.provider_name,
            detail="WhatsApp provider is not configured.",
        )


class MetaWhatsAppCloudProvider:
    provider_name = "meta_cloud"

    def send(self, *, to_number: str, body_text: str, preview_url: bool = True):
        token = (getattr(settings, "WHATSAPP_ACCESS_TOKEN", "") or "").strip()
        phone_number_id = (getattr(settings, "WHATSAPP_PHONE_NUMBER_ID", "") or "").strip()
        base_url = (
            getattr(settings, "WHATSAPP_GRAPH_API_BASE_URL", "") or "https://graph.facebook.com/v23.0"
        ).rstrip("/")
        if not token or not phone_number_id:
            return WhatsAppSendResult(
                success=False,
                provider=self.provider_name,
                detail="WHATSAPP_ACCESS_TOKEN or WHATSAPP_PHONE_NUMBER_ID is not configured.",
            )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_number,
            "type": "text",
            "text": {
                "preview_url": bool(preview_url),
                "body": body_text,
            },
        }
        request = Request(
            f"{base_url}/{phone_number_id}/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw or "{}")
                message_id = ""
                contacts = parsed.get("messages") or []
                if contacts:
                    message_id = str((contacts[0] or {}).get("id") or "")
                status = getattr(response, "status", 200)
                return WhatsAppSendResult(
                    success=200 <= status < 300,
                    provider=self.provider_name,
                    detail=f"status={status}",
                    message_id=message_id,
                )
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            return WhatsAppSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"HTTPError {exc.code}: {detail}",
            )
        except URLError as exc:
            return WhatsAppSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"URLError {exc.reason}",
            )
        except Exception as exc:  # noqa: BLE001
            return WhatsAppSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"{type(exc).__name__}: {exc}",
            )


def get_whatsapp_provider():
    configured = (getattr(settings, "WHATSAPP_PROVIDER", "disabled") or "disabled").strip().lower()
    if configured in {"meta", "meta_cloud", "whatsapp_cloud"}:
        return MetaWhatsAppCloudProvider()
    return DisabledWhatsAppProvider()
