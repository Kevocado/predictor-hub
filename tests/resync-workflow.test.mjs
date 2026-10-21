// The re-sync workflow must cover exactly the sites check-site-sync.mjs registers, with the source dir each one vendors into.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SITES } from "../scripts/check-site-sync.mjs";

const yml = readFileSync(new URL("../.github/workflows/resync-sites.yml", import.meta.url), "utf8");

test("the matrix lists every registered site with its vendored source directory", () => {
  const inMatrix = [...yml.matchAll(/\{ repo: (\w+), src: ([\w/]+) \}/g)].map((m) => `${m[1]}:${m[2]}`).sort();
  const registered = SITES.map((s) => `${s.repo.split("/")[1]}:${s.manifest.replace(/\/predictor-ui\/SYNC\.json$/, "")}`).sort();
  assert.deepEqual(inMatrix, registered);
});

test("it never merges and it fails loudly without the token", () => {
  assert.doesNotMatch(yml, /gh pr merge|--auto|enable-auto-merge/);
  assert.match(yml, /SITES_PAT is not set/);
});

test("it only runs for changes to the package", () => {
  assert.match(yml, /paths: \["packages\/predictor-ui\/\*\*"\]/);
});
