"""A rate limit, a withdrawn model and a bad key are three different problems.

`LLMError` carried a flat string, so all three arrived at the log as
`model %s failed: HTTP <code>` and the reader's only clue was the number. Then
`_generate` caught the error and moved straight on to the fallback model — which,
on a 429, is also rate limited. So being throttled cost two requests, still
failed, and left nothing behind to explain why.

That is not hypothetical: both of the previous default models turned out to be
withdrawn from OpenRouter's free tier, and two candidates the reviewer tried
were returning 429. Neither was visible from the service; both had to be found
from a machine with egress.

So:

* `LLMError` carries a **kind**, and the log line says which kind. An operator
  reading one line can tell "fix the config" from "back off" from "fix the key".
* a 429 does **not** try the fallback. The provider is refusing this account, so
  the second attempt is the same request again.
* the counts are on `/status`, because a dead default is invisible until someone
  notices every panel is a template.

The budget question this file deliberately does **not** answer by changing code:
a 429 still spends from the daily cap, because the cap is documented as
"OpenRouter requests per UTC day" and a throttled request is one we sent. What
wastage there was, it was the retry.
"""
import httpx
import pytest

from conftest import facts, good, make, reply
from explainer.llm import OPENROUTER_URL, LLMError, complete

FACTS_URL = "http://nfl.test/api/facts/g1"

RATE_LIMITED = httpx.Response(429, json={"error": {"message": "Rate limit exceeded"}})
WITHDRAWN = httpx.Response(404, json={"error": {"message": "No endpoints found for x/y:free"}})
BAD_KEY = httpx.Response(401, json={"error": {"message": "User not found"}})


async def test_a_429_does_not_try_the_fallback_model(tmp_path, no_news):
    """The wasteful one. A throttled account is throttled for both models."""
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=RATE_LIMITED)

    out = await make(tmp_path).explain("nfl", "g1")

    assert llm.call_count == 1, (
        f"the fallback was tried after a 429 ({llm.call_count} calls). OpenRouter is "
        f"rate-limiting this account, so the second call is the same request again."
    )
    assert out["source"] == "template", "a throttled service must still render a panel"


async def test_a_withdrawn_model_does_try_the_fallback(tmp_path, no_news):
    """The opposite case, and the one that would regress if 429 were treated the
    same way: a 404 is specific to the model named, so the other one may work."""
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(side_effect=[WITHDRAWN, reply(good())])

    out = await make(tmp_path).explain("nfl", "g1")

    assert llm.call_count == 2
    assert out["source"] == "llm", "a withdrawn primary must not cost the product its model summaries"


async def _kind_for(no_news, response) -> tuple[str, str]:
    """Drive complete() with one canned HTTP response, and report the kind
    and the message.

    A plain `httpx.AsyncClient`, NOT the respx router: the router is callable,
    so handing it to complete() makes respx try to parse the request's
    `timeout=` kwarg as a route pattern and raise `KeyError: 'timeout' is not
    a valid Pattern`.
    """
    from explainer.config import Settings

    no_news.post(OPENROUTER_URL).mock(return_value=response)
    with pytest.raises(LLMError) as caught:
        await complete(httpx.AsyncClient(), Settings(openrouter_api_key="k"), "m",
                       [{"role": "user", "content": "x"}])
    return caught.value.kind, str(caught.value)


async def test_the_error_carries_a_kind_not_just_a_number(no_news):
    """A log line reading `HTTP 429` is a puzzle; `rate_limited` is an answer."""
    kind, message = await _kind_for(no_news, RATE_LIMITED)
    assert kind == "rate_limited"
    assert "429" in message, "the status code belongs in the message too"

    assert (await _kind_for(no_news, WITHDRAWN))[0] == "not_found"
    assert (await _kind_for(no_news, BAD_KEY))[0] == "unauthorized", (
        "a bad key must not read as a model problem")


async def test_an_unparseable_answer_is_its_own_kind(no_news):
    """Distinct from a 4xx: the model answered, and the answer was unusable.

    Conflating it with a transport error would hide that the model is reachable
    and merely misbehaving, which is a different thing to go and fix.
    """
    assert (await _kind_for(no_news, reply("not json at all")))[0] == "bad_response"
