"""Fee-schedule pins with mutation-grade teeth.

A verbatim copy of `tests/test_kalshi_fee_pins.py` from `algo-trade-hub-prod`
(commit 12432be, read 2026-10-17), retargeted from `shared.kalshi_fees` to
`paper.fees`. The source file it guards is a verbatim copy too, so a change to
either one that alters the published arithmetic has to break this file's pins.

`pins()` states the schedule three independent ways (an exact-fraction
reference, a golden table, and structural properties). The mutation tests then
rewrite `paper/fees.py` in memory, one constant or rounding rule at a time, and
require `pins()` to FAIL for every mutant. A pin that survives a mutation would
be decoration.
"""

from fractions import Fraction
from math import ceil
from pathlib import Path

import pytest

import paper.fees as fees

SOURCE = Path(fees.__file__).read_text(encoding="utf-8")
PRICES = range(101)
COUNTS = (1, 2, 3, 7, 10, 25, 100, 1000, 99999)  # 99999 exposes a one-part-in-10000 denominator error


def reference_cents(price: int, contracts: int, *, maker: bool) -> int:
    rate = Fraction(7, 400) if maker else Fraction(7, 100)  # 0.0175 and 0.07, exactly
    p = Fraction(price, 100)
    return ceil(rate * contracts * p * (1 - p) * 100)  # dollars -> cents, rounded UP once, on the total


GOLDEN = {  # (price cents, contracts, maker) -> total fee cents; hand-checked against the published formula
    (50, 1, False): 2, (50, 1, True): 1, (50, 100, False): 175, (50, 100, True): 44,
    (10, 100, False): 63, (90, 100, False): 63, (5, 1, False): 1, (95, 1, False): 1,
    (0, 100, False): 0, (100, 100, False): 0, (44, 10, False): 18, (20, 25, True): 7,
    (10.5, 100, False): 69,  # half a cent rounds UP to 11c (63 would mean half-even, 10c)
}


def pins(module) -> None:
    for price in PRICES:
        for contracts in COUNTS:
            for maker in (False, True):
                got = module.kalshi_fee_cents(float(price), contracts=contracts, maker=maker)
                assert got == reference_cents(price, contracts, maker=maker), (price, contracts, maker, got)
    for (price, contracts, maker), cents in GOLDEN.items():
        assert module.kalshi_fee_cents(price, contracts=contracts, maker=maker) == cents
    for price in PRICES:  # symmetry: a YES at p and a NO at 100-p cost the same
        assert module.kalshi_fee_cents(float(price)) == module.kalshi_fee_cents(float(100 - price))
    assert module.kalshi_fee_cents(50.0, contracts=0) == 0.0  # nothing traded, nothing owed
    assert module.kalshi_fee_cents(49.5) == module.kalshi_fee_cents(50.0)  # half-cents round half up
    assert module.net_edge_pct(60.0, 50.0) == pytest.approx(10.0 - 2.0)  # the fee always works against you
    assert module.net_edge_pct(40.0, 50.0) == pytest.approx(-10.0 - 2.0)


def test_the_real_schedule_satisfies_every_pin():
    pins(fees)


MUTATIONS = {
    "taker rate 7 -> 6": ("7 * contracts * p * (100 - p)", "6 * contracts * p * (100 - p)"),
    "taker rate 7 -> 8": ("7 * contracts * p * (100 - p)", "8 * contracts * p * (100 - p)"),
    "maker share 40000 -> 30000": ("40000 if maker else 10000", "30000 if maker else 10000"),
    "maker share 40000 -> 20000": ("40000 if maker else 10000", "20000 if maker else 10000"),
    "taker denominator 10000 -> 10001": ("40000 if maker else 10000", "40000 if maker else 10001"),
    "round up -> round down": ("(numerator + denominator - 1) // denominator", "numerator // denominator"),
    "round up -> round nearest": ("(numerator + denominator - 1) // denominator",
                                  "(numerator + denominator // 2) // denominator"),
    "price rounding half-up -> half-even": ("rounding=ROUND_HALF_UP", "rounding=__import__('decimal').ROUND_HALF_EVEN"),
    "price clamp 100 -> 99": ("min(100, int(rounded))", "min(99, int(rounded))"),
    "fee per order not per contract": ("7 * contracts * p", "7 * 1 * p"),
    "maker pays the taker rate": ("40000 if maker else 10000", "10000"),
    "fee subtracted with the wrong sign": ("return gross_edge_pct - fee_pct_per_contract",
                                           "return gross_edge_pct + fee_pct_per_contract"),
}


def _load(source: str):
    namespace: dict = {"__name__": "mutant"}
    exec(compile(source, "mutant_kalshi_fees", "exec"), namespace)  # noqa: S102 - our own source, mutated
    return type("Mutant", (), namespace)


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_every_fee_mutation_is_caught_by_the_pins(name):
    old, new = MUTATIONS[name]
    assert SOURCE.count(old) == 1, f"mutation anchor {old!r} must appear exactly once in fees.py"
    with pytest.raises((AssertionError, ZeroDivisionError)):
        pins(_load(SOURCE.replace(old, new)))


def test_the_copy_still_names_the_file_it_came_from():
    """A verbatim copy with no provenance is just a second implementation."""
    head = SOURCE.split('"""')[1]
    assert "algo-trade-hub" in head, "the fee module must say which repo and commit it was copied from"
    assert "12432be" in head, "the fee module must pin the commit it was copied from"
