"""The spread factor states two numbers, and claims nothing about which is bigger.

The factor used to carry a second sentence that was a CONSTANT:

    It rates BOS 4.2 points better, against a line of BOS -3.5. That is the
    market asking for more than the model thinks the gap is worth.

Nothing in the template compares `model_margin` with the quoted line, so that
sentence was a comparison stated rather than computed -- true only when the
market happens to want more than the model does, and false otherwise. With
`model_margin = 4.2`:

| quoted line | "the market is asking for more" |
|-------------|--------------------------------|
| `BOS -3.5`  | FALSE -- the market asks 3.5, the model says 4.2, so it asks for LESS |
| `BOS -4.2`  | FALSE -- the two agree exactly |
| `BOS -6.0`  | true |

The first two are the common cases: a confident model is usually more bullish
than the market, so the shipped sentence is usually wrong about the direction of
the disagreement. And the deploy runs `EXPLAINER_ENABLED=false`, so this
template is the only prose a reader ever sees.

`direction: "down"` was the same error drawn as a mark, and wrong for the same
reason: `down` means "against the pick", which requires the market to be
*softer* than the model -- and "the market is softer than the model" is a point
FOR the pick. So the mark pointed the opposite way from the claim it was
justifying.

**What the tests below pin, and why a sweep.** The fix is to say only what the
numbers support, so the rendered sentence has to be the same for all three lines
above. That is stricter than "the sentence is not false in the common case": it
forbids the claim even in the one case where it would be true, because printing
it there and not elsewhere is a comparison only something computed could decide.
`QUOTES` is that sweep, and it is the reason a mutation that reinstates either
the sentence or the mark has nowhere to hide.

Every assertion here is on rendered output. None of them reads `template.py`,
and none of them greps a source file for a word -- a check that can be satisfied
by a comment, a string constant or a decoy is not a check on what a reader sees.
"""
from __future__ import annotations

import pytest

from explainer.contract import NEUTRAL
from explainer.template import explain_from_template

#: The model's own margin, held fixed while the quoted line moves underneath it.
MARGIN = 4.2
QUOTES = [
    pytest.param("BOS -3.5", id="market asks for less than the model rates"),
    pytest.param("BOS -4.2", id="the two agree exactly"),
    pytest.param("BOS -6.0", id="market asks for more than the model rates"),
]


def _bundle(sport: str, markets: list, label: str = "BOS", **over) -> dict:
    """A bundle shaped like the one each sport's `/facts` builder really emits.

    `pick_timing` and a finished-free `status` are set so the rebuilt and final
    factors cannot fire and displace the one under test: the spread factor is
    the third candidate here, and a padding row reaching `MAX_FACTORS` first
    would make a failure read as a displacement instead of a wrong sentence.
    """
    base = {
        "sport": sport, "id": "g1", "title": "MIA at BOS",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": label, "prob": 0.62},
        "markets": markets, "drivers": [], "context": {}, "players": [],
        "record": None, "result": None,
    }
    base.update(over)
    return base


def _nba(quoted: str) -> dict:
    """NBA's shape: `line` is the MODEL's own wording, `market_line` the book's."""
    return _bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
        {"market": "spread", "model_margin": MARGIN,
         "line": "BOS by 4.2", "market_line": quoted},
    ])


def _spread(facts: dict) -> dict:
    """The spread factor, or a failure that says what rendered instead.

    The lookup is on the emitted `key`, not on position, so a factor that moved
    or was dropped is reported as missing rather than silently compared against
    whichever row took its place.
    """
    body = explain_from_template(facts)
    found = [f for f in body["factors"] if f["key"] == "spread"]
    assert len(found) == 1, (
        f"expected exactly one spread factor, found {len(found)}: {body['factors']}"
    )
    return found[0]


# --- the two honest numbers, and only them ---------------------------------

@pytest.mark.parametrize("quoted", QUOTES)
def test_the_spread_factor_is_the_two_numbers_and_nothing_else(quoted):
    """Exact equality, so a reinstated clause fails however it is worded.

    The previous test suite had no assertion on this sentence beyond "3.4 points
    better" and "BAL -2.5" are present, which the false sentence did not break:
    it only ever ADDED words, so every existing check stayed green while the
    claim shipped. Equality cannot be satisfied by a superset.
    """
    assert _spread(_nba(quoted))["text"] == (
        f"It rates BOS {MARGIN:g} points better, against a line of {quoted}."
    )


