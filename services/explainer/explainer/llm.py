"""OpenRouter chat completions, JSON out. The key goes in a header and
nowhere else: never logged, never returned."""
from __future__ import annotations

import json
import re

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REFERER = "https://40-160-91-131.sslip.io"
TIMEOUT_SECONDS = 25.0
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")


class LLMError(Exception):
    pass


async def complete(client: httpx.AsyncClient, settings, model: str, msgs: list[dict]) -> dict:
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "HTTP-Referer": REFERER,
               "X-Title": "Predictor"}
    payload = {"model": model, "messages": msgs, "temperature": 0.3, "max_tokens": 700,
               "response_format": {"type": "json_object"}}
    try:
        res = await client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise LLMError(f"request failed: {type(exc).__name__}") from None
    if res.status_code != 200:
        raise LLMError(f"HTTP {res.status_code}")
    try:
        content = res.json()["choices"][0]["message"]["content"]
        # Free models often wrap JSON in a code fence despite response_format.
        out = json.loads(_FENCE.sub("", content))
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("response was not the expected JSON") from None
    if not isinstance(out, dict):
        raise LLMError("response JSON was not an object")
    return out
