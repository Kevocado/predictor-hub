"""Shared fixtures: synthetic Kalshi rows and synthetic public snapshots.

The real artefacts are large and move; the rules they feed do not. These build
the smallest thing that still has every field the logger reads, so a test failure
points at a rule rather than at a data refresh.

Every helper lets the caller override any field, because most of these tests
exist to move exactly one field — the snapshot time, the kickoff, the result —
and assert that one field alone changes the outcome.
"""
from __future__ import annotations

import copy

import pytest

from paper import sources

KICKOFF = "2026-10-18T17:00:00+00:00"
SNAPSHOT_TS = "2026-10-17T20:00:00+00:00"
GENERATED_AT = "2026-10-17T19:00:00+00:00"


def kalshi_row(**overrides) -> dict:
    """One open moneyline rung: 'Baltimore wins', quoted at 40c, game on the 18th."""
    row = {
        "snapshot_ts": SNAPSHOT_TS,
        "series": "KXNFLGAME",
        "stat": "moneyline",
        "event_ticker": "KXNFLGAME-26OCT18BALCLE",
        "ticker": "KXNFLGAME-26OCT18BALCLE-BAL",
        "player": None,
        "line": None,
        "yes_bid": 0.38,
        "yes_ask": 0.40,
        "no_bid": 0.58,
        "no_ask": 0.62,
        "last": 0.40,
        "volume": 100.0,
        "open_interest": 100.0,
        "status": "active",
        "result": None,
        "settlement_value": None,
        "occurrence": KICKOFF,
        # Kalshi keeps the market open for days after the game, so close_time is
        # deliberately MUCH later than occurrence. Any rule that uses close_time
        # as the cutoff would let a post-final price in.
        "close_time": "2026-10-20T17:00:00+00:00",
    }
    row.update(overrides)
    return row


def nfl_snapshot(*, generated_at: str = GENERATED_AT, home_win: float = 0.60,
                 away_win: float = 0.40, played: bool = False,
                 home: str = "BAL", away: str = "CLE",
                 game_id: str = "2026_06_BAL_CLE", date: str = "2026-10-18",
                 predicted_total: float | None = 47.0, total_sigma: float | None = 12.0) -> dict:
    """A public snapshot with one game, its probability, and no final score."""
    return {
        "generated_at": generated_at,
        "season": 2026,
        "current_week": 6,
        "weeks": {
            "6": {
                "games": [{
                    "game_id": game_id,
                    "season": 2026,
                    "week": 6,
                    "gameday": f"{date}T17:00:00",
                    "home_team": home,
                    "away_team": away,
                    "home_score": 24.0 if played else None,
                    "away_score": 17.0 if played else None,
                }],
                "predictions": {
                    game_id: {
                        "home_win_prob": home_win,
                        "away_win_prob": away_win,
                        "over_prob": 0.5,
                        "under_prob": 0.5,
                        "predicted_total": predicted_total,
                        "total_sigma": total_sigma,
                    }
                },
            }
        },
    }


def config(**overrides) -> dict:
    """An allow-list with every market admitted, so tests isolate one rule at a time."""
    base = {
        "schema_version": 1,
        "edge_threshold_points": 4.0,
        "confidence_buckets": [[0.50, 0.60], [0.60, 0.70], [0.70, 0.80],
                               [0.80, 0.90], [0.90, 1.01]],
        "gate": {"min_settled": 300, "require_ci_excludes_zero": True,
                 "require_calibration_not_widening": True,
                 "min_for_calibration_trend": 100},
        "segments": [
            {"segment": "nfl:moneyline", "sport": "nfl", "market": "moneyline"},
            {"segment": "nba:moneyline", "sport": "nba", "market": "moneyline"},
        ],
    }
    base.update(overrides)
    return base


def build(rows, *, home_win=0.60, generated_at=GENERATED_AT, cfg=None, positions=None,
          committed=None, snapshot=None):
    """Run the candidate builder over `rows` against a one-game NFL snapshot."""
    from paper.log import candidate_rows
    snap = snapshot if snapshot is not None else nfl_snapshot(
        generated_at=generated_at, home_win=home_win)
    return candidate_rows(
        copy.deepcopy(rows),
        {"nfl": sources.snapshot_games(snap, "nfl")},
        cfg if cfg is not None else config(),
        committed_by_game=committed,
        positions=positions,
    )


@pytest.fixture
def ledger_path(tmp_path):
    return tmp_path / "ledger.jsonl"
