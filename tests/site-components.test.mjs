// Does every registered site actually carry every shared component?
//
// `check-site-sync.mjs` answers "is this site's copy the current one?" by
// comparing one content hash. That catches a site that is behind, and a site
// that is behind *because a component is missing* — but only as a version
// mismatch, and only once someone reads the warning. It cannot say which
// component is absent, and while ENFORCE_SITE_SYNC is unset it does not fail
// at all.
//
// The failure this file exists for is narrower and more damning: a site that
// has drifted so far, or was wired up by hand, that a component the panel
// needs is simply not there. NBA is the live example — it vendored
// predictor-ui, sat at an older version, and its game detail rendered no
// summary at all, with every test in the repo green because nothing asserted
// the component was mounted.
//
// So this asserts presence by NAME, per site, from the same SITES list the
// staleness check uses. Two properties that the hash check does not have:
//
//   * it names the missing file, so the fix is obvious from the failure;
//   * it is derived from the shipped set, so adding a component to the package
//     makes every site that has not re-vendored fail — which is the point.
//     A hard-coded list here would go stale the same way the code did.
//
// Like its sibling, nothing here depends on a network call that can be refused:
// the file listing comes from `git ls-tree` against each site's local
// `origin/main`, so it is a pure function of what is already on disk.
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { DEFAULT_REF, SITES } from "../scripts/check-site-sync.mjs";
import { SRC, shippedFiles } from "../scripts/ui-package.mjs";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
/** Where the sibling repos live.
 *
 * `SITES_ROOT`, required, and discovered from the hub's own path when unset.
 *
 * The first version hard-coded `/Users/sigey/Documents/Projects.nosync`, which
 * is a workstation path in a test: it works on one machine, silently resolves
 * to nothing on another, and fails there with a message about a missing
 * checkout rather than about the missing setting.
 *
 * Discovery walks UP from the hub looking for a directory that actually
 * contains the sites, because the hub is checked out in two shapes — the plain
 * clone (`<root>/predictor-hub`) and a worktree
 * (`<root>/predictor-hub-worktrees/<branch>`) — and `<root>` is the parent of the
 * former but the GRANDparent of the latter. Inferring from `..` alone is what
 * sent the first attempt to `predictor-hub-worktrees/PL_Predictor`.
 *
 * `SITES_ROOT` overrides both, which is what CI and any other layout uses.
 */
const SITE_NAMES = ["PL_Predictor", "Sports_Predictor", "NBA_Predictor", "F1_Predictor"];

function discoverSitesRoot() {
  const fromEnv = process.env.SITES_ROOT;
  if (fromEnv) return fromEnv;
  // Up to 5 levels: enough to clear a worktree, shallow enough not to wander
  // into an unrelated ancestor that happens to hold a directory of that name.
  let dir = HUB;
  for (let i = 0; i < 5; i++) {
    const parent = dirname(dir);
    if (SITE_NAMES.every((n) => existsSync(join(parent, n, ".git"))
                         || existsSync(join(parent, n)))) {
      return parent;
    }
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

const DISCOVERED = discoverSitesRoot();

/** Which ref of each site to judge. `main` is the answer for production —
 *  that is what every site builds from on the VPS. Overridable so this can be
 *  pointed at a branch to prove the check goes green once a site re-vendors,
 *  rather than only ever being seen red. */
const ref = () => process.env.SITES_REF || DEFAULT_REF;

/** Every shipped file, as site-relative paths. */
const shipped = () =>
  shippedFiles().map((f) => f.slice(SRC.length + 1).split("\\").join("/"));

/** The files a site's ref carries, from the local checkout.
 *
 * `git ls-tree` against the local `origin/main`, not the GitHub API. Two
 * attempts used `gh api repos/.../git/trees/main?recursive=1` and both failed
 * for the same non-obvious reason: `gh api` substitutes its own placeholders
 * into the path, so `main` is replaced by a resolved sha and the `?` is
 * mangled — the call returns a branch-name string where a tree was expected.
 * `ls-tree` has no such rewriting, needs no token, and cannot be rate-limited.
 */
const listingFor = (site) => {
  if (!DISCOVERED) {
    assert.fail(
      `could not find the sibling site checkouts. Set SITES_ROOT to the directory ` +
        `holding ${SITE_NAMES.join(", ")} — the first version of this test hard-coded ` +
        `one machine's path, so it worked there and failed everywhere else with a ` +
        `message about a missing checkout rather than about the missing setting.`,
    );
  }
  const repo = join(DISCOVERED, basename(site.repo));
  if (!existsSync(join(repo, ".git"))) {
    // A SET-but-wrong SITES_ROOT is a different mistake from no setting, and it
    // gets its own message: "the directory you named has no such checkout" reads
    // as a typo in the path, while the generic text below reads as a broken repo.
    assert.fail(
      process.env.SITES_ROOT
        ? `SITES_ROOT is set to ${DISCOVERED} but it has no checkout of ` +
          `${basename(site.repo)} (looked for ${repo}). The setting is wrong, not the repo.`
        : `no local checkout for ${site.repo} at ${repo}, so its components were not ` +
          `checked. This is a skip-shaped hole, not a pass.`,
    );
  }
  const out = execFileSync("git", ["-C", repo, "ls-tree", "-r", "--name-only", `origin/${ref()}`], {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return new Set(out.split("\n").filter(Boolean));
};

test("every registered site vendors every shipped component", () => {
  const want = shipped();
  assert.ok(want.length > 0, "the package shipped nothing, so this test would pass on an empty set");
  assert.ok(
    want.some((f) => f.startsWith("components/")),
    "no components in the shipped set, so this would pass on a package with none",
  );

  for (const site of SITES) {
    const have = listingFor(site);
    const prefix = site.manifest.replace(/SYNC\.json$/, "");
    const missing = want.filter((f) => !have.has(`${prefix}${f}`));
    assert.deepEqual(
      missing,
      [],
      `${site.repo} is missing ${missing.length} shared component(s): ${missing.join(", ")}. ` +
        `Re-vendor: node scripts/sync-ui.mjs <site-frontend-src>`,
    );
  }
});

test("the required set is derived from the package, not typed out here", () => {
  // Guards the guard. If `shipped()` is ever replaced by a literal array, a
  // component added to the package later stops being required and this file
  // goes quietly blind — the exact failure it was written to end.
  const source = shipped.toString();
  assert.ok(
    !/\[\s*["']/.test(source),
    "shipped() must read the package, not return a hard-coded array",
  );
  assert.ok(shipped().includes("components/FixtureExplainer.tsx"),
    "FixtureExplainer is expected in the shipped set; if it moved, this assertion needs updating");
});

test("a missing component is named, so the fix is obvious from the failure", () => {
  // The whole value of checking by name rather than by hash. Asserted on the
  // comparison itself, with no network and no checkout involved.
  const want = shipped();
  const have = new Set(want.slice(1));
  const missing = want.filter((f) => !have.has(f));
  assert.equal(missing.length, 1);
  assert.ok(
    missing[0].startsWith("components/"),
    `the named component should be a component, got ${missing[0]}`,
  );
});
