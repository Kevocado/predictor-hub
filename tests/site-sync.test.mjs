// The staleness guard: is each site's vendored copy the current one?
//
// These tests are the reason the guard can be believed. A check that cannot
// run, or that compares against the wrong number, is worse than no check —
// both are green, and one of them is green *because* it did nothing. So the
// cases below are the three that matter, and each one asserts the failure as
// loudly as the pass:
//
//   * a comparison against a committed constant rather than the computed
//     version  →  the whole suite goes red the moment the package changes;
//   * an unreadable site manifest                     →  a hard failure, and
//     never a pass, in the warning mode as well as the enforcing one;
//   * no credential                                  →  a loud, stated skip
//     that claims nothing.
//
// Nothing here touches the network: `fetch` is a function argument, and the one
// place the real thing is used is against a local file system.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { after } from "node:test";

import { DEFAULT_REF, SITES, STALE, UNREADABLE, checkSite, main, manifestSource } from "../scripts/check-site-sync.mjs";
import { SRC, currentSource, shippedFiles, sourceFor } from "../scripts/ui-package.mjs";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
const made = [];
const temp = () => { const d = mkdtempSync(join(tmpdir(), "site-sync-")); made.push(d); return d; };
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));

const VERBOSE = process.argv.includes("--verbose") || process.env.TEST_VERBOSE === "1";
const log = (...a) => VERBOSE && console.error(...a);

// A `fetch` that answers from a map of `repo/ref/path` → a response spec, and
// 404s anything it was not told about — the same shape as the real API's
// "Not Found", which is what a wrong path in SITES actually produces.
const stubFetch = (files) => async (url) => {
  const u = new URL(url);
  // `repo/path`, the way a hand-written table reads best.
  const [, , owner, name, kind, ...rest] = u.pathname.split("/");
  const key = `${owner}/${name}/${rest.join("/")}@${u.searchParams.get("ref")}`;
  assert.equal(kind, "contents", `unexpected API path: ${u.pathname}`);
  const spec = files[key];
  if (!spec) return jsonResponse(404, { message: "Not Found" });
  if (spec.raw !== undefined) return { ok: true, status: 200, json: async () => spec.raw };
  return jsonResponse(200, { type: "file", encoding: "base64", content: Buffer.from(spec.text).toString("base64") });
};
const jsonResponse = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

const oneSite = [{ repo: "acme/One", manifest: "src/predictor-ui/SYNC.json" }];
const MANIFEST = (source) => JSON.stringify({ source, files: {} }) + "\n";

// ---------------------------------------------------------------- the number

test("the version the guard compares against is the one the sync tool writes", async () => {
  // The load-bearing identity, and the one that makes "compare against a
  // committed constant" impossible to get away with. Derived the long way here:
  // run the real tool into a scratch directory and read the manifest it wrote.
  //
  // What this does and does not catch, precisely, because the difference is the
  // whole argument for computing the number: a hand-typed constant that is
  // *currently right* is indistinguishable from the computation, and no
  // hermetic test can tell them apart — the package has not changed yet, so
  // nothing is wrong. A constant that has gone stale fails here the moment it
  // is wrong, which is the first moment it can be caught, and the mutation
  // notes in the report show both halves. What the assertion buys is that the
  // value is pinned to the derivation rather than free, in the guard *and* in
  // main()'s default, so it cannot be quietly repointed.
  const site = temp();
  execFileSync(process.execPath, [join(HUB, "scripts", "sync-ui.mjs"), site], { encoding: "utf8" });
  const written = manifestSource(readFileSync(join(site, "predictor-ui", "SYNC.json"), "utf8"));
  assert.equal(currentSource(), written, "the guard and the tool disagree about the current version");

  const { rows } = await main({
    env: { GITHUB_TOKEN: "t" }, out: () => {},
    sites: oneSite, fetchImpl: stubFetch({ [`acme/One/${oneSite[0].manifest}@main`]: { text: MANIFEST(written) } }),
  });
  assert.equal(rows[0].want, written, "main()'s default is not the computed version");
  assert.equal(rows[0].status, "current");
});

