"""The v2 answer shape, and the band rule, defined once.

The model supplies words and ordering; it never supplies a number the panel
renders, and — per spec §13a — not the confidence band either. So a factor is a
*reference* to a market plus a direction, and the resolution of that reference
against the facts lives here: the one place that knows both vocabularies.

An unknown key drops the factor rather than raising. A model inventing a market
name is a reason to show the reader less, not a reason to fail their request.

The band is here for the same reason. The spec originally argued a band must not
be a *number*, because no fact supports one. That was half the argument: a band
is a **word**, and a word is the same defect with less checking, since nothing
ties "strong" to anything. So the band is computed from `pick.prob` by
`band_for`, and the model is never asked for one.

And the pick is here for that reason too, by `pick_for`. The panel has to know
which segment of a bar to emphasise, and a model asked to name its own pick can
disagree with the facts the verdict was computed from — which would leave the bar
emphasising a different side than the sentence describes. So the pick is read off
the facts, and `None` when the facts carry none, because the panel acts on its
absence.
"""
from __future__ import annotations

import math

VERDICT_BANDS = ("leaning", "moderate", "strong")

#: The direction that claims nothing about the pick. It is a real value rather
#: than an absence because the panel has to draw a row either way, and because
#: "there is no pick to be for or against" is itself a thing worth saying.
NEUTRAL = "neutral"

#: `up` is a factor arguing FOR the pick, `down` one arguing AGAINST it, and
#: `neutral` one that is neither — a statement about the game (the total, both
#: teams to score) or about the record, neither of which is for or against
#: anything. The third value exists because a factor with no pick-relative
#: meaning used to be given one anyway, and the one it was given was "up".
DIRECTIONS = ("up", "down", NEUTRAL)
#: Things a factor may point at that are not markets in `facts["markets"]`.
#:
#: **`pick` and `outcome` are here because `_outcome_key` can fall through, and
#: the two rows that call it have to be told apart when it does.** A served
#: sport's bundle can carry no market at all, or none of the three names
#: `_outcome_key` recognises -- each builder guards its pick market rather than
#: always emitting it, and ALL FIVE also have a `markets: [] if (started and
#: ...)` arm that returns an empty list outright, so this is reachable rather
#: than hypothetical. The measured table is in `tests/test_factor_keys.py`.
#:
#: The two rows pass their own name as `_outcome_key`'s `default`, which is what
#: stops them sharing a key: `FactorList` renders
#: `data-testid={`factor-${factor.key}`}` and lights on
#: `highlighted === factor.key`, so two factors under one key render two
#: elements with the same testid and light together. They are NOT allowed to
#: fall back to `context`, which is the padding and rebuilt-disclosure rows' key
#: and the padding loop's own "have I emitted one yet" sentinel.
#:
#: A factor keyed `pick` or `outcome` lights no figure, exactly as one keyed
#: `record` or `context` does. That is the honest outcome: the row says there is
#: a pick, and there is no market in the bundle for the panel to point at.
PSEUDO_MARKETS = ("record", "context", "pick", "outcome")

#: The band thresholds from spec §13a. Two-way and three-way differ because
#: no-edge is 0.50 when the pick's market has two outcomes and about 0.333 when
#: it has three — a three-way market has a draw, and ignoring that would call a
#: 45% home win "leaning" and a 40% one "strong", which is inverted.
#:
#: One table, called from `_answer` for the model path and from
#: `explain_from_template` for the default. A second hand-written ladder in
#: either place is how the two paths would drift, and drift there is exactly what
#: spec §8 forbids.
BAND_THRESHOLDS = {
    "two_way": {"strong": 0.60, "moderate": 0.52},
    "three_way": {"strong": 0.50, "moderate": 0.40},
}


def band_for(prob, shape: str) -> str:
    """The confidence word, derived. Never asked of the model.

    A `prob` that is absent, out of range, or NaN is treated as absent, and an
    absent probability means there is no pick — so there is no confidence to
    claim, and the weakest word is the only honest one. Anything else risks a
    malformed value reading as certainty.
    """
    if not isinstance(prob, (int, float)) or isinstance(prob, bool):
        return "leaning"
    if not math.isfinite(prob) or not 0.0 <= prob <= 1.0:
        return "leaning"
    limits = BAND_THRESHOLDS[shape]
    if prob >= limits["strong"]:
        return "strong"
    if prob >= limits["moderate"]:
        return "moderate"
    return "leaning"


