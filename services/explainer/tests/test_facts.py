import pytest

from explainer.facts import Facts, render

BASE = dict(sport="nfl", id="g1", title="Chiefs at Ravens", starts_at="2026-10-05T00:20:00Z",
            status="upcoming", pick_timing="pre_kickoff", pick={"label": "BAL", "prob": 0.62},
            markets=[{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}])


def test_facts_accepts_sport_specific_market_fields():
    f = Facts(**BASE)
    assert f.markets[0].model_dump()["model_margin"] == 3.4


def test_render_is_stable_regardless_of_key_order():
    a = render(Facts(**BASE))
    b = render(Facts(**dict(reversed(list(BASE.items())))))
    assert a == b


def test_rebuilt_final_cannot_claim_the_pick_won():
    with pytest.raises(ValueError):
        Facts(**{**BASE, "status": "final", "pick_timing": "rebuilt", "result": {"score": "27-20", "pick_won": True}})


def test_unknown_sport_is_rejected():
    with pytest.raises(ValueError):
        Facts(**{**BASE, "sport": "mlb"})
