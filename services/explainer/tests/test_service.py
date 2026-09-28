import asyncio
import json

import httpx
import pytest
import respx

from conftest import facts, good, make, reply
from explainer import news
from explainer.cache import Cache
from explainer.config import Settings
from explainer.ledger import Ledger
from explainer.facts import Facts, render
from explainer.llm import OPENROUTER_URL
from explainer.service import Explainer, NotFound, Upstream

FACTS_URL = "http://nfl.test/api/facts/g1"


def models_called(route):
    return [json.loads(c.request.content)["model"] for c in route.calls]


async def test_happy_path_is_llm_then_a_cache_hit(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    first = await ex.explain("nfl", "g1")
    second = await ex.explain("nfl", "g1")
    assert first["source"] == "llm" and first["model"] == "m1"
    assert first["verdict"] and [f["key"] for f in first["factors"]]
    assert second == first and llm.call_count == 1
    assert set(first) >= {"sport", "id", "verdict", "factors", "band", "source", "model",
                          "generated_at", "prompt_version", "pick_timing"}
    # The band is computed from the facts, so it is the same whatever the model
    # said — and this fixture's pick is 0.62 on a two-way market, which is strong.
    assert first["band"] == "strong", f"band={first['band']!r}"


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
    bad = good(verdict="A 70% chance for Baltimore")
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
    assert out["verdict"] and out["factors"] and out["band"]


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
    assert second["source"] == "template" and "64%" in " ".join(
        [second["verdict"]] + [f["text"] for f in second["factors"]])
    assert second["band"] == "strong", f"band={second['band']!r}"


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
    assert "rebuilt after kickoff" in " ".join(
        [out["verdict"]] + [f["text"] for f in out["factors"]])


async def test_response_carries_the_pick_timing_so_the_panel_can_say_so(tmp_path, no_news):
    """The panel has to repeat the site's "Rebuilt after kickoff" status. It
    cannot know the timing from the prose: a model can be told to disclose a
    rebuilt pick in its own words, and the template's wording is not the site's
    status label. So the honest timing travels with the answer, and the panel
    renders it rather than guessing it."""
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts(pick_timing="rebuilt")))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    assert (await make(tmp_path).explain("nfl", "g1"))["pick_timing"] == "rebuilt"


async def test_pick_timing_travels_with_a_cached_answer_too(tmp_path, no_news):
    """The timing comes from the facts, not the cache row, so a cache hit must
    carry the same value as the miss that filled it."""
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts(pick_timing="pre_kickoff")))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    assert (await ex.explain("nfl", "g1"))["pick_timing"] == "pre_kickoff"
    assert (await ex.explain("nfl", "g1"))["pick_timing"] == "pre_kickoff"


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


async def test_the_response_carries_the_pick(tmp_path, no_news):
    """The response has to say what the pick is, or the panel cannot follow it.

    `ProbabilityBar` emphasises a segment, and with nothing in the answer saying
    which side the pick is on, the only thing it could follow was segment order —
    which is how BAL at 62% came to be drawn in grey while KC at 38% wore the
    accent. The value is derived, so this is the same on both paths.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    out = await ex.explain("nfl", "g1")
    assert out["source"] == "llm"
    assert out["pick"] == {"label": "BAL"}, out.get("pick")
    # And on the template path, and on a cache hit, because the panel cannot tell
    # which path wrote the words it is rendering.
    no_news.post(OPENROUTER_URL).mock(side_effect=httpx.ConnectError("down"))
    other = tmp_path / "template"
    other.mkdir()
    assert (await make(other).explain("nfl", "g1"))["pick"] == {"label": "BAL"}
    assert (await ex.explain("nfl", "g1"))["pick"] == {"label": "BAL"}


async def test_the_pick_is_the_facts_pick_not_the_model_says(tmp_path, no_news):
    """Derived, never asked. The model's verdict names the other side.

    A model told to name its own pick can disagree with the facts the verdict was
    computed from, and then the bar emphasises a different segment than the
    sentence describes — the "right number, wrong attribution" shape. So the
    model's opinion here changes nothing, and the test is only worth anything
    because the body is accepted: `source == "llm"` below is the proof.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good(
        verdict="Kansas City is the pick, but the line is thinner than the number.")))
    out = await make(tmp_path).explain("nfl", "g1")
    assert out["source"] == "llm", f"the body was rejected, so this proves nothing: {out['source']}"
    assert out["pick"] == {"label": "BAL"}, out.get("pick")