test("the version is a hash of the package's contents, not a value that can be typed in", () => {
  // A guard that compared against a committed constant would still pass this
  // only if the constant happened to be a content hash, which is the point of
  // building the case: two packages, one file apart, two versions — and the
  // same package hashed twice is the same answer, so the number is a function.
  const pkg = (name, body) => {
    const d = temp();
    mkdirSync(join(d, "components"), { recursive: true });
    writeFileSync(join(d, "tokens.css"), body);
    writeFileSync(join(d, "components", "MatchCard.tsx"), name);
    return d;
  };
  const a1 = pkg("A", ":root { --x: 1; }\n");
  const a2 = pkg("A", ":root { --x: 1; }\n");
  const b = pkg("B", ":root { --x: 1; }\n");
  assert.equal(sourceFor(shippedFiles(a1), a1), sourceFor(shippedFiles(a2), a2), "not a function of the contents");
  assert.notEqual(sourceFor(shippedFiles(a1), a1), sourceFor(shippedFiles(b), b), "a changed file did not move it");
  // A test file is not shipped, so it must not move the number either.
  writeFileSync(join(a1, "fmt.test.ts"), "export const x = 1;\n");
  assert.equal(sourceFor(shippedFiles(a1), a1), sourceFor(shippedFiles(a2), a2), "an unshipped file moved it");
});

test("the shipped set is the real one, and the guard hashes the same files the tool vendors", () => {
  assert.ok(shippedFiles().length >= 10, `only ${shippedFiles().length} shipped files`);
  assert.ok(shippedFiles().every((f) => f.startsWith(SRC)), "a file outside packages/predictor-ui/src");
  assert.match(currentSource(), /^predictor-ui@[0-9a-f]{12}$/);
});

// ------------------------------------------------------------------ outcomes

test("a site at the hub's version is current and a site behind it is stale", async () => {
  const want = currentSource();
  const fetchImpl = stubFetch({
    "acme/One/src/predictor-ui/SYNC.json@main": { text: MANIFEST(want) },
  });
  const fresh = await checkSite(oneSite[0], { token: "t", fetchImpl, want });
  assert.equal(fresh.status, "current");
  assert.equal(fresh.have, want);

  const behind = await checkSite(oneSite[0], {
    token: "t", fetchImpl: stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: MANIFEST("predictor-ui@000000000000") } }), want,
  });
  assert.equal(behind.status, STALE);
  assert.equal(behind.have, "predictor-ui@000000000000");
});

test("an unreadable manifest is never a pass, in either mode", async () => {
  // The mutation the brief asks for: if an unreadable manifest is treated as
  // "nothing to report", a site that was renamed, moved, made private, or
  // stopped vendoring passes silently — and "we could not look" is reported as
  // "we looked and it was fine".
  const want = currentSource();
  const unreadable = [
    ["404 — path or repo wrong", stubFetch({})],
    ["200 but not a file", stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { raw: { type: "dir" } } })],
    ["manifest is not JSON", stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: "404: Not Found" } })],
    ["manifest has no source", stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: JSON.stringify({ files: {} }) } })],
    ["source is not a version", stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: JSON.stringify({ source: "main" }) } })],
  ];
  for (const [why, fetchImpl] of unreadable) {
    const row = await checkSite(oneSite[0], { token: "t", fetchImpl, want });
    assert.equal(row.status, UNREADABLE, `${why} was not unreadable`);
    assert.ok(row.detail, `${why} carries no reason`);

    for (const enforce of [false, true]) {
      const lines = [];
      const { code, rows } = await main({
        env: { GITHUB_TOKEN: "t", ENFORCE_SITE_SYNC: enforce ? "1" : "0" },
        out: (l) => lines.push(l), fetchImpl, sites: oneSite, want,
      });
      const out = lines.join("\n");
      assert.equal(code, 1, `${why} passed the run (enforce=${enforce})`);
      assert.equal(rows[0].status, UNREADABLE);
      assert.match(out, /::error /, `${why} produced no error annotation`);
      assert.doesNotMatch(out, /PASS/, `${why} printed a pass`);
    }
  }
});

