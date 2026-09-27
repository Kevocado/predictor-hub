"""The default and the model must reach the panel through one shape.

This is the test that makes "the template is just as good" structural rather
than aspirational. The panel's layout is driven by the data it is handed and
does not know whether a model was involved, so the two paths agreeing is not a
matter of writing a good template — it is a matter of both emitting the same
shape, and this is what checks that they do.
"""
import pytest

from explainer.contract import band_for, market_shape, resolve_factors
from explainer.template import explain_from_template, minimal

NFL = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}},
                {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}

PL = {
    "sport": "pl", "id": "gw1", "title": "Arsenal v Chelsea",
    "status": "upcoming", "pick_timing": "pre_kickoff",
    "pick": {"side": "home", "label": "Arsenal", "prob": 0.45},
    "markets": [{"market": "result", "model": {"home_win": 0.45, "draw": 0.27, "away_win": 0.28}},
                {"market": "total_goals", "model_total": 2.7, "line": 2.5}],
    "record": {"label": "Picks made before kickoff", "hits": 30, "settled": 55},
}

# The awkward bundle: a pick at 0.0, so any code path that defaults a missing
# probability to something confident is caught here.
NO_PICK = {**NFL, "pick": {"label": "BAL", "prob": 0.0}}

FINISHED = {**NFL, "status": "final", "result": {"score": "24-17", "pick_won": True}}
REBUILT = {**NFL, "pick_timing": "rebuilt"}


def _text(v) -> str:
    return " ".join([v["verdict"]] + [f["headline"] + " " + f["text"] for f in v["factors"]])


@pytest.mark.parametrize("facts", [NFL, PL, NO_PICK, FINISHED, REBUILT], ids=str)
def test_the_template_emits_the_v2_shape(facts):
    out = explain_from_template(facts)
    assert set(out) == {"verdict", "band", "factors"}, f"wrong shape: {sorted(out)}"
    assert out["band"] in ("leaning", "moderate", "strong")
    assert 2 <= len(out["factors"]) <= 4, f"{len(out['factors'])} factors"
    for f in out["factors"]:
        assert set(f) == {"key", "direction", "headline", "text"}, f"wrong factor shape: {sorted(f)}"
        assert f["direction"] in ("up", "down")
        assert f["headline"] and f["text"]


@pytest.mark.parametrize("facts", [NFL, PL, NO_PICK, FINISHED, REBUILT], ids=str)
def test_every_template_factor_resolves_against_the_facts(facts):
    """The point of the whole design.

    The template cannot name a market the panel would have to render as a dash,
    because it reads the same key list the panel resolves against. A template
    that did would put an empty row in the middle of a reader's explanation.
    """
    out = explain_from_template(facts)
    assert len(resolve_factors(out, facts)) == len(out["factors"]), (
        f"unresolvable factors: {[f['key'] for f in out['factors']]} against "
        f"{facts.get('markets')}"
    )


@pytest.mark.parametrize("prob", [0.0, 0.39, 0.40, 0.45, 0.51, 0.52, 0.60, 0.61, 0.99, None])
def test_the_template_band_comes_from_the_one_function(prob):
    """Swept, not spot-checked.

    A template carrying its own private threshold ladder passes any
    single-probability assertion and still drifts from the service's. The first
    draft of this plan had exactly that: `>= 0.6 / < 0.45`, hand-written, beside
    the service's own table.
    """
    facts = {**NFL, "pick": {"label": "BAL", "prob": prob}}
    assert explain_from_template(facts)["band"] == band_for(prob, "two_way"), (
        f"the template's band diverged from band_for at prob={prob}"
    )


def test_a_three_way_bundle_gets_the_three_way_thresholds():
    assert explain_from_template(PL)["band"] == band_for(0.45, "three_way") == "moderate"
    assert explain_from_template(NFL)["band"] == band_for(0.62, "two_way") == "strong"


def test_a_finished_game_says_how_it_went():
    out = explain_from_template(FINISHED)
    text = _text(out).lower()
    assert "24-17" in text, f"the score is missing from the template: {text}"
    assert "right" in text, f"a pre-kickoff pick that won was not called: {text}"


def test_a_rebuilt_pick_says_so_and_is_not_scored():
    """The pre-kickoff rule, inherited rather than re-implemented.

    The facts are careful about this: a rebuilt pick has no `pick_won` at all.
    The template must not imply it was graded.
    """
    out = explain_from_template(REBUILT)
    text = _text(out).lower()
    assert "rebuilt" in text, f"a rebuilt pick is not disclosed: {text}"
    assert "right" not in text and "wrong" not in text, (
        f"a rebuilt pick was graded: {text}"
    )


def test_no_derived_percentage_is_stated():
    """record is hits/settled; the proportion is the bar's width, not a figure.

    The facts contain no 60.3. Stating it would be the same class of error as a
    model inventing a number, and it is the mistake the first draft of the
    spec's own mocks made.
    """
    text = _text(explain_from_template(NFL))
    assert "60.3" not in text and "60%" not in text and "82%" not in text
    # The counts themselves are fine — they are in the facts.
    assert "41" in text and "68" in text


def test_the_template_never_raises_on_a_bare_bundle():
    """It is the last resort, so it must survive whatever the facts are."""
    for facts in ({}, {"sport": "nfl"}, {"markets": None}, {"markets": [{}]},
                  {"pick": "not a dict"}, {"pick": {"label": None, "prob": None}},
                  {"markets": [{"market": "moneyline"}]}, {"record": {}}):
        out = explain_from_template(facts)
        assert isinstance(out.get("verdict"), str) and out["verdict"]
        assert 2 <= len(out["factors"]) <= 4, f"{facts} gave {len(out['factors'])} factors"


def test_minimal_is_also_v2():
    out = minimal({"title": "Chiefs at Ravens"})
    assert set(out) == {"verdict", "band", "factors"}
    assert 2 <= len(out["factors"]) <= 4
    # Every factor must SURVIVE resolution against a bundle with no markets —
    # not the other way round. `resolve_factors` keeps the pseudo-markets, so the
    # check is that the count is unchanged. (The first draft of this assertion
    # was `== []`, which asks for the factors to be *dropped*; it failed for the
    # right reason and the assertion was backwards.)
    assert len(resolve_factors(out, {"markets": []})) == len(out["factors"]), (
        "the absolute fallback names a market, so the panel would render a row with "
        "nothing in it — this runs precisely when things are broken"
    )
