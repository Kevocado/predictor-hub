"""The template path's Edge and Risk rows (AI plan Task 5).

The template is what a reader gets with the model off, so the redesign has to
work here or it does not work at all for most games: `context.matchups` arrives
from the sport API either way, and the deterministic path has to turn the same
rows into the same slots the model path gets.

Three properties are load-bearing here and none of them is about the wording:

* **Edge is the strongest duel toward the pick, Risk the strongest against it**,
  and `toward_pick` is the CODE's word. The template reads it and never works it
  out from the duel's direction, because the duel's own direction is a statement
  about the two teams, not about the pick.
* **Every figure the row prints is in the facts.** The ranks and the league size
  come out of the matchup row, so they are in the bundle and the validator's
  number pool already carries them — but only if the template prints exactly
  those and no derived figure, which is why there is no "a 25-place gap" wording
  here.
* **A duel the code declined to direct is `neutral` context**, never Edge or
  Risk. Before the lift gate has run for a duel type, `toward_pick` is `None`,
  and every matchup row on the page is context until it says otherwise.
"""
from explainer.template import explain_from_template

DUEL = lambda i, toward: {"id": i, "attacker": "Bills", "defender": "Jets", "stat": "passing offence",
                          "foil": "pass defence", "attacker_rank": 3, "defender_rank": 28,
                          "n_teams": 32, "toward_pick": toward}  # noqa: E731


def _facts(matchups):
    return {"sport": "nfl", "id": "g1", "title": "Bills at Jets", "starts_at": "2026-10-11T17:00:00Z",
            "status": "upcoming", "pick_timing": "pre_kickoff",
            "pick": {"label": "Bills", "side": "home", "prob": 0.64},
            "markets": [{"market": "moneyline", "home_prob": 0.64}],
            "context": {"matchups": matchups}}


def _rows(out):
    return [(f["slot"], f["key"]) for f in out["factors"] if f["key"].startswith("matchup:")]


def test_edge_and_risk_rows_come_from_the_duels_toward_and_against_the_pick():
    out = explain_from_template(_facts([DUEL("a", True), DUEL("b", False)]))
    assert ("edge", "matchup:a") in _rows(out) and ("risk", "matchup:b") in _rows(out)


def test_the_row_text_states_the_ranks_from_facts():
    out = explain_from_template(_facts([DUEL("a", True)]))
    row = next(f for f in out["factors"] if f["key"] == "matchup:a")
    assert "3" in row["headline"] and "28" in row["headline"]


def test_a_duel_the_code_did_not_direct_is_a_neutral_context_row():
    out = explain_from_template(_facts([DUEL("n", None)]))
    row = next(f for f in out["factors"] if f["key"] == "matchup:n")
    assert row["direction"] == "neutral" and row["slot"] == "context"


def test_every_factor_carries_a_slot():
    out = explain_from_template(_facts([DUEL("a", True), DUEL("b", False), DUEL("n", None)]))
    assert out["factors"] and all(f.get("slot") for f in out["factors"])


def test_no_duels_means_no_matchup_rows_and_no_padding_about_them():
    out = explain_from_template(_facts([]))
    assert not _rows(out)


def test_the_strongest_duel_toward_the_pick_is_the_edge_row():
    """Rows arrive strongest first, and the template reads that order rather than
    ranking: the code already did the ranking (`Duel.strength`).

    The second duel toward the pick is dropped rather than emitted second, because
    the design allows at most two Edge rows and the second one is never the one a
    reader should act on. Asserted so a later "and now emit them all" is a
    failure rather than a quiet widening of the panel.
    """
    out = explain_from_template(_facts([DUEL("a", True), DUEL("a2", True)]))
    assert [k for _, k in _rows(out)] == ["matchup:a"]


def test_a_bundle_with_no_matchups_still_resolves_every_row():
    """The pseudo-markets and the market rows are unaffected: a sport that sends
    no duels gets exactly the body it got before.
    """
    facts = _facts([])
    out = explain_from_template(facts)
    assert {f["slot"] for f in out["factors"]} <= {"edge", "risk", "price", "context"}
    assert 2 <= len(out["factors"]) <= 4