@pytest.mark.parametrize("quoted", QUOTES)
def test_the_spread_factor_claims_no_direction(quoted):
    """`neutral`, for all three lines, including the one where `down` would fit.

    The mark is not a decoration on the sentence: `up`/`down` is what the panel
    draws a triangle and a "for the pick" / "against it" word from, so a mark
    the two numbers do not support is the same false claim in a louder form. The
    third case is in the sweep precisely because the mark would be *correct*
    there -- which is how a constant mark survives a spot check.
    """
    factor = _spread(_nba(quoted))
    assert factor["direction"] == NEUTRAL, (
        f"a {factor['direction']!r} mark on a quoted {quoted!r} is a claim about which "
        f"of the two numbers is bigger, and nothing in the template computes it: {factor}"
    )


def test_the_sentence_cannot_depend_on_the_comparison():
    """The sweep as one assertion, so "it happens to be right here" is not enough.

    Three lines whose only difference is whether the market wants more, less, or
    exactly as much as the model. Prose making that comparison has to differ in
    at least one of them; requiring all three sentences to be identical once the
    quoted token is masked is a statement about the code -- the template is not
    comparing them -- rather than about today's wording.
    """
    lines = ["BOS -3.5", "BOS -4.2", "BOS -6.0"]
    masked = {_spread(_nba(line))["text"].replace(line, "<line>") for line in lines}
    assert len(masked) == 1, f"the sentence varies with the two numbers: {sorted(masked)}"


# --- not just NBA ----------------------------------------------------------

@pytest.mark.parametrize("sport,model_margin,line,label,expected", [
    # NFL and CFB put the MARKET's line in `line` and have no `market_line`.
    ("nfl", 3.4, "BAL -2.5", "BAL", "It rates BAL 3.4 points better, against a line of BAL -2.5."),
    ("cfb", 3.4, "BAL -2.5", "BAL", "It rates BAL 3.4 points better, against a line of BAL -2.5."),
])
def test_every_sport_that_renders_the_factor_gets_the_honest_one(sport, model_margin, line,
                                                                 label, expected):
    """The clause was not NBA's bug; NBA only made it reachable in a new shape.

    NFL and CFB have quoted this sentence since before NBA was served, so a fix
    that only lands on the `market_line` path would leave two of the four served
    sports still telling readers the market disagrees with the model. PL and F1
    are absent by construction -- a three-way `result` market and an unserved
    sport, neither of which carries a spread -- and
    `test_template_quoted_line.test_pl_is_unaffected` is what pins that.
    """
    facts = _bundle(sport, [
        {"market": "moneyline", "model": {label: 0.62, "X": 0.38}},
        {"market": "spread", "model_margin": model_margin, "line": line},
    ], label=label)
    factor = _spread(facts)
    assert factor["text"] == expected
    assert factor["direction"] == NEUTRAL, f"[{sport}] {factor}"


def test_a_negative_model_margin_is_written_as_a_magnitude():
    """`model_margin` is home-minus-away, so it is negative when the away side is
    favoured, and the sentence has to read "4.2 better", never "-4.2 better".

    Found by mutation: dropping the `abs()` left the whole suite green, because
    every bundle any test builds has a POSITIVE margin. `abs(margin)` was the only
    arithmetic in the sentence, and nothing covered it.

    **This asserts the FORMATTING and nothing else, on purpose.** Which team's gap
    the number belongs to is NOT pinned here, because it is not derivable from the
    bundle: the facts carry `model_margin` and a moneyline `model` dict, and no
    home/away designation, so with `model_margin: -4.2` and a pick of BOS the
    rendered "It rates BOS 4.2 points better" may be attributing the away side's
    margin to the home side. NBA's own builder is where that comparison happens --
    it returns the literal "Toss-up" when the win model and the margin model point
    at different teams -- and all that survives into the facts is the wording, so
    the template cannot make the call. Asserting the full sentence here would pin
    a claim that may be false; that is a separate defect, reported rather than
    pinned.
    """
    facts = _nba("MIA -3.5")
    facts["markets"][1]["model_margin"] = -MARGIN
    text = _spread(facts)["text"]
    assert f"{MARGIN:g}" in text, f"the magnitude is missing: {text}"
    assert f"-{MARGIN:g}" not in text, f"a negative margin was written as a signed gap: {text}"
