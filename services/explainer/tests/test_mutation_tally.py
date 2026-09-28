"""The harness's own arithmetic, pinned -- because a harness that miscounts is
indistinguishable from a harness whose guards do not bite.

`tools/mutcheck_template_line.py` decides every row's verdict by reading two
numbers out of pytest's output: how many tests failed, and how many passed. A
mutation BITES if `failed > 0`. So the two numbers are the entire basis on which
this project concludes that a guard is load-bearing, and they were being read out
of the FIRST match of `re.search(r"(\\d+) (failed|passed)", stdout + stderr)`.

That is wrong, and wrong in the direction that matters, because the first match
is wherever the word appears first and a failing test's own output is full of
numbers:

* a run with 26 real failures reported `2 failed`;
* 257 real passes reported as `26`;
* a run whose output echoed "0 passed" reported `passed: 0`.

The third is the live path to a false PASS. A row is judged on `failed > 0`, so
an earlier `0 failed` anywhere in the output -- an echoed line, a traceback
quoting a string, a fixture's own text -- makes a mutation that broke five tests
report SILENT. The table is then read as "no test covers this", which is the
conclusion a person acts on, and it is wrong.

**Every case below is the reviewer's, run against the real function.** The
before/after numbers are in the docstring of each test. `--tb=no` is part of the
fix and is asserted separately, because the heuristic is "the summary line is
last" and tracebacks are a page of text between the failure and the summary.

Nothing here runs pytest: these are strings, and the function under test is the
one the harness calls. A test that shelled out to produce real output would be
slower, slower again on the machine that is already slow, and would not cover
the cases that matter -- the ones that only arise when the output contains
something unexpected.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

#: The harness is a script in `tools/`, not a package member, so it is loaded by
#: path. Reading it as a MODULE rather than grepping its source is the point of
#: this file: a check that greps a script for a string is satisfied by a comment
#: quoting the code, which is the same decoy this repo has been bitten by.
HARNESS = pathlib.Path(__file__).resolve().parents[1] / "tools" / "mutcheck_template_line.py"
_spec = importlib.util.spec_from_file_location("mutcheck_template_line", HARNESS)
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

_last_count = harness._last_count


def _tally(out: str) -> tuple[int, int]:
    """(failed, passed) exactly as `harness.run` computes them."""
    return _last_count(out, "failed"), _last_count(out, "passed")


# --- the reviewer's three cases, before and after ---------------------------

#: A realistic `-q` run whose failure text mentions both count words with other
#: numbers. Built from what pytest actually prints: progress dots, a
#: `FAILED ...` line per test, and a summary. The "2 failed" and "26 passed"
#: earlier in the output are a skipped test's reason line and a test's own
#: docstring text captured in the failure report.
CASE_MID_SUMMARY = """\
.F...F......F................F.............F.....F..F........F..........F...F......F..F.......F........F.......F....F...F........F........F..F....F....F.......F..F...F....F....F......F...
=================================== FAILURES ===================================
_____________________________ test_a _____________________________
    def test_a():
>       assert 26 == 2
E       assert 26 == 2

_____________________________ test_b _____________________________
    def test_b():
        # A test whose own text mentions a tally: 2 failed, 26 passed once.
>       assert x is None
E       AssertionError
=========================== short test summary info ============================
FAILED tests/test_x.py::test_a - assert 26 == 2
26 failed, 257 passed in 12.34s
"""

#: An echoed "0 passed" -- the false-pass case. A fixture or a log line in the
#: middle of the output says the run passed nothing, and the first-match tally
#: believed it.
CASE_ECHOED_ZERO_PASSED = """\
FF..F.......F......F..........F....F.......F......F....F.....F......F.......F...
=================================== FAILURES ===================================
    E   AssertionError: 0 passed, 5 failed
