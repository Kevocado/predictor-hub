"""The no-hindsight rules. This is the file that matters most.

A paper ledger's entire value is that its rows were decidable at the time they
were written. A row that borrows a later price, or a probability computed after
the price was seen, is not a paper bet — it is a backtest wearing a ledger's
clothes, and it will report an edge that was never available to anyone.

So each rule gets its own test, and each test moves exactly one field.
"""
from __future__ import annotations

import pytest
from conftest import GENERATED_AT, KICKOFF, SNAPSHOT_TS, build, config, kalshi_row, nfl_snapshot

from paper import sources


# --- rule 1: the price must have been observed before kickoff -----------------

@pytest.mark.parametrize("snapshot_ts", [
    KICKOFF,                                        # exactly at kickoff is not before it
    "2026-10-18T18:00:00+00:00",                    # an hour after kickoff
    "2026-10-19T00:00:00+00:00",                    # the next day
    "2026-10-20T17:00:00+00:00",                    # after close_time, i.e. long settled
])
def test_a_price_observed_at_or_after_kickoff_is_never_logged(snapshot_ts):
    made, skipped = build([kalshi_row(snapshot_ts=snapshot_ts)])
    assert made == []
    assert skipped.get("price_at_or_after_kickoff") == 1


def test_a_price_before_kickoff_is_logged_even_though_close_time_is_long_past():
    """The trap: Kalshi keeps these markets open for days after the game.

    This row's close_time is two days AFTER kickoff, so any rule that used
    close_time as the cutoff would reject a perfectly legal pre-kickoff price —
    and any rule that used it to mean "safe" would let a post-final price in. The
    comparison is against occurrence, and this row survives because its snapshot
    is a day early.
    """
    row = kalshi_row()
    assert sources.kickoff(row) == sources.parse_ts(KICKOFF)
    assert sources.parse_ts(row["close_time"]) > sources.kickoff(row)
    made, _ = build([row])
    assert len(made) == 1


def test_the_logged_price_comes_from_the_logged_row_and_nowhere_else():
    """Two snapshots of one market: the candidate carries the FIRST price.

    The second row is priced differently and observed later. It may not change
    the price already on file, and it may not produce a second candidate.
    """
    early = kalshi_row(snapshot_ts="2026-10-16T20:00:00+00:00", yes_ask=0.30, yes_bid=0.28)
    late = kalshi_row(snapshot_ts="2026-10-17T20:00:00+00:00", yes_ask=0.48, yes_bid=0.46)
    made, _ = build([early, late], generated_at="2026-10-16T12:00:00+00:00")

    assert len(made) == 1
    assert made[0]["market_price"] == 0.30
    assert made[0]["price_observed_at"] == "2026-10-16T20:00:00+00:00"


def test_the_later_observation_cannot_replace_a_price_already_on_file(ledger_path):
    """The same thing one run later: first write wins, in the file and not only
    in the builder."""
    from paper.ledger import Ledger
    ledger = Ledger(ledger_path)
    made, _ = build([kalshi_row(yes_ask=0.30, yes_bid=0.28)],
                    generated_at="2026-10-16T12:00:00+00:00")
    ledger.append_new(made)

    later, _ = build([kalshi_row(snapshot_ts="2026-10-17T20:00:00+00:00",
                                 yes_ask=0.48, yes_bid=0.46)],
                     generated_at="2026-10-17T12:00:00+00:00")
    assert ledger.append_new(later) == []
    assert ledger.candidates()[0]["market_price"] == 0.30