test("one unreadable site fails a run whose other sites are all current", async () => {
  // The shape that hides: 3 green, 1 that could not be read, run summarised by
  // the green ones.
  const want = currentSource();
  const sites = [{ repo: "acme/A", manifest: "a/SYNC.json" }, { repo: "acme/Gone", manifest: "gone/SYNC.json" }];
  const lines = [];
  const { code, rows } = await main({
    env: { GITHUB_TOKEN: "t" },
    out: (l) => lines.push(l), sites, want,
    fetchImpl: stubFetch({ "acme/A/a/SYNC.json@main": { text: MANIFEST(want) } }),
  });
  assert.equal(code, 1);
  assert.deepEqual(rows.map((r) => r.status), ["current", UNREADABLE]);
  const out = lines.join("\n");
  assert.match(out, /FAIL — 1 of 2 sites could not be read/);
  assert.doesNotMatch(out, /site-sync: PASS/);
});

test("a stale site warns while the migration is in flight, and fails once enforced", async () => {
  const want = currentSource();
  const fetchImpl = stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: MANIFEST("predictor-ui@000000000000") } });
  const run = async (enforce) => {
    const lines = [];
    const { code } = await main({
      env: { GITHUB_TOKEN: "t", ENFORCE_SITE_SYNC: enforce ? "1" : "0" },
      out: (l) => lines.push(l), fetchImpl, sites: oneSite, want,
    });
    return { code, out: lines.join("\n") };
  };
  const warn = await run(false);
  assert.equal(warn.code, 0, "a stale site must not fail the build before the sites are synced");
  assert.match(warn.out, /::warning /, "a stale site produced no warning annotation");
  assert.match(warn.out, /BEHIND — 1 of 1/);
  assert.match(warn.out, /not a pass/, "the migration state must not read as a pass");
  assert.match(warn.out, /ENFORCE_SITE_SYNC: "1"/, "the warning must say how to turn this into a failure");
  assert.match(warn.out, /node scripts\/sync-ui\.mjs/, "the warning must say what to run, not only that something is wrong");

  const enforced = await run(true);
  assert.equal(enforced.code, 1, "with ENFORCE_SITE_SYNC=1 a stale site must fail the build");
  assert.match(enforced.out, /FAIL — 1 of 1/);
});

test("a run where every site is current passes, and says which version it proved", async () => {
  const want = currentSource();
  const lines = [];
  const { code } = await main({
    env: { GITHUB_TOKEN: "t" },
    out: (l) => lines.push(l), sites: oneSite, want,
    fetchImpl: stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: MANIFEST(want) } }),
  });
  const out = lines.join("\n");
  log(out);
  assert.equal(code, 0);
  assert.match(out, new RegExp(`PASS — 1 of 1 sites are at ${want.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`));
  assert.doesNotMatch(out, /::warning/, "a clean run annotated a warning");
});

test("no credential is a loud skip that claims nothing, and does not read a repo", async () => {
  let asked = 0;
  const fetchImpl = async () => { asked += 1; throw new Error("must not be called"); };
  const lines = [];
  const { code, rows, skipped } = await main({
    env: {}, out: (l) => lines.push(l), sites: oneSite, want: currentSource(), fetchImpl,
  });
  const out = lines.join("\n");
  log(out);
  assert.equal(code, 0, "a skip must not fail a build that has no credential to offer");
  assert.equal(asked, 0, "it asked GitHub anyway");
  assert.equal(rows.length, 0);
  assert.match(skipped, /SITE_REPOS_TOKEN/);
  assert.match(out, /::warning /, "a skip with no annotation is a silent pass");
  assert.match(out, /SKIPPED — 0 of 1 sites compared/);
  assert.match(out, /not a pass|this is a skip, not a pass/i);
  assert.doesNotMatch(out, /site-sync: PASS/);
  // The message has to be actionable, or the next person repeats it.
  assert.match(out, /gh auth token/);
});

