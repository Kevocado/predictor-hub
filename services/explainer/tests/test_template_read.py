"""The deterministic read: 2-3 neutral sentences from matchup rows, named players and form rows."""
import pytest

from explainer.service import _clean
from explainer.template import explain_from_template, tactical_read
from explainer.validate import validate

import json

DUELS = [
    {"id": "pass_off_vs_pass_def:home", "attacker": "Bills", "defender": "Jets", "stat": "passing offence",
     "foil": "pass defence", "attacker_rank": 3, "defender_rank": 28, "n_teams": 32, "toward_pick": None},
    {"id": "rush_off_vs_rush_def:away", "attacker": "Jets", "defender": "Bills", "stat": "rushing offence",
     "foil": "run defence", "attacker_rank": 19, "defender_rank": 6, "n_teams": 32, "toward_pick": True},
    {"id": "x", "attacker": "A", "defender": "B", "stat": "s", "foil": "f", "attacker_rank": 1, "defender_rank": 2,
     "n_teams": 32, "toward_pick": False},
]
PLAYERS = [{"team": "BUF", "name": "Josh Allen", "role": "top_passer", "stat": "passing yards", "value": 265},
           {"team": "NYJ", "name": "Breece Hall", "role": "top_rusher", "stat": "rushing yards", "value": 71}]
FORMS = [{"id": "q", "subject": "Norris", "label": "qualifying pace", "value": "+0.08s", "rank": 2, "n": 20},
         {"id": "t", "subject": "Norris", "label": "track history", "value": "2 podiums in 4", "rank": None, "n": None}]


def facts(**ctx):
    return {"sport": "nfl", "id": "g", "title": "Bills at Jets", "status": "upcoming", "pick_timing": "pre_kickoff",
            "starts_at": "2026-10-11T17:00:00Z", "pick": {"label": "Bills", "prob": 0.64},
            "markets": [{"market": "moneyline", "model": {"Bills": 0.64, "Jets": 0.36}}], "context": ctx}


def sentences(text):
    return [s for s in text.replace("?", ".").split(". ") if s.strip()]


def test_duels_and_players_make_three_sentences():
    r = tactical_read(facts(matchups=DUELS, player_context=PLAYERS))
    assert len(sentences(r)) == 3
    assert "Bills' passing offence ranks #3 of 32" in r and "Josh Allen (BUF) as a top passer" in r


def test_form_rows_state_value_and_rank_only_when_present():
    r = tactical_read(facts(form_rows=FORMS))
    assert "Norris' qualifying pace is +0.08s (#2 of 20)" in r
    assert "Norris' track history is 2 podiums in 4." in r  # no rank, so no "#"


def test_nothing_in_nothing_out():
    assert tactical_read(facts()) == ""
    assert tactical_read({"context": None}) == ""
    assert explain_from_template(facts())["read"] == ""


@pytest.mark.parametrize("toward", [None, True, False])
def test_it_never_says_advantage_or_favours(toward):
    rows = [{**DUELS[0], "toward_pick": toward}]
    r = tactical_read(facts(matchups=rows, player_context=PLAYERS)).lower()
    assert "advantage" not in r and "favour" not in r and "favor" not in r


def test_junk_rows_are_skipped():
    r = tactical_read(facts(matchups=[{"id": "a"}, "x", {**DUELS[0], "attacker_rank": None}],
                            player_context=[{"name": "N", "role": "kicker"}], form_rows=[{"subject": "s"}]))
    assert r == ""


def test_the_template_read_passes_the_validators_read_rules():
    f = facts(matchups=DUELS[:1], player_context=PLAYERS[:1])
    out = explain_from_template(f)
    assert validate({"verdict": out["verdict"], "read": out["read"]}, json.dumps(f), "[]") == []


def test_clean_keeps_verdict_and_read_only():
    assert _clean({"verdict": " v ", "read": " r. s. ", "factors": [1], "x": 2}, facts()) == \
        {"verdict": "v", "read": "r. s.", "factors": []}
    with pytest.raises(ValueError):
        _clean({"verdict": "v", "factors": []}, facts())
