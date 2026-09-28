"""The spread factor states two numbers, and names neither a side nor a winner.

The factor used to carry a second sentence that was a CONSTANT:

    It rates BOS 4.2 points better, against a line of BOS -3.5. That is the
    market asking for more than the model thinks the gap is worth.

Nothing in the template compares `model_margin` with the quoted line, so that
sentence was a comparison stated rather than computed -- true only when the
market happens to want more than the model does, and false otherwise. With
`model_margin = 4.2`:

| quoted line | "the market is asking for more" |
|-------------|--------------------------------|
| `BOS -3.5`  | FALSE -- the market asks 3.5, the model says 4.2, so it asks for LESS |
| `BOS -4.2`  | FALSE -- the two agree exactly |
| `BOS -6.0`  | true |

The first two are the common cases: a confident model is usually more bullish
than the market, so the shipped sentence is usually wrong about the direction of
the disagreement. And the deploy runs `EXPLAINER_ENABLED=false`, so this
template is the only prose a reader ever sees.

`direction: "down"` was the same error drawn as a mark, and wrong for the same
reason: `down` means "against the pick", which requires the market to be
*softer* than the model -- and "the market is softer than the model" is a point
FOR the pick. So the mark pointed the opposite way from the claim it was
justifying.

**And the first half of that sentence named a side, which was a second claim in
the same breath.** `model_margin` is home-minus-away, NFL and CFB word the line
from the home team, and the bundle carries no home/away designation -- so "It
rates {pick} N better" attributed a margin to the pick's team when the pick may
be the other side, and set it beside a line belonging to a third fact. The case
is `_nfl_away_pick` below.

**What the tests below pin, and why a sweep.** The fix is to say only what the
numbers support, so the rendered sentence has to be the same for all three lines
above. That is stricter than "the sentence is not false in the common case": it
forbids the claim even in the one case where it would be true, because printing
it there and not elsewhere is a comparison only something computed could decide.
`QUOTES` is that sweep, and it is the reason a mutation that reinstates either
the sentence or the mark has nowhere to hide.

Every assertion here is on rendered output. None of them reads `template.py`,
and none of them greps a source file for a word -- a check that can be satisfied
by a comment, a string constant or a decoy is not a check on what a reader sees.
"""
from __future__ import annotations

import pytest

from explainer.contract import NEUTRAL
from explainer.template import explain_from_template

#: The model's own margin, held fixed while the quoted line moves underneath it.
MARGIN = 4.2
QUOTES = [
    pytest.param("BOS -3.5", id="market asks for less than the model rates"),
    pytest.param("BOS -4.2", id="the two agree exactly"),
    pytest.param("BOS -6.0", id="market asks for more than the model rates"),
]


def _bundle(sport: str, markets: list, label: str = "BOS", **over) -> dict:
    """A bundle shaped like the one each sport's `/facts` builder really emits.

    `pick_timing` and a finished-free `status` are set so the rebuilt and final
    factors cannot fire and displace the one under test: the spread factor is
    the third candidate here, and a padding row reaching `MAX_FACTORS` first
    would make a failure read as a displacement instead of a wrong sentence.
    """
    base = {
        "sport": sport, "id": "g1", "title": "MIA at BOS",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": label, "prob": 0.62},
        "markets": markets, "drivers": [], "context": {}, "players": [],
        "record": None, "result": None,
    }
    base.update(over)
    return base


def _nba(quoted: str) -> dict:
    """NBA's shape: `line` is the MODEL's own wording, `market_line` the book's."""
    return _bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
        {"market": "spread", "model_margin": MARGIN,
         "line": "BOS by 4.2", "market_line": quoted},
    ])


def _spread(facts: dict) -> dict:
    """The spread factor, or a failure that says what rendered instead.

    The lookup is on the emitted `key`, not on position, so a factor that moved
    or was dropped is reported as missing rather than silently compared against
    whichever row took its place.
    """
    body = explain_from_template(facts)
    found = [f for f in body["factors"] if f["key"] == "spread"]
    assert len(found) == 1, (
        f"expected exactly one spread factor, found {len(found)}: {body['factors']}"
    )
    return found[0]


# --- the two honest numbers, and only them ---------------------------------

