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
-- two `factor-context` testids on a rebuilt session. And the fall-through is
NOT confined to a new sport: every served sport's builder can emit a bundle with
no `result`/`moneyline`/`win` market at all, which is what `THIN` below renders.

**A new sport needs an entry here, and this file will tell you which.** An
earlier version of this docstring said "a sport added tomorrow is covered by this
file with no edit", and that was false in the direction that matters least but
still mattered: `SERVED_SPORTS` is derived from `config`, so a sixth sport would
be parametrised in, and then `MARKETS[sport]` would raise `KeyError: 'nhl'` five
times over. Loud, red, and the safe direction -- but the message said a dict
lookup failed, not what to do about it. So `_check_markets_cover_every_served_
sport` now fails first, and names the sport, the keys `MARKETS` does have, and
the `test_factor_keys.py` entry it needs. It is a `MARKETS` edit, not no edit,
and saying so was the whole of the correction.

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

**Which test carries which weight, for the states the exemption does not reach.**
The exemption is a `DESIGNED_SHARED_KEY` comparison, so it tolerates that pair
sharing a key and nothing else -- but before the `pick`/`outcome` fallbacks it
would have tolerated a THIN finished F1 bundle whose pick and outcome rows both
fell through to `context`, because that pair's two headlines are exactly the
exempted two. The matrix test does not catch that; the matrix says only "these
two rows may share a key", never "these two rows may share a key with each other
BY ACCIDENT". `test_f1s_pick_row_is_keyed_win_not_the_context_pseudo_market` in
`tests/test_f1_served.py` is what caught it, by naming F1's pick row's key
rather than counting keys. **Everything else is unexempted:** a new collision on
any other key, for any served sport, in any state, fails here.
"""
import pytest

from explainer.config import SERVED_SPORTS
from explainer.contract import resolve_factors
from explainer.template import explain_from_template

#: The pair both rows above name, as a set so the assertion is order-independent
#: -- the template emits "How it finished" first, but pinning the order would
#: make a reordering look like a new defect.
DESIGNED_SHARED_KEY = frozenset({"How it finished", "The pick"})

#: The three market names `_outcome_key` recognises, which is why they are the
#: three a THIN bundle drops. Kept beside `MARKETS` and not inside it, because
#: the thinning is a property of the *recognised* set, not of any one sport.
RECOGNISED_MARKETS = ("result", "moneyline", "win")

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
#: row that collided with F1's pick -- and `status` decides whether the "How it
#: finished" row is. Both are needed: the collision the ruling is about is only
#: visible with `rebuilt`, and a matrix that left `final` out would have hidden
#: the outcome/pick pair named in the module docstring.
STATES = [
    ("pre_kickoff", "upcoming"),
    ("rebuilt", "upcoming"),
    ("pre_kickoff", "final"),
    ("rebuilt", "final"),
]

#: `thin` is the other half: the bundle carries no recognised pick market.
#:
#: **Reachable on every served sport, measured on each builder at its
#: `origin/main`, and each by a branch that can return without the market. ALL
#: FIVE also carry a `markets: [] if (started and ...)` arm that returns an
#: empty list outright** -- F1 `:537`, NBA `:362`, NFL `:472`, CFB `:437`,
#: PL `:400`:
#:
#: | sport | file:line | the branch |
#: |---|---|---|
#: | f1  | `src/f1_predictor/api/facts.py:313-314` | `if win:` guards the `win` append, so a prediction with no driver `win` and no stored one yields `podium`/`points`/`dnf` only |
#: | f1  | `src/f1_predictor/api/facts.py:295-296, 537` | `[] if (started and not stored)`, and `_markets`' own `if prediction is None and not stored: return []` |
#: | nba | `src/nba_predictor/api/facts.py:209` | `if home_prob is not None:` guards the `moneyline` append; the `total` at :229 is gated only on `total`, so a `total`-only bundle is reachable |
#: | nba | `src/nba_predictor/api/facts.py:205-206, 362` | `if prediction is None: return out`, and `[] if (started and chosen is None)` |
#: | nfl | `src/nfl_predictor/api/facts.py:258-260` | `if home_prob is not None and away_prob is not None:` guards `moneyline`, and `home_prob` is read off `moneyline_from or prediction` (:257) -- a DIFFERENT row from the one the spread (:290) and total (:296) are gated on |
#: | cfb | `src/cfb_predictor/api/facts.py:264-266` | the same shape as NFL |
#: | pl  | `src/pl_predictor/api/facts.py:178` | `if probs is not None:` guards `result`; `total_goals` (:203) and `btts` (:212) are not gated on it |
#: | pl  | `src/pl_predictor/api/facts.py:400` | `[] if (started and card is None)` |
#:
#: So this is not a hypothetical bundle, and the `context` fall-through is live
#: on all five. `THIN` is a DERIVATION rather than a second set of literals --
#: it drops whichever entry `MARKETS` holds for a recognised name -- so a new
#: sport gets a thin bundle for free, and cannot be added here with no thin
#: coverage.
THIN = [False, True]


def _thin_markets(sport: str) -> list[dict]:
    """This sport's markets with the one `_outcome_key` would recognise removed."""
    kept = [m for m in MARKETS[sport] if m["market"] not in RECOGNISED_MARKETS]
    assert kept != MARKETS[sport], (
        f"the {sport} bundle has no market for _outcome_key to fall through "
        f"past, so the thin case would be the same bundle: {MARKETS[sport]}"
    )
    return kept


