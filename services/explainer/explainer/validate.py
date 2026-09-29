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

from .contract import DIRECTIONS, PSEUDO_MARKETS, as_dict, market_keys
from .template import DEFAULT_MARKET_LINE_KEY, MARKET_LINE_KEY

BANNED = ["lock", "bet", "betting advice", "hammer", "guaranteed", "sure thing", "value play"]
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED) + r")s?\b", re.I)
_NUM_RE = re.compile(r"[-−+]?\d+(?:,\d{3})*(?:\.\d+)?%?")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REBUILT_WORDS = ("rebuilt", "after kickoff", "after the start", "after the session")

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
MAX_FACTORS = 4


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
#: Keys are the contract's own vocabulary, so a market named here is one the
#: panel can resolve.
#:
#: "line" alone is deliberately NOT a trigger. It is far too common in ordinary
#: English — "the line between favourite and also-ran" — and a rule that fired on
#: it would reject honest prose to catch one sentence. It fires only inside the
#: attribution phrases below, which cannot mean anything else.
#: Each entry is (market keys it can mean, is-a-line-market).
#: A line market needs a quote to be nameable; a probability market does not,
#: because "the moneyline" names the thing the panel already draws.
MARKET_WORDS: dict[str, tuple[tuple[str, ...], bool]] = {
    "moneyline": (("moneyline",), False),
    "spread": (("spread", "handicap"), True),
    "total": (("total", "total_goals", "over_under"), True),
    "implied": (("implied",), False),
}
#: Phrases that assert a figure belongs to a book. These are what make the
#: live sentence false; a bare "spread" or "total" is much weaker and is handled
#: by the quoted-market rule instead.
#:
#: "covering"/"covers" are here rather than in MARKET_WORDS for a reason worth
#: stating: covering a spread is only a meaningful claim if a book quoted one,
#: so it is an assertion about the book, not a way of naming a market. Treating
#: it as a bare market word would let "Miami covering the spread" through on a
#: sport with no spread at all.
ATTRIBUTION_PHRASES: tuple[str, ...] = (
    "market line", "market's line", "market margin", "market total",
    "market price", "market odds", "money line", "the book", "the books",
    "the market has", "the market sits", "the market is", "point spread",
    "over/under", "over-under", "the implied probability", "quoted at",
    "covering", "covers", "against the spread", "against the total",
)
#: Single words that name a market, for the exists-but-unquoted case.
_MARKET_WORD_RE = re.compile(
    r"\b(?:spread|handicap|money\s?line|total\s+goals|total|implied)\b", re.I
)
_ATTRIBUTION_RE = re.compile(
    "|".join(re.escape(p) for p in ATTRIBUTION_PHRASES), re.I
)


def _named_markets(body: str) -> set[str]:
    """Concepts this prose names, in either spelling.

    A concept the prose explicitly attributes to the MODEL is not a market
    claim. "The total projects near 220" and "the model's spread" are the model
    talking about itself, which is the honest case and the common one — and the
    prompt already tells the model to say "the model" or "the projection" rather
    than "the line" for exactly this. Exempting it is what stops the guard from
    rejecting the sentence it is trying to produce.
    """
    low = body.lower()
    found: set[str] = set()
    for concept, (keys, _) in MARKET_WORDS.items():
        # `money line` and `total goals` are two words; the contract key is
        # `moneyline`, so the match has to tolerate the space.
        # Built outside the f-string: Python 3.11 (the image's) rejects a
        # backslash inside an f-string expression; 3.12+ allows it, which is how
        # this shipped green locally and crash-looped the service.
        money_line = r"money\s?line"
        if any(re.search(rf"\b{re.escape(k).replace('moneyline', money_line)}\b", low)
               for k in keys):
            if _OWNED_BY_MODEL_RE.search(low) and not _ATTRIBUTION_RE.search(low):
                continue
            found.add(concept)
    return found


#: "the model's own figure", said out loud. Only exempts a market word when the
#: sentence is not ALSO making a market claim — "the model's total is 2.7, which
#: is what the market line says" is still a claim about the book.
_OWNED_BY_MODEL_RE = re.compile(
    r"\b(?:model'?s?|model|projection|projected|projects|projects? near|forecast|"
    r"our|algorithm|it expects|we expect)\b",
    re.I,
)


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
    for concept in _named_markets(body):
        keys, is_line = MARKET_WORDS[concept]
        if concept in PSEUDO_MARKETS or not is_line:
            continue
        if not (set(keys) & present):
            problems.append(
                f"the text names a market the {sport} facts do not carry: {concept} "
                f"(present: {', '.join(sorted(present)) or 'none'})"
            )
        elif not (set(keys) & quoted):
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
    allowed = market_keys(facts) | set(PSEUDO_MARKETS)
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
    problems.extend(_verdict_problems(facts, body))
    problems.extend(_market_problems(facts, body))
    return problems
