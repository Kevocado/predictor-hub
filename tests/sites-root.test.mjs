// Can a missing or stale site checkout explain itself?
//
// This file exists because of a measured failure, not a hypothetical one. A
// test that walks the sibling checkouts reported a missing checkout with a
// message that pointed at the wrong thing: `no local checkout for X at Y, so its
// components were not checked` reads as a broken repo, and the reviewer working
// from several checkouts had twice concluded "the code says X" from a tree that
// was simply stale. Two separate mistakes were wearing one costume:
//
//   1. WHICH checkout is missing, and where it expected to find it. The old
//      message named the site but walked off on the FIRST one it could not
//      read, so a root missing two checkouts reported one — and the one it
//      reported was not necessarily the one that mattered.
//   2. A checkout whose `HEAD` differs from `origin/main` said nothing at all,
//      even though that is the exact shape of "the code says X" from a stale
//      tree. The listing the test reads IS `origin/main`, so a reviewer reading
//      the working tree is reading something the test never looked at.
//
// Both are message problems, not behaviour problems. Absence stays fatal: a
// check that could not run must not look like one that ran. What changes is
// that the failure now carries the whole picture — every site it looked for,
// the path it looked at, whether that path is there, and where the checkout's
// HEAD sits against `origin/main`.
//
// Nothing here touches the network. The fixtures are real git repositories made
// with `git init` in a temp directory, and the SHAs are the ones git itself
// produced.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { after } from "node:test";

import {
  SITE_NAMES,
  discoverSitesRoot,
  inspectCheckout,
  inspectSites,
  missingCheckouts,
  sitesRootReport,
  staleCheckouts,
} from "../scripts/sites-root.mjs";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");

const made = [];
const temp = () => { const d = mkdtempSync(join(tmpdir(), "sites-root-")); made.push(d); return d; };
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));

const git = (cwd, args) => execFileSync("git", ["-C", cwd, ...args], {
  encoding: "utf8",
  env: {
    ...process.env,
    GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t",
  },
});

/** A real git repo with `count` commits, and an `origin/main` ref.
 *
 * `originMain` is how many commits back `origin/main` sits: `0` means the
 * checkout is exactly at `origin/main` (the healthy case), `1` means the local
 * `HEAD` has one commit the remote ref does not — a checkout that is stale, and
 * the shape the reviewer was burned by. `null` means no `origin/main` ref at
 * all, which is a third state and not the same as either of the others.
 */
const repo = (dir, { commits = 2, originMain = 0 } = {}) => {
  mkdirSync(dir, { recursive: true });
  git(dir, ["init", "-q", "-b", "main"]);
  for (let i = 0; i < commits; i++) {
    writeFileSync(join(dir, `f${i}.txt`), `${i}\n`);
    git(dir, ["add", "-A"]);
    git(dir, ["commit", "-q", "-m", `c${i}`]);
  }
  if (originMain !== null) {
    const ref = originMain === 0 ? "HEAD" : `HEAD~${originMain}`;
    git(dir, ["update-ref", "refs/remotes/origin/main", ref]);
  }
  return {
    head: git(dir, ["rev-parse", "--short=12", "HEAD"]).trim(),
    originMain: originMain === null ? null : git(dir, ["rev-parse", "--short=12", "origin/main"]).trim(),
  };
};

const noEnv = { env: {}, hub: HUB };

// ------------------------------------------------------------------ the shape

test("a checkout that is present and current is reported as present and current", () => {
  const root = temp();
  const want = repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });

  const got = inspectCheckout("PL_Predictor", root);

  assert.equal(got.name, "PL_Predictor");
  assert.equal(got.path, join(root, "PL_Predictor"), "the report must name the path it looked at");
  assert.equal(got.exists, true);
  assert.equal(got.isRepo, true);
  assert.equal(got.head, want.head);
  assert.equal(got.originMain, want.originMain);
  assert.equal(got.diverged, false, "HEAD is origin/main; this must not be reported as stale");
  assert.equal(got.problem, null);
});

test("a missing checkout names the site and the exact path it looked for", () => {
  // The first requirement, and the one the old message half-met: the site, and
  // where it expected to find it.
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });

  const got = inspectCheckout("NBA_Predictor", root);

  assert.equal(got.exists, false);
  assert.equal(got.isRepo, false);
  assert.equal(got.path, join(root, "NBA_Predictor"), "the path looked at must be in the result");
  assert.match(got.problem, /NBA_Predictor/, "the failure must say which site is missing");
  assert.match(got.problem, /does not exist/, "and say plainly that the path is not there");
});

test("a path that exists but is not a git checkout is reported as that, not as present", () => {
  // The nastier half of "exists": a directory with the right NAME that is not a
  // clone. `existsSync` says yes, a naive report says "present", and the next
  // git call fails somewhere further down with a message about the repo.
  const root = temp();
  mkdirSync(join(root, "PL_Predictor"), { recursive: true });

  const got = inspectCheckout("PL_Predictor", root);

  assert.equal(got.exists, true, "the directory is there");
  assert.equal(got.isRepo, false);
  assert.match(got.problem, /not a git checkout/, "a directory that is not a clone must say so");
});

