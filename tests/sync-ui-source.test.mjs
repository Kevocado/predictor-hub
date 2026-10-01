// Does `sync-ui.mjs` refuse to vendor from a hub checkout it cannot vouch for,
// and refuse to delete a component the source no longer has?
//
// THE DEFECT THIS EXISTS FOR. `sync-ui.mjs` vendors `packages/predictor-ui/src`
// from the checkout that contains it. That checkout sat on `docs-nfl-players-
// decision`, which does not contain the newly merged `PicksList`, and the script
// vendored the package anyway — silently — DELETING `InstantBlock` and
// `bundleFacts` from a site that shipped them. Nothing warned. Three separate
// branches in one session hit it (PL, NBA, F1); two worked around it by syncing
// from a detached hub worktree at the right commit. The failure is dangerous
// because it is silent and because it REMOVES shipped code, so both halves get a
// guard: one for the state of the source, one for what the write would delete.
//
// EVERY TEST HERE IS A THROWAWAY GIT REPO. Real `git init`, real commits, real
// `origin` (a bare repo on disk), real `push`. No network, nothing shared, and
// the script under test is a real copy of `scripts/sync-ui.mjs` executed from
// inside the throwaway hub — so `ui-package.mjs` resolves `SRC` to that hub's
// package, which is what makes "vendor from this checkout" a thing the test can
// actually vary.
//
// EVERY GUARD HAS A CONTROL. The control is the same setup with the bad
// condition removed, asserted to SUCCEED. A guard that only ever fires proves
// nothing — it cannot tell a working guard from a script that refuses everything,
// and it will happily pass on a broken happy path. Where the two differ by one
// git command and the bytes are identical (detached vs on-main, other-branch vs
// main), the control is asserted at the SAME COMMIT, so a guard that fired on
// anything other than the actual bad state would be caught.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync, execFileSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { after } from "node:test";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
/** The scripts the throwaway hub needs to be a working hub. Copied, not linked:
 *  `ui-package.mjs` resolves `SRC` from its own path, so a copy is what makes the
 *  copy under test read the throwaway package instead of this repo's. */
const SCRIPTS = ["sync-ui.mjs", "ui-package.mjs", "hub-source.mjs"];

const made = [];
after(() => made.forEach((d) => rmSync(d, { recursive: true, force: true })));
const tempDir = () => { const d = mkdtempSync(join(tmpdir(), "syncui-")); made.push(d); return d; };

const git = (cwd, ...args) =>
  execFileSync("git", ["-C", cwd, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });

/** A hub that is at the top of main, clean, with a working `origin/main`.
 *
 *  Commit 1 ships two files. Every guard below perturbs THIS, so the control for
 *  each one is this repo untouched, and the perturbation is a single git command
 *  from it. */
function buildHub() {
  const root = tempDir();
  const hub = join(root, "hub");
  const origin = join(root, "origin.git");
  mkdirSync(hub);
  git(hub, "init", "-q", "-b", "main");
  git(hub, "config", "user.email", "hub@example.invalid");
  git(hub, "config", "user.name", "hub test");

  mkdirSync(join(hub, "scripts"), { recursive: true });
  for (const f of SCRIPTS) copyFileSync(join(HUB, "scripts", f), join(hub, "scripts", f));

  const src = join(hub, "packages", "predictor-ui", "src");
  mkdirSync(join(src, "components"), { recursive: true });
  writeFileSync(join(src, "fmt.ts"), "export const fmt = (n) => n.toFixed(1);\n");
  writeFileSync(join(src, "components", "MatchCard.tsx"), "export const MatchCard = () => null;\n");

  git(hub, "add", "-A");
  git(hub, "commit", "-qm", "hub: first cut of predictor-ui");
  git(hub, "init", "-q", "--bare", "-b", "main", origin);
  git(hub, "remote", "add", "origin", origin);
  git(hub, "push", "-q", "origin", "main");

  return {
    root,
    hub,
    origin,
    src,
    script: join(hub, "scripts", "sync-ui.mjs"),
    /** A site to vendor INTO. A plain directory: the site's own repo state is not
     *  this script's business, and only the vendored folder matters here.
     *
     *  `mkdirSync` returns undefined, and every site then being the literal
     *  string "undefined" made every test in this file write into ONE shared
     *  directory — so a test that expected a clean site found the previous
     *  test's `PicksList` and the deletion guard correctly refused it. The
     *  return value is the whole reason this is not a one-liner. */
    site: () => {
      const d = join(tempDir(), "site");
      mkdirSync(d);
      return d;
    },
    git: (...args) => git(hub, ...args),
    /** Ship another file from the package and publish it, so the hub is still
     *  clean and still at origin/main afterwards. */
    ship(name, body = `export const ${name.replace(/\W/g, "")} = () => null;\n`) {
      writeFileSync(join(src, name), body);
      git(hub, "add", "-A");
      git(hub, "commit", "-qm", `hub: ship ${name}`);
      git(hub, "push", "-q", "origin", "main");
    },
    publish() { git(hub, "push", "-q", "origin", "main"); },
    run(...args) { return spawnSync(process.execPath, [join(hub, "scripts", "sync-ui.mjs"), ...args], { encoding: "utf8" }); },
  };
}

