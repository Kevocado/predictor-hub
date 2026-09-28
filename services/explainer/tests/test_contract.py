"""The v2 shape, and the band, in one place.

Two things live here that used to live nowhere:

* what a v2 answer *is* — a verdict and 2–4 factors that **reference** a market
  by key, never carry a figure. The panel resolves those references against the
  facts and draws the numbers itself, so the model has no way to supply one.
* the confidence band, which is **computed from the facts** rather than asked
  for. A v1.5 draft let the model choose it, on the reasoning that a band should
  not be a *number*. That reasoning was half right and missed the worse half: a
  band is a *word*, and nothing ties "strong" to anything, so a model can call a
  52% pick strong and the reader sees a confident sentence with no fact behind
  the confidence — the exact failure this redesign exists to remove.

Both are here rather than in `validate.py` or `service.py` so the validator, the
template and the service cannot disagree about them. Two copies of a rule would
agree today and drift the first time one of them was edited.
"""
import pytest

from explainer.contract import (DIRECTIONS, NEUTRAL, PSEUDO_MARKETS, VERDICT_BANDS, band_for,
                                clean_verdict, market_keys, market_shape,
                                resolve_factors)

# Shaped like the real NFL bundle (see spec §5c, verified against the live
# facts), because a hand-shaped double has been the root cause of four separate
# bugs in this project and the fifth is not worth the gamble.
FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}},
                {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}

# PL's shape: a three-way `result` MARKET, with a top-level `result` too.
PL_FACTS = {
    "sport": "pl", "id": "gw1", "title": "Arsenal v Chelsea",
    "status": "upcoming", "pick_timing": "pre_kickoff",
    "pick": {"side": "home", "label": "Arsenal", "prob": 0.45},
    "markets": [{"market": "result", "model": {"home_win": 0.45, "draw": 0.27, "away_win": 0.28}}],
    "result": {"score": None},
}


# --- the shape -------------------------------------------------------------

def test_the_vocabularies_are_closed():
    assert VERDICT_BANDS == ("leaning", "moderate", "strong")
    assert all(b.isalpha() for b in VERDICT_BANDS), "a numeric band is a figure no fact supports"
    # The third value is `NEUTRAL`, added for the spread factor. Its mark is a
    # claim about the pick -- `up` argues for it, `down` against -- and the
    # spread factor's two numbers say nothing about where the market sits, so
    # the only honest mark was the one that claims nothing. The panel has a
    # branch for it (it draws no triangle and says "context"), so this is a
    # value the whole stack already knows how to render, not a new one.
    #
    # Pinned here, exactly, because this is the only place the vocabulary is
    # decided: `test_template_v2` and `test_template_spread_claim` both read
    # `DIRECTIONS`, so appending to it would leave every direction guard green
    # while widening what the panel is asked to draw.
    assert DIRECTIONS == ("up", "down", NEUTRAL)
    assert NEUTRAL == "neutral", "the value the panel's `MARK` table is keyed on"
    assert PSEUDO_MARKETS == ("record", "context")


def test_clean_verdict_coerces_and_never_invents_a_key():
    out = clean_verdict({
        "verdict": "Baltimore is the pick.",
        "factors": [{"key": "spread", "direction": "up", "headline": "The line", "text": "Because."},
                    {"direction": "up", "headline": "No key", "text": "Dropped."}],
    })
    assert out["verdict"] == "Baltimore is the pick."
    assert [f["key"] for f in out["factors"]] == ["spread"], "a factor with no key survived"


def test_a_model_supplied_band_is_ignored_entirely():
    # `band` is not in the contract, but a model trained on the old shape emits
    # it anyway. Removing a field from a schema is not the same as refusing to
    # read it, and the second is the one that has to be tested.
    out = clean_verdict({"verdict": "v", "band": "strong", "factors": [
        {"key": "moneyline", "direction": "up", "headline": "h", "text": "t"}]})
    assert "band" not in out, "the model's band survived into the answer"


def test_an_unknown_direction_becomes_up_rather_than_being_dropped():
    out = clean_verdict({"verdict": "v", "factors": [
        {"key": "spread", "direction": "sideways", "headline": "h", "text": "t"}]})
    assert out["factors"][0]["direction"] == "up"
    # A factor is not dropped for a bad direction: `validate()` is what refuses
    # the answer, and a coercion here would hide that from it.


def test_an_unknown_key_is_kept_by_clean_and_dropped_by_resolve():
    """The two functions have different jobs, and the split is the point.

    `clean_verdict` only knows the *shape*, so it cannot tell a good key from a
    made-up one — and it must not try, or it would be re-deriving the facts
    behind the validator's back. `resolve_factors` is the one holding the facts,
    and it drops the key.

    Asserting this the other way round would make `clean_verdict` a
    half-validator, which is how a shape check and a truth check end up
    disagreeing about the same field. The first draft of this file did exactly
    that, and the layering was wrong.
    """
    cleaned = clean_verdict({"verdict": "v", "factors": [
        {"key": "quarterback_weather", "direction": "up", "headline": "h", "text": "t"}]})
    assert [f["key"] for f in cleaned["factors"]] == ["quarterback_weather"], (
        "clean_verdict dropped a factor for naming a market it cannot check"
    )
    # And resolution does not raise on a key it has never seen: a model
    # inventing a market name is a reason to show the reader less, not a
    # reason to fail their request.
    assert resolve_factors(cleaned, FACTS) == [], "an invented market survived resolution"
    assert resolve_factors(cleaned, {}) == []


