"""validate() on the v9 body: {verdict, read}.

The number pool, banned words, rebuilt/unknown-timing disclosure, verdict-claim
and market-word rules still run over the prose (their own files). This file owns
the shape, the read-length rules, and the new rule: a read may not restate the
pick probability, the spread, the total, the moneyline or rest days.
"""
import json

import pytest

from explainer.validate import MAX_READ_WORDS, numbers_in, validate

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Bills at Jets",
    "starts_at": "2026-10-11T17:00:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "Bills", "prob": 0.64},
    "markets": [{"market": "moneyline", "model": {"Bills": 0.64, "Jets": 0.36}},
                {"market": "spread", "model_margin": 6.5, "line": "BUF -3.5"},
                {"market": "total", "model_total": 44.5, "line": 43.5}],
    "context": {
        "home_rest_days": 10, "away_rest_days": 7,
        "matchups": [{"id": "pass_off_vs_pass_def:home", "attacker": "Bills", "defender": "Jets",
                      "stat": "passing offence", "foil": "pass defence", "attacker_rank": 3,
                      "defender_rank": 28, "n_teams": 32, "toward_pick": None}],
        "player_context": [{"team": "BUF", "name": "Josh Allen", "role": "top_passer",
                            "stat": "passing yards", "value": 265}],
    },
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}
F = json.dumps(FACTS)
READ = ("Buffalo's passing offence ranks #3 of 32 and meets a Jets pass defence ranked #28. "
        "Josh Allen is the passer to watch in that matchup.")


def body(read=READ, verdict="Bills are the pick."):
    return {"verdict": verdict, "read": read}


def test_an_honest_read_passes():
    assert validate(body(), F, "[]") == []


def test_a_figure_free_read_passes():
    assert validate(body("The Bills' passing game meets a weak pass defence. Allen decides how it goes."), F, "[]") == []


def test_extra_keys_are_ignored_and_factors_are_not_required():
    assert validate({**body(), "factors": [], "band": "strong"}, F, "[]") == []


@pytest.mark.parametrize("bad", [{"nope": 1}, {"verdict": "x"}, {"read": "x. y."}, {"verdict": "x", "read": 3},
                                 {"verdict": "x", "factors": []}])
def test_the_shape_needs_a_verdict_and_a_read(bad):
    assert validate(bad, F, "[]")


def test_read_length_rules():
    assert any("sentences" in p for p in validate(body("One sentence only."), F, "[]"))
    assert any("sentences" in p for p in validate(body("A. B. C. D."), F, "[]"))
    long = " ".join(["Word"] * (MAX_READ_WORDS // 2) + ["."]) + " " + " ".join(["word"] * (MAX_READ_WORDS // 2 + 1)) + "."
    assert any("words" in p for p in validate(body(long), F, "[]"))
    assert any("verdict" in p for p in validate(body(verdict="word " * 19), F, "[]"))


# --- the new rule: no restated market, probability or rest figure ------------

@pytest.mark.parametrize("figure", ["64%", "3.5", "43.5", "44.5", "6.5", "10", "36%"])
def test_a_read_that_restates_a_market_or_rest_figure_is_rejected(figure):
    problems = validate(body(f"The matchup is about {figure} of the story. Allen is the passer to watch."), F, "[]")
    assert any("restates" in p for p in problems), (figure, problems)


def test_the_verdict_may_name_the_pick_probability():
    assert validate(body(verdict="Bills are the pick at 64%."), F, "[]") == []


def test_a_rank_is_not_a_market_figure():
    assert validate(body("The #3 passing offence meets the #28 pass defence. It is one of 32 such duels."), F, "[]") == []


def test_a_player_stat_is_allowed():
    assert validate(body("Allen projects for 265 yards through the air. That is the figure the Jets must answer."), F, "[]") == []


def test_the_number_pool_still_applies():
    assert any("not in the facts" in p for p in validate(body("A 70-point swing. Allen decides it."), F, "[]"))


def test_a_figure_that_is_both_market_and_tactical_is_allowed():
    """Documented ceiling: value alone cannot say which it is. Here a rank of 3 and
    a spread of 3 are the same token."""
    f = json.loads(F)
    f["markets"][1]["line"] = "BUF -3"
    assert validate(body("The #3 passing offence meets the #28 pass defence. Allen is the passer to watch."),
                    json.dumps(f), "[]") == []


def test_rebuilt_must_say_so():
    rebuilt = json.dumps({**FACTS, "pick_timing": "rebuilt"})
    assert any("rebuilt" in p for p in validate(body(), rebuilt, "[]"))
    ok = body(READ + " This pick was rebuilt after kickoff.")
    assert not any("rebuilt" in p for p in validate({**ok, "read": ok["read"]}, rebuilt, "[]"))


def test_numbers_in_reads_percents_both_ways():
    assert {0.62, 62.0, -2.5, 6.0, 10.0} <= numbers_in("62% vs −2.5, 6/10")
