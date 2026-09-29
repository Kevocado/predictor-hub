"""Prose may not name a market the facts do not carry.

The number rules came first and are thorough: every digit in the prose is
checked against the facts and the news. This file is about the one thing they
cannot see — a market named in WORDS when the figure is real.

It is not hypothetical. Against NBA game 401909903 the deployed model wrote:

    verdict: "BOS favored at tip-off, but ORL has real shot."
    factor:  "The market line of BOS by 1.9 sits very close to the model's
              calculated margin of about 1.9 points."

That game's facts carry a `spread` market whose `line` is `"BOS by 1.9"` — the
MODEL's margin, not a quote. `template.MARKET_LINE_KEY` says so explicitly: for
NBA only `market_line` is the book's, and this game has none. So the sentence
told a reader the market and the model agreed, on the strength of one number
attributed to two sources. `1.9` is in the facts, so every pre-existing rule
passed. Nothing about the number was wrong; the CLAIM was.

Two directions are pinned, because a rule that only ever fires is a rule nobody
has checked:

* the exact live sentences are rejected, and the service falls back to the
  template;
* PL and NFL prose that names a market those facts DO carry still passes — a
  guard that rejected honest copy would push the model into saying less, which
  is its own failure.

And the over-reach cases, which are as important as the hit: "the line between
favourite and also-ran" must NOT be rejected. A rule keyed on the bare word
"line" would catch every honest sentence in the product to catch one false one.
"""
import json

import pytest

from explainer.contract import market_keys
from explainer.validate import _ATTRIBUTION_RE, _market_problems, _named_markets, validate

