from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.lan"
LOGO_PATH = ROOT / "static" / "images" / "ndga" / "logo.png"
WINNERS_PDF = ROOT / "ndga" / "NDGA-Election-Winners-Only.pdf"
ANALYTICS_PDF = ROOT / "ndga" / "NDGA-Election-Analytics-Summary.pdf"


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _attachment_payload(path: Path) -> dict[str, str]:
    return {
        "name": path.name,
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def build_subject() -> str:
    return "Official Memo: 2026 Prefect Election Results"


def build_text_body() -> str:
    return (
        "OFFICIAL MEMO\n"
        "Notre Dame Girls' Academy\n"
        "Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje Abuja\n"
        "FROM THE PRINCIPAL'S DESK\n"
        "DATE: 23 April 2026\n"
        "TO: Parents and Guardians\n"
        "SUBJECT: 2026 Prefect Election Results\n\n"
        "Dear Parents and Guardians,\n\n"
        "This is to formally inform you that Notre Dame Girls' Academy has concluded the 2026 prefect election through the school's electronic voting platform. Eligible students and staff participated in the exercise in an orderly, transparent, and well-monitored process.\n\n"
        "The election was conducted as a free and fair exercise, and the final records have been preserved through the school's digital system.\n\n"
        "Attached to this communication are the official election result summary and the analytics summary for your information.\n\n"
        "For offices structured as Head and Assistant positions, the candidate with the highest valid votes is declared the substantive Head Prefect, while the candidate with the second-highest valid votes is declared the Assistant Prefect.\n\n"
        "We appreciate your continued confidence in the school's commitment to discipline, fairness, credibility, and the responsible use of technology in student leadership processes.\n\n"
        "\"Let all things be done decently and in order.\" (1 Corinthians 14:40)\n\n"
        "Thank you for your continued partnership with the school.\n\n"
        "Yours faithfully,\n"
        "Sr. Rita Ezekwem, SNDdeN.\n"
        "Principal"
    )


def build_html_body() -> str:
    logo_src = _data_uri(LOGO_PATH)
    logo_block = ""
    if logo_src:
        logo_block = (
            "<div style='width:72px;height:72px;border-radius:18px;background:#ffffff;"
            "display:flex;align-items:center;justify-content:center;padding:10px;'>"
            f"<img src='{logo_src}' alt='NDGA logo' style='width:52px;height:52px;object-fit:contain;'>"
            "</div>"
        )
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;background:#f5f7fb;padding:24px 0;color:#334155;">
      <div style="max-width:720px;margin:0 auto;background:#ffffff;border-radius:24px;overflow:hidden;box-shadow:0 20px 48px rgba(15,23,42,0.10);">
        <div style="padding:24px 28px;background:linear-gradient(135deg,#102f57 0%,#1a487d 65%,#c79a35 100%);color:#ffffff;">
          <div style="display:flex;gap:18px;align-items:flex-start;">
            {logo_block}
            <div>
              <div style="display:inline-block;padding:7px 14px;border-radius:999px;background:rgba(255,255,255,0.18);font-size:11px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">Official Memo</div>
              <h1 style="margin:10px 0 6px;font-size:28px;line-height:1.1;">Notre Dame Girls' Academy</h1>
              <p style="margin:0;font-size:14px;color:#e2e8f0;">Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje Abuja</p>
              <p style="margin:10px 0 0;font-size:14px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#f8d78f;">From the Principal's Desk</p>
            </div>
          </div>
        </div>
        <div style="padding:28px;">
          <div style="border:1px solid #dbe4f0;border-radius:18px;background:#f8fbff;padding:18px 20px;margin:0 0 22px;">
            <p style="margin:0 0 6px;font-size:14px;color:#0f172a;"><strong>Date:</strong> 23 April 2026</p>
            <p style="margin:0 0 6px;font-size:14px;color:#0f172a;"><strong>To:</strong> Parents and Guardians</p>
            <p style="margin:0;font-size:14px;color:#0f172a;"><strong>Subject:</strong> 2026 Prefect Election Results</p>
          </div>

          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">Dear Parents and Guardians,</p>
          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">This is to formally inform you that Notre Dame Girls' Academy has concluded the 2026 prefect election through the school's electronic voting platform. Eligible students and staff participated in the exercise in an orderly, transparent, and well-monitored process.</p>
          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">The election was conducted as a free and fair exercise, and the final records have been preserved through the school's digital system.</p>
          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">Attached to this communication are the official election result summary and the analytics summary for your information.</p>

          <div style="margin:0 0 18px;padding:18px 20px;border-radius:18px;background:#fffaf0;border:1px solid #ecd8a4;">
            <p style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#9a6b08;">Result Structure</p>
            <p style="margin:0;font-size:15px;line-height:1.8;color:#5b4630;">For offices structured as Head and Assistant positions, the candidate with the highest valid votes is declared the substantive Head Prefect, while the candidate with the second-highest valid votes is declared the Assistant Prefect.</p>
          </div>

          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">We appreciate your continued confidence in the school's commitment to discipline, fairness, credibility, and the responsible use of technology in student leadership processes.</p>

          <div style="margin:0 0 18px;padding:16px 18px;border-left:4px solid #c79a35;background:#fffaf0;border-radius:0 14px 14px 0;">
            <p style="margin:0;font-size:14px;line-height:1.8;color:#5b4630;"><em>"Let all things be done decently and in order." (1 Corinthians 14:40)</em></p>
          </div>

          <p style="margin:0 0 14px;font-size:15px;line-height:1.85;">Thank you for your continued partnership with the school.</p>
          <p style="margin:18px 0 8px;font-size:15px;">Yours faithfully,</p>
          <p style="margin:0;font-size:16px;font-weight:700;color:#0f172a;">Sr. Rita Ezekwem, SNDdeN.</p>
          <p style="margin:2px 0 0;font-size:14px;color:#475569;">Principal</p>
        </div>
      </div>
    </div>
    """


def send_preview() -> dict[str, str | int | bool]:
    env = _load_env_file(ENV_PATH)
    api_key = env.get("BREVO_API_KEY", "").strip()
    sender_email = env.get("NOTIFICATIONS_FROM_EMAIL", "office@ndgakuje.org").strip()
    sender_name = env.get("BREVO_SENDER_NAME", "NOTRE DAME GIRLS ACADEMY").strip()
    recipient = os.getenv("NDGA_PREVIEW_RECIPIENT", "szubby10@gmail.com").strip()
    if not api_key:
        raise RuntimeError("BREVO_API_KEY is missing from .env.lan")
    for path in (WINNERS_PDF, ANALYTICS_PDF):
        if not path.exists():
            raise FileNotFoundError(path)

    payload = {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": recipient}],
        "subject": build_subject(),
        "textContent": build_text_body(),
        "htmlContent": build_html_body(),
        "attachment": [
            _attachment_payload(WINNERS_PDF),
            _attachment_payload(ANALYTICS_PDF),
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
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "success": True,
                "status": resp.status,
                "recipient": recipient,
                "response": body,
            }
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": exc.code,
            "recipient": recipient,
            "response": body,
        }


if __name__ == "__main__":
    print(send_preview())
