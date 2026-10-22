"""The ledger's evidence is GAMES, not bets.

A Kalshi ladder is many contracts on one game: a CFB game has a moneyline, a
spread ladder of a dozen rungs and a total ladder of a dozen more. The live
ledger makes the scale obvious -- 239 CFB candidates from 44 games, and 6 F1
contracts from a single race.

So the old gate, which counted every rung as an independent bet, could certify a
segment as "has an edge" on the strength of about twenty-five games. The
bootstrap had the same problem from the other end: resampling bets treats
thirteen rungs of one game as thirteen independent observations, so the
interval came out far too narrow.

Three things change:

  * a segment reports n_games next to n_bets, so the evidence is visible;
  * the pnl interval is a CLUSTER bootstrap -- each game's rungs are summed
    into one value, and the games are resampled;
  * a second floor, min_settled_games, has to be met ALONGSIDE the existing
    300-settled-bets floor.

Nothing existing is lowered. The 300-bet floor stays exactly where it is; the
game floor is added.
"""
from __future__ import annotations

import pytest

from conftest import config

from paper import stats
from paper.report import build, summarise
from paper.segments import gate as gate_of

GATE = gate_of(config())


def row(**over) -> dict:
    """A settled ledger row."""
    base = {
        "record": "candidate", "kind": "candidate", "id": "id0",
        "sport": "nfl", "market": "moneyline",
        "game_id": "g0", "ticker": "KXNFLGAME-26OCT18BALCLE-BAL", "selection": "BAL",
        "side": "yes", "line": None,
        "model_p": 0.60, "market_price": 0.50, "fee": 0.02, "edge": 8.0,
        "segment": "nfl:moneyline:0.60-0.70", "stake": 5.0,
        "status": "settled", "outcome": "yes", "pnl_per_contract": 0.48,
        "price_observed_at": "2026-10-17T20:00:00+00:00", "kickoff": "2026-10-18T17:00:00+00:00",
    }
    base.update(over)
    return base


def ladder_rows(n_games: int, rungs_per_game: int, *, pnl: float = 0.48,
                segment: str = "nfl:moneyline:0.60-0.70") -> list[dict]:
    """`n_games` games, each carrying `rungs_per_game` winning rungs.

    Every rung wins, so the BET-level interval is comfortably above zero -- which
    is the point: a bet-level test cannot tell this from 300 independent wins.
    """
    out = []
    for g in range(n_games):
        for r in range(rungs_per_game):
            out.append(row(
                id=f"g{g}r{r}",
                game_id=f"game{g}",
                ticker=f"KXNFLGAME-26OCT18BALCLE-G{g}R{r}",
                segment=segment,
                pnl_per_contract=pnl,
                stake=1.0,
            ))
    return out


# --- n_games beside n_bets ---------------------------------------------------

def test_a_segment_reports_the_games_as_well_as_the_bets():
    rows = ladder_rows(4, 3)
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_bets"] == 12
    assert s["n_games"] == 4


def test_a_segment_with_one_rung_per_game_counts_the_same_number_of_each():
    rows = ladder_rows(5, 1)
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_bets"] == 5
    assert s["n_games"] == 5


def test_the_game_count_is_distinct_games_not_rows():
    # The whole point: 12 rows on 4 games is 4 games of evidence.
    rows = ladder_rows(4, 3)
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_games"] != s["n_bets"]


def test_open_rows_do_not_count_towards_the_settled_game_count():
    rows = [row(id=f"o{i}", game_id="g0", status="open", outcome=None,
                pnl_per_contract=None) for i in range(5)]
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_settled_games"] == 0
    assert s["n_settled"] == 0


# --- the cluster bootstrap ---------------------------------------------------

