"""The main guard against invented numbers: every figure the model writes
must come from the facts or the news it was given. Also shape, length,
banned words, and the rebuilt-pick disclosure.

v2 changed the shape the model returns and nothing about any of those guards. A
factor references a market by key and carries a direction; the panel resolves the
key and draws the figures itself. So the number pool still runs over the prose —
a digit in a factor is as invented as a digit in a section — and the
outcome-verdict check still has to see a claim wherever the prose now lives.
"""
from __future__ import annotations

import json
import re

from .contract import DIRECTIONS, PSEUDO_MARKETS, as_dict, market_keys, matchup_rows
from .template import DEFAULT_MARKET_LINE_KEY, MARKET_LINE_KEY

BANNED = ["lock", "bet", "betting advice", "hammer", "guaranteed", "sure thing", "value play"]
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED) + r")s?\b", re.I)
_NUM_RE = re.compile(r"[-−+]?\d+(?:,\d{3})*(?:\.\d+)?%?")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REBUILT_WORDS = ("rebuilt", "after kickoff", "after the start", "after the session")
#: What the text may say instead when the facts refuse to place a pick in time.
#: The rule is TIMING-SPECIFIC: the phrase must appear in a clause about the pick's
#: timing (pick, timing, made before, session, kickoff, tip-off), not as a
#: standalone word like "unknown" which could refer to weather, lineup, etc.
#: This prevents "The weather is unknown" from satisfying the disclosure rule.
UNVERIFIED_PHRASES = (
    "not verified", "unverified", "not established",
    "cannot be confirmed", "could not be confirmed",
    "no session time", "no kickoff time", "no tip-off time",
    "timing is not", "timing not", "timing could not",
    "cannot be shown as made before",
    "could not be shown as made before",
    "schedule did not provide",
)

#: Word caps for the v2 body. A verdict line inherits v1's 18-word headline cap;
#: a factor headline and sentence are new, and are tighter because a factor is
#: one row of a panel rather than a paragraph beside it. There is deliberately
#: **no minimum**: v1 demanded 120-220 words, and a v2 body is short by
#: construction because the figures are drawn rather than written. A floor kept
#: from v1 would reject the honest short answer and push the model into padding.
MAX_VERDICT_WORDS = 18
MAX_HEADLINE_WORDS = 10
MAX_FACTOR_WORDS = 35
MIN_FACTORS = 2
#: Raised 4 -> 5 with the Edge / Risk / Price redesign: two duel rows (one toward
#: the pick, one against it) on top of the four the old cap allowed, and the
#: design says the Price row appears only when a quoted line exists, so a full
#: body is five rows rather than four.
#:
#: **Equal to `template.MAX_FACTORS`, and `test_the_cap_is_five_on_both_sides`
#: holds that.** The template is what a reader gets when the model's body fails
#: this check, so the two caps disagreeing would mean the service accepts bodies
#: its own fallback would never produce — the drift spec §8 forbids. The
#: per-factor length rules are unchanged.
MAX_FACTORS = 5


