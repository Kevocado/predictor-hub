"""The fallback when no model is available, over budget, or its output fails
validation: a verdict and a few factors built only from the facts.

**Same shape as the model's answer, on purpose.** The panel's layout is driven
by the data it is handed and does not know whether a model was involved, so
there is exactly one renderer and the two paths cannot drift apart in the reader's
eyes. That is the whole of spec §8: template parity is a property of the design
rather than of how carefully this file is written.

So the template reads the same `market_keys` the panel resolves against, and
every factor it emits names one of them. A factor pointing at a market the facts
lack would have to render as a dash, and spec §6 says an absent market renders
*nothing*.

Facts fields beyond the contract's core are loose dicts, so every read here is
defensive: this is the last resort and it must never raise.
"""
from __future__ import annotations

from .contract import as_dict, band_for, market_shape, pick_prob

_TENS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
#: How each sport names the moment the game begins. NBA says "tip-off" in its
#: prompts (`prompts.py` `SPORT_NOTES`) and in the record label the panel renders,
#: so a sentence reading "rebuilt after kickoff" sat next to "picks made before
#: tip-off" on the same screen. The default is kept for the two football sports
#: rather than listing them, so a new sport gets a sensible word instead of
#: `KeyError`.
_START = {"f1": "the session started", "pl": "kickoff", "nba": "tip-off"}
MAX_FACTORS = 4


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _pct(p: float) -> str:
    if p <= 0.005:
        return "<1%"
    if p >= 0.995:
        return ">99%"
    return f"{round(p * 100)}%"


def _dicts(xs) -> list[dict]:
    return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []


def _fact(key: str, direction: str, headline: str, text: str) -> dict:
    return {"key": key, "direction": direction, "headline": headline, "text": text}


def _outcome_key(by_key: dict) -> str:
    """The market a pick or an outcome belongs to, for use as a factor `key`.

    PL's three-way market is literally named `result`; NFL's and CFB's outcome is
    a top-level `result` with the pick's market named `moneyline`. So a factor
    about the pick or how it finished cannot just be keyed `result` — for NFL
    that names a market the facts do not carry, and the panel would resolve it to
    nothing and render an empty row. Same trap as `contract.market_shape`, and
    for the same reason.
    """
    if "result" in by_key:
        return "result"
    if "moneyline" in by_key:
        return "moneyline"
    return "context"


def _quoted_line(market: dict | None) -> str | None:
    """The line a READER can check against a book, from whichever key this sport
    used to put it in.

    The key `line` means two different things across the family. NFL and CFB put
    the market's line in it (`"BAL -2.5"`) and have no `market_line`. NBA puts the
    MODEL's own projected margin there (`"BOS by 4.2"`, or the literal `"Toss-up"`
    when the margin rounds to nothing) and the market's line in `market_line`.

    Reading `line` as the market's is therefore right for two sports and wrong for
    one, and for NBA it renders the model compared with itself: *"It rates BOS 4.2
    points better, against a line of BOS by 4.2."* That is the same failure as
    narrating a prediction without its timing, so the two are not adjacent
    concerns -- they are the same rule.

    `market_line` wins when both are present, because the quoted line is the one a
    reader can check and the model's own wording is not. Neither key means there is
    no disagreement to narrate, and the caller omits the factor rather than
    inventing one.

    **Numbers are accepted, not just strings.** A total's `line` is a float --
    `{"market": "total", "line": 45.5}` -- while a spread's is a worded string. The
    first version of this helper type-checked for `str` and silently dropped the
    total factor for every sport, which `test_template_covers_markets_and_the_record`
    caught immediately. A truthy check is the honest one here: `0` and `False` are
    not lines anything would be quoted against.
    """
    if not market:
        return None
    for key in ("market_line", "line"):
        value = market.get(key)
        if isinstance(value, str):
            # Stripped before the truthiness test, so a whitespace-only line falls
            # through instead of rendering "against a line of    .". An earlier
            # version of this loop also had an explicit
            # `if value is None or value == "": continue`, which was dead -- the
            # truthy test below already rejects `None`, `""`, `0` and `[]`. It
            # survived a mutation check that reported it as covered, because
            # removing it changed nothing at all. One check, not two.
            value = value.strip()
        if value:
            return str(value)
    return None


