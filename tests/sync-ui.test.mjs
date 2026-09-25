import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const script = new URL("../scripts/sync-ui.mjs", import.meta.url).pathname;
const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: "utf8" });

test("vendors the package source (no tests) with a do-not-edit header and a checksum manifest", () => {
  const site = mkdtempSync(join(tmpdir(), "site-"));
  const r = run(site);
  assert.equal(r.status, 0, r.stderr);
  const out = join(site, "predictor-ui");
  assert.ok(existsSync(join(out, "fmt.ts")));
  assert.ok(existsSync(join(out, "tokens.css")));
  assert.ok(existsSync(join(out, "components", "MatchCard.tsx")));
  assert.ok(!existsSync(join(out, "fmt.test.ts")), "tests are not vendored");
  assert.match(readFileSync(join(out, "fmt.ts"), "utf8"), /^\/\/ Synced from predictor-hub/);
  assert.match(readFileSync(join(out, "tokens.css"), "utf8"), /^\/\* Synced from predictor-hub/);
  const manifest = JSON.parse(readFileSync(join(out, "SYNC.json"), "utf8"));
  assert.ok(manifest.files["fmt.ts"].match(/^[0-9a-f]{64}$/));
});

test("is idempotent and --check passes on an untouched copy", () => {
  const site = mkdtempSync(join(tmpdir(), "site-"));
  run(site);
  const first = readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8");
  run(site);
  assert.equal(readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8"), first);
  assert.equal(run("--check", site).status, 0);
});

test("--check fails when a vendored file was edited by hand", () => {
  const site = mkdtempSync(join(tmpdir(), "site-"));
  run(site);
  const f = join(site, "predictor-ui", "fmt.ts");
  writeFileSync(f, readFileSync(f, "utf8") + "\n// local tweak\n");
  const r = run("--check", site);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /fmt\.ts/);
});
