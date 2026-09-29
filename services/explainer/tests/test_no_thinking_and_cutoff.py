"""Two properties of a model call, both of which failed silently.

**Thinking off, in every request.** OpenRouter defaults a reasoning model to
reasoning, and a reasoning model spends `max_tokens` on thinking before it
writes a token of the answer. At this service's 700 that is most of the budget:
the model thinks, runs out, and returns half a JSON object. Nothing about the
request looks wrong — it returned 200 — so the only evidence is a short body,
and the count lands in `bad_response`, which reads as "this model is broken"
rather than "this budget is too small".

**Cut-off counted separately.** `finish_reason == "length"` is a budget
problem with a different fix from a model that answers with nonsense, so it
gets its own `kind` and its own line in `/status`. Filing it under
`bad_response` sends an operator to replace a model that is working fine.

Both are checked here against the request that goes out and the error that
comes back, because both were invisible from the outside.
"""
import httpx
import pytest

from conftest import reply
from explainer.llm import OPENROUTER_URL, LLMError, complete
from explainer.config import Settings

MSGS = [{"role": "user", "content": "x"}]


def _cut_off() -> httpx.Response:
    """A 200 whose body stops mid-object, which is what a truncated answer is.

    Built to fail a JSON parse on its own, so the assertion that follows is
    about the KIND and not about the parse happening to succeed.
    """
    return httpx.Response(200, json={
        "choices": [{"finish_reason": "length",
                     "message": {"content": '{"verdict": "Balti'}}],
    })


async def _call(no_news, response: httpx.Response):
    """Drive complete() with one canned response, returning the call mock."""
    no_news.post(OPENROUTER_URL).mock(return_value=response)
    with pytest.raises(LLMError) as caught:
        await complete(httpx.AsyncClient(), Settings(openrouter_api_key="k"), "m", MSGS)
    return caught.value, no_news.post(OPENROUTER_URL)


async def test_every_request_asks_for_no_thinking(no_news):
    """The payload, not the model.

    This is the half that cannot be observed after the fact: a service that
    omits the key looks exactly like one that sent it, up until a reasoning
    model starts returning half an answer and the cause is not in any log.
    """
    no_news.post(OPENROUTER_URL).mock(return_value=reply({"verdict": "v", "factors": []}))
    await complete(httpx.AsyncClient(), Settings(openrouter_api_key="k"), "m", MSGS)

    sent = no_news.post(OPENROUTER_URL).calls[0].request
    body = sent.read().decode()
    assert '"reasoning"' in body, (
        "the request carries no reasoning key, so a reasoning model defaults to "
        "thinking and spends max_tokens before answering"
    )
    # Both spellings are sent deliberately: providers disagree about which they
    # read, and an ignored key costs every panel its summary.
    assert '"effort":"none"' in body.replace(" ", ""), "reasoning effort is not set to none"
    assert '"enabled":false' in body.replace(" ", ""), "reasoning is not disabled explicitly"


async def test_a_cut_off_answer_is_its_own_kind(no_news):
    """Not `bad_response`. The fixes are different and only one of them works."""
    exc, _ = await _call(no_news, _cut_off())
    assert exc.kind == "cut_off", (
        f"a truncated answer was filed as {exc.kind!r}. It is a budget problem: raise "
        f"max_tokens or turn reasoning off. `bad_response` says the model is broken, "
        f"which sends an operator to replace a model that is answering fine."
    )


async def test_cut_off_is_reported_before_the_parse(no_news):
    """The body is also invalid JSON, so the order is the thing under test.

    Checked the parse first, a truncated body fails there and lands in
    `bad_response` every time — which is the bug this whole change is for.
    """
    exc, _ = await _call(no_news, _cut_off())
    assert "cut off" in str(exc), f"the message does not say it was cut off: {exc}"


async def test_a_missing_finish_reason_is_not_treated_as_cut_off(no_news):
    """Absence of evidence is not evidence.

    A provider that omits `finish_reason` entirely is not truncating, and
    filing those as `cut_off` would make the new counter a lie in the other
    direction.
    """
    ok = httpx.Response(200, json={"choices": [{"message": {"content": '{"verdict":"v"}'}}]})
    no_news.post(OPENROUTER_URL).mock(return_value=ok)
    result = await complete(httpx.AsyncClient(), Settings(openrouter_api_key="k"), "m", MSGS)
    assert result == {"verdict": "v"}


async def test_a_complete_answer_is_still_parsed(no_news):
    """The guard above must not swallow the normal case."""
    no_news.post(OPENROUTER_URL).mock(
        return_value=httpx.Response(200, json={
            "choices": [{"finish_reason": "stop",
                         "message": {"content": '{"verdict":"Boston at 62%","factors":[]}'}}]}))
    result = await complete(httpx.AsyncClient(), Settings(openrouter_api_key="k"), "m", MSGS)
    assert result["verdict"] == "Boston at 62%"


async def test_status_publishes_the_cut_off_count(tmp_path):
    """Counting it and not publishing it is the same as not counting it.

    `/status` builds its `failures` dict from a hard-coded tuple, so a new kind
    is invisible there until it is added — and an operator watching for budget
    trouble has no way to see it. The sibling test in test_app.py pins the
    zero-valued contract; this pins that the key exists at all.
    """
    from test_app import client

    with client(tmp_path) as c:
        failures = c.get("/status").json()["failures"]
    assert "cut_off" in failures, (
        f"/status publishes {sorted(failures)} — `cut_off` is counted in the service "
        f"but read nowhere, which is exactly the 'no failures' vs 'not being read' "
        f"confusion this endpoint exists to prevent."
    )
