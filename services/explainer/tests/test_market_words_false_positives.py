"""Three ways this guard misfired, each found in production and each verified here.

Every one of these is a **false positive**: honest prose rejected, and the
reader gets the template instead of the summary. That direction matters more
than the false negatives it also has. A guard that fires on ordinary English
teaches the model to write less, which is the same outcome as the dishonesty
this rule was added to prevent — a reader sees a template and concludes the
model had nothing to say.

1. **`_ATTRIBUTION_RE` had no word boundaries.** `recovering` contains
   `covering`, `discovers` and `uncovers` contain `covers`, `the bookings`
   contains `the book`. So "Boston is still recovering from the road trip" was
   reported as a market attribution against a game whose facts quote nothing.

2. **The model exemption searched the whole body.** One factor saying "the
   model" disabled the guard for every OTHER factor, so
   `["The model has Boston at 65%.", "The spread favours Boston."]` named no
   market at all. A guard that an unrelated clause elsewhere in the same answer
   can switch off is not a guard. Now applied per sentence.

3. **The prompt invited prose the validator discards.** Rule 8 said "unless
   that market is in FACTS", but `_market_problems` needs a QUOTE: a market
   present in FACTS with only the model's own figure is still not nameable.
   The prompt and the validator disagreed, and the model was being set up to
   fail.
"""
import pytest

from explainer.validate import _ATTRIBUTION_RE, _market_problems, _named_markets
from explainer.prompts import SYSTEM

from test_market_words import NBA_FACTS, PL_FACTS


# --- 1. word boundaries ----------------------------------------------------------

@pytest.mark.parametrize("text,word", [
    ("Boston is still recovering from the road trip.", "covering"),
    ("The model discovers something.", "covers"),
    ("The bookings desk is closed.", "the book"),
    ("She is rediscovering form.", "covering"),
    ("The uncovered grass.", "covers"),
])
def test_ordinary_english_is_not_a_market_attribution(text, word):
    """The exact false positives, each containing a real trigger as a substring.

    Asserted on the regex directly, because the regex is the defect:
    `_market_problems` reads it, and a test that only went through the rule
    would pass if the rule grew a compensating check.
    """
    assert not _ATTRIBUTION_RE.search(text.lower()), (
        f"{text!r} matched a market attribution ({word!r} inside a longer word). "
        f"Honest prose must not be rejected."
    )


@pytest.mark.parametrize("text", [
    "Boston is still recovering from the road trip.",
    "The model discovers something.",
    "The bookings desk is closed.",
    "She is rediscovering form.",
    "The uncovered grass.",
])
def test_those_sentences_survive_the_whole_rule(text):
    """The end-to-end half: not being an *attribution* is not the same as
    passing. A sentence with no market word at all must produce no problems,
    or the reader still gets the template."""
    assert _market_problems(NBA_FACTS, text) == [], (
        f"honest prose rejected: {text!r} -> {_market_problems(NBA_FACTS, text)}"
    )


def test_the_real_triggers_still_match_after_anchoring():
    """The control. Anchoring must not have disarmed the rule — which is the
    failure mode of every "just add \\b" fix."""
    for text in ("Miami covering the spread", "it covers the spread",
                 "the market line of BOS by 1.9", "the book has it at two and a half",
                 "the point spread is tight", "over/under is 220"):
        assert _ATTRIBUTION_RE.search(text.lower()), f"{text!r} should still be attribution"


# --- 2. the exemption is per sentence -------------------------------------------

def test_one_factor_saying_model_does_not_exempt_another():
    """The defect, verbatim from the review.

    Before: a whole-body search meant `["The model has Boston at 65%.",
    "The spread favours Boston."]` named nothing. A guard that an unrelated
    clause elsewhere in the same answer can switch off is not a guard.
    """
    body = "The model has Boston at 65%. The spread favours Boston."
    assert "spread" in _named_markets(body), (
        "the second sentence's market word was exempted by the first sentence's "
        "mention of the model"
    )


def test_a_model_attributed_figure_is_still_exempt():
    """The control for the fix. Scoping must not make the exemption useless."""
    for text in ("The total projects near 220.",
                 "The model's total is 2.7.",
                 "The model projects 220 points."):
        assert _named_markets(text) == set(), f"model-owned figure wrongly flagged: {text!r}"


def test_a_sentence_that_both_claims_the_model_and_the_market_is_still_a_claim():
    """Exempting "the model's total" must not extend to "the model's total, which
    is what the market line says" — that sentence does make a market claim."""
    text = "The model's total is 2.7, which is what the market line says."
    assert _market_problems(NBA_FACTS, text), (
        "a sentence that attributes the model AND the market was exempted"
    )


def test_the_exemption_does_not_leak_across_a_list_of_factors():
    """Checked on the shape `validate` actually builds: several factors joined.

    The real body is a concatenation of factor fields, so a per-body exemption
    is the same defect one level up.
    """
    fields = [
        "The model has Boston at 65%.",
        "The spread favours Boston.",
        "The total goals figure looks high.",
    ]
    assert _named_markets(" ".join(fields)) == {"spread", "total"}


# --- 3. the prompt agrees with the validator ------------------------------------

def test_the_prompt_does_not_permit_what_the_validator_discards():
    """Rule 8 used to say "unless that market is in FACTS".

    The validator needs a QUOTE, not presence: NBA's `spread` entry exists in
    FACTS and holds the model's own margin, so the prompt told the model that
    naming it was fine and the validator then threw the answer away. A prompt
    that sets the model up to fail is a bug in the prompt even when the
    validator is right.
    """
    rule8 = [r for r in SYSTEM.split("\n") if r.strip().startswith("7.")]
    assert rule8, "the market rule is missing from the frame"
    text = rule8[0].lower()
    assert "quoted line" in text, (
        "the market rule does not mention a quoted line, so it still reads as 'present in "
        "FACTS is enough' — which the validator disagrees with"
    )
    # And the frame must not tell the model a present-but-unquoted market is fine.
    assert "unless that market is in facts" not in text, (
        "the market rule still invites naming any market present in FACTS"
    )


def test_the_prompt_states_the_consequence_of_getting_it_wrong():
    """Not a style point. A model told a rule with no consequence cannot
    calibrate against it, and the observable result is discarded answers."""
    rule8 = [r for r in SYSTEM.split("\n") if r.strip().startswith("7.")]
    assert "discarded" in rule8[0].lower(), (
        "the market rule does not say the answer is discarded, so the model has no way to "
        "tell which phrasings survive"
    )


# --- the two guards together ----------------------------------------------------

def test_an_honest_answer_about_a_quoted_market_still_passes_end_to_end():
    """Nothing above may have disarmed the rule. NBA 2026-09-29 shipped an
    answer claiming a book quote that did not exist; the replacement has to
    pass, or the fix is silence rather than honesty."""
    quoted = dict(NBA_FACTS, markets=[
        {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
        {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
         "market_line": "BOS by 2.0"},
    ])
    honest = ("The model has Boston at 65%. The market line of BOS by 2.0 is close "
              "to the model's margin.")
    assert _market_problems(quoted, honest) == []


def test_pl_prose_with_ordinary_english_is_untouched():
    """The family-wide case: a sport whose facts quote their own lines, saying
    nothing unusual."""
    for text in ("Boston is still recovering from the road trip.",
                 "The bookings desk publishes odds in the morning.",
                 "The model has Arsenal at 48%."):
        assert _market_problems(PL_FACTS, text) == [], f"rejected: {text!r}"
