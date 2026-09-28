"""The fallback when no model is available, over budget, or its output fails
validation: a verdict and a few factors built only from the facts.

**Same shape as the model's answer, on purpose.** The panel's layout is driven
by the data it is handed and does not know whether a model was involved, so
there is exactly one renderer and the two paths cannot drift apart in the reader's
eyes. That is the whole of spec §8: template parity is a property of the design
rather than of how carefully this file is written.

So the template reads the same `market_keys` the panel resolves against, and
every factor it emits names one of them. A factor pointing at a market the facts
lack would have to render as a dash, and spec §6 says an absent market renders
*nothing*.

`direction` is relative to the pick, so with no pick there is nothing for a
factor to be for or against, and a factor that cannot be relative to anything
says `neutral` rather than reaching for "up" — see `_toward`. That is a rule
about every row below, not a special case for the rows that mention a pick: the
total, both-teams-to-score and the record are statements about the game and about
other picks, so they are `neutral` whether or not this one exists.

One row is `neutral` for the *other* reason, and `_toward` is not what puts it
there: the spread factor, which cannot be directional even with a pick in hand,
because nothing in this file compares the model's margin against the quoted line.
See the comment at that row — it is `neutral` always, and would be wrong to
write as `_toward(NEUTRAL, has_pick)`, which is a no-op that reads like a rule.

Facts fields beyond the contract's core are loose dicts, so every read here is
defensive: this is the last resort and it must never raise.
"""
from __future__ import annotations

from .contract import NEUTRAL, as_dict, band_for, market_shape, pick_for, pick_prob

_TENS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
#: Which key holds the MARKET's quoted line, per sport. Read in order; the first
#: key present with a non-empty value wins, and if none is present the factor is
#: omitted rather than narrated against nothing.
#:
#: This is a table rather than a precedence rule because `line` does not mean one
#: thing across the family. NFL and CFB put the market's line there; NBA puts the
#: MODEL's own projected margin there and the market's in `market_line`. A blanket
#: fallback reaches the model's wording whenever NBA has no pre-tip quote, and
#: NBA omits `market_line` in exactly that case -- so the fallback fired on NBA's
#: common path and rendered "against a line of Toss-up".
#:
#: The end state is NFL and CFB emitting `market_line` the way NBA already does
#: (NBA's own facts.py says so: "`market_line` in every market, so the panel reads
#: one key for the quoted book line. `line` is reserved for the model's own
#: wording"). One line each in two sibling repos, and this table empties.
#:
#: Absent from the table means the default, which is right for a sport whose `line`
#: IS the market's line. A new sport that puts its model's own wording in `line`
#: must be added here -- and that is the failure this table exists to make
#: visible rather than guess at.
#: Only the sports whose `line` is NOT the market's need an entry. Everyone else
#: gets the default, which prefers `market_line` and falls back to `line` -- right
#: for a sport that puts the market's line in either key, and wrong for one that
#: puts something else in `line`. NBA is currently the only such sport.
MARKET_LINE_KEY: dict[str, tuple[str, ...]] = {
    "nba": ("market_line",),
}

#: The key list a sport gets when it is **absent** from `MARKET_LINE_KEY` above:
#: the market's quoted key first, then the sport's own `line`, which is the
#: market's line for every sport that has only one of the two.
#:
#: It is a named constant and not a default argument, and both call sites pass it
#: explicitly. The signature used to declare the same two-key tuple as a default
#: while BOTH callers overrode it, so the default was dead code, the value existed
#: in three places, and nothing tied them together -- changing the default to a
#: single key changed no rendered output and failed no test, which is the only
#: reason it is worth writing down. Stated once here, it is reachable by the two
#: rows that use it, and
#: `test_a_sport_absent_from_the_table_prefers_the_quoted_key_over_the_model_key`
#: fails if the order or the length changes.
DEFAULT_MARKET_LINE_KEY: tuple[str, ...] = ("market_line", "line")

