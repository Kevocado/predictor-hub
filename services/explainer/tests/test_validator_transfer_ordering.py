"""A clause's subject has to be a SOURCE before it can hand a market word away.

`#56` scoped the model-ownership exemption to a clause and opened a matching
permit for a clause somebody ELSE owns. Both halves were right. The permit was
loose, and it is loose in a way the trigger measurement cannot see at all,
because a laundered claim does not *fire* a trigger — it is quietly **exempted**
by one, so every false-positive count in `tools/measure_trigger_fps.py` is blind
to it by construction.

`_clause_is_a_transfer` had two gates: a noun from `_THIRD_PARTY_RE`, and that
noun sitting before the first market word. A noun naming a **participant in the
game** rather than a source of information about it walks through both:

    "The model likes Boston, and the side favours the spread."

`side` is in the table. `side` comes before `spread`. Nothing in the clause
sounds like a book. So the clause is somebody else's clause, the spread claim in
it is exempted from the quote requirement, and the bundle underneath is NBA's —
whose `spread` holds the MODEL's own margin and carries no book quote at all.
The reader is told a third party said it when the model said it, which is the
one sentence shape this whole rule exists to stop.

The same sentence with a real source in place of the participant is the permit
working, and it has to keep working:

    "The model likes Boston, and the injury report calls the spread too wide."

So the fix is the noun, not the splitter and not the ordering: **a participant is
not a source.** The four other boundaries English marks are the same bug written
four more ways, and they are pinned here separately because a fix that only
understood `, and` would close the reported sentence and leave the next one open
— which is exactly what sentence scope did to clause scope in `#56`.
"""
import json

import pytest

from explainer.validate import _clause_is_a_transfer, _clauses, _market_problems, _named_markets
from conftest import rule_validate as validate

from test_market_words import NBA_FACTS


# --- the reported bypass -------------------------------------------------------

#: CodeRabbit's Major, verbatim. `_market_problems` returns `[]` for it on
#: `origin/main` (`bb91579`), which is the whole of the finding: the claim is
#: accepted rather than rejected, and the only reason is the word "side".
CODERABBIT_EXAMPLE = "The model likes Boston, and the side favours the spread."

#: CodeRabbit's second half, also verbatim: the same noun with no model clause in
#: front of it at all, so nothing about the *first* clause is doing the work. If a
#: fix only looked at what precedes a market word it would pass this one.
CODERABBIT_REGRESSION = "Either side of the spread is two and a half."


#: The same bypass at each boundary `_CLAUSE_SPLIT_RE` splits on, plus the two
#: frames a model writes when it wants a claim to look sourced. All five are
#: accepted on `origin/main`, and they are five separate ways in, so they are five
#: separate tests: a splitter change that fixed the first and not the fifth would
#: still be a bypass.
LAUNDERED_ACROSS = [
    ("comma and", CODERABBIT_EXAMPLE),
    ("semicolon", "The model likes Boston; the side favours the spread."),
    ("em dash", "The model likes Boston — the side favours the spread."),
    ("according to", "The model likes Boston, and according to the side the spread "
                     "is two and a half."),
    ("trailing per the report",
     "The model likes Boston, and the side favours the spread, per the report."),
]


@pytest.mark.parametrize("text", [CODERABBIT_EXAMPLE, CODERABBIT_REGRESSION],
                         ids=["appended clause", "no model clause in front"])
def test_a_participant_in_the_subject_position_is_not_a_source(text):
    """CodeRabbit's example, asserted on the claim rather than on the helper.

    `_clause_is_a_transfer` returning False is the mechanism; `"spread" in
    _named_markets(text)` is the consequence, and the consequence is what a reader
    experiences. Asserting only the first would let a later change to
    `_market_problems` silently re-open this.
    """
    assert "spread" in _named_markets(text), (
        f"a participant noun carried the market word out of the guard: {text!r} "
        f"-> {_named_markets(text)}"
    )
    assert _market_problems(NBA_FACTS, text), (
        f"the sentence was accepted: {text!r}"
    )