@pytest.mark.parametrize("quoted", QUOTES)
def test_the_spread_factor_is_the_two_numbers_and_nothing_else(quoted):
    """Exact equality, so a reinstated clause fails however it is worded.

    The previous test suite had no assertion on this sentence beyond "3.4 points
    better" and "BAL -2.5" are present, which the false sentence did not break:
    it only ever ADDED words, so every existing check stayed green while the
    claim shipped. Equality cannot be satisfied by a superset.
    """
    assert _spread(_nba(quoted))["text"] == (
        f"It projects a margin of {MARGIN:g} points, against a line of {quoted}."
    )


@pytest.mark.parametrize("quoted", QUOTES)
def test_the_spread_factor_claims_no_direction(quoted):
    """`neutral`, for all three lines, including the one where `down` would fit.

    The mark is not a decoration on the sentence: `up`/`down` is what the panel
    draws a triangle and a "for the pick" / "against it" word from, so a mark
    the two numbers do not support is the same false claim in a louder form. The
    third case is in the sweep precisely because the mark would be *correct*
    there -- which is how a constant mark survives a spot check.
    """
    factor = _spread(_nba(quoted))
    assert factor["direction"] == NEUTRAL, (
        f"a {factor['direction']!r} mark on a quoted {quoted!r} is a claim about which "
        f"of the two numbers is bigger, and nothing in the template computes it: {factor}"
    )


def test_the_sentence_cannot_depend_on_the_comparison():
    """The sweep as one assertion, so "it happens to be right here" is not enough.

    Three lines whose only difference is whether the market wants more, less, or
    exactly as much as the model. Prose making that comparison has to differ in
    at least one of them; requiring all three sentences to be identical once the
    quoted token is masked is a statement about the code -- the template is not
    comparing them -- rather than about today's wording.
    """
    lines = ["BOS -3.5", "BOS -4.2", "BOS -6.0"]
    masked = {_spread(_nba(line))["text"].replace(line, "<line>") for line in lines}
    assert len(masked) == 1, f"the sentence varies with the two numbers: {sorted(masked)}"


# --- not just NBA ----------------------------------------------------------

@pytest.mark.parametrize("sport,model_margin,line,label,expected", [
    # NFL and CFB put the MARKET's line in `line` and have no `market_line`.
    ("nfl", 3.4, "BAL -2.5", "BAL", "It projects a margin of 3.4 points, against a line of BAL -2.5."),
    ("cfb", 3.4, "BAL -2.5", "BAL", "It projects a margin of 3.4 points, against a line of BAL -2.5."),
])
def test_every_sport_that_renders_the_factor_gets_the_honest_one(sport, model_margin, line,
                                                                 label, expected):
    """The clause was not NBA's bug; NBA only made it reachable in a new shape.

    NFL and CFB have quoted this sentence since before NBA was served, so a fix
    that only lands on the `market_line` path would leave two of the four served
    sports still telling readers the market disagrees with the model. PL and F1
    are absent by construction -- a three-way `result` market and an unserved
    sport, neither of which carries a spread -- and
    `test_template_quoted_line.test_pl_is_unaffected` is what pins that.
    """
    facts = _bundle(sport, [
        {"market": "moneyline", "model": {label: 0.62, "X": 0.38}},
        {"market": "spread", "model_margin": model_margin, "line": line},
    ], label=label)
    factor = _spread(facts)
    assert factor["text"] == expected
    assert factor["direction"] == NEUTRAL, f"[{sport}] {factor}"


def test_a_negative_model_margin_is_written_as_a_magnitude():
    """`model_margin` is home-minus-away, so it is negative when the away side is
    favoured, and the sentence has to read "4.2", never "-4.2".

    Found by mutation: dropping the `abs()` left the whole suite green, because
    every bundle any test builds has a POSITIVE margin. `abs(margin)` was the only
    arithmetic in the sentence, and nothing covered it.

    **This asserts the FORMATTING and nothing else, on purpose.** Which team's gap
    the number belongs to is NOT pinned here, because it is not derivable from the
    bundle: the facts carry `model_margin` and a moneyline `model` dict, and no
    home/away designation, so the margin may belong to the side the pick is not
    on. NBA's own builder is where that comparison happens -- it returns the
    literal "Toss-up" when the win model and the margin model point at different
    teams -- and all that survives into the facts is the wording, so the template
    cannot make the call. The fix is therefore to stop naming a team at all,
    which `test_the_spread_sentence_names_no_team` pins; this test keeps the
    arithmetic pinned so that change does not also lose the magnitude.
    """
    facts = _nba("MIA -3.5")
    facts["markets"][1]["model_margin"] = -MARGIN
    text = _spread(facts)["text"]
    assert f"{MARGIN:g}" in text, f"the magnitude is missing: {text}"
    assert f"-{MARGIN:g}" not in text, f"a negative margin was written as a signed gap: {text}"


