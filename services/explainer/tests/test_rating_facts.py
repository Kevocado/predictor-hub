"""AIS-2: matchups carry a source and a gap the reader cannot see above the panel.

The fixture detail already draws the two ranks. It does not draw the gap, and
nothing in the bundle says where the ranks came from. The explainer expands the
site's `context.matchups` into `context.rating_facts`, so the prompt and the
template can cite "a 25-place gap" without inventing it, and a fact without a
source is not a fact.
"""
import json

from explainer.facts import Facts, render
from explainer.validate import validate

BASE = {
    "sport": "nfl", "id": "g1", "title": "Bills at Jets",
    "starts_at": "2026-10-11T17:00:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "Bills", "prob": 0.64},
    "markets": [{"market": "spread", "model_margin": 6.5, "line": "BUF -3.5"}],
    "context": {
        "matchups": [
            {"id": "pass_off_vs_pass_def:home", "attacker": "Bills", "defender": "Jets",
             "stat": "passing offence", "foil": "pass defence", "attacker_rank": 3,
             "defender_rank": 28, "n_teams": 32, "toward_pick": None},
        ],
    },
}


def test_a_matchup_becomes_a_sourced_rating_fact_with_a_gap():
    f = Facts(**BASE)
    facts = f.context["rating_facts"]
    assert len(facts) == 1
    fact = facts[0]
    assert fact["attacker"] == "Bills"
    assert fact["defender"] == "Jets"
    assert fact["attack_rank"] == 3
    assert fact["defence_rank"] == 28
    assert fact["gap"] == 25
    assert fact["source"]


def test_the_gap_is_rendered_so_the_validator_can_see_it():
    rendered = json.loads(render(Facts(**BASE)))
    assert rendered["context"]["rating_facts"][0]["gap"] == 25


def test_a_row_without_both_ranks_is_not_a_fact():
    facts = Facts(**{**BASE, "context": {"matchups": [
        {"id": "x", "attacker": "Bills", "defender": "Jets", "stat": "passing offence",
         "foil": "pass defence", "attacker_rank": 3, "n_teams": 32},
    ]}})
    assert "rating_facts" not in facts.context


def test_a_bundle_with_no_matchups_carries_no_rating_facts():
    facts = Facts(**{**BASE, "context": {"conferences": "ACC at Big 12"}})
    assert "rating_facts" not in facts.context


def test_a_read_may_cite_the_gap_because_the_gap_is_a_fact():
    body = {"verdict": "Bills are the pick.",
            "read": "Buffalo's #3 passing offence meets the Jets' #28 pass defence, a 25-place gap. "
                    "Allen decides how it goes."}
    assert validate(body, render(Facts(**BASE)), "[]") == []


def test_a_read_may_not_cite_a_gap_the_facts_do_not_carry():
    body = {"verdict": "Bills are the pick.",
            "read": "Buffalo's #3 passing offence meets the Jets' #28 pass defence, a 26-place gap. "
                    "Allen decides how it goes."}
    assert any("not in the facts" in p for p in validate(body, render(Facts(**BASE)), "[]"))
