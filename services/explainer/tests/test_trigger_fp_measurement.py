"""The trigger measurement is a measurement, so the measurement is pinned.

`tools/measure_trigger_fps.py` exists because the phrase-trigger tables in
`validate.py` have each grown by one entry after a live sentence got through or a
reader got the template instead of the summary, and nothing had ever recorded what
they cost on text that was ALREADY honest. The number in the PR is only worth
anything if re-running the tool gives the same number, and that is a property of
the harness, not of the tables.

What is asserted here, and why each:

* **the corpus is non-empty and spans all three declared sources.** A harvest that
  quietly returned nothing would report a 0% false-positive rate and be perfectly
  believable -- a guard measured against no sentences reads as a guard that never
  misfires, which is the most flattering possible lie. So the count is a floor,
  not an exact figure: prose is added to this repository constantly and an exact
  count would fail on every unrelated copy edit, which is how a guard gets deleted.
* **every entry of the trigger tables is exercised or reported as unreached.** A
  measurement that only reports the triggers it happened to hit is a coverage
  report wearing a measurement's clothes.
* **`scan` finds what it claims on a known sentence.** The tool is a reader of
  `validate`'s own regexes, and a reader that stopped reading would still print a
  confident table.

**No test here touches the network.** The tool reads files from this repository
and applies regexes; that is the whole of what it does, and it is why its numbers
reproduce on a machine with no credentials.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from explainer.validate import ATTRIBUTION_PHRASES, BANNED

TOOL = pathlib.Path(__file__).resolve().parents[1] / "tools" / "measure_trigger_fps.py"
#: Loaded by path, not imported as a package member: `tools/` is a directory of
#: scripts rather than a package, and adding an `__init__.py` to import one would
#: be a change to the service's layout to accommodate a test.
_spec = importlib.util.spec_from_file_location("measure_trigger_fps", TOOL)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)


def test_the_tool_reads_the_shipped_validator_rather_than_restating_it():
    """The measurement has to be of the guard that ships.

    If the tool carried its own copy of the banned-word list or the attribution
    phrases, it would keep reporting the same rate after somebody edited
    `validate.py` -- which is the whole failure this tool was written to end. So
    the names are compared by identity, not by value.
    """
    assert tool.BANNED is BANNED, "the tool re-states BANNED; it must import it"
    assert tool.ATTRIBUTION_PHRASES is ATTRIBUTION_PHRASES, (
        "the tool re-states ATTRIBUTION_PHRASES; it must import it"
    )


def test_the_corpus_is_harvested_from_all_three_declared_sources():
    """A floor, and each source named, because a rate over no sentences is a lie.

    The three sources are the ones the measurement declared: `template.py`'s own
    copy, the prose the test fixtures hand to the validator, and the example
    sentences in the specs. Asserted as a floor per source rather than as exact
    counts -- `template.py` alone is the only source guaranteed not to shrink,
    and a test that fails whenever a fixture is reworded is a test that gets
    commented out.
    """
    corpus = tool.harvest()
    assert len(corpus) >= 50, (
        f"the corpus fell to {len(corpus)} sentences. Check the harvest before "
        "believing any rate computed from it."
    )
    sources = {src for src, _ in corpus}
    assert "explainer/template.py" in sources, "the template copy is missing"
    assert any(src.startswith("test_") for src in sources), (
        "no fixture prose was harvested from tests/"
    )
    assert any(src.endswith(".md") for src in sources), "no spec examples were harvested"


def test_every_harvested_sentence_is_prose_and_not_a_fragment():
    """The corpus is sentences, or the denominator is a word count.

    Checked against the harvester's own predicate rather than by re-deriving it,
    plus two properties the predicate cannot see on its own: a sentence has a
    space in it, and it is not the same string twice under different spacing.
    """
    corpus = tool.harvest()
    for _, sentence in corpus:
        assert " " in sentence, f"not a sentence: {sentence!r}"
        assert tool._is_sentence(sentence), f"failed the shape predicate: {sentence!r}"
    seen = [s for _, s in corpus]
    assert len(seen) == len({s.lower() for s in seen}), (
        "the corpus contains a duplicate; the rate's denominator is wrong"
    )


@pytest.mark.parametrize("sentence,trigger,matched", [
    ("The market line of BOS by 1.9 sits very close to the model's margin.",
     "attribution", "market line"),
    ("Lock it in.", "banned", "lock"),
    ("The pick was right and it landed easily.", "verdict", "claims the pick won"),
    ("The total goals figure is tight.", "market_word", r"total\s+goals"),
], ids=["attribution", "banned", "verdict", "market_word"])
def test_scan_finds_the_trigger_it_names(sentence, trigger, matched):
    """The one tool behaviour that is asserted on a hand-written input.

    The rest of this file checks the harness's SHAPE. This checks that `scan`
    still reads `validate`'s regexes, by asking it about a sentence whose trigger
    is not in doubt and comparing the exact string it reports -- not just that it
    fired, because "fired on something" is exactly what a reader who has stopped
    reading the tables would report.
    """
    hits = tool.scan(sentence)
    assert trigger in [t for t, _ in hits], f"{trigger} not in {hits}"
    assert matched in [m for _, m in hits], f"{matched!r} not in {hits}"


def test_a_trigger_that_matches_nothing_is_reported_as_such_not_as_quiet():
    """The negative control, and the direction that matters.

    "The line between favourite and also-ran is thinner than usual" is honest
    English in this repository's own control lists. If `scan` reported a trigger
    for it, the false-positive rate in the PR body would be understated, so this
    is the assertion that keeps the reported number honest rather than the one
    that flatters it.
    """
    for sentence in ("The line between favourite and also-ran is thinner than usual.",
                     "Both teams sit on the same line this season.",
                     "Total commitment from midfield.",
                     "Boston is still recovering from the road trip.",
                     "The record argues against a bet on this one."):
        # The last one DOES fire, on the banned word "bet" -- which is correct,
        # and is why it is here rather than in the list above. It is the case
        # that separates "the trigger fired" from "the trigger fired wrongly":
        # the sentence names no market, so the market guard must stay silent, and
        # the only thing that fires is the banned-word table doing its job.
        expected = [] if "bet on" not in sentence else [("banned", "bet")]
        assert tool.scan(sentence) == expected, (
            f"honest prose reported as firing: {sentence!r} -> {tool.scan(sentence)}"
        )


def test_the_report_names_the_corpus_size_and_every_firing():
    """The report is the artefact the PR quotes, so its shape is the contract.

    Asserted on the rendered string rather than on the functions behind it: a
    number that is computed and never printed is a number nobody can check, and
    this is what stops the table and the claim from drifting apart.
    """
    report = tool.report()
    corpus = tool.harvest()
    assert f"sentences            {len(corpus)}" in report
    assert "fired on at least one trigger" in report
    assert "triggers this corpus did NOT reach" in report

    # Every firing in the corpus appears in the report, with its trigger. Compared
    # sentence-by-sentence rather than by counting, because a report that printed
    # the right NUMBER of lines while dropping one sentence and inventing another
    # is exactly the failure a count cannot see.
    for _, sentence in corpus:
        hits = tool.scan(sentence)
        if not hits:
            continue
        assert sentence in report, f"a firing is missing from the report: {sentence!r}"
        for _, matched in hits:
            assert repr(matched) in report, (
                f"the report does not name the match {matched!r} for {sentence!r}"
            )


def test_the_report_explains_the_bias_rather_than_only_the_rate():
    """The corpus is not a random sample, and the report has to say so.

    This repository's fixture prose exists largely to exercise these guards, so it
    clusters on the trigger boundary far more densely than live model output would.
    A rate quoted without that is a rate presented as more representative than it
    is, and the sentence is asserted so it cannot be edited out to make the
    number read better.
    """
    report = tool.report()
    assert "NOT a random sample" in tool.__doc__, (
        "the tool's own docstring no longer warns that the corpus is not a random "
        "sample, and that is the sentence standing between a 22% rate and a claim "
        "about live model output"
    )
    assert "de-duplicated" in report, (
        "the report does not say the corpus is de-duplicated, so a reader cannot "
        "tell whether shared fixture copy was counted once or twice"
    )


def test_the_measurement_runs_offline_and_never_calls_a_model():
    """The repo's own rule: tests never touch the network.

    Asserted on the tool's SOURCE rather than left as a claim in the docstring,
    because the docstring is the thing a reader trusts. `httpx`/`respx`/`openai`/
    `requests` appearing in a scanner that walks its own AST is the finding.
    """
    import ast

    source = TOOL.read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"httpx", "respx", "requests", "openai", "aiohttp", "urllib", "socket"}
    assert not (imported & forbidden), (
        f"the measurement imports {imported & forbidden}; it must read files and "
        "apply regexes, nothing else"
    )


def test_the_shipped_fixtures_still_carry_a_known_measured_sentence():
    """One sentence from the corpus is pinned to its source file.

    So the corpus is not just "a number the tool produced". If `harvest` stopped
    reaching `test_market_words.py`, every rate would fall and nothing in the
    suite would notice -- the corpus shrinking is the failure that makes a
    measurement look better than it is.
    """
    corpus = tool.harvest()
    sources = dict((s, src) for src, s in corpus)
    assert sources.get("The total goals figure is tight.") == "test_market_words.py", (
        "the measured false positive is no longer in the corpus (or moved files), so "
        "the rate in the PR body no longer describes what the tool sees"
    )