@pytest.mark.parametrize("label,text", LAUNDERED_ACROSS, ids=[i for i, _ in LAUNDERED_ACROSS])
def test_the_bypass_does_not_reopen_at_another_clause_boundary(label, text):
    """One bypass, five ways in, and a splitter that knows only one of them is a
    bypass. `label` is taken as a parameter so the failing id says WHICH boundary
    was open; that is the difference between a fix and a coincidence."""
    appended = [c for c in _clauses(text) if "spread" in c.lower()]
    assert appended, f"the sentence no longer splits the way this test assumes: {text!r}"
    assert not any(_clause_is_a_transfer(c) for c in appended), (
        f"[{label}] a participant clause was read as a third party's clause: {text!r}"
    )
    assert "spread" in _named_markets(text), (
        f"[{label}] the market word was exempted anyway: {text!r} -> {_named_markets(text)}"
    )
    assert _market_problems(NBA_FACTS, text), f"[{label}] accepted: {text!r}"


#: Each noun CodeRabbit named, in a clause whose ONLY third-party noun is that
#: word. That is what makes these a test of the table rather than of the
#: sentence, and it is a stricter constraint than it looks: a first draft of this
#: list wrote "The release calls the update on the spread too wide", which passes
#: for a completely different reason -- `release` is a genuine source, so the
#: clause is a transfer whatever the fix does to `update`. Each sentence below is
#: built to be UNRECOVERABLE except by the word under test, and every other noun
#: in it was checked against `_THIRD_PARTY_RE` and `_BOOK_SOUNDING_RE`.
PARTICIPANT_AND_EVENT_NOUNS = [
    ("side", "One side of this game has the spread covered."),
    ("sides", "Both sides read the spread as fair."),
    ("team", "The team has the spread covered."),
    ("teams", "Both teams read the spread as fair."),
    ("club", "The club has the spread covered."),
    ("test", "A test of the two styles points to a tight spread."),
    ("update", "An update on the squad leaves the spread where it was."),
    ("notes", "The notes on the squad put the spread where it was."),
    ("news", "The news from the road trip leaves the spread where it was."),
]


@pytest.mark.parametrize("noun,text", PARTICIPANT_AND_EVENT_NOUNS,
                         ids=[n for n, _ in PARTICIPANT_AND_EVENT_NOUNS])
def test_a_participant_or_event_noun_is_not_in_the_source_table(noun, text):
    """The table holds sources, and these are the words that were not sources.

    Every one of these clauses names a *game* noun or an *event* noun and no
    source at all: the thing doing the predicting is the thing the sentence is
    about. CodeRabbit's list is the source of the list; the reason it is a list
    and not one word is that the next person to add an entry has to see the
    distinction being drawn rather than infer it from a single deletion.
    """
    assert _market_problems(NBA_FACTS, text), (
        f"{noun!r} still counts as a third party, so a clause naming only "
        f"{noun!r} was exempted from the quote requirement: {text!r}"
    )


@pytest.mark.parametrize("label,text", LAUNDERED_ACROSS, ids=[i for i, _ in LAUNDERED_ACROSS])
def test_a_dressed_up_participant_clause_is_rejected_end_to_end(label, text):
    """Through `validate`, which is the path a reader's text actually takes.

    `test_market_words.py` learned this the hard way: every case in that file
    called `_market_problems` directly, and deleting the
    `problems.extend(_market_problems(...))` line left the file green.
    """
    out = {
        "verdict": "Boston are favoured here.",
        "band": "moderate",
        "factors": [
            {"key": "context", "direction": "neutral", "headline": "Gap", "text": text},
            {"key": "context", "direction": "neutral", "headline": "Form",
             "text": "Boston have been consistent."},
        ],
        "source": "llm", "model": "m", "generated_at": "2026-09-29T00:00:00Z",
        "sport": "nba", "pick_timing": "pre_kickoff",
    }
    problems = validate(out, json.dumps(NBA_FACTS), "[]")
    assert any("market" in p for p in problems), (
        f"[{label}] validate() accepted a market claim dressed up with a "
        f"participant clause: {text!r} -> {problems}"
    )


