"""The real-traffic measurement is a measurement, so the harness is pinned too.

`tools/measure_llm_trigger_fps.py` exists because reviewer item 3(b) asked for the
phrase-trigger false-positive rate against what the model actually wrote, and the
62-sentence corpus in `tools/measure_trigger_fps.py` is fixture prose — the
reviewer's objection to it was correct and is not answered by a second fixture
corpus. This file keeps the tool that reads the production cache honest about
the four things that decide whether its numbers mean anything:

* **it reads a LOCAL COPY and nothing else.** No network, no ssh, no `docker`, and
  a `mode=ro` handle, so a measurement cannot become a second way to touch
  production. Asserted on the tool's own imports, for the reason
  `test_trigger_fp_measurement.py` gives: a docstring is the thing a reader
  trusts, and the imports are the fact.
* **it maps BOTH prompt shapes.** The cache holds v1 bodies (`headline` +
  `sections`) alongside v2+ (`verdict` + `factors`), and a tool that read only
  the new shape would silently drop 14 of the 32 rows in the corpus the PR
  quotes. A measurement over half its corpus still prints a confident number.
* **it cannot join to the facts, and says so.** `cache.Cache` stores the hash of
  the facts and never the facts, so "was the reader rejected" is not computable
  from this corpus. The report has to carry that sentence, because a reader who
  does not know it will read a trigger count as a rejection count.
* **it refuses to print a percentage below its floor.** 342 units is not a rate,
  and the tool declining to call it one is the property worth pinning: a
  measurement that always produces a percentage is a measurement that always
  produces a number somebody can quote out of context.

**The cache itself is not in this repository and must not be.** It is production
text; `services/explainer/.gitignore` lists `*.sqlite`, and that is asserted
here rather than trusted, because a file that cannot be committed by accident is
a rule somebody eventually makes an exception to.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import pathlib
import re
import sqlite3

import pytest

from explainer.validate import ATTRIBUTION_PHRASES, BANNED, _transferred_markets

SERVICE = pathlib.Path(__file__).resolve().parents[1]
TOOL = SERVICE / "tools" / "measure_llm_trigger_fps.py"
_spec = importlib.util.spec_from_file_location("measure_llm_trigger_fps", TOOL)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def _cache(tmp_path: pathlib.Path, bodies) -> pathlib.Path:
    """A cache with THIS repo's schema, holding the given `(body, source)` rows.

    Built here rather than shipped, for the reason the whole file is about: the
    real file is production text. The schema is copied from
    `explainer.cache.Cache`'s CREATE TABLE, so a test against this fixture is a
    test against the shape the production database actually has — including its
    most consequential property, that there is no facts column to join to.
    """
    path = tmp_path / "explainer.sqlite"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE explanations (key TEXT PRIMARY KEY, sport TEXT, id TEXT, "
        "body_json TEXT, source TEXT, model TEXT, prompt_version TEXT, created_at TEXT)"
    )
    for i, (body, source) in enumerate(bodies):
        con.execute("INSERT INTO explanations VALUES (?,?,?,?,?,?,?,?)",
                    (f"k{i}", "nba", f"g{i}", json.dumps(body), source, "m", "v7",
                     f"2026-09-2{i % 6 + 1}T00:00:00+00:00"))
    con.commit()
    columns = [r[1] for r in con.execute("PRAGMA table_info(explainer)")]
    con.close()
    return path, columns


# --- the schema fact that decides what this tool can and cannot report --------

def test_the_cache_schema_stores_no_facts_so_the_join_is_impossible(tmp_path):
    """Pinned on the schema `explainer.cache.Cache` creates, not on a copy of it.

    The PR quotes a trigger count and says it is not a rejection count. That
    sentence is only true because the facts are not in the table — the cache key
    is a hash of them, which cannot be reversed. If somebody adds a facts
    column, the tool can answer a better question, and this test failing is the
    signal to go and answer it rather than to re-justify the weaker claim.
    """
    import explainer.cache

    path, columns = _cache(tmp_path, [({"verdict": "Boston are favoured here."}, "llm")])
    assert "facts" not in " ".join(columns), (
        f"the cache schema now carries facts ({columns}); the join the tool says "
        "is impossible may be possible, and the PR's caveat is out of date"
    )
    # The key is a sha256 of the facts, so the facts are recoverable from the
    # cache only by brute force over every possible bundle.
    assert len(explainer.cache.Cache.key("nba", "1", "{}", "[]", "v7", "m")) == 64
    assert tool.read_rows(path)[0][3].startswith("{")


# --- both prompt shapes, because the cache holds both ------------------------

V1_BODY = {
    "headline": "Arizona edges Washington State in a tight clash",
    "sections": [
        {"market": "moneyline", "title": "Model favours Arizona slightly",
         "text": "The model gives Arizona a 50% chance to win."},
    ],
}
V2_BODY = {
    "verdict": "Miami are slight favourites.",
    "factors": [
        {"key": "moneyline", "direction": "up", "headline": "Moneyline leans Miami",
         "text": "The model gives Miami a 52% chance."},
    ],
}


@pytest.mark.parametrize("body,expected", [
    (V1_BODY, ["Arizona edges Washington State in a tight clash",
               "Model favours Arizona slightly",
               "The model gives Arizona a 50% chance to win."]),
    (V2_BODY, ["Miami are slight favourites.", "Moneyline leans Miami",
               "The model gives Miami a 52% chance."]),
], ids=["v1 headline+sections", "v2 verdict+factors"])
def test_both_prompt_shapes_are_read_in_full(body, expected):
    """A tool that only read `verdict` would drop every v1 row in the corpus.

    14 of the 32 rows the PR quotes are v1. Losing them would not fail — the
    corpus would just be smaller and the rate would still print — which is why
    this is pinned per shape rather than as a total.
    """
    assert tool.prose_fields(body) == expected


@pytest.mark.parametrize("body,expected", [
    ({"verdict": "Fine."}, ["Fine."]),                                # no factors key
    ({"verdict": "Fine.", "factors": "not a list"}, ["Fine."]),       # wrong type
    ({"verdict": "Fine.", "factors": [{"text": None}]}, ["Fine."]),   # a null inside
    ({"sections": [{"title": "T", "text": 7}]}, ["T"]),                # numbers
    ({}, []),                                                         # empty
    ([], []),                                                         # not even a dict
    ({"verdict": "   "}, []),                                         # whitespace only
], ids=["no factors", "factors not a list", "null text", "int text", "empty dict",
        "not a dict", "whitespace only"])
def test_a_malformed_body_yields_no_prose_rather_than_a_stringified_none(body, expected):
    """A field that is not a string contributes nothing.

    `str(None)` as prose would put the word "None" in the denominator of a
    false-positive rate, and a rate with a synthetic word in it is not a rate.
    The expected lists are written out rather than derived from the tool, so a
    change to `prose_fields` that started accepting junk fails here.
    """
    assert tool.prose_fields(body) == expected


def test_template_rows_are_excluded_and_llm_rows_are_not(tmp_path):
    """`source='llm'` is the filter, and it is the whole filter.

    A cache also holds `source='template'` rows: 120 of them against 32 llm rows
    in the corpus the PR quotes. Folding the templates in would replace a
    measurement of model output with a measurement of this repository's own copy
    — which is the fixture corpus by another route, and is what the review
    objected to.
    """
    path, _ = _cache(tmp_path, [(V2_BODY, "llm"), (V1_BODY, "template")])
    rows = tool.read_rows(path)
    assert len(rows) == 1
    assert json.loads(rows[0][3])["verdict"] == "Miami are slight favourites."


# --- the corpus, and the four numbers the PR quotes --------------------------

def test_the_corpus_is_split_into_sentences_and_deduplicated_case_blind(tmp_path):
    """Two units that differ only in case and spacing are one observation.

    The same fixture sentence appears in several fields of several bodies; a
    corpus that counted copies would have a denominator made of duplicates, and
    every rate computed from it would be a rate about repetition.
    """
    body = {"verdict": "Boston are favoured here.",
            "factors": [{"key": "context", "direction": "neutral",
                         "headline": "Gap", "text": "Boston are favoured here.  They have been."}]}
    path, _ = _cache(tmp_path, [(body, "llm")])
    units = [s for _, _, _, s in tool.corpus(tool.read_rows(path))]
    assert units == ["Boston are favoured here.", "Gap", "They have been."], (
        "the verdict and the factor text are the same sentence and must count "
        "once; the double space after the full stop must not survive either"
    )


def _distinct(count: int) -> list:
    """`count` bodies whose prose is pairwise distinct, for the floor tests.

    Repeating one body would not do: the corpus de-duplicates, so 300 copies of
    the same sentence is 2 units, and a test for "above the floor" would be
    testing the de-duplicator instead.
    """
    return [{"verdict": f"Game {i} is nearly even.",
             "factors": [{"key": "context", "direction": "neutral",
                          "headline": f"Edge {i}", "text": f"Both sides read game {i} as tight."}]}
            for i in range(count)]


def test_a_v7_noun_phrase_headline_is_counted_but_flagged_as_not_a_sentence(tmp_path):
    """The v7 shape writes headlines as noun phrases, and they are prose.

    "Moneyline leans toward Aggies" is what a reader sees and what the guard
    reads, so dropping it would understate the corpus. It is also not a sentence,
    so pooling it with the fixture corpus's sentences would make the two
    measurements incomparable. Both facts are reported rather than resolved.
    """
    body = {"verdict": "Fine.", "factors": [
        {"key": "context", "direction": "neutral", "headline": "Moneyline leans Aggies",
         "text": "The model has Boston at 65%."}]}
    path, _ = _cache(tmp_path, [(body, "llm")])
    units = tool.corpus(tool.read_rows(path))
    headlines = [s for _, _, _, s in units if s == "Moneyline leans Aggies"]
    assert headlines, "the noun-phrase headline was dropped from the corpus"
    assert not tool.is_a_sentence("Moneyline leans Aggies")
    assert tool.is_a_sentence("The model has Boston at 65%.")


def test_a_corpus_below_the_floor_prints_counts_and_no_percentage(tmp_path):
    """The refusal is the point, so it is what the test asserts.

    Four rows is not a rate. A tool that always prints a percentage can be quoted
    as one no matter how small the corpus was, and the number that comes out is
    precise-looking and meaningless.
    """
    path, _ = _cache(tmp_path, [(b, "llm") for b in _distinct(4)])
    report = tool.report(path)
    assert "no percentage" in report, (
        "a four-row corpus produced a percentage; that is the failure this tool "
        "was written to make impossible"
    )
    assert f"{tool.MIN_ROWS_FOR_A_RATE}" in report


def test_the_floor_counts_generations_rather_than_prose_units(tmp_path):
    """The distinction the whole refusal rests on, asserted both ways.

    Twelve bodies of eight units each is 96 prose units and 12 observations. A
    floor on units would clear that and print "6%", which is a rate for a sample
    of twelve generations -- and a plausible-looking one, because the percentage
    is computed and the number under it is not.
    """
    bodies = [{"verdict": f"Game {i} is even. " + " ".join(
        f"Factor {i}.{j} is a neutral note." for j in range(7)).replace(".", ". "),
        "factors": [{"key": "context", "direction": "neutral",
                     "headline": f"H{i}", "text": f"T{i} is a neutral note."}]}
        for i in range(12)]
    path, _ = _cache(tmp_path, [(b, "llm") for b in bodies])
    report = tool.report(path)
    units = int(re.search(r"prose units\s+(\d+)", report).group(1))
    assert units >= 48, f"the fixture was supposed to be fat, got {units} units"
    assert units > 12, "the units are supposed to outnumber the rows"
    assert "no percentage" in report, (
        f"{units} units from 12 generations cleared the floor; the floor is on "
        "rows and something made it count units"
    )


def test_a_corpus_above_the_floor_does_print_the_percentage(tmp_path):
    """The other direction, so the floor is a threshold and not a hardcoded
    "never print a rate"."""
    path, _ = _cache(tmp_path, [(b, "llm") for b in _distinct(300)])
    report = tool.report(path)
    assert "no percentage" not in report
    assert "%" in report


# --- the cost column, which is derived rather than guessed -------------------

@pytest.mark.parametrize("sentence,cannot_cost", [
    ("The moneyline is nearly level.", True),            # probability market only
    ("The implied order was never in doubt.", True),      # and so is implied
    ("The model rates Boston 3.4 better.", True),         # model-owned clause
    ("The spread is fair at two and a half.", False),     # a line market, unowned
    ("The market line sits at two and a half.", False),   # an attribution phrase
    ("Very close to the line.", False),                   # bare-reference phrase
    ("Boston are favoured here.", True),                  # nothing fires at all
], ids=["moneyline", "implied", "model-owned", "spread", "market line",
        "bare line reference", "no trigger"])
def test_cannot_cost_a_reader_is_derived_from_the_guard_not_guessed(sentence, cannot_cost):
    """Read straight off `_market_problems`' two rules, so the column it feeds
    cannot drift from the code that would actually reject a reader.

    `moneyline` and `implied` are the reason this column exists: they fire 29
    times in the quoted corpus and cost a reader nothing, because
    `MARKET_WORDS` marks them `is_line=False` and the guard `continue`s over them
    before either check. Counting them as false positives would have tripled the
    headline number with firings the guard cannot act on.
    """
    assert tool.cannot_cost_a_reader(sentence) is cannot_cost


# --- the idioms the review named --------------------------------------------

@pytest.mark.parametrize("idiom,probe,expected", [
    ("game on the line", "The game is on the line for both clubs tonight.",
     ("attribution", "on the line")),
    ("over the line", "The performance was over the line and nobody argued.",
     ("attribution", "over the line")),
], ids=["game on the line", "over the line"])
def test_each_named_idiom_would_fire_the_attribution_table(idiom, probe, expected):
    """The reviewer's question, answered the only way it can be answered on a
    corpus this size: not "how often does it misfire" but "what happens when it
    does".

    Both idioms are ordinary English that has nothing to do with a market, and
    `ATTRIBUTION_PHRASES` contains `on the line` and `over the line` verbatim.
    So the guard rejects the sentence — `rule 1` fires on the body-scoped
    attribution and the reader gets the template. That is determinable from the
    trigger table alone and is asserted here; the FREQUENCY is not determinable
    from 32 cached rows, and the tool reports its count rather than a rate.
    """
    from explainer.validate import _market_problems

    assert idiom in tool.IDIOMS
    assert tool.scan(probe) == [expected], (
        f"{idiom!r} no longer fires {expected!r}; the table changed under the "
        "claim in the PR body"
    )
    problems = _market_problems({"sport": "nba", "markets": [], "pick": None}, probe)
    assert problems, (
        f"{idiom!r} fires the attribution table but costs the reader nothing, so "
        "the PR's claim that it is a false positive no longer holds"
    )


def test_the_idiom_counts_are_reported_per_idiom_and_default_to_zero(tmp_path):
    """Zero is printed as zero, never as "rare" or "no evidence of".

    The corpus the PR quotes contains neither idiom. The honest report of that is
    the number 0 next to the name, and the reason it is per-idiom rather than a
    combined total is that "on the line" DOES occur once — so a combined "line
    idioms: 1" would have buried both zero rows under a number that is about a
    third idiom.
    """
    body = {"verdict": "Fine.", "factors": [
        {"key": "context", "direction": "neutral", "headline": "Gap",
         "text": "The model has Boston at 65%."}]}
    path, _ = _cache(tmp_path, [(body, "llm")])
    report = tool.report(path)
    for idiom in tool.IDIOMS:
        assert repr(idiom) in report, f"{idiom!r} is not counted in the report"
    assert "'game on the line'   0" in report
    assert "'over the line'      0" in report


def test_the_report_lists_the_clauses_the_guard_silently_exempted(tmp_path):
    """The section a false-positive count structurally cannot contain.

    A market word a third-party clause carries is EXEMPTED, not fired: no trigger,
    no problem, no reader-visible rejection. So it is invisible to every rate in
    this report and in `measure_trigger_fps`, and it is the channel the review's
    Major finding came through. A tool that measures false positives and prints
    nothing about exemptions would have reported that bypass as a clean sheet.
    """
    report = tool.report(_cache(tmp_path, [(V2_BODY, "llm")])[0])
    assert "silently exempted" in report
    assert _exempted(report) == "", (
        f"a body that triggers nothing and hands nothing away listed exemptions: "
        f"{_exempted(report)!r}"
    )


def test_a_clause_handed_away_by_a_third_party_shows_up_in_the_exempted_section(tmp_path):
    """The section a false-positive count structurally cannot contain, and the
    one the review's Major finding would have gone unreported through.

    A market word a third-party clause carries is EXEMPTED, not fired: no trigger,
    no problem, no reader-visible rejection. So it is invisible to every rate in
    this report and in `measure_trigger_fps` — the review's sentence would have
    been reported as a clean sheet by the very tool meant to catch it. The
    section exists so the next run can see whether the shape comes back.

    A GENUINE source is used here, not a participant: this test is about the
    section existing and working, and the participant case is covered (and
    rejected) in `test_validator_transfer_ordering.py`.
    """
    body = {"verdict": "Fine.", "factors": [
        {"key": "context", "direction": "neutral", "headline": "Gap",
         "text": "The club injury report calls the spread too wide."}]}
    report = tool.report(_cache(tmp_path, [(body, "llm")])[0])
    assert "The club injury report calls the spread too wide." in _exempted(report), (
        "_transferred_markets no longer exempts a genuine third-party clause, so "
        "the section reports nothing and a laundering shape would be invisible. "
        f"Section was: {_exempted(report)!r}"
    )
    assert "exempted: spread" in report


def _exempted(report: str) -> str:
    """The units listed under the exempted header, and nothing else.

    Split on the two bracketed line headers rather than on the section title,
    because the title is not a line of its own in the report and slicing on it
    would return a fragment that starts mid-sentence — which is what happened the
    first time this was written.
    """
    body = report.split("silently exempted", 1)[1]
    body = body.split("every firing, with the trigger named:", 1)[0]
    return "\n".join(line for line in body.splitlines() if line.startswith("  ["))


def test_a_participant_clause_is_no_longer_exempted_and_says_so(tmp_path):
    """The review's sentence, in this tool's own output.

    Before `test_validator_transfer_ordering.py`'s fix, this unit appeared under
    "silently exempted" in the real-traffic report: `team` in the subject seat
    carried a `moneyline` claim out of the guard with no trigger fired and no
    problem raised. After it, it does not. Asserted here as well as in the
    validator's own suite because this is the view the measurement took, and a
    fix that passed the validator tests while leaving the measurement unchanged
    would mean the two are measuring different things.
    """
    sentence = "That gives the home team a clear edge on the moneyline."
    assert not _transferred_markets(sentence), (
        "a participant noun is exempting a market word again; the review's bypass "
        "is back and this is the tool that would have shown it"
    )
    body = {"verdict": "Fine.", "factors": [
        {"key": "context", "direction": "neutral", "headline": "Gap", "text": sentence}]}
    report = tool.report(_cache(tmp_path, [(body, "llm")])[0])
    assert _exempted(report) == "", (
        f"the review's shape is listed as exempt again: {_exempted(report)!r}"
    )


def test_the_report_splits_the_corpus_by_prompt_version(tmp_path):
    """A cache holds every generation it ever made, and the tables changed under
    them.

    14 of the 32 rows in the corpus the PR quotes are v1, written before the
    market guard existed. Pooled, the report measures a mixture that is not a
    prompt anybody runs. The per-version block is what stops the reader from
    quoting the pooled number as a statement about today's model.
    """
    rows = [(dict(V2_BODY, verdict=f"Game {i} is even."), "llm") for i in range(3)]
    path, _ = _cache(tmp_path, rows)
    report = tool.report(path)
    assert "by prompt version" in report
    assert "v7" in report


def test_the_report_names_the_phrases_the_corpus_never_reached(tmp_path):
    """A measurement that only reports the triggers it happened to hit is a
    coverage report wearing a measurement's clothes.

    Every banned word and 26 of 36 attribution phrases are unreached on real
    traffic in this corpus, which is the single most load-bearing caveat on any
    rate computed from it: most of the table has never seen a real sentence.
    """
    report = tool.report(_cache(tmp_path, [(V2_BODY, "llm")])[0])
    assert "never reached" in report
    assert f"banned ({len(BANNED)}/{len(BANNED)})" in report
    for word in BANNED:
        assert word in report, f"{word!r} is not reported as unreached"


# --- production safety, asserted -------------------------------------------

def test_the_tool_imports_nothing_that_could_reach_a_machine():
    """No network, no `subprocess`, no `docker`, no `ssh`.

    Asserted on the SOURCE rather than left as a promise, because a measurement
    tool that could shell out is a measurement tool that could be pointed at the
    VPS, and the difference between the two is one import. `sqlite3` and `pathlib`
    are the whole of what it is allowed to need.
    """
    imported: set[str] = set()
    for node in ast.walk(ast.parse(TOOL.read_text())):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"httpx", "respx", "requests", "openai", "aiohttp", "urllib", "socket",
                 "subprocess", "paramiko", "fabric", "docker", "asyncio", "shutil"}
    assert not (imported & forbidden), (
        f"the measurement imports {sorted(imported & forbidden)}; it must open one "
        "local sqlite file and apply regexes, nothing else"
    )


def test_the_cache_is_opened_read_only():
    """`mode=ro`, in the URI, so a measurement cannot write to a cache.

    Not a promise in the docstring: a sqlite handle opened read-write would
    happily create a journal next to production, and the tool has no reason
    whatsoever to hold one.
    """
    assert 'mode=ro' in TOOL.read_text()
    assert "uri=True" in TOOL.read_text()


def test_the_production_cache_is_not_in_the_repository():
    """The rule the whole file rests on, asserted rather than trusted.

    `services/explainer/.gitignore` lists `*.sqlite`. A file that cannot be
    committed by accident is a rule somebody eventually makes an exception to
    "just to check", and this file's entire reason to exist is that the copy is
    production prose.
    """
    assert "*.sqlite" in (SERVICE / ".gitignore").read_text()
    committed = [p.name for p in SERVICE.rglob("*.sqlite")
                 if ".venv" not in p.parts and "__pycache__" not in p.parts]
    assert not committed, (
        f"a sqlite file is sitting in the service tree: {committed}. That is the "
        "production cache or a copy of it."
    )


def test_the_fixture_corpus_tool_and_this_one_share_one_scan():
    """`scan` is imported, not copied.

    Two copies of the trigger regexes would keep reporting yesterday's rate after
    somebody edited `validate.py`, which is the failure `measure_trigger_fps.py`
    was written to end. Asserted by identity for the same reason
    `test_trigger_fp_measurement.py` asserts it.
    """
    import measure_trigger_fps

    assert tool.scan is measure_trigger_fps.scan


@pytest.mark.parametrize("argv,code", [
    ([], 2),
    (["/nonexistent/explainer.sqlite"], 2),
    ([str(TOOL), "extra"], 2),
])
def test_usage_errors_exit_non_zero_without_reading_anything(argv, code, capsys):
    """A measurement that silently proceeds on a missing file reports a rate for
    no corpus, which is the most flattering possible lie."""
    assert tool.main(["measure_llm_trigger_fps.py", *argv]) == code
    assert capsys.readouterr().err
