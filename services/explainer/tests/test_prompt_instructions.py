"""The prompt may not ask the model for a claim this service cannot check.

`prompts.SYSTEM` used to end one of its rules by offering a sentence as the
*preferred* phrasing:

    Say "the line asks for more than the model rates the gap" and let the panel
    show the gap.

That sentence is a comparison between the model's margin and the quoted line,
and nothing anywhere in the service makes it. The facts carry `model_margin`
(a float, home-minus-away) and a market line that is a WORDED string
(`"BAL -2.5"`, or NBA's `"BOS by 4.2"`), and the bundle carries no home/away
designation at all, so which of the two is bigger is not a question these two
fields can answer. The template had already worked this out and stopped making
the claim -- `template.py`'s spread factor states the two figures and nothing
about their relationship, and `test_template_spread_claim.py` pins that -- which
left the prompt instructing the model to say the thing the renderer had just
decided it could not say.

**And nothing would have caught it.** `validate()` checks the body's shape, the
length caps, the banned words, whether every figure the prose writes appears in
the facts, and whether a verdict is claimed. It does not check prose. So a
2xx-bounded twelve-word sentence with no digits in it, no banned word and no
verdict claim passes validation and is served as the model's own honest answer --
while a twelve-word sentence that says the opposite also passes. The prompt is
the only control on this, which is why it is worth a test of its own rather than
a comment nobody re-reads.

**Not fixed in `validate()`, and the reason is the repo's own.** A phrase
blacklist over the model's prose is what `validate._verdict_problems` already
rejects in its own words: "a keyword list would reject all of it, which is its
own honesty failure: the service falls back to the template and the panel
quietly loses the explanations it exists for". "more" and "less" are ordinary
words in honest football prose, so a blacklist would reject the good sentences
and let the bad one through anyway, on the days it was worded differently.

**Reachable today, or it would not be urgent.** The model path is gated on
`s.enabled and s.openrouter_api_key`, and `deploy-explainer.sh setup` writes
`EXPLAINER_ENABLED=false` only while the env file has no key line in it.
`golive` appends one and sets the flag to true, and after that every subsequent
`setup` re-derives the flag from the presence of the key line alone -- so the
switch is sticky in the enabling direction. The template-only deploy is the
first deploy, not the shape of the service.

Every assertion here reads `prompts.SYSTEM` -- the imported constant, not the
source file. A check that greps a source file can be satisfied by a comment
sitting beside the code, which is the same decoy the mutation harness documents
for its own anchors; reading the value the model is actually sent closes that,
and a comment-only edit then changes nothing and passes, which is the correct
answer for a change to no behaviour.
"""
from __future__ import annotations

import re
import sys

import pytest

from explainer.config import SERVED_SPORTS
from explainer.prompts import SPORT_NOTES, SYSTEM, messages

#: The opening of the only paragraph about figures. Unique in `SYSTEM`, and used
#: as a locator rather than as the assertion -- the assertion is the whole
#: paragraph, so an edit anywhere inside it fails rather than passing as a
#: substring that still happens to be there.
FIGURES_RULE_HEAD = "Write NO figures in the panel."

#: What that paragraph says, in full. Held here rather than compared by a
#: keyword, because the claim this file exists for is not "a word is missing" --
#: it is "the instruction says something different". A keyword test would go
#: green on a rewording that reintroduced the comparison in other words, which is
#: the only kind of edit that matters.
FIGURES_RULE = (
    "Write NO figures in the panel. The panel draws every number from FACTS "
    "itself, so a figure in your text would either duplicate it or contradict it. "
    "Say which market the row is about and let the panel show the gap; do not say "
    "which number is bigger."
)

