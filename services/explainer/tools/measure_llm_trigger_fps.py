#!/usr/bin/env python3
"""Measure `validate`'s phrase triggers against REAL model output, not fixtures.

Run from `services/explainer`, against a LOCAL COPY of the explainer's cache:

    docker cp <container>:/data/explainer.sqlite /tmp/local-copy.sqlite   # once, by hand
    PYTHONPATH=. uv run --python 3.11 --extra dev --no-sync \
        python tools/measure_llm_trigger_fps.py /tmp/local-copy.sqlite

Answers reviewer item 3(b). `tools/measure_trigger_fps.py` measures the same
triggers against 62 sentences that live in this repository, and its own docstring
says the useful thing about that corpus: it is fixture prose, it exists largely
because these guards have already bitten, and it is not a sample of anything.
This tool is the same measurement over what the model actually wrote.

**The copy stays out of the repo, on purpose.** `services/explainer/.gitignore`
lists `*.sqlite` so the file cannot be committed by accident, and this script
takes the path as an argument rather than looking in a fixed place, so nobody is
tempted to vendor the production copy into the tree. It opens the database
`mode=ro`: the measurement has no business writing to a cache, and a read-only
handle is the cheapest way to make that a fact rather than a promise.

**Three things this tool cannot do, stated up front because each one changes what
the number means.**

1. **It cannot join to the facts.** `cache.Cache` stores the hash of the facts in
   the row's `key` and the facts themselves nowhere — the schema is
   `(key, sport, id, body_json, source, model, prompt_version, created_at)`. So
   the tool can say which trigger fired, and it CANNOT say whether a reader was
   rejected, because whether the quote requirement was met depends on a bundle
   this corpus does not contain. `measure_trigger_fps.py` can print both halves
   because its corpus is a repo it can also read the fixtures from. It prints
   this half only, and says so in its own output.
2. **It cannot separate the prompt versions.** The cache keeps every generation
   it ever made, and the rows in one cache span several `prompt_version` values.
   The trigger tables have changed under them. So the rows are grouped and
   printed by version, and the number is a measurement of *the corpus*, not of
   today's prompt.
3. **A corpus of tens of sentences is not a rate.** A hundred rows of v1 prose
   from one week is a sample of one prompt on one week of fixtures. The tool
   prints the counts and refuses to print a percentage for a corpus below a
   floor, because a percentage on a small denominator reads as a rate and is not
   one.

Nothing here runs a model, opens a socket, or reads anything but the file it is
pointed at. It is the same code path as the fixture tool — `scan` is imported
from there rather than copied, so the two measurements cannot drift apart.
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3
import sys

_HERE = pathlib.Path(__file__).resolve().parent
SERVICE = _HERE.parent
for _path in (SERVICE, _HERE):
    # `_HERE` as well as `SERVICE`: `scan` is imported from the sibling tool, and
    # `tools/` is a directory of scripts rather than a package. When this file is
    # loaded BY PATH (which is how the test loads it, because adding an
    # `__init__.py` to `tools/` would be a change to the service's layout to
    # accommodate a test) `sys.path[0]` is the caller's directory, not this one.
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Imported, not re-implemented: the trigger tables are the thing under
# measurement, so a second copy of the regexes would keep reporting yesterday's
# rate. `measure_trigger_fps.scan` reads `validate`'s own compiled patterns.
from measure_trigger_fps import scan  # noqa: E402

from explainer.validate import (  # noqa: E402
    ATTRIBUTION_PHRASES, BANNED, MARKET_WORDS, _concepts_in, _named_markets,
    _transferred_markets,
)

#: **The floor is on independent generations, not on sentences**, and that is the
#: whole point of it. One cached body yields 8-15 prose units, and 342 units from
#: 32 rows is not 342 observations -- it is 32, and the sentences inside one body
#: share a prompt, a model, a facts bundle and an author. A floor set on units
#: would clear itself on a dozen rows and hand back a precise-looking percentage
#: of a sample of one. Set on rows, the corpus this tool was written for -- one
#: service, one cache, five days, four prompt versions -- sits under it and the
#: tool declines, which is the honest answer.
MIN_ROWS_FOR_A_RATE = 250

#: The two idioms the review named. Counted by literal substring, in the clear,
#: because the question asked of them is "does this text ever say that", and
#: `ATTRIBUTION_PHRASES` holds `on the line` and `over the line` — the trigger
#: fires on the idiom *because* the idiom contains the phrase, which is the whole
#: of the concern. Zero occurrences is reported as zero occurrences; it is not
#: turned into an estimate.
IDIOMS = ("game on the line", "on the line", "over the line", "over/under line")

#: What each idiom's presence would cost, computed by running the trigger layer
#: over a fixed example rather than by reasoning about it. Deterministic, and
#: therefore reportable; the FREQUENCY half is not determinable and is not
#: invented here.
IDIOM_PROBES = {
    "game on the line": "The game is on the line for both clubs tonight.",
    "over the line": "The performance was over the line and nobody argued.",
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def prose_fields(body: dict) -> list[str]:
    """Every piece of prose in one cached body, whatever prompt version wrote it.

    `prompt_version` v1 bodies are `{headline, sections: [{title, text}]}`; v2 and
    after are `{verdict, factors: [{key, direction, headline, text}]}`. The
    validator reads the v2 names, and the cache is not all v2, so both shapes are
    mapped rather than one of them being silently dropped — a measurement over
    half the corpus would be a measurement of a version nobody runs.

    A key whose value is not a string contributes nothing rather than a
    `str(None)`: a malformed row is a fact about the corpus, and `None` as prose
    would put a word in the denominator that no reader ever saw.
    """
    if not isinstance(body, dict):
        return []
    if "verdict" in body:
        out = [body.get("verdict")]
        factors = body.get("factors")
        for factor in factors if isinstance(factors, list) else []:
            if isinstance(factor, dict):
                out += [factor.get("headline"), factor.get("text")]
    else:
        out = [body.get("headline")]
        sections = body.get("sections")
        for section in sections if isinstance(sections, list) else []:
            if isinstance(section, dict):
                out += [section.get("title"), section.get("text")]
    return [s.strip() for s in out if isinstance(s, str) and s.strip()]


def read_rows(path: pathlib.Path) -> list[tuple[str, str, str, str]]:
    """`(created_at, sport, prompt_version, body_json)` for every `source='llm'`.

    Opened read-only and selected with an explicit column list, so the query in
    the PR body and the query in this function are the same thing: a reader can
    paste one line into `sqlite3` and get the same rows.
    """
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return con.execute(
            "SELECT created_at, sport, prompt_version, body_json FROM explanations "
            "WHERE source = 'llm' ORDER BY created_at"
        ).fetchall()
    finally:
        con.close()


def corpus(rows) -> list[tuple[str, str, str, str]]:
    """`(day, sport, prompt_version, sentence)` — the denominator.

    De-duplicated case-blind and whitespace-collapsed, for the reason
    `measure_trigger_fps.harvest` gives: the same sentence appears in several
    fields and counting a copy inflates the denominator with one observation.
    Sentence splitting is the validator's own, so a unit here is a unit the
    validator would read.
    """
    seen: set[str] = set()
    out: list[tuple[str, str, str, str]] = []
    for created_at, sport, prompt_version, body_json in rows:
        try:
            body = json.loads(body_json)
        except ValueError:
            continue
        for field in prose_fields(body):
            for piece in _SENTENCE_SPLIT.split(field.strip()):
                sentence = piece.strip()
                key = re.sub(r"\s+", " ", sentence).lower()
                if sentence and key not in seen:
                    seen.add(key)
                    out.append((str(created_at)[:10], sport, prompt_version, sentence))
    return out


def is_a_sentence(text: str) -> bool:
    """Whether a unit ends in a terminal mark — the v7 factor-headline split.

    v7 writes headlines as noun phrases ("Moneyline leans toward Aggies"), and
    the fixture corpus is sentences only. Both are reported, separately, because
    pooling them makes the real-traffic number incomparable with the fixture one
    and uninterpretable on its own.
    """
    return text.endswith((".", "!", "?"))


def cannot_cost_a_reader(sentence: str) -> bool:
    """Whether this unit provably cannot reject anything, whatever the facts.

    Read off `_market_problems`, in the order that function applies its own two
    rules, and nothing else:

    * **an attribution phrase fired** -> rule 1 can reject outright. This is the
      only path that does not care about ownership.
    * **a LINE concept is named** (`MARKET_WORDS[concept][1]` is `is_line`, so
      `spread` and `total` but not `moneyline` or `implied`) -> rule 2 can reject
      it for want of a quote, UNLESS clause ownership already claimed the word.
    * **neither** -> the guard cannot act. `moneyline` and `implied` are
      probability markets and are `continue`d over before either check, which is
      why "the moneyline" appearing 23 times in this corpus costs a reader
      nothing at all.

    The ownership escape hatch is the second clause's, and it is checked with
    `validate`'s own functions rather than a restatement of them: a unit whose
    market word the model-ownership exemption or the third-party permit already
    claimed cannot be rejected for that word.

    Reported separately from the false-positive count, for the reason
    `measure_trigger_fps` gives for its `implied` row: "the trigger fired" and
    "the reader lost their summary" are different states, and folding them
    together credits or damns the guard for firings it cannot act on.
    """
    hits = scan(sentence)
    if any(t == "attribution" for t, _ in hits):
        return False
    if not any(c in _named_markets(sentence) | _transferred_markets(sentence)
               for c in _concepts_in(sentence) if MARKET_WORDS[c][1]):
        return True
    return not (_named_markets(sentence) | _transferred_markets(sentence))


def idiom_counts(sentences) -> dict[str, int]:
    """How often each named idiom appears at all, in any unit."""
    out = {idiom: 0 for idiom in IDIOMS}
    for _, _, _, sentence in sentences:
        low = sentence.lower()
        for idiom in IDIOMS:
            if idiom in low:
                out[idiom] += 1
    return out


def report(path: pathlib.Path) -> str:
    rows = read_rows(path)
    sentences = corpus(rows)
    sentence_shaped = [s for s in sentences if is_a_sentence(s[3])]
    fired = [(row, scan(row[3])) for row in sentences if scan(row[3])]

    by_trigger: dict[str, int] = {}
    by_phrase: dict[str, int] = {}
    for _, hits in fired:
        for trigger, matched in hits:
            by_trigger[trigger] = by_trigger.get(trigger, 0) + 1
            by_phrase[matched] = by_phrase.get(matched, 0) + 1
    by_version: dict[str, int] = {}
    for _, _, prompt_version, _ in sentences:
        by_version[prompt_version] = by_version.get(prompt_version, 0) + 1

    period = f"{rows[0][0]} .. {rows[-1][0]}" if rows else "(no rows)"
    lines = [
        f"source                 {path.name}",
        f"llm rows read          {len(rows)}",
        f"period                 {period}",
        f"prompt versions        "
        + (", ".join(f"{k}={v}" for k, v in sorted(by_version.items())) or "none"),
        f"prose units            {len(sentences)} (de-duplicated, case-blind)",
        f"  of which sentences   {len(sentence_shaped)}",
        "",
        "FACTS JOIN: impossible. cache.Cache stores the hash of the facts in",
        "`key` and never the facts, so this measurement reports what FIRED and",
        "cannot report whether a reader was rejected. See the tool's docstring.",
        "",
        f"fired on at least one trigger: {len(fired)} of {len(sentences)}",
    ]
    if len(rows) >= MIN_ROWS_FOR_A_RATE:
        lines.append(f"  ({100 * len(fired) // max(len(sentences), 1)}%)")
    else:
        lines.append(
            f"  (no percentage: {len(rows)} llm rows is below the tool's floor of "
            f"{MIN_ROWS_FOR_A_RATE}. The {len(sentences)} units are not "
            f"{len(sentences)} independent observations -- they come out of "
            f"{len(rows)} generations that share a prompt, a model and a facts "
            "bundle, and a percentage here would read as a rate)"
        )
    lines.append("  " + (", ".join(f"{k}={v}" for k, v in sorted(by_trigger.items()))
                          or "(nothing fired)")
                 + "   (a unit may fire more than one)")
    fired_sentences = [row for row, _ in fired if is_a_sentence(row[3])]
    lines.append(f"  of which sentence-shaped: {len(fired_sentences)}"
                 + (f" of {len(sentence_shaped)}" if sentence_shaped else ""))

    # The split the review actually asked for. `cannot_cost_a_reader` is derived
    # from `validate`; TRUE POSITIVE vs FALSE POSITIVE is a human reading of the
    # sentence and is NOT computed here, because a rule that decided it would be
    # tuned until it agreed with whatever number was wanted. The two are printed
    # as separate columns so a reader can see which part is arithmetic.
    undecidable = [row for row in sentences if scan(row[3]) and not cannot_cost_a_reader(row[3])]
    lines += [
        "",
        "COST: a unit the guard CAN act on (a line concept named, or an attribution",
        "phrase fired) and CANNOT be waved off by ownership. True-vs-false positive",
        "on these is a reading, not a computation, and is in the PR body:",
        f"  units the guard can act on   {len(undecidable)} of {len(fired)} firings",
        f"  units it provably cannot     {len(fired) - len(undecidable)}",
    ]

    lines += ["", "the phrases that fired, by frequency:"]
    lines += [f"  {n:3}  {p!r}" for p, n in sorted(by_phrase.items(), key=lambda kv: -kv[1])] \
        or ["  (none)"]

    # Split by prompt version, because a cache holds every generation it ever made
    # and the trigger tables have changed under them. A row pooled across v1 and
    # v7 measures a mixture, and the mixture is not a prompt anybody runs.
    lines += ["", "by prompt version (a unit may fire more than one trigger):"]
    for version in sorted(by_version):
        units = [row for row in sentences if row[2] == version]
        rows_here = sum(1 for r in rows if r[2] == version)
        groups = [scan(u[3]) for u in units]
        counts: dict[str, int] = {}
        for group in groups:
            for trigger, _ in group:
                counts[trigger] = counts.get(trigger, 0) + 1
        lines.append(f"  {version:>4}  rows={rows_here:>3}  units={len(units):>4}  "
                     f"fired={sum(1 for g in groups if g):>3}  "
                     + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "-"))

    lines += ["", "phrases in the tables this corpus never reached:"]
    unreached = [p for p in ATTRIBUTION_PHRASES
                 if not any(p.lower() in m.lower() for m in by_phrase)]
    lines.append(f"  attribution ({len(unreached)}/{len(ATTRIBUTION_PHRASES)}): "
                 + (", ".join(unreached) or "(none)"))
    unreached_banned = [w for w in BANNED
                        if not any(w.lower() in m.lower() for m in by_phrase)]
    lines.append(f"  banned ({len(unreached_banned)}/{len(BANNED)}): "
                 + (", ".join(unreached_banned) or "(none)"))

    lines += ["", "idioms the review named, counted in the clear:"]
    for idiom, count in idiom_counts(sentences).items():
        lines.append(f"  {idiom!r:20} {count}")
    lines.append("  what one would cost, by running the trigger layer over a fixed probe:")
    for idiom, probe in IDIOM_PROBES.items():
        lines.append(f"  {idiom!r:20} {scan(probe) or 'fires nothing'}")

    # The section a false-positive count structurally cannot contain. A market word
    # a third-party clause carries is EXEMPTED, not fired: it produces no
    # trigger, no problem, and no reader-visible rejection, so every rate in this
    # report and in `measure_trigger_fps` is blind to it by construction. The one
    # that mattered on live traffic was a participant noun in the subject seat
    # (`side`, `team`), which is what `test_validator_transfer_ordering.py` now
    # pins; it is printed here so the next run of this tool can see whether the
    # shape has come back.
    lines += ["", "silently exempted (no trigger fired; a clause handed the market away):"]
    exempted = [(row, _transferred_markets(row[3])) for row in sentences
                if _transferred_markets(row[3])]
    if exempted:
        for (day, sport, prompt_version, sentence), concepts in exempted:
            lines.append(f"  [{day} {sport} {prompt_version}] {sentence}")
            lines.append(f"      exempted: {', '.join(sorted(concepts))}")
    else:
        lines.append("  (none)")

    lines += ["", "every firing, with the trigger named:"]
    for (day, sport, prompt_version, sentence), hits in fired:
        lines.append(f"  [{day} {sport} {prompt_version}] {sentence}")
        for trigger, matched in hits:
            lines.append(f"      {trigger}: {matched!r}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: measure_llm_trigger_fps.py <local-copy-of-explainer.sqlite>",
              file=sys.stderr)
        return 2
    path = pathlib.Path(argv[1])
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    print(report(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
