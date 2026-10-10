"""A model that skips the null-direction duels must not erase the Matchup rows."""
from explainer.service import _clean
from explainer.template import MAX_FACTORS

from test_template_matchups import DUEL, _facts


def _body(n):
    keys = ["moneyline", "spread", "total", "record", "context"][:n]
    return {"verdict": "Bills are the pick.", "factors": [
        {"key": k, "direction": "neutral", "headline": k, "text": k} for k in keys]}


def test_model_without_matchups_gets_neutral_rows_within_cap():
    facts = _facts([DUEL("pass_off_vs_pass_def:home", None), DUEL("rush_off_vs_rush_def:home", None)])
    facts["markets"] = [{"market": m, "home_prob": 0.6} for m in ("moneyline", "spread", "total")]
    out = _clean(_body(5), facts)["factors"]
    keys = [f["key"] for f in out]
    assert sum(k.startswith("matchup:") for k in keys) == 2
    assert len(out) <= MAX_FACTORS
    assert {"moneyline", "spread", "total"} <= set(keys)  # market rows survive; only context rows are trimmed


def test_model_matchups_are_left_alone():
    facts = _facts([DUEL("pass_off_vs_pass_def:home", None)])
    body = {"verdict": "v", "factors": [{"key": "matchup:pass_off_vs_pass_def:home", "direction": "neutral",
                                         "headline": "h", "text": "t"}]}
    assert [f["key"] for f in _clean(body, facts)["factors"]] == ["matchup:pass_off_vs_pass_def:home"]


def test_no_matchups_in_facts_changes_nothing():
    out = _clean(_body(2), _facts([]))["factors"]
    assert [f["key"] for f in out] == ["moneyline"]
