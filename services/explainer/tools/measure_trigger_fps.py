#!/usr/bin/env python3
"""Measure how often `validate`'s PHRASE triggers fire on honest prose in this repo.

Run from `services/explainer`:
    PYTHONPATH=. uv run --python 3.11 --extra dev --no-sync python tools/measure_trigger_fps.py

Answers reviewer item 4(b). The number is not an estimate: it is the count of
sentences in the corpus that a trigger's own regex matches, and every sentence
that matched is printed with the trigger named, so the table can be checked by
reading it rather than trusted.

**Why this is a file and not a paragraph of numbers.** The trigger tables in
`validate.py` have each grown by one entry at a time, every one of them after a
live sentence got through or a reader got the template instead of the summary,
and there is no record of what they cost on text that was already honest. A rate
measured once, by a script, is reproducible; a rate asserted from memory is a
claim about a table somebody has since edited.

**What counts as the corpus, and why it is small.** Honest sentences that already
exist in this repository, from three sources and no others:

1. `explainer/template.py` -- every non-docstring string in the module. Those
   strings are the copy the fallback renders for a reader.
2. `tests/test_*.py` -- the prose a fixture hands to the validator: dict values
   under `verdict` / `headline` / `text`, the fixture constants that hold them
   (`_VERDICT`, `_SPREAD`, `_RECORD`, `_CONTEXT`, `PADDING_*`), and the string
   arguments of the `good()` / `body()` builders that build them.
3. `docs/superpowers/specs/*.md` -- the example sentences inside fenced code
   blocks.

Two deliberate exclusions, both of which change the number and both of which are
stated here because the number is only as good as them:

* **docstrings and `#` comments are not harvested.** A docstring in this
  repository argues with the code in the imperative mood -- "delete this and the
  suite stays green" -- and it is prose the way a changelog is prose. Counting it
  would inflate the denominator with sentences no reader and no model ever wrote.
* **the corpus is NOT a random sample of English, and the number must not be read
  as one.** This repo's fixture prose exists largely to exercise these guards, so
  it clusters on the trigger boundary far more densely than product copy does. A
  corpus drawn from where the guards have already bitten will over-report
  firings relative to live traffic. That biases the denominator upward in the
  direction that makes the guards look BUSIER than they are on real output, and
  it is the reason the tool reports per-trigger counts and prints every firing
  rather than summarising a single rate.

**Two numbers, not one, because they are different questions.** "The trigger
fired" is what the regex says; "the reader got the template" is what
`_market_problems` does about it against a given bundle. `implied` is the
worked example and it is in this repo's own control list: "The implied order was
never in doubt" fires `implied` and is not rejected, because `implied` is a
probability market. Printing only the first number would credit the guard for
firing where nothing was lost, and printing only the second would hide a trigger
that is one bundle away from costing a reader their summary.

Nothing here runs a model or touches the network. It reads files and applies
regexes, which is why it can be re-run on a laptop and why its numbers are the
same on yours.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

_HERE = pathlib.Path(__file__).resolve().parent
SERVICE = _HERE.parent
REPO = SERVICE.parents[1]
if str(SERVICE) not in sys.path:
    sys.path.insert(0, str(SERVICE))

from explainer.validate import (  # noqa: E402
    ATTRIBUTION_PHRASES, BANNED, CLAIMS_LOST, CLAIMS_WON, PROSE_WORDS,
    _ATTRIBUTION_RE, _BANNED_RE, _market_problems,
)

#: The keys `validate` reads its prose out of, plus the fixture constants that
#: hold them. A string under any other key is not prose a reader sees.
PROSE_KEYS = frozenset({
    "verdict", "headline", "text",
    "_VERDICT", "_SPREAD", "_RECORD", "_CONTEXT",
    "PADDING_NO_QUOTE", "PADDING_BOTH", "PADDING_NO_PROJECTION",
})
#: The fixture builders whose string arguments become a factor `text`.
PROSE_CALLS = frozenset({"body", "good"})

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_CODE_FENCE = re.compile(r"^```[a-z]*\n(.*?)^```", re.M | re.S)
_QUOTED_LITERAL = re.compile(r'"([^"\n]{12,})"')
#: Kept in step with `validate._named_markets`' own spelling of the moneyline,
#: which accepts the two-word form as well as the one-word one.
_MONEY_LINE = r"money\s?line"


def _is_sentence(text: str) -> bool:
    """Whether a harvested fragment is prose rather than a key, path or regex.

    The shape is deliberately blunt -- at least three words, some letters, a
    terminal mark, a capital first letter, no format or regex metacharacters --
    because a sharper rule needed a corpus-specific exception list, and an
    exception list is where a measurement goes to be tuned until it agrees with
    the answer somebody wanted.
    """
    return (
        len(text.split()) >= 3
        and re.search(r"[a-zA-Z]{3}", text)
        and text.endswith((".", "!", "?"))
        and text[0].isupper()
        and not re.search(r"[{}<>|\\^`$@]|=>|://", text)
    )


def _docstring_ids(tree: ast.AST) -> set[int]:
    """The string nodes that are a docstring, so the harvester can skip them."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (first is not None and isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                out.add(id(first.value))
    return out


