"""F1: a Kalshi F1 contract is ONE DRIVER's contract, not a game's.

Every other sport in this ledger prices a game: the model publishes a
probability for the home side and another for the away side, and the Kalshi
rung names which side it is. F1 has no sides. Kalshi lists one binary
market per driver per race -- "Main Race: Max Verstappen wins" -- so the
probability that belongs to a rung is that DRIVER's own probability for that
race, and the lookup is by (race, driver) rather than by home/away.

Three of those rules are about not fooling ourselves, and each gets a test
here:

  * the probability must be that driver's own. A wrong driver must not be
    handed another driver's number;
  * a prediction the model published AFTER the session it is about (a
    backtest, or a rebuild the tracking store cannot vouch for) is not a
    forward-looking prediction and is never paired with a live price;
  * Kalshi's F1 `occurrence_datetime` runs about six hours LATER than the
    session it names -- verified against Kalshi's own finalisation
    timestamps, which for the Singapore, Dutch and Azerbaijan races are
    published BEFORE Kalshi's stated occurrence, which cannot be true of a
    race start. So the cutoff is the EARLIER of Kalshi's occurrence and the
    session time the snapshot knows, and a price seen after the real start
    is not logged even though Kalshi's own field would let it through.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from conftest import config

from paper import sources
from paper.log import candidate_rows

# --- the real world's values, read off Kalshi and the F1 snapshot -----------

#: Kalshi's own `occurrence_datetime` for `KXF1RACE-UNIS26`.
KALSHI_RACE_OCCURRENCE = "2026-10-26T02:00:00+00:00"
#: The snapshot's `race_datetime` for round 18 (United States Grand Prix).
RACE_START = "2026-10-25T20:00:00+00:00"
#: Kalshi's own `occurrence_datetime` for `KXF1POLE-UNIS26`.
KALSHI_POLE_OCCURRENCE = "2026-10-25T03:00:00+00:00"
#: The snapshot's qualifying session start for round 18.
QUALI_START = "2026-10-24T21:00:00+00:00"

#: Kalshi's own quote for `KXF1RACE-UNIS26-VER` on 2026-10-21: 42c.
REAL_YES_BID, REAL_YES_ASK = 0.40, 0.42

#: A price observed after the round-18 race started but before Kalshi's
#: (six hours late) occurrence. Kalshi's own field would accept it; the
#: race is over and it must not be logged.
AFTER_THE_RACE = "2026-10-25T21:00:00+00:00"
BEFORE_THE_RACE = "2026-10-22T12:00:00+00:00"

GENERATED_AT = "2026-10-21T22:00:16+00:00"


def kalshi_row(**over) -> dict:
    """One Kalshi F1 rung: `KXF1RACE-UNIS26-VER`.

    The price is NOT Kalshi's real one. The real quote was 42c against the
    model's 12.6%, which is no edge at all, so the fixture prices below the
    model to exercise the edge rule;
    `test_the_real_kalshi_price_has_no_edge` pins the real quote.
    """
    series = over.pop("series", "KXF1RACE")
    # Kalshi's real event tickers: `<SERIES>-<GP CODE><YY>` for a race
    # weekend, `<SERIES>-<YY>` for a season-long contract.
    gp = "26" if series == "KXF1" else "UNIS26"
    event_ticker = over.pop("event_ticker", f"{series}-{gp}")
    row = {
        "snapshot_ts": BEFORE_THE_RACE,
        "series": series,
        "stat": "race_win",
        "ticker": f"{event_ticker}-VER",
        "title": "Main Race: Max Verstappen wins",
        "event_ticker": event_ticker,
        "player": None,
        "line": None,
        "yes_bid": 0.03,
        "yes_ask": 0.04,
        "no_bid": 0.96,
        "no_ask": 0.97,
        "last": 0.04,
        "volume": 21774.68,
        "open_interest": 21774.68,
        "status": "active",
        "result": None,
        "settlement_value": None,
        "occurrence": KALSHI_RACE_OCCURRENCE,
        "close_time": "2026-11-02T02:00:00+00:00",
    }
    row.update(over)
    return row


def f1_snapshot(**over) -> dict:
    """The F1 site's published snapshot, trimmed to rounds 18 and 19.

    The numbers are the real ones from `data/public_snapshot.json` in
    F1_Predictor at commit 4a57902.
    """
    snapshot = {
        "generated_at": GENERATED_AT,
        "season": 2026,
        "current_round": 18,
        "races": [
            {"season": 2026, "round": 18, "race_name": "United States Grand Prix",
             "circuit_name": "Circuit of the Americas",
             "race_datetime": RACE_START, "is_sprint_weekend": False, "completed": False},
            {"season": 2026, "round": 19, "race_name": "Mexico City Grand Prix",
             "circuit_name": "Autodromo Hermanos Rodriguez",
             "race_datetime": "2026-11-01T20:00:00+00:00",
             "is_sprint_weekend": False, "completed": False},
        ],
        "predictions": {
            "18": {
                "season": 2026, "round": 18, "race_name": "United States Grand Prix",
                "tier": "pre_weekend", "source": "live",
                "predictions": [
                    {"driver_id": "leclerc", "constructor_id": "ferrari",
                     "p_win": 0.1366, "p_podium": 0.3793, "p_points_finish": 0.8143,
                     "p_dnf": 0.1391},
                    {"driver_id": "max_verstappen", "constructor_id": "red_bull",
                     "p_win": 0.1258, "p_podium": 0.3491, "p_points_finish": 0.7837,
                     "p_dnf": 0.1588},
                    {"driver_id": "antonelli", "constructor_id": "mercedes",
                     "p_win": 0.095, "p_podium": 0.2754, "p_points_finish": 0.7135,
                     "p_dnf": 0.1902},
                ],
            },
        },
        "session_predictions": {
            "qualifying": {
                "18": {
                    "season": 2026, "round": 18, "race_name": "United States Grand Prix",
                    "session_type": "qualifying", "tier": "pre_weekend", "source": "live",
                    "session_datetime": QUALI_START,
                    "predictions": [
                        {"driver_id": "antonelli", "p_pole": 0.1203, "p_top_3": 0.3296,
                         "p_top_10": 0.8552},
                        {"driver_id": "max_verstappen", "p_pole": 0.1138, "p_top_3": 0.3343,
                         "p_top_10": 0.859},
                        {"driver_id": "russell", "p_pole": 0.1064, "p_top_3": 0.3142,
                         "p_top_10": 0.8343},
                    ],
                },
            },
        },
        "championship": {
            "drivers": {
                "season": 2026, "as_of_round": 17, "n_trials": 2000,
                "standings": [
                    {"entity_id": "antonelli", "win_prob": 0.998, "top3_prob": 1.0},
                    {"entity_id": "russell", "win_prob": 0.0015, "top3_prob": 0.9485},
                ],
            },
        },
    }
    snapshot.update(over)
    return snapshot


def f1_config(**over) -> dict:
    """The committed allow-list's F1 entries, on top of the shared fixture."""
    cfg = config()
    cfg["segments"] = cfg["segments"] + [
        {"segment": f"f1:{market}", "sport": "f1", "market": market}
        for market in ("race_win", "race_podium", "top10", "pole", "championship")
    ]
    # The same bands the committed config gives F1: a race is spread over
    # two dozen drivers, so the model's per-driver probabilities live well
    # below 0.50. `test_the_committed_config_gives_f1_its_own_bands` pins the
    # committed copy against this one.
    cfg["confidence_buckets_by_sport"] = {
        "f1": [[0.05, 0.10], [0.10, 0.20], [0.20, 0.30], [0.30, 0.40],
               [0.40, 0.50], [0.50, 0.60], [0.60, 0.70], [0.70, 0.80],
               [0.80, 0.90], [0.90, 1.01]],
    }
    cfg.update(over)
    return cfg