def _bundle(sport: str, timing: str, status: str, thin: bool = False) -> dict:
    return {
        "sport": sport, "id": "g1", "title": "A fixture",
        "starts_at": "2026-10-20T00:00:00Z", "status": status,
        "pick_timing": timing, "pick": {"label": "BOS", "prob": 0.62},
        "markets": _thin_markets(sport) if thin else MARKETS[sport],
        "drivers": [], "context": {}, "players": [],
        "record": {"label": "Picks made before kickoff", "hits": 30, "settled": 50},
        "result": {"score": "2-1", "pick_won": True} if status == "final" else None,
    }


def _shared_keys(factors: list[dict]) -> dict[str, list[str]]:
    """Every key more than one factor is filed under, as `{key: [headline, ...]}`."""
    seen: dict[str, list[str]] = {}
    for f in factors:
        seen.setdefault(f["key"], []).append(f["headline"])
    return {k: v for k, v in seen.items() if len(v) > 1}


def test_markets_cover_every_served_sport():
    """`MARKETS` is a literal, so a new served sport has to be added to it.

    Without this the six `MARKETS[sport]` lookups below raise
    `KeyError: 'nhl'` and the failure names a dict subscript rather than the
    thing to do about it. Five identical tracebacks is not a guard; this is one
    message that says which sport is missing and which file needs the entry.
    """
    missing = [s for s in SERVED_SPORTS if s not in MARKETS]
    assert not missing, (
        f"{missing} serve, so they are parametrised into every test in this file, "
        f"but `MARKETS` has no entry for them. Add one to `MARKETS` in "
        f"tests/test_factor_keys.py, in the shape that sport's own `/facts` "
        f"builder emits -- it must include a market from {RECOGNISED_MARKETS} for "
        f"_thin_markets to have something to drop. `MARKETS` currently covers "
        f"{sorted(MARKETS)}."
    )


