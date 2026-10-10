"""Clause scope: who owns the claim in a sentence, and who does not.

`_named_markets` exempts a market word when the sentence that holds it also
holds a word that says the model is talking about itself. That exemption is
**sentence-scoped**, and a sentence is too big a scope to be an ownership
statement. Measured on `origin/main` (`f7f4ee8`):

    "The model rates Boston 3.4 points better, and the spread is fair at
     two and a half."     ->  _named_markets(...) == set()   # no problem

    "The model has Boston at 65%; the total goals figure looks high."
                                             ->  _named_markets(...) == set()

Both name a line market the NBA bundle carries only the MODEL's own figure for,
and both were accepted. One clause saying "the model" licensed a claim made by a
different clause, which is the defect class `test_market_words_false_positives.py`
recorded once already (`test_one_factor_saying_model_does_not_exempt_another`) and
which sentence scope did not actually fix -- it moved the boundary from the answer
to the sentence, and a sentence is still not a clause.

The other direction is the same defect from the other side. A sentence may hand
ownership to somebody else entirely, and the guard read every market word as the
model's own claim about the market:

    "The club injury report calls the spread too wide."
                                             ->  rejected, market problem
    "The report gives him a handicap of three and a half."
                                             ->  rejected, market problem

Both are a third party asserting something about a line, which is not the model
attributing a figure to a book, and a reader getting the template for them is the
same loss as the leak the rule was added to stop.

So a clause is the unit of ownership, and this file pins three things about it:

* **a clause the model owns is exempt** (the existing behaviour, now bounded);
* **a clause a third party owns is exempt**, and "third party" is defined
  narrowly enough that a book is not one;
* **nothing here touches the attribution rule**, which stays body-scoped on
  purpose, so a claim cannot be laundered by saying who said it.
"""
import pytest

from explainer.validate import _market_problems, _named_markets
from conftest import rule_validate as validate

from test_market_words import NBA_FACTS, PL_FACTS