test("an ENFORCED run with no credential FAILS, because it proved nothing", async () => {
  // The hole that only opens once enforcement is on. While ENFORCE_SITE_SYNC was
  // "0", exiting 0 on a skip was RIGHT: a developer with no token should not be
  // blocked by a check they cannot run, and the skip is loud in both modes.
  //
  // Under enforcement the meaning inverts. The build now asserts that the sites
  // are current, and a skip that returns 0 asserts it without looking at a single
  // site. That is the one failure mode this check exists to prevent, and it is
  // reachable the moment the credential stops working -- a token scope change, a
  // site going private, a policy change -- which is precisely when nobody is
  // watching. So an enforced skip fails, and says it failed for want of a
  // credential rather than for want of a current site.
  let asked = 0;
  const fetchImpl = async () => { asked += 1; throw new Error("must not be called"); };
  const lines = [];
  const { code, rows } = await main({
    env: { ENFORCE_SITE_SYNC: "1" }, out: (l) => lines.push(l), sites: oneSite, want: currentSource(), fetchImpl,
  });
  const out = lines.join("\n");
  log(out);
  assert.equal(code, 1, "an enforced run that compared 0 sites must not report success");
  assert.equal(asked, 0, "it asked GitHub anyway");
  assert.equal(rows.length, 0);
  assert.match(out, /::error /, "failing without an annotation is a failure nobody is told about");
  assert.doesNotMatch(out, /site-sync: PASS/, "a skip that also claims a pass is the worst version");
  // It must not tell the reader to switch enforcement off to make this go away:
  // that restores a check that cannot fail, which is the bug being fixed here.
  assert.doesNotMatch(out, /set ENFORCE_SITE_SYNC: "0"/);
});

test("SITE_REPOS_TOKEN is preferred, because the automatic token is scoped to this repo", async () => {
  // The escape hatch is only an escape hatch if it is actually used, and the
  // order is the whole point: an installation token may not be honoured for a
  // different repository, and the documented fix has to win when it is present.
  const want = currentSource();
  for (const env of [
    { SITE_REPOS_TOKEN: "srt", GITHUB_TOKEN: "ght" },
    { GITHUB_TOKEN: "ght" },
    { GH_TOKEN: "ght" },
  ]) {
    const used = [];
    const { rows, code } = await main({
      env, out: () => {}, sites: oneSite, want,
      fetchImpl: async (_url, init) => {
        used.push(init.headers.authorization);
        return jsonResponse(200, { type: "file", encoding: "base64", content: Buffer.from(MANIFEST(want)).toString("base64") });
      },
    });
    assert.equal(code, 0, JSON.stringify(env));
    assert.equal(rows[0].status, "current");
    const expected = env.SITE_REPOS_TOKEN || env.GITHUB_TOKEN || env.GH_TOKEN;
    assert.deepEqual(used, [`Bearer ${expected}`], JSON.stringify(env));
  }
});

// ------------------------------------------------------------------ the list

test("every registered site is a real path to a manifest, and the list is not empty", () => {
  // A missing entry fails silently, which is the whole failure mode here, so
  // the entry is at least held to shape. The path was measured with
  // `git ls-tree -r --name-only origin/main | grep predictor-ui/SYNC.json` in
  // each repo; this cannot re-measure it without the network, and pretending
  // otherwise would be the mistake this file is arguing against.
  assert.ok(SITES.length >= 4, "the site list shrank; a removed entry stops checking that site");
  for (const { repo, manifest, ref } of SITES) {
    assert.match(repo, /^Kevocado\/[A-Za-z0-9_]+$/, repo);
    assert.match(manifest, /(^|\/)predictor-ui\/SYNC\.json$/, `${repo}: ${manifest}`);
    assert.equal(ref, undefined, `${repo} pins a ref; every site is read at ${DEFAULT_REF} on purpose`);
  }
  // NFL and CFB are API repos with no vendored frontend. Named so that their
  // absence reads as a decision rather than an oversight.
  const repos = SITES.map((s) => s.repo);
  assert.ok(!repos.includes("Kevocado/NFL_Predictor") && !repos.includes("Kevocado/CFB_Predictor"));
  assert.deepEqual(repos, [...new Set(repos)], "a repo is registered twice");
});