#: Nothing used to live here, and its absence is worth writing down rather than
#: leaving a gap someone fills.
#:
#: There was a `COMPARATIVES: tuple[str, ...] = ()` on this line -- a ban list
#: that was empty, pre-existing, and referenced zero times repo-wide. An empty
#: tuple annotated as a list of comparatives reads as *"the ban list, currently
#: empty"*, and the next person to fill it in writes the phrase blacklist that
#: this file's own docstring rejects in the same breath: a keyword list over the
#: model's prose rejects the honest sentences and lets the forbidden one through
#: on the day it is worded differently. `validate._verdict_problems` says so, and
#: `test_the_figures_rule_offers_no_sentence_to_imitate` exists because a first
#: version of this file wrote exactly that list and failed on the replacement
#: instruction. So the constant is gone and the reason is on `_quotes` below,
#: which is where a reader deciding what to quote needs it.

# --- rule 2, and the example sentence it used to hand the model --------------
#
# **The branch halved this contradiction rather than creating it.** `origin/main`
# told the model to *say* the comparison -- "the line asks for more than the model
# rates the gap" -- and this branch tells it not to. The example sentence itself
# survived byte-identical, in a different rule, under a different justification:
#
#     Disagreement with the market is information ("the model rates BAL a little
#     better than the line does"), not a recommendation.
#
# So rule 2 was left holding the one sentence the frame exists to stop the model
# writing, in the voice of a piece of house style, in the rule whose subject is
# the anti-advice ban -- the one rule whose whole job is to say what the prose may
# not do. It is not a leftover nobody reads: `deploy-explainer.sh setup`
# re-derives `EXPLAINER_ENABLED` from the presence of the key line, so the first
# `setup` after `golive` turns the model on, and this is the prompt it is sent.
#
# A model handed an example produces something close to it, so an example that
# asserts a comparison is an instruction to assert a comparison however the
# instruction is worded. That is why the guard below is STRUCTURAL -- it reads
# what the frame quotes -- and not a keyword test: `validate()` cannot catch this
# class at all, for the reason this module's docstring gives.

#: The terms rule 2 bans, in the order it names them. Held here as a list rather
#: than a set, because the order is part of the instruction and the assertion
#: below is a sequence equality: a rule that quoted one of these twice, or in a
#: different order, is a different prompt.
BANNED_TERMS = ("lock", "bet", "value play", "hammer", "guaranteed", "sure thing")

#: Rule 2, in full. Pinned for the same reason `FIGURES_RULE` is: the claim this
#: section exists for is not "a word is missing" but "the instruction says
#: something else", and a keyword test goes green on a rewording that
#: reintroduces the comparison in other words -- which is the only kind of edit
#: that matters.
#:
#: Kept to the anti-advice ban, which is rule 2's real subject and the only part
#: of it the model needs in order to comply. The second sentence keeps the half
#: that was always true -- that a disagreement is information and not a
#: recommendation -- and replaces the example with an instruction that hands the
#: model nothing to imitate: name the market, let the panel draw the two figures,
#: do not rank them. It asks for no comparison, and it asks for no figures either,
#: so it does not collide with the figures rule two paragraphs later.
RULE_TWO = (
    "2. No betting advice: never write \"lock\", \"bet\", \"value play\", "
    "\"hammer\", \"guaranteed\" or \"sure thing\". If the model and the market do "
    "not agree, that is information, not a recommendation: name the market the row "
    "is about, let the panel draw the two figures side by side, and do not rank "
    "them."
)