/** A hub with NO remote at all, so `origin/main` cannot be resolved. Built
 *  separately because `buildHub` always wires one up — otherwise "never fetched"
 *  would be untestable, which is the case most likely to read as clean. */
function buildHubWithoutRemote() {
  const h = buildHub();
  git(h.hub, "remote", "remove", "origin");
  return h;
}

const vendored = (site) => join(site, "predictor-ui");
const filesIn = (dir) =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory()
      ? filesIn(join(dir, e.name)).map((f) => `${e.name}/${f}`)
      : [e.name]);
const manifest = (site) => JSON.parse(readFileSync(join(vendored(site), "SYNC.json"), "utf8"));

// ---------------------------------------------------------------- the control

test("CONTROL: a hub on main, clean, at origin/main vendors and nothing is refused", () => {
  const h = buildHub();
  const site = h.site();
  const r = h.run(site);
  assert.equal(r.status, 0, `expected the normal case to succeed.\nstdout: ${r.stdout}\nstderr: ${r.stderr}`);
  assert.match(r.stdout, /Synced 2 files/);
  assert.ok(existsSync(join(vendored(site), "components", "MatchCard.tsx")));
  assert.ok(existsSync(join(vendored(site), "fmt.ts")));
  assert.ok(!existsSync(join(vendored(site), "hub-source.mjs")), "only the package is vendored");
  assert.equal(h.run("--check", site).status, 0, "--check must pass on what a clean sync just wrote");
});

test("CONTROL: --check reports drift from a hub that is dirty, detached AND behind", () => {
  // The guards describe the SOURCE, and `--check` never reads the source — it
  // compares the site against the site's own manifest. So a hub in the worst
  // state on earth must not stop `--check` from doing its one job.
  const h = buildHub();
  const site = h.site();
  h.ship("components/PicksList.tsx");
  assert.equal(h.run(site).status, 0);
  assert.equal(h.run("--check", site).status, 0);

  h.ship("components/SummaryButton.tsx");
  h.git("reset", "-q", "--hard", "HEAD~1");
  h.git("checkout", "-q", "--detach", "HEAD");
  writeFileSync(join(h.src, "fmt.ts"), "export const fmt = (n) => n;\n");

  assert.equal(h.run("--check", site).status, 0, "a stale hub must not affect --check on an untouched site");
  writeFileSync(join(vendored(site), "fmt.ts"), "// hand edited\n");
  const drifted = h.run("--check", site);
  assert.equal(drifted.status, 1);
  assert.match(drifted.stderr, /fmt\.ts/, "--check must still name the drifted file");
});

// ------------------------------------------------- guard 1: dirty source tree

test("refuses a hub with uncommitted changes to the package, naming the file", () => {
  const h = buildHub();
  writeFileSync(join(h.src, "fmt.ts"), "export const fmt = (n) => String(n);\n");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0, "a dirty package must not be vendored without a word");
  assert.match(r.stderr, /fmt\.ts/, "the message must name the uncommitted file");
  assert.match(r.stderr, /uncommitted|dirty/i);
});

test("CONTROL: the same hub with the change reverted vendors normally", () => {
  const h = buildHub();
  writeFileSync(join(h.src, "fmt.ts"), "export const fmt = (n) => String(n);\n");
  assert.notEqual(h.run(h.site()).status, 0, "precondition: the dirty hub is refused");
  h.git("checkout", "--", "packages/predictor-ui/src/fmt.ts");
  const r = h.run(h.site());
  assert.equal(r.status, 0, `reverting the file must restore the normal path.\nstderr: ${r.stderr}`);
});

