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
    """A failed model call, carrying WHAT KIND of failure it was.

    The kind is the whole point. A withdrawn model, a rate limit, a bad key and
    a model that answered with nonsense are four different problems with four
    different fixes, and as a bare `HTTP <code>` string they all arrive looking
    alike — so a dead default can sit there costing every panel its explanation
    while the log says nothing actionable. Both previous defaults turned out to
    be withdrawn from the free tier, and two candidates were returning 429;
    neither was visible from here.

    `kind` is one of:

    ``rate_limited``   the provider is throttling this account. Retrying
                       another model immediately is the same request again, so
                       the caller does not.
    ``not_found``      this model id does not exist (withdrawn, renamed, typo).
                       Specific to the model named, so another one may work.
    ``unauthorized``   the key is wrong or revoked. Nothing will work.
    ``bad_response``   the model answered and the answer was unusable. It is
                       reachable and merely misbehaving.
    ``cut_off``        the model hit ``max_tokens`` mid-answer. Reached and
                       healthy — the budget is too small, or it is a reasoning
                       model that spent the budget thinking. Distinct from
                       ``bad_response`` because the fixes differ: raise the
                       limit, or turn reasoning off, rather than replacing a
                       model that is working.
    ``transport``      the request never completed (DNS, TLS, timeout).
    """

    def __init__(self, message: str, kind: str = "unknown", status: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.status = status


def classify(status: int) -> str:
    if status == 429:
        return "rate_limited"
    if status == 404:
        return "not_found"
    if status in (401, 403):
        return "unauthorized"
    return "provider_error"


async def complete(client: httpx.AsyncClient, settings, model: str, msgs: list[dict]) -> dict:
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "HTTP-Referer": REFERER,
               "X-Title": "Predictor"}
    payload = {"model": model, "messages": msgs, "temperature": 0.3, "max_tokens": 700,
               "response_format": {"type": "json_object"},
               # Reasoning off, explicitly, on every request.
               #
               # OpenRouter defaults a reasoning model to ON, and a reasoning
               # model spends the `max_tokens` budget on thinking before it
               # writes a token of the answer. At 700 that is most of the budget,
               # so the model reasons, runs out, and returns either nothing or
               # half a JSON object. That is the `cut_off` kind below, and it is
               # invisible without this key: the request succeeded, the model is
               # reachable, and the only evidence is a short body.
               #
               # `reasoning: {effort: "none"}` is the documented way to ask for
               # none. Sending `enabled: false` as well is deliberate belt and
               # braces -- providers disagree about which of the two they read,
               # and a silently-ignored key here costs every panel its summary
               # while the request reports success. OpenRouter passes unknown
               # keys through rather than rejecting the request, so a provider
               # that honours neither is no worse off than before.
               "reasoning": {"effort": "none", "enabled": False}}
    try:
        res = await client.post(OPENROUTER_URL, json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise LLMError(f"request failed: {type(exc).__name__}", kind="transport") from None
    if res.status_code != 200:
        raise LLMError(f"HTTP {res.status_code}", kind=classify(res.status_code), status=res.status_code)
    try:
        choice = res.json()["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("response was not the expected JSON", kind="bad_response") from None
    # A truncated answer is its own kind, counted separately.
    #
    # `finish_reason == "length"` means the model hit `max_tokens` mid-answer.
    # That is a budget problem, not a broken model: raising it or switching model
    # fixes it, while the `bad_response` it used to be filed under says neither
    # and sends an operator to look at a model that is working fine. Checked
    # BEFORE the JSON parse so the count reflects the real cause — a truncated
    # body fails to parse too, and would otherwise be filed as `bad_response`
    # every time. Length is only trusted when the provider actually sent it;
    # a missing key is not evidence of truncation.
    if choice.get("finish_reason") == "length":
        raise LLMError("answer was cut off at the token limit", kind="cut_off")
    try:
        # Free models often wrap JSON in a code fence despite response_format.
        out = json.loads(_FENCE.sub("", content))
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("response was not the expected JSON", kind="bad_response") from None
    if not isinstance(out, dict):
        raise LLMError("response JSON was not an object", kind="bad_response")
    return out