#: Everything the frame's numbered rules quote, in order.
#:
#: **An inventory, not a ban list**, and the distinction is the whole guard. A
#: first version of this test asserted that the only quoted things anywhere in the
#: frame were rule 2's six banned terms, and it failed on six chunks that are all
#: legitimate and all deliberate: rule 1 quoting a phrase FORM for a quantity
#: ("a little more than the line", "about four times in ten"), rule 3 quoting two
#: `pick_timing` VALUES the model has to key off ("rebuilt", "none"), and rule 4
#: quoting a worked illustration of expressing uncertainty. So "no quotes" is not
#: available, and a keyword blacklist over the rest is not either -- which words
#: count as a comparison is a judgement about English, and `validate`'s own comment
#: rejects that shape for exactly this reason.
#:
#: What IS available is a complete, ordered snapshot: every quote the frame makes,
#: pinned. Then any ADDITION fails -- which is the deleted comparative coming
#: back, in rule 2 or in a rule nobody thought to check -- and so does any removal
#: or any move, because the sequence is compared end to end.
#:
#: Its own limit, stated: a snapshot is a copy, so editing this list in the same
#: commit as the prompt satisfies it. That is not fixable by any assertion on
#: prompt prose, and it is why the harness table carries a row that reinstates the
#: comparative -- a mutation nobody can satisfy by editing a test.
FRAME_QUOTES = [
    # rule 1 -- how to express a quantity without computing a new figure
    "a little more than the line",
    "about four times in ten",
    # rule 2 -- the six words it bans, and NOTHING else
    "lock", "bet", "value play", "hammer", "guaranteed", "sure thing",
    # rule 3 -- pick_timing values, which are inputs rather than things to write
    "rebuilt",
    "none",
    # rule 4 -- a worked illustration of expressing uncertainty
    "62% still loses about four times in ten",
]


def _rules() -> list[str]:
    """The numbered rules, which is the part of the frame that is an instruction.

    Scoped away from the JSON schema below them, which is full of double quotes
    and is a shape specification rather than prose. `SYSTEM` is a module attribute
    read at call time, so a comment above the literal cannot satisfy a check here
    and a comment-only change cannot break one.
    """
    return [line for line in SYSTEM.split("\n") if re.match(r"^\d+\. ", line)]


def _quotes(rule: str) -> list[str]:
    r"""Every quoted chunk of a rule, in the order it appears.

    **Both quote characters, and that is the whole fix.** The first version of this
    function split on `"` and took the odd segments, which is a complete answer to
    "what does the frame quote" for as long as the frame only uses one kind of
    quote -- and the guard's docstring advertised a total it did not have. A
    `'`-quoted example slipped past BOTH quote guards:
    `test_rule_two_quotes_the_banned_terms_and_nothing_else` would have read rule
    2's six banned terms and reported that the rule quotes nothing else, while the
    rule sat there holding a seventh quoted thing in single quotes. It was caught
    elsewhere -- the whole-frame inventory compares the flat list, and a reworded
    prompt also moves the prompt digest -- so the SYSTEM held. The GUARD did not,
    and a guard advertised as total which is not is a shape this repo keeps paying
    for.

    **A tokenizer, and not a split -- a split on `'` is worse than no guard at
    all.** `rule.split("'")[1::2]` invents a chunk out of every contraction in the
    frame: rule 3 says *"isn't counted"*, so the naive read reports a quoted thing
    that is not there and breaks `FRAME_QUOTES` for a reason that has nothing to
    do with the prompt. A guard that cries wolf on the text that actually ships is
    a guard that gets deleted, and deleting it takes the real check with it.

    So an opening quote has to be told from an apostrophe, and the only signal in
    running English is the character in front of it: the apostrophe in `isn't`
    and `model's` follows a letter, and a quoted phrase follows a space, a bracket,
    a colon or nothing at all. `(?<![A-Za-z])` is that test, and it is named in
    prose here rather than left inside the pattern so the next reader knows which
    word it is protecting.

    Its own limit, stated: a quoted phrase beginning immediately after a letter is
    not found, and neither is a nested quote of the other kind. The frame has
    neither, and a rule that grew one would be a rule whose quoting this reader
    cannot see -- which is the honest way for it to fail, because it shows up as a
    chunk that is MISSING rather than a chunk that is wrong.

    One pass over both characters, so the order is the order they appear in the
    sentence rather than "all the doubles, then all the singles" -- which would be
    a different order from the one `FRAME_QUOTES` records, and would report a
    reordering that had not happened.
    """
    return [a or b for a, b in
            re.findall(r"(?<![A-Za-z])'([^']*)'|\"([^\"]*)\"", rule)]