#: Words that name a MARKET rather than a figure, and the market key each one
#: implies. The guard is about the market being *named*, not about a number:
#: every number rule above already passed, because the number was real.
#:
#: The failure this exists for is live output, not a hypothetical. Against NBA
#: game 401909903, whose facts carry a `spread` market holding the MODEL's own
#: margin (`line: "BOS by 1.9"`, and no `market_line` at all), the deployed model
#: wrote:
#:
#:     "The market line of BOS by 1.9 sits very close to the model's
#:      calculated margin of about 1.9 points."
#:
#: `1.9` is in the facts, so every existing rule passed. The sentence was still
#: false: it attributed the model's own number to the market, and told a reader
#: two independent sources agreed when there was one. A number check cannot see
#: this, because nothing about the number was wrong.
#:
#: Keys are the contract's own vocabulary (`contract.market_keys`), so a market
#: named here is one the panel can actually resolve.
#:
#: "line" alone is deliberately NOT a trigger. It is far too common in ordinary
#: English — "the line between favourite and also-ran" — and a rule that fired on
#: it would reject honest prose to catch one sentence. It fires only in the
#: specific compounds below, which cannot mean anything else.
#: Words that name a MARKET rather than a figure, and the market keys each can
#: mean. The guard is about the market being *named as the market's*, not about
#: a number: every number rule above already passed, because the number was real.
#:
#: The failure this exists for is live output, not a hypothetical. Against NBA
#: game 401909903 the deployed model wrote:
#:
#:     "The market line of BOS by 1.9 sits very close to the model's
#:      calculated margin of about 1.9 points."
#:
#: and a verdict reading "The model leans slightly toward Miami covering the
#: spread". That game's facts DO carry a `spread` entry — and it is the trap.
#: For NBA, `line` holds the MODEL's own margin and the book's is `market_line`
#: (`template.MARKET_LINE_KEY` says so, and `tests/test_template_quoted_line.py`
#: pins it); this game has no `market_line`. So the entry describes the model
#: only, there was no quote, and the sentence told a reader the book agreed
#: with the model. `1.9` is in the facts, so every number rule passed.
#:
#: "Does this market exist" is therefore the wrong question — the key was right
#: there. The question is whether the market is **quoted**: a `spread` the facts
#: carry but never sourced to a book is the model's own projection wearing a
#: market's name, and prose may not call it the market's.
#:
#: Each entry is (market keys it can mean, is-a-line-market).
#:
#: **`total` lists `total` itself as a key it can mean**, which it did not until
#: the trigger measurement in `tools/measure_trigger_fps.py`. That tool runs the
#: trigger layer over every honest sentence in this repo and found one
#: false positive: `test_market_words.py`'s own fixture sentence "The total goals
#: figure is tight." was reported as naming a market NBA's facts do not carry --
#: NBA names that market `total`, this row resolved the prose concept to
#: `("total_goals", "over_under")` only, `set(keys) & present` came out empty, and
#: the guard told a reader the sentence was about a market that was on screen.
#: The problem text even printed it: "names a market the nba facts do not carry:
#: total (present: moneyline, spread, total)". Naming a key the facts actually
#: carry, in the same row the facts are checked against, is the vocabulary
#: disagreeing with itself.
#:
#: It is added beside `total_goals` rather than in place of it, so a sport that
#: names the market either way resolves it. `test_the_total_concept_resolves_a_key`
#: in `test_market_words.py` pins the shape.
#: A line market needs a quote to be nameable; a probability market does not,
#: because "the moneyline" names the thing the panel already draws.
MARKET_WORDS: dict[str, tuple[tuple[str, ...], bool]] = {
    "moneyline": (("moneyline",), False),
    "spread": (("spread", "handicap"), True),
    # `total_goals` and `over_under` are the CONTRACT keys; bare `total` is
    # deliberately not among them. "Total commitment from midfield" and "a total
    # of two chances" are ordinary English and were being reported as naming a
    # market the facts do not carry. The contract's own vocabulary is what gets
    # matched — a word the panel cannot resolve is not a market reference.
    "total": (("total_goals", "total", "over_under"), True),
    "implied": (("implied",), False),
}
#: The words PROSE uses for each concept, as opposed to the contract keys in
#: `MARKET_WORDS` above. Kept apart because they are different vocabularies and
#: conflating them is how bare `total` came to reject "Total commitment from
#: midfield": the contract has no `total` key, so the word in prose could not be
#: checked against it at all, and the only way to make it work was to add
#: `total` to the keys — which is a word the panel cannot resolve.
PROSE_WORDS: dict[str, tuple[str, ...]] = {
    "moneyline": ("moneyline", "money line"),
    "spread": ("spread", "handicap", "point spread"),
    # Written as a regex, so the separator may be a slash, a hyphen or a space --
    # all three are written in practice, and a guard that matched only one of
    # them would be right by luck.
    "total": (r"total\s+goals", r"over\s*[/-]?\s*under"),
    "implied": ("implied",),
}

#: Phrases that assert a figure belongs to a book. These are what make the
#: live sentence false; a bare "spread" or "total" is much weaker and is handled
#: by the quoted-market rule instead.
#:
#: "covering"/"covers" are here rather than in MARKET_WORDS for a reason worth
#: stating: covering a spread is only a meaningful claim if a book quoted one,
#: so it is an assertion about the book, not a way of naming a market.
#:
#: **Word boundaries, and they are load-bearing.** The first version of this had
#: no `\b` anchors and a plain alternation, so it matched inside longer words:
#:
#:     "recovering"    contains "covering"
#:     "discovers"     contains "covers"
#:     "uncovers"      contains "covers"
#:     "the bookings"  contains "the book"
#:
#: "Boston is still recovering from the road trip" was therefore reported as a
#: market attribution and the reader got the template instead of the summary —
#: a guard that fires on ordinary English is one the model learns to avoid by
#: writing less, which is the same failure as the one this rule was added to fix.
#: Every alternative is anchored on both sides.
ATTRIBUTION_PHRASES: tuple[str, ...] = (
    "market line", "market's line", "market margin", "market total",
    "market price", "market odds", "money line", "the book", "the books",
    "the market has", "the market sits", "the market is", "point spread",
    "over/under", "over-under", "the implied probability", "quoted at",
    "covering", "covers", "against the spread", "against the total",
    # BARE references to the book, with no "market" in front of them. These are
    # the live NBA leak: "Very close to the line." passed while "The market is
    # right there." was caught, which is an asymmetry with no principle behind
    # it — a book quote is a book quote however the sentence names it, and NBA
    # carries no quoted line at all.
    #
    # Every one is a two-or-more-word phrase, and that is what keeps this from
    # becoming the "line" mistake this file has already made once. A bare "line"
    # cannot be a trigger: "the line between favourite and also-ran" is ordinary
    # English, and rejecting it would reject the product to catch one sentence.
    # "close to the line", "the number", and "pick'em" cannot mean anything else.
    "close to the line", "just off the line", "on the line", "above the line",
    "below the line", "under the line", "over the line", "the line sits",
    "the number is", "the number sits", "quick number", "the total sits",
    "pick'em", "pick em", "picks'em",
)
#: Words that name a market, for the exists-but-unquoted case.
#:
#: **`total` was a bare alternative and had to become a phrase.** Found by a test
#: written for a different fix, which is the usual way these surface: "Total
#: commitment from midfield" and "A total of two chances" were both reported as
#: naming a market the facts do not carry, and a reader got the template instead
#: of the summary. Same shape as the "line" mistake, one rule along — a single
#: common English noun cannot be a market marker. "total goals" and "over/under"
#: are unambiguous, so those are what it matches now.
_MARKET_WORD_RE = re.compile(
    r"\b(?:spread|handicap|money\s?line|total\s+goals|over\s?/?\s?under|implied)\b", re.I
)
_ATTRIBUTION_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in ATTRIBUTION_PHRASES) + r")\b", re.I
)

