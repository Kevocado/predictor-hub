"""The quoted line is the MARKET's, whatever the sport calls the key.

The template writes two sentences that both attribute a line to the market:

    "It rates BOS 4.2 points better, against a line of BOS by 4.2."

and

    "It projects 226.5 against a line of 224.5."

Read across the five sports' `/facts` builders, the key `line` means **two
different things**:

| market        | `line`                        | `market_line`          |
|---------------|-------------------------------|------------------------|
| NFL, CFB      | the MARKET's line, `"BAL -2.5"` | absent               |
| NBA           | the MODEL's own wording, `"BOS by 4.2"` or `"Toss-up"` | the market's, `"BOS -3.5"` |
| PL            | absent (three-way result)     | absent                 |
| F1            | absent (unserved)             | absent                 |

So reading `line` as the market's is right for two sports and wrong for one, and
for NBA it produces the model compared with itself — which is the exact failure
`PRODUCT.md`'s "a pick shown without knowing when it was made" and the F1 refusal
both exist to prevent. Reached for the first time here, because NBA's template
never ran before this change.

**And it is silent.** The template gates the total factor on `line is not None`,
and NBA's total market has no `line`, so the factor is dropped without a word. A
reader sees a shorter explanation and has no way to know a figure was withheld.
"""
import pytest

from explainer.template import _quoted_line, explain_from_template

UNIT = {"nfl": "points", "cfb": "points", "nba": "points", "pl": "goals"}


def bundle(sport, markets, **over):
    base = {
        "sport": sport, "id": "g1", "title": "PHI at BOS",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "BOS", "prob": 0.62},
        "markets": markets, "drivers": [], "context": {}, "players": [],
        "record": {"label": "Picks made before tip-off", "hits": 30, "settled": 50},
        "result": None,
    }
    base.update(over)
    return base


def factor(body, key):
    return next((f for f in body["factors"] if f["key"] == key), None)


# --- the bug, in the shapes each sport actually emits ----------------------

def test_an_nba_spread_does_not_quote_the_model_back_at_itself():
    """The failure, verbatim from the real template output before the fix.

    "against a line of BOS by 4.2" -- the sentence claims a disagreement with the
    market and then quotes the model. The market's actual line is in `market_line`.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "spread", "model_margin": 4.2,
         "line": "BOS by 4.2", "market_line": "BOS -3.5"},
        {"market": "total", "model_total": 226.5, "market_line": "224.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "BOS -3.5" in text, f"the market's line is missing: {text}"
    assert "BOS by 4.2" not in text, f"the model is quoted as the market: {text}"


def test_a_toss_up_is_not_presented_as_a_market_line():
    """NBA's `_margin_line` returns the literal "Toss-up" when the margin rounds to
    nothing or points at a different team than the moneyline does. Rendered as
    "against a line of Toss-up" it is not a weak sentence, it is a sentence with no
    meaning in it -- and `PRODUCT.md` says uncertainty is shown, not dressed up.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.51, "PHI": 0.49}},
        {"market": "spread", "model_margin": 0.2, "line": "Toss-up", "market_line": "BOS -0.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "Toss-up" not in text, f"the model's own wording leaked into the prose: {text}"
    assert "BOS -0.5" in text, text


def test_nbas_total_factor_is_not_silently_dropped():
    """NBA's total market has no `line` at all, so the old gate
    (`total_market.get("line") is not None`) removed the factor without a word.

    The clause that matters is not "is the factor present" -- a total with no line
    anywhere legitimately has nothing to compare against -- but that a total WITH a
    quoted line is never dropped. Before the fix this was the second of the two
    ways NBA rendered short.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "total", "model_total": 226.5, "market_line": "224.5"},
    ]))
    f = factor(body, "total")
    assert f is not None, f"the total factor was dropped: {body['factors']}"
    assert "224.5" in f["text"], f["text"]


def test_a_total_with_no_quoted_line_is_still_omitted():
    """The other half. NBA's total also appears with no line when there is no
    quoted market total, and there is nothing to compare 226.5 against. Emitting
    "It projects 226.5" on its own would be a number with no disagreement
    attached, which is the same emptiness in a different shape.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "total", "model_total": 226.5},
    ]))
    assert factor(body, "total") is None, "a total with nothing to compare against should not be narrated"


# --- the three sports that already work must not change -------------------