// ------------------------------------------- a PR that bumps the package itself

// The deadlock, in one sentence. `sync-ui.mjs` copies `packages/predictor-ui`
// as it stands on the hub's main, and each site vendors that copy, so a PR that
// changes the package cannot have its sites re-vendor *before* it merges. Enforce
// drift on that PR and the check can only go green after the four site PRs that
// are queued behind it — which is #52: its one job was red with
//
//     site-sync: FAIL — 4 of 4 sites are behind the hub.
//
// for exactly this reason, and the thing it could not do was merge to unblock
// the site PRs.
//
// The fix is a third state, not a weaker check: on a PR that changes the
// package, report the sites as PENDING and exit 0; enforce everywhere else; and
// keep enforcing on main, where "behind" is real drift that clears when the
// site PRs land. The tests below pin all three, and the workflow tests run the
// workflow's own `run:` block rather than asserting a regex still matches it.

const STALE_SOURCE = "predictor-ui@000000000000";
const behindSite = (source = STALE_SOURCE) =>
  stubFetch({ "acme/One/src/predictor-ui/SYNC.json@main": { text: MANIFEST(source) } });
const unreadableSite = () => stubFetch({});

/** Drive `main()` with an env and one site, and hand back what it said. */
async function drive(env, fetchImpl = behindSite()) {
  const lines = [];
  const { code, rows } = await main({
    env: { GITHUB_TOKEN: "t", ...env },
    out: (l) => lines.push(l), fetchImpl, sites: oneSite, want: currentSource(),
  });
  return { code, rows, out: lines.join("\n") };
}

test("a PR that bumps the package reports the sites as PENDING, and passes", async () => {
  const { code, rows, out } = await drive({ ENFORCE_SITE_SYNC: "0", SITE_SYNC_EXPECT_RESYNC: "1" });
  log(out);
  assert.equal(code, 0, "the sites cannot re-vendor a package that is not on main yet, so failing here deadlocks the PR");
  assert.equal(rows[0].status, STALE, "the drift must still be measured — PENDING is a verdict, not a skip");
  // PENDING, and the count. "Something is behind" without a number is the
  // sentence this whole section exists to replace.
  assert.match(out, /site-sync: PENDING — 1 of 1 sites/, out);
  assert.match(out, /re-sync that follows this merge/, "PENDING must say what it is waiting for");
  // The table is the same table, because it is the same comparison.
  assert.match(out, /acme\/One\s+main\s+predictor-ui@000000000000\s+stale/);
  assert.match(out, /::warning /, "a pending site still gets an annotation");
  assert.doesNotMatch(out, /FAIL/, out);
  assert.doesNotMatch(out, /::error/, out);
  // And it must not print the migration advice, which is a different state and
  // a misleading one here: enforcement is not "off, flip it on", it is on for
  // main and off for this PR only.
  assert.doesNotMatch(out, /adoption is a migration/, out);
  assert.doesNotMatch(out, /ENFORCE_SITE_SYNC: "1"/, out);
});

test("PENDING does not excuse a site that could not be read", async () => {
  // The relaxation is about *staleness*, which has a known cause and a known
  // fix. A manifest that could not be read has neither: it is the hole this
  // check was written to stop, and it must stay a failure in every mode.
  const { code, out } = await drive(
    { ENFORCE_SITE_SYNC: "0", SITE_SYNC_EXPECT_RESYNC: "1" }, unreadableSite(),
  );
  assert.equal(code, 1, "a PR that bumps the package must not make an unreadable site pass");
  assert.match(out, /::error /, out);
  assert.match(out, /FAIL — 1 of 1 sites could not be read/, out);
  assert.doesNotMatch(out, /site-sync: PENDING/, out);
});