test("refuses a hub with an UNTRACKED file inside the package", () => {
  // `git status --porcelain` on a directory: an untracked file inside the
  // vendored source is a file the site would receive and no commit accounts for.
  const h = buildHub();
  writeFileSync(join(h.src, "components", "Sneaky.tsx"), "export const Sneaky = () => null;\n");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /Sneaky\.tsx/);
});

test("--vendor-anyway overrides the dirty-source guard, and says so", () => {
  const h = buildHub();
  writeFileSync(join(h.src, "fmt.ts"), "export const fmt = (n) => String(n);\n");
  const site = h.site();
  const r = h.run("--vendor-anyway", site);
  assert.equal(r.status, 0, `the explicit opt-in must work.\nstderr: ${r.stderr}`);
  assert.match(r.stderr, /vendor-anyway|override/i, "opting in must be reported, not silent");
  assert.match(readFileSync(join(vendored(site), "fmt.ts"), "utf8"), /String\(n\)/);
});

// ------------------------------------------------ guard 2: detached HEAD

test("refuses a detached HEAD, even when it is exactly at origin/main", () => {
  const h = buildHub();
  h.git("checkout", "-q", "--detach", "HEAD");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0, "a detached HEAD cannot be attributed to a branch");
  assert.match(r.stderr, /detached/i);
});

test("CONTROL: the identical commit on branch main vendors", () => {
  // Same SHA, same bytes, different git state. If this passes and the test above
  // fails, the guard is reading the branch state — which is the claim — and not
  // the file contents or some accident of setup.
  const h = buildHub();
  h.git("checkout", "-q", "--detach", "HEAD");
  const sha = h.git("rev-parse", "HEAD").trim();
  assert.notEqual(h.run(h.site()).status, 0, "precondition: detached is refused");
  h.git("checkout", "-q", "main");
  assert.equal(h.git("rev-parse", "HEAD").trim(), sha, "precondition: same commit");
  const r = h.run(h.site());
  assert.equal(r.status, 0, `on main at the same commit must succeed.\nstderr: ${r.stderr}`);
});

// ------------------------------------------ guard 3: a branch other than main

test("refuses a hub on a branch other than main, naming the branch", () => {
  const h = buildHub();
  h.git("checkout", "-q", "-b", "docs-nfl-players-decision");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /docs-nfl-players-decision/, "the message must name the branch it found");
  assert.match(r.stderr, /main/);
});

test("CONTROL: main at the same commit vendors", () => {
  const h = buildHub();
  h.git("checkout", "-q", "-b", "docs-nfl-players-decision");
  const sha = h.git("rev-parse", "HEAD").trim();
  assert.notEqual(h.run(h.site()).status, 0, "precondition: the side branch is refused");
  h.git("checkout", "-q", "main");
  assert.equal(h.git("rev-parse", "HEAD").trim(), sha, "precondition: same commit");
  assert.equal(h.run(h.site()).status, 0);
});

test("a side branch with NO component difference from main is still refused", () => {
  // The defect's own shape: the branch was a docs branch, and its package was
  // probably not even different. Nothing about the vendored bytes gives the
  // branch away, so a byte-diff check would pass this. Only git state catches it.
  const h = buildHub();
  h.git("checkout", "-q", "-b", "docs-nfl-players-decision");
  const before = h.run("--check", h.site());
  assert.equal(before.status, 1, "precondition: the site has not been synced yet");
  assert.notEqual(h.run(h.site()).status, 0);
});

// ---------------------------------------------- guard 4: behind origin/main

test("refuses a hub behind origin/main, naming both revisions and the distance", () => {
  const h = buildHub();
  h.ship("components/PicksList.tsx");
  h.git("reset", "-q", "--hard", "HEAD~1");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0, "a hub a commit behind main does not have PicksList to vendor");
  assert.match(r.stderr, /behind/i);
  assert.match(r.stderr, /PicksList|origin\/main/i);
  assert.ok(
    r.stderr.includes(h.git("rev-parse", "--short=12", "HEAD").trim()),
    "the message must carry the HEAD it found",
  );
  assert.ok(
    r.stderr.includes(h.git("rev-parse", "--short=12", "origin/main").trim()),
    "the message must carry origin/main it should have been at",
  );
});

