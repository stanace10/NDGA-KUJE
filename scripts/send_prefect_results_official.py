from __future__ import annotations

import json
from pathlib import Path
from urllib import error, request

from send_prefect_results_preview import (
    ANALYTICS_PDF,
    ENV_PATH,
    WINNERS_PDF,
    _attachment_payload,
    _load_env_file,
    build_html_body,
    build_subject,
    build_text_body,
)


ROOT = Path(__file__).resolve().parents[1]
RECIPIENTS_FILE = ROOT / "ndga" / "parent_emails_2026-04-23.txt"


def _load_recipients(path: Path) -> list[str]:
    recipients: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        email = raw_line.strip().lower()
        if not email or email.startswith("#") or email in seen:
            continue
        seen.add(email)
        recipients.append(email)
    return recipients


def send_official() -> dict[str, object]:
    env = _load_env_file(ENV_PATH)
    api_key = env.get("BREVO_API_KEY", "").strip()
    sender_email = env.get("NOTIFICATIONS_FROM_EMAIL", "office@ndgakuje.org").strip()
    sender_name = env.get("BREVO_SENDER_NAME", "NOTRE DAME GIRLS ACADEMY").strip()
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is missing from .env.lan")
    for path in (WINNERS_PDF, ANALYTICS_PDF, RECIPIENTS_FILE):
        if not path.exists():
            raise FileNotFoundError(path)

    recipients = _load_recipients(RECIPIENTS_FILE)
    subject = build_subject()
    text_body = build_text_body()
    html_body = build_html_body()
    attachments = [
        _attachment_payload(WINNERS_PDF),
        _attachment_payload(ANALYTICS_PDF),
    ]

    chunks = [recipients[i : i + 25] for i in range(0, len(recipients), 25)]
    sent = 0
    failed = 0
    failures: list[dict[str, object]] = []
    batch_message_ids: list[list[str]] = []
    for index, chunk in enumerate(chunks, start=1):
        payload = {
            "sender": {"name": sender_name, "email": sender_email},
            "subject": subject,
            "textContent": text_body,
            "htmlContent": html_body,
            "attachment": attachments,
            "messageVersions": [
                {
                    "to": [{"email": recipient}],
                }
                for recipient in chunk
            ],
        }
        req = request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
                if resp.status == 201:
                    sent += len(chunk)
                    batch_message_ids.append(list(data.get("messageIds") or []))
                else:
                    failed += len(chunk)
                    failures.append(
                        {
                            "batch": index,
                            "recipients": chunk,
                            "status": resp.status,
                        }
                    )
        except error.HTTPError as exc:
            failed += len(chunk)
            failures.append(
                {
                    "batch": index,
                    "recipients": chunk,
                    "status": exc.code,
                    "response": exc.read().decode("utf-8", errors="replace"),
                }
            )

    return {
        "recipient_count": len(recipients),
        "sent": sent,
        "failed": failed,
        "batch_count": len(chunks),
        "message_id_batches": batch_message_ids,
        "failures": failures[:10],
    }


if __name__ == "__main__":
    print(send_official())