def build(rows, *, snapshot=None, cfg=None):
    """Run the candidate builder over F1 rows against the F1 snapshot."""
    snap = snapshot if snapshot is not None else f1_snapshot()
    return candidate_rows(
        copy.deepcopy(rows),
        {"f1": sources.snapshot_games(snap, "f1")},
        cfg if cfg is not None else f1_config(),
    )


# --- the probability is the driver's own --------------------------------------

def test_a_driver_contract_gets_that_driver_s_own_probability():
    """Two drivers, two contracts, two numbers. Not one number for both."""
    rows = [
        kalshi_row(ticker="KXF1RACE-UNIS26-VER", title="Main Race: Max Verstappen wins"),
        kalshi_row(ticker="KXF1RACE-UNIS26-LEC", title="Main Race: Charles Leclerc wins"),
    ]
    made, _ = build(rows)
    by_driver = {row["selection"]: row["model_p"] for row in made}
    assert by_driver == {"max_verstappen": 0.1258, "leclerc": 0.1366}


def test_a_driver_contract_never_gets_another_driver_s_probability():
    """The mistake this guards: one number reused for the whole field.

    Russell has a qualifying probability in this snapshot but no RACE
    probability, so his race contract must produce no row -- not
    Verstappen's 12.6%, not a zero.
    """
    rows = [kalshi_row(ticker="KXF1RACE-UNIS26-RUS", title="Main Race: George Russell wins")]
    made, skipped = build(rows)
    assert made == []
    assert skipped.get("no_model_probability") == 1