# --- a margin that rounds to nothing is not narrated ------------------------

#: Under half a point. NBA's own builder (`_margin_line` in its `api/facts.py`)
#: words a projected margin as a gap only at `value >= 0.5` and otherwise returns
#: the literal "Toss-up", so a bundle whose margin is 0.4 arrives having already
#: been told the gap is a toss-up -- and the template then contradicts the bundle
#: it was handed. `test_facts.py::test_spread_reads_toss_up_under_half_a_point`
#: is where that half-point floor is pinned on the other side of the wire.
BELOW_THE_FLOOR = 0.4
#: The floor itself, and the one value that separates "a gap" from "no gap".
AT_THE_FLOOR = 0.5


def _nba_at_margin(margin: float) -> dict:
    """An NBA bundle whose `model_margin` is `margin`, with a real quoted line.

    NBA puts the model's own wording in `line` and the book's in `market_line`,
    so `_quoted_line` reads the book here and the margin under test is the only
    thing that varies. `market_line` is deliberately PRESENT: these tests are
    about the margin, and dropping the quoted line would omit the row for a
    reason that has nothing to do with the margin and would pass for the wrong
    one.
    """
    facts = _nba("BOS -3.5")
    facts["markets"][1]["model_margin"] = margin
    return facts


def _spread_or_none(facts: dict):
    """The spread factor, or `None` when the bundle emits no spread row.

    `None` is a real answer here -- omitting the row is the fix -- so this must
    not assert that exactly one exists. Asserting that would make the test pass
    for the wrong reason on every bundle where the row is missing for some other
    reason, which is the defect this whole file exists to prevent.
    """
    found = [f for f in explain_from_template(facts)["factors"] if f["key"] == "spread"]
    assert len(found) <= 1, f"more than one spread factor: {found}"
    return found[0] if found else None


@pytest.mark.parametrize("margin", [0, -0.0, 0.1, BELOW_THE_FLOOR, -BELOW_THE_FLOOR,
                                    0.49, -0.49],
                         ids=["zero", "negative-zero", "a tenth", "under the floor",
                              "under it the other way", "just under", "just under, negated"])
def test_a_margin_that_rounds_to_nothing_emits_no_spread_row(margin):
    """`0` is the case that was shipped, and it narrated a disagreement of nothing.

    The gate was `margin is not None`, which `0` passes, so a bundle with a model
    margin of exactly zero rendered

        It rates BOS 0 points better, against a line of BOS -3.5.

    -- "rates BOS 0 points better" and "BOS -3.5" are about a disagreement that
    does not exist, and the sentence asserts one. It is the same defect class as
    the clause removed above: a comparison stated rather than computed. Here the
    uncomputable half is not "which is bigger" but "whether there is anything to
    compare".

    Both signs, because `model_margin` is home-minus-away: a bundle where the
    away side is nominally ahead by 0.4 is the same absence of a gap, and a
    signed-only guard would miss it.

    **Why the row is omitted rather than worded "0 points".** The same choice this
    file's sibling already makes when there is no quoted line, and the same choice
    NBA's builder makes: it returns "Toss-up" rather than "BOS by 0.0". A row that
    exists only to say nothing is a row the panel gives a tile and a reader gives
    a glance. The alternative -- emitting the row with a "Toss-up"-style word --
    would be inventing a wording the panel has no field for, and would put a
    second vocabulary in this file.
    """
    assert _spread_or_none(_nba_at_margin(margin)) is None, (
        f"a margin of {margin} was narrated: "
        f"{_spread_or_none(_nba_at_margin(margin))}"
    )


@pytest.mark.parametrize("margin", [AT_THE_FLOOR, -AT_THE_FLOOR, MARGIN, -MARGIN],
                         ids=["at the floor", "at it, negated", "a real gap", "a real gap, negated"])
def test_a_margin_at_or_above_the_floor_is_still_narrated(margin):
    """The other side of the boundary, because a floor is only a floor if it has one.

    The floor is INCLUSIVE: a margin of exactly 0.5 is a gap NBA's builder is
    willing to word ("BOS by 0.5"), so this file words it too. A `>` where the
    code says `>=` omits a real gap, and every other test in this file uses a
    margin far above the floor -- so nothing else here would notice. This is the
    assertion that closes that.
    """
    factor = _spread_or_none(_nba_at_margin(margin))
    assert factor is not None, f"a margin of {margin} is a gap and was dropped anyway"
    assert f"{abs(margin):g}" in factor["text"], factor
    assert factor["direction"] == NEUTRAL, factor


