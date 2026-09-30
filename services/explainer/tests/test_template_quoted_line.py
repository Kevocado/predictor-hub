"""The quoted line is the MARKET's, whatever the sport calls the key.

The template writes two sentences that both attribute a line to the market:

    "It rates BOS 4.2 points better, against a line of BOS by 4.2."

and

    "It projects 226.5 against a line of 224.5."

Read across the five sports' `/facts` builders, the key `line` means **two
different things**:

| market        | `line`                        | `market_line`          |
|---------------|-------------------------------|------------------------|
| NFL, CFB      | the MARKET's line, `"BAL -2.5"` | absent               |
| NBA           | the MODEL's own wording, `"BOS by 4.2"` or `"Toss-up"` | the market's, `"BOS -3.5"` |
| PL            | absent (three-way result)     | absent                 |
| F1            | absent (unserved)             | absent                 |

So reading `line` as the market's is right for two sports and wrong for one, and
for NBA it produces the model compared with itself — which is the exact failure
`PRODUCT.md`'s "a pick shown without knowing when it was made" and the F1 refusal
both exist to prevent. Reached for the first time here, because NBA's template
never ran before this change.

**And it is silent.** The template gates the total factor on `line is not None`,
and NBA's total market has no `line`, so the factor is dropped without a word. A
reader sees a shorter explanation and has no way to know a figure was withheld.
"""
from explainer.template import _quoted_line, explain_from_template

UNIT = {"nfl": "points", "cfb": "points", "nba": "points", "pl": "goals"}


def bundle(sport, markets, **over):
    base = {
        "sport": sport, "id": "g1", "title": "PHI at BOS",
        "starts_at": "2026-10-20T00:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "BOS", "prob": 0.62},
        "markets": markets, "drivers": [], "context": {}, "players": [],
        "record": {"label": "Picks made before tip-off", "hits": 30, "settled": 50},
        "result": None,
    }
    base.update(over)
    return base


def factor(body, key):
    return next((f for f in body["factors"] if f["key"] == key), None)


# --- the bug, in the shapes each sport actually emits ----------------------

def test_an_nba_spread_does_not_quote_the_model_back_at_itself():
    """The failure, verbatim from the real template output before the fix.

    "against a line of BOS by 4.2" -- the sentence claims a disagreement with the
    market and then quotes the model. The market's actual line is in `market_line`.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "spread", "model_margin": 4.2,
         "line": "BOS by 4.2", "market_line": "BOS -3.5"},
        {"market": "total", "model_total": 226.5, "market_line": "224.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "BOS -3.5" in text, f"the market's line is missing: {text}"
    assert "BOS by 4.2" not in text, f"the model is quoted as the market: {text}"


def test_a_toss_up_is_not_presented_as_a_market_line():
    """NBA's `_margin_line` returns the literal "Toss-up" when the margin rounds to
    nothing or points at a different team than the moneyline does. Rendered as
    "against a line of Toss-up" it is not a weak sentence, it is a sentence with no
    meaning in it -- and `PRODUCT.md` says uncertainty is shown, not dressed up.

    **Both of the ways NBA produces "Toss-up", because the margin floor closed one
    of them and the other is still reachable.** A margin under half a point now
    omits the row outright, so the leak this test was written for is unreachable
    by that route -- and the second assertion below could not be satisfied, which
    is why it is gone rather than kept in weakened form. NBA also says "Toss-up"
    when the margin is comfortably large but points at the team the moneyline
    does not favour, and the template cannot check that (no home/away designation
    in the bundle), so the row IS still emitted there. That is the case that can
    still leak, so it is the case that is asserted.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.51, "PHI": 0.49}},
        {"market": "spread", "model_margin": 4.2, "line": "Toss-up", "market_line": "BOS -0.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "Toss-up" not in text, f"the model's own wording leaked into the prose: {text}"
    assert "BOS -0.5" in text, text


def test_a_toss_up_margin_under_the_floor_narrates_nothing_at_all():
    """The other half of the same wording, now settled by omission rather than by
    reading the right key.

    `model_margin: 0.2` with `line: "Toss-up"` used to be the sharpest version of
    this defect: the model says the game is a coin flip, and the panel said "It
    rates BOS 0.2 points better". Under `MIN_SPREAD_MARGIN` the row is omitted, so
    there is no sentence in which "Toss-up" could have leaked and no
    sub-half-point gap narrated as one.

    Asserting the ABSENCE rather than the absence of a word, because the word is
    what the previous fix removed and a test that only greps for it would go green
    if the row came back worded differently -- which is the defect, not the
    wording.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.51, "PHI": 0.49}},
        {"market": "spread", "model_margin": 0.2, "line": "Toss-up", "market_line": "BOS -0.5"},
    ]))
    assert factor(body, "spread") is None, (
        f"a sub-half-point margin was still narrated: {body['factors']}"
    )
    assert "Toss-up" not in " ".join(f["text"] for f in body["factors"]), body["factors"]


def test_nbas_total_factor_is_not_silently_dropped():
    """NBA's total market has no `line` at all, so the old gate
    (`total_market.get("line") is not None`) removed the factor without a word.

    The clause that matters is not "is the factor present" -- a total with no line
    anywhere legitimately has nothing to compare against -- but that a total WITH a
    quoted line is never dropped. Before the fix this was the second of the two
    ways NBA rendered short.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "total", "model_total": 226.5, "market_line": "224.5"},
    ]))
    f = factor(body, "total")
    assert f is not None, f"the total factor was dropped: {body['factors']}"
    assert "224.5" in f["text"], f["text"]