def test_a_contract_for_a_driver_the_model_does_not_price_logs_nothing():
    """No probability is not a zero. A zero would be a claim; a guess is worse."""
    rows = [kalshi_row(title="Main Race: Lando Norris wins")]
    made, skipped = build(rows)
    assert made == []
    assert skipped.get("f1_no_driver") == 1


def test_a_driver_with_no_probability_for_that_market_logs_nothing():
    """The driver is known; this market's probability is not published."""
    snapshot = f1_snapshot()
    snapshot["session_predictions"]["qualifying"]["18"]["predictions"] = [
        r for r in snapshot["session_predictions"]["qualifying"]["18"]["predictions"]
        if r["driver_id"] != "max_verstappen"
    ]
    rows = [kalshi_row(series="KXF1POLE", stat="pole",
                       ticker="KXF1POLE-UNIS26-VER",
                       title="Max Verstappen is awarded Pole Position",
                       occurrence=KALSHI_POLE_OCCURRENCE)]
    made, skipped = build(rows, snapshot=snapshot)
    assert made == []
    assert skipped.get("no_model_probability") == 1


# --- the event ticker resolves to the right race ----------------------------

def test_a_kalshi_event_ticker_resolves_to_the_right_race():
    """`KXF1RACE-UNIS26` is the United States Grand Prix, round 18.

    Pinned against the real Kalshi event ticker and the snapshot's own
    race list: the mapping is by WHEN the session starts, because Kalshi's
    grand-prix code is respelled every season (2025's `AGP25` is 2026's
    `AUSGP26`) and carries nothing the snapshot does not already know.
    """
    games = sources.snapshot_games(f1_snapshot(), "f1")
    row = kalshi_row()
    game = sources.join_f1_race(row, games, "race")
    assert game is not None
    assert game["round"] == 18
    assert game["race_name"] == "United States Grand Prix"


def test_an_event_ticker_that_is_not_in_the_snapshot_resolves_to_nothing():
    """Fails closed: an unknown weekend is not a nearby weekend."""
    games = sources.snapshot_games(f1_snapshot(), "f1")
    row = kalshi_row(event_ticker="KXF1RACE-MEXGP26", occurrence="2026-11-02T02:00:00+00:00")
    assert sources.join_f1_race(row, games, "race") is None


# --- the price is the ask, and it is before the session ---------------------

def test_a_driver_contract_is_priced_at_the_ask_not_the_midpoint():
    """A midpoint is not a price anybody pays."""
    row = kalshi_row(yes_bid=0.03, yes_ask=0.04)
    made, _ = build([row])
    assert len(made) == 1
    assert made[0]["market_price"] == 0.04
    assert made[0]["market_price"] != (row["yes_bid"] + row["yes_ask"]) / 2


