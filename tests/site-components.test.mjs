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
import { SITE_NAMES, discoverSitesRoot, inspectSites, sitesRootReport } from "../scripts/sites-root.mjs";
import { SRC, shippedFiles } from "../scripts/ui-package.mjs";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
/** Where the sibling repos live: `SITES_ROOT`, else discovered by walking up
 *  from the hub. Both the rule and the reasons are in scripts/sites-root.mjs —
 *  which also reports what it found, so a failure here says which checkout is
 *  missing and where it looked rather than naming the repo and stopping. */
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
/** The report, built once. Every failure below carries it.
 *
 * It answers, in one place, the three questions that were being answered
 * wrongly: which checkout is missing, where it looked for it, and where the
 * working tree sits against the `origin/main` the checks actually read. */
const report = sitesRootReport({ root: DISCOVERED, hub: HUB });

const listingFor = (site) => {
  // Absence stays fatal: a check that could not run must not look like one that
  // ran. What is fixed is the message.
  if (!DISCOVERED) {
    assert.fail(
      `could not find the sibling site checkouts, and SITES_ROOT is unset. ${report}. ` +
        `Set SITES_ROOT to the directory holding them — this test used to hard-code one ` +
        `machine's path, so it worked there and failed everywhere else with a message ` +
        `about a missing checkout rather than about the missing setting.`,
    );
  }
  const repo = join(DISCOVERED, basename(site.repo));
  if (!existsSync(join(repo, ".git"))) {
    assert.fail(
      `${site.repo} could not be checked. This is a skip-shaped hole, not a pass.\n\n${report}`,
    );
  }
  const out = execFileSync("git", ["-C", repo, "ls-tree", "-r", "--name-only", `origin/${ref()}`], {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  return new Set(out.split("\n").filter(Boolean));
};

test("every site checkout is present, and says where it was looked for", () => {
  // Ahead of the component check, and separate from it, because "can this run at
  // all" and "do the sites have the components" are different questions.
  //
  // Folded into the loop below, an absent checkout was only discovered when the
  // loop happened to reach that site — so a site that failed the component
  // comparison first masked every absence behind it, and the report naming the
  // missing checkouts never appeared at all. Checked first, it always appears.
  const { rows, missing } = inspectSites(DISCOVERED ?? "", SITES.map((s) => basename(s.repo)));

  assert.deepEqual(
    missing.map((r) => `${r.name} at ${r.path}`),
    [],
    `these site checkouts are not usable, so no site's components were checked — this is a ` +
      `skip-shaped hole, not a pass:\n\n${report}`,
  );
  // Present, but say it. A checkout the reviewer reads may not be the ref the
  // check reads, and that difference is the trap this whole file exists for.
  for (const r of rows) {
    assert.ok(r.isRepo, `${r.name} at ${r.path} is not a git checkout:\n\n${report}`);
  }
});

test("a checkout behind origin/main is reported, so a stale tree is never read as a code defect", () => {
  // Does NOT fail on staleness — the check reads `origin/main`, which is
  // correct whatever the working tree holds, and failing here would make every
  // developer with a feature branch unable to run the suite. It reports, because
  // the trap this replaces is reading the working tree, believing it describes
  // what the check saw, and concluding the code is wrong when it is not.
  for (const r of inspectSites(DISCOVERED ?? "", SITE_NAMES).rows) {
    if (r.diverged === true) {
      console.error(
        `note: ${r.name} at ${r.path} is at HEAD ${r.head}, not origin/main ${r.originMain}. ` +
          `This check reads origin/main, so its verdict is unaffected — but "the code says X" ` +
          `from the working tree does not describe what was checked.`,
      );
    }
  }
  assert.ok(true, "this reports; it does not fail on a stale checkout");
});

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
