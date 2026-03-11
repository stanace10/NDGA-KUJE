from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from django.conf import settings


DEFAULT_AI_PROVIDER_ORDER = ("openai", "groq", "gemini", "huggingface")


def _setting(name, default=""):
    return getattr(settings, name, "") or os.getenv(name, default)


def _extract_json_payload(raw_text):
    text = str(raw_text or "").strip()
    if not text:
        return ""
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    start_brace = text.find("{")
    start_list = text.find("[")
    starts = [value for value in (start_brace, start_list) if value >= 0]
    if starts:
        text = text[min(starts):]
    last_brace = text.rfind("}")
    last_list = text.rfind("]")
    ends = [value for value in (last_brace, last_list) if value >= 0]
    if ends:
        text = text[: max(ends) + 1]
    return text.strip()


def _load_json(raw_text):
    payload_text = _extract_json_payload(raw_text)
    if not payload_text:
        return None
    try:
        return json.loads(payload_text)
    except json.JSONDecodeError:
        return None


def _provider_order():
    raw = str(_setting("AI_PROVIDER_ORDER", "")).strip()
    if not raw:
        return list(DEFAULT_AI_PROVIDER_ORDER)
    values = [row.strip().lower() for row in raw.split(",") if row.strip()]
    return values or list(DEFAULT_AI_PROVIDER_ORDER)


def _openai_compatible_json_response(*, api_key, model, system_prompt, user_prompt, base_url=None):
    if not api_key or not model:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None

    client_kwargs = {"api_key": api_key, "max_retries": 0}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)
    raw_text = ""

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw_text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        error_text = str(exc).lower()
        if "429" in error_text or "rate limit" in error_text:
            return None
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw_text = (response.choices[0].message.content or "").strip()
        except Exception:
            return None

    return _load_json(raw_text)


def _gemini_json_response(*, api_key, model, system_prompt, user_prompt):
    if not api_key or not model:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    candidates = raw.get("candidates") or []
    if not candidates:
        return None
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    text = "\n".join(str(row.get("text") or "").strip() for row in parts if isinstance(row, dict))
    return _load_json(text)


def ai_json_response(*, system_prompt, user_prompt):
    provider_map = {
        "openai": lambda: _openai_compatible_json_response(
            api_key=str(_setting("OPENAI_API_KEY", "")).strip(),
            model=str(_setting("OPENAI_CBT_MODEL", "gpt-4.1-mini")).strip() or "gpt-4.1-mini",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ),
        "groq": lambda: _openai_compatible_json_response(
            api_key=str(_setting("GROQ_API_KEY", "")).strip(),
            model=str(_setting("GROQ_MODEL", "llama-3.1-8b-instant")).strip() or "llama-3.1-8b-instant",
            base_url="https://api.groq.com/openai/v1",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ),
        "gemini": lambda: _gemini_json_response(
            api_key=str(_setting("GEMINI_API_KEY", "")).strip(),
            model=str(_setting("GEMINI_MODEL", "gemini-2.5-flash-lite")).strip() or "gemini-2.5-flash-lite",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ),
        "huggingface": lambda: _openai_compatible_json_response(
            api_key=str(_setting("HUGGINGFACE_API_KEY", "") or _setting("HF_TOKEN", "")).strip(),
            model=str(_setting("HUGGINGFACE_MODEL", "google/gemma-2-2b-it")).strip() or "google/gemma-2-2b-it",
            base_url="https://router.huggingface.co/v1",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        ),
    }

    for provider in _provider_order():
        handler = provider_map.get(provider)
        if not handler:
            continue
        payload = handler()
        if payload is not None:
            if isinstance(payload, dict) and "_ai_provider" not in payload:
                payload["_ai_provider"] = provider
            return payload
    return None
