"""The report and the page: per-sport rows, and what each one has to say.

The spec asks for per-sport rows in `report.json` and `paper.html` — one table,
a sport filter — and for each segment to show:

  * logged / shadow / settled counts,
  * the net-of-fee result with its interval,
  * the mean CLV and its n,
  * the reason it cannot be judged yet, in plain words,
  * the excluded-legacy note where it applies,

and for NO segment to be called "has an edge" below the gate.

The per-sport roll-up is what lets the page filter by sport without the page
having to parse the segment keys, and it is what the plain-words reason is
attached to: "nfl:moneyline:0.60-0.70" means nothing to a reader, and
"needs 297 more settled bets" does.
"""
from __future__ import annotations

import json

import pytest
from conftest import config

from paper.report import build, render
from paper.segments import gate as gate_of

GATE = gate_of(config())


def row(**over) -> dict:
    """A logged ledger row."""
    base = {
        "record": "candidate", "kind": "candidate", "id": "id0",
        "sport": "nfl", "market": "moneyline",
        "game_id": "g", "ticker": "KXNFLGAME-26OCT18BALCLE-BAL", "selection": "BAL",
        "side": "yes", "line": None,
        "model_p": 0.60, "market_price": 0.50, "fee": 0.02, "edge": 8.0,
        "segment": "nfl:moneyline:0.60-0.70", "stake": 5.0,
        "status": "settled", "outcome": "yes", "pnl_per_contract": 0.48,
        "price_observed_at": "2026-10-17T20:00:00+00:00", "kickoff": "2026-10-18T17:00:00+00:00",
    }
    base.update(over)
    return base


def batch(n: int, *, sport: str = "nfl", segment: str | None = None,
          wins: int | None = None, kind: str = "candidate") -> list[dict]:
    """`n` logged rows for one sport. `wins` leading rows win."""
    wins = n if wins is None else wins
    segment = segment or f"{sport}:moneyline:0.60-0.70"
    out = []
    for i in range(n):
        won = i < wins
        out.append(row(id=f"{sport}{i}", sport=sport, segment=segment, kind=kind,
                       ticker=f"T-{sport}-{i}", game_id=f"g-{sport}-{i}",
                       outcome="yes" if won else "no",
                       pnl_per_contract=0.48 if won else -0.52,
                       stake=5.0 if kind != "shadow" else 0.0))
    return out


# --- per-sport rows -----------------------------------------------------------

def test_the_report_has_a_row_per_sport():
    rows = batch(5, sport="nfl") + batch(3, sport="cfb") + batch(2, sport="pl")
    report = build(rows, closing={}, gate_cfg=GATE)
    assert set(report["per_sport"]) == {"nfl", "cfb", "pl"}


def test_a_sport_row_carries_the_counts_a_reader_needs():
    rows = (batch(4, sport="nfl")
            + batch(2, sport="nfl", kind="shadow"))
    report = build(rows, closing={}, gate_cfg=GATE)
    nfl = report["per_sport"]["nfl"]
    assert nfl["n_logged"] == 6
    assert nfl["n_candidates"] == 4
    assert nfl["n_shadow"] == 2
    assert nfl["n_settled"] == 6
    assert nfl["segments"] == 1


def test_a_sport_row_carries_the_result_and_its_interval():
    rows = batch(10, sport="nfl", wins=7)
    report = build(rows, closing={}, gate_cfg=GATE)
    nfl = report["per_sport"]["nfl"]
    assert nfl["pnl"] == pytest.approx(7 * 0.48 + 3 * -0.52, abs=1e-6)
    assert nfl["pnl_ci95"] is not None
    assert len(nfl["pnl_ci95"]) == 2


def test_a_sport_row_carries_the_mean_clv_and_its_n():
    rows = batch(4, sport="nfl")
    closing = {"T-nfl-0": {"_seen_at": 1, "_kickoff": 2, "_price": 0.55, "_no_price": 0.55}}
    report = build(rows, closing=closing, gate_cfg=GATE)
    nfl = report["per_sport"]["nfl"]
    assert nfl["mean_clv_cents"] == pytest.approx(5.0)
    assert nfl["n_clv"] == 1
    assert nfl["share_clv_positive"] == pytest.approx(1.0)