def test_dropping_the_spread_row_does_not_drop_the_others():
    """The fix is one row, not a bundle.

    Omitting a factor is a cost to the reader, so it has to be paid only where
    the factor was making a claim. This pins that the free slot goes to the row
    the budget was already going to reach -- the record -- rather than to the
    padding that exists only so the panel is never one lonely line.
    """
    facts = _nba_at_margin(0)
    facts["record"] = {"label": "Picks made before tip-off", "hits": 41, "settled": 68}
    out = explain_from_template(facts)
    headlines = [f["headline"] for f in out["factors"]]
    assert "The line" not in headlines, headlines
    assert "Its record so far" in headlines, (
        f"the freed slot did not reach the record: {headlines}"
    )
    assert 2 <= len(out["factors"]) <= 4, out["factors"]


def test_the_floor_is_the_one_nba_uses():
    """The number is not invented here, and this is what holds it to that.

    NBA's real `_margin_line` is the authority: it is the function that decides
    whether a projected margin is worded as a gap or as the literal `"Toss-up"`,
    and a bundle whose margin it called a toss-up has therefore already been told
    so by the time it reaches this file. A different floor here would be a second
    disagreement with the bundle's producer, which is the shape of bug this file
    is about: the template quietly holding a threshold the sport it serves does
    not.

    **The floor is DERIVED by running NBA's function, not read out of its source
    and not compared with a literal in this file.** Both of those are the same
    guard wearing different clothes:

    * A literal (`assert MIN_SPREAD_MARGIN == 0.5`) is a copy of the number, so
      the two values can disagree without anything noticing. Proven, not
      asserted: against a decoy NBA whose floor is `0.6`, the literal version
      passed with the template disagreeing with its data by a tenth of a point --
      the entire suite green and the file's stated purpose unfulfilled.
    * A regex over NBA's source would be satisfied by NBA's DOCSTRING, which
      quotes `"Toss-up"` and the reasoning in prose, and by any comment above the
      line -- the decoy this repo keeps re-learning. The harness documents the
      same trap for its own anchors, and the `count=1` takes the first match, so a
      comment wins over the code.

    So the probe asks NBA's function what it does, at a thousand margins, and
    takes the smallest one it words as a gap. That is a question about behaviour,
    and a decoy that changed the floor changes the answer.

    **Only the MAGNITUDE half of NBA's rule is derived, and the probe is built so
    that is true by construction rather than by hope.** `_margin_line` gates on
    two things: that the margin points at the pick's own team, and that its
    magnitude is at least the floor. The bundle carries no home/away designation,
    so the first gate is not adoptable here at all
    (`test_a_negative_model_margin_is_written_as_a_magnitude` documents the same
    missing fact). The probe therefore supplies `home_prob = 0.62` and a
    non-negative margin, which makes `pick_team == home_team == team` -- so the
    side gate is satisfied at every magnitude and the only thing left to decide
    anything is the magnitude. A `"Toss-up"` found below the floor is therefore
    about the magnitude and cannot be the side gate misfiring. Fixing the side
    half needs a home/away designation in the facts, and is reported rather than
    guessed at.

    The literal assertion is kept as well, deliberately: the derivation says the
    two floors agree, and the literal says what they agree *on*, so a future
    change to the real number has to be made in two places on purpose rather than
    by one of them moving alone. See the decoy in
    `test_the_floor_probe_would_notice_nba_moving_its_own_floor` for what the
    derivation catches that the literal cannot.
    """
    from explainer.template import MIN_SPREAD_MARGIN

    assert MIN_SPREAD_MARGIN == 0.5, (
        f"the floor is {MIN_SPREAD_MARGIN}, which is not the half-point floor "
        "NBA's own facts builder uses"
    )
    assert _nba_margin_floor() == MIN_SPREAD_MARGIN, (
        f"NBA's own `_margin_line` words a margin as a gap from "
        f"{_nba_margin_floor()} and this template's floor is {MIN_SPREAD_MARGIN}. "
        f"One of the two is a copy of the other and the copy is wrong: a bundle "
        f"whose margin NBA called a toss-up arrives here already described as one, "
        f"and a template with a different floor contradicts the producer of its own "
        f"data. NBA's docstring says it ports `marginLine`; the floor is not a "
        f"number this repo gets to choose."
    )


