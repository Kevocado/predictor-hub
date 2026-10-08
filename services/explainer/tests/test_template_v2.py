"""The default and the model must reach the panel through one shape.

This is the test that makes "the template is just as good" structural rather
than aspirational. The panel's layout is driven by the data it is handed and
does not know whether a model was involved, so the two paths agreeing is not a
matter of writing a good template — it is a matter of both emitting the same
shape, and this is what checks that they do.
"""
import pytest

from explainer.contract import (DIRECTIONS, NEUTRAL, SLOTS, band_for, market_shape, pick_for,
                                resolve_factors)
from explainer.template import MAX_FACTORS, explain_from_template, minimal

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
# probability to something confident is caught here. Note this is NOT a no-pick
# bundle: 0.0 is a usable probability, so there IS a pick here and the rows about
# the pick stay directional. The bundles with no pick at all are the ones below.
NO_PICK = {**NFL, "pick": {"label": "BAL", "prob": 0.0}}

FINISHED = {**NFL, "status": "final", "result": {"score": "24-17", "pick_won": True}}
REBUILT = {**NFL, "pick_timing": "rebuilt"}

# A PL bundle carrying every market the panel can draw, so the total and the
# both-teams-to-score rows are actually reachable. `PL` has no `btts`, and a rule
# about the btts direction that is never reached is not a test.
PL_FULL = {**PL, "markets": [*PL["markets"], {"market": "btts", "yes_prob": 0.61}]}

# No pick. `None` is what the `Facts` model allows and what a sport API sends
# when the model has not produced one — and it is the case the harness could not
# test, because `harness/main.tsx` writes its own factors by hand. A no-pick
# state there proves something about the harness fixture and nothing about what
# this function emits.
WITHOUT_PICK = {**PL_FULL, "pick": None}
WITHOUT_PICK_FINISHED = {**WITHOUT_PICK, "status": "final", "result": {"score": "1-1"}}
WITHOUT_PICK_REBUILT = {**WITHOUT_PICK, "pick_timing": "rebuilt"}
# A half-written pick: a label and no probability. The verdict says there is no
# pick, so nothing may be for or against one — but the label is there, so the
# line row is still emitted and used to read "against it".
WITHOUT_PROBABILITY = {**NFL, "pick": {"label": "BAL"}}
BARE = {"sport": "pl", "id": "gw2", "title": "Everton v Newcastle",
        "pick_timing": "none", "pick": None}

ALL = [NFL, PL, NO_PICK, FINISHED, REBUILT, PL_FULL,
       WITHOUT_PICK, WITHOUT_PICK_FINISHED, WITHOUT_PICK_REBUILT,
       WITHOUT_PROBABILITY, BARE]


def _text(v) -> str:
    return " ".join([v["verdict"]] + [f["headline"] + " " + f["text"] for f in v["factors"]])


def _directions(v) -> dict[str, str]:
    """headline -> direction, so a failure names the row that is wrong."""
    return {f["headline"]: f["direction"] for f in v["factors"]}


@pytest.mark.parametrize("facts", ALL, ids=str)
def test_the_template_emits_the_v2_shape(facts):
    out = explain_from_template(facts)
    assert set(out) == {"verdict", "band", "factors"}, f"wrong shape: {sorted(out)}"
    assert out["band"] in ("leaning", "moderate", "strong")
    # `MAX_FACTORS` rather than a literal, because this file's job is to check the
    # SHAPE of every row and the cap moved from 4 to 5 with the matchup redesign.
    # A literal `4` here would be a second copy of the cap that fails for a reason
    # having nothing to do with shape.
    assert 2 <= len(out["factors"]) <= MAX_FACTORS, f"{len(out['factors'])} factors"
    for f in out["factors"]:
        # `slot` joined the four contract fields with the Edge / Risk / Price
        # redesign. It is part of the response now and the panel groups by it, so
        # a row without one would render in whichever group its absence implies.
        assert set(f) == {"key", "direction", "headline", "text", "slot"}, \
            f"wrong factor shape: {sorted(f)}"
        assert f["slot"] in SLOTS, f"undrawable slot: {f['slot']!r}"
        # `DIRECTIONS` rather than a literal pair, from both directions: a second
        # copy of the vocabulary here is how a "neutral" row would have started
        # failing this file instead of the service, and a hardcoded `("up",
        # "down")` is what made the spread factor's `neutral` a shape failure
        # rather than a decision. The failure message names the undrawable value,
        # because "direction not in tuple" alone does not say which row did it.
        # `test_contract.test_the_vocabularies_are_closed` pins the CONTENTS, so
        # this is not a comparison against a constant nobody watches.
        assert f["direction"] in DIRECTIONS, f"undrawable direction: {f['direction']!r}"
        assert f["headline"] and f["text"]


