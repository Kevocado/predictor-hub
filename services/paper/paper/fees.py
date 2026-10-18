"""
kalshi_fees.py — Kalshi's exact fee formula, for the paper ledger.

VERBATIM COPY. Do not edit the arithmetic here.

Source of truth: `shared/kalshi_fees.py` in `algo-trade-hub-prod`
(github.com/Kevocado/algo-trade-hub), read at commit 12432be
(branch fix-health-untracked-timers) on 2026-10-17. Its pin tests live beside it
as `tests/test_kalshi_fee_pins.py` and are copied into this repo as
`services/paper/tests/test_fees_pins.py`; they rewrite this file in memory and
require the pins to FAIL for every mutant, so any edit that changes the rounding
or the rate breaks CI here too.

Why copy rather than import: that repo is a separate service with its own
dependencies, and this one must stay dependency-free. Duplicating five lines of
published arithmetic is cheaper than a cross-service import, and the pin tests
are what keep the two copies honest.

Kalshi's published general fee schedule rounds the total fee for an order
up to the next cent. With P expressed as a probability in [0, 1] and C as
the number of contracts:
    taker fee = round_up(0.07 * C * P * (1 - P)) dollars
    maker fee = round_up(0.0175 * C * P * (1 - P)) dollars
The maker rate is 25% of the taker rate for the markets that charge maker
fees. This helper returns cents, so it rounds the calculated cent amount
once, after applying the contract count.

Each Kalshi contract has $1 notional, so a fee expressed in cents is
numerically the same as a fee expressed in percentage points of edge on a
single contract — that lets net_edge_pct() subtract fee cents directly
from a model-vs-market edge expressed in percentage points.

The ledger is paper-only and always assumes a TAKER fill: it logs the price it
could actually have bought at (the ask), so a maker rate would be the wrong
number to quote against it.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


TAKER_RATE = 0.07
MAKER_SHARE = 0.25


def _ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def _whole_price_cents(price_cents: float) -> int:
    value = Decimal(str(price_cents))
    rounded = value.to_integral_value(rounding=ROUND_HALF_UP)
    return max(0, min(100, int(rounded)))


def kalshi_fee_cents(price_cents: float, *, contracts: int = 1, maker: bool = False) -> float:
    """
    Returns the total fee, in whole cents, for trading `contracts` contracts
    at `price_cents` (e.g. 45.0 for a 45c YES contract).

    The fee is calculated with integer cent arithmetic so floating-point dust
    cannot turn an exact fee into an extra cent.
    """
    if contracts <= 0:
        return 0.0
    p = _whole_price_cents(price_cents)
    numerator = 7 * contracts * p * (100 - p)
    denominator = 40000 if maker else 10000
    return float(_ceil_div(numerator, denominator))


def net_edge_pct(model_prob_pct: float, kalshi_price_cents: float, *, contracts: int = 1, maker: bool = False) -> float:
    """
    Edge in percentage points after subtracting Kalshi's per-contract fee.
    The fee always works against the position, regardless of direction.
    """
    gross_edge_pct = model_prob_pct - kalshi_price_cents
    fee_cents_total = kalshi_fee_cents(kalshi_price_cents, contracts=contracts, maker=maker)
    fee_pct_per_contract = fee_cents_total / contracts
    return gross_edge_pct - fee_pct_per_contract