def _join(template: ast.AST) -> str:
    """An f-string's literal parts, with each hole as `N`.

    `N` rather than a real figure because none of the triggers read a digit: this
    measures phrase triggers, and substituting an invented number would change
    the corpus to make a number up.
    """
    if isinstance(template, ast.Constant) and isinstance(template.value, str):
        return template.value
    if isinstance(template, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "N"
                       for v in template.values)
    return ""


def template_copy(path: pathlib.Path) -> list[str]:
    """Every non-docstring string in a copy module: that IS its reader-facing text."""
    tree = ast.parse(path.read_text())
    skip = _docstring_ids(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip:
            out.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            out.append(_join(node))
    return out


def fixture_prose(path: pathlib.Path) -> list[str]:
    """The prose a test module hands to the validator, and nothing else."""
    tree = ast.parse(path.read_text())
    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            out.extend(v for k, v in zip(node.keys, node.values)
                       if isinstance(k, ast.Constant) and k.value in PROSE_KEYS)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in PROSE_KEYS:
            out.append(node.value)
        elif isinstance(node, ast.Call):
            wanted = node.func.id if isinstance(node.func, ast.Name) else ""
            if wanted in PROSE_CALLS:
                out.extend(node.args)
            out.extend(kw.value for kw in node.keywords if kw.arg in PROSE_KEYS)
    return [s for s in (_join(n) for n in out) if s]


def spec_examples(path: pathlib.Path) -> list[str]:
    """Example sentences from fenced code blocks in a spec."""
    text = path.read_text()
    out: list[str] = []
    for block in _CODE_FENCE.findall(text):
        out.extend(_QUOTED_LITERAL.findall(block))
        out.extend(block.splitlines())
    return out


def harvest() -> list[tuple[str, str]]:
    """`(source, sentence)` over the three sources, de-duplicated case-blind.

    De-duplication is by lowercased text because the same fixture sentence is
    written out in several files -- `test_market_words.py` and
    `test_bare_line_references.py` share most of their corpus -- and counting a
    sentence twice because two files quote it inflates the denominator with
    copies of one observation.
    """
    raw: list[tuple[str, str]] = []
    for chunk in template_copy(SERVICE / "explainer" / "template.py"):
        raw += [("explainer/template.py", s)
                for s in (p.strip() for p in _SENTENCE_SPLIT.split(chunk))
                if _is_sentence(s)]
    for path in sorted((SERVICE / "tests").glob("test_*.py")):
        for chunk in fixture_prose(path):
            raw += [(path.name, s)
                    for s in (p.strip() for p in _SENTENCE_SPLIT.split(chunk))
                    if _is_sentence(s)]
    for path in sorted((REPO / "docs/superpowers/specs").glob("*.md")):
        for line in spec_examples(path):
            raw += [(path.name, s)
                    for s in (p.strip() for p in _SENTENCE_SPLIT.split(line))
                    if _is_sentence(s)]
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for source, sentence in raw:
        key = re.sub(r"\s+", " ", sentence).lower()
        if key not in seen:
            seen.add(key)
            out.append((source, sentence))
    return out


def _named_concepts(sentence: str) -> list[tuple[str, str]]:
    """(concept, spelling) for each market the sentence names, on the PROSE words.

    Read from `validate.PROSE_WORDS` rather than restated, so this tool cannot
    drift into measuring a different vocabulary from the one the guard uses --
    which is the same reason the market-word table is read from
    `contract.market_keys` in `validate` itself.
    """
    low = sentence.lower()
    out = []
    for concept, words in PROSE_WORDS.items():
        for word in words:
            pattern = rf"\b(?:{_MONEY_LINE})\b" if "moneyline" in word \
                else rf"\b(?:{word})\b"
            if re.search(pattern, low):
                out.append((concept, word))
                break
    return out


def scan(sentence: str) -> list[tuple[str, str]]:
    """Every phrase trigger that matches, as `(trigger, what it matched)`."""
    low = sentence.lower()
    out: list[tuple[str, str]] = []
    out += [("banned", m.group(0)) for m in _BANNED_RE.finditer(low)
            if m.group(0) != "Hammers"]
    out += [("attribution", m.group(0)) for m in _ATTRIBUTION_RE.finditer(low)]
    out += [("market_word", w) for _, w in _named_concepts(sentence)]
    if CLAIMS_WON.search(sentence):
        out.append(("verdict", "claims the pick won"))
    if CLAIMS_LOST.search(sentence):
        out.append(("verdict", "claims the pick lost"))
    return out


#: The three bundles a firing is measured against, and why these three.
#: NBA-with-no-quote is the live case the market guard was added for; NBA with a
#: `market_line` is the same bundle once the book has quoted, which is where every
#: legitimate comparison lives; PL quotes its own goals line in `line` and is the
#: family-wide control.
BUNDLES = {
    "nba, nothing quoted": {
        "sport": "nba", "id": "401909903", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "BOS", "prob": 0.652},
        "markets": [
            {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
            {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9"},
            {"market": "total", "model_total": 220.4},
        ],
        "drivers": [], "context": {},
    },
    "nba, market_line quoted": {
        "sport": "nba", "id": "401909903", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "BOS", "prob": 0.652},
        "markets": [
            {"market": "moneyline", "model": {"ORL": 0.348, "BOS": 0.652}},
            {"market": "spread", "model_margin": -1.857, "line": "BOS by 1.9",
             "market_line": "BOS by 2.0"},
            {"market": "total", "model_total": 220.4, "market_line": 221.5},
        ],
        "drivers": [], "context": {},
    },
    "pl, own goals line": {
        "sport": "pl", "id": "pl-1", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "Arsenal", "prob": 0.48},
        "markets": [
            {"market": "result", "model": {"Arsenal": 0.48, "Draw": 0.26,
                                            "Chelsea": 0.26}},
            {"market": "total_goals", "model": 2.7, "line": 2.5},
            {"market": "btts", "model": 0.61},
        ],
        "drivers": [], "context": {},
    },
}


