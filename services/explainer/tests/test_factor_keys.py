"""A factor's `key` names the figure the panel lights for it, so two factors
sharing a key are two rows the reader cannot tell apart.

`FactorList` draws `data-testid={`factor-${factor.key}`}` and lights a row on
`highlighted === factor.key`. A body with two factors under one key therefore
renders two elements with the same testid, and selecting either lights both. The
panel's own tests already assume the keys are unique -- `getByTestId(
"factor-moneyline")` throws on a second match -- so uniqueness is a contract the
service owes the panel, not a nicety.

It was not upheld. F1's pick row was keyed `context` because `_outcome_key`
recognises `result` and `moneyline` and F1's market is `win`, so the pick row
fell through to the pseudo-market and landed on the rebuilt-disclosure row's key
-- two `factor-context` testids on a rebuilt session.

**This file checks the property over EVERY served sport, and that is the part
that matters.** F1 was found by reading F1; a sport nobody thought about would
not be. `SERVED` is derived from `config`, so a sport added tomorrow is covered
by this file with no edit.

**The one pair the design shares on purpose, and why it is named rather than
fixed.** `_outcome_key`'s docstring says it is "the market a pick **or an
outcome** belongs to", and on a finished game the "How it finished" row and the
"The pick" row are two sentences about the same market. §13c links a row to a
FIGURE, and both rows name the moneyline's, so both lighting is the linkage
working. Making them distinct needs a key the panel resolves but that is not the
pick's market -- either a third pseudo-market, which would stop the "How it
finished" row lighting the moneyline tile on every finished game, or a change to
the key vocabulary, which is a decision about what the panel draws. Neither is
this file's to take, so the pair is exempted BY NAME and the exemption is
itself asserted by `test_the_only_shared_key_is_the_pair_the_design_names`, so
it cannot be widened quietly and the reader is told when it stops being needed.

**Everything else is unexempted.** A new collision fails here.
"""
import pytest

from explainer.config import SERVED_SPORTS
from explainer.template import explain_from_template

#: The pair both rows above name, as a set so the assertion is order-independent
#: -- the template emits "How it finished" first, but pinning the order would
#: make a reordering look like a new defect.
DESIGNED_SHARED_KEY = frozenset({"How it finished", "The pick"})