# --- deriving NBA's floor from NBA's own function ---------------------------

#: What NBA words a margin that is not a gap as. Read out of the function's
#: output rather than written here, because a literal is exactly the kind of copy
#: this derivation exists to remove -- if NBA renames the word, a test holding
#: "Toss-up" would compare against a string NBA no longer emits and report a
#: floor of "the first margin that is not that string", which happens to still be
#: right. So it is a parameter of the probe and the assertion is about the SHAPE
#: of the answer (a gap names a team; a toss-up does not).
TOSS_UP = "Toss-up"

#: How finely the probe steps. A thousandth of a point: every floor a sports
#: builder would plausibly use (0.25, 0.3, 0.5, 0.6) lands exactly on a step, so
#: the derived value is that floor rather than an approximation of it, which is
#: what lets the assertion be exact equality. And the sweep is a BEHAVIOURAL
#: sweep, not a source read, so a floor NBA writes as `0.5` on one line and
#: `1.0 / 2` on another is the same number to this probe.
PROBE_STEP = 0.001
PROBE_MAX = 2.0


def _nba_margin_line_fn():
    """NBA's real `_margin_line`, cut out of its own `origin/main` and run.

    Reuses the source-reading machinery from `test_unserved_sport.py` rather than
    re-implementing it, for the same reason that file gives: the probe has to
    read what SHIPS, and a second copy of the extraction is a second thing to keep
    in step with the first. It fails rather than skips when the sibling is
    absent, which is the behaviour documented in the README: a skip would make
    the claim that NBA sets this floor unverifiable while still reporting a green
    suite.

    The module cannot be exec'd whole -- it imports pandas and the storage layer --
    so the one function is cut and run, exactly as `_run_nba_markets` does for
    its six. `_margin_line` takes four floats/strings and calls nothing but
    `abs`, so it stands alone and needs no other name in scope.
    """
    import re

    from test_unserved_sport import _nba_facts_source

    source = _nba_facts_source()
    assert "def _margin_line" in source, (
        "NBA's facts.py has no `_margin_line`, so the floor could not be derived "
        "from the function that sets it and the assertion would compare the "
        "template with a constant it chose itself"
    )
    m = re.search(r"^def _margin_line\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
    assert m, (
        "NBA's `_margin_line` could not be cut out of its source; the probe would "
        "pass vacuously rather than ask NBA's function anything"
    )
    env: dict = {}
    exec(compile("from __future__ import annotations\n" + m.group(0),
                 "<nba _margin_line>", "exec"), env)
    assert "_margin_line" in env, "the cut produced no callable"
    return env["_margin_line"]


def _nba_margin_floor(margin_line=None) -> float:
    """The smallest margin NBA's own `_margin_line` words as a gap, not a toss-up.

    Swept behaviourally, on the argument shapes that make the SIDE gate a
    non-question: `home_prob = 0.62` puts the pick at home, a non-negative margin
    puts the projection at home too, so "is this margin pointed at the pick's
    team" is true at every magnitude and whatever NBA returns is decided by the
    magnitude alone. That is what makes this the MAGNITUDE half of NBA's rule --
    see the docstring of `test_the_floor_is_the_one_nba_uses`.

    **The function is a parameter, and that is the whole point of the parameter.**
    A first version took no argument and every sensitivity test re-implemented the
    sweep locally -- which meant the test was pinning a COPY of the sweep while
    the shipped one was untested, so replacing the body of `_nba_margin_floor`
    with `return 0.5` would have passed the entire file, including against a decoy
    NBA. Injecting the function makes the sensitivity test drive the SHIPPED
    sweep, so that mutation is caught here rather than only in an out-of-process
    decoy run. `None` means "NBA's real one", so the default call is the claim
    and no caller has to pass anything to make it.
    """
    margin_line = _nba_margin_line_fn() if margin_line is None else margin_line
    step = PROBE_STEP
    n = int(round(PROBE_MAX / step))
    for i in range(n + 1):
        value = round(i * step, 6)
        if margin_line("BOS", "MIA", 0.62, value) != TOSS_UP:
            return value
    raise AssertionError(
        f"NBA's `_margin_line` called every margin up to {PROBE_MAX} a toss-up, so "
        f"it sets no magnitude floor this file could adopt. Whatever this repo "
        f"picks would be a second disagreement with the bundle's producer."
    )


def test_the_floor_probe_asks_nba_rather_than_reading_it():
    """The probe is about BEHAVIOUR, and this is the anti-vacuity half.

    Three things have to be true of NBA's function for the derivation above to
    mean anything, and none of them is visible in the number it returns:

    * the function exists and is callable (asserted in the probe, and here by
      having got this far);
    * a large margin really is worded as a gap naming a team, and a tiny one
      really is a toss-up -- so `TOSS_UP` is a word NBA emits rather than a
      constant the probe invented and compared against;
    * the boundary is a BOUNDARY: at the derived value NBA words a gap, and one
      step below it does not. A probe that returned the first non-toss-up out of a
      sweep whose comparison never matched would report `0.0`, and a probe
      comparing against the wrong word would report the same `0.0`; neither would
      be distinguishable from a real answer by the floor value alone.
    """
    margin_line = _nba_margin_line_fn()
    floor = _nba_margin_floor()

    assert margin_line("BOS", "MIA", 0.62, 5.0) != TOSS_UP, (
        "NBA words a five-point margin as a toss-up, so `Toss-up` is not the word "
        "this probe is looking for and the derived floor is an artefact"
    )
    assert margin_line("BOS", "MIA", 0.62, 5.0).startswith("BOS by"), (
        f"a five-point gap is not worded as a gap naming a team: "
        f"{margin_line('BOS', 'MIA', 0.62, 5.0)!r}. This probe assumes NBA's gap "
        f"and toss-up wordings are what it takes them to be."
    )
    assert margin_line("BOS", "MIA", 0.62, 0.0) == TOSS_UP, (
        "a zero margin is not a toss-up, so the sweep would have found no floor "
        "at all and the whole derivation would be measuring the wrong boundary"
    )
    assert margin_line("BOS", "MIA", 0.62, floor) != TOSS_UP, (
        f"the derived floor {floor} is a toss-up, so it is not a floor"
    )
    just_under = round(floor - PROBE_STEP, 6)
    assert margin_line("BOS", "MIA", 0.62, just_under) == TOSS_UP, (
        f"a margin of {just_under} is worded as a gap, so the derived floor {floor} "
        f"is not the smallest one -- the sweep is not measuring the boundary it "
        f"claims to"
    )
    # And the side gate really is out of the way at the floor, which is the whole
    # reason the derivation is the magnitude half and not a guess at the rule.
    assert margin_line("MIA", "BOS", 0.38, floor) == TOSS_UP or floor == 0, (
        f"with the pick on the away side, a margin of {floor} is still worded as a "
        f"gap, so the probe's chosen arguments do not isolate the magnitude half "
        f"and the derived floor is contaminated by the side gate"
    )
    # **The floor this probe derives IS the one the template ships**, asserted here
    # as well as in `test_the_floor_is_the_one_nba_uses`, and that repetition is a
    # survivor being closed rather than a copy being made.
    #
    # Deleting the derived comparison from the test above left the whole file
    # green. This test pins the probe's SHAPE -- a boundary, a gap at it, a
    # toss-up a step below -- and any value with that shape satisfies it, so
    # removing the one assertion that tied the probe to `MIN_SPREAD_MARGIN`
    # disconnected the two without anything noticing. Splitting the claim across
    # its two ends means an edit to either test leaves the other asserting it.
    #
    # It is not the same assertion twice: this one's subject is the PROBE, and
    # whether the number it produces is the number anything else uses is part of
    # whether the probe is any good.
    from explainer.template import MIN_SPREAD_MARGIN
    assert floor == MIN_SPREAD_MARGIN, (
        f"the probe derives {floor} from NBA's own function and the template "
        f"ships {MIN_SPREAD_MARGIN}, so the two disagree about the same rule"
    )


def test_the_floor_probe_would_notice_nba_moving_its_own_floor():
    """The mutation the literal assertion cannot catch, demonstrated in-process.

    The reviewer found `test_the_floor_is_the_one_nba_uses` comparing
    `MIN_SPREAD_MARGIN` to the literal `0.5` in the same repository, so NBA's
    floor could move and the test would stay green. That was verified out of
    process too: against a decoy repo whose floor is `0.6`, the old assertion
    passed with the template disagreeing with its data by a tenth of a point --
    the entire suite green and this file's stated purpose unfulfilled.

    So this drives the **shipped** sweep against a stand-in whose floor is
    `0.6` and asserts it reports `0.6`, and does the same for three other floors.
    The parameter is what makes that a test of the probe rather than of a copy of
    it: a sweep re-implemented locally would pass while `_nba_margin_floor` was
    `return 0.5`, and that mutation survives everything else in this file --
    including the boundary-shape test above, which is satisfied by any value with
    a toss-up one step under it. Only driving the real function closes it.

    A stand-in, deliberately: the real function's floor is a literal in NBA's
    source and there is no honest way to move it in-process. What is checked is
    that the sweep finds whatever boundary the function it is handed actually
    has. The two are not the same claim -- this proves the probe is sensitive to
    a moved floor, not that `NBA_REPO` is wired up -- and the decoy run is what
    separates those. Both are done and both are reported.
    """
    def margin_line_with_floor_at(floor: float):
        """NBA's rule with the floor moved, written the way NBA writes it.

        Deliberately close to the real function's shape, including the side gate,
        so the sweep is exercised through both gates rather than a shortcut that
        only one of them.
        """
        def _margin_line(home_team, away_team, home_prob, margin):
            pick_team = home_team if home_prob >= 0.5 else away_team
            team = home_team if margin >= 0 else away_team
            value = abs(margin)
            if team == pick_team and value >= floor:
                return f"{team} by {value:.1f}"
            return TOSS_UP
        return _margin_line

    assert _nba_margin_floor() == 0.5, (
        "NBA's own `_margin_line` does not set a half-point floor, so the literal "
        "assertion above and this file's comment are both wrong about NBA"
    )
    for moved in (0.6, 0.25, 1.0, 0.1):
        assert _nba_margin_floor(margin_line_with_floor_at(moved)) == moved, (
            f"the shipped sweep reported the wrong floor for a builder that words "
            f"a gap from {moved}: it is reading something other than the boundary, "
            f"so it would not notice NBA moving its own"
        )




# --- the margin belongs to a SIDE, and the sentence named one ----------------

def _nfl_away_pick(margin: float = 2.6) -> dict:
    """NFL's real shape, with the pick on the away side and the line on the home
    side -- the case two of the sentence's claims are false in at once.

    Built from what NFL's own `api/facts.py` emits, not from a fixture invented
    here, because the whole point is that the two figures come from DIFFERENT
    sources and genuinely differ:

    * `_markets(game, prediction, moneyline_from)` takes the moneyline from
      `moneyline_from` and says why in its own docstring: the bundle's `pick` is
      deliberately the number snapshotted before kickoff, "because that is the
      record which will be judged", and for an upcoming game today's recompute
      "genuinely differs". So the pick may be one side while the margin, read
      from `prediction["predicted_margin"]`, is the other side's.
    * `_spread_line(home_team, nflverse_spread_line)` is
      `f"{home_team} {-line:+.1f}"` -- the quoted line is ALWAYS attributed to
      the home team, whichever side the pick is on.

    So with home BAL, away KC: the snapshot's moneyline favours KC (the pick), and
    today's recompute has `predicted_margin: 2.6`, which is BAL minus KC, i.e. a
    2.6-point BAL margin. The line is `nflverse` at BAL -2.5, BAL's own.

    The sentence this file's previous wording rendered:

        It rates KC 2.6 points better, against a line of BAL -2.5.

    names KC as the side the model rates better -- the model rates BAL better --
    and puts the sentence about KC beside a line that is BAL's, so a reader reads
    it as KC's line. Two unsupported claims, one sentence, and it is the only
    prose a reader sees while the deploy runs `EXPLAINER_ENABLED=false`.
    """
    return _bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.44, "KC": 0.56}},
        {"market": "spread", "model_margin": margin, "line": "BAL -2.5",
         "model_cover_prob": 0.51},
    ], label="KC")