def test_a_sport_with_no_closed_rows_reports_null_clv_not_zero():
    rows = batch(4, sport="nfl")
    report = build(rows, closing={}, gate_cfg=GATE)
    nfl = report["per_sport"]["nfl"]
    assert nfl["mean_clv_cents"] is None
    assert nfl["n_clv"] == 0
    assert nfl["share_clv_positive"] is None


# --- the plain-words reason ----------------------------------------------------

def test_a_sport_says_in_plain_words_why_it_cannot_be_judged_yet():
    rows = batch(5, sport="nfl")
    report = build(rows, closing={}, gate_cfg=GATE)
    reason = report["per_sport"]["nfl"]["why_not_yet"]
    assert isinstance(reason, str) and reason
    # It has to say what is missing, not repeat a number.
    assert "295" in reason and "settled" in reason


def test_a_sport_with_enough_rows_says_what_is_still_missing():
    # 300 settled bets clears the count, but a coin-flip result does not clear
    # the interval, so the reason must be about THAT and not about the count.
    rows = batch(300, sport="nfl", wins=150)
    report = build(rows, closing={}, gate_cfg=GATE)
    reason = report["per_sport"]["nfl"]["why_not_yet"]
    assert reason
    assert "more settled bets" not in reason
    assert "interval" in reason.lower()


def test_a_sport_that_clears_every_condition_has_no_reason():
    rows = batch(300, sport="nfl", wins=299)
    report = build(rows, closing={}, gate_cfg=GATE)
    assert report["per_sport"]["nfl"]["why_not_yet"] is None
    assert report["per_sport"]["nfl"]["qualifies_for_edge_claim"] is True


def test_a_sport_that_qualifies_has_no_reason():
    rows = batch(300, sport="nfl", wins=299)
    report = build(rows, closing={}, gate_cfg=GATE)
    assert report["per_sport"]["nfl"]["why_not_yet"] is None
    assert report["per_sport"]["nfl"]["qualifies_for_edge_claim"] is True


def test_a_shadow_only_sport_says_it_carries_no_stake():
    rows = batch(5, sport="cfb", kind="shadow")
    report = build(rows, closing={}, gate_cfg=GATE)
    reason = report["per_sport"]["cfb"]["why_not_yet"]
    assert "shadow" in reason.lower()


def test_no_sport_below_the_gate_is_called_having_an_edge():
    for sport in ("nfl", "cfb", "pl"):
        rows = batch(299, sport=sport)
        report = build(rows, closing={}, gate_cfg=GATE)
        assert report["per_sport"][sport]["qualifies_for_edge_claim"] is False
        assert report["per_sport"][sport]["has_edge_claim"] is False


# --- the excluded-legacy note -------------------------------------------------

def test_the_excluded_legacy_note_is_carried_where_it_applies():
    legacy = row(market="total", segment="nfl:total:0.50-0.60", id="old", model_basis=None)
    sound = row(market="total", segment="nfl:total:0.50-0.60", id="new",
                model_basis="normal(predicted_total, total_sigma) at the rung line")
    report = build([legacy, sound], closing={}, gate_cfg=GATE)
    assert report["per_sport"]["nfl"]["excluded_legacy_total_rows"] == 1


def test_a_sport_with_no_excluded_rows_says_zero_rather_than_omitting_it():
    rows = batch(5, sport="pl")
    report = build(rows, closing={}, gate_cfg=GATE)
    assert report["per_sport"]["pl"]["excluded_legacy_total_rows"] == 0


# --- the page ------------------------------------------------------------------

def test_the_page_renders_one_table_with_a_sport_filter():
    from pathlib import Path
    html = Path(__file__).resolve().parents[3] / "paper.html"
    text = html.read_text(encoding="utf-8")
    # One table of segments, and a way to filter it by sport.
    assert text.count('id="segment-table"') == 1
    assert "sport" in text.lower()


def test_the_report_json_keeps_its_schema_version():
    rows = batch(5, sport="nfl")
    report = build(rows, closing={}, gate_cfg=GATE)
    assert report["schema_version"] == 1
    # The whole report must survive a JSON round trip: the page reads the file.
    json.dumps(report)
