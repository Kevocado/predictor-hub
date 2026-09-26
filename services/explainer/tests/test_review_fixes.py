"""Regression tests for the Tasks 1–6 review."""
import json

import httpx
import pytest
import respx

from conftest import facts, good
from explainer import news
from explainer.llm import OPENROUTER_URL
from explainer.template import explain_from_template
from explainer.validate import validate
from conftest import make, reply

FACTS_URL = "http://nfl.test/api/facts/g1"


def text_of(out):
    return " ".join(s["text"] for s in out["sections"])


# I1: the template must survive loose facts
def test_template_survives_malformed_optional_fields():
    out = explain_from_template({"title": "A v B", "pick": {"label": "A", "prob": "0.6"},
                                 "markets": [{"market": "spread", "model_margin": "x", "line": None}, "junk"],
                                 "players": [{"team": "A"}, "junk"], "record": {"hits": None}})
    assert out["headline"] and len(out["sections"]) >= 1


async def test_a_template_crash_still_answers_and_frees_the_lock(tmp_path, no_news, monkeypatch):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    no_news.post(OPENROUTER_URL).mock(return_value=reply("not json"))
    monkeypatch.setattr("explainer.service.explain_from_template", lambda f: 1 / 0)
    ex = make(tmp_path)
    out = await ex.explain("nfl", "g1")
    assert out["source"] == "template" and out["sections"]
    assert ex._locks == {}


# I2: confidence line uses the pick's own probability
def test_draw_pick_at_30_percent_is_described_honestly():
    out = explain_from_template({"title": "Arsenal v Spurs", "sport": "pl", "pick": {"label": "Draw", "prob": 0.30}})
    assert "70%" not in text_of(out)
    assert "misses about seven times in ten" in text_of(out)


# I3: finals show the result; pick_won only for pre-kickoff picks
def test_template_final_shows_score_and_verdict_only_when_counted():
    final = {"title": "Chiefs at Ravens", "status": "final", "pick": {"label": "BAL", "prob": 0.62},
             "pick_timing": "pre_kickoff", "result": {"score": "BAL 27–20", "pick_won": True}}
    t = text_of(explain_from_template(final))
    assert "BAL 27–20" in t and "the pick was right" in t.lower()
    rebuilt = {**final, "pick_timing": "rebuilt", "result": {"score": "BAL 27–20"}}
    t = text_of(explain_from_template(rebuilt))
    assert "BAL 27–20" in t and "right" not in t.lower() and "wrong" not in t.lower()


# I4: an odd ESPN payload never breaks the explanation
@respx.mock
async def test_news_with_nulls_and_odd_types_is_safe():
    news._CACHE.clear()
    respx.get(news.ESPN_NEWS["nfl"]).mock(return_value=httpx.Response(200, json={"articles": [
        {"headline": "Ravens win", "published": None}, {"headline": 7}, "junk",
        {"headline": "Ravens again", "description": None, "published": "2026-10-01"}]}))
    async with httpx.AsyncClient() as c:
        out = await news.headlines(c, "nfl", ["Ravens", 5])
    assert [o["headline"] for o in out] == ["Ravens again", "Ravens win"]


# I5: West Ham's nickname isn't betting slang
def test_hammers_nickname_is_allowed_but_hammer_is_not():
    f = json.dumps(facts())
    assert validate(good(headline="The Hammers visit Baltimore at 62%"), f, "[]") == []
    assert validate(good(headline="Hammer Baltimore at 62%"), f, "[]")


# I6: the prompt no longer shows a derived number, and forbids computing
def test_prompt_example_has_no_derived_number_and_forbids_arithmetic():
    from explainer.prompts import SYSTEM
    assert "4 points better" not in SYSTEM
    assert "never compute" in SYSTEM.lower()


# I7: budget: news changes don't regenerate; validation failures don't retry
async def test_new_headlines_alone_do_not_cost_a_regeneration(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path)
    await ex.explain("nfl", "g1")
    news._CACHE["nfl"] = (1e12, [{"headline": "Ravens sign a punter", "published": "2026-10-03"}])
    await ex.explain("nfl", "g1")
    assert llm.call_count == 1


async def test_a_validation_failure_template_is_not_retried(tmp_path, no_news, monkeypatch):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good(headline="A 70% chance")))
    monkeypatch.setattr("explainer.service.TEMPLATE_RETRY_SECONDS", -1)
    ex = make(tmp_path)
    await ex.explain("nfl", "g1")
    await ex.explain("nfl", "g1")
    assert llm.call_count == 2


async def test_no_key_template_is_retried_once_a_key_exists(tmp_path, no_news, monkeypatch):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))
    ex = make(tmp_path, key=None)
    assert (await ex.explain("nfl", "g1"))["source"] == "template"
    ex.settings.openrouter_api_key = "k"
    monkeypatch.setattr("explainer.service.TEMPLATE_RETRY_SECONDS", -1)
    assert (await ex.explain("nfl", "g1"))["source"] == "llm" and llm.call_count == 1


# Minors
def test_percent_only_matches_fractions_or_written_percents():
    f = json.dumps(facts())  # record hits 41
    assert any("41%" in p for p in validate(good(headline="Right 41% of the time"), f, "[]"))


def test_integer_cannot_round_a_half_point_line_or_a_probability():
    f = facts(); f["markets"].append({"market": "total", "model_total": 47.8, "line": 45.5})
    fj = json.dumps(f)
    assert validate(good(headline="Line near 46 at 62%"), fj, "[]")
    assert validate(good(headline="Won 1-0 at 62%"), fj, "[]")
    assert validate(good(headline="Total near 48 at 62%"), fj, "[]") == []


async def test_answer_drops_numbers_used_and_stringifies_titles(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    g = good(); g["sections"][0]["title"] = ["Pick"]
    no_news.post(OPENROUTER_URL).mock(return_value=reply(g))
    out = await make(tmp_path).explain("nfl", "g1")
    assert out["source"] == "llm"
    assert all("numbers_used" not in s for s in out["sections"])
    assert all(isinstance(s["title"], str) and isinstance(s["market"], str) for s in out["sections"])


async def test_id_is_quoted_into_the_sport_api_url(tmp_path, no_news):
    route = no_news.get("http://nfl.test/api/facts/a%3Fb").mock(return_value=httpx.Response(404))
    from explainer.service import NotFound
    with pytest.raises(NotFound):
        await make(tmp_path).explain("nfl", "a?b")
    assert route.called