#: "the model's own figure", said out loud.
#:
#: **Scoped per sentence, deliberately.** The first version searched the whole
#: joined body, so ONE factor saying "the model" exempted every bare market word
#: in every other factor — the guard silently switched itself off for the rest
#: of the answer. It is applied below per sentence and per field, so a factor
#: that says "the model's total is 2.7" is exempt and a factor beside it that
#: says "The spread favours Boston" is still checked.
_OWNED_BY_MODEL_RE = re.compile(
    r"\b(?:model'?s?|model|projection|projected|projects|forecast|"
    r"our|algorithm|it expects|we expect)\b",
    re.I,
)
#: Sentence splitter for the same reason. Deliberately simple and deliberately
#: NOT a dependency: a prose guard that silently fails to split leaves the
#: false positive in place, which is the bug being fixed.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
#: Clause splitter, and the second step of the same argument. A sentence is not a
#: scope either, for the reason `test_validator_clause_scope.py` records:
#:
#:     "The model rates Boston 3.4 points better, and the spread is fair at two
#:      and a half."
#:
#: names a spread the facts do not quote, and said "the model" in a clause that
#: has nothing to do with it. Ownership is a property of a CLAUSE -- who the
#: sentence says is doing the asserting -- so this is the unit the exemption is
#: allowed to travel through.
#:
#: Split on `;`, `:`, an em dash and the coordinating conjunctions, because those
#: are the boundaries English actually marks, and a comma followed by a
#: conjunction is the commonest one. A BARE comma is not a boundary: "Boston 3.4
#: points better, a little more than the line the market is offering" is one
#: clause, and splitting it would put "the model" and "the market is offering" in
#: different clauses -- which is the same tunnel this whole change exists to
#: close, entered from the other side.
_CLAUSE_SPLIT_RE = re.compile(
    r";|:|—|\s+--\s+|,\s*(?:and|but|so|then|yet|while|though|although|whereas)\b",
    re.I,
)
#: A third party that can be the CLAUSE's subject, and so can own what the clause
#: says. This is the permit the review asked for: "the injury report lists him as
#: doubtful" and "the coach calls the spread too wide" are those parties
#: asserting things, and reading them as the model attributing a figure to a book
#: costs a reader their summary for a sentence that asserts nothing the facts
#: contradict.
#:
#: Every entry is a noun that names a SOURCE OF INFORMATION ABOUT A GAME --
#: medical, official or institutional -- and none of them is a market. A reader
#: who sees "the coach said" knows where the claim came from, which is exactly
#: what the rule above asks for and exactly what "the market line" does not give.
#:
#: Deliberately absent: `market`, `book`, `odds`, `price`, `line`. Those are not
#: third parties, they are the counterparty this guard exists to police, and
#: letting one of them into this table would hand every rejection a way out.
#: `_BOOK_SOUNDING_RE` below is what stops that from happening by accident, and
#: `test_a_book_is_never_a_third_party_transfer` is what holds it.
#:
#: **And a PARTICIPANT is not a source**, which is the second half of that
#: principle and the half that was missing. `side`, `sides`, `team`, `teams`,
#: `club` and `clubs` name the thing the sentence is *about* -- the two sides of
#: the game, the team being predicted -- and every one of them walked into the
#: permit, because the second gate (`_clause_is_a_transfer`'s ordering test) only
#: asks whether the noun sits before the market word. Measured on `origin/main`
#: (`bb91579`):
#:
#:     "The model likes Boston, and the side favours the spread."
#:         _market_problems(...) == []        # accepted
#:
#: `side` is before `spread`, nothing in the clause sounds like a book, so the
#: clause is somebody else's clause and the spread claim in it skips the quote
#: requirement -- against NBA, whose `spread` holds the MODEL's own margin and
#: carries no book quote at all. The reader is told a third party said it when
#: the model said it, which is the one sentence shape this rule exists to stop.
#:
#: `test`, `tests`, `update`, `updates`, `notes` and `news` went for a different
#: reason: they are event nouns. "An update on the squad" and "the notes on the
#: squad" are about a game and are not anybody's account of it, and a permit
#: keyed on them is a permit keyed on "the sentence mentions something
#: report-shaped". `medical team`, `injury report` and `league bulletin` all keep
#: working, because the SOURCE half of the compound is what matches.
#:
#: The cost, stated rather than discovered: "The news says the handicap is a
#: shade tighter" is now rejected unless a book quoted one, and the model was
#: given news to read. That is the same trade this file has made twice already
#: (`line` alone, bare `total`) and it is the safe side of it — a news-sourced
#: spread figure is exactly the unverified figure class — but it is a real
#: narrowing and `test_a_genuine_source_still_owns_its_own_clause` is what keeps
#: the sources that remain from shrinking further.
_THIRD_PARTY_RE = re.compile(
    r"\b(?:report|reports|reported|bulletin|bulletins|wire|release|releases|"
    r"headline|headlines|feed|filing|filings|coach|coaches|manager|managers|"
    r"staff|owner|owners|board|director|directors|"
    r"doctor|doctors|medical|medic|medics|injury|injuries|roster|scanner|"
    r"scanners|official|officials|umpire|umpires|referee|league|"
    r"conference|commissioner|coach's|diagnosis|scan|scans)\b",
    re.I,
)
#: Words that name the MARKET or a book, as a subject or an object. A clause that
#: holds one of these is never a third-party transfer, however innocent the rest
#: of the clause looks -- "the injury report lists the market line at two and a
#: half" is the laundering attempt, and it is one word away from a claim the
#: facts do not support.
#:
#: Bare `market` rather than "the market", because "the market" is how the guard
#: phrases itself in its own rules and "the markets" is how a sentence says the
#: same thing about a different game. Bare `line` and `number` are NOT here: they
#: are ordinary English, `test_bare_line_references.py` is the file that says so at
#: length, and `_ATTRIBUTION_RE` already handles them in unambiguous compounds.
_BOOK_SOUNDING_RE = re.compile(
    r"\b(?:market|markets|book|books|bookmaker|bookmakers|bookie|bookies|"
    r"sportsbook|sportsbooks|odds|price|prices|tipster|tipsters|handicapper|"
    r"handicappers|sharps?|whales?|trader|traders|desk|line|numbers?)\b",
    re.I,
)


