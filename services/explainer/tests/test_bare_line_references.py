"""A book quote is a book quote however the sentence names it.

The review found this live: NBA's game detail served "Very close to the line."
for a game whose facts quote nothing at all. #41 added the market-word rule and
covered "the market line of BOS by 1.9" — and the same sentence with "the
market" dropped in front of "line" walked straight through, because the rule
anchored on a phrase that had to name the market explicitly.

That asymmetry is the bug. It is not a style preference: there is no principle
by which "the market line" is a claim about a book and "the line" is not, when
both are saying the same thing and the facts carry no quote to support either.

**The over-reach risk is the whole difficulty here, and this file has already
made the mistake once** — a bare "line" trigger rejected "the line between
favourite and also-ran" and was fixed in #41. So every phrase below is
unambiguous by construction, and the ordinary-English cases are asserted as
tests rather than assumed.
"""
import pytest

from explainer.validate import _market_problems

from test_market_words import NBA_FACTS, PL_FACTS


# --- the live leak, and its siblings --------------------------------------------

@pytest.mark.parametrize("text", [
    # The exact sentence from the review, verbatim.
    "Very close to the line.",
    "The number is a shade below the model figure.",
    "That's a pick'em game.",
    "That is a pick em game.",
    "The market has it a point lower.",
    "Just off the line on the spread.",
    "The line sits at 220.",
    "The total sits under the number.",
    "A quick number favours Boston.",
    "It's on the line at the half.",
    "Under the line all afternoon.",
])
def test_a_bare_book_reference_is_caught(text):
    problems = _market_problems(NBA_FACTS, text)
    assert problems, (
        f"{text!r} names a book figure NBA's facts do not quote, and passed. The "
        f"market-word rule anchors on 'the market line' and this is the same "
        f"sentence with the words dropped."
    )
    assert any("market" in p for p in problems), problems


def test_the_live_sentence_is_caught_through_validate():
    """Through the real entry point, not the private helper.

    A guard that is wired up wrong looks identical to one that works when every
    test calls the helper directly — the failure this repo's own handover warns
    about, and one this rule has already been bitten by.
    """
    import json

    from explainer.validate import validate

    out = {
        "verdict": "Boston are favoured here.",
        "band": "moderate",
        "factors": [
            {"key": "context", "direction": "up", "headline": "Margin",
             "text": "Very close to the line."},
            {"key": "context", "direction": "neutral", "headline": "Form",
             "text": "Boston have been consistent."},
        ],
        "source": "llm", "model": "m",
        "generated_at": "2026-09-29T00:00:00Z", "sport": "nba",
        "pick_timing": "pre_kickoff",
    }
    problems = validate(out, json.dumps(NBA_FACTS), "[]")
    assert any("market" in p for p in problems), (
        f"validate() accepted a bare book reference: {problems}"
    )


# --- the over-reach, which is the reason this list is phrases -------------------

@pytest.mark.parametrize("text", [
    # The sentence that broke the previous attempt at this, verbatim.
    "The line between favourite and also-ran is thinner than usual.",
    "Both teams sit on the same line this season.",
    "The line to beat is a steep climb.",
    "A good number of passes found the target.",
    "The number of attempts speaks for itself.",
    "Total commitment from midfield.",
    "The implied order was never in doubt.",
])
def test_ordinary_english_is_still_not_a_claim(text):
    """The control, and the reason every trigger is two words or more.

    A bare "line", "number" or "total" would catch all of these. They are the
    sentences a model writes when it is being honest and unremarkable, and a
    guard that rejects them teaches it to write less — the same outcome as the
    dishonesty the guard exists to prevent.
    """
    assert _market_problems(NBA_FACTS, text) == [], (
        f"honest prose rejected: {text!r} -> {_market_problems(NBA_FACTS, text)}"
    )


# --- and the case that means the most -------------------------------------------

def test_a_quoted_market_makes_every_one_of_them_honest_again():
    """The control on the whole rule.

    On a sport whose facts DO quote a line, every sentence above is a legitimate
    comparison. If these were rejected here the guard would be wrong in the
    common case and right only in the rare one.
    """
    quoted = dict(NBA_FACTS, markets=[
        {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
        {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
         "market_line": "BOS by 2.0"},
        {"market": "total", "model_total": 220.4, "market_line": 221.5},
    ])
    for text in ("Very close to the line.", "The number is a shade below.",
                 "The line sits at 221.5."):
        assert _market_problems(quoted, text) == [], (
            f"rejected a legitimate comparison where a quote exists: {text!r}"
        )


def test_pl_prose_naming_its_own_quoted_line_is_untouched():
    """PL puts the market's goals line in `line`, so these are its sentences."""
    for text in ("Very close to the line.", "The total sits under the number."):
        assert _market_problems(PL_FACTS, text) == [], f"rejected: {text!r}"