def test_nfl_keeps_reading_its_line_key_as_the_market():
    """NFL and CFB put the MARKET's line in `line` and have no `market_line` at
    all, so the fix has to prefer `market_line` *without* requiring it. This is the
    case that would break first if the fix simply demanded the new key.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
        {"market": "total", "model_total": 47.8, "line": "44.5"},
    ]))
    assert "BAL -2.5" in factor(body, "spread")["text"]
    assert "44.5" in factor(body, "total")["text"]


def test_a_sport_with_both_keys_prefers_the_quoted_one():
    """If a sport ever fills both, the quoted line is the one a reader can check
    against a book, and the model's own wording is not. Pinned so the precedence
    is a decision rather than an accident of key order.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL by 3.4", "market_line": "BAL -2.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "BAL -2.5" in text, text
    assert "BAL by 3.4" not in text, text


def test_pl_is_unaffected():
    """PL has a three-way `result` market and a `total_goals` market with no line,
    so neither factor fires today and must not start firing on a fix meant for NBA.
    """
    body = explain_from_template(bundle("pl", [
        {"market": "result", "model": {"Arsenal": 0.48, "Draw": 0.26, "Chelsea": 0.26}},
        {"market": "total_goals", "model_total": 2.7},
    ]))
    assert factor(body, "spread") is None
    assert factor(body, "total") is None


# --- a regression this fix caused, and the reason it is pinned ------------

def test_a_numeric_total_line_is_still_read():
    """A total's `line` is a FLOAT, not a worded string.

    The first version of `_quoted_line` type-checked for `str`, and dropped the
    total factor for every sport -- NFL, CFB, all of them -- because 45.5 is not
    a string. `test_template_covers_markets_and_the_record` caught it, but that is
    luck rather than design: the suite happened to have an assertion on the
    total's figure.

    Pinned here so the narrowing cannot come back, and so the asymmetry between
    the two markets is written down where the helper is: a spread's line is
    wording ("BAL -2.5", "BOS by 4.2"), a total's is a number.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "total", "model_total": 47.8, "line": 45.5},
    ]))
    f = factor(body, "total")
    assert f is not None, f"the total factor was dropped for a numeric line: {body['factors']}"
    assert "45.5" in f["text"], f["text"]


def test_an_empty_line_is_treated_as_no_line():
    """`""` and `None` mean there is no line to quote. A factor built on one would
    read "against a line of ." — and `0` is not a line either, so it is not
    rendered as one."""
    assert _quoted_line({"market": "total", "line": ""}) is None
    assert _quoted_line({"market": "total", "line": None}) is None
    assert _quoted_line({"market": "total", "line": 0}) is None
    assert _quoted_line(None) is None
    assert _quoted_line({}) is None


def test_a_whitespace_only_line_is_treated_as_no_line():
    """Why `_quoted_line` strips before it tests, rather than testing first.

    The strip is the only reason a blank-looking line is rejected. Without it,
    `"   "` is truthy and the factor renders *"against a line of    ."* -- a
    sentence with nothing in it, which is the same emptiness the total-market
    guard above exists to prevent, reached through a different key.

    The earlier loop carried a second check for `None` and `""` alongside this
    one. It was dead, and a mutation check reported it as covered, because
    deleting it changed nothing -- which is the failure mode this whole file
    exists to catch, sitting inside the fix itself. So this pins the one check
    that is load-bearing.
    """
    assert _quoted_line({"market": "total", "line": "   "}) is None
    assert _quoted_line({"market": "spread", "market_line": "  ", "line": "BOS -3.5"}) == "BOS -3.5", (
        "a blank quoted line must fall through to the sport's own key, not end the search"
    )


def test_nbas_rebuilt_pick_says_tip_off_not_kickoff():
    """The panel says "tip-off" for NBA everywhere else, so this sentence must too.

    A rebuilt pick renders "This pick was rebuilt after {_START.get(sport, 'kickoff')}",
    and `_START` had no NBA entry -- so on an NBA game the panel read
    "rebuilt after kickoff" directly above a record labelled "picks made before
    tip-off". One screen, two words for the same moment, and only one of them
    right for the sport.
    """
    body = explain_from_template(bundle(
        "nba", [{"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}}],
        pick_timing="rebuilt"))
    text = " ".join(f["text"] for f in body["factors"])
    assert "tip-off" in text, text
    assert "kickoff" not in text, f"NBA must not be told in football's word: {text}"