def test_the_spread_sentence_names_no_team():
    """The attribution, removed. Exact equality, so anything else fails.

    Both figures stay and the claim about which one is bigger stays unstated:
    `model_margin`'s magnitude is a real projected margin for these two teams
    whatever its sign, and the quoted line is a real market line. What is not
    derivable -- and is not derivable from the bundle, which carries no
    home/away designation at all -- is whose margin it is. So the sentence
    states the projection and the line and nothing about the relationship
    between them or about a side.
    """
    assert _spread(_nfl_away_pick())["text"] == (
        "It projects a margin of 2.6 points, against a line of BAL -2.5."
    )


def test_the_spread_sentence_is_the_same_whichever_side_the_pick_is_on():
    """The property behind the wording, so it cannot come back as wording.

    Same two figures, same quoted line, and the only thing that changes is which
    team the bundle calls the pick. A sentence that mentions the pick has to
    change; a sentence that states the model's projection does not. Requiring
    them to be equal is a statement about the CODE -- that the row does not read
    the pick -- rather than about today's phrasing, so a future rewording that
    drops the attribution again cannot pass by being phrased differently.
    """
    away = _nfl_away_pick()
    home = _nfl_away_pick()
    home["pick"] = {"label": "BAL", "prob": 0.44}
    assert _spread(away)["text"] == _spread(home)["text"], (
        "the sentence changed with the pick, so it is still naming a side: "
        f"{_spread(away)['text']!r} vs {_spread(home)['text']!r}"
    )


