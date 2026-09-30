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
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