def rejections(sentence: str) -> dict[str, list[str]]:
    """`_market_problems` for each bundle: what a firing actually costs a reader."""
    return {name: _market_problems(bundle, sentence) for name, bundle in BUNDLES.items()}


def report() -> str:
    corpus = harvest()
    fired = [(src, sent, scan(sent)) for src, sent in corpus if scan(sent)]
    by_source: dict[str, int] = {}
    for src, _ in corpus:
        by_source[src] = by_source.get(src, 0) + 1
    by_trigger: dict[str, int] = {}
    for _, _, hits in fired:
        for trigger, _ in hits:
            by_trigger[trigger] = by_trigger.get(trigger, 0) + 1

    lines = [
        "corpus",
        f"  sentences            {len(corpus)} (de-duplicated, case-blind)",
        "  " + ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())),
        "",
        f"fired on at least one trigger: {len(fired)} of {len(corpus)}"
        f"  ({100 * len(fired) // max(len(corpus), 1)}%)",
        "  " + ", ".join(f"{k}={v}" for k, v in sorted(by_trigger.items()))
        + "   (a sentence may fire more than one)",
        "",
        "triggers this corpus did NOT reach",
    ]
    unreached: list[str] = []
    for label, names in (("banned", BANNED), ("attribution", ATTRIBUTION_PHRASES)):
        missed = [n for n in names
                  if not any(n.lower() in m.lower() for _, _, hits in fired
                             for t, m in hits if t == label)]
        if missed:
            unreached.append(f"  {label} ({len(missed)}/{len(names)}): "
                             + ", ".join(missed))
    lines += unreached or ["  (none -- every entry of every table was reached)"]

    lines += ["", "every firing, with the trigger named:"]
    for src, sent, hits in fired:
        lines.append(f"  [{src}] {sent}")
        for trigger, matched in hits:
            cost = rejections(sent)
            where = [name for name, problems in cost.items() if problems]
            lines.append(f"      {trigger}: {matched!r}")
            lines.append(f"        rejected against: {', '.join(where) or 'no bundle'}")
    return "\n".join(lines)


def main() -> int:
    print(report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