def test_the_real_kalshi_price_has_no_edge():
    """Kalshi's own 42c against the model's 12.6% is a 29-point disagreement.

    The model is not better than the market on this contract, so no row is
    logged: that is the ledger working, not the ledger failing.
    """
    made, skipped = build([kalshi_row(yes_bid=REAL_YES_BID, yes_ask=REAL_YES_ASK)])
    assert made == []
    assert skipped.get("below_edge_threshold") == 1


def test_a_price_seen_after_the_real_start_is_not_logged():
    """Kalshi's F1 occurrence is six hours late; the real start is the cutoff.

    This price is after the race (20:00 on the 25th) but before Kalshi's
    stated occurrence (02:00 on the 26th), so a rule that trusted
    Kalshi's field alone would log a bet on a race that was already over.
    """
    made, skipped = build([kalshi_row(snapshot_ts=AFTER_THE_RACE)])
    assert made == []
    assert skipped.get("price_at_or_after_kickoff") == 1


def test_a_price_seen_before_the_real_start_is_logged():
    made, _ = build([kalshi_row(snapshot_ts=BEFORE_THE_RACE)])
    assert len(made) == 1
    assert made[0]["kickoff"] == "2026-10-25T20:00:00+00:00"


def test_a_driver_contract_with_no_liquidity_is_not_logged():
    """The liquidity rules are the same for F1 as for everything else."""
    for over in ({"volume": 0.0}, {"yes_bid": 0.0}, {"yes_ask": 0.01}):
        made, _ = build([kalshi_row(**over)])
        assert made == [], over


# --- the no-hindsight rules --------------------------------------------------

def test_a_backtest_prediction_is_never_paired_with_a_live_price():
    """A backtest is a replay computed after the race. It is history."""
    snapshot = f1_snapshot()
    snapshot["predictions"]["18"]["source"] = "backtest"
    made, skipped = build([kalshi_row()], snapshot=snapshot)
    assert made == []
    assert skipped.get("f1_hindsight_prediction") == 1


def test_a_rebuilt_prediction_is_never_paired_with_a_live_price():
    """`rebuilt` means the tracking store cannot vouch for the snapshot."""
    snapshot = f1_snapshot()
    snapshot["predictions"]["18"]["source"] = "rebuilt"
    made, skipped = build([kalshi_row()], snapshot=snapshot)
    assert made == []
    assert skipped.get("f1_hindsight_prediction") == 1


def test_a_pole_contract_is_not_priced_from_a_post_qualifying_tier():
    """After qualifying, the grid is known. The model would know too.

    A `post_qualifying` tier for the qualifying session was computed after
    that session started, so pairing it with a pre-session price is the
    same leak as a backtest, just with a respectable label on it.
    """
    snapshot = f1_snapshot()
    snapshot["session_predictions"]["qualifying"]["18"]["tier"] = "post_qualifying"
    rows = [kalshi_row(series="KXF1POLE", stat="pole",
                       ticker="KXF1POLE-UNIS26-VER",
                       title="Max Verstappen is awarded Pole Position",
                       occurrence=KALSHI_POLE_OCCURRENCE)]
    made, skipped = build(rows, snapshot=snapshot)
    assert made == []
    assert skipped.get("f1_hindsight_prediction") == 1


def test_a_pole_contract_is_priced_at_the_qualifying_probability():
    """The pole contract is about the qualifying session, so it is priced
    from the qualifying session's prediction -- not the race's."""
    rows = [kalshi_row(series="KXF1POLE", stat="pole",
                       ticker="KXF1POLE-UNIS26-VER",
                       title="Max Verstappen is awarded Pole Position",
                       occurrence=KALSHI_POLE_OCCURRENCE)]
    made, _ = build(rows)
    assert len(made) == 1
    assert made[0]["model_p"] == 0.1138
    assert made[0]["market"] == "pole"
    assert made[0]["kickoff"] == "2026-10-24T21:00:00+00:00"


# --- the markets the model can and cannot price -----------------------------