test("CONTROL: the same hub moved up to origin/main vendors, and PicksList with it", () => {
  const h = buildHub();
  h.ship("components/PicksList.tsx");
  h.git("reset", "-q", "--hard", "HEAD~1");
  assert.notEqual(h.run(h.site()).status, 0, "precondition: behind is refused");
  h.git("reset", "-q", "--hard", "origin/main");
  const site = h.site();
  const r = h.run(site);
  assert.equal(r.status, 0, `fast-forwarding must restore the normal path.\nstderr: ${r.stderr}`);
  assert.ok(existsSync(join(vendored(site), "components", "PicksList.tsx")));
});

test("refuses a hub AHEAD of origin/main, because the bytes are nobody else's", () => {
  const h = buildHub();
  // Commit on main without pushing: HEAD is a descendant of origin/main, so the
  // bytes are real and reproducible here and nowhere else.
  writeFileSync(join(h.src, "components", "Local.tsx"), "export const Local = () => null;\n");
  h.git("add", "-A");
  h.git("commit", "-qm", "hub: unpushed local component");
  assert.equal(h.git("status", "--porcelain").trim(), "", "precondition: clean, just unpublished");
  const r = h.run(h.site());
  assert.notEqual(r.status, 0, "vendoring an unpushed commit writes bytes no other checkout can reproduce");
  assert.match(r.stderr, /ahead|origin\/main/i);
});

test("CONTROL: that same hub, once pushed, vendors", () => {
  // The AHEAD test's exact setup — same commands, same order — with `push` as
  // the only difference. So if this fails while that passes, the guard is
  // refusing something other than "ahead", which is the thing under test.
  const h = buildHub();
  writeFileSync(join(h.src, "components", "Local.tsx"), "export const Local = () => null;\n");
  h.git("add", "-A");
  h.git("commit", "-qm", "hub: unpushed local component");
  assert.notEqual(h.run(h.site()).status, 0, "precondition: ahead is refused");
  h.publish();
  const site = h.site();
  const r = h.run(site);
  assert.equal(r.status, 0, `pushing must restore the normal path.\nstderr: ${r.stderr}`);
  assert.ok(existsSync(join(vendored(site), "components", "Local.tsx")));
});

test("refuses a hub with no origin/main at all, rather than assuming it is current", () => {
  const h = buildHubWithoutRemote();
  const r = h.run(h.site());
  assert.notEqual(r.status, 0, "with no origin/main there is no way to know the hub is current");
  assert.match(r.stderr, /origin\/main|fetch/i);
});

test("CONTROL: that same hub, once it has a remote, vendors", () => {
  const h = buildHubWithoutRemote();
  assert.notEqual(h.run(h.site()).status, 0, "precondition: no remote is refused");
  h.git("remote", "add", "origin", h.origin);
  h.publish();
  assert.equal(h.run(h.site()).status, 0);
});

// ---------------------------------------- guard 5: the write would DELETE a file

test("refuses to delete a shipped component the source no longer has, and writes nothing", () => {
  const h = buildHub();
  h.ship("components/InstantBlock.tsx");
  const site = h.site();
  assert.equal(h.run(site).status, 0, "precondition: the site vendors the full package first");
  assert.ok(existsSync(join(vendored(site), "components", "InstantBlock.tsx")));

  // The hub is now clean and at origin/main — the source guard passes. Only the
  // deletion guard can stop this, which is what makes the attribution clean.
  h.git("rm", "-q", "packages/predictor-ui/src/components/InstantBlock.tsx");
  h.git("commit", "-qm", "hub: drop InstantBlock");
  h.publish();
  assert.equal(h.git("status", "--porcelain").trim(), "", "precondition: the hub is clean and at origin/main");

  const r = h.run(site);
  assert.notEqual(r.status, 0, "silently deleting a shipped component is the exact bug");
  assert.match(r.stderr, /InstantBlock\.tsx/, "the deletion must be named");
  assert.match(r.stderr, /delete|drop|would/i);
  assert.ok(existsSync(join(vendored(site), "components", "InstantBlock.tsx")), "the refused run must leave the site alone");
  assert.ok(manifest(site).files["components/InstantBlock.tsx"], "the manifest must be untouched too");
});

test("CONTROL: the same hub vendored into a site that has nothing to lose succeeds", () => {
  const h = buildHub();
  h.ship("components/InstantBlock.tsx");
  h.git("rm", "-q", "packages/predictor-ui/src/components/InstantBlock.tsx");
  h.git("commit", "-qm", "hub: drop InstantBlock");
  h.publish();
  const empty = h.site();
  const r = h.run(empty);
  assert.equal(r.status, 0, `no target file to lose means nothing to refuse.\nstderr: ${r.stderr}`);
  assert.ok(!existsSync(join(vendored(empty), "components", "InstantBlock.tsx")));
});