def _sentences(text: str) -> list[str]:
    """Split prose into sentences, keeping the pieces non-empty.

    A field is also its own unit even if it holds several sentences, so the
    caller checks each field separately and this handles the within-field case.
    """
    return [s for s in (p.strip() for p in _SENTENCE_SPLIT_RE.split(text)) if s]


def _clauses(sentence: str) -> list[str]:
    """Split one sentence into clauses, keeping the pieces non-empty.

    Falls back to the whole sentence when a split would leave nothing, so a
    clause model can never turn a sentence into zero things to check -- the
    direction that matters, because a dropped clause is a dropped guard.
    """
    parts = [p.strip(" ,") for p in _CLAUSE_SPLIT_RE.split(sentence)]
    return [p for p in parts if p] or [sentence]


def _clause_is_a_transfer(clause: str) -> bool:
    """Whether some OTHER subject owns what this clause asserts.

    Three conditions, and the third is the one that keeps this from being a way
    to say anything:

    * somebody other than the model is named in it, and "somebody" means a SOURCE
      -- `_THIRD_PARTY_RE` holds no participant and no event noun, which is what
      stops "the side favours the spread" from reading as somebody else's claim;
    * nobody who names a book or a market is named in it, so the sentence cannot
      be pointing at the very counterparty the guard exists to check;
    * the third party comes BEFORE the market word, so it is the clause's
      subject and the market is what it is said to be doing. "The injury report
      calls the spread too wide" is a transfer; "the spread is two and a half
      and the injury report agrees" is not, and the position test is what tells
      them apart. Without it, prefixing any claim with any source would pass.

    **What the ordering test is not, and the residual it leaves.** It compares
    positions and nothing else, so it cannot tell a subject from an object, and a
    clause that names a real source in the middle still reads as that source's
    clause -- "and per the report the spread is two and a half" is a transfer.
    Closing that needs a subject parser, and a rule that guessed at subjects
    would start rejecting the honest sentences the third bullet is here to admit.
    What is left is bounded to clauses naming a genuine source, which is the
    case a reader can already see the source of, so it is stated rather than
    guessed at.
    """
    party = _THIRD_PARTY_RE.search(clause)
    if not party or _BOOK_SOUNDING_RE.search(clause):
        return False
    return not _named_market_positions(clause) or \
        party.start() < min(_named_market_positions(clause))


def _named_market_positions(clause: str) -> list[int]:
    r"""Where in this clause each market word sits, for the ordering test above.

    Raw-prefixed (the `r` before the quotes) rather than a bare docstring: the body
    spells a backslash-s in a docstring example, which is a SyntaxWarning on the
    way in. Not load-bearing -- but a warning printed on every import of the
    validator is how a real one stops being read.

    Built outside the f-string expression for the reason `_named_markets` says:
    Python 3.11, the image's, rejects a backslash inside an f-string expression,
    so the moneyline pattern cannot be written inline there and works only on
    3.12+. This is the second place in the file that has to spell it out, which
    is why the reason is repeated instead of pointed at.
    """
    low = clause.lower()
    money_line = r"money\s?line"
    out: list[int] = []
    for words in PROSE_WORDS.values():
        for word in words:
            pattern = rf"\b(?:{word})\b" if "moneyline" not in word \
                else rf"\b(?:{money_line})\b"
            match = re.search(pattern, low)
            if match:
                out.append(match.start())
                break
    return out


