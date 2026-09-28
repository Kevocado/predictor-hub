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
"""
from __future__ import annotations

import math

VERDICT_BANDS = ("leaning", "moderate", "strong")

#: The direction that claims nothing about the pick. It is a real value rather
#: than an absence because the panel still has to draw a row, and because "there
#: is no pick to be for or against" is itself a thing worth saying.
NEUTRAL = "neutral"

#: `up` is a factor arguing FOR the pick, `down` one arguing AGAINST it, and
#: `neutral` one that is neither -- a statement about the game (the total, both
#: teams to score) or about the record, neither of which is for or against
#: anything. The third value exists because a factor with no pick-relative
#: meaning used to be handed one anyway, and the one it was handed was a mark
#: the sentence did not support.
DIRECTIONS = ("up", "down", NEUTRAL)
#: Things a factor may point at that are not markets in `facts["markets"]`.
PSEUDO_MARKETS = ("record", "context")

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
            "direction": f.get("direction") if f.get("direction") in DIRECTIONS else "up",
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


def resolve_factors(verdict: dict, facts: dict) -> list[dict]:
    """Keep only the factors whose key names something the facts carry.

    An absent market renders *nothing* (spec §6), so a factor pointing at one
    would have to render a dash or a zero. Dropping it is the honest answer, and
    it is why this never raises: a key we do not recognise is a reason to show
    less, not to break.
    """
    allowed = market_keys(facts) | set(PSEUDO_MARKETS)
    return [f for f in verdict.get("factors") or [] if f.get("key") in allowed]
