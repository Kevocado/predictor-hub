#!/usr/bin/env python3
"""Mutation-check the explainer's quoted-line helper and its two call sites.

Run from `services/explainer`: `uv run --extra dev python tools/mutcheck_template_line.py`

Why this exists as a file rather than a shell loop: three harnesses in this
session reported a *collection error* or a *partial* failure as "all passed",
because they read the passed count out of a line like `1 failed, 9 passed`. A
mutation harness that cannot tell "the guard held" from "the test file did not
even parse" is worse than no harness -- it manufactures confidence. So this
script:

* reads failures, passes **and** errors separately, and treats any of the three
  as a bite (a mutation that breaks collection *did* change behaviour);
* carries a canary that must stay silent, so a harness which never applies its
  mutations is distinguishable from a set of guards that never fail;
* restores the file after every mutation and re-runs at the end to prove it;
* **purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE`** before every run.

That last one is not tidiness. Python decides a `.pyc` is current by comparing
the source's mtime and size, and the mtime it stores has one-second resolution.
So a mutation that happens to keep the file the same length as the original --
swapping `("market_line", "line")` for `("line", "market_line")`, which is 21
characters either way -- and lands in the same second as the last restore, is
silently ignored: pytest imports the *unmutated* bytecode and reports a clean
pass.

It is intermittent, which is the worst way for a harness to be wrong. This
script reported "precedence flipped: SILENT" on four runs out of five and
correctly reported BITES on the fifth, purely on where the second boundary fell.
Adding a debug `read_text()` "fixed" it, because the extra few milliseconds were
enough. A guard check that passes most of the time and fails for no visible
reason is a guard nobody will trust, so the cache is purged explicitly.

The guards it covers are the fix for NBA: the key `line` means the MARKET's line
in NFL and CFB and the MODEL's own wording in NBA, and the template used to read
it as the market's in both the spread and the total factor.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

TARGET = pathlib.Path("explainer/template.py")
TEST = "tests/test_template_quoted_line.py"
KEEP = TARGET.read_text()

CANARY = "CANARY: nothing covers this"

MUTATIONS = [
    (CANARY, r"^MAX_FACTORS = 4$", "MAX_FACTORS = 9"),
    # the precedence between the two keys
    ("precedence flipped: line before market_line",
     r'    for key in \("market_line", "line"\):', '    for key in ("line", "market_line"):'),
    ("neither key is read",
     r'    for key in \("market_line", "line"\):', "    for key in ():"),
    ("the strip is dropped (blank lines slip through)",
     r"        if isinstance\(value, str\):", "        if False:"),
    ("the truthiness test is dropped (0 and '' become lines)",
     r"^        if value:$", "        if True:"),
    ("a None market is dereferenced",
     r"^    if not market:$", "    if False:"),
    # the two call sites -- these are the actual fix
    ("the spread factor never fires",
     r"if margin_market is not None and margin is not None and label and quoted:",
     "if False:"),
    ("the total gate reverts to the NBA-blind `line` check",
     r"if total_market is not None and total is not None and total_line is not None:",
     'if total_market is not None and total is not None and total_market.get("line") is not None:'),
    ("NBA's tip-off wording removed again",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "the session started", "pl": "kickoff"}'),
]


def _purge_bytecode() -> None:
    """Delete every `__pycache__` so a mutation can never be masked by a stale
    `.pyc`. See the module docstring for why this is load-bearing and not
    tidiness."""
    for d in pathlib.Path(".").rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run() -> tuple[int, int, int]:
    """(failed, passed, errored). Any of the first and third counts as a bite."""
    _purge_bytecode()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(
        ["uv", "run", "--extra", "dev", "python", "-m", "pytest", TEST,
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
    silent: list[str] = []
    canary_ok = False

    for label, pattern, replacement in MUTATIONS:
        new, n = re.subn(pattern, replacement, KEEP, count=1, flags=re.M)
        if n != 1:
            print(f"  {label:<52} NOT APPLIED (matched {n}x)")
            silent.append(label + " [not applied]")
            continue
        TARGET.write_text(new)
        failed, passed, errored = run()
        TARGET.write_text(KEEP)
        if errored:
            verdict = "BITES (collection error)"
        elif failed > 0:
            verdict = f"BITES ({failed} failed)"
        else:
            verdict = f"*** SILENT *** ({passed} passed)"
            if label == CANARY:
                canary_ok = True
            else:
                silent.append(label)
        print(f"  {label:<52} {verdict}")

    failed, passed, errored = run()
    if errored or failed:
        print(f"\n  RESTORE FAILED: {failed} failed, {errored} errored -- file not intact")
        return 1
    print(f"\n  restored: {passed} passed, 0 failed")

    if silent:
        print(f"  {len(silent)} mutation(s) did not bite:")
        for s in silent:
            print(f"    - {s}")
        return 1
    if not canary_ok:
        print("  the canary BORE -- the harness is misreporting; distrust the table")
        return 1
    print("  every mutation bit, and the canary stayed silent as it should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
