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

`direction` is relative to the pick, so with no pick there is nothing for a
factor to be for or against, and a factor that cannot be relative to anything
says `neutral` rather than reaching for "up" — see `_toward`. That is a rule
about every row below, not a special case for the rows that mention a pick: the
total, both-teams-to-score and the record are statements about the game and about
other picks, so they are `neutral` whether or not this one exists.

Facts fields beyond the contract's core are loose dicts, so every read here is
defensive: this is the last resort and it must never raise.
"""
from __future__ import annotations

from .contract import NEUTRAL, as_dict, band_for, market_shape, pick_for, pick_prob

_TENS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_START = {"f1": "the session started", "pl": "kickoff"}
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


def _toward(direction: str, has_pick: bool) -> str:
    """A pick-relative direction, or `neutral` when there is no pick to be relative to.

    `direction` means "for the pick" or "against it" and nothing else, so it is
    only knowable when there IS a pick. With no pick, "up" would render a factor
    that says nothing about any pick as one arguing for it, which is the defect
    this exists to remove — so the row claims nothing instead.
    """
    return direction if has_pick else NEUTRAL


def explain_from_template(facts: dict) -> dict:
    """The no-model path, in the model's own shape, built from the facts."""
    facts = as_dict(facts)
    title = str(facts.get("title") or "This match")
    pick = facts.get("pick") if isinstance(facts.get("pick"), dict) else {}
    label = pick.get("label")
    label = str(label) if label not in (None, "") else None
    prob = pick_prob(facts)
    # Whether there is a pick at all, from the same function the response's own
    # `pick` field is built by, so a factor can never point at a pick the answer
    # does not carry.
    has_pick = pick_for(facts) is not None
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
        factors.append(_fact(_outcome_key(by_key), _toward("up", has_pick), "How it finished", text))

    # A rebuilt pick is disclosed as a factor in its own right, so it cannot be
    # missed by a reader who only reads the first row.
    if timing == "rebuilt":
        factors.append(_fact(
            "context", _toward("down", has_pick), "Rebuilt after the start",
            f"This pick was rebuilt after {_START.get(sport, 'kickoff')}, so it is shown but "
            f"not counted, and it is not graded either way."))

    if label and prob is not None:
        factors.append(_fact(_outcome_key(by_key), "up", "The pick",
                             f"The model makes {label} the pick at {_pct(prob)}."))

    margin_market = by_key.get("spread") or by_key.get("handicap")
    margin = _num((margin_market or {}).get("model_margin"))
    if margin_market is not None and margin is not None and label and margin_market.get("line"):
        line = margin_market["line"]
        # down: the market asking for more than the model rates the gap is a
        # point *against* the pick, which is what `direction` means.
        factors.append(_fact(str(margin_market["market"]), _toward("down", has_pick), "The line",
                             f"It rates {label} {abs(margin):g} {unit} better, against a line of {line}. "
                             f"That is the market asking for more than the model thinks the gap is worth."))

    total_market = by_key.get("total") or by_key.get("total_goals")
    total = _num((total_market or {}).get("model_total"))
    if total_market is not None and total is not None and total_market.get("line") is not None:
        # A projection for the game, not a claim about the pick: emitted whether
        # or not there is one, so it can only be neutral.
        factors.append(_fact(str(total_market["market"]), NEUTRAL, "The total",
                             f"It projects {total:g} {unit} against a line of {total_market['line']}."))

    btts = by_key.get("btts")
    yes = _num((btts or {}).get("yes_prob"))
    if btts is not None and yes is not None:
        # As the total: a statement about the game, so neutral either way.
        factors.append(_fact("btts", NEUTRAL, "Both to score",
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
        # Neutral, and always: the record counts OTHER picks, so it is not
        # evidence for this one even when this one exists. Reading it as "for the
        # pick" would let a season's hits stand in for a match.
        factors.append(_fact("record", NEUTRAL, "Its record so far",
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
                factors.append(_fact("context", _toward("down", has_pick), "Not much to go on",
                                     "The facts for this one are still filling in."))
            else:
                # Neutral always. "So there is little to weigh up here" is not an
                # argument FOR a pick; it was given "up" because the row needed a
                # direction, and the words above it do not support one.
                factors.append(_fact("context", NEUTRAL, "Where this stands",
                                     f"So there is little to weigh up here: {title}."))

    verdict = f"{label} is the pick." if label and prob is not None else "There is no pick for this one yet."
    return {"verdict": verdict, "band": band_for(prob, market_shape(facts)),
            "factors": factors[:MAX_FACTORS]}


def minimal(facts: dict) -> dict:
    """If even the template fails: say so, never error.

    Only the pseudo-markets, so every factor resolves against a bundle with no
    markets at all — this runs precisely when things are broken. Both are
    `neutral`: there is no pick here to be for or against, and these rows are
    about the service rather than about any prediction.
    """
    return {
        "verdict": "No explanation is available for this one yet.",
        "band": "leaning",
        "factors": [
            _fact("context", NEUTRAL, "Not ready",
                  "The explanation service could not build a summary for this fixture."),
            _fact("context", NEUTRAL, "Try again",
                  "A later visit may find the facts in place."),
        ],
    }