def test_a_total_with_no_quoted_line_is_still_omitted():
    """The other half. NBA's total also appears with no line when there is no
    quoted market total, and there is nothing to compare 226.5 against. Emitting
    "It projects 226.5" on its own would be a number with no disagreement
    attached, which is the same emptiness in a different shape.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "total", "model_total": 226.5},
    ]))
    assert factor(body, "total") is None, "a total with nothing to compare against should not be narrated"


# --- the three sports that already work must not change -------------------

def test_nfl_keeps_reading_its_line_key_as_the_market():
    """NFL and CFB put the MARKET's line in `line` and have no `market_line` at
    all, so the fix has to prefer `market_line` *without* requiring it. This is the
    case that would break first if the fix simply demanded the new key.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
        {"market": "total", "model_total": 47.8, "line": "44.5"},
    ]))
    assert "BAL -2.5" in factor(body, "spread")["text"]
    assert "44.5" in factor(body, "total")["text"]


def test_a_sport_with_both_keys_prefers_the_quoted_one():
    """If a sport ever fills both, the quoted line is the one a reader can check
    against a book, and the model's own wording is not. Pinned so the precedence
    is a decision rather than an accident of key order.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL by 3.4", "market_line": "BAL -2.5"},
    ]))
    text = factor(body, "spread")["text"]
    assert "BAL -2.5" in text, text
    assert "BAL by 3.4" not in text, text


def test_pl_is_unaffected():
    """PL has a three-way `result` market and a `total_goals` market with no line,
    so neither factor fires today and must not start firing on a fix meant for NBA.
    """
    body = explain_from_template(bundle("pl", [
        {"market": "result", "model": {"Arsenal": 0.48, "Draw": 0.26, "Chelsea": 0.26}},
        {"market": "total_goals", "model_total": 2.7},
    ]))
    assert factor(body, "spread") is None
    assert factor(body, "total") is None


# --- a regression this fix caused, and the reason it is pinned ------------

def test_a_numeric_total_line_is_still_read():
    """A total's `line` is a FLOAT, not a worded string.

    The first version of `_quoted_line` type-checked for `str`, and dropped the
    total factor for every sport -- NFL, CFB, all of them -- because 45.5 is not
    a string. `test_template_covers_markets_and_the_record` caught it, but that is
    luck rather than design: the suite happened to have an assertion on the
    total's figure.

    Pinned here so the narrowing cannot come back, and so the asymmetry between
    the two markets is written down where the helper is: a spread's line is
    wording ("BAL -2.5", "BOS by 4.2"), a total's is a number.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "total", "model_total": 47.8, "line": 45.5},
    ]))
    f = factor(body, "total")
    assert f is not None, f"the total factor was dropped for a numeric line: {body['factors']}"
    assert "45.5" in f["text"], f["text"]