#: How each sport names the moment the game begins. NBA says "tip-off" in its
#: prompts (`prompts.py` `SPORT_NOTES`) and in the record label the panel renders,
#: so a sentence reading "rebuilt after kickoff" sat next to "picks made before
#: tip-off" on the same screen. The default is kept for the two football sports
#: rather than listing them, so a new sport gets a sensible word instead of
#: `KeyError`.
_START = {"f1": "the session started", "pl": "kickoff", "nba": "tip-off"}
#: How small a projected margin may be before the spread factor stops narrating
#: it, in points. Half a point, and not a number invented here: NBA's own
#: `_margin_line` (`api/facts.py`) words a margin as a gap only at
#: `abs(margin) >= 0.5` and otherwise returns the literal "Toss-up". So a bundle
#: whose margin is 0.4 arrives having already been told the gap is a toss-up, and
#: a template without this floor contradicts the bundle it was handed.
#:
#: The floor exists because `margin is not None` passes for `0`, and the row it
#: gates then exists only to say nothing. It used to be worse than that -- the
#: sentence it gated ended "It rates BOS 0 points better", a claim about a
#: disagreement that does not exist, and that comparison has since been taken out
#: of the sentence altogether (see the spread factor below). The floor is still
#: load-bearing: NBA's own builder words a margin as a gap only at
#: `abs(margin) >= 0.5` and otherwise returns the literal "Toss-up", so a bundle
#: whose margin is 0.4 arrives having already been told the gap is a toss-up,
#: and a template without this floor contradicts the bundle it was handed -- it
#: would print a gap where the producer said there is none, and a reader would
#: give a tile to a row with nothing in it. Same defect class as the clause this
#: file once ended that sentence with -- a comparison stated rather than computed
#: -- except the uncomputable half here is not "which of the two is bigger" but
#: "whether there is anything to compare at all".
#:
#: **Only the MAGNITUDE half of NBA's rule.** NBA also requires the margin to
#: point at the pick's own team before wording it, and that check is not
#: available here: the bundle carries no home/away designation, so which side a
#: margin belongs to is not derivable. A bundle whose margin disagrees with the
#: moneyline's favourite therefore still gets its row. Fixing that needs a
#: home/away designation in the facts, not a guess in this file.
#:
#: Inclusive, because a margin of exactly 0.5 is one NBA is willing to word.
MIN_SPREAD_MARGIN = 0.5
MAX_FACTORS = 4


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _pct(p: float) -> str:
    if p <= 0.005:
        return "<1%"
    if p >= 0.995:
        return ">99%"
    return f"{round(p * 100)}%"


def _dicts(xs) -> list[dict]:
    return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []


def _fact(key: str, direction: str, headline: str, text: str) -> dict:
    return {"key": key, "direction": direction, "headline": headline, "text": text}


def _outcome_key(by_key: dict) -> str:
    """The market a pick or an outcome belongs to, for use as a factor `key`.

    PL's three-way market is literally named `result`; NFL's and CFB's outcome is
    a top-level `result` with the pick's market named `moneyline`. So a factor
    about the pick or how it finished cannot just be keyed `result` — for NFL
    that names a market the facts do not carry, and the panel would resolve it to
    nothing and render an empty row. Same trap as `contract.market_shape`, and
    for the same reason.
    """
    if "result" in by_key:
        return "result"
    if "moneyline" in by_key:
        return "moneyline"
    return "context"


def _toward(direction: str, has_pick: bool) -> str:
    """A pick-relative direction, or `neutral` when there is no pick to be relative to.

    `direction` means "for the pick" or "against it" and nothing else, so it is
    only knowable when there IS a pick. With no pick, "up" would render a factor
    that says nothing about any pick as one arguing for it, which is the defect
    this exists to remove — so the row claims nothing instead.
    """
    return direction if has_pick else NEUTRAL