def _named_markets(body: str) -> set[str]:
    """Concepts this prose names, in either spelling.

    A concept the prose explicitly attributes to the MODEL is not a market
    claim. "The total projects near 220" and "the model's spread" are the model
    talking about itself, which is the honest case and the common one — and the
    prompt already tells the model to say "the model" or "the projection" rather
    than "the line" for exactly this.

    **Per clause, and that is the whole of the change.** The exemption used to be
    a single search over the whole body, so one factor saying "the model"
    disabled the guard for every other factor: `["The model has Boston at 65%.",
    "The spread favours Boston."]` named no market at all. Scoping it to the
    SENTENCE closed that case and left the next one open — "The model rates
    Boston 3.4 points better, and the spread is fair at two and a half" says
    "the model" in a clause that has nothing to do with the spread, and named no
    market either. Ownership is a property of a clause, so a clause is the unit.

    **And a clause somebody ELSE owns is exempt too**, which is the other half
    the review asked for. "The club injury report calls the spread too wide" is a
    third party asserting something about a line, and reading it as the model
    attributing a figure to a book rejects honest prose for the ordinary reason
    the model-ownership exemption exists to prevent. The transfer is narrow — see
    `_clause_is_a_transfer` — and it is bounded on the other side by the rules it
    does NOT touch: an attribution phrase anywhere in the clause still wins, and
    `_market_problems`' body-scoped attribution rule is untouched, so "the injury
    report says the market line is two and a half" is still rejected.
    """
    found: set[str] = set()
    for clause, transferred in _clauses_with_ownership(body):
        if transferred:
            continue
        # The attribution test stays INSIDE the model-ownership test, and this is
        # not a cosmetic nesting. "money line" and "the implied probability" are
        # BOTH entries in `ATTRIBUTION_PHRASES` and BOTH the unambiguous
        # spellings of their own markets, so a clause naming one still has to map
        # to its concept. Attribution defeats the MODEL's exemption; it does not
        # delete the market the sentence named. Hoisting it into its own `continue`
        # — which reads tidier and is what this did first — unmaps both and fails
        # `test_each_spelling_maps_to_its_market`.
        if _OWNED_BY_MODEL_RE.search(clause) and not _ATTRIBUTION_RE.search(clause):
            continue
        found |= _concepts_in(clause)
    return found


def _transferred_markets(body: str) -> set[str]:
    """Concepts named only inside a clause a THIRD PARTY owns.

    Separate from `_named_markets` rather than folded into it, and the split is
    the point: `_market_problems` asks two different questions of a market a
    third party named, and they have different answers.

    * "Does this market exist in the facts at all?" — YES still matters. A
      bundle carrying no `spread` cannot render one, so prose naming it leaves
      the reader with a claim about nothing, and who said it does not change
      that. A coach saying "the spread is too wide" on a bundle with no spread is
      wrong about the facts in the same way the model would be.
    * "Is this the model's own figure wearing a market's name?" — NO, and this is
      where the exemption earns its place. "The club injury report calls the
      spread too wide" attributes nothing to a book.

    So a transferred concept is checked for existence and exempted from the
    quote requirement, and keeping the two apart is what stops the permit from
    being a blanket one. Returning them from one function would have made the
    caller re-derive which is which, which is how the two rules drift into one.
    """
    found: set[str] = set()
    for clause, transferred in _clauses_with_ownership(body):
        if transferred and not _ATTRIBUTION_RE.search(clause):
            found |= _concepts_in(clause)
    return found


def _clauses_with_ownership(body: str) -> list[tuple[str, bool]]:
    """`(clause, owned by a third party)` for every clause in this prose."""
    return [(c, _clause_is_a_transfer(c))
            for sentence in _sentences(body) for c in _clauses(sentence)]


def _concepts_in(clause: str) -> set[str]:
    """The market concepts one clause names, in either spelling."""
    low = clause.lower()
    # Built outside the f-string: Python 3.11 (the image's) rejects a
    # backslash inside an f-string expression; 3.12+ allows it, which is how
    # this shipped green locally and crash-looped the service.
    money_line = r"money\s?line"
    found: set[str] = set()
    for concept, words in PROSE_WORDS.items():
        # Matched on the PROSE vocabulary, and the concept is then checked
        # against the CONTRACT keys. The two are separate on purpose: a word
        # the panel cannot resolve is not a market reference, and a contract
        # key that never appears in prose would make the rule unfireable.
        # The patterns are regexes already (`total goals`, `over/under`),
        # so they are used as written rather than escaped — escaping a
        # pattern would make it a literal and it would never match.
        if any(re.search(rf"\b(?:{w})\b" if "moneyline" not in w else rf"\b(?:{money_line})\b", low)
               for w in words):
            found.add(concept)
    return found


def _quoted_markets(facts: dict) -> set[str]:
    """Market keys the facts source to a book, as opposed to describing the model.

    A `spread`/`total` entry with a `line` is a quote for every sport except the
    ones that put their model's own wording in `line` — NBA. So the key list
    comes from `template.MARKET_LINE_KEY` rather than being re-derived here,
    which is what keeps the two files from disagreeing about the same fact.
    """
    sport = as_dict(facts).get("sport") or ""
    quote_keys = MARKET_LINE_KEY.get(sport, DEFAULT_MARKET_LINE_KEY)
    out: set[str] = set()
    for m in as_dict(facts).get("markets") or []:
        if not isinstance(m, dict):
            continue
        key = str(m.get("market") or "")
        if any(m.get(k) not in (None, "") for k in quote_keys):
            out.add(key)
    return out