@pytest.mark.parametrize("facts", ALL, ids=str)
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


# --- direction, and the no-pick case ----------------------------------------

def test_with_no_pick_nothing_is_for_or_against_one():
    """The real template path, with facts that have no pick.

    This is the test the harness could not be. Every row the template emits here
    used to carry "up", which the panel renders as "FOR THE PICK" — beside a
    verdict saying there is no pick at all. A factor that cannot be relative to a
    pick says `neutral`, and the assertion is over EVERY row rather than the one
    that was noticed, because the total and the record were wrong in exactly the
    same way as the row in the screenshot.
    """
    out = explain_from_template(WITHOUT_PICK)
    assert out["verdict"] == "There is no pick for this one yet.", out["verdict"]
    wrong = {h: d for h, d in _directions(out).items() if d != NEUTRAL}
    assert not wrong, (
        f"with no pick these rows are for or against one: {wrong}\nfull: {out}"
    )


@pytest.mark.parametrize("facts", [WITHOUT_PICK, WITHOUT_PICK_FINISHED,
                                   WITHOUT_PICK_REBUILT, WITHOUT_PROBABILITY, BARE],
                         ids=["no-pick", "no-pick-final", "no-pick-rebuilt",
                              "label-without-prob", "bare"])
def test_no_pick_bundle_emits_nothing_directional(facts):
    directions = _directions(explain_from_template(facts))
    wrong = {h: d for h, d in directions.items() if d != NEUTRAL}
    assert not wrong, f"{facts.get('pick_timing')}/{facts.get('pick')}: {wrong}"


def test_the_game_rows_are_still_there_without_a_pick():
    """The fix is the direction, not hiding the row.

    A projection for the total and a both-teams-to-score probability are true,
    useful statements about a match with no pick, and the panel has tiles for
    both. Dropping the rows to dodge the wording would be the dishonest fix: it
    would show a reader less because a word was wrong rather than because the
    number was.
    """
    out = explain_from_template(WITHOUT_PICK)
    headlines = _directions(out)
    assert "The total" in headlines and "Both to score" in headlines, headlines
    assert "The pick" not in headlines, headlines
    assert "2.7" in _text(out) and "61%" in _text(out), _text(out)


def test_a_row_about_the_game_is_neutral_even_when_there_is_a_pick():
    """Both halves of the rule, because the second is a judgement.

    The total, both teams to score and the record are statements about the game
    and about other picks, not about this one, so they carry no direction at all.
    "For the pick" beside "It projects 2.7 goals against a line of 2.5" tells the
    reader something they cannot check and that the words do not support: the pick
    is on the result market, and nothing here says which way it leans.
    """
    out = explain_from_template(PL_FULL)
    assert _directions(out) == {
        "The pick": "up",
        "The total": NEUTRAL,
        "Both to score": NEUTRAL,
        "Its record so far": NEUTRAL,
    }, _directions(out)


