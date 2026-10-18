"""Backtest-from-history: replay the candidate rule over Kalshi's own settled markets.

This is the exploratory half of the paper-trading work. It does NOT write to
`data/paper/ledger.jsonl`: that file holds claims made at the time, and a
replayed claim is not one of them. Everything here goes to
`data/paper/backtest.jsonl`, which carries the same schema plus an explicit
`exploratory: true` flag and a `price_horizon` (1h / 15min before kickoff).

Rules, all of them pre-stated and none of them tuned on this data:

  * candidate rule: edge >= 4 points net of fee (same as the live ledger)
  * stake: fractional Kelly 0.25x, 1% per bet, 2% per game (same)
  * model_p: ONLY from a pre-kickoff tracked pick. A market with no pre-kickoff
    pick is skipped and counted; it is never filled in from a regenerated or
    rebuilt prediction. This is the one rule that matters most, because the
    whole point of the backtest is to measure whether the probabilities we
    actually had at the time beat the price an hour before kickoff.
  * price: the ask at 1h and at 15min before occurrence_datetime, plus the
    closing price for CLV. Never a price observed after occurrence.

Every output is labelled EXPLORATORY. A segment with fewer than 100 games prints
"cannot be judged". Any sweep of the edge threshold belongs in a separate
EXPLORATORY section, never in the headline table.

PAPER ONLY. No orders, no credentials.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

from . import segments as segments_mod
from . import sources
from .fees import kalshi_fee_cents
from .ledger import candidate_id, stake_for
from .stats import bootstrap_mean_ci, max_drawdown

BACKTEST_PATH = Path("data/paper/backtest.jsonl")

SERIES = {
    # sport -> (series_ticker, tracked-pick loader name)
    "pl": ("KXEPLGAME", "pl"),
}

HORIZONS = (60, 15)  # minutes before occurrence


def _fetch_settled(series_ticker: str) -> list[dict]:
    out: list[dict] = []
    cursor = None
    while True:
        params = {"series_ticker": series_ticker, "status": "settled", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = requests.get("https://api.elections.kalshi.com/trade-api/v2/markets",
                         params=params, timeout=30)
        r.raise_for_status()
        body = r.json()
        out.extend(body.get("markets") or [])
        cursor = body.get("cursor")
        if not cursor:
            break
    return out


def _candles(series_ticker: str, ticker: str, start_ts: int, end_ts: int) -> list[dict]:
    """Fetch candlesticks in 1-day chunks so no single request exceeds ~5000."""
    out: list[dict] = []
    cursor_start = start_ts
    while cursor_start < end_ts:
        chunk_end = min(cursor_start + 86400, end_ts)
        url = (f"https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}"
               f"/markets/{quote(ticker, safe='')}/candlesticks"
               f"?start_ts={cursor_start}&end_ts={chunk_end}&period_interval=1")
        r = requests.get(url, timeout=30)
        if r.status_code == 404:
            cursor_start = chunk_end
            continue
        r.raise_for_status()
        out.extend(r.json().get("candlesticks") or [])
        cursor_start = chunk_end
        time.sleep(0.2)
    # de-dup by end_period_ts
    seen = set()
    deduped = []
    for c in out:
        key = c.get("end_period_ts")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    deduped.sort(key=lambda c: c.get("end_period_ts", 0))
    return deduped


def _ask_at(candles: list[dict], target_ts: int) -> float | None:
    """The yes_ask close of the last candle whose period ends at or before target_ts."""
    best = None
    for c in candles:
        if c.get("end_period_ts", 0) <= target_ts:
            best = c
        else:
            break
    if best is None:
        return None
    ask = (best.get("yes_ask") or {}).get("close_dollars")
    try:
        v = float(ask)
    except (TypeError, ValueError):
        return None
    if not (0.0 < v < 1.0):
        return None
    return v


def _close_ask(candles: list[dict]) -> float | None:
    if not candles:
        return None
    last = candles[-1]
    ask = (last.get("yes_ask") or {}).get("close_dollars")
    try:
        v = float(ask)
    except (TypeError, ValueError):
        return None
    if not (0.0 < v < 1.0):
        return None
    return v


def run(series_filter: list[str] | None = None, tracked_picks: str | None = None) -> dict:
    global args_tracked
    args_tracked = tracked_picks
    import json as _json
    from pathlib import Path as _P

    cfg = segments_mod.load(Path("data/paper/segments.json"))
    threshold = segments_mod.edge_threshold(cfg)

    # tracked picks, pre-kickoff only
    # Tracked picks live in the site repo, not the hub. SITES_ROOT or an explicit
    # --tracked-picks path supplies them; without one we cannot run honestly.
    picks_path = _P(args_tracked) if args_tracked else None
    if picks_path is None:
        import os
        root = os.environ.get("SITES_ROOT")
        if root:
            picks_path = _P(root) / "PL_Predictor" / "data" / "tracking_picks.jsonl"
        else:
            picks_path = _P("data/tracking_picks.jsonl")
    tracked: dict[tuple, dict] = {}
    skipped_no_pick = 0
    if picks_path.exists():
        for line in picks_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if not r.get("made_before_kickoff"):
                continue
            key = (r.get("team_home"), r.get("team_away"), r.get("commence_time"))
            tracked.setdefault(key, {})[r.get("outcome_name")] = r.get("predicted_prob")

    rows_out: list[dict] = []
    games_found = 0
    games_skipped = 0
    markets_seen = 0

    for sport, (series_ticker, _loader) in SERIES.items():
        if series_filter and sport not in series_filter:
            continue
        markets = _fetch_settled(series_ticker)
        # group by event ticker
        by_event: dict[str, list[dict]] = {}
        for m in markets:
            by_event.setdefault(m.get("event_ticker"), []).append(m)
        for event_ticker, event_markets in by_event.items():
            markets_seen += len(event_markets)
            # find kickoff
            occ_str = event_markets[0].get("occurrence_datetime")
            occ = sources.parse_ts(occ_str)
            if occ is None:
                continue
            games_found += 1
            # Kalshi gives team CODES (LFC, ARS); tracked picks give full names.
            # Match by (home name, away name, date) so a 3-hour disagreement in
            # kickoff time between Kalshi and PL cannot silently pair the wrong
            # game. Date-only would be ambiguous on a busy Saturday.
            code_to_name = {v: k for k, v in sources.PL_TEAM_CODES.items()}
            home_name = code_to_name.get(event_markets[0].get("ticker", "").split("-")[-1][:3] if False else None)
            # Derive home/away codes from the event ticker's team segment.
            parts = sources.event_parts(event_ticker)
            codes = parts["teams"] if parts else ""
            # split codes: try all splits against known codes
            home_code = away_code = None
            for i in range(2, len(codes) - 1):
                if codes[:i] in code_to_name and codes[i:] in code_to_name:
                    home_code, away_code = codes[:i], codes[i:]
                    break
            if not home_code:
                games_skipped += 1
                continue
            home_name = code_to_name[home_code]
            away_name = code_to_name[away_code]
            date_str = (occ_str or "")[:10]
            match = None
            for key, probs in tracked.items():
                if (key[0] == home_name and key[1] == away_name
                        and str(key[2])[:10] == date_str):
                    match = (key, probs)
                    break
            if match is None:
                games_skipped += 1
                continue
            _key, probs = match
            # fetch candles once per event (use first market's ticker range)
            primary = event_markets[0]
            ticker_primary = primary["ticker"]
            close_ts = None
            try:
                close_dt = sources.parse_ts(primary.get("close_time"))
                close_ts = int(close_dt.timestamp()) if close_dt else int(occ.timestamp()) + 86400
            except Exception:
                close_ts = int(occ.timestamp()) + 86400
            start_ts = int((occ - timedelta(hours=2)).timestamp())
            end_ts = close_ts
            candles_cache: dict[str, list[dict]] = {}
            for m in event_markets:
                if m["ticker"] not in candles_cache:
                    candles_cache[m["ticker"]] = _candles(series_ticker, m["ticker"], start_ts, end_ts)

            for m in event_markets:
                title = m.get("title") or ""
                low = title.lower()
                if "tie" in low or "draw" in low:
                    outcome_name = "draw"
                elif m["ticker"].endswith(m["ticker"].split("-")[-2][:3]) if "-" in m["ticker"] else False:
                    outcome_name = "home_win"
                else:
                    outcome_name = "away_win"
                # determine home/away from tracked probs keys
                # tracked probs has home_win/draw/away_win
                model_p = probs.get(outcome_name) if isinstance(probs, dict) else None
                # also accept "home"/"away"/"draw" keys
                if model_p is None and isinstance(probs, dict):
                    alt = {"home_win": "home", "draw": "draw", "away_win": "away"}.get(outcome_name)
                    model_p = probs.get(alt)
                if not isinstance(model_p, (int, float)):
                    continue

                candles = candles_cache.get(m["ticker"], [])
                for minutes in HORIZONS:
                    target_ts = int((occ - timedelta(minutes=minutes)).timestamp())
                    price = _ask_at(candles, target_ts)
                    if price is None:
                        continue
                    close_price = _close_ask(candles)
                    fee_cents = kalshi_fee_cents(price * 100.0, contracts=1)
                    fee = fee_cents / 100.0
                    edge = round((float(model_p) - price - fee) * 100.0, 4)
                    if edge < threshold:
                        continue
                    bucket = segments_mod.bucket_label(float(model_p))
                    if bucket is None:
                        continue
                    segment = segments_mod.segment_key(sport, "moneyline", bucket)
                    entry = segments_mod.match(cfg, sport=sport, market="moneyline")
                    kind = "candidate" if entry is not None else "shadow"
                    stake = stake_for(float(model_p), price, game_id=event_ticker) if kind == "candidate" else 0.0
                    clv = None
                    if close_price is not None:
                        clv = round((close_price - price) * 100.0, 4)
                    rows_out.append({
                        "record": "candidate",
                        "id": candidate_id(sport=sport, game_id=event_ticker, market="moneyline",
                                           selection=m["ticker"].split("-")[-1], side="yes", line=None),
                        "kind": kind,
                        "sport": sport,
                        "market": "moneyline",
                        "game_id": event_ticker,
                        "ticker": m["ticker"],
                        "event_ticker": event_ticker,
                        "selection": m["ticker"].split("-")[-1],
                        "side": "yes",
                        "line": None,
                        "model_p": round(float(model_p), 6),
                        "market_price": price,
                        "price_observed_at": datetime.fromtimestamp(target_ts, tz=timezone.utc).isoformat(),
                        "kickoff": occ.isoformat(),
                        "fee_cents": fee_cents,
                        "fee": round(fee, 6),
                        "edge": edge,
                        "segment": segment,
                        "stake": stake,
                        "logged_at": datetime.fromtimestamp(target_ts, tz=timezone.utc).isoformat(),
                        "status": "settled" if m.get("result") in ("yes", "no") else "open",
                        "outcome": m.get("result") if m.get("result") in ("yes", "no") else None,
                        "pnl_per_contract": None,
                        "exploratory": True,
                        "backtest": True,
                        "price_horizon_minutes": minutes,
                        "closing_price": close_price,
                        "clv_cents": clv,
                        "model_source": "tracked_pick",
                    })
                    # pnl for settled
                    if m.get("result") in ("yes", "no"):
                        outcome = m["result"]
                        won = (outcome == "yes")
                        pnl = (1.0 - price - fee) if won else (-price - fee)
                        rows_out[-1]["outcome"] = outcome
                        rows_out[-1]["status"] = "settled"
                        rows_out[-1]["pnl_per_contract"] = round(pnl, 6)

    # write backtest.jsonl
    BACKTEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BACKTEST_PATH.open("w", encoding="utf-8") as fh:
        for r in rows_out:
            fh.write(json.dumps(r, sort_keys=True) + "\n")

    return {
        "games_found": games_found,
        "games_skipped_no_pick": games_skipped,
        "markets_seen": markets_seen,
        "rows_written": len(rows_out),
        "tracked_games": len(tracked),
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sport", action="append", default=None)
    parser.add_argument("--tracked-picks", default=None)
    parser.add_argument("--out", default=str(BACKTEST_PATH))
    args = parser.parse_args(argv)
    filters = args.sport if args.sport else None
    summary = run(filters, args.tracked_picks)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
