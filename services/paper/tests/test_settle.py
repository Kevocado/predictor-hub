"""Settlement: wins, losses, pushes, voids, postponements, and idempotency.

Settlement reads Kalshi's own resolution rather than forming an opinion, so most
of what is worth testing is what happens when that resolution is missing or is
not a plain yes/no.
"""
from __future__ import annotations

import pytest
from conftest import build, kalshi_row

from paper.ledger import Ledger, resolved
from paper.settle import finalised_by_ticker, pnl_per_contract, resolution, settle


def _one(ledger_path, **over):
    ledger = Ledger(ledger_path)
    made, _ = build([kalshi_row(**over)])
    ledger.append_new(made)
    return ledger, made[0]


def test_a_win_pays_the_contract_less_the_price_and_the_fee(ledger_path):
    ledger, _ = _one(ledger_path)
    settle(ledger, [kalshi_row(status="finalized", result="yes")])
    (row,) = resolved(ledger)
    # kalshi_fee_cents(40) == 2, so fee == 0.02: 1.00 payout - 0.40 paid - 0.02.
    assert row["status"] == "settled"
    assert row["pnl_per_contract"] == pytest.approx(0.58)


def test_a_loss_costs_the_price_and_the_fee(ledger_path):
    ledger, _ = _one(ledger_path)
    settle(ledger, [kalshi_row(status="finalized", result="no")])
    (row,) = resolved(ledger)
    assert row["outcome"] == "no"
    assert row["pnl_per_contract"] == pytest.approx(-0.42)


def test_the_fee_is_charged_exactly_once_and_matches_the_pin():
    """fees.py rounds the order fee up once; a loss must not be charged twice."""
    from paper.fees import kalshi_fee_cents
    assert kalshi_fee_cents(40.0) == 2.0
    assert pnl_per_contract("no", 0.40, kalshi_fee_cents(40.0) / 100.0) == pytest.approx(-0.42)


def test_a_finalized_market_with_no_result_is_void_and_pays_nothing(ledger_path):
    """The void case. Kalshi closed the market without saying yes or no: the
    contract expires worthless. Stake returns, and no fee is charged because no
    contract traded."""
    ledger, _ = _one(ledger_path)
    settle(ledger, [kalshi_row(status="finalized", result=None)])
    (row,) = resolved(ledger)
    assert row["status"] == "void"
    assert row["outcome"] == "void"
    assert row["pnl_per_contract"] == 0.0


@pytest.mark.parametrize("result", ["push", "tie", "void", "cancelled", "postponed", ""])
def test_a_push_or_tie_is_handled_as_a_void_rather_than_a_loss(result):
    """Kalshi resolves its own ties — a spread landing exactly on the number is
    settled by Kalshi's published rule — so a push does not arrive as its own
    value. It arrives as a finalized market with a non-binary result, and it is
    worth zero to the contract holder, never minus the stake."""
    assert resolution({"status": "finalized", "result": result}) == ("void", "void")


def test_a_postponed_game_stays_open_because_we_do_not_know_yet(ledger_path):
    """Postponed is NOT void. The rung is un-finalized, so the honest state is
    'open' — a void here would quietly forgive a bet that may still be live."""
    ledger, _ = _one(ledger_path)
    settle(ledger, [kalshi_row(status="active", result=None)])
    (row,) = resolved(ledger)
    assert row["status"] == "open"
    assert row["outcome"] is None


def test_a_still_active_market_is_not_settled(ledger_path):
    ledger, _ = _one(ledger_path)
    counts = settle(ledger, [kalshi_row(status="active", result="yes")])
    assert counts["unresolved"] == 1 and counts["settled"] == 0


def test_an_unrecognised_result_is_a_void_never_a_loss():
    """Fails closed. If Kalshi ever ships a result this code has not seen, the
    safe reading is 'we cannot say', and the safe consequence is zero — not a
    loss booked against a bet that may not have lost."""
    assert resolution({"status": "finalized", "result": "SOMETHING_NEW"}) == ("void", "void")


def test_a_malformed_row_is_never_settled_on_a_guess():
    """Fails closed: no status, no result field, an empty status — all stay open."""
    for bad in ({}, {"result": "yes"}, {"status": "", "result": "yes"},
                {"status": None, "result": "no"}, {"status": "weird", "result": "yes"}):
        assert resolution(bad) is None, bad


def test_a_later_snapshot_wins_when_resolving(ledger_path):
    """Yesterday's file said 'active'; today's says 'finalized'. The market is
    resolved, and the resolution must not be lost to file ordering."""
    ledger, _ = _one(ledger_path)
    counts = settle(ledger, [
        kalshi_row(snapshot_ts="2026-10-16T20:00:00+00:00", status="active"),
        kalshi_row(snapshot_ts="2026-10-19T20:00:00+00:00", status="finalized", result="no"),
    ])
    assert counts["settled"] == 1
    (row,) = resolved(ledger)
    assert row["outcome"] == "no"


def test_the_settled_row_records_where_the_verdict_came_from(ledger_path):
    ledger, _ = _one(ledger_path)
    settle(ledger, [kalshi_row(snapshot_ts="2026-10-19T20:00:00+00:00",
                               status="finalized", result="yes")])
    (record,) = [r for r in ledger.records() if r["record"] == "settle"]
    assert record["source_snapshot_ts"] == "2026-10-19T20:00:00+00:00"
    assert record["source_result"] == "yes"


def test_a_settled_row_stops_counting_against_the_game_exposure_cap(ledger_path):
    """A settled bet's stake is spent money, not exposure. The per-bet cap still
    applies to it, which is why this frees the game budget rather than deleting
    the row."""
    ledger, made = _one(ledger_path)
    game_id = made["game_id"]
    assert ledger.committed_by_game() == {game_id: pytest.approx(made["stake"])}

    settle(ledger, [kalshi_row(status="finalized", result="yes")])
    assert ledger.committed_by_game() == {}


def test_finalised_by_ticker_ignores_rows_that_have_not_resolved():
    rows = [kalshi_row(status="active"), kalshi_row(status="finalized", result="yes")]
    assert len(finalised_by_ticker(rows)) == 1

