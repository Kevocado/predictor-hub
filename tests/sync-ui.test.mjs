import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { after } from "node:test";

const script = fileURLToPath(new URL("../scripts/sync-ui.mjs", import.meta.url));
const made = [];
const tempSite = () => { const d = mkdtempSync(join(tmpdir(), "site-")); made.push(d); return d; };
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));
const run = (...args) => spawnSync(process.execPath, [script, ...args], { encoding: "utf8" });

test("vendors the package source (no tests) with a do-not-edit header and a checksum manifest", () => {
  const site = tempSite();
  const r = run(site);
  assert.equal(r.status, 0, r.stderr);
  const out = join(site, "predictor-ui");
  assert.ok(existsSync(join(out, "fmt.ts")));
  assert.ok(existsSync(join(out, "tokens.css")));
  assert.ok(existsSync(join(out, "components", "MatchCard.tsx")));
  assert.ok(!existsSync(join(out, "fmt.test.ts")), "tests are not vendored");
  assert.match(readFileSync(join(out, "fmt.ts"), "utf8"), /^\/\/ Synced from predictor-ui@/);
  assert.match(readFileSync(join(out, "tokens.css"), "utf8"), /^\/\* Synced from predictor-ui@/);
  const manifest = JSON.parse(readFileSync(join(out, "SYNC.json"), "utf8"));
  assert.ok(manifest.files["fmt.ts"].match(/^[0-9a-f]{64}$/));
});

test("is idempotent and --check passes on an untouched copy", () => {
  const site = tempSite();
  run(site);
  const first = readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8");
  run(site);
  assert.equal(readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8"), first);
  assert.equal(run("--check", site).status, 0);
});

test("--check fails when a vendored file was edited by hand", () => {
  const site = tempSite();
  run(site);
  const f = join(site, "predictor-ui", "fmt.ts");
  writeFileSync(f, readFileSync(f, "utf8") + "\n// local tweak\n");
  const r = run("--check", site);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /fmt\.ts/);
});

test("stamps a hash of the package contents, so a new hub commit alone changes nothing", () => {
  const site = tempSite();
  run(site);
  const manifest = JSON.parse(readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8"));
  assert.match(manifest.source, /^predictor-ui@[0-9a-f]{12}$/);
  assert.match(readFileSync(join(site, "predictor-ui", "fmt.ts"), "utf8"), /^\/\/ Synced from predictor-ui@[0-9a-f]{12}\./);
});

test("--check fails on files added to the vendored folder by hand", () => {
  const site = tempSite();
  run(site);
  writeFileSync(join(site, "predictor-ui", "local.ts"), "export const x = 1;\n");
  const r = run("--check", site);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /local\.ts/);
});

test("writes LF line endings whatever the checkout uses", () => {
  const site = tempSite();
  run(site);
  assert.ok(!readFileSync(join(site, "predictor-ui", "fmt.ts"), "utf8").includes("\r"));
});