def test_a_boolean_line_is_not_a_line():
    """`True` is truthy, so without the bool guard it renders "against a line of
    True" -- and a sentence with `True` in it reads as a bug report, not a line.

    `_num()` four lines away in the same module excludes bools explicitly for the
    same reason, so the asymmetry was visible in the file; it just had no test.
    Found by mutation: dropping `isinstance(value, bool)` left the suite green.
    """
    from explainer.template import DEFAULT_MARKET_LINE_KEY

    assert _quoted_line({"market": "spread", "line": True}, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line({"market": "spread", "market_line": False, "line": "BOS -3.5"},
                         DEFAULT_MARKET_LINE_KEY) == "BOS -3.5", (
        "a boolean quoted line must fall through to the sport's own key"
    )


def test_an_empty_line_is_treated_as_no_line():
    """`""` and `None` mean there is no line to quote. A factor built on one would
    read "against a line of ." — and `0` is not a line either, so it is not
    rendered as one."""
    from explainer.template import DEFAULT_MARKET_LINE_KEY

    assert _quoted_line({"market": "total", "line": ""}, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line({"market": "total", "line": None}, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line({"market": "total", "line": 0}, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line(None, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line({}, DEFAULT_MARKET_LINE_KEY) is None


def test_a_whitespace_only_line_is_treated_as_no_line():
    """Why `_quoted_line` strips before it tests, rather than testing first.

    The strip is the only reason a blank-looking line is rejected. Without it,
    `"   "` is truthy and the factor renders *"against a line of    ."* -- a
    sentence with nothing in it, which is the same emptiness the total-market
    guard above exists to prevent, reached through a different key.

    The earlier loop carried a second check for `None` and `""` alongside this
    one. It was dead, and a mutation check reported it as covered, because
    deleting it changed nothing -- which is the failure mode this whole file
    exists to catch, sitting inside the fix itself. So this pins the one check
    that is load-bearing.
    """
    from explainer.template import DEFAULT_MARKET_LINE_KEY

    assert _quoted_line({"market": "total", "line": "   "}, DEFAULT_MARKET_LINE_KEY) is None
    assert _quoted_line({"market": "spread", "market_line": "  ", "line": "BOS -3.5"},
                         DEFAULT_MARKET_LINE_KEY) == "BOS -3.5", (
        "a blank quoted line must fall through to the sport's own key, not end the search"
    )


def test_nbas_rebuilt_pick_says_tip_off_not_kickoff():
    """The panel says "tip-off" for NBA everywhere else, so this sentence must too.

    A rebuilt pick renders "This pick was rebuilt after {_START.get(sport, 'kickoff')}",
    and `_START` had no NBA entry -- so on an NBA game the panel read
    "rebuilt after kickoff" directly above a record labelled "picks made before
    tip-off". One screen, two words for the same moment, and only one of them
    right for the sport.
    """
    body = explain_from_template(bundle(
        "nba", [{"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}}],
        pick_timing="rebuilt"))
    text = " ".join(f["text"] for f in body["factors"])
    assert "tip-off" in text, text
    assert "kickoff" not in text, f"NBA must not be told in football's word: {text}"


# --- the gap the first version of this fix left open -----------------------

def test_nbas_no_quote_state_does_not_render_the_models_wording_as_a_line():
    """The case that actually ships, and the one the first fix did not cover.

    NBA's `_markets` sets `market_line` only `if quoted is not None` -- there is
    no pre-tip market row. So in that state the spread carries `line` (the
    MODEL's wording, `"Toss-up"`) and **no `market_line` at all**, and the total
    carries no line whatsoever.

    `_quoted_line` preferred `market_line` and fell back to `line`, which is
    correct for NFL and CFB and wrong for NBA, where `line` is never a market
    line. So the fallback resurrected the exact sentence the fix exists to
    remove, from the real builder rather than a fixture that always supplied a
    quote:

        It rates BOS 0.2 points better, against a line of Toss-up. That is the
        market asking for more than the model thinks the gap is worth.

    The trailing clause is the worse half: it makes a claim about the market
    derived from a figure the model produced.

    This is the state NBA is in most of the time, and the deploy runs
    `EXPLAINER_ENABLED=false`, so this template is the only thing a reader sees.
    A precedence rule cannot fix it -- for NBA the fallback key is not merely
    lower-priority, it means something else entirely.
    """
    body = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.51, "MIA": 0.49}},
        # exactly what NBA's `_markets` returns with no pre-tip market row
        {"market": "spread", "model_margin": 0.2, "line": "Toss-up"},
        {"market": "total", "model_total": 226.5},
    ]))
    # The factor is OMITTED, not reworded. There is no market line to disagree
    # with, and "It rates BOS 0.2 points better" on its own is a number with no
    # disagreement attached -- the same emptiness as a total with no line, which
    # `test_a_total_with_no_quoted_line_is_still_omitted` already rules out.
    assert factor(body, "spread") is None, (
        "a spread with no market line must be omitted rather than narrated: "
        f"{factor(body, 'spread')}"
    )
    rendered = " ".join(f["text"] for f in body["factors"])
    assert "Toss-up" not in rendered, f"the model's own wording is shown: {rendered}"
    assert "market asking" not in rendered, (
        f"a claim about the market is derived from the model's own figure: {rendered}"
    )
    # And the total, which also has no quoted line in this state, likewise.
    assert factor(body, "total") is None, f"the total has no line either: {body['factors']}"


def test_the_fallback_key_is_never_a_models_wording_whatever_it_says():
    """`line` is a spread's market line in NFL and CFB and the MODEL's wording in
    NBA. `_quoted_line` is told which is which per sport rather than inferring it
    from key order, because no precedence rule can distinguish "lower-priority
    source of the same thing" from "a different thing that happens to share a
    name".

    NFL and CFB keep working, which is the other half of the obligation: if the
    fix were simply "never read `line`", their spreads would lose their factor
    and their sites would silently show less.
    """
    nfl = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
        {"market": "total", "model_total": 47.8, "line": 45.5},
    ]))
    assert "BAL -2.5" in factor(nfl, "spread")["text"]
    assert "45.5" in factor(nfl, "total")["text"]

    # And the same shape under a sport whose `line` means the other thing gets
    # nothing, rather than the wrong sentence.
    nba = explain_from_template(bundle("nba", [
        {"market": "moneyline", "model": {"BOS": 0.62, "PHI": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BOS by 3.4"},
    ]))
    assert factor(nba, "spread") is None, (
        "a spread whose only line is the model's own wording must not be narrated "
        f"as a disagreement with anyone: {factor(nba, 'spread')}"
    )


# --- two behaviour changes the review found were silent --------------------

def test_a_padded_line_renders_without_its_padding():
    """A line with padding around it now renders trimmed.

    Silent, and an improvement: before, `"  BAL -2.5  "` rendered as *"against a
    line of   BAL -2.5  "* with the padding carried into the sentence. Real data
    is `f"{home_team} {-line:+.1f}"`, which has no padding, so this is inert in
    production -- which is exactly why it needed a test. An inert improvement is
    the change most likely to be reverted by someone who thinks it is a
    regression.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "  BAL -2.5  "},
    ]))
    text = factor(body, "spread")["text"]
    assert "against a line of BAL -2.5." in text, text
    assert "  BAL" not in text, f"padding leaked into the sentence: {text}"


def test_a_zero_total_line_drops_the_factor_rather_than_quoting_zero():
    """A total whose `line` is `0` used to render *"It projects 47.8 points against
    a line of 0"* and is now omitted.

    Silent, and an improvement: a total of 0 is not a line anyone is quoted
    against, and the old sentence read as though it were. The general rule is
    already asserted in `test_an_empty_line_is_treated_as_no_line`; this pins the
    numeric case specifically, because `0` is falsy in a way `""` is not and the
    two took different paths through an earlier version of the helper.
    """
    body = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "total", "model_total": 47.8, "line": 0},
    ]))
    assert factor(body, "total") is None, (
        f"a total with line=0 must not be narrated as 'against a line of 0': "
        f"{factor(body, 'total')}"
    )
    # And a total with a REAL zero-ish line still renders, so the rule is not
    # "drop anything small".
    body2 = explain_from_template(bundle("nfl", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "total", "model_total": 47.8, "line": 0.5},
    ]))
    assert "0.5" in factor(body2, "total")["text"]


def test_an_nba_rebuilt_pick_with_all_three_markets_loses_the_record():
    """NBA's factor budget is now full, and this is the displacement.

    A REBUILT pick adds a `context` factor, so moneyline + spread + total +
    context + record is five candidates against `MAX_FACTORS = 4`. The record is
    what gets dropped.

    Two corrections to how this was first written, both found by running it
    rather than reasoning about it. A *final but not rebuilt* NBA game produces
    exactly four factors and loses nothing -- so "a final game renders five" is
    wrong, and the review that suggested it was wrong for the same reason I would
    have been: the fifth factor is the rebuilt note, not the final-score one. And
    the `context` factor sorts FIRST, not last, so the record is displaced by
    appearing after it rather than by being appended.

    Worth stating plainly: the panel's record strip is NOT this factor. A reader
    still sees their record; what is lost is the record *sentence* inside the
    explanation.
    """
    markets = [
        {"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
        {"market": "spread", "model_margin": 4.2,
         "line": "BOS by 4.2", "market_line": "BOS -3.5"},
        {"market": "total", "model_total": 226.5, "market_line": "224.5"},
    ]
    rebuilt = explain_from_template(bundle(
        "nba", markets, pick_timing="rebuilt", status="final",
        result={"pick_won": True}))
    keys = [f["key"] for f in rebuilt["factors"]]

    assert len(keys) == 4, f"MAX_FACTORS is not being applied: {keys}"
    assert keys == ["context", "moneyline", "spread", "total"], keys
    assert "record" not in keys, (
        f"expected the record sentence to be the one dropped for a rebuilt NBA pick "
        f"with all three markets: {keys}"
    )

    # And the control: the same game NOT rebuilt fits, so the displacement is
    # caused by the rebuilt note rather than by NBA's three markets alone.
    plain = explain_from_template(bundle(
        "nba", markets, status="final", result={"pick_won": True}))
    plain_keys = [f["key"] for f in plain["factors"]]
    assert "record" in plain_keys, (
        f"a non-rebuilt NBA game should keep its record sentence: {plain_keys}"
    )


# --- the moment each sport names the start of a game ------------------------

def test_every_served_sport_names_the_moment_in_its_own_word():
    """A rebuilt pick renders "This pick was rebuilt after {moment}".

    Only NBA's word was pinned, and swapping the `f1` and `pl` entries survived
    with the whole suite green. That is the same shape as every other gap this
    file started with: one sport's row tested, the rest assumed.

    The list is derived from `SERVED_SPORTS`, so a newly served sport is covered
    the moment it is added rather than the moment someone remembers -- which is
    what this test did to itself when F1 was served: it failed on its own table
    and the fix was the entry, not the check.

    **F1 is in the table now, and its word is asserted twice over.** It was not
    when this was written, because F1 was refused and `_START["f1"]` was
    unreachable; the swap row the mutcheck harness carries would have been silent
    then, and the table would have had nothing to compare. The separate
    `test_f1s_moment_is_the_session_because_that_is_the_word_f1_uses` below reads
    the constant directly, so one guard watches the rendered sentence for a sport
    whose shape is F1's and the other watches the word in the table.
    """
    from explainer.config import SERVED_SPORTS

    expected = {
        "pl": "kickoff",      # a league match kicks off
        "nfl": "kickoff",
        "cfb": "kickoff",
        "nba": "tip-off",     # not a kickoff, and the panel says so elsewhere too
        "f1": "the session started",   # a race weekend has sessions, and "kickoff" is a lie
    }
    assert set(expected) == set(SERVED_SPORTS), (
        f"this test's table is out of step with SERVED_SPORTS: "
        f"{sorted(set(expected) ^ set(SERVED_SPORTS))}"
    )
    for sport, word in expected.items():
        body = explain_from_template(bundle(
            sport, [{"market": "moneyline", "model": {"A": 0.6, "B": 0.4}}],
            pick_timing="rebuilt"))
        text = " ".join(f["text"] for f in body["factors"])
        assert f"after {word}" in text, f"[{sport}] {text}"


def test_f1s_moment_is_the_session_because_that_is_the_word_f1_uses():
    """`_START["f1"]` was **unreachable** when this was written -- F1 was refused
    at the edge, so the template never ran for it -- and it is now the live path,
    because F1 serves.

    Not an oversight then, and not one now. The default for an unlisted sport is
    "kickoff", which is the wrong word for a Formula 1 session, so the entry was
    the only thing standing between "F1 is un-refused" and "F1 says 'rebuilt
    after kickoff'". Asserting a table's contents is legitimate when the row
    exists precisely for a future caller; leaving it unpinned is how it becomes a
    wrong word nobody notices.

    **It reads the constant rather than a rendered sentence, so it is the witness
    that does not need F1 to be served.** The table above renders a sport's word
    only for sports in `SERVED_SPORTS`, so un-serving F1 -- a reversal nobody has
    promised will not happen twice -- would leave this row unpinned and
    `tests/test_f1_served.py` would be the only thing saying the word matters.
    A test whose subject is a config list is a test that goes away with the
    config; this one reads `_START`, which is what actually renders.
    """
    from explainer.template import _START

    assert _START["f1"] == "the session started", _START
    assert "kickoff" not in _START["f1"], _START


# --- the default key list, which was stated three times and stated nowhere ----

def test_the_helper_takes_no_default_key_list():
    """`keys` was declared with a default, and BOTH call sites overrode it.

    `_quoted_line(market, keys=("market_line", "line"))` was the signature, and
    the two callers both passed `MARKET_LINE_KEY.get(sport, ("market_line",
    "line"))` -- the same two-key tuple, written a second time at each call site
    rather than once. So the default was dead code, the value it held existed in
    three places, and nothing tied them together.

    **It was dead in a way a mutation could not see.** Changing the default to
    `("line",)` is SILENT: the default is never reached, so no rendered output
    changes and no test fails. That is the finding -- a default that cannot be
    observed is a statement nobody is relying on, and it is one more place for
    the two-key list to be edited in one place only.

    Asserted against the signature rather than by calling the function both ways,
    because calling it both ways cannot distinguish "the default is this" from
    "the default is something else and both callers pass their own".
    """
    import inspect

    from explainer.template import _quoted_line

    sig = inspect.signature(_quoted_line)
    assert "keys" in sig.parameters, f"the parameter is gone: {sig}"
    assert sig.parameters["keys"].default is inspect.Parameter.empty, (
        f"`keys` has a default ({sig.parameters['keys'].default!r}) and both call "
        f"sites pass their own, so the default is dead code that can be changed "
        f"without changing anything a reader sees"
    )


def test_both_call_sites_read_the_one_key_list():
    """The list now lives once, in a named constant, and this says so.

    `DEFAULT_MARKET_LINE_KEY` is what a sport absent from `MARKET_LINE_KEY` gets,
    and it is the answer to "which key does a new sport read by default". Asserted
    on the CALL SITES' behaviour rather than by reading `template.py`, because a
    check that greps the source for the constant's name is satisfied by a comment
    mentioning it.

    The two call sites are the spread and the total, and they are driven here by
    one bundle whose spread carries only `market_line` and whose total carries
    only `market_line`, so both rows depend on the default list.
    """
    from explainer.template import DEFAULT_MARKET_LINE_KEY

    assert DEFAULT_MARKET_LINE_KEY == ("market_line", "line"), (
        f"the default key list is {DEFAULT_MARKET_LINE_KEY!r}, which is not "
        f"prefers-the-quoted-then-falls-back-to-line"
    )

    # A sport that is NOT in the table and fills `market_line` only must read it.
    quoted_only = explain_from_template(bundle("cfb", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "market_line": "BAL -2.5"},
        {"market": "total", "model_total": 47.8, "market_line": "44.5"},
    ]))
    assert "BAL -2.5" in factor(quoted_only, "spread")["text"], (
        f"a sport absent from the table lost its spread factor: {quoted_only['factors']}"
    )
    assert "44.5" in factor(quoted_only, "total")["text"], (
        f"a sport absent from the table lost its total factor: {quoted_only['factors']}"
    )


def test_a_sport_absent_from_the_table_prefers_the_quoted_key_over_the_model_key():
    """The order matters and the default is where it lives.

    A sport in NBA's shape but not yet in `MARKET_LINE_KEY` -- the state a new
    sport is in on the day it is added -- fills both keys, with the market's in
    `market_line` and the model's own wording in `line`. The default must read
    `market_line` first, and reading `line` first is what the whole
    `MARKET_LINE_KEY` table exists to prevent for NBA.

    So this bites on the default being reordered or shortened, which is exactly
    the change the reviewer found silent while the default was dead code. It bites
    now because the value is stated once and both call sites go through it.
    """
    both = explain_from_template(bundle("cfb", [
        {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
        {"market": "spread", "model_margin": 3.4, "line": "BAL by 3.4", "market_line": "BAL -2.5"},
        {"market": "total", "model_total": 47.8, "line": 45.0, "market_line": "44.5"},
    ]))
    assert "BAL -2.5" in factor(both, "spread")["text"], factor(both, "spread")
    assert "BAL by 3.4" not in factor(both, "spread")["text"], factor(both, "spread")
    assert "44.5" in factor(both, "total")["text"], factor(both, "total")

