from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@dataclass
class EmailSendResult:
    success: bool
    provider: str
    detail: str = ""


class EmailProvider(Protocol):
    provider_name: str

    def send(
        self,
        *,
        to_emails: list[str],
        subject: str,
        body_text: str,
        body_html: str = "",
    ) -> EmailSendResult:
        ...


class ConsoleEmailProvider:
    provider_name = "console"

    def send(self, *, to_emails, subject, body_text, body_html=""):
        from_email = settings.NOTIFICATIONS_FROM_EMAIL
        message = EmailMultiAlternatives(
            subject=subject,
            body=body_text,
            from_email=from_email,
            to=to_emails,
        )
        if body_html:
            message.attach_alternative(body_html, "text/html")
        sent = message.send(fail_silently=False)
        return EmailSendResult(
            success=sent > 0,
            provider=self.provider_name,
            detail="sent" if sent > 0 else "not-sent",
        )


class BrevoEmailProvider:
    provider_name = "brevo"
    endpoint = "https://api.brevo.com/v3/smtp/email"

    def send(self, *, to_emails, subject, body_text, body_html=""):
        if not settings.BREVO_API_KEY:
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                detail="BREVO_API_KEY not configured.",
            )
        payload = {
            "sender": {
                "name": settings.BREVO_SENDER_NAME,
                "email": settings.NOTIFICATIONS_FROM_EMAIL,
            },
            "to": [{"email": email} for email in to_emails],
            "subject": subject,
            "textContent": body_text,
        }
        if body_html:
            payload["htmlContent"] = body_html
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "accept": "application/json",
                "api-key": settings.BREVO_API_KEY,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=12) as response:
                status = getattr(response, "status", 200)
                ok = 200 <= status < 300
                return EmailSendResult(
                    success=ok,
                    provider=self.provider_name,
                    detail=f"status={status}",
                )
        except HTTPError as exc:
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"HTTPError {exc.code}",
            )
        except URLError as exc:
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"URLError {exc.reason}",
            )
        except Exception as exc:  # noqa: BLE001
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                detail=f"{type(exc).__name__}: {exc}",
            )


def get_email_provider():
    configured = (settings.NOTIFICATIONS_EMAIL_PROVIDER or "console").strip().lower()
    if configured == "brevo":
        return BrevoEmailProvider()
    return ConsoleEmailProvider()
