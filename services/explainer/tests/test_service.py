import asyncio
import json

import httpx
import pytest
import respx

from conftest import facts, good
from explainer import news
from explainer.cache import Cache
from explainer.config import Settings
from explainer.ledger import Ledger
from explainer.llm import OPENROUTER_URL
from explainer.service import Explainer, NotFound, Upstream

FACTS_URL = "http://nfl.test/api/facts/g1"


def reply(body, status=200):
    content = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture(autouse=True)
def no_news():
    news._CACHE.clear()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith="https://site.api.espn.com").mock(return_value=httpx.Response(200, json={"articles": []}))
        yield mock


def make(tmp_path, key="k", cap=10, enabled=True):
    s = Settings(openrouter_api_key=key, sport_api_nfl="http://nfl.test/api", EXPLAINER_DAILY_CAP=cap,
                 EXPLAINER_ENABLED=enabled, EXPLAINER_MODEL="m1", EXPLAINER_FALLBACK_MODEL="m2")
    db = str(tmp_path / "e.sqlite")
    return Explainer(s, Cache(db), Ledger(db, cap=cap), httpx.AsyncClient())


def models_called(route):
    return [json.loads(c.request.content)["model"] for c in route.calls]


async def test_happy_path_is_llm_then_a_cache_hit(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    first = await ex.explain("nfl", "g1")
    second = await ex.explain("nfl", "g1")
    assert first["source"] == "llm" and first["model"] == "m1" and first["headline"] == "Baltimore favored at 62%"
    assert second == first and llm.call_count == 1
    assert set(first) >= {"sport", "id", "headline", "sections", "source", "model", "generated_at", "prompt_version"}


async def test_request_carries_the_openrouter_headers_and_settings(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    await make(tmp_path).explain("nfl", "g1")
    req = llm.calls[0].request
    body = json.loads(req.content)
    assert req.headers["Authorization"] == "Bearer k"
    assert req.headers["HTTP-Referer"] == "https://40-160-91-131.sslip.io" and req.headers["X-Title"] == "Predictor"
    assert body["temperature"] == 0.3 and body["max_tokens"] == 700
    assert body["response_format"] == {"type": "json_object"}
    assert "Chiefs at Ravens" in body["messages"][-1]["content"]


async def test_invalid_first_answer_retries_once_on_the_fallback(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    bad = good(headline="A 70% chance for Baltimore")
    llm = no_news.post(OPENROUTER_URL).mock(side_effect=[reply(bad), reply(good())])
    out = await make(tmp_path).explain("nfl", "g1")
    assert models_called(llm) == ["m1", "m2"] and out["source"] == "llm" and out["model"] == "m2"


async def test_fenced_json_is_accepted(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    no_news.post(OPENROUTER_URL).mock(return_value=reply("```json\n" + json.dumps(good()) + "\n```"))
    assert (await make(tmp_path).explain("nfl", "g1"))["source"] == "llm"


async def test_both_invalid_or_erroring_means_template(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(side_effect=[reply("not json"), httpx.Response(404, json={"error": "no such model"})])
    out = await make(tmp_path).explain("nfl", "g1")
    assert out["source"] == "template" and llm.call_count == 2
    assert out["headline"] == "Chiefs at Ravens: BAL at 62%"


async def test_ledger_at_cap_means_template_and_no_calls(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    out = await make(tmp_path, cap=0).explain("nfl", "g1")
    assert out["source"] == "template" and llm.call_count == 0


@pytest.mark.parametrize("kw", [{"key": None}, {"enabled": False}])
async def test_no_key_or_disabled_means_template(tmp_path, no_news, kw):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    assert (await make(tmp_path, **kw).explain("nfl", "g1"))["source"] == "template"
    assert llm.call_count == 0


async def test_concurrent_callers_share_one_generation(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))

    async def slow(request):
        await asyncio.sleep(0.05)
        return reply(good())

    llm = no_news.post(OPENROUTER_URL).mock(side_effect=slow)
    ex = make(tmp_path)
    a, b = await asyncio.gather(ex.explain("nfl", "g1"), ex.explain("nfl", "g1"))
    assert llm.call_count == 1 and a == b


async def test_new_facts_regenerate(tmp_path, no_news):
    route = no_news.get(FACTS_URL).mock(side_effect=[httpx.Response(200, json=facts()),
                                                     httpx.Response(200, json=facts(pick={"label": "BAL", "prob": 0.64}))])
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    await ex.explain("nfl", "g1")
    second = await ex.explain("nfl", "g1")
    assert llm.call_count == 3  # 62% text is invalid against 64% facts: retry, then template
    assert second["source"] == "template" and "64%" in second["headline"]


async def test_a_template_made_in_an_outage_is_retried_later(tmp_path, no_news, monkeypatch):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(side_effect=[httpx.Response(503), httpx.Response(503), reply(good())])
    ex = make(tmp_path)
    assert (await ex.explain("nfl", "g1"))["source"] == "template"
    assert (await ex.explain("nfl", "g1"))["source"] == "template"  # within the retry window: cached
    monkeypatch.setattr("explainer.service.TEMPLATE_RETRY_SECONDS", -1)
    assert (await ex.explain("nfl", "g1"))["source"] == "llm" and llm.call_count == 3


async def test_rebuilt_pick_without_disclosure_is_rejected(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts(pick_timing="rebuilt")))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    out = await make(tmp_path).explain("nfl", "g1")
    assert out["source"] == "template"
    assert "rebuilt after kickoff" in " ".join(s["text"] for s in out["sections"])


async def test_sport_api_errors_are_typed(tmp_path, no_news):
    ex = make(tmp_path)
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(NotFound):
        await ex.explain("nfl", "g1")
    no_news.get("http://nfl.test/api/facts/g2").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(Upstream):
        await ex.explain("nfl", "g2")
    no_news.get("http://nfl.test/api/facts/g3").mock(return_value=httpx.Response(200, json={"nope": 1}))
    with pytest.raises(Upstream):
        await ex.explain("nfl", "g3")
    with pytest.raises(NotFound):
        await ex.explain("pl", "x")  # sport not configured