def _market_problems(facts: dict, body: str) -> list[str]:
    """Prose may not attribute a figure to a market the facts do not quote.

    Note what this is NOT: it does not check that a number matches (the
    existing rules do that) and it does not check that a named market agrees
    with anything. It is one step earlier — whether there is a book to agree —
    and it is the step that let a real number be reported as the market's.
    """
    present = market_keys(facts)
    quoted = _quoted_markets(facts)
    low = body.lower()
    sport = as_dict(facts).get("sport") or "this sport"
    problems: list[str] = []

    # 1. An outright attribution to a book with nothing quoted anywhere.
    if _ATTRIBUTION_RE.search(low) and not quoted:
        problems.append(
            f"the text attributes a figure to the market, but no {sport} market in the "
            f"facts is sourced to a book (markets present: "
            f"{', '.join(sorted(present)) or 'none'})"
        )
        return problems

    # 2. A line market named while the facts only carry the model's own figure
    #    for it. This is the live case, and it is not caught by (1) when some
    #    other market IS quoted.
    #
    #    The two halves come from two places on purpose. A concept the prose
    #    claims as the MODEL's, or as nobody's, needs a quote to be nameable. A
    #    concept a THIRD PARTY named needs only for the market to exist -- see
    #    `_transferred_markets` for why those are different questions, and
    #    `test_a_third_party_transfer_is_about_the_market_and_the_facts_still_decide`
    #    for the case that keeps the second half honest.
    transferred = _transferred_markets(body)
    for concept in _named_markets(body) | transferred:
        keys, is_line = MARKET_WORDS[concept]
        if concept in PSEUDO_MARKETS or not is_line:
            continue
        if not (set(keys) & present):
            problems.append(
                f"the text names a market the {sport} facts do not carry: {concept} "
                f"(present: {', '.join(sorted(present)) or 'none'})"
            )
        elif not (set(keys) & quoted) and concept not in transferred:
            problems.append(
                f"the text calls the {concept} the market's, but the {sport} facts carry "
                f"only the model's own figure for it and no book quote "
                f"({', '.join(sorted(set(keys) & present))} present, quoted: "
                f"{', '.join(sorted(quoted)) or 'none'})"
            )
    return problems


def _candidates(token: str) -> list[tuple[float, float]]:
    """(value, tolerance) readings of a written number. The tolerance is
    rounding of what was written, half a unit of its last digit: "3.4"
    covers 3.35–3.45, "48" covers 47.8, "62%" covers 61.5–62.5% (never
    64%)."""
    t = token.replace("−", "-").replace(",", "")
    pct = t.endswith("%")
    t = t.rstrip("%")
    decimals = len(t.split(".")[1]) if "." in t else 0
    v, tol = float(t), 0.5 * 10 ** -decimals
    if pct:
        return [(v / 100, tol / 100), (v, tol)]  # "62%" matches 0.62 or 62
    return [(v, tol)]


def _values(token: str) -> list[float]:
    return [v for v, _ in _candidates(token)]


def _written_sign(token: str) -> int:
    """The direction the prose asserted: -1, 0 for none written, +1.

    `_candidates` strips the sign, which is right for magnitude and wrong for
    truth: "BAL -2.5" and "BAL +2.5" are opposite claims about the same game,
    and a validator that cannot see the difference accepts either. Three-valued
    rather than a boolean, because a bare "2.5" asserts no direction and must
    keep passing.
    """
    head = token.lstrip()
    # U+2212 MINUS SIGN is a MINUS. Reading it as a plus is the kind of thing
    # `test_true_minus_and_rounding_are_tolerated` exists to catch, and it did:
    # every "−2.50" in honest prose was being treated as "+2.50" and rejected as a
    # sign flip against its own fact.
    if head.startswith("-") or head.startswith("\u2212"):
        return -1
    if head.startswith("+"):
        return 1
    return 0


def _is_margin_key(key: str) -> bool:
    """A margin's sign is a convention; a line's sign is the claim."""
    return "margin" in key


def numbers_in(text: str) -> set[float]:
    return {v for tok in _NUM_RE.findall(text) for v in _values(tok)}


def _pool(node, key: str = "") -> tuple[set[float], set[float]]:
    """(numbers, written percents) a text may cite. Ids and dates/times are
    left out: their digits ("00:20", "2026-10-05") would otherwise excuse
    invented figures."""
    nums: set[float] = set()
    pcts: set[float] = set()
    # Magnitudes whose sign is a convention, so a written sign may be flipped
    # against them. A line's may not.
    flippable: set[float] = set()

    def walk(n, k=""):
        if isinstance(n, bool) or n is None:
            return
        if isinstance(n, (int, float)):
            nums.add(float(n))
            if _is_margin_key(k):
                flippable.add(abs(float(n)))
        elif isinstance(n, str):
            if k == "id" or k.endswith("_id") or _DATE_RE.search(n):
                return
            for tok in _NUM_RE.findall(n):
                v = _candidates(tok)[-1][0]
                (pcts if tok.endswith("%") else nums).add(v)
                if tok.endswith("%"):
                    nums.add(v)
                elif _is_margin_key(k):
                    flippable.add(abs(v))
        elif isinstance(n, dict):
            for kk, v in n.items():
                walk(v, kk)
        elif isinstance(n, list):
            for v in n:
                walk(v, k)

    walk(node, key)
    return nums, pcts, flippable


