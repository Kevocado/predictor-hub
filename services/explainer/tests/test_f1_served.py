"""F1 is served, and what it says about a session is true.

This reverses a recorded decision. `SERVED_SPORTS` omitted `f1` because "a win
probability IS the explanation" -- which remains true of the win probability, and
was never an argument against the race story around it. The reversal is recorded
in the spec and in the ledger; this file is its enforcement.

F1's facts carry `win`, `podium`, `points` and `dnf` and NO line, so the spread
and total factors must not fire. That is not a degradation: a `KeyNumberTile`
comparing the model to a book would have nothing honest to draw, which was the
original reason, and it still holds for THOSE elements.
"""
from explainer.config import SERVED_SPORTS
from explainer.template import explain_from_template


def _f1_facts(**over):
    base = {
        "sport": "f1", "id": "s1", "title": "2026 Bahrain Grand Prix",
        "starts_at": "2026-03-15T15:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "Lando Norris", "prob": 0.34},
        "markets": [
            {"market": "win", "model": {
                "Lando Norris": 0.34, "Max Verstappen": 0.29, "Oscar Piastri": 0.24}},
            {"market": "podium", "model": {"Lando Norris": 0.88}},
        ],
        "drivers": [{"name": "Lando Norris"}, {"name": "Max Verstappen"}],
        "context": {}, "players": [],
        "record": {"label": "Picks made before the session", "hits": 9, "settled": 20},
        "result": None,
    }
    base.update(over)
    return base


def test_f1_is_served():
    assert "f1" in SERVED_SPORTS, (
        f"f1 is not in SERVED_SPORTS={SERVED_SPORTS}. The refusal was reversed: "
        f"a win probability is the explanation, but the race story around it is "
        f"not, and F1's facts carry it."
    )


def test_f1_gets_a_pick_and_a_record_and_nothing_it_cannot_support():
    out = explain_from_template(_f1_facts())
    keys = [f["key"] for f in out["factors"]]
    assert keys, f"F1 produced no factors at all: {out}"
    assert "spread" not in keys, (
        f"F1 has no spread market and no line; a spread factor here would be "
        f"narrating a disagreement with a book that quoted nothing: {keys}"
    )
    assert "total" not in keys, f"F1's `points` market is not a `total`: {keys}"


def test_f1_names_the_session_not_a_kickoff():
    """A rebuilt session says the session, because `_START["f1"]` exists for
    exactly that and the default would say "kickoff"."""
    out = explain_from_template(_f1_facts(pick_timing="rebuilt"))
    text = " ".join(f["text"] for f in out["factors"])
    assert "after the session started" in text, text
    assert "kickoff" not in text, text