#: Each sport's markets, in the shape its own `/facts` builder emits.
#:
#: A literal rather than a double, because the code that produces these lives in
#: sibling repos this service does not import -- `_nba_facts` in
#: `tests/test_unserved_sport.py` and `_f1_facts` in `tests/test_f1_served.py`
#: are literals for the same reason, and `test_nbas_facts_carry_the_markets_the_
#: panel_draws` is the file that runs NBA's real builder to check the shape here
#: is still right.
#:
#: F1 carries `win` and `podium` and no line of any kind. NFL and CFB put the
#: MARKET's line in `line`; NBA puts the MODEL's in `line` and the market's in
#: `market_line`. Those differences are the subject of
#: `tests/test_template_quoted_line.py`; what matters here is that every sport
#: contributes a bundle its own row set can fire on.
MARKETS: dict[str, list[dict]] = {
    "pl": [{"market": "result", "model": {"LIV": 0.44, "ARS": 0.33, "MCI": 0.23}}],
    "nfl": [{"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
            {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
            {"market": "total", "model_total": 45.5, "line": "45.5"}],
    "cfb": [{"market": "moneyline", "model": {"ALA": 0.70, "UGA": 0.30}},
            {"market": "spread", "model_margin": 10.0, "line": "ALA -10.0"},
            {"market": "total", "model_total": 55.0, "line": "55.0"}],
    "nba": [{"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
            {"market": "spread", "model_margin": 4.2,
             "line": "BOS by 4.2", "market_line": "BOS -3.5"},
            {"market": "total", "model_total": 226.5, "market_line": "224.5"}],
    "f1": [{"market": "win", "model": {"Lando Norris": 0.34, "Max Verstappen": 0.29}},
           {"market": "podium", "model": {"Lando Norris": 0.88}}],
}

#: Every state of a bundle the template branches on and can be reached in.
#:
#: `pick_timing` decides whether the rebuilt-disclosure row is emitted -- the
#: row that collides with F1's pick -- and `status` decides whether the
#: "How it finished" row is. Both are needed: the collision the ruling is about
#: is only visible with `rebuilt`, and a matrix that left `final` out would have
#: hidden the outcome/pick pair named in the module docstring.
STATES = [
    ("pre_kickoff", "upcoming"),
    ("rebuilt", "upcoming"),
    ("pre_kickoff", "final"),
    ("rebuilt", "final"),
]


def _bundle(sport: str, timing: str, status: str) -> dict:
    return {
        "sport": sport, "id": "g1", "title": "A fixture",
        "starts_at": "2026-10-20T00:00:00Z", "status": status,
        "pick_timing": timing, "pick": {"label": "BOS", "prob": 0.62},
        "markets": MARKETS[sport], "drivers": [], "context": {}, "players": [],
        "record": {"label": "Picks made before kickoff", "hits": 30, "settled": 50},
        "result": {"score": "2-1", "pick_won": True} if status == "final" else None,
    }


def _shared_keys(factors: list[dict]) -> dict[str, list[str]]:
    """Every key more than one factor is filed under, as `{key: [headline, ...]}`."""
    seen: dict[str, list[str]] = {}
    for f in factors:
        seen.setdefault(f["key"], []).append(f["headline"])
    return {k: v for k, v in seen.items() if len(v) > 1}


@pytest.mark.parametrize("sport", SERVED_SPORTS)
@pytest.mark.parametrize("timing,status", STATES)
def test_no_two_factors_in_one_body_share_a_key(sport, timing, status):
    """The property, over every served sport and every state it can be in."""
    factors = explain_from_template(_bundle(sport, timing, status))["factors"]
    shared = _shared_keys(factors)

    # A shared key is only allowed to be the named pair, and only as exactly two
    # factors. `len(v) == 2` is checked as well as the set, so a third row
    # joining that key is not read as the exemption plus a new defect.
    unexpected = {k: v for k, v in shared.items()
                  if len(v) != 2 or frozenset(v) != DESIGNED_SHARED_KEY}
    assert not unexpected, (
        f"two factors in one {sport} body ({timing}, {status}) share a key, so the "
        f"panel renders two elements with the same `data-testid` and lights both "
        f"when either is selected: {unexpected}. All factors: {factors}. The only "
        f"pair allowed to share a key is {sorted(DESIGNED_SHARED_KEY)} -- see this "
        f"module's docstring -- and a row about a MARKET must never land on a "
        f"pseudo-market's key."
    )


@pytest.mark.parametrize("sport", SERVED_SPORTS)
def test_the_only_shared_key_is_the_pair_the_design_names(sport):
    """The exemption, audited, in both directions.

    Two claims, and either one alone would be a guard that can be silenced:

    * **No shared key other than the named pair** -- so the exemption in the test
      above cannot be widened without this failing, and there is one place to
      look.
    * **The named pair is still there** -- so the exemption cannot quietly stop
      matching, which would leave the matrix above asserting a property over a
      gap nobody is tracking any more. If the outcome/pick pair is ever split
      apart -- a third pseudo-market, or a key vocabulary that distinguishes
      them -- this test fails and says the exemption is now unnecessary rather
      than letting it rot into a silently-narrow exemption.
    """
    found: dict[str, list[list[str]]] = {}
    for timing, status in STATES:
        for key, heads in _shared_keys(
                explain_from_template(_bundle(sport, timing, status))["factors"]).items():
            found.setdefault(f"{key}:{'+'.join(sorted(heads))}", []).append(f"{timing}/{status}")

    other = {k: v for k, v in found.items()
             if frozenset(k.split(":", 1)[1].split("+")) != DESIGNED_SHARED_KEY}
    assert not other, f"{sport}: shared keys other than the designed pair: {other}"

    # Keyed rather than asserted as a literal, because the market the outcome
    # row names is the sport's own (`moneyline` for the two football sports and
    # NBA, `result` for PL), and a literal here would be a copy that goes stale
    # in the same way `_outcome_key` went stale.
    assert found, (
        f"{sport}: no key is shared at all, so the exemption in "
        f"`test_no_two_factors_in_one_body_share_a_key` is no longer "
        f"load-bearing. Delete DESIGNED_SHARED_KEY and the exemption, and say in "
        f"this module's docstring which change made the outcome and the pick "
        f"distinct."
    )