def test_a_bet_seen_first_without_provable_ordering_is_staked_once_it_is_provable():
    """The shadow-to-candidate upgrade, and why it is not hindsight.

    The model snapshot is generated at 19:00 on the 17th. A price from the 16th
    cannot be proven to predate it, so that observation is a shadow; a price from
    the 20:00 snapshot can. Logging the shadow would fix the id to an
    un-stakeable row forever and the valid candidate would be swallowed as a
    duplicate. Both observations predate kickoff and neither knows the result, so
    choosing between them is a data-quality rule, not a peek at the outcome.
    """
    early = kalshi_row(snapshot_ts="2026-10-16T20:00:00+00:00", yes_ask=0.30, yes_bid=0.28)
    late = kalshi_row(snapshot_ts="2026-10-17T20:00:00+00:00", yes_ask=0.48, yes_bid=0.46)
    made, _ = build([early, late])  # generated_at defaults to the 17th at 19:00

    assert len(made) == 1
    assert made[0]["kind"] == "candidate"
    assert made[0]["stake"] > 0
    assert made[0]["market_price"] == 0.48


def test_logged_at_is_the_observation_time_not_the_time_the_logger_ran():
    """A row written today carries the timestamp of the price, not of now()."""
    made, _ = build([kalshi_row(snapshot_ts="2026-10-01T03:00:00+00:00")])
    assert made[0]["logged_at"] == "2026-10-01T03:00:00+00:00"


def test_an_unreadable_timestamp_is_treated_as_proof_of_nothing():
    """Fails closed. A missing or malformed snapshot_ts cannot be ordered against
    kickoff, so the row is not logged — it is not quietly assumed to be early."""
    for bad in (None, "", "not a date", "2026-10-17 20:00:00"):
        made, skipped = build([kalshi_row(snapshot_ts=bad)])
        assert made == [], bad
        assert skipped.get("unreadable_snapshot_ts") == 1, bad


def test_a_naive_timestamp_is_unreadable_rather_than_assumed_utc():
    """`2026-10-17T20:00:00` with no offset cannot be compared against an aware
    kickoff without inventing a timezone, so it fails the same way."""
    made, skipped = build([kalshi_row(snapshot_ts="2026-10-17T20:00:00")])
    assert made == []
    assert skipped.get("unreadable_snapshot_ts") == 1


def test_a_row_with_no_kickoff_at_all_is_not_logged():
    made, skipped = build([kalshi_row(occurrence=None, close_time=None)])
    assert made == []
    assert skipped.get("no_kickoff") == 1


# --- rule 4: the probability must predate the price ---------------------------

def test_a_probability_published_after_the_price_is_a_shadow_not_a_candidate():
    """The leak this guards is invisible in the output: the row still looks fine.

    The model snapshot was generated an hour AFTER the price we logged, so the
    "pre-game" probability could already contain the price. It is logged as a
    shadow — kept, countable, un-stakeable — rather than as a candidate.
    """
    made, _ = build([kalshi_row()], generated_at="2026-10-17T21:00:00+00:00")

    assert len(made) == 1
    assert made[0]["kind"] == "shadow"
    assert made[0]["stake"] == 0.0
    assert made[0]["model_ordering_proven"] is False


def test_a_probability_published_at_the_same_second_is_accepted():
    """Equality is not a violation. A refresh that lands in the same second as
    the price has not seen anything the price did not."""
    made, _ = build([kalshi_row()], generated_at=SNAPSHOT_TS)
    assert made[0]["kind"] == "candidate"
    assert made[0]["model_ordering_proven"] is True


def test_a_probability_published_earlier_is_accepted():
    made, _ = build([kalshi_row()], generated_at="2026-10-17T09:00:00+00:00")
    assert made[0]["kind"] == "candidate"


def test_a_probability_with_no_timestamp_is_a_shadow():
    """Unprovable ordering is not an ordering."""
    made, _ = build([kalshi_row()], generated_at=None)
    assert made[0]["kind"] == "shadow"
    assert made[0]["model_ordering_proven"] is False


def test_a_game_with_a_final_score_is_never_a_candidate():
    """A settled game's probability is history. It must not be logged against a
    price that was observed before the game, because there was no bet to make."""
    snap = nfl_snapshot(generated_at=GENERATED_AT, played=True)
    made, skipped = build([kalshi_row()], snapshot=snap)
    assert made == []
    assert skipped.get("no_matching_game") == 1