def as_dict(facts) -> dict:
    """The facts as a plain dict, whether they arrived as one or as a model.

    `_answer` holds a validated `Facts` and `template.explain_from_template`
    holds `model_dump()` of the same thing, so both shapes reach this module.
    Normalising here means the accessors below are written once against one
    shape, rather than every caller remembering which one it holds — and
    `Facts.get` is an AttributeError at runtime, not a wrong answer, so the
    failure mode of getting this wrong is loud but late.
    """
    if isinstance(facts, dict):
        return facts
    dump = getattr(facts, "model_dump", None)
    if callable(dump):
        return dump()
    return {}


def pick_prob(facts) -> float | None:
    """The pick's probability, or None when there is no usable one.

    Shared by the service and the template so "what counts as a probability" is
    one decision. A non-numeric or out-of-range value is None, which
    `band_for` treats as no pick — the panel's weakest band, rather than a
    confidence invented from a value that cannot mean anything.
    """
    pick = as_dict(facts).get("pick")
    if not isinstance(pick, dict):
        return None
    prob = pick.get("prob")
    if not isinstance(prob, (int, float)) or isinstance(prob, bool):
        return None
    return float(prob) if math.isfinite(prob) and 0.0 <= prob <= 1.0 else None


def pick_for(facts) -> dict | None:
    """The pick's identity, derived from the facts. None when there is none.

    The panel has to know WHICH segment of a two-way bar to emphasise, and until
    this existed nothing in the answer said: the response carried the verdict and
    the factors but not the pick, so a renderer could only fall back on segment
    order — which emphasises the wrong side whenever the pick is the second one.

    Derived here for the same reason the band is. A model asked to name its own
    pick can disagree with the facts the verdict was computed from, and then the
    bar would emphasise a different segment than the verdict describes: the
    "right number, wrong attribution" shape. So the facts are the only source,
    and the panel follows them.

    `None` rather than a placeholder, because the renderer acts on the ABSENCE:
    a `{"label": ""}` or `{"label": null}` would still be an object to emphasise,
    and the failure this is here to prevent is emphasising a segment. `as_dict`
    above is what lets this read a pydantic `Facts` and a `model_dump()` alike.

    Gated on a usable label AND a usable probability — the same two things
    `pick_prob` and the template's verdict require — so "is there a pick" is one
    decision rather than three that can drift. A label with no probability is a
    half-written pick, and the answer says so in words ("There is no pick for this
    one yet."); carrying a `pick` beside that sentence would point the panel at a
    segment for a pick the verdict just denied.

    The probability is deliberately NOT in the result. The panel draws every
    figure from the facts itself (§5a-bis); a second copy here is a second thing
    that can disagree with the bar.
    """
    pick = as_dict(facts).get("pick")
    if not isinstance(pick, dict):
        return None
    raw = pick.get("label")
    label = str(raw) if raw not in (None, "") else None
    if not label or pick_prob(facts) is None:
        return None
    out = {"label": label}
    # `side` is PL's `home`/`away` against a draw; NFL's pick has none, and the
    # panel joins on the label either way, so this rides along when it is there
    # rather than being invented when it is not.
    side = pick.get("side")
    if isinstance(side, str) and side.strip():
        out["side"] = side.strip()
    return out


def market_keys(facts) -> set[str]:
    markets = as_dict(facts).get("markets")
    return {str(m.get("market")) for m in (markets or [])
            if isinstance(m, dict) and m.get("market")}


def market_shape(facts: dict) -> str:
    """Whether the pick's market has two outcomes or three.

    Read from the **market** keys, and defaulting to `two_way` on purpose. Two
    traps, both of which inflate confidence rather than merely mislabel it:

    * NFL's facts carry a top-level `result` (the score) as well as a `result`
      MARKET being PL's three-way one. Keying on the string alone would call
      every finished NFL game three-way.
    * An unrecognised bundle must not be assumed three-way, because the
      three-way thresholds are lower, so a 0.52 pick would read "strong".

    `two_way` is the reading that cannot inflate.
    """
    return "three_way" if "result" in market_keys(facts) else "two_way"