def _rule_two() -> str:
    """Rule 2, or a failure that says what is there instead."""
    found = [r for r in _rules() if r.startswith("2. ")]
    assert len(found) == 1, (
        f"expected exactly one rule starting '2. ', found {len(found)}: {found}"
    )
    return found[0]


def test_rule_two_says_exactly_this():
    """The anti-advice ban, and the replacement for the example sentence.

    Reads the imported constant, so the string here and the string shipped are two
    separate objects and a comment above the literal cannot stand in for either.
    """
    assert _rule_two() == RULE_TWO, (
        f"rule 2 now reads:\n{_rule_two()!r}\nwhich is not the instruction this "
        f"test pins."
    )


def _assert_rule_two_quotes_only_the_banned_terms() -> None:
    """The body of the rule-2 quote guard, as a function rather than a test body.

    **A test that only runs against the shipped prompt cannot prove the guard
    WORKS** -- only that the prompt is currently clean, and "the prompt is
    currently clean" is exactly the state the guard was in while it was blind. So
    the assertion is a named function, the test below calls it against the live
    `SYSTEM`, and this file's other test calls it against a prompt that HAS a
    quote in it. One body, two prompts: a copy of the assertion would be a second
    thing to keep in step, and the copy is what would drift.

    It reads `_rule_two()`, and `_rules()` reads the module-global `SYSTEM`, which
    is what lets a test substitute a prompt for it.
    """
    assert _quotes(_rule_two()) == list(BANNED_TERMS), (
        f"rule 2 quotes {_quotes(_rule_two())!r}, and the only things it may quote "
        f"are the {list(BANNED_TERMS)} it bans. Anything else in the rule that tells "
        f"the model what to write is a sentence to imitate, and a model handed an "
        f"example produces something close to it: the deleted clause here was a "
        f"model-vs-market comparison the service cannot compute, and this is what "
        f"stops it returning in any wording."
    )


def test_rule_two_quotes_the_banned_terms_and_nothing_else():
    """**The structural guard for this whole section**, and it reads the LIVE
    constant rather than the copy above -- so it does not go quiet when `RULE_TWO`
    is edited to match a prompt.

    Rule 2 is the one rule that has to quote, because a ban nobody names is not a
    ban: it has to list the six words. What it may not do -- what it used to do --
    is quote anything else, and there is no honest way for it to do that: a quoted
    sentence in the rule whose subject is what the prose may not say is a sentence
    the model is being shown how to say.

    An exact list equality, not a keyword test. It rejects nothing on the grounds
    of what a word MEANS, so it cannot reject an honest sentence -- the objection
    `validate._verdict_problems` raises against a phrase blacklist and raises
    correctly. It says only: these six quoted things, in this order, and no
    seventh.
    """
    _assert_rule_two_quotes_only_the_banned_terms()


