"""A written sign is a claim. The validator has to read it.

`model_margin: 3.4` and `line: "BAL -2.5"` are both facts, and the prose is
allowed to cite either — but they are not the same kind of fact. A margin's sign
is a convention (home minus away), so "Chelsea by 3.4" and "-3.4" describe the
same thing. A **line's** sign is the claim: "BAL -2.5" says Baltimore gives
points, and "BAL +2.5" says they receive them. Those are opposite predictions
about the same game.

The old `_known` compared magnitudes with `abs()` on both sides, so it accepted
every sign for every number. Measured on a real bundle:

    pool: [-2.5, 3.4]
      3.4  accepted
     -3.4  accepted      <- legitimate: the margin from the other side
      2.5  accepted      <- the bare magnitude of the line
     -2.5  accepted      <- correct
     +2.5  accepted      <- THE BUG: Baltimore RECEIVING 2.5, not giving

So the fix is not "stop using abs" — that would reject honest prose about a
margin from the other team's side, and a false rejection is its own failure. The
fix is that the tokenizer must report **whether a sign was written**, and a
written sign must match a fact's sign, except against a margin where the sign is
a convention.

This file pins all four cases, because the tempting over-correction is to reject
`-3.4` and a test that only checks the bug will not notice.
"""
import json

import pytest

from conftest import rule_validate as validate

# The shape §5c gives NFL: a margin and a line, which is exactly the pair where
# the two sign rules differ.
FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "status": "upcoming", "pick_timing": "pre_kickoff",
    "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
                {"market": "total", "model_total": 45.2, "line": 44.5}],
}
F = json.dumps(FACTS)


def _v(*texts: str) -> dict:
    return {"verdict": "Baltimore is the pick.",
            "factors": [{"key": "spread", "direction": "up", "headline": "The line", "text": t}
                        for t in texts]}


def _unknown(*texts: str) -> list[str]:
    return [p for p in validate(_v(*texts), F, "[]") if "number not in" in p]


# --- the bug ---------------------------------------------------------------

def test_a_written_sign_contradicting_a_line_is_rejected():
    problems = _unknown("Baltimore is +2.5 for this one.")
    assert problems, "a flipped line sign passed; the facts say BAL -2.5"


def test_a_written_sign_matching_the_line_is_accepted():
    assert _unknown("The line is BAL -2.5.") == []


def test_the_unicode_minus_is_a_minus_not_a_plus():
    """The gap a mutation found and this file did not.

    `_written_sign` first mapped U+2212 MINUS SIGN to **+1**, so every "−2.50"
    in honest prose was read as "+2.50" and rejected as a sign flip against its
    own fact. The existing suite caught it — and the six sign tests in THIS file
    all passed with it broken, because every one of them writes an ASCII hyphen.
    A test file about signs that never uses the typographic minus is testing half
    the language the product actually renders, since `fmt` emits U+2212.
    """
    assert _unknown("The line is \u22122.5.") == []
    assert _unknown("It rates Baltimore \u22122.5 better.") == []
    assert _unknown("It rates Baltimore \u22122.5 better.") == [], (
        "a unicode minus about a margin must read as a minus"
    )


def test_the_bare_magnitude_of_a_line_is_accepted():
    # "2.5" is a magnitude, not a sign claim, and people say it that way. Only an
    # explicit + or - is a claim about which way the line runs.
    assert _unknown("The line is 2.5 points.") == []


# --- and the cases an over-correction would break ----------------------------

def test_a_margin_may_be_written_from_the_other_side():
    """The false rejection this fix must not cause.

    `model_margin: 3.4` is home-minus-away, so a sentence about the away team
    legitimately carries the other sign. Rejecting it would push the model toward
    vague prose, and a false rejection costs a reader their explanation.
    """
    assert _unknown("It rates Baltimore 3.4 better.") == []
    assert _unknown("It rates Baltimore -3.4 better.") == []


def test_a_margin_may_also_be_written_with_no_sign():
    assert _unknown("The gap is 3.4 points.") == []


def test_an_unsigned_line_does_not_borrow_a_flip_from_being_numeric():
    # `line: 44.5` is a number rather than a string, and it is still a line with a
    # direction: the facts say the total is 44.5 and nothing more, so "-44.5" is a
    # claim they do not support. The first draft of this test asserted the
    # opposite — it was named "does not gain a flip" and then asserted the value
    # was ACCEPTED, which is the opposite of the name. The implementation caught
    # the inversion; a test that cannot be wrong about its own name is not a test.
    assert _unknown("It is -44.5 at the total.") != []
    assert _unknown("It is 44.5 at the total.") == []


def test_the_pick_probability_is_unaffected():
    # 62% goes down the percent branch, which never had a sign problem. Pinning it
    # so a change to the sign handling cannot quietly break the commonest figure.
    assert _unknown("The model has Baltimore at 62%.") == []
    assert _unknown("The model has Baltimore at 63%.") != []


def test_a_percentage_with_a_written_sign_is_rejected():
    # -62% is not a thing anyone means, and accepting it would be a free pass for
    # any sign flip dressed as a percentage.
    assert _unknown("Baltimore at -62%.") != []