def test_the_rows_about_the_pick_still_carry_their_direction():
    """Neutral is not a demotion of everything.

    With a pick, the rows that really are for or against it keep saying so, or
    neutral would be a way of losing the panel's argument rather than a way of
    keeping it honest.

    **`"The line"` is `neutral` here, and this used to assert `"down"` for it.**
    That entry was not the point of this test -- the point is that a row which
    really is about the pick keeps its direction -- and the "down" was inherited
    from the template rather than argued for here. It was wrong: nothing in
    `template.py` compares `model_margin` against the quoted line, so "down"
    (which means "against the pick", i.e. a market SOFTER than the model) was a
    mark asserting a comparison that is never computed. `test_template_spread_claim`
    is the authority on that row now, and it says `neutral` for all three
    orderings of the two numbers.

    The intent is kept at full strength, and this is still an exact-equality
    assertion on the whole row set rather than a membership check, so a template
    that made "The pick" neutral to "balance" the rows would fail here. What is
    lost is one witness for "with a pick, a row about the line is still
    directional"; the two that remain -- "How it finished" and "Rebuilt after
    the start", one `up` and one `down` -- are the ones that were argued for, and
    they cover both directions of the vocabulary between them.
    """
    assert _directions(explain_from_template(NFL)) == {
        "The pick": "up",
        "The line": NEUTRAL,
        "Its record so far": NEUTRAL,
    }, _directions(explain_from_template(NFL))
    assert _directions(explain_from_template(FINISHED))["How it finished"] == "up", (
        f"{_directions(explain_from_template(FINISHED))}"
    )
    assert _directions(explain_from_template(REBUILT))["Rebuilt after the start"] == "down", (
        "a rebuilt pick is a reason not to lean on it, which is a real 'against'"
    )


def test_the_line_row_is_neutral_with_a_pick_and_without_one_alike():
    """The pair that distinguishes a constant from a `_toward` call.

    `NFL` has a full pick and `WITHOUT_PROBABILITY` has a label and no
    probability, so the two disagree about `has_pick` and agree about everything
    else the row reads. If the row were still `_toward("down", has_pick)` the two
    would differ -- `down` and `neutral` -- and this fails. They do not, so the
    row's direction does not consult the pick at all.

    This is the half of main's no-pick rule that the spread fix made
    unreachable: the rule is real and still applies to every OTHER row (see
    `test_no_pick_bundle_emits_nothing_directional`), but for THIS row the
    direction was already unavailable with a pick in hand, which is a stronger
    reason and reached earlier. Asserting it once, on one bundle, would have let
    the `_toward` call hide in here.
    """
    with_pick = _directions(explain_from_template(NFL))
    without_pick = _directions(explain_from_template(WITHOUT_PROBABILITY))
    assert with_pick["The line"] == NEUTRAL, with_pick
    assert without_pick["The line"] == NEUTRAL, without_pick


def test_a_finished_game_with_no_pick_is_neutral_not_up():
    """The one row that grades the pick, on a bundle with no pick to grade.

    It still reports the score — that is the thing a reader opening a finished
    panel is asking for — but with nothing to be right or wrong about, it is not
    a point FOR the pick.
    """
    out = explain_from_template(WITHOUT_PICK_FINISHED)
    assert "1-1" in _text(out), _text(out)
    assert _directions(out)["How it finished"] == NEUTRAL, _directions(out)


def test_a_label_without_a_probability_gives_neutral_where_it_names_a_side():
    """The half-written pick, which is where the two tests of "a pick" differ.

    The verdict says there is no pick, so the line row cannot read "against it"
    even though the label is there for it to name. This is the row the panel
    would have pointed at the pick for, so it is the row where being wrong is
    visible rather than merely wrong.

    **What this now rests on.** When this was written the row's direction was
    `_toward("down", has_pick)`, so this test was the only thing standing between
    a half-written pick and a row reading "against it" — and if `_toward` had
    been dropped, this would have failed. It no longer would: the row's direction
    is a constant `NEUTRAL` (see the spread fix), so the assertion holds
    whatever `has_pick` is. Kept, because the verdict/label half of the claim is
    still worth stating and still holds, but it is no longer a guard on
    `has_pick`. The guard that is, for this row, is the with/without pair in
    `test_the_line_row_is_neutral_with_a_pick_and_without_one_alike`; for every
    other row it is `test_no_pick_bundle_emits_nothing_directional`.
    """
    out = explain_from_template(WITHOUT_PROBABILITY)
    assert out["verdict"] == "There is no pick for this one yet."
    assert pick_for(WITHOUT_PROBABILITY) is None
    assert _directions(out)["The line"] == NEUTRAL, _directions(out)


def test_minimal_claims_nothing_about_a_pick():
    """The last resort has no pick either, and never did.

    "Not ready" used to be "down" and "Try again" "up", so a reader whose
    explanation failed outright was told the service had a case against the pick
    and a case for it.
    """
    out = minimal({"title": "Chiefs at Ravens"})
    assert set(_directions(out).values()) == {NEUTRAL}, _directions(out)


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