def _sign_ok(sign: int, magnitude: float, fact: float, flippable: set[float]) -> bool:
    """Whether a written direction is one the facts support.

    No sign written means the prose cited a magnitude, which any fact of that
    size supports — people write "2.5" for a 2.5-point line without asserting a
    direction. A sign written IS a claim, and it has to agree with the fact's own
    direction, unless the fact is a margin: `model_margin: 3.4` is
    home-minus-away, so a sentence about the away team legitimately carries the
    other sign, and rejecting that would cost a reader their explanation.
    """
    if sign == 0:
        return True
    if fact == 0:
        return False
    if sign * fact > 0:
        return True
    return abs(fact) in flippable


def _known(token: str, nums: set[float], pcts: set[float], flippable: set[float]) -> bool:
    t = token.replace("\u2212", "-").replace(",", "")
    sign = _written_sign(token)
    decimals = len(t.rstrip("%").split(".")[1]) if "." in t else 0
    tol = 0.5 * 10 ** -decimals
    v = abs(float(t.rstrip("%")))
    if t.endswith("%"):
        # A percentage has no direction: "-62%" is not a thing anyone means, and
        # accepting it would be a free pass for any sign flip dressed as a percent.
        if sign != 0:
            return False
        # A percent is a probability (a fraction in the facts) or a percent
        # the facts themselves wrote; never a raw count like 41 hits.
        return any(abs(v / 100 - p) <= tol / 100 + 1e-9 for p in nums if 0 <= p <= 1) \
            or any(abs(v - q) <= tol + 1e-9 for q in pcts)
    if decimals == 0:
        # A whole number may round a decimal (48 for 47.8) but not a half
        # line (46 for 45.5), and never stands for a probability.
        return any((abs(v - abs(p)) < tol or v == abs(p)) and _sign_ok(sign, v, p, flippable)
                   for p in nums if abs(p) >= 1 or p == 0)
    return any(abs(v - abs(p)) <= tol + 1e-9 and _sign_ok(sign, v, p, flippable)
               for p in nums)


# A verdict claim is a SUBJECT plus a VERB, not a word. "won" and "right" both
# occur constantly in honest football prose — "Baltimore won the toss", "the
# right read on the weather" — and a keyword list would reject all of it, which
# is its own honesty failure: the service falls back to the template and the
# panel quietly loses the explanations it exists for. So the claim must be
# about the pick, and only then does the verb mean anything.
#
# A false rejection costs a reader some prose. A false acceptance costs them a
# lie. When the two conflict, the pattern is deliberately the tighter one.
_PICK_REF = (
    r"(?:this|that|the|our)\s+"
    r"(?:pick|call|read|forecast|projection|lean|side|bet\b|tip)"
)
_WON_VERB = r"(?:won|win|winner|right|correct|landed|came\s+in|struck|hit|delivered)"
_LOST_VERB = r"(?:wrong|lost|missed|miss|fell\s+short|did\s*n[o']?t\s+land|didn'?t\s+land|not\s+land)"

# A bounded gap rather than "anywhere later in the sentence": the claim has to
# be about the same clause, or "the pick is close. Baltimore won." trips it.
_GAP = r"(?:\s|\w|[^\w\s]){0,32}?"

CLAIMS_WON = re.compile(
    rf"{_PICK_REF}{_GAP}(?:{_WON_VERB})"
    # "picked the winner" needs no subject: nobody writes it about anything else.
    rf"|pick(?:s|ed)?{_GAP}the\s+winner",
    re.I,
)
CLAIMS_LOST = re.compile(rf"{_PICK_REF}{_GAP}(?:{_LOST_VERB})", re.I)


def _verdict_problems(facts: dict, body: str) -> list[str]:
    """Whether the prose may claim an outcome the facts do not support.

    The facts carry the ground truth, and they are careful about it: a rebuilt
    pick deliberately has NO `pick_won`, because there is no honest verdict to
    give. So "the facts do not say" and "the facts say no" are different states
    and both forbid a claim, for different reasons.
    """
    problems = []
    if not CLAIMS_WON.search(body) and not CLAIMS_LOST.search(body):
        return problems

    pick = facts.get("pick")
    if not pick:
        # There is no pick, so there is nothing to have been right about.
        problems.append("the text claims a verdict but the facts carry no pick")
        return problems

    if facts.get("pick_timing") == "rebuilt":
        # A pick made after the start is shown and never judged. The facts omit
        # `pick_won` here precisely so nothing can grade it — prose that
        # nonetheless calls it right or wrong is reading a verdict that does not
        # exist, and "it happened to be right anyway" is the exact thing the
        # honesty rule exists to prevent being invisible.
        problems.append(
            "no verdict may be claimed for a pick rebuilt after the start"
        )
        return problems

    won = (facts.get("result") or {}).get("pick_won")
    if won is None:
        problems.append("the text claims a verdict but the facts record none")
    elif won is False and CLAIMS_WON.search(body):
        problems.append("the text claims a verdict the facts contradict: the pick lost")
    elif won is True and CLAIMS_LOST.search(body):
        problems.append("the text claims a verdict the facts contradict: the pick won")
    return problems