def test_a_series_the_model_publishes_no_probability_for_is_skipped():
    """Kalshi's top-5 and fastest-lap markets exist. The model has no
    probability for either, so nothing is logged -- no guess, no zero."""
    for series, stat, title in (
        ("KXF1TOP5", "top5", "Main Race: Max Verstappen to finish top 5"),
        ("KXF1FASTLAP", "fastest_lap", "Main Race Fastest Lap: Max Verstappen"),
        ("KXF1OCCUR", "occurrence", "Will the 2026 F1 Abu Dhabi Grand Prix main race take place?"),
    ):
        made, skipped = build([kalshi_row(series=series, stat=stat, title=title)])
        assert made == [], series
        assert skipped.get("f1_unpriceable_series") == 1, series


def test_the_top_ten_contract_is_priced_at_the_points_finish_probability():
    """`p_points_finish` is P(finish in the points) and the points table
    ends at P10, so it is exactly Kalshi's "to finish top 10"."""
    rows = [kalshi_row(series="KXF1TOP10", stat="top10",
                       ticker="KXF1TOP10-UNIS26-VER",
                       title="Main Race: Max Verstappen to finish top 10")]
    made, _ = build(rows)
    assert len(made) == 1
    assert made[0]["model_p"] == 0.7837
    assert made[0]["market"] == "top10"


def test_the_podium_contract_is_priced_at_the_podium_probability():
    rows = [kalshi_row(series="KXF1RACEPODIUM", stat="race_podium",
                       ticker="KXF1RACEPODIUM-UNIS26-VER",
                       title="Main Race: Max Verstappen to finish top 3")]
    made, _ = build(rows)
    assert len(made) == 1
    assert made[0]["model_p"] == 0.3491
    assert made[0]["market"] == "race_podium"


# --- the drivers' championship is a season-long contract --------------------

def test_the_championship_contract_is_priced_at_the_championship_probability():
    """`KXF1-26` is a season-long futures market, not a race.

    The snapshot publishes a per-driver championship probability
    (`championship.drivers.standings[].win_prob`), so the contract is
    priceable -- and it is a different kind of contract, scoped to the
    season rather than to a race.
    """
    rows = [kalshi_row(series="KXF1", stat="championship",
                       ticker="KXF1-26-ANT",
                       title="Will Andrea Kimi Antonelli win the F1 Drivers Championship?",
                       event_ticker="KXF1-26",
                       occurrence=None,
                       close_time="2026-12-22T15:00:00+00:00")]
    made, _ = build(rows)
    assert len(made) == 1
    assert made[0]["model_p"] == 0.998
    assert made[0]["market"] == "championship"
    # The season is decided by the last race, so that is the cutoff.
    assert made[0]["kickoff"] == "2026-11-01T20:00:00+00:00"


def test_a_championship_contract_for_another_season_is_not_priced():
    """A 2025 championship market is a different contract from a 2026 one.

    The snapshot's championship probability is for the 2026 season, so the
    event ticker's year has to be the snapshot's year.
    """
    rows = [kalshi_row(series="KXF1", stat="championship",
                       ticker="KXF1-25-ANT",
                       title="Will Andrea Kimi Antonelli win the F1 Drivers Championship?",
                       event_ticker="KXF1-25",
                       snapshot_ts="2025-10-20T12:00:00+00:00",
                       occurrence=None,
                       close_time="2025-12-22T15:00:00+00:00")]
    made, skipped = build(rows)
    assert made == []
    assert skipped.get("f1_no_matching_race") == 1