@pytest.mark.parametrize("pick", [
    None,                             # no pick at all
    {},                               # a stub
    {"label": "BAL"},                 # a label and no probability
    {"label": "BAL", "prob": 1.4},    # a probability that cannot mean anything
])
async def test_no_pick_means_no_pick_key_at_all(tmp_path, no_news, pick):
    """ABSENT, not null, not an object with a label in it.

    The renderer acts on the absence — it decides whether to emphasise a segment
    at all — so `"pick": null` and `"pick": {"label": ""}` are both answers to a
    question that was not asked. The key not being there is the whole signal.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts(pick=pick)))
    no_news.post(OPENROUTER_URL).mock(return_value=reply(good(
        verdict="There is no pick for this one yet.")))
    out = await make(tmp_path).explain("nfl", "g1")
    assert "pick" not in out, (
        f"a bundle with pick={pick!r} carried {out.get('pick')!r} — the panel would "
        "emphasise a segment for a pick that is not there"
    )
    # The band is the other half of the same rule: no pick, no confidence to claim.
    assert out["band"] == "leaning", out["band"]


async def test_the_template_path_carries_no_pick_either(tmp_path, no_news):
    """The no-pick answer comes from the template as often as from a model.

    A test that only drove the model path would pass while the template path
    served a `pick` it made up — and this is the path that runs when the model is
    over budget, which is most days.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts(pick=None)))
    no_news.post(OPENROUTER_URL).mock(side_effect=httpx.ConnectError("down"))
    out = await make(tmp_path).explain("nfl", "g1")
    assert out["source"] == "template", out["source"]
    assert "pick" not in out, out.get("pick")


async def test_a_confident_model_cannot_promote_a_52_percent_pick(tmp_path, no_news):
    """§13a's deliberately-broken input, end to end.

    Every other guard in this phase is proven by deleting a check. This one is
    proven by a model actively trying to inflate its own confidence: it returns
    `"band": "strong"` beside a 52% pick, and the response must read `moderate`.

    The model's body is written here rather than reusing `good()`, because
    `good()` quotes 62% and a 62% figure is itself invalid against 0.52 — so the
    answer would be rejected as an invented number and fall through to the
    template, and the test would pass for a reason that has nothing to do with
    the band. No digits anywhere, so the only thing that can reject this body is
    a rule about the band.
    """
    facts_52 = facts(pick={"label": "BAL", "prob": 0.52})
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts_52))
    g = {"verdict": "Baltimore is the pick, though the line asks for more.",
         "factors": [
             {"key": "spread", "direction": "up", "headline": "The model likes Baltimore",
              "text": "It rates Baltimore ahead, though the market is nearly level."},
             {"key": "record", "direction": "up", "headline": "Its record so far",
              "text": "Counted from picks made before the start."}],
         "band": "strong"}
    no_news.post(OPENROUTER_URL).mock(return_value=reply(g))

    ex = make(tmp_path)
    out = await ex.explain("nfl", "g1")

    assert out["source"] == "llm", f"the body was rejected, so this proves nothing: {out['source']}"
    # `.get`, not `out["band"]`: with the override removed the key is simply
    # absent, and a KeyError would fail the test without saying anything about
    # the band. The assertion has to be the thing that reports.
    assert out.get("band") == "moderate", (
        f"a model-supplied band reached the response: {out.get('band')!r} for a 0.52 pick"
    )

    # Defence in depth, made testable — and the layer that is NOT the load-bearing
    # one. `_answer` sets the band after spreading the body, so the override is
    # what guarantees the response; mutating `clean_verdict` to keep the model's
    # band changes nothing observable, which is worth knowing rather than
    # assuming. What still matters is not *persisting* it: the cache is where a
    # field nobody reads yet becomes a field somebody reads later.
    assert ex._answer is not None
    stored_key = Cache.key("nfl", "g1", render(Facts(**facts_52)), "",
                           ex.settings.prompt_version,
                           f"{ex.settings.model}|{ex.settings.fallback_model}")
    stored = ex.cache.get(stored_key)
    assert stored is not None, "nothing was cached, so this says nothing"
    assert "band" not in stored["body"], f"a model band was persisted: {sorted(stored['body'])}"


async def test_the_band_is_the_same_whether_the_model_answered_or_not(tmp_path, no_news):
    """The two paths cannot disagree about confidence.

    The band is computed in `_answer` for both, so the template's own value is
    overwritten rather than trusted. If that ever became conditional, the default
    would start reading differently from the model — which is the failure §8
    exists to prevent, and the one a reader would never notice.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL)
    # Two separate Explainers, so the second is a genuine miss rather than a cache
    # hit on the first. The directories have to exist or sqlite cannot open them.
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()

    llm.mock(return_value=reply(good()))
    from_model = await make(a).explain("nfl", "g1")
    llm.mock(side_effect=httpx.ConnectError("down"))
    from_template = await make(b).explain("nfl", "g1")

    assert from_model["source"] == "llm" and from_template["source"] == "template"
    assert from_model["band"] == from_template["band"] == "strong", (
        f"model said {from_model['band']!r}, template said {from_template['band']!r}"
    )