def test_the_interval_resamples_games_not_bets():
    """The cluster bootstrap must be wider than the bet-level one.

    Thirteen rungs of one game are thirteen observations of the SAME thing. If
    the interval is computed by resampling bets, the thirteen count as
    independent evidence and the interval comes out narrow. Resampling games
    cannot manufacture that independence.
    """
    rows = ladder_rows(3, 13)
    pnls = [float(r["pnl_per_contract"]) for r in rows]
    by_bet = stats.bootstrap_mean_ci(pnls)
    by_game = stats.bootstrap_mean_ci_clustered(
        [(r["game_id"], float(r["pnl_per_contract"])) for r in rows]
    )
    assert by_bet is not None and by_game is not None
    # Same mean (every rung wins), but the clustered interval is wider because
    # there are only three independent draws in it.
    assert by_game[0] < by_bet[0] or by_game[1] > by_bet[1]


def test_the_cluster_bootstrap_sums_each_games_rungs_into_one_value():
    """Three games of thirteen winning rungs is three observations of 13 * 0.48."""
    rows = ladder_rows(3, 13)
    ci = stats.bootstrap_mean_ci_clustered(
        [(r["game_id"], float(r["pnl_per_contract"])) for r in rows]
    )
    assert ci is not None
    # Every game total is 13 * 0.48 = 6.24, so every bootstrap mean is 6.24.
    assert ci[0] == pytest.approx(6.24, abs=1e-6)
    assert ci[1] == pytest.approx(6.24, abs=1e-6)


def test_the_cluster_bootstrap_of_one_game_is_a_point():
    rows = ladder_rows(1, 13)
    ci = stats.bootstrap_mean_ci_clustered(
        [(r["game_id"], float(r["pnl_per_contract"])) for r in rows]
    )
    assert ci == pytest.approx((6.24, 6.24))


def test_the_cluster_bootstrap_of_nothing_is_none():
    assert stats.bootstrap_mean_ci_clustered([]) is None


def test_the_cluster_bootstrap_is_seeded():
    rows = ladder_rows(5, 4)
    pairs = [(r["game_id"], float(r["pnl_per_contract"])) for r in rows]
    assert stats.bootstrap_mean_ci_clustered(pairs) == stats.bootstrap_mean_ci_clustered(pairs)


# --- the second floor --------------------------------------------------------

def test_the_gate_has_a_second_floor_on_games():
    assert GATE["min_settled_games"] == 100


def test_a_segment_below_the_game_floor_cannot_qualify():
    """40 rungs from 3 games, every rung winning.

    The bet-level interval is far above zero -- that is asserted, not assumed
    -- and there are more than 300 bets if you add enough rungs -- but there
    are THREE games, and three games is not evidence about anything.
    """
    rows = ladder_rows(3, 40)
    pnls = [float(r["pnl_per_contract"]) for r in rows]
    # The bet-level interval really is above zero. If it were not, this test
    # would be passing for the wrong reason.
    bet_ci = stats.bootstrap_mean_ci(pnls)
    assert bet_ci is not None and stats.excludes_zero(bet_ci) is True
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    assert s["n_bets"] == 120
    assert s["n_games"] == 3
    assert s["qualifies_for_edge_claim"] is False
    assert any("game" in r for r in s["disqualifying"])


def test_300_bets_from_3_games_cannot_qualify():
    """The bet floor met, the game floor not: only the game floor can catch it.

    3 games x 100 rungs is 300 settled bets, so the floor that existed before
    this change is satisfied. Under the old code this segment QUALIFIED: the
    old gate read 832 bets from 64 games as 832 independent wins. The game
    floor is what stops it.
    """
    rows = ladder_rows(3, 100)
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    assert s["n_settled"] == 300, "the bet floor should be met by this fixture"
    assert s["n_settled_games"] == 3
    assert s["qualifies_for_edge_claim"] is False
    reasons = " ".join(s["disqualifying"])
    assert "settled games" in reasons
    assert "settled bets" not in reasons, "the bet floor is met, so it must not be the reason"


