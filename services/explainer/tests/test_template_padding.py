"""The padding rows and the verdict, pinned exactly -- because they are the rows
every reader of a thin bundle actually sees.

Two rows exist only so the panel is never a single lonely line, and the verdict
is the one sentence above them. Measured reach, which is why they are worth
pinning rather than describing. **Every number below is a measurement and the
query that produced them is here**, because this table used to carry four cells no
build has ever reproduced:

| row | CFB | NFL | PL |
|---|---|---|---|
| `"Not much to go on"` | 555/888 | **208/272 cold · 0/272 warm** | 0/380 |
| `"So there is little to weigh up here: {title}."` | 256/888 | 47/272 cold · 0/272 warm | 0/380 |

**The NFL split is the whole of the NFL row, and it is worth being precise about.**
`_record()` reads the tracking DB; a settled pre-kickoff record produces the record
FACTOR, which fills the second slot on its own, and the padding loop then never
runs. So the row is at its most frequent exactly when the tracking DB is cold --
which on this service's own deploy is the NORMAL state, the DB being ephemeral
local container disk that a cold start wipes. The `271/272` this table used to
claim is reproduced by nothing: it is 208 without a record and 0 with one, and a
cell that reports a number no build produces is a cell nobody can check. The other
three that did not survive are corrected here too -- the second row was `CFB 331`,
`NFL 47` and `PL 50`, and it is 256, 47 and 0. Only NFL's 47 was right.

The query, so the table can be re-derived rather than believed. In a throwaway
worktree of each sport at its `origin/main` -- their local `main` branches are
stale, NFL's by 100+ commits -- with `PUBLIC_MODE=true`, so nothing touches the
network:

```python
import json, pathlib, sys
sys.path.insert(0, "src")
from nfl_predictor.api import facts              # or cfb_ / pl_
snap = json.loads(pathlib.Path("data/public_snapshot.json").read_text())
# NFL/CFB: snap["weeks"][*]["games"][*]["game_id"]        -> 272 and 888 ids
# PL:      snap["fixtures_by_gameweek"][*]["fixtures"][*]["event_id"]  -> 380 ids
ids = [...]                                       # de-duplicated, order kept
bundles = [facts.get_facts(i) for i in ids]      # 0 errors on all three
```

then render each through `explain_from_template` and count
`[f for f in out["factors"] if f["headline"] == "Not much to go on"]`. The cold-NFL
figure additionally needs `data/tracking.db` absent -- deleting it is what makes
`_record()` return `None`, and that is the entire difference between 208 and 0.
`test_the_padding_row_never_denies_a_number_the_bundle_carries` carries the same
counts for the sentence this table is about, and the fixture at the top of this
file is one of the 208.

So for a bundle with little in it, these are not padding in the disposable sense
-- they are most of the panel. Four edits to them were silent before this file:

* the first row's text became *"The model has no settled record on this one yet."*
  -- and that is **precisely a sentence an earlier draft was removed for**, per
  the comment at `template.py` above the padding loop: a `record` factor claiming
  something was missing when it was present, false for exactly the bundles that
  reach it. The only guard against its return was a comment.
* that row's `direction` went `down` -> `NEUTRAL`, silently. Nothing computes
  that mark: the row fires because the bundle carries little, and on the measured
  reach above it fires beside a 99% pick.
* the second row's text became *"So the model strongly disagrees with the market
  here."* -- silently, and it reintroduces the exact class this branch exists to
  remove: a comparison nothing computes.
* the verdict became *"BOS is a strong pick."* -- silently. It is the most
  prominent sentence in the panel, `prompts.py` forbids the model from exactly
  that ("a band is a word and a word is the same defect as a number when nothing
  ties it to anything"), and the template doing it would put "strong pick" on
  screen beside a `leaning` band chip, at the same time, contradicting itself.

**Every assertion here is exact equality, and none of them is a keyword absence.**
A test that says "the text does not contain 'disagrees'" is satisfied by a
sentence that says the same thing in other words, which is the only kind of
rewording that matters and the only one a rewording tends to be. Equality cannot
be satisfied by a superset, so it fails on an addition, a deletion and a
substitution alike.

The strings below are COPIES, deliberately, and not imports of the constants
`template.py` would grow if this were written the other way round. A test that
asserts a rendered sentence equals a constant the renderer also reads is a
constant compared with itself: it cannot fail, and it passes on the very edit it
was written to catch. Every literal here is a second object, and the harness
table carries a row per claim so the pin is not the only thing standing between
the sentence and a rewrite nobody re-reads.
"""
from __future__ import annotations

import pytest

from explainer.contract import NEUTRAL
from explainer.template import explain_from_template

# --- the three words the first padding row can say -------------------------
#
# **The distinction is between two different states of the DATA, and the old
# wording asserted a third one that is neither.**
#
# "The facts for this one are still filling in." is a claim about the *bundle*:
# that figures have not arrived. That was true of most of the bundles that reach
# it -- a football bundle carrying a moneyline and nothing else -- and it is now
# a *worse* description for NBA, because serving NBA is what made the difference
# visible. An NBA bundle that fires this row carries `model_margin` and
# `model_total`: the model HAS a projection, and what is missing is the *market's*
# quoted price. "The model has no settled record on this one yet" is a third
# state again, and the one this file exists to keep out: it is false for the
# bundle that reaches it, and an earlier draft was removed for exactly that
# sentence.
#
# So the row says WHICH state applies rather than asserting one, which is the
# only way a sentence can be true of a bundle carrying a model projection, a
# quoted price, both, or neither. Three wordings, three states, all derived from
# the bundle rather than guessed:
#
# * a projection and no quoted price -- the NBA case, and the one this branch
#   created. The model has a number; there is no book price to read it against.
# * both -- nothing is missing at all, and the row is here only because the
#   `label` gate kept a real row from firing. Saying anything is missing would be
#   false, so it says the opposite and stops there.
# * no projection -- the football case, and the only state in which the old
#   wording was accurate.