def test_resolve_keeps_only_keys_the_facts_actually_carry():
    verdict = clean_verdict({"verdict": "v", "factors": [
        {"key": "moneyline", "direction": "up", "headline": "h", "text": "t"},
        {"key": "record", "direction": "down", "headline": "h", "text": "t"},
        {"key": "total", "direction": "up", "headline": "h", "text": "t"}]})
    resolved = resolve_factors(verdict, FACTS)
    assert [f["key"] for f in resolved] == ["moneyline", "record"], (
        "total is not in these facts and must be dropped, not rendered as a dash"
    )
    assert market_keys(FACTS) == {"moneyline", "spread"}


# --- the band --------------------------------------------------------------

def test_the_band_is_computed_from_the_probability_not_chosen():
    # Thresholds are the ones written in spec §13a, so this fails if anyone
    # retunes them silently.
    assert band_for(0.52, "two_way") == "moderate"
    assert band_for(0.61, "two_way") == "strong"
    assert band_for(0.51, "two_way") == "leaning"
    # A three-way market has no-edge near 0.333, not 0.50. Using the two-way
    # numbers here would call a 45% PL home win "leaning" and a 40% one
    # "strong", which is inverted.
    assert band_for(0.52, "three_way") == "strong"
    assert band_for(0.45, "three_way") == "moderate"
    assert band_for(0.39, "three_way") == "leaning"


def test_the_thresholds_are_exact_boundaries():
    """`>=`, not `>`. A 0.60 pick is strong or the band is off by a hair."""
    assert band_for(0.60, "two_way") == "strong"
    assert band_for(0.5999, "two_way") == "moderate"
    assert band_for(0.52, "two_way") == "moderate"
    assert band_for(0.5199, "two_way") == "leaning"
    assert band_for(0.50, "three_way") == "strong"
    assert band_for(0.4999, "three_way") == "moderate"
    assert band_for(0.40, "three_way") == "moderate"
    assert band_for(0.3999, "three_way") == "leaning"


def test_no_probability_gives_the_weakest_band_not_the_middle_one():
    # There is no pick, so there is no confidence to claim. Defaulting to
    # "moderate" would be inventing one.
    assert band_for(None, "two_way") == "leaning"
    assert band_for(None, "three_way") == "leaning"


def test_the_shape_is_read_from_the_markets_not_the_sport_name():
    assert market_shape(FACTS) == "two_way"
    assert market_shape(PL_FACTS) == "three_way"


def test_a_top_level_result_does_not_make_a_two_way_bundle_look_three_way():
    """The trap: NFL's facts carry a top-level `result` (the score) too.

    Keying on `result` without checking it is a *market* key would classify
    every finished NFL game as three-way, and the three-way thresholds are lower
    — so a 0.52 NFL pick would read "strong". The band would inflate precisely
    where the market is most familiar.
    """
    finished_nfl = {**FACTS, "status": "final",
                    "result": {"score": "24-17", "pick_won": True}}
    assert "result" not in market_keys(finished_nfl)
    assert market_shape(finished_nfl) == "two_way"
    assert band_for(0.52, market_shape(finished_nfl)) == "moderate"


def test_an_unrecognised_market_bundle_fails_toward_two_way():
    """Deliberately the *stricter* classification.

    Three-way thresholds are lower, so misreading a two-way market as three-way
    would let a 52% pick read "strong". The ambiguous case must fail toward the
    reading that cannot inflate confidence.
    """
    sparse = {"sport": "nfl", "markets": [{"market": "spread", "model_margin": 3.4}]}
    assert market_shape(sparse) == "two_way"
    assert band_for(0.52, market_shape(sparse)) == "moderate"


def test_a_probability_outside_zero_to_one_does_not_produce_a_band():
    """A malformed prob must not read as certainty.

    `pick.prob` is validated upstream, but the band is what a reader trusts, and
    a value of 1.4 or -0.2 is not a confidence at all. Treated as absent.
    """
    for bad in (1.4, -0.2, float("nan")):
        assert band_for(bad, "two_way") in VERDICT_BANDS, "sanity"
    assert band_for(1.4, "two_way") == "leaning"
    assert band_for(-0.2, "two_way") == "leaning"
    # NaN compares false against every threshold, so it would fall through to
    # "leaning" anyway -- but by accident rather than by decision, so it is
    # pinned here.
    assert band_for(float("nan"), "two_way") == "leaning"