def explain_from_template(facts: dict) -> dict:
    """The no-model path, in the model's own shape, built from the facts."""
    facts = as_dict(facts)
    title = str(facts.get("title") or "This match")
    pick = facts.get("pick") if isinstance(facts.get("pick"), dict) else {}
    label = pick.get("label")
    label = str(label) if label not in (None, "") else None
    prob = pick_prob(facts)
    sport = facts.get("sport", "")
    unit = "goals" if sport == "pl" else "points"
    timing = facts.get("pick_timing")
    by_key = {str(m.get("market")): m for m in _dicts(facts.get("markets")) if m.get("market")}

    factors: list[dict] = []

    # How it finished. Before the pick factor, because a finished game is the one
    # thing a reader opening the panel is actually asking.
    result = facts.get("result") if isinstance(facts.get("result"), dict) else None
    if facts.get("status") == "final" and result and result.get("score"):
        text = f"Final: {result['score']}."
        # Only a pick made before the start is judged. The facts omit `pick_won`
        # for a rebuilt pick precisely so nothing can grade it.
        if timing == "pre_kickoff" and isinstance(result.get("pick_won"), bool) and label:
            text += f" The pick was {'right' if result['pick_won'] else 'wrong'}: {label}."
        factors.append(_fact(_outcome_key(by_key), "up", "How it finished", text))

    # A rebuilt pick is disclosed as a factor in its own right, so it cannot be
    # missed by a reader who only reads the first row.
    if timing == "rebuilt":
        factors.append(_fact(
            "context", "down", "Rebuilt after the start",
            f"This pick was rebuilt after {_START.get(sport, 'kickoff')}, so it is shown but "
            f"not counted, and it is not graded either way."))

    if label and prob is not None:
        factors.append(_fact(_outcome_key(by_key), "up", "The pick",
                             f"The model makes {label} the pick at {_pct(prob)}."))

    margin_market = by_key.get("spread") or by_key.get("handicap")
    margin = _num((margin_market or {}).get("model_margin"))
    quoted = _quoted_line(margin_market)
    if margin_market is not None and margin is not None and label and quoted:
        line = quoted
        # down: the market asking for more than the model rates the gap is a
        # point *against* the pick, which is what `direction` means.
        factors.append(_fact(str(margin_market["market"]), "down", "The line",
                             f"It rates {label} {abs(margin):g} {unit} better, against a line of {line}. "
                             f"That is the market asking for more than the model thinks the gap is worth."))

    total_market = by_key.get("total") or by_key.get("total_goals")
    total = _num((total_market or {}).get("model_total"))
    total_line = _quoted_line(total_market)
    if total_market is not None and total is not None and total_line is not None:
        factors.append(_fact(str(total_market["market"]), "up", "The total",
                             f"It projects {total:g} {unit} against a line of {total_line}."))

    btts = by_key.get("btts")
    yes = _num((btts or {}).get("yes_prob"))
    if btts is not None and yes is not None:
        factors.append(_fact("btts", "up", "Both to score",
                             f"It puts {_pct(yes)} on both teams scoring."))

    # The record states counts, never a proportion. It is a factor here as well as
    # a panel extra, but it goes LAST on purpose: there are four slots and a
    # bundle can carry three markets, so this is the one that gets sliced off
    # when there is no room. `record` is hits/settled and
    # the facts contain no percentage; the panel draws the bar's width from the
    # two numbers, and a derived "60.3%" here would be a figure no fact carries
    # (spec §5a-bis). This is also the one place "right"/"wrong" must not appear
    # for a rebuilt pick, which is why it says "recorded" rather than "correct".
    record = facts.get("record") if isinstance(facts.get("record"), dict) else None
    hits, settled = (_num(record.get("hits")), _num(record.get("settled"))) if record else (None, None)
    if hits is not None and settled:
        what = str(record.get("label") or "picks made before the start").lower()
        factors.append(_fact("record", "up", "Its record so far",
                             f"{int(hits)} of {int(settled)} {what} have landed."))

    # Two rows minimum, so the panel is never a single lonely line. Padding only
    # ever uses the pseudo-markets, which resolve regardless of what the facts
    # carry, and it says plainly that there is nothing there rather than
    # inventing a reason to read it.
    if len(factors) < 2:
        # Only `context` padding, and never a claim that something is missing when
        # it is present: an earlier draft padded with a `record` factor saying
        # "no settled record yet", which would have been false for exactly the
        # bundles that reach it.
        while len(factors) < 2:
            if not any(f["key"] == "context" for f in factors):
                factors.append(_fact("context", "down", "Not much to go on",
                                     "The facts for this one are still filling in."))
            else:
                factors.append(_fact("context", "up", "Where this stands",
                                     f"So there is little to weigh up here: {title}."))

    verdict = f"{label} is the pick." if label and prob is not None else "There is no pick for this one yet."
    return {"verdict": verdict, "band": band_for(prob, market_shape(facts)),
            "factors": factors[:MAX_FACTORS]}


def minimal(facts: dict) -> dict:
    """If even the template fails: say so, never error.

    Only the pseudo-markets, so every factor resolves against a bundle with no
    markets at all — this runs precisely when things are broken.
    """
    return {
        "verdict": "No explanation is available for this one yet.",
        "band": "leaning",
        "factors": [
            _fact("context", "down", "Not ready",
                  "The explanation service could not build a summary for this fixture."),
            _fact("context", "up", "Try again",
                  "A later visit may find the facts in place."),
        ],
    }
