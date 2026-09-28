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

#: Nothing. There was meant to be a list of comparatives here, and it was
#: deleted because the sentence that forbids a comparison has to name one. See
#: `test_the_figures_rule_offers_no_sentence_to_imitate`.
COMPARATIVES: tuple[str, ...] = ()


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
    quoted = [chunk.strip(' "“”') for chunk in paragraph.split('"')[1::2]]
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