@pytest.mark.parametrize("sport", SERVED_SPORTS)
@pytest.mark.parametrize("timing,status", STATES)
@pytest.mark.parametrize("thin", THIN)
def test_no_two_factors_in_one_body_share_a_key(sport, timing, status, thin):
    """The property, over every served sport and every state it can be in."""
    factors = explain_from_template(_bundle(sport, timing, status, thin))["factors"]
    shared = _shared_keys(factors)

    # A shared key is only allowed to be the named pair, and only as exactly two
    # factors. `len(v) == 2` is checked as well as the set, so a third row
    # joining that key is not read as the exemption plus a new defect.
    unexpected = {k: v for k, v in shared.items()
                  if len(v) != 2 or frozenset(v) != DESIGNED_SHARED_KEY}
    assert not unexpected, (
        f"two factors in one {sport} body ({timing}, {status}, thin={thin}) share "
        f"a key, so the panel renders two elements with the same `data-testid` and "
        f"lights both when either is selected: {unexpected}. All factors: {factors}. "
        f"The only pair allowed to share a key is {sorted(DESIGNED_SHARED_KEY)} -- "
        f"see this module's docstring -- and a row about a MARKET must never land "
        f"on a pseudo-market's key. A thin bundle is reachable on every served "
        f"sport; see the THIN table."
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

    Sweeps the `thin` bundles too, and that is not decoration: the exemption is
    a comparison on the two HEADLINES, so it cannot see that those two rows
    arrived at their key by accident. Before the `pick`/`outcome` fallbacks a
    thin finished bundle put both of them on `context` and this test passed
    happily -- the matrix above passed too, which is what the module docstring
    says about the division of labour.
    """
    found: dict[str, list[list[str]]] = {}
    for thin in THIN:
        for timing, status in STATES:
            for key, heads in _shared_keys(
                    explain_from_template(_bundle(sport, timing, status, thin))
                    ["factors"]).items():
                found.setdefault(f"{key}:{'+'.join(sorted(heads))}", []).append(
                    f"{timing}/{status}/thin={thin}")

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


@pytest.mark.parametrize("sport", SERVED_SPORTS)
def test_a_thin_bundle_names_the_rows_it_cannot_place(sport):
    """What the fall-through key is, for a bundle with no recognised market.

    `_outcome_key` cannot name a market the bundle does not carry, and the two
    callers say who they are rather than both taking a shared default -- so a
    thin bundle produces `pick` and `outcome` as two distinct pseudo-markets and
    neither lands on `context`, which belongs to the padding and disclosure
    rows.

    **This is the assertion the docstring's "a row about a MARKET must never
    land on a pseudo-market's key" needed and did not have.** Asserted per ROW
    and by headline, so a row that moves to the wrong key is named rather than
    counted: the previous shape of this check, a membership test over a key
    list, is the one Important 2 was about.

    `pick` and `outcome` are pseudo-markets in `contract.PSEUDO_MARKETS`, and
    `test_template_v2.py` requires every factor the template emits to survive
    `contract.resolve_factors` -- which is what makes them usable as keys at all.
    """
    factors = explain_from_template(_bundle(sport, "pre_kickoff", "final", thin=True))["factors"]
    by_head = {f["headline"]: f["key"] for f in factors}

    assert "The pick" in by_head, f"{sport}: a thin bundle with a pick has no pick row: {factors}"
    assert "How it finished" in by_head, f"{sport}: a finished thin bundle has no outcome row: {factors}"
    assert by_head["The pick"] == "pick", (
        f"{sport}: the pick row of a thin bundle is keyed "
        f"{by_head['The pick']!r}, not 'pick'. The key says there is a pick and no "
        f"market to name it by; 'context' is the padding and disclosure row's key, "
        f"and a row landing there renders a second `factor-context` and lights both"
    )
    assert by_head["How it finished"] == "outcome", (
        f"{sport}: the outcome row of a thin bundle is keyed "
        f"{by_head['How it finished']!r}, not 'outcome', and must differ from the "
        f"pick row's rather than share one key"
    )


@pytest.mark.parametrize("sport", SERVED_SPORTS)
def test_every_key_this_file_sees_survives_resolution(sport):
    """A key the facts do not carry is DROPPED, not rendered -- so the two new
    names have to be in the vocabulary, and nothing else in the suite would say
    so.

    `contract.resolve_factors` keeps a factor only if its key is in
    `market_keys(facts) | PSEUDO_MARKETS`. `pick` and `outcome` are only in
    `PSEUDO_MARKETS`, so a name removed from that tuple does not raise: the
    template emits the row, the resolver throws it away, and the reader sees a
    shorter explanation. `tests/test_template_v2.py` looks like the guard for
    this -- it requires every factor to survive resolution -- but it renders a
    FULL bundle, where `_outcome_key` never falls through, so `pick` and
    `outcome` are never emitted and the assertion is never asked about them.
    Verified, not assumed: dropping `"pick"` from `PSEUDO_MARKETS` fails only
    `test_contract.py::test_the_vocabularies_are_closed`, which is a literal
    pin on the tuple, and nothing else in the suite.

    So this is the behavioural half of that pin, over the bundles that actually
    reach the fall-through. The literal is still worth having -- it is where a
    new name is decided -- but a pin cannot notice a row that vanished.
    """
    for thin in THIN:
        for timing, status in STATES:
            facts = _bundle(sport, timing, status, thin)
            out = explain_from_template(facts)
            keys = [f["key"] for f in out["factors"]]
            kept = resolve_factors(out, facts)
            assert len(kept) == len(out["factors"]), (
                f"{sport} ({timing}, {status}, thin={thin}): the template emitted "
                f"{keys} and resolution kept {[f['key'] for f in kept]}. A key that "
                f"does not resolve renders NOTHING (spec 6), so the dropped row is "
                f"a row the reader simply does not see. `pick` and `outcome` "
                f"resolve only as pseudo-markets, so a name missing from "
                f"contract.PSEUDO_MARKETS loses the row silently."
            )


def test_a_full_bundle_still_names_the_market_so_nothing_moves():
    """The fall-through must not become the common case.

    The `default` argument is a safety net for a bundle that cannot name its
    market. If a sport's builder ever taught `_outcome_key` a name and this
    stopped holding, every row on that sport would become a pseudo-market that
    highlights nothing, and the fix would have quietly replaced one live defect
    with a silent one. Asserted over the full bundles, which is the state a
    normal game is in.
    """
    for sport in SERVED_SPORTS:
        keys = {f["headline"]: f["key"]
                for f in explain_from_template(_bundle(sport, "pre_kickoff", "final"))["factors"]}
        named = {"The pick", "How it finished"} & keys.keys()
        assert named, f"{sport}: the full bundle rendered neither row: {keys}"
        for head in named:
            assert keys[head] in RECOGNISED_MARKETS, (
                f"{sport}: the full bundle has a market _outcome_key recognises, so "
                f"{head!r} is keyed {keys[head]!r} and has fallen through to the "
                f"pseudo-market that is only for bundles that cannot name one"
            )