test("enforcement wins when a pending PR and ENFORCE_SITE_SYNC are both set", async () => {
  // Fails *closed* on a contradictory configuration. If the workflow ever sets
  // both — by a mistake, or by a change to one branch of its own logic — the
  // safe reading is the enforced one, so that misconfiguration is a louder
  // failure rather than a silent pass.
  const { code, out } = await drive({ ENFORCE_SITE_SYNC: "1", SITE_SYNC_EXPECT_RESYNC: "1" });
  assert.equal(code, 1, "enforcement must not be switchable off by a second variable");
  assert.match(out, /FAIL — 1 of 1 sites are behind the hub/, out);
  assert.doesNotMatch(out, /PENDING/, out);
});

test("a stale site is still PENDING-shaped without the flag, and still fails when enforced", async () => {
  // The third case from the top, in the script: a run that is not told the
  // package is changing is an ordinary enforced run. Without the flag the
  // existing warning path is byte-for-byte the migration message it always was.
  const migration = await drive({ ENFORCE_SITE_SYNC: "0" });
  assert.equal(migration.code, 0);
  assert.match(migration.out, /BEHIND — 1 of 1/, "the pre-existing warning mode must not change");
  assert.match(migration.out, /ENFORCE_SITE_SYNC: "1"/);
  assert.doesNotMatch(migration.out, /PENDING/, "the flag is what says pending; nothing else may");

  const enforced = await drive({ ENFORCE_SITE_SYNC: "1" });
  assert.equal(enforced.code, 1);
  assert.match(enforced.out, /FAIL — 1 of 1 sites are behind the hub/);
});

// -------------------------------------------------------- the workflow's decision

// The three cases are only worth anything if the workflow computes them. A test
// that calls `main()` directly proves the script honours a mode; it does not
// prove anything ever puts the workflow in that mode, and a workflow file has no
// test of its own — a typo in one is invisible until a run is red. Same argument
// `services/explainer/tests/test_ci_workflow.py` makes for the explainer
// workflow, and the same remedy: read the file, then run the step.

const WORKFLOW = join(HUB, ".github", "workflows", "site-sync-check.yml");

/** The workflow's `run:` blocks, paired with the step each belongs to.
 *
 * By hand rather than with a YAML parser, because the hub has no dependencies
 * and adding one to read a 90-line file would be a worse trade than eight lines
 * of line-splitting. Tolerates anything it is not looking at: it collects block
 * scalars under `- ` items and ignores every other key.
 */
function workflowSteps(text) {
  const steps = [];
  let name = null;
  let body = null;
  let base = null;
  const endRun = () => {
    if (body !== null) steps.push({ name: name ?? "(unnamed)", run: body.join("\n") });
    body = null; base = null;
  };
  for (const line of text.split("\n")) {
    // A `- ` starts a new step, so any half-read run block belongs to the old
    // one and the name is reset. `run:` itself is not a `- ` item — it sits
    // beside `name:` — so it only closes the body, leaving the name standing.
    if (/^\s*-\s/.test(line)) { endRun(); name = null; }
    const key = line.match(/^\s*(?:-\s+)?(name|run):\s*(.*)$/);
    if (key) {
      if (key[1] === "name") name = key[2].trim();
      else if (key[2].includes("|")) { endRun(); body = []; }
      else { endRun(); body = [key[2]]; }
      continue;
    }
    if (body === null) continue;
    if (base === null) {
      // The block's own indentation, from its first non-blank line: assuming two
      // past the key would break silently on the first re-indent.
      if (!line.trim()) { body.push(""); continue; }
      base = line.match(/^ */)[0].length;
    }
    if (line.match(/^ */)[0].length >= base) body.push(line.slice(base));
    else endRun();
  }
  endRun();
  return steps;
}

/** Run one `run:` block the way Actions runs it — `bash -e` — with a stub `git`
 *  first on PATH, and return the `KEY=value` lines it appended to GITHUB_ENV.
 *
 *  `changed` is the PR's whole file list, and the stub honours the pathspec the
 *  step actually asked for: a diff of `docs/…` against `-- packages/predictor-ui/`
 *  is empty, exactly as git would answer it. A stub that ignored the pathspec
 *  would pass a step that checks the wrong thing, which is the mistake this
 *  section exists to prevent. */