test("CONTROL: vendoring a superset of what the site has is not a deletion", () => {
  const h = buildHub();
  const site = h.site();
  assert.equal(h.run(site).status, 0, "precondition: the site is at the old package");
  const before = Object.keys(manifest(site).files);
  h.ship("components/PicksList.tsx");
  const r = h.run(site);
  assert.equal(r.status, 0, `adding a file is the normal update, not a deletion.\nstderr: ${r.stderr}`);
  const after = Object.keys(manifest(site).files);
  assert.ok(after.includes("components/PicksList.tsx"));
  assert.deepEqual(
    before.filter((f) => !after.includes(f)),
    [],
    "nothing the site had may go missing",
  );
});

test("refuses when the source no longer ships a file the site added by hand", () => {
  // `sync` removes the whole vendored folder before writing, so a file nobody
  // recorded is destroyed just as silently as one in the manifest.
  const h = buildHub();
  const site = h.site();
  assert.equal(h.run(site).status, 0);
  writeFileSync(join(vendored(site), "local.ts"), "export const x = 1;\n");
  const r = h.run(site);
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /local\.ts/);
  assert.ok(existsSync(join(vendored(site), "local.ts")));
});

test("--allow-deletions performs the deletion, naming every file it removes", () => {
  const h = buildHub();
  h.ship("components/InstantBlock.tsx");
  const site = h.site();
  assert.equal(h.run(site).status, 0);
  h.git("rm", "-q", "packages/predictor-ui/src/components/InstantBlock.tsx");
  h.git("commit", "-qm", "hub: drop InstantBlock");
  h.publish();

  assert.notEqual(h.run(site).status, 0, "precondition: refused without the flag");
  const r = h.run("--allow-deletions", site);
  assert.equal(r.status, 0, `the explicit opt-in must work.\nstderr: ${r.stderr}`);
  assert.ok(!existsSync(join(vendored(site), "components", "InstantBlock.tsx")), "now the file is gone, on purpose");
  assert.match(r.stderr, /InstantBlock\.tsx/, "even when allowed, the removal must be reported");
});

test("--allow-deletions does NOT open the source guard", () => {
  // Two decisions, two flags. A deletion opt-in must not become a licence to
  // vendor from a branch that is not main.
  const h = buildHub();
  h.git("checkout", "-q", "-b", "docs-nfl-players-decision");
  const r = h.run("--allow-deletions", h.site());
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /docs-nfl-players-decision/);
});

test("--vendor-anyway does NOT open the deletion guard", () => {
  // And the reverse, for the same reason: InstantBlock must be impossible to
  // remove by accident even by someone who has already waved through a dirty tree.
  const h = buildHub();
  h.ship("components/InstantBlock.tsx");
  const site = h.site();
  assert.equal(h.run(site).status, 0);
  h.git("rm", "-q", "packages/predictor-ui/src/components/InstantBlock.tsx");
  h.git("commit", "-qm", "hub: drop InstantBlock");
  h.publish();
  const r = h.run("--vendor-anyway", site);
  assert.notEqual(r.status, 0, "the deletion guard must hold on its own");
  assert.match(r.stderr, /InstantBlock\.tsx/);
  assert.ok(existsSync(join(vendored(site), "components", "InstantBlock.tsx")));
});

// -------------------------------------------------- --from: naming the source

test("--from <path> vendors from another checkout, and says which one", () => {
  const h = buildHub();
  const other = buildHub();
  other.git("checkout", "-q", "main");
  writeFileSync(join(other.src, "components", "OnlyInOther.tsx"), "export const OnlyInOther = () => null;\n");
  other.git("add", "-A");
  other.git("commit", "-qm", "hub: OnlyInOther");
  other.publish();

  const site = h.site();
  assert.ok(!existsSync(join(h.src, "components", "OnlyInOther.tsx")), "precondition: only the other hub has it");
  const r = h.run("--from", other.hub, site);
  assert.equal(r.status, 0, `--from must be a working route, not a dead end.\nstderr: ${r.stderr}`);
  assert.ok(
    existsSync(join(vendored(site), "components", "OnlyInOther.tsx")),
    "must read the named checkout, not the one holding the script",
  );
  assert.ok(r.stdout.includes(other.hub), `the run must name the checkout it read. stdout: ${r.stdout}`);
});

