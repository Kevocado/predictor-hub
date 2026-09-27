"""The hub's one read: what each sport picks next, how sure, and how it has done.

The hub was five same-size link cards, which is the one place in the product that
answered none of the three questions `PRODUCT.md` says a game surface answers
first. A reader had to leave it to learn whether there was a reason to stay. This
is the data for that, and it is deliberately **not** an explanation: a pick, a
computed band and a record, per sport.

Which is why it covers all five sports while `/explain` serves three. Refusing to
write prose for a sport with no panel specified is a different decision from
declining to say which way the model leans, and coupling them would mean the hub
silently drops two sports because a *writing* decision excluded them.

**Why here and not in the hub.** The hub is one static `index.html` with no build
step. Putting this in the explainer means one endpoint instead of five, no CORS
headers on five APIs, and the read sits beside the component that already fetches
facts bundles and already owns the band arithmetic.

Three things this module refuses to do, each of which is a test:

- **Believe a band from the payload.** `band_for` computes it from the pick's
  probability and the market's shape (spec §13a). A bundle may carry a `band`
  key; it is ignored, because the payload is the part of the system a future
  change might let a model fill in.
- **Turn an absent record into a zero.** NBA has no settled record yet and says
  so with `record: null`. `0/0` reads as "wrong every time", which is a claim
  about a record that does not exist.
- **Echo an upstream body into a reason.** Every other proxy in this family
  refuses to, for the reason PL's states: an upstream error can carry an
  internal path. The reason is a fixed phrase plus a machine-readable
  `reason_kind`, so a reader sees words and an operator can still tell an
  offseason sport from a broken API — which matters, because those two look
  identical as a bare "unavailable".
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
from pydantic import ValidationError

from .config import SPORTS
from .contract import as_dict, band_for, market_shape
from .facts import Facts

#: The same window the deploy smoke check uses, so "upcoming" means one thing in
#: both places. A second definition here would let the two disagree about which
#: fixture is next.
UPCOMING_HOURS = 336

TIMEOUT = 15.0

#: Reader-facing, fixed, and identical in shape to every other failure message in
#: the family. `reason_kind` carries the machine-readable half.
REASONS = {
    "no_fixture": "no fixture scheduled in the next two weeks",
    "unreachable": "the sport's service could not be reached",
    "not_answered": "the sport's service did not answer",
    "bad_contract": "the sport's facts did not match the contract",
    "no_pick_label": "the sport's pick carries a figure but names no side",
    # Deliberately NOT worded as a contract problem. A bug in this module would
    # otherwise be reported as "the sport's facts did not match", which sends an
    # operator to the wrong repository to look for bad data that is perfectly
    # good. Same reason the Caddy fix in Sports_Predictor stops echoing an
    # upstream body: the message is a claim about who is at fault.
    "internal": "the hub could not read this sport",
}


def _fail(sport: str, kind: str) -> dict[str, Any]:
    return {"sport": sport, "ok": False, "pick": None, "record": None,
            "band": None, "reason": REASONS[kind], "reason_kind": kind}


def _shape(sport: str, facts: Facts) -> dict[str, Any]:
    body = as_dict(facts)
    pick = body.get("pick") or None
    timing = body.get("pick_timing")
    label = pick.get("label") if isinstance(pick, dict) else None
    prob = pick.get("prob") if isinstance(pick, dict) else None

    # Three states that look alike and are not, kept apart because they are three
    # different bugs (or not a bug):
    #
    #   no pick, timing "none"        -> VALID. A sport with no forecast says so.
    #   no pick, timing promised      -> a contradiction; one half is wrong and the
    #                                    hub cannot tell which, so it says so.
    #   a pick with no usable label   -> a figure next to nothing. The band would
    #                                    be a confidence word about a side the
    #                                    reader cannot name.
    if not isinstance(pick, dict):
        if timing == "none":
            return {"sport": sport, "ok": True, "id": body.get("id"),
                    "title": body.get("title"), "starts_at": body.get("starts_at"),
                    "status": body.get("status"), "pick_timing": "none",
                    "pick": None, "band": None, "record": None}
        return {**_fail(sport, "bad_contract"),
                "reason": "the sport's facts promise a pick and carry none",
                "id": body.get("id"), "title": body.get("title"),
                "starts_at": body.get("starts_at"), "status": body.get("status")}

    if not isinstance(label, str) or not label.strip():
        return {**_fail(sport, "no_pick_label"),
                "reason": "the sport's pick carries a figure but names no side",
                "id": body.get("id"), "title": body.get("title"),
                "starts_at": body.get("starts_at"), "status": body.get("status")}

    # The record is passed through as the sport wrote it, including `label`:
    # "before kickoff", "before kick-off" and "before tip-off" are the sports'
    # own wording for one rule, and the hub is not the place to regularise them.
    record = body.get("record") if isinstance(body.get("record"), dict) else None

    return {
        "sport": sport,
        "ok": True,
        "id": body.get("id"),
        "title": body.get("title"),
        "starts_at": body.get("starts_at"),
        "status": body.get("status"),
        "pick_timing": body.get("pick_timing"),
        "pick": {"label": label, "prob": prob if isinstance(prob, (int, float)) else None},
        # Computed, always. `band_for` treats a missing or out-of-range
        # probability as no pick and returns the weakest word, which is the only
        # honest thing to do with one.
        "band": band_for(prob, market_shape(body)),
        "record": record,
    }


async def _one(explainer, sport: str) -> dict[str, Any]:
    base = explainer.settings.sport_api.get(sport)
    if not base:
        return _fail(sport, "unreachable")
    try:
        listing = await explainer.client.get(f"{base}/facts/upcoming",
                                              params={"hours": UPCOMING_HOURS}, timeout=TIMEOUT)
    except httpx.HTTPError:
        return _fail(sport, "unreachable")
    if listing.status_code != 200:
        return _fail(sport, "not_answered")
    try:
        ids = listing.json().get("ids") or []
    except ValueError:
        return _fail(sport, "not_answered")
    if not ids:
        return _fail(sport, "no_fixture")

    # `ids[0]`, and the endpoint makes no ordering promise — it appends as it
    # walks the games list, and its only consumer so far (pre-generation) did not
    # need an order. In practice the snapshots are chronological. So the fixture's
    # own `starts_at` travels with the entry: if this ever picks a later game, the
    # date on the card is what shows it, rather than a silent wrong answer. Making
    # the five endpoints sort is a change in five repos and is not this PR.
    try:
        res = await explainer.client.get(f"{base}/facts/{ids[0]}", timeout=TIMEOUT)
    except httpx.HTTPError:
        return _fail(sport, "unreachable")
    if res.status_code == 404:
        return _fail(sport, "no_fixture")
    if res.status_code != 200:
        return _fail(sport, "not_answered")
    # Parsing and shaping are separated on purpose. Only the parse can be "the
    # sport's data was wrong"; a bug in `_shape` is ours, and catching it here
    # would report our bug as their bad data. So the parse is inside the guard
    # and `_shape` is outside it, where a fault propagates to the gather and
    # lands as `internal` — which is what the first version got wrong, caught by
    # the test that injects the fault.
    try:
        facts = Facts(**res.json())
    except (ValueError, ValidationError, TypeError):
        return _fail(sport, "bad_contract")
    return _shape(sport, facts)


async def summary(explainer) -> dict[str, Any]:
    """One entry per configured sport, in `SPORTS` order, always all of them.

    Concurrent, because a page load is the reader waiting and each fetch has a
    fifteen-second timeout. `return_exceptions=True` so a sport that raises
    anyway costs its own card rather than the page: the whole point of the hub is
    that there are five things to see, and four of them are still true.
    """
    sports = [s for s in SPORTS if explainer.settings.sport_api.get(s)]
    results = await asyncio.gather(*(_one(explainer, s) for s in sports), return_exceptions=True)
    out = []
    for sport, result in zip(sports, results):
        out.append(_fail(sport, "internal") if isinstance(result, BaseException) else result)
    return {"sports": out}