def _quoted_nba():
    """The same bundle with a real book quote, so a market claim is supportable."""
    return dict(NBA_FACTS, markets=[
        {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
        {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
         "market_line": "BOS by 2.0"},
    ])


# --- the permit half: ownership handed to somebody else -------------------------

#: The reviewer's own examples, verbatim. **Both already passed before this
#: change** -- they name no market word and no attribution phrase, so no rule in
#: `validate` reached them. They are pinned anyway, for the reason the rest of
#: this file's controls are pinned: the clause model has to keep passing them,
#: and a sentence the reviewer named by hand is the one most likely to be
#: "improved" into a rejection by the next person to touch the splitter.
REVIEWER_EXAMPLES = [
    "The injury report lists him as doubtful.",
    "The market moved.",
]


#: Ownership handed to a third party, in a clause that names a line market. These
#: DID trip the guard before this change, which is what makes them the tests.
THIRD_PARTY_TRANSFERS = [
    "The club injury report calls the spread too wide.",
    "The report gives him a handicap of three and a half.",
    "The coach said the handicap would be a shade tighter.",
    "According to the medical team, the handicap is not where it was on Tuesday.",
    "The league's injury bulletin calls the spread too wide.",
]

@pytest.mark.parametrize("text", REVIEWER_EXAMPLES, ids=lambda t: t[:40])
def test_a_sentence_handing_ownership_to_another_subject_is_not_a_model_claim(text):
    """The literal sentence the review named. Asserted through the whole rule, not
    through the helper, because "is not an attribution" is not "passes"."""
    assert _market_problems(NBA_FACTS, text) == [], f"rejected: {text!r}"


@pytest.mark.parametrize("text", THIRD_PARTY_TRANSFERS, ids=lambda t: t[:40])
def test_a_clause_owned_by_a_third_party_may_name_a_line_market(text):
    """The permit, and the case that needed it.

    A report, a coach or a medical team saying something about a line is that
    party making the statement. It is not the model attributing its own figure to
    a book, which is the failure `_market_problems` exists to catch, and rejecting
    it costs a reader their summary for a sentence that asserts nothing the facts
    contradict.
    """
    assert _named_markets(text) == set(), (
        f"a third party's own clause was read as the model naming a market: {text!r}"
    )
    assert _market_problems(NBA_FACTS, text) == [], f"rejected: {text!r}"


#: The trigger measurement's one genuine false positive, kept here as the
#: cross-reference for the fix rather than as a duplicate of the test that owns
#: it. `MARKET_WORDS["total"]` resolved the prose concept to `("total_goals",
#: "over_under")` only, so against NBA's own facts -- which name the market
#: `total` -- the intersection came out empty and the guard reported "names a
#: market the nba facts do not carry: total (present: moneyline, spread, total)".
#: Fixed in `MARKET_WORDS`; pinned by
#: `test_market_words.py::test_the_total_concept_resolves_a_key`.
MEASURED_FALSE_POSITIVE = "The total goals figure is tight."


def test_a_third_party_transfer_is_judged_on_whether_the_market_exists_not_on_who_spoke():
    """The permit is bounded by the facts, and both halves are asserted.

    The transfer exempts a clause from being read as the MODEL's claim. It does
    not stop `_market_problems` asking whether the market exists: a bundle with no
    `spread` cannot render one, so prose naming it is a claim about nothing, and
    who said it does not change that. This is the test that keeps the permit from
    being a blanket one, and it is why `_transferred_markets` is a separate
    function rather than an early return inside `_named_markets`.
    """
    empty = {"sport": "nba", "markets": [], "pick": None}
    problems = _market_problems(empty, "The club injury report calls the spread too wide.")
    assert problems, (
        "a third-party transfer made the rule unfireable against a bundle that "
        "carries no market to be talked about"
    )


@pytest.mark.parametrize("quoted", [True, False], ids=["bundle quotes the total",
                                                      "bundle has no total"])
def test_a_transfer_about_a_quoted_market_is_accepted_and_about_an_absent_one_is_not(quoted):
    bundle = {
        "sport": "nba",
        "markets": ([{"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
                     {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
                      "market_line": "BOS by 2.0"},
                     {"market": "total", "model_total": 220.4, "market_line": 221.5}]
                    if quoted else []),
        "pick": {"label": "BOS", "prob": 0.652}, "drivers": [], "context": {},
    }
    text = "The coach said the total goals figure would be lower."
    problems = _market_problems(bundle, text)
    if quoted:
        assert problems == [], f"rejected prose about a market that exists: {text!r}"
    else:
        assert problems, (
            "a bundle carrying no total at all was told a sentence about it was "
            "fine, because a coach said it"
        )


# --- the block half: the exemption is not a loophole ----------------------------

#: Each of these is the sentence-scope exemption being used as a tunnel. One
#: clause says "the model"; a DIFFERENT clause makes the market claim. On
#: `origin/main` every one of them was accepted.
DRESSED_UP = [
    ("The model rates Boston 3.4 points better, and the spread is fair at two "
     "and a half."),
    ("The model has Boston at 65%; the total goals figure looks high."),
    ("The model likes Boston, but the handicap looks wide."),
]

#: The same tunnel with a full stop instead of a comma, which the per-SENTENCE
#: scope already closed. It is here so the fix cannot be a narrowing that reopens
#: this one: a splitter that only understood `;` and `, and` would still pass it.
ALREADY_SCOPED = "The model is a number cruncher. The spread is fair at two and a half."


@pytest.mark.parametrize("text,concept", [
    (DRESSED_UP[0], "spread"),
    (DRESSED_UP[1], "total"),
    (DRESSED_UP[2], "spread"),
    (ALREADY_SCOPED, "spread"),
], ids=["comma and", "semicolon", "but", "sentence boundary -- already scoped"])
def test_the_model_exemption_does_not_cross_a_clause(text, concept):
    """The defect, verbatim from the review.

    Before: `_named_markets` asked whether the SENTENCE said "the model", so a
    first clause saying it licensed a market word in a later clause of the same
    sentence. The last row already held -- the exemption is per sentence -- which
    is the whole of what the old fix did, and a sentence is still not a clause.
    """
    assert concept in _named_markets(text), (
        f"a market word in a clause the model does not own was exempted by another "
        f"clause saying 'the model': {text!r} -> {_named_markets(text)}"
    )


@pytest.mark.parametrize("text,concept", [
    (DRESSED_UP[0], "spread"),
    (DRESSED_UP[1], "total"),
    (DRESSED_UP[2], "spread"),
    (ALREADY_SCOPED, "spread"),
], ids=["comma and", "semicolon", "but", "sentence boundary -- already scoped"])
def test_a_dressed_up_claim_is_rejected_end_to_end(text, concept):
    """And through `validate`, which is the path a reader's text actually takes.

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
    problems = validate(out, __import__("json").dumps(NBA_FACTS), "[]")
    assert any("market" in p for p in problems), (
        f"validate() accepted a claim dressed up with another clause: {text!r} "
        f"-> {problems}"
    )


#: A book is never a neutral third party. This is the whole boundary of the
#: permit: "the injury report says the spread is 2.5" is a transfer, and
#: "the bookmaker's site lists the spread at 2.5" is the exact failure the rule
#: was added for, wearing a hat.
BOOK_SOUNDING = [
    "The bookmaker's site lists the spread at two and a half.",
    "The trading desk puts the total goals at two and a half.",
    "The injury report lists the market line at two and a half.",
    "The club bulletin says the market has the spread at two and a half.",
]

#: The other way to launder it, and the reason the third party has to come FIRST.
#: A trailing source is agreeing with a claim rather than making one: "the spread
#: is too wide, per the club's report" reads the report as a witness to something
#: the sentence already asserted, which is exactly the shape the transfer is not
#: for. Without the ordering test these pass, because "report" is in the table and
#: appears in the clause.
TRAILING_SOURCE = [
    "The spread is too wide, per the club's report.",
    "The spread is two and a half and the injury report agrees.",
    "The handicap is generous, as the coaching staff see it.",
]


@pytest.mark.parametrize("text", TRAILING_SOURCE, ids=lambda t: t[:40])
def test_a_source_that_agrees_rather_than_asserts_is_not_a_transfer(text):
    """The subject-position half of `_clause_is_a_transfer`, on its own.

    The third-party table is about who is DOING the asserting. Naming a report
    at the end of a clause is not that -- the clause has already made its claim
    and the source is being cited as a witness -- and treating the two the same
    is how "the spread is too wide, per the report" would get through.
    """
    # Asserted through `_market_problems` rather than through the ordering helper,
    # for two reasons. It is the behaviour a reader experiences, and it keeps this
    # file importable against a `validate` that has no ordering helper at all --
    # which is what lets the red proof for the whole file be a list of failing
    # assertions rather than one collection error (see the PR body).
    assert _market_problems(NBA_FACTS, text), (
        f"a clause that cites a source after making its own claim was read as "
        f"that source's clause: {text!r} -> {_market_problems(NBA_FACTS, text)}"
    )


@pytest.mark.parametrize("text", BOOK_SOUNDING, ids=lambda t: t[:40])
def test_a_book_is_never_a_third_party_transfer(text):
    """The exemption cannot be reached by naming a market's own source.

    Without this, every one of these is a one-word edit away from the live leak:
    a model that wanted to claim a quote it does not have could attribute it to
    anybody the guard had not heard of.
    """
    assert _market_problems(NBA_FACTS, text), (
        f"a book-sounding source was accepted as a neutral third party: {text!r}"
    )


def test_the_attribution_rule_is_not_a_third_party_transfer_away():
    """`_market_problems` rule 1 stays BODY-scoped on purpose.

    The clause model is about *who owns a market word*. It is not a licence to
    say "X said it" in front of a sentence the guard has already decided is a
    book quote, so the attribution rule is not touched and this pins that it was
    not. Getting this wrong would turn every rejection into a sentence the model
    can talk its way past.
    """
    text = "The injury report says the market line is two and a half."
    assert _market_problems(NBA_FACTS, text), (
        "naming a third party in front of an attribution phrase laundered it"
    )


# --- the model's own clause, which must keep working ---------------------------

MODEL_OWNS = [
    "The total projects near 220.",
    "The model's total is 2.7.",
    "The model projects 220 points.",
    "The model's spread is a shade tighter than the other one.",
    "It rates Boston 3.4 points better, and the model's own margin is 3.4.",
]


@pytest.mark.parametrize("text", MODEL_OWNS, ids=lambda t: t[:40])
def test_a_clause_the_model_owns_is_still_exempt(text):
    """The control for every test above.

    Scoping the exemption to a clause must not make it useless. This is the
    commonest honest shape the prompt asks for -- "the model", "the projection"
    instead of "the line" -- and a rule that started rejecting it would push the
    model back into the phrasings above.
    """
    assert _named_markets(text) == set(), f"model-owned clause wrongly flagged: {text!r}"


def test_the_exemption_still_loses_to_an_attribution_phrase_in_the_same_clause():
    """Unchanged from `test_market_words_false_positives.py`, and repeated here
    because it is the one sentence that is both: "the model's total, which is what
    the market line says" attributes a figure to a book AND talks about the
    model. Bounding the exemption to a clause does not make it beat an
    attribution phrase."""
    text = "The model's total is 2.7, which is what the market line says."
    assert _market_problems(NBA_FACTS, text)


# --- the honest answers the rule was never about -------------------------------

def test_ordinary_english_still_names_no_market_at_all():
    """The control the whole rule rests on, kept beside the new boundary.

    Every sentence here is one the repo already pins as honest in
    `test_bare_line_references.py` and `test_market_words.py`. None of them is
    in scope for a clause model, and a splitter wide enough to reach one of them
    would be a splitter that invents clause boundaries.
    """
    for text in (
        "the line between favourite and also-ran is thinner than usual",
        "Both teams sit on the same line this season.",
        "The line to beat is a steep climb.",
        "A good number of passes found the target.",
        "Total commitment from midfield.",
        "Boston is still recovering from the road trip.",
    ):
        assert _named_markets(text) == set(), f"ordinary English named a market: {text!r}"
        assert _market_problems(NBA_FACTS, text) == [], f"rejected: {text!r}"
    # "The implied order was never in doubt." names `implied` and does not, and
    # is the reason the two assertions above are not one assertion: `implied` is
    # a probability market, so it is named but never nameable-without-a-quote,
    # and `_market_problems` steps over it. Asserted separately rather than
    # dropped, because "the trigger fired" and "the reader got the template" are
    # different states and only one of them costs a summary.
    implied = "The implied order was never in doubt."
    assert _market_problems(NBA_FACTS, implied) == [], f"rejected: {implied!r}"


def test_an_honest_answer_about_a_quoted_market_still_passes_end_to_end():
    """Nothing in this file may have disarmed the rule.

    NBA 2026-09-29 shipped an answer claiming a book quote that did not exist.
    The replacement has to pass, or the work here is silence rather than honesty.
    """
    honest = ("The model has Boston at 65%. The market line of BOS by 2.0 is close "
              "to the model's margin.")
    assert _market_problems(_quoted_nba(), honest) == []


def test_pl_prose_naming_a_market_pl_carries_is_still_untouched():
    """A sport whose facts DO quote their own line, saying nothing unusual."""
    for text in ("The total goals figure is the tightest part of this one.",
                 "The result market barely separates these two."):
        assert _market_problems(PL_FACTS, text) == [], f"rejected: {text!r}"