test("--from <sha> accepts a named commit, and refuses one this checkout is not at", () => {
  const h = buildHub();
  h.git("checkout", "-q", "-b", "docs-nfl-players-decision");
  const sha = h.git("rev-parse", "--short=12", "HEAD").trim();
  assert.notEqual(h.run(h.site()).status, 0, "precondition: an unnamed side branch is refused");
  assert.equal(h.run("--from", sha, h.site()).status, 0, `--from <sha> must be a working route.\n${h.run("--from", sha, h.site()).stderr}`);
});

test("--from <sha> that does not match HEAD is refused, naming both", () => {
  const h = buildHub();
  h.ship("components/PicksList.tsx");
  const older = h.git("rev-parse", "--short=12", "HEAD~1").trim();
  const r = h.run("--from", older, h.site());
  assert.notEqual(r.status, 0, "--from must not become a way to claim a commit you are not at");
  assert.ok(r.stderr.includes(older), "must name the commit asked for");
  assert.ok(
    r.stderr.includes(h.git("rev-parse", "--short=12", "HEAD").trim()),
    "must name the commit actually checked out",
  );
});

test("--from still refuses a dirty package, because a named commit is not the bytes on disk", () => {
  const h = buildHub();
  const sha = h.git("rev-parse", "--short=12", "HEAD").trim();
  writeFileSync(join(h.src, "fmt.ts"), "export const fmt = (n) => String(n);\n");
  const r = h.run("--from", sha, h.site());
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /fmt\.ts/);
});

test("--from pointing at a path with no package is refused, not crashed on", () => {
  const h = buildHub();
  const empty = tempDir();
  const r = h.run("--from", empty, h.site());
  assert.notEqual(r.status, 0);
  assert.ok(r.status !== 1 || r.stderr.length > 0);
  assert.match(r.stderr, /predictor-ui|package/i);
});

// ------------------------------------------------------------- argument rules

test("an unknown flag is refused rather than treated as a site path", () => {
  const h = buildHub();
  const site = h.site();
  const r = h.run("--force", site);
  assert.notEqual(r.status, 0);
  assert.match(r.stderr, /usage|--force/i);
  assert.ok(!existsSync(join(vendored(site), "SYNC.json")), "nothing may be written on an unknown flag");
});

test("the usage message names both opt-in flags, so a refusal is actionable", () => {
  const h = buildHub();
  const r = h.run();
  assert.equal(r.status, 2);
  assert.match(r.stderr, /--vendor-anyway/);
  assert.match(r.stderr, /--allow-deletions/);
  assert.match(r.stderr, /--from/);
  assert.match(r.stderr, /--check/);
});

// ------------------------------------------- the guards are the real ones

test("the guard reads git state of the hub, not a heuristic over the package bytes", () => {
  // If any of this is a hand-rolled check over the file list, the two "same
  // bytes, different git state" tests above are the only thing holding it up.
  // Assert the source of the verdicts is git, so a rewrite to a byte-diff is
  // caught here rather than by a silent regression in the field.
  const src = readFileSync(join(HUB, "scripts", "hub-source.mjs"), "utf8");
  assert.match(src, /execFileSync\("git"/, "hub-source must shell out to git");
  for (const probe of ["status", "rev-parse", "symbolic-ref", "rev-list"]) {
    assert.match(src, new RegExp(probe), `hub-source must consult \`git ${probe}\``);
  }
  assert.ok(
    !/shippedFiles\(|contentVersion\(/.test(src),
    "hub-source judges git state only; deciding what is shipped belongs to ui-package.mjs",
  );
});

test("sync-ui asks hub-source, and both opt-in flags reach it", () => {
  const src = readFileSync(join(HUB, "scripts", "sync-ui.mjs"), "utf8");
  assert.match(src, /from "\.\/hub-source\.mjs"/, "sync-ui must call the guard rather than reimplement it");
  assert.match(src, /--vendor-anyway/);
  assert.match(src, /--allow-deletions/);
  assert.match(src, /--from/);
});

test("a guard that only ever fires would be caught here", () => {
  // The control tests above are the real proof. This one only asserts that the
  // suite contains them, so that deleting a control cannot leave the file
  // looking equally strong.
  const self = readFileSync(fileURLToPath(import.meta.url), "utf8");
  const controls = self.match(/^test\("CONTROL:/gm) ?? [];
  assert.ok(controls.length >= 10, `expected a control per guard, found ${controls.length}`);
  assert.match(self, /throwaway git repo|real commits/i, "the setup must be real git repos, not mocks");
});