=========================== short test summary info ============================
5 failed, 283 passed in 8.90s
"""

#: A clean run. The control: the fix must not change this one, or every row
#: would report a bite it does not have.
CASE_CLEAN = """\
................................................................. [100%]
283 passed in 1.18s
"""


@pytest.mark.parametrize("out,expected", [
    pytest.param(CASE_MID_SUMMARY, (26, 257), id="the first match found the wrong numbers"),
    pytest.param(CASE_ECHOED_ZERO_PASSED, (5, 283), id="an echoed 0 passed was read as the tally"),
    pytest.param(CASE_CLEAN, (0, 283), id="a clean run, unchanged"),
])
def test_the_tally_reads_the_summary_and_not_the_first_mention(out, expected):
    """`re.findall(...)[-1]`: the last mention, which is the summary line.

    Before, the same three cases read `(2, 26)`, `(0, 0)` and `(0, 283)` -- the
    first of which turns a mutation that broke 26 tests into "BITES (2 failed)",
    which looks like a partial pass, and the second reports a run with five
    failures as having passed nothing and failed nothing at all.
    """
    assert _tally(out) == expected, f"read {_tally(out)}, expected {expected}"


def test_a_count_appears_in_a_traceback_and_is_not_the_tally():
    """The specific false-pass path, isolated so a future reader cannot miss it.

    The harness calls a row SILENT when `failed == 0`. So an output containing
    "0 failed" before the real summary makes a biting mutation silent, and the
    table then says "no test covers this" -- which is the sentence a person acts
    on, and it is the wrong one. Asserted as its own case rather than folded
    into the table above because it is the one with a consequence.
    """
    out = ("some helper printed: 0 failed\n"
           "=================================== FAILURES ===================================\n"
           "    assert 5 == 0\n"
           "=========================== short test summary info ============================\n"
           "5 failed, 300 passed in 9.99s\n")
    failed, passed = _tally(out)
    assert (failed, passed) == (5, 300), f"read {(failed, passed)}"
    assert failed > 0, "a run that failed five tests was read as clean, so mutations bite for free"


def test_output_with_no_counts_at_all_is_zero_not_an_error():
    """The shape a count-less output has to take, so it is a decision.

    pytest always prints a summary, so this case is unreachable in practice. It
    is pinned because the alternative -- raising, or defaulting to a number that
    reads as a bite -- is the kind of choice that gets made silently and then
    reads as "the harness said everything bites" on a machine whose pytest is
    configured differently.
    """
    assert _tally("no numbers here at all\n") == (0, 0)


def test_a_collection_error_is_still_counted_as_an_error_not_a_zero():
    """`run()` returns before the tally on a bad exit code, and this is why.

    A mutation that produces a syntax error makes pytest exit 2, and `run()`
    returns `(-1, 0, 1)` -- errored, which counts as a bite. It never reaches
    `_last_count`, because a collection error prints no `passed` line at all and
    the tally would read `(0, 0)`, i.e. SILENT: a mutation that broke the file
    into not parsing would have been reported as covering nothing. The docstring
    in the harness records this as the second of the three ways an earlier version
    reported all-passed for the wrong reason; this test states the invariant the
    early return protects, so the early return is not "simplification" to a
    later reader.
    """
    import subprocess

    out = ("ERROR: SyntaxError: invalid syntax\n"
           "!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!\n")
    failed, passed = _tally(out)
    assert (failed, passed) == (0, 0), (
        f"a collection error tallies as {(failed, passed)}; run() must return before "
        f"this, on the exit code, or the row reads silent"
    )
    assert subprocess.run(["true"]).returncode == 0


# --- a row that does not parse is not a guard ------------------------------
#
# **The reviewer's finding, and it is the one this file's whole method exists to
# catch.** A row whose anchor or replacement does not parse makes pytest exit 2,
# `run()` returns `errored`, and the loop used to read that as
# `verdict, bite = "BITES (collection error)", True`. So the one outcome that
# means *this row tested nothing at all* was filed under the one outcome that
# means *this row proved a guard is load-bearing*. The reviewer's own added row
# demonstrated it end to end: an anchor ending in `.*` (matched with `re.S`, so
# it swallows to end of file) replaced the rest of `template.py`, the harness
# printed `BITES (collection error)`, then printed "every mutation bit or was
# documented as expected-silent, and the canary stayed silent as it should", and
# exited 0.
#
# The module docstring already records two historical rows that did exactly this
# by hand, so the file is not making a novel claim -- it is making a claim about
# a hole that two previous passes already fell into.


def test_a_collection_error_is_its_own_bucket_rather_than_a_bite():
    """BROKEN, checked BEFORE the mark, and never a bite.

    A broken row is not a guard that bit; it is a row that never ran. Filing it
    as `BITES` puts "this mutation is covered" into a table cell when the truth is
    "this mutation is untested", and the reader of that table is looking for
    coverage.

    Checked before the `EXPECTED_SILENT_MARK` deliberately. A row can be both
    marked expected-silent and broken, and the question "was the mark right?" is
    unanswerable while the row is untested -- so the untested answer is the one
    that gets reported, and MISLABELLED stays a statement about rows that ran.
    """
    assert harness.classify(UNMARKED, bite=True, broken=True) == harness.BROKEN, (
        "a collection error is still filed as BITES, so a row that never ran is "
        "reported as a guard that held"
    )
    assert harness.classify(MARKED, bite=True, broken=True) == harness.BROKEN, (
        "a broken row was judged by its expected-silent mark, which is a claim "
        "about a run that did not happen"
    )
    # And a row that is NOT broken still reaches the ordinary four buckets, so
    # the new parameter cannot swallow the existing decisions.
    assert harness.classify(UNMARKED, bite=True, broken=False) == harness.BITES
    assert harness.classify(UNMARKED, bite=False, broken=False) == harness.SILENT
    assert harness.classify(MARKED, bite=False, broken=False) == harness.EXPECTED
    assert harness.classify(MARKED, bite=True, broken=False) == harness.MISLABELLED


def test_a_broken_row_exits_non_zero_and_is_reported_before_the_silent_one(tmp_path):
    """Not the classification, the consequence -- the shape the reviewer found.

    `main` printed its success line and returned 0 with a broken row in the table.
    So the exit code is asserted, the success line is asserted ABSENT, and the
    broken rows are asserted to be reported **before** the silent-mutation report.

    "Before" is asserted as `return 1` and not as two lists printed in an order:
    the broken check returns immediately, so on a table holding both a broken row
    and a silent row the silent report is never reached at all. That is the
    ordering the fix asks for -- a reader who stops at the first finding cannot
    stop at the wrong one -- and asserting the absence is what pins it, because a
    version that collected both and printed broken-then-silent would satisfy a
    looser check while the important property (the run is already over) is what
    keeps it honest.

    Driven with a replacement of `BROKEN = ((( ` -- a real syntax error, so the
    demonstration does not depend on a stub inventing the exit code.
    """
    rows = [
        SILENT_CANARY,
        ("a decoy that does not parse", r"^MARKER = 1$", "BROKEN = ((( "),
        ("a decoy that stays silent", r"^MARKER = 1$", "MARKER = 1"),
    ]
    # One answer per `run()` call, in order: the baseline, then one per row, then
    # the post-restore run. The canary is a ROW here, so it takes the second
    # answer -- and it has to take a clean one, or the run fails for the canary's
    # sake and this test stops being about the broken row.
    runs = [(0, 300, 0), (0, 300, 0), (-1, 0, 1), (0, 300, 0), (0, 300, 0)]

    code, printed = _run_main(rows, runs, tmp=tmp_path)

    assert code == 1, f"a broken row exited {code}, not 1\n{printed}"
    assert "every mutation bit" not in printed, (
        f"the success line printed with a broken row in the table:\n{printed}"
    )
    # The per-row verdict column is the table working: the broken row is labelled
    # BROKEN there and the silent one SILENT, and neither is called a bite.
    assert "BROKEN (collection error)" in printed, printed

    # Everything from the post-restore run on is the REPORT, and the report is
    # what a reader reads as a conclusion. Scoped to it, because the per-row
    # column above names every row by design and the absence claims are about
    # findings, not labels.
    report = printed.split("restored:")[-1]
    assert "1 mutation(s) did not parse" in report, report
    assert "a decoy that does not parse" in report, report
    # The silent report is unreachable while a broken row stands, so the reader
    # cannot be left reading a silent-mutation list that omits the untested row.
    assert "did not bite" not in report, (
        f"the silent report printed alongside a broken row:\n{report}"
    )
    assert "a decoy that stays silent" not in report, (
        f"the silent row was reported while an untested row was standing:\n{report}"
    )
    assert "ACTUALLY BITES" not in report, report


def test_a_broken_canary_is_not_a_silent_control(tmp_path):
    """The one row whose own bucket is asserted, and the second half of the canary
    check.

    The canary's whole job is to be a control that can FAIL, and a run that filed
    a broken canary as `not bite` would set `canary_ok` -- printing a table in
    which the control destroyed the file and reporting the run as clean. The
    broken bucket is what makes that combination visible, and the run still exits
    non-zero either way; this pins that the broken finding is *named*, so the exit
    is for the reason a reader can act on rather than an accident of ordering.
    """
    rows = [("CANARY: nothing covers this", r"^MARKER = 1$", "BROKEN = ((( ")]
    runs = [(0, 300, 0), (-1, 0, 1), (0, 300, 0)]

    code, printed = _run_main(rows, runs, tmp=tmp_path)

    assert code == 1, printed
    assert "did not parse" in printed, printed
    assert "CANARY: nothing covers this" in printed, (
        f"a broken canary was not reported as broken:\n{printed}"
    )
    assert "every mutation bit" not in printed, printed


def test_a_broken_row_with_nothing_else_wrong_still_exits_one(tmp_path):
    """The broken row on its own, which is the reviewer's actual scenario.

    A table of one broken row and a silent canary has an EMPTY silent list, so the
    ordering assertion above has nothing to order against and this is the case that
    would have slipped past it: nothing else wrong, one row untested, and the only
    question is the exit code.
    """
    rows = [SILENT_CANARY, ("a decoy that does not parse", r"^MARKER = 1$", "BROKEN = ((( ")]
    runs = [(0, 300, 0), (0, 300, 0), (-1, 0, 1), (0, 300, 0)]

    code, printed = _run_main(rows, runs, tmp=tmp_path)

    assert code == 1, f"a broken row and nothing else wrong exited {code}\n{printed}"
    assert "every mutation bit" not in printed, printed
    assert "did not bite" not in printed, (
        f"a broken row was also filed as a silent mutation:\n{printed}"
    )
    assert "1 mutation(s) did not parse" in printed, printed


def test_a_clean_run_says_nothing_about_broken_rows(tmp_path):
    """The control for the row above.

    If `broken` were non-empty on a clean run -- a list initialised wrong, or the
    check placed so it fires on the canary -- the new failure would mask the
    results instead of adding to them, and a green run would start reporting a
    problem it does not have.
    """
    code, printed = _run_main([SILENT_CANARY], [(0, 300, 0)] * 3, tmp=tmp_path)
    assert code == 0, printed
    assert "did not parse" not in printed, printed
    assert "every mutation bit" in printed, printed


# --- the static check: an anchor may not hold a DOTALL `.` ------------------
#
# The two halves of the fix, and this is the cheaper one. The broken bucket above
# makes a bad row *fail*; it does not make it *obvious*. A pattern containing an
# unescaped `.` is matched with `re.S`, where `.` means "any character, including
# a newline" -- so `r"...keys:.*$"` matches to the END OF FILE, and
# `re.subn(..., count=1)` replaces the entire tail of the source with the
# replacement. The file stops parsing, the run errors, and (before the bucket
# above) the table reported a bite.
#
# The whole-line spelling `^...$` with `[^\n]*` is the DOTALL-safe one and the
# table already documents it on the two rows that were fixed by hand. This is the
# check that stops the third one.


def test_no_anchor_in_the_table_holds_a_dot_the_regex_would_read_as_any_character():
    """Every row, on every file. This is the guard, and it is a property of the
    TABLE rather than of one row -- which is what makes it hold for the next row
    somebody adds rather than the ones that are already here.

    Asserted on `MUTATIONS` itself rather than on a checked-in copy of it, so
    deleting the rows does not make the check vacuous: the list is read from the
    harness module, which is the same object `main` iterates.
    """
    offenders = harness.dot_problems()
    assert offenders == [], (
        "an anchor in the table contains a `.`, which under re.S means 'any "
        "character including a newline' and so matches to the end of the file:\n"
        + "\n".join(f"  {label}: {fragment!r}" for label, fragment in offenders)
        + "\nWrite the anchor whole-line (`^...$`) and spell any run as "
          "`[^\\n]*`, or escape the dot."
    )


@pytest.mark.parametrize("pattern,expected", [
    # The two shapes a DOTALL-unsafe anchor takes, both of which the reviewer and
    # the module docstring have already hit by hand.
    (r"^    for key in keys:.*$", True),
    (r"^Write NO figures in the panel\..*do not say which number is bigger\.$", True),
    # And the spellings that are safe, so the check is not "reject every dot".
    (r"^    for key in keys:$", False),
    (r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$", False),
    (r"^Write NO figures in the panel\.[^\n]*$", False),
    (r"^MIN_SPREAD_MARGIN = 0\.5$", False),
    (r"^    if margin_market is not None and margin is not None and label and quoted and big_enough:$", False),
    (r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', False),
    # A dot INSIDE a character class is a literal and is safe, so the check has to
    # be about what the regex reads rather than about the character appearing.
    (r"^MARK[.]{1}A = 1$", False),
    (r'    "nba": \("market_line"\),$', False),
], ids=[
    "a trailing .* swallows the file",
    "an interior . spans the newlines under re.S",
    "a whole-line anchor with no dot",
    "escaped parens and a bare >=",
    "the DOTALL-safe run spelling the table documents",
    "an escaped literal dot",
    "a long whole-line anchor",
    "escaped quotes and parens",
    "a dot inside a character class is a literal",
    "the only unescaped dots here are inside quoted source",
])
def test_the_dot_check_reads_the_pattern_the_way_the_regex_will(pattern, expected):
    r"""The check itself, on the shapes that decide it -- including the two that
    must be ACCEPTED, so it cannot degenerate into a ban on the character.

    The last case is the one that could go wrong quietly: an anchor quoting source
    with double quotes has no `\.` in it, because `"` is not a regex metacharacter
    and needs no escape. A check that banned unescaped dots would still pass it --
    and a check that banned dots *before* the class/escape logic would reject the
    two rows the table documents as safe, which is how a guard gets deleted.
    """
    assert bool(harness.unescaped_dots(pattern)) is expected, (
        f"{pattern!r}: expected a dot-finding check to be "
        f"{'TRUE' if expected else 'FALSE'}"
    )


def test_a_table_holding_a_dot_anchor_is_refused_before_any_mutation_is_written(tmp_path):
    """The demonstration, as a test, so it does not depend on anyone remembering
    to add the row by hand.

    Two things are asserted, and the second is the one that matters. The run
    refuses with a message naming the row, and it does so **before the baseline
    pytest run**: a table that is wrong in its first row would otherwise cost a
    full 30-row sweep to discover, and a reviewer who ran out of patience would
    be right to.

    The refusal is also total rather than partial. A run that applied 31 rows and
    then refused would have written 31 mutations into the working tree, and the
    `.bak` is the only thing standing between that and a lost fix.
    """
    rows = [SILENT_CANARY, ("an anchor ending in .*", r"^MARKER = 1.*$", "MARKER = 1")]
    baks = _baks(tmp_path)

    code, printed = _run_main(rows, [(0, 300, 0)] * 3, tmp=tmp_path)

    assert code == 1, f"a table with a DOTALL-unsafe anchor exited {code}\n{printed}"
    assert "ends in a dot" in printed or "dot" in printed, printed
    assert "an anchor ending in .*" in printed, printed
    # No baseline, no mutation, no recovery copy: nothing was ever written.
    assert "baseline" not in printed, f"the static check ran after the baseline:\n{printed}"
    assert "BITES" not in printed, printed
    for bak in baks:
        assert not bak.exists(), f"{bak} was written by a run that refused the table"


# --- the expected-silent mark, checked against the observation -------------

#: The one row that carries the mark, spelled the way `MUTATIONS` spells it.
MARKED = (f"SERVED_SPORTS reordered [{harness.EXPECTED_SILENT_MARK}: "
         f"order-independence is the design]")
UNMARKED = "SERVED_SPORTS loses nba"

#: A canary row that APPLIES and does not bite, which is the shape a passing run
#: needs: `main` refuses to return 0 unless it saw the canary and it stayed
#: silent, so a run carrying no canary at all exits 1 for the right reason and
#: these tests would assert on the wrong exit code.
#:
#: **Anchored on the THROWAWAY files, never on `template.py`.** An earlier
#: version of this row anchored on a real line of the real template and replaced
#: it with a no-op. `main` then wrote that mutation into the working tree and
#: shelled out to pytest, which re-collected this file, which called `main`
#: again -- so a test of the harness mutated the source the harness is checking
#: and recursed into itself. The files are redirected to a tmp dir by
#: `_run_main`; this anchor only has to exist in them.
SILENT_CANARY = (harness.CANARY, r"^MARKER = 1$", "MARKER = 1")


def test_a_marked_row_that_bites_is_mislabelled_not_expected_silent():
    """The defect, as a function call rather than as a 27-minute run.

    `EXPECTED_SILENT_MARK` was tested BEFORE `elif not bite`, so for any marked
    row the `bite` value was never consulted: relabelling a row that fails 5
    tests as expected-silent printed `BITES (5 failed)`, listed it under "silent
    as documented", printed the success line, and exited 0. The label won
    because it was checked first, which makes the verdict a declaration rather
    than an observation.
    """
    assert harness.classify(MARKED, bite=False) == harness.EXPECTED
    assert harness.classify(MARKED, bite=True) == harness.MISLABELLED, (
        "a marked row that bit was accepted as expected-silent: the label decided "
        "the verdict instead of the run"
    )


def test_an_unmarked_row_is_reported_as_observed():
    """The other two buckets, so `classify` is covered rather than half-covered."""
    assert harness.classify(UNMARKED, bite=True) == harness.BITES
    assert harness.classify(UNMARKED, bite=False) == harness.SILENT


def test_the_mark_is_found_wherever_it_appears_in_a_label():
    """A substring test, in both directions.

    The mark is written into labels with a bracketed reason after it, so
    `in` rather than `==` is correct. A row whose label happens to contain the
    mark in its own text must be treated as marked: the alternative -- matching
    only at the end -- would let a row smuggle the mark in and escape the check.
    """
    assert harness.classify("anything at all " + harness.EXPECTED_SILENT_MARK, True) == harness.MISLABELLED
    assert harness.classify(harness.EXPECTED_SILENT_MARK, False) == harness.EXPECTED
    assert harness.classify("a row about the mark itself", True) == harness.BITES


def test_every_marked_row_in_the_table_names_a_reason():
    """A mark without a reason is a label with no claim in it.

    `SERVED_SPORTS reordered [expected silent: order-independence is the design]`
    is the whole reason the mechanism is allowed to exist: a reader has to be able
    to tell "nothing covers this input" (a failure) from "nothing depends on this"
    (a property of the design). A bare mark would collapse the two, which is the
    confusion the tool exists to remove.
    """
    marked = [label for label, _, _ in harness.MUTATIONS if harness.EXPECTED_SILENT_MARK in label]
    assert marked, "the mechanism is unused, so the table below proves nothing"
    for label in marked:
        _, _, reason = label.partition("[")
        reason = reason.rstrip("]").partition(":")[2].strip()
        assert reason, f"{label!r} carries the mark with no reason after the colon"
        assert len(reason) > 20, f"{label!r} has a reason too short to be one: {reason!r}"


def test_a_mislabelled_row_exits_non_zero(tmp_path):
    """Not the classification, the consequence.

    A bucket nothing acts on is a bucket that does not matter, and the bug being
    fixed was not that a marked row could bite -- it could not, by construction
    -- it was that a run reporting one still exited 0. So the exit code is
    asserted rather than inferred from the classification, and the success line
    is asserted absent, because "exited 1" and "printed the success line" were
    both true in the demonstration.
    """
    code, printed = _run_main(
        [(MARKED, r"^MARKER = 1$", "MARKER = 2")],
        [(0, 300, 0), (5, 295, 0), (0, 300, 0)],
        tmp=tmp_path,
    )
    assert code == 1, f"a mislabelled biting row exited {code}, not 1\n{printed}"
    assert "ACTUALLY BITES" in printed, printed
    assert "every mutation bit" not in printed, (
        f"the success line printed with a mislabelled row present: {printed}"
    )


def _run_main(mutations=(), runs=None, tmp=None) -> tuple[int, str]:
    """`main()` against throwaway files, with the pytest subprocess stubbed out.

    Three things are redirected, and each was a real failure:

    * **`run()`**, because it shells out to the real suite and a test that called
      it for real would re-enter this file's own collection and fork the suite
      into itself. The `.bak` lifecycle lives in `main` and not in `run`, so
      stubbing `run` still exercises the code under test.
    * **`ORIGINALS`**, because `main` writes the mutated source to disk. Against
      the real `template.py` a test of the harness mutated the file the harness
      exists to check, and the nested pytest run then measured the mutation.
    * **`MUTATIONS`**, so each test drives the one exit it is about.

    `runs` is the stub's per-call answer, so a test can drive the exit reasons
    (clean, a silent row, a biting canary, a red restore) separately. Default:
    three clean runs -- baseline, one mutation, restore.
    """
    import contextlib
    import io

    original_originals = dict(harness.ORIGINALS)
    original_mutations, original_run = harness.MUTATIONS, harness.run
    if tmp is not None:
        harness.ORIGINALS = {
            tmp / path.name: f"MARKER = 1\n{text}" for path, text in original_originals.items()
        }
    harness.MUTATIONS = list(mutations)
    answers = list(runs) if runs else [(0, 300, 0)] * 3
    calls = {"n": 0}

    def stub():
        answer = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        return answer

    harness.run = stub
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = harness.main()
    finally:
        harness.ORIGINALS = original_originals
        harness.MUTATIONS, harness.run = original_mutations, original_run
    return code, out.getvalue()


def _baks(tmp=None) -> list:
    """The `.bak` paths a run under `tmp` would leave, or the real ones."""
    names = [p.name for p in (harness.TARGET, harness.CONFIG, harness.PROMPTS)]
    base = [harness.TARGET, harness.CONFIG, harness.PROMPTS] if tmp is None else \
        [tmp / n for n in names]
    return [p.with_suffix(p.suffix + ".bak") for p in base]


def test_a_clean_run_leaves_no_bak_behind(tmp_path):
    """Item 6b: the `.bak` files existed for recovery, and only the SUCCESS path
    deleted them, so a clean failing run left two untracked files in the tree.

    The fix is not to stop writing them -- a run interrupted mid-table must not
    leave mutated source -- but to remove them on every path except a genuine
    crash, which cannot clean up after itself by definition. Asserted on the
    clean path here and on the failure paths below.

    Driven against `tmp_path` copies rather than the working tree: `main` writes
    every mutation to disk, so a test of the cleanup that ran against the real
    files would leave the real tree mutated whenever the assertion failed.
    """
    baks = _baks(tmp_path)
    code, printed = _run_main([SILENT_CANARY], tmp=tmp_path)
    assert code == 0, printed
    for bak in baks:
        assert not bak.exists(), f"{bak} was left behind by a clean run"


def test_a_failing_run_also_leaves_no_bak_behind(tmp_path):
    """The case that was broken: exit non-zero with a clean tree.

    A run that reports a silent mutation returns 1, and it used to return 1
    *with* `template.py.bak` and `config.py.bak` still on disk -- litter after a
    run that completed normally, which is the case where litter is least
    defensible. The same holds for the canary-bit and mislabelled exits, so all
    three are driven: they return 1 for different reasons and each must clean up.
    """
    baks = _baks(tmp_path)
    never = (r"NOT_AN_ANCHOR_ANYWHERE", "")
    # Three non-zero exits, three different reasons, one requirement each: the
    # tree was restored, so the recovery copies are litter. The fourth -- a red
    # restore -- is the exception, and is the next test.
    cases = {
        "an unmarked silent row": ([("a silent row", *never)], [(0, 300, 0)] * 3),
        "a mislabelled biting row": (
            [(MARKED, r"^MARKER = 1$", "MARKER = 2")],
            [(0, 300, 0), (5, 295, 0), (0, 300, 0)],
        ),
        "a biting canary": (
            [(harness.CANARY, r"^MARKER = 1$", "MARKER = 2")],
            [(0, 300, 0), (5, 295, 0), (0, 300, 0)],
        ),
    }
    for name, (mutations, runs) in cases.items():
        code, printed = _run_main(mutations, runs, tmp=tmp_path)
        assert code == 1, f"{name}: exited {code}\n{printed}"
        for bak in baks:
            assert not bak.exists(), f"{name} left {bak} behind on a {code} exit"


def test_a_failed_restore_keeps_the_bak_because_it_is_the_recovery_path(tmp_path):
    """The one path that must NOT clean up, and why it is the exception.

    If the post-restore run is red, the working tree does not hold the original
    and the `.bak` files are the only copy that does. Deleting them there would
    turn a loud, recoverable failure into a silent loss. So the cleanup is placed
    after the restore check rather than in a `finally`, which is the opposite of
    the usual instinct and is the whole reason the placement is commented.
    """
    baks = _baks(tmp_path)
    # baseline clean, canary silent, restore RED
    code, printed = _run_main([SILENT_CANARY], [(0, 300, 0), (0, 300, 0), (9, 0, 0)], tmp=tmp_path)
    assert code == 1, printed
    assert "RESTORE FAILED" in printed, printed
    for bak in baks:
        assert bak.exists(), (
            f"{bak} was deleted after a failed restore, which is the one copy of "
            f"the original that was left"
        )


def test_the_harness_passes_no_tracebacks():
    """`--tb=no` is part of the fix, and this is what holds it there.

    The corrected tally is "the summary line is last", and that is a heuristic
    rather than a rule. Tracebacks are a page of text between a failure and the
    summary, and a page of failing-test output is exactly where a stray
    "5 passed" comes from. Removing the tracebacks shrinks the surface the
    heuristic has to survive, which is why it is a flag and not a preference.

    Checked against the built argument list rather than the source text, so a
    comment mentioning the flag cannot satisfy it.
    """
    captured: list[list[str]] = []
    real_run = harness.subprocess.run

    def fake_run(args, **kwargs):
        captured.append(args)
        return real_run(["true"], **kwargs)

    original = harness.subprocess.run
    harness.subprocess.run = fake_run
    try:
        harness.run()
    finally:
        harness.subprocess.run = original

    assert captured, "the harness did not invoke pytest"
    argv = captured[0]
    assert "--tb=no" in argv, f"pytest is run without --tb=no: {argv}"
    assert "-q" in argv, f"pytest is run without -q: {argv}"