# --- the price must be one you could actually have paid ----------------------

def test_a_midpoint_is_not_a_price_anybody_pays():
    """The NFL ladder route publishes (bid+ask)/2 as `p_over`. Using it as the
    buyable price would overstate every edge in the ledger by half the spread."""
    row = kalshi_row(yes_bid=0.38, yes_ask=0.40)
    assert sources.buyable_price(row, "yes") == 0.40
    assert (row["yes_bid"] + row["yes_ask"]) / 2 == 0.39


def test_a_dead_or_crossed_quote_is_not_logged():
    """No quote, a quote at 0 or 1 cent, and a book whose ask is below its bid are
    all reasons there was no price to pay."""
    for over in ({"yes_ask": None}, {"yes_ask": 0.0}, {"yes_ask": 1.0},
                 {"yes_bid": 0.55, "yes_ask": 0.40}):
        made, _ = build([kalshi_row(**over)])
        assert made == [], over


def test_a_no_side_price_is_the_no_ask_not_one_minus_the_yes_bid():
    row = kalshi_row(no_bid=0.58, no_ask=0.62)
    assert sources.buyable_price(row, "no") == 0.62


# --- liquidity: a quote you cannot trade is not a price ----------------------

def test_a_market_with_no_bid_is_not_logged():
    made, skipped = build([kalshi_row(yes_bid=0.0)])
    assert made == [] and skipped.get("no_bid") == 1


def test_a_market_with_no_bid_field_at_all_is_not_logged():
    made, skipped = build([kalshi_row(yes_bid=None)])
    assert made == [] and skipped.get("no_bid") == 1


def test_a_wide_spread_is_not_logged():
    # 40c bid, 50c ask = 10 points, above the default 8-point limit
    made, skipped = build([kalshi_row(yes_bid=0.40, yes_ask=0.50)])
    assert made == [] and skipped.get("spread_too_wide") == 1


def test_a_spread_at_exactly_the_limit_is_allowed():
    # 40c bid, 48c ask = 8 points, exactly the limit
    made, _ = build([kalshi_row(yes_bid=0.40, yes_ask=0.48)])
    assert len(made) == 1


def test_a_market_with_zero_volume_is_not_logged():
    made, skipped = build([kalshi_row(volume=0.0)])
    assert made == [] and skipped.get("zero_volume") == 1


def test_a_market_with_no_volume_field_is_not_logged():
    made, skipped = build([kalshi_row(volume=None)])
    assert made == [] and skipped.get("zero_volume") == 1


def test_a_dead_one_cent_ask_is_not_logged():
    made, skipped = build([kalshi_row(yes_bid=0.01, yes_ask=0.01)])
    assert made == [] and skipped.get("dead_quote") == 1


def test_a_dead_ninety_nine_cent_ask_is_not_logged():
    made, skipped = build([kalshi_row(yes_bid=0.98, yes_ask=0.99)])
    assert made == [] and skipped.get("dead_quote") == 1


def test_a_candidate_carries_the_liquidity_fields_it_was_checked_against():
    made, _ = build([kalshi_row(yes_bid=0.38, yes_ask=0.40, volume=100.0, open_interest=50.0)])
    assert len(made) == 1
    row = made[0]
    assert row["yes_bid"] == 0.38
    assert row["no_bid"] == 0.58
    assert row["spread_points"] == 2.0
    assert row["volume"] == 100.0
    assert row["open_interest"] == 50.0


def test_a_candidate_carries_the_model_fingerprint_from_its_snapshot():
    snap = nfl_snapshot(generated_at=GENERATED_AT)
    snap["model_fingerprint"] = "abc123"
    made, _ = build([kalshi_row()], snapshot=snap)
    assert made[0]["model_fingerprint"] == "abc123"


def test_a_missing_fingerprint_is_recorded_as_none_not_dropped():
    made, _ = build([kalshi_row()])
    assert "model_fingerprint" in made[0]
    assert made[0]["model_fingerprint"] is None
