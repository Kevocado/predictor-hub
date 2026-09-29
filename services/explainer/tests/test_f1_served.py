"""F1 is served, and what it says about a session is true.

This reverses a recorded decision. `SERVED_SPORTS` omitted `f1` because "a win
probability IS the explanation" -- which remains true of the win probability, and
was never an argument against the race story around it. The reversal is recorded
in the spec and in the ledger; this file is its enforcement.

F1's facts carry `win`, `podium`, `points` and `dnf` and NO line, so the spread
and total factors must not fire. That is not a degradation: a `KeyNumberTile`
comparing the model to a book would have nothing honest to draw, which was the
original reason, and it still holds for THOSE elements.
"""
from explainer.config import SERVED_SPORTS
from explainer.template import explain_from_template


def _f1_facts(**over):
    base = {
        "sport": "f1", "id": "s1", "title": "2026 Bahrain Grand Prix",
        "starts_at": "2026-03-15T15:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "Lando Norris", "prob": 0.34},
        "markets": [
            {"market": "win", "model": {
                "Lando Norris": 0.34, "Max Verstappen": 0.29, "Oscar Piastri": 0.24}},
            {"market": "podium", "model": {"Lando Norris": 0.88}},
        ],
        "drivers": [{"name": "Lando Norris"}, {"name": "Max Verstappen"}],
        "context": {}, "players": [],
        "record": {"label": "Picks made before the session", "hits": 9, "settled": 20},
        "result": None,
    }
    base.update(over)
    return base


def test_f1_is_served():
    assert "f1" in SERVED_SPORTS, (
        f"f1 is not in SERVED_SPORTS={SERVED_SPORTS}. The refusal was reversed: "
        f"a win probability is the explanation, but the race story around it is "
        f"not, and F1's facts carry it."
    )


def test_f1_gets_a_pick_and_a_record_and_nothing_it_cannot_support():
    out = explain_from_template(_f1_facts())
    factors = out["factors"]
    keys = [f["key"] for f in factors]
    heads = [f["headline"] for f in factors]
    text = " ".join(f["text"] for f in factors)

    # The three the test is NAMED for. `assert keys` alone proved only "at least
    # one factor", so deleting the pick row outright left `keys == ["record"]`
    # green -- the name promised a pick and a record and the body asserted
    # neither.
    assert "record" in keys, f"F1's bundle carries a 9/20 record and no record row: {keys}"
    assert "The pick" in heads, f"F1 has a pick and no pick row: {heads}"
    assert "Lando Norris" in text, f"the pick row does not name the pick: {text}"
    # And the record is a count read off `record`, not a placeholder.
    assert "9 of 20" in text, f"the record row does not read the record: {text}"

    # **On HEADLINES, not on keys.** The first version of these two assertions
    # read the factor KEYS, and both rows are keyed `str(market["market"])` -- so
    # a row that fired under a RENAMED market got a different key and sailed
    # straight past a check that was looking for the name it no longer had. The
    # reviewer ran that: F1's `win` market given a `model_margin` and a `line`,
    # and the spread row reading `... or by_key.get("win")`, renders
    #
    #     It projects a margin of 3.4 points, against a line of Norris by 3.4.
    #
    # and `"spread" not in keys` and `"total" not in keys` were BOTH true while
    # it was on screen. That is the model compared with itself, on the one sport
    # with no market line at all, and `_quoted_line`'s docstring names it as the
    # failure that helper exists to prevent.
    #
    # (The key list that reproduction prints has moved since the ruling and is
    # recorded here so nobody chases a stale one: it was `["context", "win",
    # "record"]` before `_outcome_key` learned `win`, and is `["win", "win",
    # "record"]` after -- the spread row and the pick row now collide with EACH
    # OTHER, which `tests/test_factor_keys.py` is what reports. Neither list has
    # a "spread" in it, which is the whole point.) The headline is the row's
    # identity and does not move with a market rename, so it is what the
    # assertion reads.
    assert "The line" not in heads, (
        f"F1 has no market line at all, so the spread row is the model compared "
        f"with itself -- the exact failure `_quoted_line` exists to prevent: {heads}"
    )
    assert "The total" not in heads, (
        f"F1's `points` market is not a `total`, and no quoted price exists to "
        f"read one against: {heads}"
    )


def test_f1s_pick_row_is_keyed_win_not_the_context_pseudo_market():
    """F1's pick is on `win`, so the row that carries it says `win`.

    `_outcome_key` recognises `result` (PL's three-way market) and `moneyline`
    (NFL's and CFB's pick market) and falls through to `context` otherwise. F1
    has neither name -- its markets are `win` and `podium` -- so the pick row
    fell into `context`, the pseudo-market, and collided with the rebuilt-
    disclosure row, which is also `context`.

    **`context` is not a market and the collision is not cosmetic.**
    `FactorList` renders `data-testid={`factor-${factor.key}`}` and lights a row
    on `highlighted === factor.key`, so two factors keyed `context` render two
    elements with the same `data-testid` and selecting either lights both. And
    `contract.resolve_factors` keeps a key only if it is in
    `market_keys(facts) | PSEUDO_MARKETS`, so the pick row was being kept by the
    pseudo-market allowance rather than by naming the market it is about.

    Asserted on the ROW, not on the key list: the assertion has to be about this
    factor, and a list membership cannot say which factor it found.
    """
    out = explain_from_template(_f1_facts())
    pick = next((f for f in out["factors"] if f["headline"] == "The pick"), None)
    assert pick is not None, f"F1 has a pick and no pick row: {out['factors']}"
    assert pick["key"] == "win", (
        f"F1's pick row is keyed {pick['key']!r}, not 'win'. F1's facts carry a "
        f"`win` market, so `win` is the market this row is about; `context` is "
        f"the pseudo-market the key falls through to when no market name matches, "
        f"and it is the same key the rebuilt-disclosure row uses, so the panel "
        f"renders two `factor-context` testids and lights both when either is "
        f"selected."
    )


def test_f1_names_the_session_not_a_kickoff():
    """A rebuilt session says the session, because `_START["f1"]` exists for
    exactly that and the default would say "kickoff"."""
    out = explain_from_template(_f1_facts(pick_timing="rebuilt"))
    text = " ".join(f["text"] for f in out["factors"])
    assert "after the session started" in text, text
    assert "kickoff" not in text, text