def _quoted_line(market: dict | None, keys: tuple[str, ...]) -> str | None:
    """The line a READER can check against a book, from whichever key this sport
    used to put it in.

    The key `line` means two different things across the family. NFL and CFB put
    the market's line in it (`"BAL -2.5"`) and have no `market_line`. NBA puts the
    MODEL's own projected margin there (`"BOS by 4.2"`, or the literal `"Toss-up"`
    when the margin rounds to nothing) and the market's line in `market_line`.

    Reading `line` as the market's is therefore right for two sports and wrong for
    one, and for NBA it renders the model compared with itself: *"It rates BOS 4.2
    points better, against a line of BOS by 4.2."* That is the same failure as
    narrating a prediction without its timing, so the two are not adjacent
    concerns -- they are the same rule.

    **Which key holds the market's line is a per-sport fact, not a precedence
    rule.** NFL and CFB put it in `line` and have no `market_line`; NBA puts the
    MODEL's own wording in `line` and the market's in `market_line`. So the
    fallback to `line` is right for two sports and wrong for one, and for NBA it
    renders the model compared with itself.

    The first version of this helper preferred `market_line` and fell back to
    `line`, on the reasoning that a lower-priority source of the same thing is
    harmless. It is not, because the fallback key does not hold the same thing:
    NBA emits `market_line` only when there is a pre-tip market row, so in the
    no-quote state -- which is NBA's common case -- the fallback reached the
    model's own wording and produced

        It rates BOS 0.2 points better, against a line of Toss-up. That is the
        market asking for more than the model thinks the gap is worth.

    (Both halves of that quotation are historical. The trailing clause was
    removed later and for a separate reason -- it was a constant claim, since
    nothing compares the two numbers -- and the first half was then narrowed
    further, because it attributed the margin to the pick's team and the bundle
    carries no home/away designation. The sentence the factor emits today names
    neither a side nor a comparison. See the spread factor below.)

    A precedence rule cannot distinguish "a worse source of the same fact" from
    "a different fact that happens to share a key name", so the caller says which
    is which: `MARKET_LINE_KEY` below. The end state is the two football sports
    emitting `market_line` like NBA already does, at which point the table is
    empty and every sport reads one key.

    **Numbers are accepted, not just strings.** A total's `line` is a float --
    `{"market": "total", "line": 45.5}` -- while a spread's is a worded string. The
    first version of this helper type-checked for `str` and silently dropped the
    total factor for every sport, which `test_template_covers_markets_and_the_record`
    caught immediately. A truthy check is the honest one here: `0` and `False` are
    not lines anything would be quoted against.
    """
    if not isinstance(market, dict):
        # The module docstring promises every read here is defensive, and a
        # non-dict market would raise on `.get`. Nothing produces one -- `by_key`
        # is built from `_dicts(...)` -- but the promise is cheap to keep.
        return None
    for key in keys:
        value = market.get(key)
        if isinstance(value, bool):
            # `True` is truthy and would render "against a line of True". `_num`
            # four lines up excludes bools explicitly for the same reason.
            continue
        if isinstance(value, str):
            # Stripped before the truthiness test, so a whitespace-only line falls
            # through instead of rendering "against a line of    .". An earlier
            # version of this loop also had an explicit
            # `if value is None or value == "": continue`, which was dead -- the
            # truthy test below already rejects `None`, `""`, `0` and `[]`. It
            # survived a mutation check that reported it as covered, because
            # removing it changed nothing at all. One check, not two.
            value = value.strip()
        if value:
            return str(value)
    return None