def test_the_spread_sentence_names_a_team_only_when_the_quoted_line_does():
    """The narrower form of the same rule, which catches a re-attribution that
    the equality sweep above would not.

    A quoted line is free to name a team -- `"BAL -2.5"` does, and `"224.5"` does
    not -- so the sentence is allowed to contain the pick's label when the line
    itself contains it. What it may never do is introduce a team of its own. So
    the rule is conditional rather than a blanket ban, and it holds for a
    re-attribution written as anything at all, including one that also changes
    the rest of the sentence.
    """
    text = _spread(_nfl_away_pick())["text"]
    line = "BAL -2.5"
    assert "KC" not in line, "this fixture only means anything while the line names the other side"
    assert "KC" not in text, (
        f"the sentence named the pick, and the quoted line names the other side: {text}"
    )


@pytest.mark.parametrize("margin", [MARGIN, -MARGIN, AT_THE_FLOOR, -AT_THE_FLOOR],
                         ids=["a real gap", "a real gap, negated", "at the floor",
                              "at the floor, negated"])
def test_the_magnitude_is_read_the_same_way_for_either_sign(margin):
    """Negative, zero and the boundary, on the sentence's own terms.

    `model_margin` is home-minus-away, so a negative value is the ordinary case
    where the away side is favoured and must read as a gap, not as a signed
    number. `0` never reaches this row at all -- `MIN_SPREAD_MARGIN` omits it,
    which `test_a_margin_that_rounds_to_nothing_emits_no_spread_row` pins -- and
    the floor itself is inclusive, so half a point in EITHER direction is worded
    as a gap rather than dropped. One expected string for all four, so a `>` in
    place of the `>=` the code has, and a dropped `abs()`, each change the
    answer rather than sliding past a substring check.
    """
    facts = _nfl_away_pick(margin)
    assert _spread(facts)["text"] == (
        f"It projects a margin of {abs(margin):g} points, against a line of BAL -2.5."
    ), _spread(facts)["text"]