function runWorkflowStep(step, { env = {}, changed = [], code = 0 } = {}) {
  const dir = temp();
  const bin = join(dir, "bin");
  mkdirSync(bin, { recursive: true });
  // Records argv, then answers as `git diff --name-only … -- <pathspec>` would.
  // The pathspec is taken off the end of argv with sed rather than `${*##-- }`,
  // which is not portable to /bin/sh and silently yields the whole string.
  writeFileSync(join(bin, "git"), [
    "#!/bin/sh",
    'printf "%s\\n" "$*" > "$STUB_GIT_ARGV"',
    'pathspec=$(printf "%s" "$*" | sed "s/^.*-- //")',
    'printf "%s\\n" "$STUB_CHANGED" | grep "^$pathspec" || true',
    `exit ${code}`,
    "",
  ].join("\n"));
  chmodSync(join(bin, "git"), 0o755);

  const script = join(dir, "step.sh");
  writeFileSync(script, step.run);
  const envFile = join(dir, "github_env");
  const argvFile = join(dir, "git_argv");
  writeFileSync(envFile, "");
  let stdout = "";
  try {
    stdout = execFileSync("bash", ["-e", script], {
      encoding: "utf8",
      env: {
        PATH: `${bin}:${process.env.PATH}`,
        GITHUB_ENV: envFile, STUB_GIT_ARGV: argvFile, STUB_CHANGED: changed.join("\n"), ...env,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (err) {
    throw new Error(`the step exited non-zero under bash -e:\n${err.stderr ?? ""}\n${stdout}`);
  }
  return {
    stdout,
    argv: existsSync(argvFile) ? readFileSync(argvFile, "utf8").trim() : null,
    env: Object.fromEntries(readFileSync(envFile, "utf8").split("\n").filter(Boolean).map((l) => l.split("="))),
  };
}

const workflow = readFileSync(WORKFLOW, "utf8");
/** The step that decides, found by what it does rather than where it sits. */
const decideStep = () => {
  const steps = workflowSteps(workflow);
  const step = steps.find((s) => /enforce/i.test(s.name) && /GITHUB_ENV/.test(s.run));
  assert.ok(step, `no step in ${WORKFLOW} computes the enforcement decision; the three cases cannot be told apart without it`);
  return step;
};

const pkgChange = ["packages/predictor-ui/src/components/InstantBlock.tsx"];

test("a PR that changes packages/predictor-ui is pending; a PR that does not, and main, enforce", async () => {
  // The three cases, from the workflow's own logic rather than from this
  // file's reading of it.
  const bumped = runWorkflowStep(decideStep(), {
    env: { EVENT_NAME: "pull_request", BASE_REF: "main" }, changed: pkgChange,
  });
  assert.equal(bumped.env.enforce, "0", "a package-bumping PR must not be blocked by sites that cannot sync yet");
  assert.equal(bumped.env.expect_resync, "1", "and it must be told the drift is expected, so it can say PENDING");

  const other = runWorkflowStep(decideStep(), {
    env: { EVENT_NAME: "pull_request", BASE_REF: "main" },
    changed: ["docs/superpowers/plans/2026-09-30-phase1-instant-block.md"],
  });
  assert.equal(other.env.enforce, "1", "a PR that does not touch the package must enforce exactly as before");
  assert.equal(other.env.expect_resync, "0");

  const landed = runWorkflowStep(decideStep(), {
    env: { EVENT_NAME: "push", BASE_REF: "" }, changed: pkgChange,
  });
  assert.equal(landed.env.enforce, "1",
    "main must keep enforcing: right after the bump merges the sites ARE behind, and that red is the correct signal until the four site PRs land");
  assert.equal(landed.env.expect_resync, "0", "main is not waiting for a re-sync, it owes one");
});

test("the diff that decides is this PR's, filtered to the vendored package", () => {
  const run = decideStep().run;
  const bumped = runWorkflowStep(decideStep(), {
    env: { EVENT_NAME: "pull_request", BASE_REF: "main" }, changed: pkgChange,
  });
  assert.equal(bumped.argv, "diff --name-only origin/main...HEAD -- packages/predictor-ui/",
    "the step must diff this PR against its base, triple-dot, with a pathspec limited to the vendored package");
  // Every other trigger is one input, and the only condition on the base ref is
  // that it is a pull request. Anything that widens this widens the hole.
  assert.match(run, /EVENT_NAME/, run);
  assert.match(run, /BASE_REF/, run);
});

test("the workflow passes the decision to the check, and the check step has no hard-coded verdict", () => {
  // The step's own environment is the contract. A hard-coded `ENFORCE_SITE_SYNC:
  // "1"` in the check step would pass every test above while deadlocking #52
  // again, because the decision would never arrive.
  const check = workflowSteps(workflow).find((s) => /check-site-sync\.mjs/.test(s.run));
  assert.ok(check, "the workflow no longer runs the check");
  assert.match(check.run, /node scripts\/check-site-sync\.mjs/, check.run);
  assert.match(workflow, /ENFORCE_SITE_SYNC:\s*\$\{\{\s*steps\.[\w-]+\.outputs\.enforce\s*\}\}/,
    "ENFORCE_SITE_SYNC is not the step's decision; the script decides its own mode again");
  assert.match(workflow, /SITE_SYNC_EXPECT_RESYNC:\s*\$\{\{\s*steps\.[\w-]+\.outputs\.expect_resync\s*\}\}/,
    "the pending mode is never wired up, so a bumping PR would print the migration message instead of PENDING");
  assert.doesNotMatch(check.run, /ENFORCE_SITE_SYNC:\s*"[01]"/, "the check step hard-codes the verdict");
});

test("the check still reads every site on a pending PR, and the comparison is not bypassed", () => {
  // The relaxation is a verdict, not a filter. The `git diff` pathspec is
  // deliberately `packages/predictor-ui/` and not `packages/`, because a
  // widening of it to the whole package dir would swallow README edits and
  // release the sites' guard on a commit that cannot have moved them.
  const step = decideStep();
  assert.doesNotMatch(step.run, /-- packages\/predictor-ui\s/, "the pathspec lost its trailing slash");
  assert.doesNotMatch(workflow, /continue-on-error/, "a step was marked non-blocking instead of the verdict being computed");
  assert.doesNotMatch(workflow, /check-site-sync\.mjs\s*(?:\|\||&&|:)/,
    "the check is short-circuited rather than run and reported");
  // Fail-closed: if the diff cannot be computed, the run enforces. The step
  // therefore has to keep the command's failure inside a condition, not let it
  // abort the job into a "success" it never earned.
  assert.match(step.run, /if\s+changed="\$\(/, "the diff is not guarded, so a failure aborts before ENFORCE is written");
});

// A workflow can read `steps.<id>.outputs.<name>` only if that step wrote
// `<name>=...` to $GITHUB_OUTPUT. Writing to $GITHUB_ENV instead creates an
// environment variable and leaves the output EMPTY -- which here meant
// ENFORCE_SITE_SYNC="" and a check that silently stopped enforcing anything.
test("every steps.<id>.outputs.<name> the site-sync workflow reads is written to GITHUB_OUTPUT by that step", () => {
  const yml = readFileSync(new URL("../.github/workflows/site-sync-check.yml", import.meta.url), "utf8");
  const refs = [...yml.matchAll(/steps\.([A-Za-z0-9_-]+)\.outputs\.([A-Za-z0-9_-]+)/g)].map((m) => [m[1], m[2]]);
  assert.ok(refs.length > 0, "the workflow is expected to read at least one step output");
  for (const [id, name] of refs) {
    const start = yml.indexOf(`id: ${id}`);
    assert.ok(start >= 0, `step id '${id}' is read but not defined`);
    const nextStep = yml.indexOf("\n      - ", start + 1);
    const body = yml.slice(start, nextStep === -1 ? undefined : nextStep);
    assert.match(
      body,
      new RegExp(`${name}=[^\\n]*>>\\s*"?\\$GITHUB_OUTPUT"?`),
      `step '${id}' must write ${name}= to $GITHUB_OUTPUT (found GITHUB_ENV instead: ${/GITHUB_ENV/.test(body)})`,
    );
  }
});