# --- the facts, as the deployed service received them -----------------------------
# NBA 401909903. `line` is the model's own wording; there is no `market_line`,
# which is the whole point: a number is present and unattributed to any book.
NBA_FACTS = {
    "sport": "nba",
    "id": "401909903",
    "status": "upcoming",
    "pick_timing": "pre_kickoff",
    "pick": {"label": "BOS", "prob": 0.652},
    "markets": [
        {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
        {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9"},
        {"market": "total", "model_total": 220.4},
    ],
    "drivers": [],
    "context": {},
}

PL_FACTS = {
    "sport": "pl",
    "id": "pl-1",
    "status": "upcoming",
    "pick_timing": "pre_kickoff",
    "pick": {"label": "Arsenal", "prob": 0.48},
    "markets": [
        {"market": "result", "model": {"Arsenal": 0.48, "Draw": 0.26, "Chelsea": 0.26}},
        # PL puts the MARKET's goals line in `line` (it is absent from
        # MARKET_LINE_KEY, so it gets the default two-key list), which is what
        # makes PL's total nameable and NBA's not.
        {"market": "total_goals", "model": 2.7, "line": 2.5},
        {"market": "btts", "model": 0.61},
    ],
    "drivers": [],
    "context": {},
}


def body(verdict: str, *texts: str) -> dict:
    """A minimal v2 body, so `_market_problems` is what is under test."""
    return {
        "verdict": verdict,
        "band": "moderate",
        "factors": [
            {"key": "context", "direction": "neutral", "headline": "h", "text": t}
            for t in texts
        ],
        "source": "llm",
        "model": "m",
        "generated_at": "2026-09-29T18:19:23Z",
        "sport": "nba",
        "pick_timing": "pre_kickoff",
    }


# --- the live failure -------------------------------------------------------------

def test_validate_itself_rejects_the_live_body_end_to_end():
    """THE test that matters, and the one the rest of this file failed to be.

    Every other case here calls `_market_problems` directly. That makes them
    good tests of the rule and useless as tests of the SHIPPED behaviour: with
    the `problems.extend(_market_problems(...))` line deleted from `validate`,
    this whole file stayed green — 503 passed with the guard not running at all.
    Verified by mutation, not assumed.

    The service calls `validate`, so this is the only call that exercises the
    path a reader's text actually takes. It goes through the real body, with the
    real NBA facts, and asserts the live sentences are in the returned problems.
    """
    out = {
        "verdict": "The model leans slightly toward Miami covering the spread",
        "band": "moderate",
        "factors": [
            {"key": "moneyline", "direction": "up", "headline": "Home edge",
             "text": "Model gives BOS a 65% chance to win."},
            {"key": "context", "direction": "neutral", "headline": "Record",
             "text": "The market line of BOS by 1.9 sits very close to the model's "
                     "calculated margin of about 1.9 points."},
        ],
        "source": "llm",
        "model": "m",
        "generated_at": "2026-09-29T18:19:23Z",
        "sport": "nba",
        "pick_timing": "pre_kickoff",
    }
    problems = validate(out, json.dumps(NBA_FACTS), "[]")
    assert problems, (
        "validate() accepted the live body. Either the market guard is not wired "
        "into validate(), or the template would be shown for text that invents a "
        "book quote."
    )
    assert any("market" in p for p in problems), problems


def test_validate_still_accepts_an_honest_body_through_the_same_path():
    """The control for the test above, and the reason the guard is safe to ship.

    Same entry point, same facts, honest prose about a market the facts quote:
    no problems. Without this, "always return a problem" would pass the first
    test and quietly turn every summary into a template row.
    """
    quoted = dict(NBA_FACTS, markets=[
        {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
        {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
         "market_line": "BOS by 2.0"},
    ])
    out = {
        "verdict": "Boston are favoured, and the market line is close.",
        "band": "moderate",
        "factors": [
            {"key": "moneyline", "direction": "up", "headline": "Home edge",
             "text": "Model gives BOS a 65% chance to win."},
            {"key": "spread", "direction": "neutral", "headline": "Line",
             "text": "The market line of BOS by 2.0 is near the model's margin."},
        ],
        "source": "llm", "model": "m", "generated_at": "2026-09-29T18:19:23Z",
        "sport": "nba", "pick_timing": "pre_kickoff",
    }
    assert validate(out, json.dumps(quoted), "[]") == []


def test_the_live_sentence_that_attributed_the_models_own_margin_to_the_market():
    """Verbatim from the deployed service, minus its numbers.

    The numbers are kept. That is the point: `1.9` passes the number rules, and
    the sentence is still false.
    """
    text = ("The market line of BOS by 1.9 sits very close to the model's "
            "calculated margin of about 1.9 points.")
    problems = _market_problems(NBA_FACTS, text)
    assert problems, "the live false sentence passed the validator"
    assert "spread" in problems[0]
    # It must not be filed as a number problem — that is what it is not.
    assert "number" not in problems[0]


def test_the_live_verdict_naming_a_market_the_facts_do_not_carry():
    """The second live sentence, from the review that raised this."""
    problems = _market_problems(
        NBA_FACTS, "The model leans slightly toward Miami covering the spread")
    assert problems
    assert "spread" in problems[0]


def test_a_bundle_with_no_markets_at_all_rejects_every_line_market():
    """A bare bundle: the strongest form of the same rule.

    `moneyline` is excluded because it is a probability market, not a line
    market — "the moneyline says so" names a thing, and the panel draws
    probability markets from the model without any book quote existing. Firing
    on it would reject the ordinary case to catch the extraordinary one.
    """
    empty = {"sport": "nfl", "markets": [], "pick": None}
    for text in ("the spread is tight", "over the total", "the total goals figure"):
        assert _market_problems(empty, text), f"{text!r} should name a missing market"
    # The attribution form fires regardless, because nothing at all is quoted.
    assert _market_problems(empty, "the market line sits at two and a half")


# --- the direction that matters just as much: honest copy must survive ------------

def test_pl_prose_naming_a_market_pl_carries_still_passes():
    """A guard that rejected honest copy would push the model into saying less,
    which is its own failure. PL carries result/total_goals/btts; prose about
    them must be untouched."""
    for text in (
        "The total goals figure is the tightest part of this one.",
        "Both teams to score is the pick's best support.",
        "The result market barely separates these two.",
    ):
        assert _market_problems(PL_FACTS, text) == [], f"honest PL prose rejected: {text!r}"


def test_nba_prose_naming_the_markets_nba_does_carry_still_passes():
    """NBA's markets ARE present, so naming them is fine — this is the
    `moneyline` case, and it is what stops the fix from banning the word."""
    for text in ("Boston is the moneyline favourite.", "The total projects near 220."):
        assert _market_problems(NBA_FACTS, text) == [], f"honest NBA prose rejected: {text!r}"


# --- over-reach: the false positives that would break the product -----------------

def test_the_word_line_on_its_own_is_never_a_market_claim():
    """The reason "line" is not a trigger word.

    It is ordinary English. A rule that fired on it would reject honest prose
    across every sport to catch one false sentence.
    """
    for text in (
        "the line between favourite and also-ran is thinner than usual",
        "Both teams sit on the same line this season.",
        "The line to beat is a steep climb.",
    ):
        assert _market_problems(NBA_FACTS, text) == [], f"false positive: {text!r}"


def test_record_and_context_are_not_quoted_markets():
    """`PSEUDO_MARKETS` are things the panel has by construction. Without the
    exclusion, "the record" reads as the total and honest prose is rejected."""
    text = "The record argues against a bet on this one."
    assert _market_problems(PL_FACTS, text) == []


def test_a_market_named_in_a_factor_key_is_not_prose_and_is_not_checked():
    """The key is the contract's business, not this guard's.

    A body whose factor `key` is a market PL does not carry is caught by
    `validate`'s key rule. Re-reporting it here would double-count one fault.
    """
    out = body("Arsenal are the pick.", "The total goals figure is tight.")
    out["factors"][0]["key"] = "spread"
    assert "market" not in validate(out, json.dumps(PL_FACTS), "[]")[0]


# --- the word mapping itself ------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("the spread is tight", "spread"),
    ("the handicap looks fair", "spread"),
    ("the moneyline favourite", "moneyline"),
    ("the money line", "moneyline"),
    ("over the total", "total"),
    ("the total goals figure", "total"),
    ("the implied probability", "implied"),
])
def test_each_spelling_maps_to_its_market(text, expected):
    """A bare word that names a market resolves to its concept.

    `covering` / `over-under` are NOT here: they assert something belongs to a
    book, which is the stronger and separately-tested claim. Mapping them as
    bare market words would let "Miami covering the spread" pass on a sport
    whose facts carry no spread at all.
    """
    assert expected in _named_markets(text)


@pytest.mark.parametrize("text", [
    "Miami covering the number",
    "it covers the spread",
    "the over/under is 220",
    "the market line of BOS by 1.9",
    "the book has it at two and a half",
])
def test_attribution_phrases_are_detected_as_attribution(text):
    """These say a figure belongs to a book, which is the claim under test."""
    assert _ATTRIBUTION_RE.search(text.lower()), f"{text!r} is an attribution and was not matched"


def test_a_word_the_model_may_use_without_naming_a_market_is_not_mapped():
    """The negative control for the mapping itself."""
    assert _named_markets("The home record is strong") == set()
    assert _named_markets("Both teams look good") == set()


def test_market_keys_is_what_gates_this():
    """The guard reads the contract's own vocabulary, so a market the panel can
    resolve is a market that may be named. Pinned so a future rename cannot
    silently make every mention unnameable."""
    assert "spread" in market_keys(NBA_FACTS)
    assert "spread" not in market_keys(PL_FACTS)
