"""The padding rows and the verdict, pinned exactly -- because they are the rows
every reader of a thin bundle actually sees.

Two rows exist only so the panel is never a single lonely line, and the verdict
is the one sentence above them. Measured reach, which is why they are worth
pinning rather than describing:

| row | bundles that render it |
|---|---|
| `"Not much to go on"` | NFL 271/272, CFB 555/888, NBA 373/1760 |
| `"So there is little to weigh up here: {title}."` | CFB 331, NFL 47, NBA 231, PL 50 |

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

    The states are derived, not asserted: `model_margin`/`model_total` for the
    projection and the sport's own market-line key for the quote. A row that
    reported one wording for all of them would pass a test that only built the NBA
    bundle, which is why this is a sweep over the three bundles rather than three
    separate one-line tests with three separate chances to be written loosely.
    """
    quoted = {"market": "spread", "model_margin": 4.2,
              "line": "BOS by 4.2", "market_line": "BOS -3.5"}
    projected = {"market": "total", "model_total": 226.5}
    # A quote with NO model figure. The market priced the game and the model has
    # no prediction for it, which is the one state the three wordings do not have
    # a name of their own -- and it is the case that decides the ORDER of the
    # branches in `template.py`. It has to take `PADDING_NO_PROJECTION`, because
    # that is the sentence that is true of it: the model genuinely has nothing
    # here, and `PADDING_BOTH` would be false.
    quote_only = {"market": "spread", "market_line": "BOS -3.5"}

    moneyline = {"market": "moneyline", "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}

    cases = {
        # (markets, pick present, expected)
        # The second and fourth cases are the reason a bundle with no PICK is
        # needed. The spread row is gated on `label`, so with a pick in hand the
        # quoted line renders as a real row, the panel has two factors and no
        # padding fires at all -- which is correct, and is why a quote is
        # reachable in the padding row only where the `label` gate closed the row
        # it would otherwise have had.
        "a projection and no quote": ([moneyline, projected], True,
                                      PADDING_PROJECTED_UNQUOTED),
        "both, which is not a gap in the data": ([moneyline, projected, quoted], False,
                                                 PADDING_PROJECTED_QUOTED),
        "neither, which is the old wording's only true case": ([moneyline], True,
                                                              PADDING_NOT_PROJECTED),
        "a quote and no model figure, which is the model having nothing": (
            [moneyline, quote_only], False, PADDING_NOT_PROJECTED),
    }
    for name, (markets, has_pick, expected) in cases.items():
        got = _padding(_bundle("nba", markets,
                               label="BOS" if has_pick else None))["text"]
        assert got == expected, (
            f"{name}: the row reads {got!r} rather than {expected!r}. These are "
            f"different claims about the bundle and one sentence cannot be true of "
            f"all of them -- and the last case is the one that fixes the order the "
            f"branches are tested in, because a quote with no model figure must not "
            f"be told the model has a number."
        )


def test_the_padding_row_never_claims_a_settled_record_is_missing():
    """The sentence an earlier draft was removed for, with the record PRESENT.

    That is the specific trap the comment above the padding loop records: "never a
    claim that something is missing when it is present". A record IS present here,
    the row still has to render (the pick is absent, so the record is the only
    factor), and what it must not say is that the record is missing.

    A first version of this file asserted the removed sentence is absent as a
    substring, which is a keyword test and would have been satisfied by *"The
    model has no settled record on this one yet."* -- the exact sentence the
    comment names as the reason the earlier draft was withdrawn. The prohibition
    is therefore carried by the exact-equality sweep above: three wordings, and a
    fourth has to be written and pinned on purpose.

    **What this test cannot do.** It cannot see a sentence making the same claim
    in other words -- no test on prose can, and `validate._verdict_problems`
    rejects that shape in its own words. What it does is make the three pinned
    wordings the only three, and the harness table carries a row that turns the
    first of them into "the model has no settled record on this one yet", which
    fails on the mutation rather than on the wording.
    """

    def _one_pick_bundle_with_record():
        facts = _bundle("nba", [{"market": "moneyline",
                                 "model": {"BOS": LOW_PROB, "MIA": 1 - LOW_PROB}}],
                        label=None)
        facts["record"] = {"label": "Picks made before tip-off", "hits": 30, "settled": 50}
        return facts

    text = _padding(_one_pick_bundle_with_record())["text"]
    assert text == PADDING_NOT_PROJECTED, (
        f"a bundle with a record present rendered {text!r}. The record is here and "
        f"is not missing, and the model genuinely has no margin or total for this "
        f"one -- which is what this wording says and what the removed one did not."
    )
    assert "record" not in text.lower(), (
        f"the row comments on the record: {text!r}. An earlier draft padded with a "
        f"`record` factor saying no settled record yet, which was false for exactly "
        f"the bundles that reach this loop."
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