def test_the_existing_bet_floor_still_applies():
    """300 BETS from 300 games is not enough either -- the bet floor stands."""
    rows = ladder_rows(300, 1)
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    assert s["n_settled"] == 300
    assert s["n_settled_games"] == 300
    # The bet floor is met; what remains is the interval and the calibration
    # trend, which a 300-bet all-win fixture does clear. So the segment
    # qualifies -- and that is the point: 300 GAMES is real evidence.
    assert s["qualifies_for_edge_claim"] is True


def test_the_game_floor_and_the_bet_floor_are_both_reported():
    """Both floors, so the reader can see which one is short."""
    rows = ladder_rows(3, 40)          # 120 bets, 3 games
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    joined = " ".join(s["disqualifying"])
    assert "settled bets" in joined
    assert "games" in joined


# --- clustering by race for F1, and per game for props ----------------------

def test_f1_contracts_cluster_by_race():
    """Six F1 contracts from one race are one race of evidence."""
    rows = [
        row(id=f"f{i}", sport="f1", market="race_win", game_id="f1:2026:18",
            ticker=f"KXF1RACE-UNIS26-D{i}", segment="f1:race_win:0.10-0.20",
            pnl_per_contract=0.48, stake=1.0)
        for i in range(6)
    ]
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_bets"] == 6
    assert s["n_games"] == 1
    assert s["qualifies_for_edge_claim"] is False


def test_nfl_props_on_one_game_cluster_together():
    """Two props on one game are one game of evidence."""
    rows = [
        row(id=f"p{i}", market="receptions", game_id="g_same",
            ticker=f"KXNFLREC-26OCT18BALCLE-BAL-{i}", segment="nfl:receptions:0.50-0.60",
            pnl_per_contract=0.48, stake=1.0)
        for i in range(2)
    ] + [
        row(id=f"q{i}", market="receptions", game_id=f"g{i}",
            ticker=f"KXNFLREC-26OCT18BALCLE-BAL-Q{i}", segment="nfl:receptions:0.50-0.60",
            pnl_per_contract=0.48, stake=1.0)
        for i in range(10)
    ]
    s = summarise(rows, closing={}, gate_cfg=GATE)
    assert s["n_bets"] == 12
    assert s["n_games"] == 11


# --- the page's "why not yet" names whichever floor is short -------------------

def test_the_why_not_yet_names_the_game_floor_when_that_is_the_short_one():
    """300 BETS from 3 games: the bet floor is met, the game floor is not.

    The reason has to name the GAME floor, because that is the one that is
    missing -- a reader told only "settled bets" would not know the evidence
    is spread over three games, which is the whole point.
    """
    rows = ladder_rows(3, 100)          # 300 bets, 3 games
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    joined = " ".join(s["disqualifying"])
    assert "settled games" in joined
    # The bet floor IS met, so the bet shortfall must NOT be named.
    assert "only 300 settled bets" not in joined


def test_the_why_not_yet_names_the_bet_floor_when_that_is_the_short_one():
    """300 games but only 300 bets -- both met. Now 3 games and 120 bets: both
    short, so both are named."""
    rows = ladder_rows(3, 40)
    report = build(rows, closing={}, gate_cfg=GATE)
    s = report["segments"]["nfl:moneyline:0.60-0.70 :: unknown"]
    joined = " ".join(s["disqualifying"])
    assert "settled bets" in joined
    assert "settled games" in joined


def test_the_per_sport_row_also_carries_both_counts_and_both_floors():
    from paper.report import _per_sport
    rows = ladder_rows(3, 40)
    report = build(rows, closing={}, gate_cfg=GATE)
    # The per-sport roll-up is built from the same rows; its counts must agree
    # with the segment's, because a reader compares them.
    per_sport = report["per_sport"]["nfl"]
    assert per_sport["n_bets"] == 120
    assert per_sport["n_games"] == 3
    assert per_sport["n_settled_bets"] == 120
    assert per_sport["n_settled_games"] == 3