# --- what must keep working ----------------------------------------------------

#: The permit, with a real source in the subject seat. If a fix makes "a clause
#: the model does not own" into "a clause that mentions any noun", every sentence
#: in this list starts costing a reader their summary, which is the false-
#: rejection failure this file's whole sibling is about.
GENUINE_SOURCES = [
    "The club injury report calls the spread too wide.",
    "The report gives him a handicap of three and a half.",
    "The coach said the handicap would be a shade tighter.",
    "According to the medical team, the handicap is not where it was on Tuesday.",
    "The league's injury bulletin calls the spread too wide.",
    "The medical notes call the spread too wide.",
    "The official scorer lists him as questionable.",
    # The model-says-something-then-a-real-source-says-something-else shape, which
    # is the permit inside a sentence that also has a model clause in it. This is
    # the case a "block every clause that follows a model clause" fix would break,
    # and the reason this fix is the noun rather than the ordering.
    "The model likes Boston, and the injury report calls the spread too wide.",
]


@pytest.mark.parametrize("text", GENUINE_SOURCES, ids=lambda t: t[:40])
def test_a_genuine_source_still_owns_its_own_clause(text):
    """The control for every test above, and the reason the fix is a word list.

    A participant is not a source. A report, a coach, a medical team and a league
    bulletin are, and a rule that stopped telling them apart would reject honest
    prose to catch a laundering attempt — the failure `test_bare_line_references.py`
    already records once for the word "line".
    """
    assert _market_problems(NBA_FACTS, text) == [], f"rejected: {text!r}"


def test_a_source_word_does_not_come_back_through_a_compound():
    """`medical team`, `club's medical bulletin`: the SOURCE half carries it.

    Every noun removed above also appears inside a phrase that has to keep
    working — `medical team` is a fixture in `#56`'s own permit list, and it works
    because of `medical`, not because of `team`. Pinned as a control because a
    table edit that read whole phrases instead of alternatives would pass every
    bypass test above by making the table unfireable, and would look like a
    no-op in review.
    """
    for text in ("The medical team calls the handicap a shade tighter.",
                 "The club's medical bulletin calls the total goals figure high.",
                 "The league's official bulletin calls the spread too wide.",
                 "The scan showed a tight calf, and the injury report put the "
                 "handicap a shade tighter."):
        assert _market_problems(NBA_FACTS, text) == [], f"rejected: {text!r}"


def test_the_table_itself_no_longer_carries_a_participant_noun():
    """Asserted on the compiled pattern rather than on a sentence.

    Every test above is a sentence somebody chose. This is the property, and it
    is the one that stops the next "harmless" addition from putting `side` back.
    The check is a word-boundary search per noun rather than a substring search,
    because `sides` must not be reported as present just because `side` is.
    """
    import re

    from explainer.validate import _THIRD_PARTY_RE

    for noun in ("side", "sides", "team", "teams", "club", "clubs", "test", "tests",
                 "update", "updates", "notes", "news"):
        assert not re.search(rf"\b{noun}\b", _THIRD_PARTY_RE.pattern), (
            f"{noun!r} is in _THIRD_PARTY_RE again; a participant is not a source"
        )
    # ...and the sources are still there, so the assertion above cannot be passed
    # by emptying the table.
    for noun in ("report", "coach", "medical", "bulletin", "official", "league"):
        assert re.search(rf"\b{noun}\b", _THIRD_PARTY_RE.pattern), (
            f"{noun!r} left _THIRD_PARTY_RE; the permit is now unfireable"
        )