def _factors(body: dict) -> list[dict]:
    out = []
    for f in body.get("factors") or []:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key") or "").strip()
        if not key:
            continue
        out.append({
            "key": key,
            # NEUTRAL, not "up", for a direction this contract does not know.
            # "up" renders as "for the pick", so defaulting to it reads a model
            # that said nothing — or wrote something unknown — as having argued
            # FOR the pick. The neutral value fails closed: it claims nothing
            # rather than claiming the wrong thing.
            "direction": f.get("direction") if f.get("direction") in DIRECTIONS else NEUTRAL,
            "headline": str(f.get("headline") or ""),
            "text": str(f.get("text") or ""),
        })
    return out


def clean_verdict(body: dict) -> dict:
    """No `band` key, deliberately: the model does not supply one (§13a).

    A body carrying a `band` anyway is not rejected — rejecting would turn a
    cosmetic extra key into a failed reader's request — it is simply not read.
    """
    return {
        "verdict": str(body.get("verdict") or "").strip(),
        "factors": _factors(body),
    }


def matchup_rows(facts) -> dict:
    """The code-computed duels, keyed `matchup:<id>` — the factor vocabulary for
    offence-versus-defence matchups.

    Keyed by the SAME string a factor is keyed by, so resolution is one set
    membership rather than a prefix test. A prefix test would also accept
    `matchup:` with nothing behind it, and a duel id that happens to be a
    market's name is then indistinguishable from a market.
    """
    rows = (as_dict(facts).get("context") or {}).get("matchups") or []
    return {f"matchup:{r['id']}": r for r in rows
            if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]}


#: Where a factor is drawn, and what each place MEANS: `edge` argues for the pick,
#: `risk` against it, `price` is a statement about a quoted market, and `context`
#: is everything else -- a statement about the game, the record, or a duel the
#: code declined to direct. A named set rather than a free string because the
#: panel groups by it and an unrecognised value would render as nothing.
SLOTS = ("edge", "risk", "price", "context")


def slot_for(direction: str, key: str, facts) -> str:
    """Where this factor is drawn, and why it may not be anywhere more flattering.

    `edge` = argues for the pick, `risk` = argues against, `price` = a statement
    about a quoted market, else `context`.

    **A matchup row is directed by CODE, not by the model.** It is Edge only when
    `toward_pick` is `True` AND the model wrote `up`; Risk only when `toward_pick`
    is `False` AND the model wrote `down`. Anything else is `context`, which
    covers three distinct cases and they all fail the same way: a duel type that
    failed the residual-lift gate (`toward_pick: None`), a model direction that
    disagrees with the code, and a plain profile row. A model asked to rank its
    own factors could otherwise promote a duel the code declined to direct into
    an "Edge" heading, which is the one claim in the redesign that code is
    supposed to own.
    """
    row = matchup_rows(facts).get(key)
    if row is not None:
        toward = row.get("toward_pick")
        if direction == "up" and toward is True:
            return "edge"
        if direction == "down" and toward is False:
            return "risk"
        return "context"
    if direction == "up":
        return "edge"
    if direction == "down":
        return "risk"
    return "price" if key in market_keys(facts) else "context"


def resolve_factors(verdict: dict, facts: dict) -> list[dict]:
    """Keep only the factors whose key names something the facts carry, and stamp
    each with the slot it is drawn in.

    An absent market renders *nothing* (spec §6), so a factor pointing at one
    would have to render a dash or a zero. Dropping it is the honest answer, and
    it is why this never raises: a key we do not recognise is a reason to show
    less, not to break.

    The `slot` is stamped HERE rather than left to each renderer, because the
    model path and the template path both end up in this function's vocabulary
    and a slot computed twice is a slot that can disagree with itself. The
    template calls `slot_for` itself at the end of its own assembly (it builds
    rows rather than resolving them), and both go through this one function.
    """
    allowed = market_keys(facts) | set(PSEUDO_MARKETS) | set(matchup_rows(facts))
    return [{**f, "slot": slot_for(f.get("direction"), f.get("key"), facts)}
            for f in verdict.get("factors") or [] if f.get("key") in allowed]
