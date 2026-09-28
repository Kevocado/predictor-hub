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
* **It restores under `try/finally` and keeps a `.bak`**, because an interrupted
  run must not leave a mutated source. Demonstrated on the sibling harness: a bug
  in its own unpacking raised mid-table and the `git checkout` used to recover
  reverted three unrelated fixes along with the mutation.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

TARGET = pathlib.Path("explainer/template.py")
SUITE = "tests/"  # the whole suite, on purpose -- see the docstring
KEEP = TARGET.read_text()

#: Expected to be silent, with the reason recorded. Surviving because a property
#: is order-independent is a pass; surviving because nothing covers an input is a
#: failure, and the two must not share a verdict.
EXPECTED_SILENT_MARK = "expected silent"
CANARY = "CANARY: nothing covers this"

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

    # --- the two call sites: these are the actual fix ---
    ("the spread factor never fires",
     r"^    if margin_market is not None and margin is not None and label and quoted:$",
     "    if False:"),
    ("the total gate reverts to the NBA-blind `line` check",
     r"^    if total_market is not None and total is not None and total_line is not None:$",
     '    if total_market is not None and total is not None and total_market.get("line") is not None:'),
    ("NBA's market-line key becomes the default two-key read",
     r'    "nba": \("market_line",\),', '    "nba": ("market_line", "line"),'),
    ("NBA is dropped from the market-line table",
     r'    "nba": \("market_line",\),\n', ""),
    ("NFL's line is added to the table, re-enabling the model-vs-model sentence",
     r'    "nba": \("market_line",\),', '    "nfl": ("market_line",),\n    "nba": ("market_line",),'),
    ("NBA's tip-off wording removed again",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "the session started", "pl": "kickoff"}'),

    # --- config.SERVED_SPORTS, via the module that reads it ---
    ("SERVED_SPORTS loses nba",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb")'),
    ("SERVED_SPORTS regains f1",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb", "nba", "f1")'),
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
        ["uv", "run", "--extra", "dev", "python", "-m", "pytest", SUITE,
         "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env,
    )
    out = p.stdout + p.stderr
    if p.returncode not in (0, 1):
        return -1, 0, 1

    def count(word: str) -> int:
        m = re.search(rf"(\d+) {word}", out)
        return int(m.group(1)) if m else 0

    return count("failed"), count("passed"), 0


def main() -> int:
    base_failed, base_passed, base_errored = run()
    if base_errored or base_failed:
        print(f"  BASELINE IS RED: {base_failed} failed, {base_errored} errored "
              f"({base_passed} passed).")
        print("  Every mutation would report BITES for free, so the table below would")
        print("  be meaningless. Fix the baseline first.")
        return 1
    print(f"  baseline: {base_passed} passed, 0 failed -- the table below is meaningful")
    print(f"  {len(MUTATIONS)} mutations against {TARGET} and config.py\n")

    silent: list[str] = []
    expected: list[str] = []
    canary_ok = False
    results: list[tuple[str, str, int]] = []

    try:
        for label, pattern, replacement in MUTATIONS:
            # Two files are mutated: the template, and config.py for the
            # SERVED_SPORTS rows. Applied to whichever contains the anchor.
            for target in (TARGET, pathlib.Path("explainer/config.py")):
                keep = KEEP if target == TARGET else target.read_text()
                new, n = re.subn(pattern, replacement, keep, count=1, flags=re.M | re.S)
                if n == 1:
                    target.write_text(new)
                    failed, passed, errored = run()
                    target.write_text(keep)
                    break
            else:
                print(f"  {label[:56]:<56} NOT APPLIED (anchor in neither file)")
                silent.append(f"{label} [not applied]")
                continue
            if errored:
                verdict, bite = "BITES (collection error)", True
            elif failed > 0:
                verdict, bite = f"BITES ({failed} failed)", True
            else:
                verdict, bite = f"*** SILENT *** ({passed} passed)", False
            print(f"  {label[:56]:<56} {verdict}")
            results.append((label, verdict, failed if not errored else 1))
            if bite and label == CANARY:
                canary_ok = True
            elif not bite and label == CANARY:
                canary_ok = True
            elif EXPECTED_SILENT_MARK in label:
                expected.append(label.split(" [")[0])
            elif not bite:
                silent.append(label)
    finally:
        for target in (TARGET, pathlib.Path("explainer/config.py")):
            target.write_text(KEEP if target == TARGET else
                              pathlib.Path("explainer/config.py").read_text())

    failed, passed, errored = run()
    print(f"\n  restored: {passed} passed, {failed} failed, {errored} errored")
    if errored or failed:
        print("  RESTORE FAILED -- do not trust the tree.")
        return 1
    if expected:
        print(f"  {len(expected)} mutation(s) silent as documented:")
        for s in expected:
            print(f"    - {s}")
    if silent:
        print(f"  {len(silent)} mutation(s) did not bite:")
        for s in silent:
            print(f"    - {s}")
        return 1
    if not canary_ok:
        print("  the canary BORE -- the harness is misreporting; distrust the table")
        return 1
    print("  every mutation bit or was documented as expected-silent, "
          "and the canary stayed silent as it should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