def validate(output: dict, facts_json: str, news_json: str) -> list[str]:
    """Problems with a model's output; [] means it may be shown."""
    # The facts are parsed BEFORE the shape check, because the key rule below
    # needs the market list. They are parsed defensively: a body so malformed
    # that `output` is not a dict must still produce a list of problems rather
    # than a TypeError out of a guard whose whole job is to fail safely.
    try:
        facts = json.loads(facts_json) if facts_json else {}
    except ValueError:
        facts = {}
    if not isinstance(facts, dict):
        facts = {}

    factors = output.get("factors") if isinstance(output, dict) else None
    verdict = output.get("verdict") if isinstance(output, dict) else None
    if not isinstance(verdict, str) or not isinstance(factors, list) \
            or not all(isinstance(f, dict) for f in factors):
        return ["output must be {verdict: str, factors: [{key, direction, headline, text}]}"]

    problems = []
    if not MIN_FACTORS <= len(factors) <= MAX_FACTORS:
        problems.append(f"needs {MIN_FACTORS}-{MAX_FACTORS} factors, got {len(factors)}")
    if len(verdict.split()) > MAX_VERDICT_WORDS:
        problems.append(f"verdict is over {MAX_VERDICT_WORDS} words")

    # A key the facts do not carry is a problem rather than something to drop
    # here: `contract.resolve_factors` already dropped it on the way in, so
    # reaching this point means the drop was bypassed. An absent market renders
    # *nothing* (spec §6), so the alternative is a row with nothing in it.
    #
    # `matchup:<id>` is in the vocabulary for the same reason a market is: a duel
    # the facts do not carry is a claim about a matchup nobody computed, and the
    # panel would draw an empty row for it. The model's own direction is NOT
    # checked against the duel's `toward_pick` here — that is `contract.slot_for`,
    # and it downgrades the row to `context` rather than rejecting the whole body,
    # because a model disagreeing with the code about one row is a reason to show
    # less, not to cost the reader every other row.
    allowed = market_keys(facts) | set(PSEUDO_MARKETS) | set(matchup_rows(facts))
    for i, f in enumerate(factors):
        if f.get("direction") not in DIRECTIONS:
            problems.append(f"factor {i + 1} direction must be one of {DIRECTIONS}")
        if f.get("key") not in allowed:
            problems.append(f"factor {i + 1} names {f.get('key')!r}, which the facts do not carry")
        if len(str(f.get("headline", "")).split()) > MAX_HEADLINE_WORDS:
            problems.append(f"factor {i + 1} headline is over {MAX_HEADLINE_WORDS} words")
        if len(str(f.get("text", "")).split()) > MAX_FACTOR_WORDS:
            problems.append(f"factor {i + 1} text is over {MAX_FACTOR_WORDS} words")

    # No band rule: the band is computed by `contract.band_for` from the facts,
    # never supplied by the model (§13a). Validating a field nothing writes
    # would be a check that cannot fail.
    texts = [verdict]
    for f in factors:
        texts.append(str(f.get("headline", "")))
        texts.append(str(f.get("text", "")))
    body = " ".join(texts)
    # "Hammers" is West Ham's nickname, not betting slang.
    banned = [m.group(0) for m in _BANNED_RE.finditer(body) if m.group(0) != "Hammers"]
    if banned:
        problems.append(f"banned word: {banned[0]!r}")

    fn, fp, ff = _pool(facts)
    nn, np_, nf = _pool(json.loads(news_json or "[]"))
    nums, pcts, flippable = fn | nn, fp | np_, ff | nf
    unknown = sorted({tok for tok in _NUM_RE.findall(body) if not _known(tok, nums, pcts, flippable)})
    if unknown:
        problems.append("number not in the facts or news: " + ", ".join(unknown))

    if facts.get("pick_timing") == "rebuilt" and not any(w in body.lower() for w in REBUILT_WORDS):
        problems.append("pick is rebuilt but the text doesn't say it was rebuilt after the start")
    if facts.get("pick_timing") == "unknown":
        # Timing-specific check: the disclosure must appear in a clause about the
        # pick's timing. A bare "unknown" anywhere in the text is not enough.
        body_lower = body.lower()
        timing_context_re = re.compile(
            r"(?:pick|timing|made before|session|kickoff|tip[- ]?off|start|schedule).*("
            + "|".join(re.escape(p) for p in UNVERIFIED_PHRASES)
            + r")|("
            + "|".join(re.escape(p) for p in UNVERIFIED_PHRASES)
            + r").*(?:pick|timing|made before|session|kickoff|tip[- ]?off|start|schedule)",
            re.I
        )
        if not timing_context_re.search(body_lower):
            problems.append(
                "pick timing is not established but the text does not say so"
            )
    problems.extend(_verdict_problems(facts, body))
    problems.extend(_market_problems(facts, body))
    return problems