// ------------------------------------------------- every site, not just the first

test("every missing checkout is named, not only the first one walked into", () => {
  // This is the half of the complaint the old message did not meet at all: the
  // old listing walked the sites and failed on the first absent one, so a root
  // missing two checkouts reported one of them, and the reviewer was left
  // discovering the second by hand.
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });
  repo(join(root, "Sports_Predictor"), { commits: 1, originMain: 0 });

  const { rows, missing } = inspectSites(root);
  const names = missing.map((r) => r.name);

  // NBA and F1 are absent but so are NFL and CFB — the report covers all six, so
  // it must name all four. Truncating to the first absent site is the failure.
  assert.deepEqual(names, ["NBA_Predictor", "F1_Predictor", "NFL_Predictor", "CFB_Predictor"]);
  assert.equal(missing.length, 4, "not just the first one walked into");
  for (const r of missing) {
    assert.match(r.problem, new RegExp(r.name));
    assert.equal(r.path, join(root, r.name), "each reported site carries the path it looked at");
  }
});

test("the report accounts for all six sibling checkouts, present or not", () => {
  // The reviewer works from six checkouts; the test reads four of them. A
  // report that only mentions the four cannot answer "which of mine is gone".
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });

  const { rows } = inspectSites(root);

  assert.deepEqual(
    rows.map((r) => r.name),
    SITE_NAMES,
    "the report must cover every sibling checkout, in order",
  );
  assert.equal(SITE_NAMES.length, 6);
  for (const n of ["PL_Predictor", "F1_Predictor", "NBA_Predictor", "Sports_Predictor", "NFL_Predictor", "CFB_Predictor"]) {
    assert.ok(SITE_NAMES.includes(n), `${n} must be in the report`);
  }
});

// -------------------------------------------------------------------- staleness

test("a checkout whose HEAD differs from origin/main is reported with both SHAs", () => {
  // The second requirement, and the one nothing in the repo did at all. The
  // listing the test reads is `origin/main`; a reviewer reading the working
  // tree is reading `HEAD`. When those differ, "the code says X" is a claim
  // about a tree the check never looked at — so both SHAs go in the report.
  const root = temp();
  const want = repo(join(root, "PL_Predictor"), { commits: 2, originMain: 1 });
  assert.notEqual(want.head, want.originMain, "the fixture must actually be stale");

  const got = inspectCheckout("PL_Predictor", root);

  assert.equal(got.diverged, true);
  assert.equal(got.head, want.head);
  assert.equal(got.originMain, want.originMain);
  assert.match(got.problem, new RegExp(want.head), "HEAD's SHA must be in the message");
  assert.match(got.problem, new RegExp(want.originMain), "origin/main's SHA must be in the message");
  assert.match(got.problem, /stale/i, "and it must be called what it is");
});

test("a checkout at origin/main is not flagged stale", () => {
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 3, originMain: 0 });

  const got = inspectCheckout("PL_Predictor", root);

  assert.equal(got.diverged, false);
  assert.equal(got.problem, null, "a current checkout has nothing wrong with it to report");
});

test("a checkout with no origin/main ref at all is its own state, not a stale one", () => {
  // Never fetched. "Stale" would be a guess; the honest report says the ref is
  // not there, because that is a different fix (`git fetch`) from being behind.
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: null });

  const got = inspectCheckout("PL_Predictor", root);

  assert.equal(got.exists, true);
  assert.equal(got.isRepo, true);
  assert.equal(got.originMain, null);
  assert.equal(got.diverged, null, "undeterminable is not false, and not true");
  assert.match(got.problem, /origin\/main/, "the absent ref must be named");
});

test("missing and stale are disjoint, and an undeterminable checkout is neither", () => {
  // Three buckets, not two, and the third is the one that must not be folded
  // into either. "Never fetched" is not stale — nothing has moved — and it is
  // not missing either. Calling it stale would send the reviewer to rebase a
  // checkout that simply has no remote ref yet.
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 2, originMain: 1 });      // stale
  repo(join(root, "Sports_Predictor"), { commits: 1, originMain: 0 });  // current
  repo(join(root, "NBA_Predictor"), { commits: 1, originMain: null });  // never fetched

  const { rows } = inspectSites(root);

  assert.deepEqual(missingCheckouts(rows).map((r) => r.name), ["F1_Predictor", "NFL_Predictor", "CFB_Predictor"]);
  assert.deepEqual(staleCheckouts(rows).map((r) => r.name), ["PL_Predictor"], "never-fetched is not stale");

  const overlap = missingCheckouts(rows).filter((r) => staleCheckouts(rows).includes(r));
  assert.deepEqual(overlap, [], "a checkout cannot be both missing and stale");

  // And it is still surfaced: tri-state, but never silent.
  const unfetched = rows.find((r) => r.name === "NBA_Predictor");
  assert.equal(unfetched.diverged, null);
  assert.ok(unfetched.problem, "an undeterminable checkout must still say something is wrong with it");
});