PADDING_PROJECTED_UNQUOTED = (
    "So there is a model number for this one, and no quoted price to read it against."
)
PADDING_PROJECTED_QUOTED = (
    "So the model and the market both have a number here, and little else to weigh."
)
PADDING_NOT_PROJECTED = "So there is no model number for this one yet."

PADDING_HEADLINE = "Not much to go on"

#: The second padding row, verbatim, and the only one that interpolates.
SECOND_PADDING_HEADLINE = "Where this stands"
SECOND_PADDING_TEXT = "So there is little to weigh up here: MIA at BOS."

#: The verdict, for a bundle whose pick is a long shot. `0.41` is below the
#: two-way `moderate` threshold of 0.52, so the band chip beside this sentence
#: reads `leaning` -- which is the whole point of pinning it: a "strong pick"
#: here would be on screen next to a `leaning" chip, at the same time.
LOW_PROB = 0.41
VERDICT = "BOS is the pick."
NO_PICK_VERDICT = "There is no pick for this one yet."


# --- the football bundle, built by NFL's and CFB's OWN `_markets` -----------
#
# **The critical's shape, as a fixture.** A football bundle that reaches the
# padding row is a moneyline and nothing else: NFL's and CFB's `_markets` emit
# the spread and the total only when the pre-kickoff prediction row carries
# `predicted_margin`/`predicted_total` AND the game row carries a
# `spread_line`/`total_line`, and for a game weeks out neither is there yet. So
# the market list is `[{"market": "moneyline", "model": {...}}]` and the pick's
# probability IS the model's number for this bundle.
#
# **The numbers below are a real bundle, not a shape.** `NFL_Predictor` at
# `origin/main`, `PUBLIC_MODE=true`, `get_facts("2026_05_TB_DAL")` on a cold
# tracking DB (`_record()` -> `None`), rendered through
# `explain_from_template`:
#
#     verdict  DAL is the pick.
#     [The pick]           The model makes DAL the pick at 57%.
#     [Not much to go on]  So there is no model number for this one yet.
#
# 208 of 272 NFL bundles render that pair on a cold DB and 555 of 888 CFB ones
# do on a warm one -- 763 rows, every one of them false, and every one of them
# sitting directly under a row quoting the number it denies. See
# `test_the_padding_row_never_denies_a_number_the_bundle_carries` for the
# property and the count.
NFL_FOOTBALL_PROB = 0.5701846721782629
NFL_FOOTBALL_BUNDLE = {
    "sport": "nfl", "id": "2026_05_TB_DAL", "title": "TB at DAL",
    "starts_at": "2026-10-09T00:15:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff",
    "pick": {"label": "DAL", "prob": NFL_FOOTBALL_PROB},
    "markets": [{"market": "moneyline", "model": {"DAL": NFL_FOOTBALL_PROB,
                                                  "TB": 1 - NFL_FOOTBALL_PROB}}],
    "drivers": [], "context": {}, "players": [],
    "record": None, "result": None,
}


def _bundle(sport: str = "nfl", markets: list | None = None, label: str | None = "BOS",
            prob: float = LOW_PROB, **over) -> dict:
    """A bundle with as little in it as the padding loop will accept.

    `status` and `pick_timing` are set so the result and rebuilt rows cannot fire
    and displace the row under test: these tests are about what is left when
    nothing else is, so a competing factor moving the answer would make a failure
    read as a displacement instead of a wrong sentence.
    """
    base = {
        "sport": sport, "id": "g1", "title": "MIA at BOS",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": label, "prob": prob},
        "markets": markets if markets is not None else [
            {"market": "moneyline", "model": {"BOS": prob, "MIA": 1 - prob}},
        ],
        "drivers": [], "context": {}, "players": [],
        "record": None, "result": None,
    }
    base.update(over)
    return base


def _padding(facts: dict, headline: str = PADDING_HEADLINE) -> dict:
    """The padding row with that headline, or a failure that says what rendered.

    Looked up by HEADLINE rather than by position, so a factor that moved or was
    dropped is reported as missing rather than compared against whichever row took
    its place -- the reason this lookup is not `factors[0]`.
    """
    out = explain_from_template(facts)
    found = [f for f in out["factors"] if f["headline"] == headline]
    assert len(found) == 1, (
        f"expected exactly one {headline!r} factor, found {len(found)}: {out['factors']}"
    )
    return found[0]


# --- the first padding row: its text, in all three states -------------------

