"""Turn Kalshi line snapshots into candidate rows, or refuse to.

This is where the no-hindsight rules live, so it is worth stating all four in
one place before the code:

  1. `logged_at` is the Kalshi row's OWN `snapshot_ts`, never the wall clock at
     the moment the logger happens to run. A row observed on Tuesday and written
     on Saturday is a Tuesday row.
  2. A row is only eligible if `snapshot_ts` is strictly before kickoff, read
     from the row's `occurrence` field. Unreadable means ineligible.
  3. The price logged is the ask from THAT SAME row. No other snapshot's price is
     ever consulted for a candidate.
  4. The model probability must come from a snapshot whose `generated_at` is at
     or before the price's `snapshot_ts`, using the latest such snapshot. If that
     ordering cannot be established the row is logged as a shadow, never as a
     candidate — a probability computed after we saw the price is hindsight with
     extra steps.

Rules 1-3 stop a post-kickoff price entering. Rule 4 stops a post-price
probability entering. They are different leaks and need different guards.

PAPER ONLY. Nothing here places an order; the only price written is one that was
publicly observable at the time it is stamped with.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from . import sources
from .fees import kalshi_fee_cents
from .ledger import (KIND_CANDIDATE, KIND_SHADOW, STATUS_OPEN, candidate_id, stake_for)
from . import segments as segments_mod
from .segments import bucket_label, edge_threshold, match, segment_key

# Why a row was not logged. Counted, never printed per row: a report that lists
# 6,000 rejections is unreadable, and one that lists none hides a misconfigured
# join that is silently logging nothing at all.
SKIP_REASONS = (
    "unreadable_snapshot_ts",
    "no_kickoff",
    "price_at_or_after_kickoff",
    "not_a_game_market",
    "no_matching_game",
    "no_model_probability",
    "no_bid",
    "spread_too_wide",
    "zero_volume",
    "dead_quote",
    "below_edge_threshold",
)


def _iso(stamp: datetime | None) -> str | None:
    return stamp.isoformat() if stamp else None


def candidate_rows(rows: list[dict], games_by_sport: dict[str, dict], config: dict, *,
                   committed_by_game: dict[str, float] | None = None,
                   positions: dict[str, str] | None = None) -> tuple[list[dict], dict[str, int]]:
    """Build the candidate and shadow rows for one batch of Kalshi snapshots.

    Returns the rows to append and a tally of why each rejected row was rejected.
    """
    best: dict[str, dict] = {}
    skipped: dict[str, int] = {}
    threshold = edge_threshold(config)

    def skip(reason: str) -> None:
        skipped[reason] = skipped.get(reason, 0) + 1

    for row in rows:
        parts = sources.event_parts(row.get("event_ticker"))
        if parts is None or parts["sport"] is None:
            skip("no_matching_game")
            continue
        sport, market = parts["sport"], row.get("stat")

        # -- no-hindsight 1 and 2: the price must be readable and pre-kickoff ---
        seen_at = sources.parse_ts(row.get("snapshot_ts"))
        if seen_at is None:
            skip("unreadable_snapshot_ts")
            continue
        start = sources.kickoff(row)
        if start is None:
            skip("no_kickoff")
            continue
        if seen_at >= start:
            skip("price_at_or_after_kickoff")
            continue

        if market not in sources.GAME_LEVEL_STATS:
            # Player props need a calibrated per-prop probability, which no site
            # publishes yet. Deliberately not guessed at.
            skip("not_a_game_market")
            continue

        game = sources.join_games(parts, games_by_sport.get(sport) or {})
        if game is None:
            skip("no_matching_game")
            continue

        # A Kalshi "<TEAM> wins" rung is the YES contract on that team.
        side = "yes"
        pick = sources.selection(row)
        probs = game.get("probs") or {}
        model_p = None
        if market == "total":
            # "over X points" YES contract: model_p = P(over) for the game's
            # predicted total. The snapshot's over_prob is for the book's line,
            # not Kalshi's, so this is an approximation — but it is the field
            # the brief names, and the gate will refuse to certify noise.
            model_p = probs.get("over")
        elif sport == "pl":
            # PL moneylines have three outcomes: home win, tie, away win. Each is
            # its own market (YES = that outcome), so the model probability is
            # looked up by the selection code, not by home/away.
            model_p = probs.get("draw") if pick == "TIE" else (
                probs.get("home_win") if pick == game.get("home") else
                probs.get("away_win") if pick == game.get("away") else None)
        else:
            if pick and pick == game.get("home"):
                model_p = probs.get("home_win")
            elif pick and pick == game.get("away"):
                model_p = probs.get("away_win")
        if not isinstance(model_p, (int, float)):
            skip("no_model_probability")
            continue
        model_p = float(model_p)

        # -- no-hindsight 4: the probability must predate the price -------------
        proven = _model_precedes_price(game.get("generated_at"), seen_at)

        price = sources.buyable_price(row, side)
        if price is None:
            skip("no_matching_game")
            continue

        # -- liquidity: a quote you cannot actually trade is not a price ------
        # The ask alone is not enough. A market with no bid, a wide spread, no
        # volume, or a 1-cent ask is not a market anybody can enter, and logging
        # it would report an edge that was never available to anyone.
        yes_bid = row.get("yes_bid")
        no_bid = row.get("no_bid")
        volume = row.get("volume")
        open_interest = row.get("open_interest")
        if not isinstance(yes_bid, (int, float)) or float(yes_bid) <= 0:
            skip("no_bid")
            continue
        spread = price - float(yes_bid)
        max_spread = segments_mod.max_spread_points(config) / 100.0
        if spread > max_spread:
            skip("spread_too_wide")
            continue
        if not isinstance(volume, (int, float)) or float(volume) <= 0:
            skip("zero_volume")
            continue
        if price <= 0.01 or price >= 0.99:
            skip("dead_quote")
            continue

        fee_cents = kalshi_fee_cents(price * 100.0, contracts=1)
        fee = fee_cents / 100.0
        edge = round((model_p - price - fee) * 100.0, 4)
        if edge < threshold:
            skip("below_edge_threshold")
            continue

        bucket = bucket_label(model_p)
        if bucket is None:
            skip("below_edge_threshold")
            continue
        segment = segment_key(sport, market, bucket)
        position = (positions or {}).get(pick)
        allow = match(config, sport=sport, market=market, position=position)

        # Allow-listed AND the model/price ordering is provable: a real candidate.
        # Anything else clears the same edge bar but earns no stake.
        kind = KIND_CANDIDATE if (allow is not None and proven) else KIND_SHADOW
        game_id = game["game_id"]
        row_id = candidate_id(sport=sport, game_id=game_id, market=market,
                              selection=pick, side=side, line=row.get("line"))

        made = {
            "record": KIND_CANDIDATE,  # shadows are candidate rows flagged shadow
            "id": row_id,
            "kind": kind,
            "sport": sport,
            "market": market,
            "game_id": game_id,
            "event_ticker": row.get("event_ticker"),
            "ticker": row.get("ticker"),
            "player": None,
            "selection": pick,
            "side": side,
            "line": row.get("line"),
            "model_p": round(model_p, 6),
            "market_price": price,
            "price_observed_at": _iso(seen_at),
            "kickoff": _iso(start),
            "fee_cents": fee_cents,
            "fee": round(fee, 6),
            "edge": edge,
            "segment": segment,
            "script_bucket": None,
            "yes_bid": _num(row.get("yes_bid")),
            "no_bid": _num(row.get("no_bid")),
            "spread_points": round(spread * 100.0, 4),
            "volume": _num(volume),
            "open_interest": _num(open_interest),
            "model_fingerprint": game.get("model_fingerprint"),
            "stake": 0.0,
            "logged_at": _iso(seen_at),
            "model_generated_at": game.get("generated_at"),
            "model_ordering_proven": proven,
            "status": STATUS_OPEN,
            "outcome": None,
            "pnl_per_contract": None,
        }
        _keep_best(best, made)

    # Stakes are assigned AFTER the batch is deduplicated, in observation order,
    # so the correlated-exposure cap is spent earliest-bet-first and a bet that
    # loses its place to a better-evidenced observation never consumed budget.
    committed = dict(committed_by_game or {})
    for made in sorted(best.values(), key=lambda r: r["logged_at"]):
        if made["kind"] != KIND_CANDIDATE:
            continue
        made["stake"] = stake_for(made["model_p"], made["market_price"],
                                  game_id=made["game_id"], committed_by_game=committed)
        committed[made["game_id"]] = committed.get(made["game_id"], 0.0) + made["stake"]
    return list(best.values()), skipped


def _num(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _keep_best(best: dict[str, dict], made: dict) -> None:
    """One row per bet within a batch. Which observation of a bet wins:

    1. a stakeable candidate beats a shadow, even if it was seen later;
    2. otherwise the earliest observation wins.

    Rule 1 is the one that is not obvious. A bet can be seen first at a price
    that predates the model snapshot, which makes it a shadow, and again later
    with the ordering provable. Logging the shadow first would permanently fix
    the id to a row with no stake and no proven ordering, and the later,
    perfectly valid candidate would be swallowed as a duplicate. That is a data
    QUALITY rule, not a hindsight rule: both observations happened before
    kickoff, and neither knows the result.
    """
    held = best.get(made["id"])
    if held is None:
        best[made["id"]] = made
        return
    held_is_candidate = held["kind"] == KIND_CANDIDATE
    if (made["kind"] == KIND_CANDIDATE) and not held_is_candidate:
        best[made["id"]] = made
    elif (made["kind"] == KIND_CANDIDATE) == held_is_candidate and \
            made["logged_at"] < held["logged_at"]:
        best[made["id"]] = made


def _model_precedes_price(generated_at, seen_at: datetime) -> bool:
    """True when the model's snapshot is no newer than the price we logged.

    Equality is allowed: a snapshot and a price stamped in the same second is
    not an ordering violation, and requiring strict inequality would throw away
    every candidate collected in the same instant as the snapshot refresh.
    """
    stamp = sources.parse_ts(generated_at)
    if stamp is None:
        return False
    return stamp <= seen_at


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    from . import segments as segments_mod
    from .ledger import Ledger

    parser = argparse.ArgumentParser(description="Log paper-trade candidates. PAPER ONLY.")
    parser.add_argument("--ledger", default="data/paper/ledger.jsonl")
    parser.add_argument("--segments", default="data/paper/segments.json")
    parser.add_argument("--sites-root", default=None)
    parser.add_argument("--sport", action="append", default=None,
                        help="limit to one sport (default: every sport with a collector)")
    parser.add_argument("--dry-run", action="store_true", help="report what would be written")
    args = parser.parse_args(argv)

    root = args.sites_root or sources.discover_sites_root()
    sports = args.sport or sorted(sources.SITE_FOR_SPORT)
    if root is None:
        print("no sibling site checkouts found; pass --sites-root", file=sys.stderr)
        return 2

    config = segments_mod.load(args.segments)
    ledger = Ledger(args.ledger)

    rows, games, positions = [], {}, {}
    for sport in sports:
        rows.extend(sources.read_line_files(sources.lines_files(Path(root), sport)))
        snapshot = sources.read_snapshot(Path(root) / sources.SITE_FOR_SPORT[sport] / "data" / "public_snapshot.json")
        games[sport] = sources.snapshot_games(snapshot, sport)
        positions.update(sources.snapshot_positions(snapshot))

    made, skipped = candidate_rows(rows, games, config,
                                   committed_by_game=ledger.committed_by_game(),
                                   positions=positions)
    fresh = made if args.dry_run else ledger.append_new(made)

    counts = {"candidates": sum(1 for r in fresh if r["kind"] == "candidate"),
              "shadows": sum(1 for r in fresh if r["kind"] == "shadow")}
    print(json.dumps({
        "read_rows": len(rows), "written": len(fresh), **counts,
        "skipped": dict(sorted(skipped.items())),
        "dry_run": bool(args.dry_run),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