// ------------------------------------------------------------------ the report

test("the report names the root it used and where that root came from", () => {
  // "Not found" is unanswerable without this. A reader who cannot see which
  // directory was searched, and whether that directory came from the
  // environment or from a walk up the tree, has to go and work it out.
  const root = temp();
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });

  const report = sitesRootReport({ root, source: "SITES_ROOT", names: ["PL_Predictor", "NBA_Predictor"] });

  assert.match(report, new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), "the root path must be in the report");
  assert.match(report, /SITES_ROOT/, "the report must say the root came from the setting");
  assert.match(report, /PL_Predictor/);
  assert.match(report, /NBA_Predictor/);
});

test("the report shows the path, the verdict, and both SHAs per site", () => {
  const root = temp();
  const stale = repo(join(root, "PL_Predictor"), { commits: 2, originMain: 1 });
  repo(join(root, "Sports_Predictor"), { commits: 1, originMain: 0 });

  const report = sitesRootReport({ root, source: "SITES_ROOT" });

  assert.match(report, /present/, "a present site must be shown as present");
  assert.match(report, /MISSING/, "an absent site must be visibly absent");
  assert.match(report, new RegExp(stale.head), "a stale HEAD SHA must appear");
  assert.match(report, new RegExp(stale.originMain), "so must the origin/main SHA it differs from");
  assert.match(report, new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  for (const n of SITE_NAMES) assert.match(report, new RegExp(n), `${n} must appear in the report`);
});

// ------------------------------------------------------------------ discovery

test("SITES_ROOT wins over discovery, and the source is reported", () => {
  const fromEnv = temp();
  const other = temp();
  repo(join(fromEnv, "PL_Predictor"), { commits: 1, originMain: 0 });
  repo(join(other, "PL_Predictor"), { commits: 1, originMain: 0 });

  assert.equal(discoverSitesRoot({ env: { SITES_ROOT: fromEnv }, hub: join(other, "predictor-hub") }), fromEnv);
  assert.equal(
    sitesRootReport({ env: { SITES_ROOT: fromEnv }, hub: join(other, "predictor-hub") }).match(/SITES_ROOT/) !== null,
    true,
  );
});

test("discovery finds a PARTIALLY populated root instead of walking past it", () => {
  // The shape that produced the confusing failure. Under the old rule — every
  // site must be present for a directory to count as the root — a root holding
  // three of the six was not a root at all, so discovery kept climbing and the
  // failure became "could not find the sibling site checkouts", which points at
  // the setting rather than at the checkout that is actually gone.
  const base = temp();
  const root = join(base, "root");
  repo(join(root, "PL_Predictor"), { commits: 1, originMain: 0 });

  const hub = join(base, "root", "predictor-hub-worktrees", "some-branch");
  mkdirSync(hub, { recursive: true });

  assert.equal(discoverSitesRoot({ env: {}, hub }), root, "a partially populated root is still the root");

  const report = sitesRootReport({ env: {}, hub });
  assert.match(report, /discovered/, "the report must say the root was discovered, not set");
  assert.match(report, /MISSING/, "and it must name what is missing rather than claiming none of it");
  assert.match(report, /NBA_Predictor/, "including which checkout is gone");
});

// ------------------------------------------------- the real test file, end to end

test("the real site-components test names every absent checkout and the stale SHAs", () => {
  // End to end, and against the actual file, because the unit tests above
  // describe a module and this one describes what the reviewer sees. Run as a
  // subprocess with SITES_ROOT pointed at a temp root, so nothing here can
  // depend on the checkouts on this machine.
  const root = temp();
  const stale = repo(join(root, "PL_Predictor"), { commits: 2, originMain: 1 });
  repo(join(root, "Sports_Predictor"), { commits: 1, originMain: 0 });
  // NBA_Predictor and F1_Predictor are deliberately absent.

  // NODE_TEST_CONTEXT is deleted, not passed through. The parent runner sets it
  // for its own children, and a grandchild that inherits it runs as a test
  // child rather than as a runner — which makes the whole subprocess exit 0
  // and quietly pass this test no matter what the file under test did.
  // Measured: with it inherited, exit 0; with it stripped, exit 1.
  const env = { ...process.env, SITES_ROOT: root };
  delete env.NODE_TEST_CONTEXT;

  const run = spawnSync(
    process.execPath,
    ["--test", "tests/site-components.test.mjs"],
    { cwd: HUB, encoding: "utf8", env },
  );
  const seen = `${run.stdout}\n${run.stderr}`;

  assert.notEqual(run.status, 0, "an absent checkout must still fail: absence stays fatal");
  assert.match(seen, /NBA_Predictor/, "the failing run must name the missing site");
  assert.match(seen, /F1_Predictor/, "and the other missing site, not just the first one hit");
  assert.match(seen, new RegExp(stale.head.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), "and the stale HEAD SHA");
  assert.match(
    seen,
    new RegExp(stale.originMain.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    "and the origin/main SHA it differs from",
  );
  assert.match(seen, new RegExp(root.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), "and the root it searched");
});