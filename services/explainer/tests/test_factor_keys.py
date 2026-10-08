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

**Coverage status, since a literal is only as good as what checks it: all five
sports are now cross-checked against their own builders**, by executing the
builders' real `_markets` cut out of the sibling's `origin/main` — see the
section at the foot of this file. There is no sport here that is literal-only,
so there is no unchecked literal whose staleness nobody is tracking.

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
import os
import pathlib
import re
import subprocess

import pytest

from explainer.config import SERVED_SPORTS
from explainer.contract import resolve_factors, slot_for
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
#: are literals for the same reason.
#:
#: F1 carries `win` and `podium` and no line of any kind. NFL and CFB put the
#: MARKET's line in `line`; NBA puts the MODEL's in `line` and the market's in
#: `market_line`. Those differences are the subject of
#: `tests/test_template_quoted_line.py`; what matters here is that every sport
#: contributes a bundle its own row set can fire on.
#:
#: **And all five are CHECKED against those builders**, by running them — see the
#: section at the foot of this file. The first version of this dict was
#: hand-written and four of its five entries were WRONG, which is what the
#: cross-checks are for and the reason this paragraph is a report rather than a
#: promise: PL's `model` is keyed `home_win`/`draw`/`away_win` and not by team
#: name; NFL's and CFB's total `line` is the number the game row carried, not a
#: string; NBA's away team is whatever the game row said, and its total
#: `market_line` is `'Over 224.5'` because `_line_from_market` words a total that
#: way. Each was a literal describing a bundle no builder produces, and every
#: test above this one was green on it.
#:
#: **What would still make a literal go stale, and the honest limit of the check
#: at the foot of the file.** It runs each builder's `_markets` with ONE chosen
#: input per sport, and asserts the result EQUALS this dict. So it catches a
#: changed name, a changed field, a changed value, and a moved or removed pick-
#: market guard. It does NOT catch: a guard that depends on data the runner does
#: not supply (a market that only appears for a live fixture, say), which would
#: make this dict a SUBSET of what the builder can emit; and a change in a helper
#: the runner does not cut, which is invisible for the same reason. The
#: thin-bundle half of the check is what covers the guard, and the value half is
#: what makes a subset a failure rather than a pass — but a sport that grew a
#: new conditional market would need this dict extended and the runner's input
#: widened, and nothing here would have told us in advance. That is the residual
#: and it is stated rather than hidden.
MARKETS: dict[str, list[dict]] = {
    "pl": [{"market": "result", "model": {"home_win": 0.44, "draw": 0.33, "away_win": 0.23}}],
    "nfl": [{"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
            {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
            {"market": "total", "model_total": 45.5, "line": 45.5}],
    "cfb": [{"market": "moneyline", "model": {"ALA": 0.70, "UGA": 0.30}},
            {"market": "spread", "model_margin": 10.0, "line": "ALA -10.0"},
            {"market": "total", "model_total": 55.0, "line": 55.0}],
    "nba": [{"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
            {"market": "spread", "model_margin": 4.2,
             "line": "BOS by 4.2", "market_line": "BOS -3.5"},
            {"market": "total", "model_total": 226.5, "market_line": "Over 224.5"}],
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


# --- the literals above, checked against the real builders --------------------
#
# **Why this section exists, and what it closes.** `MARKETS` is a literal, and
# everything in this file rests on it: the template's gates read the field names
# it carries, and `THIN` below drops the entry whose market name is recognised.
# So a builder edit -- NFL deciding to emit `over_prob` unconditionally, PL
# renaming a field, F1 guarding `win` differently -- would leave the literal
# describing a bundle that can no longer occur, and **nothing would fail.** The
# whole file would keep passing while testing a shape nothing produces. That is
# the defect class this task exists to eliminate, and it is the same class as the
# two findings in round 2, one level down.
#
# **How it is closed: by RUNNING each builder, not by grepping it.** The pattern
# is `_run_nba_markets` in `tests/test_unserved_sport.py` -- cut the real
# functions out of the sibling's `facts.py` at `origin/main`, `exec` them in an
# empty namespace with only the *boundary* stubbed, and call the real `_markets`.
# A regex over the source would be answered by a docstring or a comment; a
# function that is run cannot be.
#
# **What is stubbed is always the BOUNDARY, never the decision.** The storage
# read and the tip-off filter, in NBA's case; nothing else. `_markets`,
# `_spread_line`, `_driver_rows`, `_num` and the guards between them are the
# sibling's own code, so a change to a guard is a change to what this file
# observes. A stub of `_market_line` -- the function that decides what a
# `market_line` holds -- is what the NBA comment records as the earlier
# mistake, and it is not repeated here.
#
# **Each check asserts TWO things, and the second is the one round 2 needs.**
# 1. The derived markets EQUAL `MARKETS[sport]` -- names, fields and values, not
#    a subset. Equality is affordable because each runner's input is chosen to
#    reproduce the literal exactly, and it is what makes a builder edit visible.
#    A subset check would tolerate the literal naming a market the builder no
#    longer emits, which is the shape of mistake round 1's finding 2 was about.
# 2. The builder really can emit a bundle with NO recognised market -- the
#    `THIN` derivation above is only honest if the pick market is *guarded*. An
#    equality check alone would keep passing if a builder stopped guarding and
#    every bundle grew a moneyline, because the chosen input still has one.
#
# **No network, and no sibling on disk.** Every source comes from
# `git show origin/main:<path>`, so the check is against what SHIPS rather than
# against whatever is in a working tree, and it reads nothing from the sibling
# beyond that text. `pandas` is a dev-only dependency of THIS service, added so
# NFL's and CFB's real `_num` can run unmodified -- see `test_pandas_is_here_
# because_nfl_and_cfb_need_it`, which fails rather than skipping if it goes.


def _sibling_repo(sport: str) -> pathlib.Path:
    """The sibling checkout for `sport`, found the way the NBA check finds it.

    `tests/` is `<service>/tests`, so `parents[3]` is the worktree and
    `parents[4]` is where the sibling repos live. An env var per sport comes
    first, matching `NBA_REPO` in `tests/test_unserved_sport.py`, so a CI runner
    can point at a checkout without a sibling beside the repo.
    """
    env = f"{sport.upper()}_REPO"
    here = pathlib.Path(__file__).resolve()
    candidates = [pathlib.Path(os.environ[env])] if os.environ.get(env) else []
    candidates += [p / f"{sport.upper()}_Predictor" for p in here.parents]
    root = next((c for c in candidates if (c / ".git").exists()), None)
    assert root is not None, (
        f"{sport.upper()}_Predictor not found beside this repo, so the claim that "
        f"{sport}'s facts carry the markets `MARKETS` describes is UNVERIFIED rather "
        f"than true -- and an unverified literal is the thing this section exists to "
        f"prevent. Set {env}. Looked in {[str(c) for c in candidates[:4]]}"
    )
    return root


def _facts_source(sport: str) -> str:
    """`src/<sport>_predictor/api/facts.py` from the sibling's `origin/main`.

    Not a bare re-raise on failure, for the reason `tests/test_unserved_sport.py`
    gives: `origin/main` is absent in a fork and when git is not installed, and
    the default `CalledProcessError` prints a command line and an exit status
    rather than saying the CLAIM is unchecked. This test exists to keep the
    literals honest, so when it cannot check one it has to say so.
    """
    rel = f"src/{sport}_predictor/api/facts.py"
    root = _sibling_repo(sport)
    try:
        src = subprocess.run(["git", "-C", str(root), "show", f"origin/main:{rel}"],
                             capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.fail(
            f"could not read {sport}'s facts.py from {root} (origin/main:{rel}), so "
            f"MARKETS[{sport!r}] is UNVERIFIED rather than true. Underlying error: {exc}"
        )
    assert src.strip(), f"{sport}'s facts.py came back empty; the check would pass vacuously"
    return src


def _by_market(out: list) -> dict[str, dict]:
    return {str(m.get("market")): m for m in out if isinstance(m, dict)}


def _assert_matches_literal(sport: str, derived: list, what: str) -> dict:
    """The derived markets must EQUAL `MARKETS[sport]`, and the message must say how.

    Equality on names, fields AND values. A subset check is the obvious cheaper
    version and it is the one round 1's finding 2 was about: it tolerates the
    literal carrying a market the builder no longer emits, which is precisely the
    way a literal goes stale.

    The message names the sport, the branch, the derived set and the literal, and
    the keys that differ -- a builder's output is a dict of dicts and a bare
    `AssertionError` on a two-hundred-character diff tells a reader nothing about
    which side moved.
    """
    got, want = _by_market(derived), {str(m["market"]): m for m in MARKETS[sport]}
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    differing = sorted(k for k in set(want) & set(got) if got[k] != want[k])
    assert not (missing or extra or differing), (
        f"{sport}: MARKETS[{sport!r}] no longer matches what {sport}'s OWN builder "
        f"emits ({what}).\n"
        f"  the builder emits : {got}\n"
        f"  MARKETS declares  : {want}\n"
        f"  only in MARKETS   : {missing}\n"
        f"  only in the builder: {extra}\n"
        f"  same name, different content: {differing}\n"
        f"  Either the sibling's facts.py changed, or this literal is wrong. It is "
        f"not safe to leave it as it is: every test in this file builds its bundle "
        f"from it, so a literal that no longer occurs is a file testing a shape "
        f"nothing produces. Fix `MARKETS[{sport!r}]` to what the builder emits, or "
        f"change the builder deliberately -- and if the builder changed on purpose, "
        f"re-read whether `RECOGNISED_MARKETS`, `THIN` and the template's gates "
        f"still agree with it."
    )
    return got


def _assert_can_be_thin(sport: str, derived: list, what: str) -> None:
    """The builder must be able to emit a bundle with no recognised market.

    This is the half that keeps the `THIN` derivation honest. `_outcome_key`'s
    `default` argument, `THIN` and the whole "the fall-through is reachable"
    claim rest on the pick market being GUARDED -- emitted only when a figure is
    there. An equality check cannot see that: the input it drives has every
    figure, so a builder that stopped guarding and emitted a moneyline for
    everything would still match the literal, and the thin bundle this file
    renders would be unreachable in production.

    So the guard is probed directly, and the "still has other markets" half is
    asserted too: a builder that returned `[]` for everything would satisfy
    "no recognised market" while making the thin bundle vacuous in the other
    direction.
    """
    got = _by_market(derived)
    recognised = sorted(set(got) & set(RECOGNISED_MARKETS))
    assert not recognised, (
        f"{sport}: the input chosen to be a THIN bundle still produced "
        f"{recognised} ({what}), so this sport's builder does NOT guard its pick "
        f"market the way `THIN` assumes. Either the guard moved, or it was removed "
        f"-- and if it was removed then `RECOGNISED_MARKETS`, `THIN`, the "
        f"`_outcome_key` `default` argument and every test built on a thin bundle "
        f"are describing a state this sport can no longer reach."
    )
    assert got, (
        f"{sport}: the THIN input produced NO markets at all ({what}), so 'no "
        f"recognised market' holds for the wrong reason -- the bundle is empty "
        f"rather than thin, and the template's padding rows would take the place of "
        f"the rows this file is checking."
    )


#: The preamble every runner execs ahead of the cut functions: postponed
#: annotations so the sibling's `dict | None` hints need nothing, and `Any`,
#: which the sibling's own signatures name.
#:
#: **And `pandas` for NFL and CFB, which is the one third-party import here.**
#: Their `_num` ends `return None if pd.isna(number) else number`, and a service
#: with no pandas in it cannot run that unmodified. The alternative was a
#: hand-written stand-in for `pd.isna`, and a stand-in is a re-implementation
#: wearing the builder's name: if NFL ever changed that call, the stand-in would
#: keep answering the old question and the check would stay green. So pandas is a
#: **dev-only** dependency of this service -- the runtime `dependencies` list is
#: untouched -- and the real function runs against the real library.
_PREAMBLE = "from __future__ import annotations\nfrom typing import Any\n"
_PANDAS_PREAMBLE = _PREAMBLE + "import pandas as pd\n"


def _run_f1_markets(source: str, with_win: bool = True) -> list:
    """F1's real `_markets`, run, over a real `_driver_rows` and a real `_num`.

    Nothing is stubbed: all three of F1's helpers are pure functions over
    arguments, so there is no boundary to replace. `_driver_rows` is the one that
    matters -- it is what normalises the API's `p_win`/`p_podium` payload into
    the `win`/`podium` keys `_markets` then reads, and getting it wrong is a real
    way for a real F1 bundle to carry no markets at all.

    `with_win=False` is the thin probe: the payload carries `p_podium` but not
    `p_win`, which is exactly the `if win:` guard at `facts.py:313-314` refusing
    to append the market. `points` and `dnf` are left out of the payload too, so
    the derived set is `podium` alone and matches `MARKETS["f1"]` minus `win`.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"F1's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    env: dict = {}
    exec(compile(_PREAMBLE + "".join(cut(n) for n in ("_num", "_driver_rows", "_markets")),
                 "<f1 markets>", "exec"), env)

    # Two drivers and a `names` map, because F1's `_markets` keys its `model` map
    # by whatever `names` resolves a driver id to. The first version of this
    # runner passed `names={}` and produced `{'1': 0.34}`, which the equality
    # check rejected for a real reason: a real F1 bundle is keyed by driver NAME,
    # and a literal keyed by id would be one more bundle no builder produces.
    # `p_podium` is on the first driver only, which is why the two markets carry
    # different key sets.
    names = {"1": "Lando Norris", "2": "Max Verstappen"}
    norris = {"driver_id": "1", "name": "Lando Norris", "p_podium": 0.88}
    verstappen = {"driver_id": "2", "name": "Max Verstappen"}
    if with_win:
        norris["p_win"] = 0.34
        verstappen["p_win"] = 0.29
    return env["_markets"]({"predictions": [norris, verstappen]}, {}, names)


def _run_nfl_markets(source: str, with_moneyline: bool = True) -> list:
    """NFL's real `_markets`, over its real `_num` and its real `_spread_line`.

    The only stub is `_market_rows`-shaped and it is not needed here: NFL reads
    the quoted line off the `game` dict it is handed, not out of storage, so
    there is no boundary call to replace. What the runner must not lose is
    `moneyline_from` -- the whole point of NFL's signature is that the moneyline
    comes from a DIFFERENT row than the spread and total (its own docstring
    says so, and round 2's thin finding depends on it), so the runner drives it
    the way `facts.py:472` does and the derived set is a real NFL bundle.

    `with_moneyline=False` is the thin probe, and it drops the *moneyline*
    source's probabilities while leaving the spread and total alone -- which is
    the reachable state `facts.py:258-260` produces when the pre-kickoff
    snapshot has no `home_win_prob`.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"NFL's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    env: dict = {}
    exec(compile(_PANDAS_PREAMBLE + "".join(cut(n) for n in ("_num", "_spread_line", "_markets")),
                 "<nfl markets>", "exec"), env)

    game = {"home_team": "BAL", "away_team": "KC", "spread_line": 2.5, "total_line": 45.5}
    prediction = {"predicted_margin": 3.4, "predicted_total": 45.5}
    moneyline_from: dict = {"home_win_prob": 0.62, "away_win_prob": 0.38}
    if not with_moneyline:
        moneyline_from = {}
    return env["_markets"](game, prediction, moneyline_from=moneyline_from)


def _run_cfb_markets(source: str, with_moneyline: bool = True) -> list:
    """CFB's real `_markets`, over its real `_num` and its real `_spread_line`.

    Identical in shape to NFL's and deliberately not shared with it: the two
    builders are separate files with separate `_num`s, and the check has to fail
    naming the sport whose function went missing. Sharing the runner would mean
    a single missing `_spread_line` fails one sport's check with the other's
    name on it, which is a worse failure than the duplication.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"CFB's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    env: dict = {}
    exec(compile(_PANDAS_PREAMBLE + "".join(cut(n) for n in ("_num", "_spread_line", "_markets")),
                 "<cfb markets>", "exec"), env)

    game = {"home_team": "ALA", "away_team": "UGA", "spread_line": 10.0, "total_line": 55.0}
    prediction = {"predicted_margin": 10.0, "predicted_total": 55.0}
    moneyline_from: dict = {"home_win_prob": 0.70, "away_win_prob": 0.30}
    if not with_moneyline:
        moneyline_from = {}
    return env["_markets"](game, prediction, moneyline_from=moneyline_from)


def _run_pl_markets(source: str, with_probs: bool = True) -> list:
    """PL's real `_markets`, over PL's real `_field`/`_implied`/`_edge`/`_prob_field`.

    All of PL's helpers are pure functions over the `detail` it is handed -- the
    module docstring records that `_field` exists precisely so a pydantic
    `FixtureDetail` and an old cached dict both work -- so nothing is stubbed and
    the runner passes a plain dict, which is one of the two shapes `_field`
    supports.

    The `detail` is deliberately bare: no `has_live_odds`, no
    `predicted_total_goals`, no `btts_yes_prob`. That is not a convenience, it
    is what makes the derived set equal `MARKETS["pl"]`, which holds the
    `result` market alone -- and it is also the state round 2 measured, since
    `_prob_field` returns `None` for absent keys and the total and btts rows are
    guarded on exactly that.

    `with_probs=False` is the thin probe: `facts.py:178`'s `if probs is not None:`
    is the guard, and this is what it does when `probs` is `None`. **The detail
    changes with it**, because a bare `{}` with no `probs` emits NOTHING -- which
    satisfies "no recognised market" for the wrong reason, and
    `_assert_can_be_thin` rejects exactly that. So the thin input keeps a
    `btts_yes_prob` and therefore keeps the `btts` market, and what is missing is
    the `result` and only the `result`.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"PL's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    env: dict = {}
    exec(compile(_PREAMBLE + "".join(cut(n) for n in (
        "_num", "_field", "_implied", "_edge", "_prob_field", "_markets")),
        "<pl markets>", "exec"), env)

    probs = (0.44, 0.33, 0.23)
    detail: dict = {}
    if not with_probs:
        probs, detail = None, {"btts_yes_prob": 0.55}
    return env["_markets"](detail, probs, "LIV", "ARS")


def _run_nba_markets(source: str, with_moneyline: bool = True) -> list:
    """NBA's real `_markets`, over its real `_margin_line` and `_market_line`.

    Same shape as `_run_nba_markets` in `tests/test_unserved_sport.py`, and the
    same two stubs for the same reason: `_market_rows` is the STORAGE READ and
    `made_before_tip` is the tip-off filter, so `_market_line` and
    `_line_from_market` -- the functions that decide what a `market_line` holds,
    including the sign and the team attribution -- run for real. Stubbing
    `_market_line` is the mistake that file's comment records: it proves the key
    is present and says nothing about the value.

    Duplicated rather than imported for the same reason as CFB's: a missing
    helper must fail naming the sport it belongs to.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"NBA's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    env: dict = {}
    exec(compile(_PREAMBLE + "from typing import Any\n" + "".join(cut(n) for n in (
        "_num", "_favourite", "_margin_line", "_line_from_market", "_market_line", "_markets")),
        "<nba markets>", "exec"), env)

    env["_market_rows"] = lambda game_id: [
        {"market": "spread", "point": -3.5, "created_at": "2026-10-19T12:00:00Z",
         "selection": "BOS"},
        {"market": "totals", "point": 224.5, "created_at": "2026-10-19T12:00:00Z",
         "selection": "Over"},
    ]
    env["made_before_tip"] = lambda created_at, game: True

    game = {"game_id": "401585", "home_team": "BOS", "away_team": "MIA"}
    prediction: dict = {"predicted_margin": 4.2, "predicted_total": 226.5}
    if with_moneyline:
        prediction["home_win_prob"] = 0.62
    return env["_markets"](game, prediction)


#: sport -> its runner. A literal rather than a lookup by name so a missing
#: entry is a `KeyError` at the ONE place the tests below, not inside five
#: separately-written bodies.
RUNNERS = {
    "f1": _run_f1_markets,
    "nfl": _run_nfl_markets,
    "cfb": _run_cfb_markets,
    "nba": _run_nba_markets,
    "pl": _run_pl_markets,
}


def test_pandas_is_here_because_nfl_and_cfb_need_it():
    """The dev-only dependency, stated as a fact rather than assumed.

    NFL's and CFB's real `_num` ends `return None if pd.isna(number) else number`.
    If pandas left the dev extra, `_PANDAS_PREAMBLE`'s `import pandas` would
    raise `ModuleNotFoundError` inside `exec` -- and `exec` of a comprehension
    inside a test reports a traceback pointing at the cut, not at the missing
    dependency, on two of five cross-checks. This names it once, up front.

    Fails rather than skips, for the reason `tests/test_unserved_sport.py` gives
    for a missing sibling repo: a skipped cross-check is an UNVERIFIED literal
    reported as a pass, which is the thing this whole section exists to prevent.
    """
    pytest.importorskip.__doc__  # keep the import honest if the name moves
    try:
        import pandas  # noqa: F401
    except ModuleNotFoundError:
        pytest.fail(
            "pandas is gone, and NFL's and CFB's real `_num` calls `pd.isna`. It is "
            "a DEV-only dependency of this service, added so those two builders can "
            "run unmodified rather than behind a hand-written stand-in for "
            "`pd.isna`. Restore it in `[project.optional-dependencies] dev` in "
            "services/explainer/pyproject.toml. Skipping is not an option: an "
            "unverified `MARKETS` literal is the defect this section closes."
        )


@pytest.mark.parametrize("sport", sorted(RUNNERS))
def test_the_literal_matches_what_the_builder_emits(sport):
    """`MARKETS[sport]` must EQUAL what the sport's own builder emits.

    The whole file builds its bundles from these literals, so a literal that no
    longer matches its builder is a file testing a shape nothing produces -- and
    the tests here would keep passing while doing it. The runner EXECUTES the
    sibling's `_markets`; it does not re-implement it, and it does not grep for
    the market names, which a docstring could satisfy.
    """
    derived = RUNNERS[sport](_facts_source(sport))
    _assert_matches_literal(sport, derived, "the full bundle this file builds")


@pytest.mark.parametrize("sport", sorted(RUNNERS))
def test_the_builder_can_still_emit_a_bundle_with_no_recognised_market(sport):
    """The `THIN` derivation, checked against the guard it depends on.

    Round 2's finding was that the fall-through is REACHABLE, measured on these
    builders, and the whole `default` argument rests on it. A builder that
    stopped guarding its pick market would make every bundle carry one, and then
    the literal and this file would both be describing a state no fixture is in
    -- with nothing failing, because the full-bundle input the equality check
    drives has every figure either way.

    So the guard is probed directly, one sport at a time, on the real code.
    """
    derived = RUNNERS[sport](_facts_source(sport), **{"with_win": False}
                             if sport == "f1" else
                             {"with_moneyline": False} if sport in ("nfl", "cfb", "nba")
                             else {"with_probs": False})
    _assert_can_be_thin(sport, derived, "the input that omits only this sport's pick-market figure")


@pytest.mark.parametrize("sport", sorted(RUNNERS))
def test_the_runner_notices_when_the_builder_emits_something_else(sport):
    """The check's own sensitivity, measured -- a guard that cannot fail is a
    control, not a test.

    The runner is handed a source whose `_markets` has been replaced by one that
    emits a single market called `basketball`. The check must reject it, naming
    the sport. Without this, "the equality check passed" would be evidence about
    nothing: the same code path returns happily for any bundle, and a cut that
    silently matched the wrong function -- or an empty `env` that made
    `_markets` a stub of my own making -- would look identical to a real pass.

    The source is rewritten IN MEMORY. The sibling repository on disk is not
    modified, read for anything but committed `origin/main` text, or checked out.
    """
    source = _facts_source(sport)
    decoy = re.sub(r"^def _markets\(.*?(?=^def |\Z)",
                   "def _markets(*a, **k):\n    return [{\"market\": \"basketball\", \"x\": 1}]\n\n",
                   source, count=1, flags=re.S | re.M)
    assert decoy != source, f"{sport}: the decoy substitution did not apply"
    try:
        _assert_matches_literal(sport, RUNNERS[sport](decoy), "a decoy that emits basketball")
    except AssertionError as exc:
        assert sport in str(exc), f"{sport}: the failure does not name the sport: {exc}"
        assert "basketball" in str(exc), f"{sport}: the failure does not name the difference: {exc}"
    else:
        pytest.fail(
            f"{sport}: the cross-check ACCEPTED a builder that emits a single market "
            f"called 'basketball'. The runner is not running the sibling's code, or "
            f"the comparison is not looking at what the builder returned -- and "
            f"either way the five checks above are evidence about nothing."
        )


# --- matchup keys and the Edge / Risk / Price slots (AI plan Task 4) ---------
#
# A `matchup:<id>` factor names a code-computed duel in `context.matchups` rather
# than a market, and its SLOT is not a re-reading of the model's `direction`: a
# duel is Edge only when the code says it favours the pick, and Risk only when the
# code says it favours the other side. The model chooses the words and the
# ordering; which side a duel points at is computed, and a duel that failed the
# lift gate carries `toward_pick: None` and is never Edge or Risk at all.
FACTS = {"markets": [{"market": "spread"}], "context": {"matchups": [{"id": "pass_off_vs_pass_def:home"}]}}


def test_a_matchup_key_that_the_facts_carry_is_kept():
    v = {"factors": [{"key": "matchup:pass_off_vs_pass_def:home", "direction": "up", "headline": "h", "text": "t"}]}
    assert [f["key"] for f in resolve_factors(v, FACTS)] == ["matchup:pass_off_vs_pass_def:home"]


def test_a_matchup_key_the_facts_do_not_carry_is_dropped():
    v = {"factors": [{"key": "matchup:invented", "direction": "up", "headline": "h", "text": "t"}]}
    assert resolve_factors(v, FACTS) == []


def _facts(toward):
    return {"markets": [{"market": "spread"}], "context": {"matchups": [{"id": "x", "toward_pick": toward}]}}


def test_slots_follow_direction_and_market():
    assert slot_for("up", "matchup:x", _facts(True)) == "edge"
    assert slot_for("down", "matchup:x", _facts(False)) == "risk"
    assert slot_for("neutral", "spread", FACTS) == "price"
    assert slot_for("neutral", "record", FACTS) == "context"


def test_the_model_cannot_promote_a_matchup_the_code_did_not_direct():
    # code says null (failed the lift gate) or the other side: whatever direction the model wrote, the row is context
    assert slot_for("up", "matchup:x", _facts(None)) == "context"
    assert slot_for("down", "matchup:x", _facts(None)) == "context"
    assert slot_for("up", "matchup:x", _facts(False)) == "context"
    assert slot_for("down", "matchup:x", _facts(True)) == "context"


def test_resolved_factors_carry_their_slot():
    v = {"factors": [{"key": "spread", "direction": "neutral", "headline": "h", "text": "t"}]}
    assert resolve_factors(v, FACTS)[0]["slot"] == "price"