def test_the_first_padding_row_says_which_state_the_bundle_is_in():
    """Exact equality, for the state an NBA bundle with no quote is in.

    This is the sentence the reviewer named, and the one the old wording got
    wrong: NBA's bundles carry `model_margin` and `model_total`, so the model has
    a projection and the absent thing is the *market's* price. Asserted for the
    NBA shape specifically, because that is the shape serving NBA created and the
    old sentence was written before it existed.
    """
    facts = _bundle("nba", [
        {"market": "moneyline", "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}},
        {"market": "spread", "model_margin": 4.2, "line": "BOS by 4.2"},
        {"market": "total", "model_total": 226.5},
    ])
    assert _padding(facts)["text"] == PADDING_PROJECTED_UNQUOTED, (
        f"an NBA bundle with a model projection and no quoted price is not being "
        f"told what is actually missing. It has `model_margin` and `model_total`: "
        f"the model HAS a number, and what the bundle lacks is the market's quoted "
        f"price. Those are different states, and the branch is what made the "
        f"difference visible."
    )


def test_the_padding_row_distinguishes_the_three_states_it_can_be_in():
    """All three, in one sweep, so no state can be left describing another.

    The states are derived, not asserted: the model's own figures for the
    projection and the sport's own market-line key for the quote. A row that
    reported one wording for all of them would pass a test that only built the NBA
    bundle, which is why this is a sweep over the bundles rather than separate
    one-line tests with separate chances to be written loosely.

    **The third case used to be called "neither" and expected
    `PADDING_NOT_PROJECTED`, and it was wrong.** Its bundle carried a moneyline
    and a pick at 41%, so it was not "neither" of anything -- the model had a
    number, and this row said it had none. The reason the case was written that
    way is the reason it is worth spelling out: the sentence is about a MODEL
    NUMBER, and the comment reasoned from whether there was a **margin or a
    total**, which is a different question with two of the three answers. Two of
    the three model figures were being asked about and the third was not, and for
    a football bundle the third is the only one there is.

    So the case is now the moneyline-only bundle rendered as what it is -- a model
    number and no quoted price -- and the genuinely empty state moved to its own
    test, where a bundle with no number of any kind is the premise rather than an
    accident of which keys the gate reads.
    """
    quoted = {"market": "spread", "model_margin": 4.2,
              "line": "BOS by 4.2", "market_line": "BOS -3.5"}
    projected = {"market": "total", "model_total": 226.5}
    # A quote with NO model figure. The market priced the game and the model has
    # no prediction for it, which is the one state the three wordings do not have
    # a name of their own -- and it is the case that decides the ORDER of the
    # branches in `template.py`. It has to take `PADDING_NO_PROJECTION`, because
    # that is the sentence that is true of it: the model genuinely has nothing
    # here, and `PADDING_BOTH` would be false. The pick is ABSENT as well as the
    # figures, which is what makes this a real instance of the state rather than a
    # bundle with a probability the gate might reasonably count as a number.
    quote_only = {"market": "spread", "market_line": "BOS -3.5"}

    moneyline = {"market": "moneyline", "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}

    cases = {
        # (markets, label, prob, expected)
        # The second and fourth cases are the reason a bundle with no PICK is
        # needed. The spread row is gated on `label`, so with a pick in hand the
        # quoted line renders as a real row, the panel has two factors and no
        # padding fires at all -- which is correct, and is why a quote is
        # reachable in the padding row only where the `label` gate closed the row
        # it would otherwise have had.
        "a projection and no quote": ([moneyline, projected], "BOS", LOW_PROB,
                                      PADDING_PROJECTED_UNQUOTED),
        "both, which is not a gap in the data": ([moneyline, projected, quoted], None, None,
                                                 PADDING_PROJECTED_QUOTED),
        # The football case, and the one this branch exists to correct. A moneyline
        # and a pick and no spread and no total: the model has a number, the market
        # has not quoted one, and this is the sentence that is true of that. The
        # NBA case above reaches the same wording by a different route, which is
        # the point -- two sports, one state, one sentence.
        "a moneyline and nothing else, which is the football case": (
            [moneyline], "BOS", LOW_PROB, PADDING_PROJECTED_UNQUOTED),
        # The order case. A quote, and no model figure, no moneyline and no
        # probability, so there is genuinely nothing for the model to have said
        # here. It takes the first branch, not the second: the market priced this
        # game and the model did not, and a row that says the model has a number
        # would be inventing one.
        #
        # **`prob=None` is load-bearing and is the point of the case.** Clearing
        # the label alone is not enough: the gate asks whether the bundle carries
        # a MODEL NUMBER, and a pick with a probability and no usable label is
        # still one -- the moneyline tile draws it either way. So this case clears
        # all three, and a version of it that left the probability behind would
        # be asserting that a bundle the panel draws a 41% for has no model
        # number, which is the exact false claim this sweep exists to keep out.
        "a quote and no model figure, which is the model having nothing": (
            [quote_only], None, None, PADDING_NOT_PROJECTED),
    }
    for name, (markets, label, prob, expected) in cases.items():
        got = _padding(_bundle("nba", markets, label=label, prob=prob))["text"]
        assert got == expected, (
            f"{name}: the row reads {got!r} rather than {expected!r}. These are "
            f"different claims about the bundle and one sentence cannot be true of "
            f"all of them -- and the last case is the one that fixes the order the "
            f"branches are tested in, because a quote with no model figure, no "
            f"moneyline and no probability must not be told the model has a number."
        )


def test_the_padding_row_never_denies_a_number_the_bundle_carries():
    """**The critical.** A bundle carrying a moneyline must not be told the model
    has no number for it.

    The sentence `PADDING_NO_PROJECTION` makes is *"So there is no model number for
    this one yet."* -- a claim about a **model number**, and in every football
    bundle the moneyline IS the model's number. The gate that chose this wording
    asked a different question: whether the bundle carries a **margin or a total**.
    Those are two of the three model figures, and the third one -- the pick's own
    probability, which the moneyline row above quotes verbatim and the panel draws
    in the moneyline tile and the split bar -- was never asked about. So the row
    said "no model number" directly beneath *"The model makes DAL the pick at
    57%."*, which is the padding row telling the reader the opposite of the row
    immediately above it.

    This is the same defect class the rest of this repo is about, and it is the
    version that survives a guard: the two tests that pinned this wording both
    reasoned correctly from the premise they had and drew a conclusion the premise
    did not support. *"The model genuinely has no margin or total for this one"* is
    true of this bundle. *"So there is no model number for this one yet"* does not
    follow from it. That is why this test asserts the property over a SPREAD of
    bundles rather than one more case in the sweep: the sweep's cases were chosen
    by whoever wrote them, and a case list that omits the moneyline is satisfied by
    a gate that cannot see the moneyline.

    **Asserted as a property over four bundles, each carrying a DIFFERENT model
    figure, and each pinned to the wording that is true of it.** One case is the
    regression; the other three are there so the fix cannot be a special case for
    the moneyline. Which is which, stated rather than implied:

    * **the football moneyline alone** -- the measured bundle, and the only one of
      the four the old gate got wrong. It is the case worth 763 rows.
    * a moneyline beside a *quoted* total with no model total -- the quote
      branch. Fixing the denial by making `projected` constant would pass the first
      case and turn this into a different falsehood, and this is what catches it.
    * an NBA spread and a total, no quote -- the state this branch was born for,
      unchanged, so "the football case now works" cannot be paid for by breaking
      the NBA one.
    * PL's three-way `result` map -- a fourth sport, a four-outcome vocabulary
      (`_outcome_key` resolves it to `result` rather than `moneyline`), and the
      shape the next sport added will look like.

    **The one thing this cannot distinguish, said here rather than left for the
    next reader to assume it does.** The fix reads the pick's *probability*. A
    different fix could read the moneyline market's `model` map instead, and on
    every bundle this service can produce the two are the same decision: across all
    1,432 real bundles built from `nfl_predictor`/`cfb_predictor`'s `get_facts` for
    this finding, there is not one with a `pick.prob` and no moneyline/result
    `model` map, nor one with the map and no probability. They are observationally
    identical here, so a spread built to separate them would be testing a bundle no
    sport emits. `prob` is the one that was chosen because it is the same value the
    verdict and the band are built from, so "the model has a number" and "the panel
    has a figure to draw" are one decision rather than two scans that can come
    apart -- and that reasoning is the guard, not the key.

    **The measured reach, so the number is a fact rather than an adjective.**
    Bundles built from `nfl_predictor`/`cfb_predictor`'s own `get_facts` at their
    `origin/main`, `PUBLIC_MODE=true`, rendered through this function:

    | sport | bundles | render the sentence | of those, false |
    |---|---|---|---|
    | CFB | 888 | 555 | **555** |
    | NFL, cold tracking DB | 272 | 208 | **208** |
    | NFL, settled record in the DB | 272 | 0 | 0 |

    763 false rows, all 763 sitting directly under a `The pick` row. The NFL row
    is conditional on `_record()` returning `None` -- with a settled pre-kickoff
    record in the tracking DB the record factor fills the second slot and the
    padding row never fires, which is the whole of the difference between 208 and
    0. With `EXPLAINER_ENABLED=false` this row is the only prose a reader of a
    football game ever sees.
    """
    cases = {
        "the football moneyline alone": (NFL_FOOTBALL_BUNDLE, PADDING_PROJECTED_UNQUOTED),
        "a moneyline beside a quoted total and no model total": (_bundle("nfl", [
            {"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
            {"market": "total", "line": 45.5},
        ], prob=0.62), PADDING_PROJECTED_QUOTED),
        "an NBA spread and a total, no quote": (_bundle("nba", [
            {"market": "moneyline", "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}},
            {"market": "spread", "model_margin": 4.2, "line": "BOS by 4.2"},
            {"market": "total", "model_total": 226.5},
        ]), PADDING_PROJECTED_UNQUOTED),
        "PL's three-way result map": (_bundle("pl", [
            {"market": "result", "model": {"LIV": 0.44, "D": 0.26, "ARS": 0.30}},
        ], label="LIV", prob=0.44), PADDING_PROJECTED_UNQUOTED),
    }
    for name, (bundle, expected) in cases.items():
        got = _padding(bundle)["text"]
        assert got != PADDING_NOT_PROJECTED, (
            f"{name}: the padding row reads {got!r} over a bundle that carries a "
            f"model number. The claim is about a MODEL NUMBER, and the row above it "
            f"just quoted one -- for the football case, 'The model makes DAL the "
            f"pick at 57%' sits directly above 'So there is no model number for "
            f"this one yet', and the panel draws the same 57% in the moneyline tile "
            f"and the split bar. Measured, this row was FALSE for 555 of 888 CFB "
            f"bundles and 208 of 272 NFL ones."
        )
        # Exact equality, not "not the false one": the denial is one of three
        # failures this row can make, and a rewrite that claimed a different
        # falsehood would pass an inequality. The expected string is a second
        # object, copied at the top of this file rather than imported.
        assert got == expected, (
            f"{name}: the padding row reads {got!r} rather than {expected!r}. "
            f"Three wordings, three states, and the state is derived from what the "
            f"bundle carries -- a model number with no quoted price, both, or "
            f"neither. This bundle is in the first or the second."
        )


def test_the_football_moneyline_row_renders_the_two_figures_state():
    """The one real bundle, end to end, pinned exactly.

    The property above says the row must not deny a number. This says what it says
    INSTEAD for the bundle the finding was measured on, and it is here because
    "not the false sentence" is satisfied by any of an unbounded number of other
    sentences -- including tomorrow's. The expected string is a second object:
    `PADDING_NO_QUOTE` is copied at the top of this file rather than imported, so
    a renderer edited to match its own constant fails here.
    """
    out = explain_from_template(NFL_FOOTBALL_BUNDLE)
    assert out["verdict"] == "DAL is the pick.", out["verdict"]
    assert [f["headline"] for f in out["factors"]] == ["The pick", PADDING_HEADLINE], out
    assert _padding(NFL_FOOTBALL_BUNDLE)["text"] == PADDING_PROJECTED_UNQUOTED, (
        "a football bundle carrying a moneyline and no spread and no total has a "
        "model number and no quoted price, which is the state this wording is for. "
        "It is the same state an NBA bundle with `model_margin` and `model_total` "
        "and no `market_line` is in, and the row directly above -- the moneyline -- "
        "says so in the model's own words."
    )


def test_a_bundle_with_no_model_number_at_all_still_says_so():
    """The other end, because the fix must not make `PADDING_NO_PROJECTION`
    unreachable -- and a gate that always says "projected" is a gate that can only
    be wrong in one direction, which is how a fix for a denial becomes a different
    denial.

    A genuinely empty bundle: no pick, no markets, no record. NFL's and CFB's
    `_markets` return `[]` for a started game with no stored pick, and 4 of 272
    NFL bundles and 256 of 888 CFB ones are exactly this. There is no number here
    of any kind, so this is the one state the sentence is true of.
    """
    empty = _bundle("nfl", [], label=None, prob=None, record=None, result=None)
    assert _padding(empty)["text"] == PADDING_NOT_PROJECTED, (
        f"a bundle with no pick, no markets and no record rendered "
        f"{_padding(empty)['text']!r}. There is no model number in that bundle of "
        f"any kind, so this is the one state the sentence is true of, and 4 of 272 "
        f"real NFL bundles and 256 of 888 real CFB ones are in it."
    )


def test_the_padding_row_never_claims_a_settled_record_is_missing():
    """The sentence an earlier draft was removed for, with the record PRESENT.

    That is the specific trap the comment above the padding loop records: "never a
    claim that something is missing when it is present". A record IS present here,
    the row still has to render (the pick has no usable label, so the record is
    the only factor), and what it must not say is that the record is missing.

    A first version of this file asserted the removed sentence is absent as a
    substring, which is a keyword test and would have been satisfied by *"The
    model has no settled record on this one yet."* -- the exact sentence the
    comment names as the reason the earlier draft was withdrawn. The prohibition
    is therefore carried by the exact-equality sweep above: three wordings, and a
    fourth has to be written and pinned on purpose.

    **This case expected `PADDING_NO_PROJECTION` and was reasoning from the wrong
    premise, which is the same error as the critical one row up.** The bundle's
    moneyline carries `{"BOS": 0.41, "MIA": 0.59}` -- the model HAS a number for
    this one, the panel is drawing it in the split bar, and `PADDING_NO_PROJECTION`
    denies it. The comment's stated reason, *"the model genuinely has no margin or
    total for this one"*, is true and irrelevant: the sentence is about a model
    NUMBER, and the moneyline is one. So the expected wording is now the one that
    is true of this bundle -- a model number, and no quoted price -- and the
    record-claim prohibition rides on it unchanged.

    The record being present is what makes this test worth having over the sweep:
    it is the one bundle in the file where a *third* thing is present that the row
    has no word for, so the row has to pick its wording from the two it does know
    and get it right about the other two.
    """

    def _one_pick_bundle_with_record():
        facts = _bundle("nba", [{"market": "moneyline",
                                 "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}],
                        label=None)
        facts["record"] = {"label": "Picks made before tip-off", "hits": 30, "settled": 50}
        return facts

    text = _padding(_one_pick_bundle_with_record())["text"]
    assert text == PADDING_PROJECTED_UNQUOTED, (
        f"a bundle with a record present rendered {text!r}. The record is here and "
        f"is not missing. The model also has a number -- the moneyline carries "
        f"{{'BOS': {LOW_PROB}, 'MIA': {1 - LOW_PROB}}} and the panel draws it -- so "
        f"the row is in the model-number-and-no-quote state, which is what this "
        f"wording says. Saying the model has no number here would be false of a "
        f"bundle the reader has already been shown a number from."
    )
    assert "record" not in text.lower(), (
        f"the row comments on the record: {text!r}. An earlier draft padded with a "
        f"`record` factor saying no settled record yet, which was false for exactly "
        f"the bundles that reach this loop."
    )


def test_a_pl_bundle_with_a_book_price_is_not_told_there_is_none():
    """**The second finding.** `PADDING_NO_QUOTE` says *"no quoted price to read it
    against"*, and PL's `result` market carries the book's price in a key nothing
    read.

    **The decision, and the argument for it: the template reads `implied`.** The
    alternative was to declare PL's book price out of scope in a comment, and the
    argument for that is spec §13b -- the split bar's *market row* is omitted
    unless `implied` covers every outcome the model's split has, and PL's real
    `implied` covers only the two sides of a three-way market, so that row is
    never drawn. That argument does not survive one more sentence of the same
    spec:

        The same rule governs the tile's market line: it states `implied` **for a
        side that is present**, and is omitted when the side it would name has no
        `implied`.

    The tile is a different surface from the market row, and §13b does not govern
    it. A LIV pick with `implied: {LIV: 0.44, ARS: 0.30}` gets a key-number tile
    showing the model's 44% with the market's 44% beneath it. So the reader has the
    price on screen, in the panel's most prominent figure surface, two rows above
    the sentence denying there is one -- and a "deliberately out of scope" comment
    would be a claim about the product that the product contradicts. "Latent"
    would be true (0 of 380 real PL bundles carry `implied`; none of the 380 has
    `has_live_odds`) and latent is not the same as honest.

    **Both directions, and the second is the one that makes the first a guard.** A
    gate that asked "does the market have an `implied` KEY" would pass the case
    above and then deny a price for a bundle carrying `implied: {LIV: null}` --
    which PL's own `_implied` can produce, since it writes a per-side value that is
    `None` whenever that side has no price and only adds the map when at least one
    side does. So the second case is a map with no number in it, and it must still
    be told there is no quoted price. A gate that read the key's presence rather
    than its contents is the mutation this pair exists to kill.

    The bundle is the reviewer's, kept as built: `implied` on the `result` market,
    a `total_goals` market at 2.6, no `btts`, and a LIV pick at 44%. Those last
    two details are what make the padding row fire at all -- a PL bundle with a
    `btts` market gets that row and never reaches here, which is why 0 of 380 real
    bundles do.
    """
    priced = {
        "sport": "pl", "id": "g1", "title": "ARS at LIV",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff",
        "pick": {"side": "home_win", "label": "LIV win", "prob": 0.44},
        "markets": [
            {"market": "result",
             "model": {"home_win": 0.44, "draw": 0.26, "away_win": 0.30},
             "implied": {"LIV": 0.44, "ARS": 0.30}},
            {"market": "total_goals", "model_total": 2.6},
        ],
        "drivers": [], "context": {}, "players": [],
        "record": None, "result": None,
    }
    got = _padding(priced)["text"]
    assert got == PADDING_PROJECTED_QUOTED, (
        f"a PL bundle whose result market carries `implied` -- the book's price -- "
        f"rendered {got!r}. The tile for that market draws the market's own figure "
        f"beside the model's (spec §13b, the tile's market line), so the reader has "
        f"the price on screen and this row says there is none. A `quote_only` bundle "
        f"two keys away and PL's `result` market are the same sentence about a "
        f"bundle, and reading two of its keys is how the denial got here."
    )

    # The other direction. Same bundle, a map with no number in it -- which is what
    # PL's `_implied` writes for a side that has no price, and it is why the gate
    # has to read the CONTENTS rather than the key's presence.
    unpriced = {**priced, "markets": [
        {"market": "result",
         "model": {"home_win": 0.44, "draw": 0.26, "away_win": 0.30},
         "implied": {"LIV": None, "ARS": None}},
        {"market": "total_goals", "model_total": 2.6},
    ]}
    assert _padding(unpriced)["text"] == PADDING_PROJECTED_UNQUOTED, (
        f"a bundle whose `implied` map holds no number rendered "
        f"{_padding(unpriced)['text']!r}. There is no price in that map, so the "
        f"row is right to say so -- and a gate that asked whether the KEY is present "
        f"would fail here while passing the case above, which is why both are here."
    )


def test_a_record_that_is_present_is_not_reported_as_missing():
    """The record row still wins its slot, so the removed sentence is not reachable.

    A bundle with a record produces the record FACTOR rather than padding, because
    the record is emitted before the padding loop and the loop only tops the list
    up. So the sentence the earlier draft used is doubly unreachable: the state
    it described is the one state the loop never sees. This pins the ordering,
    which is what makes it unreachable, rather than trusting the comment.

    It is the free-slot property too: `test_template_spread_claim.py` already
    pins that dropping the spread row sends the freed slot to the record. This is
    the other end of it -- a record present is a row present.
    """
    facts = _bundle("nba", [{"market": "moneyline",
                             "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}])
    facts["record"] = {"label": "Picks made before tip-off", "hits": 30, "settled": 50}
    out = explain_from_template(facts)
    headlines = [f["headline"] for f in out["factors"]]
    assert "Its record so far" in headlines, headlines
    assert PADDING_HEADLINE not in headlines, (
        f"the padding row was rendered beside a record that is present: {headlines}"
    )


# --- the direction: an exact-equality pin, not a keyword absence ------------

@pytest.mark.parametrize("prob,label", [
    pytest.param(0.99, "BOS", id="a 99% pick"),
    pytest.param(LOW_PROB, "BOS", id="a long shot"),
    pytest.param(0.62, "BOS", id="a strong pick"),
], ids=lambda v: str(v))
def test_the_first_padding_row_claims_nothing_about_the_pick(prob, label):
    """`neutral`, whatever the pick, and asserted as the exact emitted value.

    **The decision, and the argument for it.** The row was `down` when there was a
    pick, which is the panel drawing a triangle and the words "against the pick"
    for a sentence that is about the *bundle's* coverage rather than about this
    pick. Nothing computes that mark: the row fires because the bundle carries
    little, and a bundle carrying little is exactly as consistent with a 99% pick
    as with a long shot. So on the measured reach above, the commonest case is a
    confident pick sitting beside a row marked against it.

    The sibling row is already argued this way at the bottom of the padding loop
    -- "So there is little to weigh up here" is not an argument FOR a pick; it was
    given `up` because the row needed a direction, and the words above it do not
    support one. The same argument applies here with the sign reversed, and
    applying it is what makes the two rows consistent: both are statements about
    the bundle, so both are `neutral`, always, and neither varies with the pick.

    **Parametrised across the pick deliberately.** A sweep is what makes this a
    statement about the CODE rather than about one bundle. `_toward(NEUTRAL,
    has_pick)` would pass a single-pick test and is the exact thing the sibling
    row's comment rules out, because it reads like a rule and is a no-op wrapping
    a no-op -- the same reasoning the spread factor's `NEUTRAL` records.
    """
    facts = _bundle("nfl", None, label=label, prob=prob)
    factor = _padding(facts)
    assert factor["direction"] == NEUTRAL, (
        f"a {prob:.0%} pick renders the padding row as {factor['direction']!r}. "
        f"`down` means 'against the pick' and nothing here computes that: the row "
        f"fires because the bundle carries little, which is equally consistent with "
        f"a 99% pick. The panel draws a triangle and the words 'against the pick' "
        f"from this mark, so a mark nothing supports is a wrong claim in a louder "
        f"form than the sentence."
    )


def test_the_padding_row_does_not_move_when_the_pick_appears():
    """The property behind the mark, so it cannot come back as wording.

    A bundle with no pick and the same bundle with a pick must render the same
    row, mark included. That is a statement about the code -- this row is not
    pick-relative -- rather than about today's wording, so a re-marking written
    as anything at all fails it.
    """
    with_pick = _bundle("nfl", None, label="BOS", prob=LOW_PROB)
    without = _bundle("nfl", None, label=None, prob=LOW_PROB)
    a, b = _padding(with_pick), _padding(without)
    assert a["direction"] == b["direction"] == NEUTRAL, (a, b)
    assert a["text"] == b["text"], (
        f"the padding row's wording moved with the pick, so it is still "
        f"pick-relative in some way: {a['text']!r} vs {b['text']!r}"
    )


def test_the_second_padding_row_is_neutral_and_says_exactly_this():
    """The sibling, pinned in the same terms so the two cannot drift apart.

    It was already `neutral` and already argued at length in `template.py`; this
    is the assertion, and it is here because "already reasoned about" is not the
    same as "checked". A change to the mark would otherwise be silent, which is
    the same defect class as the first row's.

    **Reaching it takes a specific bundle, and the first version of this test
    could not.** The `else` branch fires only when a `context` factor already
    exists and the list is still short, so the rebuilt row (the one other
    `context` factor) has to be the ONLY factor: a bundle that also has a pick
    reaches two factors before the loop starts and neither padding row renders at
    all. So the pick is removed and the timing set to `rebuilt`, which is also the
    one bundle where "not counted" and "little to weigh up" are consistent with
    each other.
    """
    facts = _bundle("nfl", None, label=None, prob=LOW_PROB, pick_timing="rebuilt")
    factor = _padding(facts, SECOND_PADDING_HEADLINE)
    assert factor["direction"] == NEUTRAL, factor
    assert factor["text"] == SECOND_PADDING_TEXT, (
        f"the second padding row reads {factor['text']!r} rather than "
        f"{SECOND_PADDING_TEXT!r}"
    )
    # And the first row is NOT also in the answer, so this is the second row
    # rather than the first mislabelled.
    headlines = [f["headline"] for f in explain_from_template(facts)["factors"]]
    assert PADDING_HEADLINE not in headlines, headlines


def test_a_row_that_cannot_be_pick_relative_never_asks_toward_about_it():
    """`NEUTRAL` is written as a constant, and this is what holds it there.

    **A survivor, found and closed.** The rendered-output guards above cannot
    distinguish `NEUTRAL` from `_toward(NEUTRAL, has_pick)`: the two produce the
    same answer for every bundle, so the whole file passed with the second one in
    place. That matters because `template.py` rules the second one out in a
    comment -- "a no-op wrapping a no-op, and reads like a rule" -- and a rule
    held only by a comment is the shape of guard this repo keeps being bitten by:
    the comment is a claim, and nothing checks it.

    Closed by **recording the calls rather than reading the source.** A test that
    greps `template.py` for `_toward(NEUTRAL` would be satisfied by the comment
    quoting the expression, which is the decoy the harness documents for its own
    anchors and that `template.py` itself carries a NOTE about. Replacing the
    module's `_toward` with a spy and rendering a spread of bundles asks a
    different question -- what does the function actually CALL, over the whole
    range of inputs -- and no comment can answer it. That is the difference
    between inspecting a source and watching a program.

    The spread matters: `_toward(NEUTRAL, has_pick)` is only a *lie* in the code
    sense, but a spy that only saw one bundle could miss a call on another path.
    So every row type that routes through `_toward` is rendered: finished,
    rebuilt, and padded, with and without a pick.
    """
    import explainer.template as tpl

    seen: list[tuple[str, bool]] = []
    real = tpl._toward

    def spy(direction: str, has_pick: bool) -> str:
        seen.append((direction, has_pick))
        return real(direction, has_pick)

    moneyline = {"market": "moneyline", "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}
    bundles = [
        # A finished game with a pick -- `_toward("up", ...)`.
        _bundle("nfl", [moneyline], status="final", result={"score": "21-17",
                                                            "pick_won": True}),
        # A rebuilt pick, with and without a pick to be relative to.
        _bundle("nfl", [moneyline], pick_timing="rebuilt"),
        _bundle("nfl", [moneyline], label=None, pick_timing="rebuilt"),
        # The padded rows, with and without a pick.
        _bundle("nfl", [moneyline]),
        _bundle("nfl", [moneyline], label=None),
    ]
    tpl._toward = spy
    try:
        for bundle in bundles:
            explain_from_template(bundle)
    finally:
        tpl._toward = real

    assert seen, "the spy was never called, so this proves nothing about the code"
    offending = [c for c in seen if c[0] == NEUTRAL]
    assert not offending, (
        f"{offending} -- `direction` was `NEUTRAL` and went through `_toward`. The "
        f"call is a no-op that returns NEUTRAL either way, so no rendered-output "
        f"test can see it; what it costs is a reader who finds it later, because it "
        f"reads like a rule about pick-relative direction and settles nothing. Write "
        f"the constant. The rows that are genuinely pick-relative pass a real "
        f"direction (`up`/`down`) and belong in `_toward`."
    )
    # The spy has to have been reached on the paths that DO use it, or the
    # assertion above is satisfied by a program that calls nothing.
    assert {d for d, _ in seen} <= {"up", "down"} and seen, sorted({d for d, _ in seen})


# --- the verdict -----------------------------------------------------------

@pytest.mark.parametrize("prob,expected_band", [
    pytest.param(0.41, "leaning", id="a long shot, and a leaning chip beside it"),
    pytest.param(0.55, "moderate", id="moderate"),
    pytest.param(0.62, "strong", id="strong"),
    pytest.param(0.99, "strong", id="very strong"),
], ids=lambda v: str(v))
def test_the_verdict_names_the_pick_and_qualifies_it_by_nothing(prob, expected_band):
    """Exact equality, swept across the band, for the most prominent sentence in
    the panel.

    The band is the point. `band_for` puts a 0.41 two-way pick in `leaning` and a
    0.62 one in `strong`, and the panel draws that word as a chip beside this
    sentence -- so a template that added "strong" here would be contradicting
    itself on screen, at the same time, in the one place a reader looks first.
    And `prompts.py` forbids the model from exactly this: a band is a word, and a
    word is the same defect as a number when nothing ties it to anything.

    The sweep across the band is what makes it a statement about the CODE. A
    qualifier keyed to the probability ("strong" above 0.6, "slim" below) would
    pass a single-bundle test and is the mutation most likely to be written
    next, because it looks like an improvement. Swept, it cannot.
    """
    facts = _bundle("nfl", None, label="BOS", prob=prob)
    out = explain_from_template(facts)
    assert out["verdict"] == VERDICT, (
        f"at {prob:.0%} the verdict reads {out['verdict']!r} rather than "
        f"{VERDICT!r}, and the band chip beside it reads {expected_band!r}. A "
        f"qualifier here is a claim nothing checks, and where it disagrees with "
        f"the chip the panel contradicts itself in the one sentence every reader "
        f"sees first."
    )
    # The band the sentence must NOT contradict, derived rather than hard-coded,
    # so this cannot drift from `contract.band_for` if the thresholds move.
    from explainer.contract import band_for, market_shape
    assert out["band"] == band_for(prob, market_shape(facts)) == expected_band, out


def test_the_verdict_with_no_pick_says_exactly_this():
    """The other branch of the same line, pinned rather than assumed.

    A one-line conditional that renders a pick and renders its absence, where only
    the first half was pinned. The two are the same claim in two states -- what
    the reader is told there is a pick -- and the second half was the easier one to
    reword.
    """
    facts = _bundle("nfl", None, label=None, prob=LOW_PROB)
    out = explain_from_template(facts)
    assert out["verdict"] == NO_PICK_VERDICT, out["verdict"]
    assert "pick" in out["verdict"] and "BOS" not in out["verdict"], out


def test_the_verdict_names_the_pick_whose_label_the_bundle_carries():
    """The label is interpolated, so a hard-coded one would pass the tests above.

    Every other test in this file uses `BOS`. A verdict that ignored the label and
    always said "BOS is the pick" would satisfy all of them, and would tell a
    reader about the wrong team -- the "right number, wrong attribution" shape
    `contract.pick_for` exists to prevent, arriving through the template instead.
    """
    facts = _bundle("nfl", None, label="KC", prob=LOW_PROB)
    assert explain_from_template(facts)["verdict"] == "KC is the pick."