def test_the_quote_guard_catches_an_example_written_in_single_quotes(monkeypatch):
    """**The hole, closed and demonstrated.** A `'`-quoted example in rule 2 is
    caught by the rule-2 quote guard ITSELF, not only by the wider inventory.

    The example is the one this file already documents: the model-vs-market
    comparison `origin/main` used to tell the model to SAY, in single quotes,
    sitting in the rule whose whole job is to say what the prose may not write.
    It is the most expensive possible thing for this guard to miss -- a model handed
    an example produces something close to it, and this comparison is one the
    service cannot compute and cannot check.

    **The old reader could not see it, and that is why this is a test and not just
    a change to the helper.** It split on `"` and took the odd segments, so a rule
    holding a seventh quoted thing in single quotes reported only its
    double-quoted content: the shipped `SYSTEM` has no single-quoted chunk, so the
    guard read rule 2's six banned terms and called the rule clean. The SYSTEM
    held anyway -- the whole-frame inventory is a flat ordered snapshot and the
    prompt digest moves with any reword -- so the defect was a guard advertised as
    total which was not, which is the class this repo keeps re-learning.

    The frame is substituted rather than the rule, because `_rules()` reads
    `SYSTEM` and that is the wiring: a guard reading a local string would pass
    while the constant the model is actually sent went unread.

    **`pristine` is captured BEFORE the first `setattr`, and that is not tidiness.**
    `SYSTEM` here is the module global, so a restore written as
    `monkeypatch.setattr(..., "SYSTEM", SYSTEM)` after the patch has already
    installed the tainted copy re-installs the tainted copy -- and the control at
    the bottom silently becomes an assertion about the wrong prompt. It is the
    "read the live constant, not a copy" rule pointed the other way: the copy has
    to be taken while the thing being copied is still the real one.
    """
    pristine = SYSTEM
    tainted = pristine.replace(
        RULE_TWO,
        RULE_TWO + " Say 'the model rates BAL a little better than the line does' "
        "when they differ.",
    )
    assert tainted != pristine, "the substitution did not apply, so this tests nothing"
    monkeypatch.setattr(sys.modules[__name__], "SYSTEM", tainted)

    with pytest.raises(AssertionError, match="the only things it may quote"):
        _assert_rule_two_quotes_only_the_banned_terms()

    # And the reader says WHY, naming the chunk rather than merely disagreeing --
    # a guard that fails without saying what it found is a guard the next person
    # works around.
    found = _quotes(_rule_two())
    assert "the model rates BAL a little better than the line does" in found, found

    # **The control, and it is the half that could have gone wrong quietly.** The
    # SHIPPED frame has to be clean under the new reader, and rule 3 contains
    # "isn't counted" -- so a tokenizer that treated that apostrophe as an opening
    # quote would invent a chunk, break `FRAME_QUOTES`, and fail every prompt test
    # in this file. This is asserted rather than left to them: a reader who has
    # just replaced a split with a regular expression wants to know the
    # contractions survived, and the assertion is where that is said.
    monkeypatch.setattr(sys.modules[__name__], "SYSTEM", pristine)
    assert "isn't counted" not in _quotes(_rule_two())
    assert _quotes(_rule_two()) == list(BANNED_TERMS)



def test_the_frame_quotes_only_what_it_quotes_today():
    """The whole-frame inventory, so the guard is not confined to rule 2.

    Rule 3 quotes two `pick_timing` values and rule 1 quotes two phrase forms, so
    "the frame quotes only banned terms" is not available and "the frame quotes
    nothing" never was. What is available is a complete ordered snapshot, which
    fails on an addition (the deleted comparative returning, here or in a rule
    nobody thought to check), on a removal, and on a move between rules.

    `test_rule_two_quotes_the_banned_terms_and_nothing_else` is the sharper
    guard, because it is scoped to the one rule that must not quote and reads the
    live constant. This one is the wider net: it is what notices a quote appearing
    somewhere the sharper guard is not looking, and the per-rule breakdown in the
    failure message is what makes that locatable.
    """
    rules = _rules()
    assert len(rules) == 6, (
        f"expected the frame's six numbered rules, found {len(rules)}: {rules}"
    )
    per_rule = {rule.split(".")[0]: _quotes(rule) for rule in rules}
    assert list(per_rule) == [str(n) for n in range(1, 7)], (
        f"the rules are not numbered 1..6 in order: {list(per_rule)}"
    )
    found = [chunk for rule in rules for chunk in _quotes(rule)]
    assert found == FRAME_QUOTES, (
        f"the frame now quotes {found!r}, against the {FRAME_QUOTES!r} it quoted "
        f"when this inventory was taken. Per rule: {per_rule}. An addition is the "
        f"deleted comparison coming back; a removal is a ban or an illustration "
        f"the frame still relies on."
    )