# --- the driver is found by name, with no table to maintain ------------------
def test_every_real_kalshi_f1_driver_title_resolves_to_its_snapshot_driver():
    """The mapping is the title's own words, so it needs no maintained table.

    These are Kalshi's real market titles for the 2026 United States Grand
    Prix, and the snapshot's own driver ids.
    """
    titles = {
        "Alexander Albon": "albon",
        "Fernando Alonso": "alonso",
        "Andrea Kimi Antonelli": "antonelli",
        "Oliver Bearman": "bearman",
        "Gabriel Bortoleto": "bortoleto",
        "Valtteri Bottas": "bottas",
        "Franco Colapinto": "colapinto",
        "Pierre Gasly": "gasly",
        "Isack Hadjar": "hadjar",
        "Lewis Hamilton": "hamilton",
        "Nico Hulkenberg": "hulkenberg",
        "Liam Lawson": "lawson",
        "Charles Leclerc": "leclerc",
        "Arvid Lindblad": "arvid_lindblad",
        "Lando Norris": "norris",
        "Esteban Ocon": "ocon",
        "Sergio Perez": "perez",
        "Oscar Piastri": "piastri",
        "George Russell": "russell",
        "Carlos Sainz Jr.": "sainz",
        "Lance Stroll": "stroll",
        "Max Verstappen": "max_verstappen",
    }
    drivers = list(titles.values())
    for name, driver_id in titles.items():
        assert sources.f1_driver(f"Main Race: {name} wins", drivers) == driver_id, name


def test_a_title_that_names_two_drivers_resolves_to_nothing():
    """Ambiguity is not a coin toss."""
    drivers = ["max_verstappen", "russell"]
    assert sources.f1_driver("Main Race: Max Verstappen beats George Russell", drivers) is None


def test_a_title_that_names_no_driver_resolves_to_nothing():
    assert sources.f1_driver("Main Race: the field wins", ["max_verstappen"]) is None


# --- the segment allow-list --------------------------------------------------

def test_the_committed_config_gives_f1_its_own_confidence_bands():
    """F1's probabilities live well below 0.50, so F1 needs its own bands.

    A race is spread over two dozen drivers: the model's best race-winner
    probability for the United States Grand Prix is 13.7%. The 0.50+ bands
    that suit a two-sided game would exclude every F1 contract there is,
    so F1 gets its own. The other sports keep the bands they had, which is
    what makes this an addition and not a loosening.
    """
    committed = json.loads(
        (Path(__file__).resolve().parents[3] / "data" / "paper" / "segments.json")
        .read_text(encoding="utf-8"))
    assert committed["confidence_buckets"] == [[0.50, 0.60], [0.60, 0.70],
                                               [0.70, 0.80], [0.80, 0.90],
                                               [0.90, 1.01]]
    bands = committed["confidence_buckets_by_sport"]["f1"]
    for model_p in (0.1366, 0.1258, 0.095, 0.3793, 0.8143, 0.1138, 0.998):
        assert any(lo <= model_p < hi for lo, hi in bands), model_p


def test_the_committed_config_allows_exactly_the_priceable_f1_markets():
    """Five contracts the model can price, and no others."""
    committed = json.loads(
        (Path(__file__).resolve().parents[3] / "data" / "paper" / "segments.json")
        .read_text(encoding="utf-8"))
    allowed = {e["market"] for e in committed["segments"] if e.get("sport") == "f1"}
    assert allowed == set(sources.F1_SERIES_MARKETS.values())
    # And every F1 series the model cannot price is not on the list.
    assert "top5" not in allowed and "fastest_lap" not in allowed


def test_an_f1_market_outside_the_allow_list_is_a_shadow_not_a_candidate():
    """Shadow rows are countable; they carry no stake."""
    cfg = f1_config()
    cfg["segments"] = [s for s in cfg["segments"] if s["market"] != "race_win"]
    made, _ = build([kalshi_row()], cfg=cfg)
    assert len(made) == 1
    assert made[0]["kind"] == "shadow"
    assert made[0]["stake"] == 0.0


def test_the_same_contract_observed_twice_is_one_row():
    """One bet, two observations: the first price stands."""
    early = kalshi_row(snapshot_ts="2026-10-22T12:00:00+00:00", yes_bid=0.03, yes_ask=0.04)
    late = kalshi_row(snapshot_ts="2026-10-23T12:00:00+00:00", yes_bid=0.06, yes_ask=0.07)
    made, _ = build([early, late])
    assert len(made) == 1
    assert made[0]["market_price"] == 0.04
