#!/usr/bin/env python3
"""Mutation-check the explainer's quoted-line handling and the NBA serving guards.

Run from `services/explainer`:
    uv run --extra dev python tools/mutcheck_template_line.py

Why this is a file and not a shell loop: three harnesses in these projects
reported "all passed" for the wrong reason, in three different ways, and two of
those shipped inside a commit.

* **It separates failed, passed and errored** and treats all three as a bite. An
  earlier version read the PASSED count out of a line reading `1 failed, 9
  passed`, so four mutations looked like partial passes; another read a collection
  error -- a mutation that produced a syntax error -- as zero failures, i.e.
  silent.
* **It purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE`** before every run.
  Python treats a `.pyc` as current on the source's mtime *and size*, and the
  stored mtime has one-second resolution, so a mutation that keeps the file the
  same length inside the same second is silently ignored and pytest imports the
  unmutated bytecode. **This script reported one guard as SILENT on four runs of
  five and BITES on the fifth, purely on where the second boundary fell.** Adding
  a debug `read_text()` "fixed" it, because a few more milliseconds was enough.
  A check that fails intermittently and for no visible reason is worse than one
  that fails consistently, because it is believed the times it says yes.
* **It runs the WHOLE suite, not one file.** Scoped to
  `test_template_quoted_line.py` it cannot see a guard in
  `test_unserved_sport.py` -- and two did survive a review that way.
* **It carries a canary** that must stay silent, so a harness which never applies
  its mutations is distinguishable from a set of guards that never fail.
* **It restores under `try/finally`, and keeps a `.bak` beside each file it
  touches**, because an interrupted run must not leave a mutated source. The
  docstring used to claim the `.bak` and nothing wrote one; and the `config.py`
  restore was `write_text(read_text())`, a no-op that would have left the file
  mutated if anything raised mid-table. Both are now real. The `.bak` exists
  because on the sibling harness a bug in its own unpacking raised mid-table, and
  the `git checkout` used to recover **reverted three unrelated fixes along with
  the mutation** -- so "restore what you mutated" has to name which file. The
  `.bak` is removed once the restore is CONFIRMED, and on no earlier exit, so a
  run that merely found a silent mutation does not leave litter behind; a crash
  still leaves them, which is the case they are for.
* **It reads its own tally out of the pytest summary and not out of the first
  number it finds**, because the first number it finds is frequently in a
  traceback. See `_last_count`.
* **It checks a row's expected-silent MARK against what the run did**, and does
  not let the mark stand in for the observation. See `classify`.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

TARGET = pathlib.Path("explainer/template.py")
CONFIG = pathlib.Path("explainer/config.py")
PROMPTS = pathlib.Path("explainer/prompts.py")
SUITE = "tests/"  # the whole suite, on purpose -- see the docstring
#: Every file a row may mutate, with its original text captured at import.
#:
#: A dict rather than three module-level names, because three names meant three
#: places to add a file and three places to forget one: `prompts.py` joined
#: because the prompt is a writer too, and a row that reinstates the figures rule
#: the template no longer supports has to be applied to the file that holds it.
#:
#: The originals are read ONCE, at import, and the `config.py` entry used to be
#: ``write_text(read_text())`` -- writing back what it had just read, so an
#: exception between the write and the restore left the file mutated. Capturing
#: the text is the only version of this that is not a no-op.
ORIGINALS: dict[pathlib.Path, str] = {
    path: path.read_text() for path in (TARGET, CONFIG, PROMPTS)
}

#: Expected to be silent, with the reason recorded. Surviving because a property
#: is order-independent is a pass; surviving because nothing covers an input is a
#: failure, and the two must not share a verdict.
EXPECTED_SILENT_MARK = "expected silent"
CANARY = "CANARY: nothing covers this"
#: The four buckets a row can land in. Named so `classify` reads as a rule rather
#: than as branching, and so a test can assert on the names.
EXPECTED = "expected-silent"
MISLABELLED = "mislabelled"
SILENT = "silent"
BITES = "bites"

#: The one line every spread-sentence row anchors on, named once because four
#: rows share it and a copy pasted four times is four things to keep in step.
#:
#: `^...$` with `count=1`, so the match is the whole line and the FIRST such line
#: in the file. Do not quote that line's text verbatim in a comment above it in
#: `template.py`: the comment would take the match, the mutation would land
#: there and change nothing, and the row would report itself covered. That is
#: not hypothetical -- the `>=`-becomes-`>` row read SILENT for exactly this
#: reason. `template.py` carries the same warning at the row it applies to.
_SPREAD_SENTENCE = r'^                             f"It projects a margin of \{abs\(margin\):g\} \{unit\}, against a line of \{line\}\."\)\)$'

MUTATIONS = [
    # --- _quoted_line: the two-key read ---
    # A canary has to mutate something NOTHING covers, or it stops being the
    # control. This one used to be `MAX_FACTORS`, and it BITES -- correctly, since
    # a review asked for the factor budget to be pinned and it now is. A canary
    # that starts failing is a canary that has been promoted into a real test,
    # which is fine for the suite and useless here.
    (CANARY, r'unit = "goals" if sport == "pl" else "points"',
     'unit = "points" if sport == "pl" else "points"'),
    ("precedence flipped: line before market_line",
     r"^    for key in keys:$", "    for key in reversed(keys):"),
    ("neither key is read",
     r"^    for key in keys:$", "    for key in ():"),
    ("the strip is dropped, so blank lines slip through",
     r"^        if isinstance\(value, str\):$", "        if False:"),
    ("the truthiness test is dropped, so 0 and '' become lines",
     r"^        if value:$", "        if True:"),
    ("the bool guard is dropped, so True renders as a line",
     r"^        if isinstance\(value, bool\):$", "        if False:"),
    ("the non-dict guard is dropped",
     r"^    if not isinstance\(market, dict\):$", "    if False:"),
    # --- the default key list, and the prompt ---
    # A default argument nothing uses is a statement no observation can check.
    # This row puts one back and the suite has to notice the code changed shape
    # even though no rendered output does: `test_the_helper_takes_no_default_
    # key_list` reads the signature. Without it the row would be SILENT, which
    # is the whole reason the default was removed -- a reader could change it and
    # no run of anything would say so.
    ("the dead default key list comes back on the helper",
     r"^def _quoted_line\(market: dict \| None, keys: tuple\[str, \.\.\.\]\) -> str \| None:$",
     'def _quoted_line(market: dict | None, keys: tuple[str, ...] = ("line",)) -> str | None:'),
    # The one statement of the default is now reachable, so a change to it
    # changes what a sport absent from the table renders. This bites on the
    # ORDER and on the LENGTH, which is what the dead default could not do.
    ("the default key list loses the market_line key",
     r'^DEFAULT_MARKET_LINE_KEY: tuple\[str, \.\.\.\] = \("market_line", "line"\)$',
     'DEFAULT_MARKET_LINE_KEY: tuple[str, ...] = ("line",)'),
    ("the default key list is reversed, so a model's wording is preferred",
     r'^DEFAULT_MARKET_LINE_KEY: tuple\[str, \.\.\.\] = \("market_line", "line"\)$',
     'DEFAULT_MARKET_LINE_KEY: tuple[str, ...] = ("line", "market_line")'),
    # `prompts.SYSTEM`'s figures rule, which used to hand the model a sentence
    # asserting a model-vs-market comparison the service cannot check.
    # `test_prompt_instructions.py` holds the wording; these two rows are what
    # stops it coming back as wording the test would have to be edited to accept.
    # `[^\n]*` rather than `.*`: these anchors are matched with `re.S`, and `.*`
    # under DOTALL runs to the end of the FILE -- so the first version of these
    # two rows replaced everything from the figures rule to the closing quote of
    # SYSTEM, and both reported BITES as a COLLECTION ERROR. A mutation that
    # breaks the file into not parsing is a bite, so the table was right and the
    # row was testing nothing it claimed to. The same DOTALL trap applies to any
    # future anchor that is not whole-line, which is why `_SPREAD_SENTENCE` above
    # is written without a `.` at all.
    ("the prompt quotes the model-vs-market comparison back",
     r"^Write NO figures in the panel\.[^\n]*$",
     'Write NO figures in the panel. The panel draws every number from FACTS itself, '
     'so a figure in your text would either duplicate it or contradict it. Say "the '
     'line asks for more than the model rates the gap" and let the panel show the gap.'),
    ("the prompt's rule on which number is bigger is dropped",
     r"^Write NO figures in the panel\.[^\n]*$",
     "Write NO figures in the panel. The panel draws every number from FACTS itself, "
     "so a figure in your text would either duplicate it or contradict it. Say which "
     "market the row is about and let the panel show the gap."),

    # --- the two call sites: these are the actual fix ---
    # The spread gate grew a `big_enough` term for the margin floor, so this
    # anchor matches the WHOLE condition and `big_enough` gets its own rows
    # below. An anchor that matched a prefix would have kept applying here and
    # silently stopped testing the whole gate -- which is the NOT APPLIED
    # failure mode, arrived at by making the code correct.
    ("the spread factor never fires",
     r"^    if margin_market is not None and margin is not None and label and quoted and big_enough:$",
     "    if False:"),
    # --- the margin floor: `model_margin: 0` narrated a disagreement of nothing ---
    ("the margin floor is dropped, so a zero gap is narrated again",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None"),
    # Anchored to the CODE line, with `^...$`, and not to the bare expression:
    # the `count=1` takes the first match in the file, and a comment quoting the
    # expression verbatim sits above this line and absorbs the mutation. That is
    # not hypothetical -- this row read SILENT for that reason while the
    # boundary test below it went unrun. See the NOTE in `template.py`.
    ("the floor becomes exclusive, so a real half-point gap is dropped",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None and abs(margin) > MIN_SPREAD_MARGIN"),
    ("the floor is lowered to 0, admitting every margin again",
     r"^MIN_SPREAD_MARGIN = 0\.5$", "MIN_SPREAD_MARGIN = 0.0"),
    ("the floor loses its abs(), so a negated small margin narrates again",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None and margin >= MIN_SPREAD_MARGIN"),
    ("the total gate reverts to the NBA-blind `line` check",
     r"^    if total_market is not None and total is not None and total_line is not None:$",
     '    if total_market is not None and total is not None and total_market.get("line") is not None:'),
    ("NBA's market-line key becomes the default two-key read",
     r'    "nba": \("market_line",\),', '    "nba": ("market_line", "line"),'),
    ("NBA is dropped from the market-line table",
     r'    "nba": \("market_line",\),\n', ""),
    ("NFL's line is added to the table, re-enabling the model-vs-model sentence",
     r'    "nba": \("market_line",\),', '    "nfl": ("market_line",),\n    "nba": ("market_line",),'),
    ("_START: f1 and pl entries swapped",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "kickoff", "pl": "the session started", "nba": "tip-off"}'),
    ("_START: the f1 phrase mangled",
     r'"f1": "the session started"', '"f1": "the race started"'),
    ("NBA's tip-off wording removed again",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "the session started", "pl": "kickoff"}'),

    # --- the spread factor's claims: about the market, about a side ---
    # A row for text that was DELETED is what stops it coming back. The three
    # below restore exactly what shipped, and the fourth invents a comparison
    # the fix declined to compute. A test that only checks the honest numbers are
    # PRESENT cannot catch any of them: the false sentence only ever added words
    # or a team, so every "3.4 points better" / "BAL -2.5" assertion stayed green
    # while the claim shipped. Exact equality is what closes that, and these rows
    # are the other half -- they are what would stop a *different* false sentence
    # passing a *different* substring test.
    ("the deleted clause comes back",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {abs(margin):g} {unit}, against a line of {line}. "\n'
     '                             f"That is the market asking for more than the model thinks the gap is worth."))'),
    # The second claim the sentence used to make, and the one with no test that
    # could see it until the sentence stopped making it: `model_margin` is
    # home-minus-away, NFL and CFB word the line from the home team, and the
    # bundle carries no home/away designation -- so naming the pick attributes a
    # margin to a side it may not belong to. The test that has to break is
    # `test_the_spread_sentence_is_the_same_whichever_side_the_pick_is_on`.
    ("the pick is named again, so a margin is attributed to a side",
     _SPREAD_SENTENCE,
     '                             f"It rates {label} {abs(margin):g} {unit} better, against a line of {line}."))'),
    ("a comparison is invented, so the sentence depends on the line",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {abs(margin):g} {unit}, against a line of {line}. "\n'
     '                             f"The market asks for {\'more\' if float(quoted.rsplit(\'-\', 1)[-1]) > abs(margin) else \'less\'}."))'),
    ("the abs() goes, so a negative margin is written as a signed gap",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {margin:g} {unit}, against a line of {line}."))'),
    ("the spread factor's mark goes back to a constant 'down'",
     r'^        factors\.append\(_fact\(str\(margin_market\["market"\]\), NEUTRAL, "The line",$',
     '        factors.append(_fact(str(margin_market["market"]), "down", "The line",'),

    # --- config.SERVED_SPORTS, via the module that reads it ---
    ("SERVED_SPORTS loses nba",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb")'),
    ("SERVED_SPORTS regains f1",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb", "nba", "f1")'),
    # The one row that carries the expected-silent mark, and the reason it is
    # still here rather than deleted.
    #
    # **The mechanism is kept because the reason is a property of the design and
    # belongs in the table, not in a reader's memory.** `SERVED_SPORTS` is read
    # for membership (`sport not in SERVED_SPORTS`, service.py) and as a set
    # (`set(expected) == set(SERVED_SPORTS)`, test_template_quoted_line.py), so
    # nothing consumes its order. "Nothing depends on this" is the one kind of
    # silence that is a RESULT rather than a gap, and a table that cannot say so
    # cannot distinguish it from a missing test -- which is the confusion the
    # whole tool exists to remove.
    #
    # The check is now `not bite` rather than "the label says so", so the row is
    # only filed as documented-silent when the run agrees. If a test is ever added
    # that makes the order matter, this row BITES and the run fails loudly,
    # which is the correct outcome: the property is no longer true.
    #
    # Its own limit, stated: the label is checked against the observation, so a
    # row marked expected-silent can no longer hide a bite. It cannot tell you
    # WHY nothing depends on the order, only that nothing does.
    (f"SERVED_SPORTS reordered [{EXPECTED_SILENT_MARK}: order-independence is the design]",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', 'SERVED_SPORTS = ("nba", "pl", "nfl", "cfb")'),
]


def _purge_bytecode() -> None:
    """Delete every `__pycache__` so a mutation can never be masked by a stale
    `.pyc`. See the module docstring for why this is load-bearing."""
    for d in pathlib.Path(".").rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run() -> tuple[int, int, int]:
    """(failed, passed, errored). Any of the first and third counts as a bite."""
    _purge_bytecode()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(
        # `--tb=no` is not a quietness setting; see `_last_count`. Without it
        # every failure prints its traceback, and a traceback is a page of text
        # containing both count words.
        ["uv", "run", "--extra", "dev", "python", "-m", "pytest", SUITE,
         "-q", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env,
    )
    out = p.stdout + p.stderr
    if p.returncode not in (0, 1):
        return -1, 0, 1

    def count(word: str) -> int:
        return _last_count(out, word)

    return count("failed"), count("passed"), 0


#: The words the tally reads, and the two test functions in
#: `tests/test_mutation_tally.py` that pin them. Kept here so a test can import
#: the same pair the harness uses rather than re-typing it and drifting.
COUNT_WORDS = ("failed", "passed")


def _last_count(out: str, word: str) -> int:
    """The count `word` reports, taken from the LAST mention in `out`.

    **The last, and the reason is that pytest's `-q` summary is the last thing it
    prints.** Everything before it is noise that happens to contain the same
    words: tracebacks quote the assertion that failed, `E   assert 1 == 2` lines
    carry the numbers, and a failure's own message can name a count. `re.search`
    took the FIRST match anywhere in `stdout + stderr`, so:

    * a run with 26 real failures reported `2 failed`, read out of an
      intermediate line, and the mutation looked like a partial bite;
    * 257 real passes reported as `26`, from the same line;
    * a run whose output echoed "0 passed" reported `passed: 0` and nothing else.

    That last one is the live path to a FALSE PASS. A mutation that breaks
    something is judged on `failed > 0`; if a `0 failed` is echoed anywhere
    earlier in the output, `re.search` reads THAT and calls the row silent, so a
    mutation that broke five tests is filed under "did not bite". A number read
    out of a traceback is a number about a traceback.

    `[-1]` because the summary line is last, not because "last" is a rule about
    how many numbers a pytest run prints. `--tb=no` is passed for the same
    reason and is load-bearing rather than cosmetic: with tracebacks on, the
    output is large enough that the last-match heuristic is being asked to find
    one line near the end of a page, and the page contains the words.
    """
    found = re.findall(rf"(\d+) {word}", out)
    return int(found[-1]) if found else 0


def classify(label: str, bite: bool) -> str:
    """Where a row goes, as one function so the rule can be tested directly.

    The three outcomes a row can have, and the mark is checked AGAINST the
    observation rather than in place of it:

    * `EXPECTED` -- the row is marked expected-silent and did not bite. The mark
      is a claim about what should happen, and the run agreed.
    * `MISLABELLED` -- the row is marked expected-silent and DID bite. A
      contradiction between the table's own labelling and the table's own
      measurement, which is a defect in the harness. This case did not exist
      before: the mark was tested before `elif not bite`, so a marked row was
      filed as documented-silent whatever it did.
    * `SILENT` / `BITES` -- an unmarked row, reported as observed.

    Extracted from `main` because a rule that can only be exercised by running
    27 mutations is a rule nobody runs on purpose, and because the bug being
    fixed here is a rule about ORDER: a table that lists `not bite` after the
    mark has decided the outcome. As one function the order is the code, and
    `tests/test_mutation_tally.py` covers all five cases without a subprocess.
    """
    marked = EXPECTED_SILENT_MARK in label
    if marked:
        return EXPECTED if not bite else MISLABELLED
    return BITES if bite else SILENT


def _drop_backups() -> None:
    """Remove the recovery copies, once the restore has been confirmed.

    They were written so an INTERRUPTED run cannot leave mutated source behind,
    which is why they exist; they are not a log and nothing reads them. The
    unlink used to sit at the end of the success path only, so every non-zero
    exit -- a silent mutation, a biting canary, a mislabelled row -- returned 1
    having left three untracked files in the working tree. That is litter after a
    run that finished, and it is the case where litter is least defensible: the
    interruption it protects against did not happen, or the run would not have
    reached the cleanup at all.

    A genuine crash still leaves them, which is the point of writing them: SIGKILL
    and a pulled power cord run no cleanup, and that is the one case where the
    `.bak` is the recovery path rather than litter.
    """
    for path in ORIGINALS:
        path.with_suffix(path.suffix + ".bak").unlink(missing_ok=True)


def main() -> int:
    base_failed, base_passed, base_errored = run()
    if base_errored or base_failed:
        print(f"  BASELINE IS RED: {base_failed} failed, {base_errored} errored "
              f"({base_passed} passed).")
        print("  Every mutation would report BITES for free, so the table below would")
        print("  be meaningless. Fix the baseline first.")
        return 1
    names = ", ".join(p.name for p in ORIGINALS)
    print(f"  baseline: {base_passed} passed, 0 failed -- the table below is meaningful")
    print(f"  {len(MUTATIONS)} mutations against {names}\n")

    silent: list[str] = []
    expected: list[str] = []
    mislabelled: list[str] = []
    canary_ok = False
    for path, text in ORIGINALS.items():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(text)
    print(f"  originals also at " + ", ".join(
        f"{p.name}.bak" for p in ORIGINALS) + ", in case this run is interrupted")

    try:
        for label, pattern, replacement in MUTATIONS:
            # Every file may hold the anchor, and the row is applied to whichever
            # one does. The template, config.py and prompts.py are all writers,
            # so all three are fair game for a row that reinstates a deleted
            # claim.
            for target, keep in ORIGINALS.items():
                new, n = re.subn(pattern, replacement, keep, count=1, flags=re.M | re.S)
                if n == 1:
                    target.write_text(new)
                    try:
                        failed, passed, errored = run()
                    finally:
                        # Restore BEFORE reading the tally, and unconditionally.
                        # An exception out of `run()` used to leave the mutated
                        # source on disk until the outer `finally`, and the outer
                        # `finally` restores the OTHER files first, so a crash
                        # between the two wrote this one back over a mutation the
                        # next run's baseline would then have measured.
                        target.write_text(keep)
                    break
            else:
                print(f"  {label[:56]:<56} NOT APPLIED (anchor in no file)")
                silent.append(f"{label} [not applied]")
                continue
            if errored:
                verdict, bite = "BITES (collection error)", True
            elif failed > 0:
                verdict, bite = f"BITES ({failed} failed)", True
            else:
                verdict, bite = f"*** SILENT *** ({passed} passed)", False
            print(f"  {label[:56]:<56} {verdict}")
            if label == CANARY:
                # The canary must be SILENT. It was previously `canary_ok = True`
                # in BOTH the biting and the silent branch, which made the check
                # below unreachable and the closing line a lie: pointed at
                # `MAX_FACTORS` -- which this round pins, so it bites -- the run
                # printed "BITES (1 failed)" and then "the canary stayed silent as
                # it should", and exited 0. A control that cannot fail is not a
                # control, and this is the only negative control the tool has.
                canary_ok = not bite
            else:
                # The mark records an EXPECTATION and is checked against the
                # observation by `classify`; see its docstring for the case that
                # did not exist before, where a marked row was filed as
                # documented-silent whether it bit or not.
                #
                # An `else` and not a bare statement after the canary branch: the
                # canary is a control, not a row, and a silent canary is the
                # passing outcome. Filing it under "did not bite" as well would
                # make every clean run report a silent mutation and exit 1 -- the
                # mirror of the defect being fixed here, and one this refactor
                # introduced before it was caught by the first clean run.
                bucket = classify(label, bite)
                if bucket == EXPECTED:
                    expected.append(label.split(" [")[0])
                elif bucket == MISLABELLED:
                    mislabelled.append(label)
                elif bucket == SILENT:
                    silent.append(label)
    finally:
        for path, text in ORIGINALS.items():
            path.write_text(text)

    failed, passed, errored = run()
    print(f"\n  restored: {passed} passed, {failed} failed, {errored} errored")
    if errored or failed:
        # No cleanup here on purpose. The tree is wrong and the `.bak` is what
        # fixes it, so removing the recovery copy would destroy the only
        # remaining copy of the original.
        print("  RESTORE FAILED -- do not trust the tree. The .bak files are the "
              "recovery path and have been left in place.")
        return 1
    # Every path from here on is a path where the tree was restored, so the
    # recovery copies are litter rather than a safety net.
    _drop_backups()
    if expected:
        print(f"  {len(expected)} mutation(s) silent as documented:")
        for s in expected:
            print(f"    - {s}")
    # Checked BEFORE the `silent` report and before the canary, because a
    # mislabelled row means the table's own labelling is wrong, and everything
    # the run says after this point is read against that labelling. Its own
    # return is 1 so a run that has one cannot exit 0.
    if mislabelled:
        print("  A ROW LABELLED EXPECTED-SILENT ACTUALLY BITES -- the harness is "
              "misreporting itself:")
        for s in mislabelled:
            print(f"    - {s}")
        print("  The label is a claim about what should happen; the run is what did.")
        print("  Either the expectation is now wrong (a test was added, so the row is "
              "a real guard and the mark must go) or the mark is on the wrong row.")
        return 1
    if silent:
        print(f"  {len(silent)} mutation(s) did not bite:")
        for s in silent:
            print(f"    - {s}")
        return 1
    if not canary_ok:
        print("  THE CANARY BIT -- the harness is misreporting; distrust the table "
              "above entirely.")
        print("  Either the canary now covers something real (a test was added for "
              "it, so it is no longer a control) or the mutations are not being "
              "applied. Fix the canary before reading any row.")
        return 1
    # The `.bak` files were already removed above, once the restore was
    # confirmed; nothing to do here. Named so a reader looking for the unlink
    # finds that it moved and why, rather than concluding it was dropped.
    print("  every mutation bit or was documented as expected-silent, "
          "and the canary stayed silent as it should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