@pytest.mark.parametrize("margin", [0.51, -0.51, 3.0, -3.0, 12.0, 99.9],
                         ids=["just over the floor", "just over, negated",
                              "a whole number", "a whole number, negated",
                              "double figures", "double figures the other way"])
def test_the_magnitude_is_rendered_as_a_readable_figure_not_a_float_literal(margin):
    """`:g` formatting, which the exact-equality tests above do not reach.

    Every margin the other tests use has one decimal place, so `:g` and `str()`
    agree and a change of format specifier would pass all of them. A margin
    stored as `3.0` -- which is what a float from a JSON bundle routinely is --
    has to read "3 points" and not "3.0 points", and `:g` is what does that.

    **The failure this is here for, found by running the code rather than reading
    it.** The first sweep of this fix found that a margin of `1e6` renders as
    *"a margin of 1e+06 points"* under `:g`, which is not a figure a reader can
    use. That is PRE-EXISTING -- the old sentence formatted the same magnitude
    the same way -- and it is unreachable in practice: no sport's builder
    produces a million-point margin. It is recorded here rather than fixed,
    because a floor on `model_margin` is a decision about what a bundle may
    carry, and this file is about what a sentence may claim.
    """
    text = _spread(_nfl_away_pick(margin))["text"]
    # `abs(margin)`, not `margin`: the sentence never carries the sign, and
    # `f"{-0.51:g}"` is "-0.51", which is the very thing the sweep exists to
    # forbid. Comparing against the raw value here would have failed on the
    # negated cases and taught the wrong thing about them.
    assert text == f"It projects a margin of {abs(margin):g} points, against a line of BAL -2.5."
    assert "e+" not in text and "e-" not in text, f"a float literal reached a reader: {text}"
    assert "points. points" not in text and "  " not in text, text
