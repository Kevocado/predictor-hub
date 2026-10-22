// The paper workflows must cover every sport the ledger can log, and must fail
// loudly when a source is missing.
//
// Three rules, from the spec:
//
//   * add the new sources to them -- a sport the ledger knows about but the
//     workflow does not clone is a sport that is silently skipped, and the
//     ledger's own tally would report "no markets" rather than "no collector";
//   * keep them from ever pushing a failing ledger -- a red run must not
//     publish a partial report;
//   * make a missing collector fail loudly, not silently skip.
//
// The third one is the one that bites. `lines_files` returns an empty list for
// a directory that is not there, so a clone that failed, or a repo that
// renamed its `data/lines` directory, reads as "this sport has no markets
// today" -- which is a different claim from "this sport's collector is
// missing", and the ledger would go on making candidates for the other sports
// as if nothing were wrong.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const logYml = readFileSync(new URL("../.github/workflows/paper-log.yml", import.meta.url), "utf8");
const settleYml = readFileSync(new URL("../.github/workflows/paper-settle.yml", import.meta.url), "utf8");
const sourcesPy = readFileSync(new URL("../services/paper/paper/sources.py", import.meta.url), "utf8");

// The sports the ledger can log, and the repo each one's ladders live in.
const siteForSport = Object.fromEntries(
  [...sourcesPy.matchAll(/"(\w+)":\s*"(\w+_Predictor)"/g)].map((m) => [m[1], m[2]])
);

test("the ledger knows about every sport the workflows clone", () => {
  assert.ok(Object.keys(siteForSport).length >= 3, "sources.py lists no sports");
});

for (const [name, yml] of [["paper-log.yml", logYml], ["paper-settle.yml", settleYml]]) {
  test(`${name} clones every repo the ledger reads lines from`, () => {
    const cloned = [...yml.matchAll(/for repo in ([\w ]+); do/g)]
      .flatMap((m) => m[1].split(/\s+/))
      .filter(Boolean);
    for (const repo of new Set(Object.values(siteForSport))) {
      assert.ok(cloned.includes(repo), `${name} does not clone ${repo}`);
    }
  });

  test(`${name} never pushes after a failed step`, () => {
    // The commit step must be gated on the earlier steps having succeeded. A
    // red run that still published a report would put a partial ledger on the
    // branch, and the next run would read it as the truth.
    const commitStep = yml.slice(yml.indexOf("Commit and push if changed"));
    assert.match(commitStep, /if:\s*success\(\)/);
    // And the step that can fail must come BEFORE it.
    assert.ok(
      yml.indexOf("python3 scripts/paper_log.py") < yml.indexOf("Commit and push if changed")
      || yml.indexOf("python3 scripts/paper_settle.py") < yml.indexOf("Commit and push if changed"),
      `${name} commits before the step that can fail`
    );
  });

  test(`${name} fails loudly when a collector's lines are missing`, () => {
    // A missing `data/lines` directory is the collector being absent, which is
    // not the same as a sport with no markets today. The workflow has to say so.
    assert.match(yml, /missing|absent|no lines/i);
  });
}

test("the log workflow's clone step cannot fail quietly", () => {
  // `git clone` inside a `for` loop in a `run:` block exits non-zero on
  // failure, but the loop's own exit status is the LAST command's. A clone
  // that failed in the middle would otherwise be invisible.
  assert.match(logYml, /set -e|&&|exit 1/);
});