def explain_from_template(facts: dict) -> dict:
    """The no-model path, in the model's own shape, built from the facts."""
    facts = as_dict(facts)
    title = str(facts.get("title") or "This match")
    pick = facts.get("pick") if isinstance(facts.get("pick"), dict) else {}
    label = pick.get("label")
    label = str(label) if label not in (None, "") else None
    prob = pick_prob(facts)
    # Whether there is a pick at all, from the same function the response's own
    # `pick` field is built by, so a factor can never point at a pick the answer
    # does not carry.
    has_pick = pick_for(facts) is not None
    sport = facts.get("sport", "")
    unit = "goals" if sport == "pl" else "points"
    timing = facts.get("pick_timing")
    by_key = {str(m.get("market")): m for m in _dicts(facts.get("markets")) if m.get("market")}

    factors: list[dict] = []

    # How it finished. Before the pick factor, because a finished game is the one
    # thing a reader opening the panel is actually asking.
    result = facts.get("result") if isinstance(facts.get("result"), dict) else None
    if facts.get("status") == "final" and result and result.get("score"):
        text = f"Final: {result['score']}."
        # Only a pick made before the start is judged. The facts omit `pick_won`
        # for a rebuilt pick precisely so nothing can grade it.
        if timing == "pre_kickoff" and isinstance(result.get("pick_won"), bool) and label:
            text += f" The pick was {'right' if result['pick_won'] else 'wrong'}: {label}."
        factors.append(_fact(_outcome_key(by_key), _toward("up", has_pick), "How it finished", text))

    # A rebuilt pick is disclosed as a factor in its own right, so it cannot be
    # missed by a reader who only reads the first row.
    if timing == "rebuilt":
        factors.append(_fact(
            "context", _toward("down", has_pick), "Rebuilt after the start",
            f"This pick was rebuilt after {_START.get(sport, 'kickoff')}, so it is shown but "
            f"not counted, and it is not graded either way."))

    if label and prob is not None:
        factors.append(_fact(_outcome_key(by_key), "up", "The pick",
                             f"The model makes {label} the pick at {_pct(prob)}."))

    margin_market = by_key.get("spread") or by_key.get("handicap")
    margin = _num((margin_market or {}).get("model_margin"))
    quoted = _quoted_line(margin_market, MARKET_LINE_KEY.get(sport, DEFAULT_MARKET_LINE_KEY))
    # The magnitude test is the point here, not `margin is not None`: a margin of
    # exactly 0 passes that, and the row it gated rendered "It rates BOS 0 points
    # better, against a line of BOS -3.5" -- a disagreement of nothing, narrated
    # as a gap. The sentence no longer claims a disagreement at all, so what is
    # left at zero is a row whose only content is a figure of nothing, which is
    # the emptiness the total-market gate below rules out for the same reason.
    # Omit the row, which is what the `quoted` clause below already does when
    # there is no line to check against, rather than word a zero.
    #
    # NOTE: this comment deliberately does not quote the expression on the next
    # line. A mutation harness anchors on source text, and a comment repeating
    # the code verbatim is a decoy that absorbs the mutation and reports it
    # covered: the `>=`-becomes-`>` row was SILENT for exactly this reason, and
    # the boundary test that was supposed to catch it could not run. `count=1`
    # takes the FIRST match, so a comment above the code wins over the code.
    big_enough = margin is not None and abs(margin) >= MIN_SPREAD_MARGIN
    if margin_market is not None and margin is not None and label and quoted and big_enough:
        line = quoted
        # NEUTRAL unconditionally -- NOT `_toward(NEUTRAL, has_pick)`, which would
        # be a no-op wrapping a no-op, and NOT `_toward("down", has_pick)`, which
        # is what this row said before. `_toward` answers "is this direction
        # knowable without a pick", and this row's direction is not knowable WITH
        # one either, so it is a plain constant by main's own idiom -- the same
        # shape as the total, `btts` and the record below.
        #
        # The sentence is the two numbers and nothing else, and that covers a
        # little more than it used to.
        #
        # It used to end "That is the market asking for more than the model thinks
        # the gap is worth", and carry `direction: "down"`. Both were CONSTANTS:
        # nothing compared `model_margin` with the quoted line, so the sentence
        # was a comparison asserted rather than computed. With a model margin of
        # 4.2 it is false against `BOS -3.5` (the market wants 3.5, so it is
        # asking for LESS) and against `BOS -4.2` (they agree), and true only
        # against `BOS -6.0` -- and a confident model is usually more bullish than
        # the market, so the shipped sentence was usually wrong.
        #
        # `down` was wrong in the same way and pointed the other way from the
        # claim: `down` means "against the pick", which takes a market SOFTER than
        # the model, and "the market is softer than the model" argues FOR the
        # pick. A wrong mark is louder than a wrong sentence -- the panel draws a
        # triangle and a "for the pick" / "against it" word from it -- so the
        # mark goes before the claim does, and neither is asserted without the
        # comparison behind it.
        #
        # So this row lost its direction on purpose, and that is a narrowing of
        # what the panel draws: with a pick in hand, a reader used to be told the
        # market was arguing against it. They are now told only what the two
        # numbers are. A neutral row the reader can check beats a directional row
        # they cannot, and `test_the_rows_about_the_pick_still_carry_their_direction`
        # is what keeps the OTHER rows directional so this did not become "make
        # everything neutral".
        #
        # **And the sentence named a SIDE, which is a second unsupported claim
        # in the same breath.** `model_margin` is home-minus-away; the bundle
        # carries no home/away designation; and NFL and CFB word the line from
        # their own `_spread_line`, which is always attributed to the home team.
        # So "It rates {label} N better" attributes a margin to the pick's team
        # when the pick may be the other side, and puts it beside a quoted line
        # that belongs to whichever team the builder chose. NFL's `_markets` makes
        # the pair genuinely mismatched and says so itself: the moneyline comes
        # from the pre-kickoff snapshot row and the spread from today's
        # recomputation, because the snapshotted pick is the one that will be
        # judged and today's model "genuinely differs". The case is built in
        # `tests/test_template_spread_claim.py::_nfl_away_pick`; it rendered
        # "It rates KC 2.6 points better, against a line of BAL -2.5", where the
        # model rates BAL better and BAL -2.5 is BAL's line rather than KC's.
        # Both figures were real; the sentence joined them to a team neither
        # belongs to.
        #
        # So the attribution and the comparative go, and both figures stay:
        # "projects a margin of N" is the model's own projection and "against a
        # line of L" is whatever `_quoted_line` found. Nothing is claimed about
        # which of the two is bigger, and nothing is claimed about a side.
        #
        # **This wording is true for every sign, every sport and every bundle,
        # and that is the property it was chosen for.** `abs(margin)` is the
        # magnitude of a projected margin between the two teams, which is a real
        # projection whichever way it points, so `+4.2` and `-4.2` render the same
        # sentence; `0` never reaches here because the floor above omits it; and
        # the floor is inclusive, so half a point in either direction is a gap and
        # is worded as one. `unit` is "points" for every sport that has a spread
        # (PL's is goals, and PL has no spread market, so the row cannot fire
        # there), and "a margin of N points" is grammatical in both. The line is
        # whatever the sport's key held, verbatim, which is the same value the
        # reader can check against a book. Nothing in the sentence varies with
        # anything the sentence does not have.
        #
        # The `label` gate above is KEPT even though the sentence no longer reads
        # it. Widening the row to bundles with no pick is a separate call about
        # what the panel has to anchor on, and it is not this fix.
        #
        # **Deriving the comparison is a real change and is not done here.** The
        # two numbers are `model_margin`, a float, and the quoted line, a WORDED
        # string ("BOS -3.5", "BAL -2.5", "BOS by 4.2"). Deciding which side of
        # the model a line sits on means parsing a magnitude and a side out of
        # that string, and the sign convention of `model_margin` is not in the
        # facts at all -- the bundle carries no home/away designation, so "the
        # market wants more" is not even a well-posed question about these two
        # fields without one. Doing it would also flip the drawn direction of a
        # row on three already-shipping sports. A mark that is wrong is worse than
        # no mark, so until the comparison is computed the row claims nothing.
        #
        # **The end state, and it is a cross-repo change.** The facts should
        # carry the margin that belongs to the PICK -- a `pick_margin` beside
        # `model_margin`, emitted by each sport's own `/facts` builder, signed so
        # that positive means the pick's team and carrying the side the figure
        # belongs to. NBA's `_margin_line` already computes the first half of that
        # and throws it away by returning a worded string; NFL and CFB would each
        # need the home/away designation they already have in `_markets`. Then
        # this row can name the pick again, and the comparison is still not
        # derivable -- the end state fixes the attribution, not the comparison,
        # which needs the line parsed to a number and a side the same way. Until
        # both arrive, two figures and no claims about them is the whole of what
        # is honest.
        factors.append(_fact(str(margin_market["market"]), NEUTRAL, "The line",
                             f"It projects a margin of {abs(margin):g} {unit}, against a line of {line}."))

    total_market = by_key.get("total") or by_key.get("total_goals")
    total = _num((total_market or {}).get("model_total"))
    total_line = _quoted_line(total_market, MARKET_LINE_KEY.get(sport, DEFAULT_MARKET_LINE_KEY))
    if total_market is not None and total is not None and total_line is not None:
        # A projection for the game, not a claim about the pick: emitted whether
        # or not there is one, so it can only be neutral. The line is read
        # through `_quoted_line` for the reason the spread above is, and this row
        # is the reason that helper accepts a number as well as a string.
        factors.append(_fact(str(total_market["market"]), NEUTRAL, "The total",
                             f"It projects {total:g} {unit} against a line of {total_line}."))

    btts = by_key.get("btts")
    yes = _num((btts or {}).get("yes_prob"))
    if btts is not None and yes is not None:
        # As the total: a statement about the game, so neutral either way.
        factors.append(_fact("btts", NEUTRAL, "Both to score",
                             f"It puts {_pct(yes)} on both teams scoring."))

    # The record states counts, never a proportion. It is a factor here as well as
    # a panel extra, but it goes LAST on purpose: there are four slots and a
    # bundle can carry three markets, so this is the one that gets sliced off
    # when there is no room. `record` is hits/settled and
    # the facts contain no percentage; the panel draws the bar's width from the
    # two numbers, and a derived "60.3%" here would be a figure no fact carries
    # (spec §5a-bis). This is also the one place "right"/"wrong" must not appear
    # for a rebuilt pick, which is why it says "recorded" rather than "correct".
    record = facts.get("record") if isinstance(facts.get("record"), dict) else None
    hits, settled = (_num(record.get("hits")), _num(record.get("settled"))) if record else (None, None)
    if hits is not None and settled:
        what = str(record.get("label") or "picks made before the start").lower()
        # Neutral, and always: the record counts OTHER picks, so it is not
        # evidence for this one even when this one exists. Reading it as "for the
        # pick" would let a season's hits stand in for a match.
        factors.append(_fact("record", NEUTRAL, "Its record so far",
                             f"{int(hits)} of {int(settled)} {what} have landed."))

    # Two rows minimum, so the panel is never a single lonely line. Padding only
    # ever uses the pseudo-markets, which resolve regardless of what the facts
    # carry, and it says plainly that there is nothing there rather than
    # inventing a reason to read it.
    if len(factors) < 2:
        # Only `context` padding, and never a claim that something is missing when
        # it is present: an earlier draft padded with a `record` factor saying
        # "no settled record yet", which would have been false for exactly the
        # bundles that reach it.
        while len(factors) < 2:
            if not any(f["key"] == "context" for f in factors):
                factors.append(_fact("context", _toward("down", has_pick), "Not much to go on",
                                     "The facts for this one are still filling in."))
            else:
                # Neutral always. "So there is little to weigh up here" is not an
                # argument FOR a pick; it was given "up" because the row needed a
                # direction, and the words above it do not support one.
                factors.append(_fact("context", NEUTRAL, "Where this stands",
                                     f"So there is little to weigh up here: {title}."))

    verdict = f"{label} is the pick." if label and prob is not None else "There is no pick for this one yet."
    return {"verdict": verdict, "band": band_for(prob, market_shape(facts)),
            "factors": factors[:MAX_FACTORS]}


def minimal(facts: dict) -> dict:
    """If even the template fails: say so, never error.

    Only the pseudo-markets, so every factor resolves against a bundle with no
    markets at all — this runs precisely when things are broken. Both are
    `neutral`: there is no pick here to be for or against, and these rows are
    about the service rather than about any prediction.
    """
    return {
        "verdict": "No explanation is available for this one yet.",
        "band": "leaning",
        "factors": [
            _fact("context", NEUTRAL, "Not ready",
                  "The explanation service could not build a summary for this fixture."),
            _fact("context", NEUTRAL, "Try again",
                  "A later visit may find the facts in place."),
        ],
    }