def test_the_anti_advice_ban_survives_the_rewording():
    """The half of rule 2 that must NOT move, stated separately.

    A rewrite that removed the comparative could equally have removed the rule's
    reason for existing. This is the assertion that says the second sentence is a
    refinement rather than a replacement, and it is checked against the pinned
    replacement rather than against `SYSTEM` so it is not a second copy of the
    check above: the quotes are already pinned there, so this holds the parts of
    the rule that are not quotes.
    """
    assert RULE_TWO.startswith("2. No betting advice:"), RULE_TWO
    assert "not a recommendation" in RULE_TWO, (
        f"rule 2 no longer says that a disagreement is information rather than a "
        f"recommendation, which is the half of it that was always true: {RULE_TWO}"
    )
    # And the shipped rule is the one that carries it, so the check is not a test
    # of a constant nothing sends.
    assert "not a recommendation" in _rule_two(), _rule_two()



def _figures_paragraph() -> str:
    """The paragraph about figures, or a failure that says what is there instead."""
    paragraphs = [p for p in SYSTEM.split("\n\n") if p.startswith(FIGURES_RULE_HEAD)]
    assert len(paragraphs) == 1, (
        f"expected exactly one paragraph starting {FIGURES_RULE_HEAD!r}, found "
        f"{len(paragraphs)}: {paragraphs}"
    )
    return paragraphs[0]


def test_the_figures_rule_says_exactly_this():
    """The instruction itself, in full. Any edit to this paragraph fails.

    Reads the imported constant, so a comment above the literal cannot satisfy
    it and a comment-only change cannot break it. What the equality buys is that
    the *replacement* is pinned as firmly as the deletion: a rewrite that drops
    the prohibition on comparing the two numbers, or that asks for a different
    example, is a different prompt and needs a deliberate edit here.
    """
    assert _figures_paragraph() == FIGURES_RULE, (
        f"the figures rule now reads:\n{_figures_paragraph()!r}\n"
        f"which is not the instruction this test pins."
    )


def test_the_figures_rule_offers_no_sentence_to_imitate():
    """The deleted instruction's shape, caught structurally rather than by keyword.

    A model handed an example sentence produces something close to it, so an
    example that asserts a comparison is an instruction to assert a comparison
    whatever it is called. The paragraph must therefore quote nothing at all for
    the model to imitate -- which is checkable without reading English, and is
    the shape the deleted instruction had.

    **A first version of this test scanned the paragraph for comparatives
    ("better", "more", "bigger", ...) and failed, on the replacement
    instruction.** Forbidding a comparison has to use a comparative to say so:
    "do not say which number is bigger" is the whole point of the sentence, and a
    word list cannot tell a rule from the thing it forbids. That is the same trap
    `validate._verdict_problems` documents for `validate()` -- a keyword list
    over prose -- met in the other file, and it is why this test is structural.

    The length assertion is the anti-vacuity half: "found no quotes" has to be a
    statement about a paragraph, not about an empty string.
    """
    paragraph = _figures_paragraph()
    assert len(paragraph) > len(FIGURES_RULE_HEAD) + 80, (
        f"the paragraph is too short for this test to have read anything: {paragraph!r}"
    )
    quoted = _quotes(paragraph)
    assert quoted == [], (
        f"the paragraph still offers the model a sentence to imitate: {quoted}. "
        f"It is the instruction, not the example, that has to carry the rule."
    )


def test_every_served_sport_is_shipped_the_whole_rule():
    """That the paragraph reaches the model at all, for every sport that serves.

    The two tests above read `SYSTEM`, which is a module attribute: a refactor
    that stopped sending it, sent a truncated copy, or sent it without a sport's
    language note would leave both of them green while the model reads something
    else. This is the wiring, and it is derived from `SERVED_SPORTS` so a sport
    added later is covered rather than remembered.
    """
    for sport in SERVED_SPORTS:
        system = messages(sport, "{}", "[]")[0]
        assert system["role"] == "system", f"[{sport}] {system['role']!r}"
        assert FIGURES_RULE in system["content"], (
            f"[{sport}] the figures rule is not in the system message the model is sent"
        )
        assert SPORT_NOTES[sport] in system["content"], f"[{sport}] its language note is missing"
