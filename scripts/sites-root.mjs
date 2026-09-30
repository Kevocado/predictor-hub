// Which directory holds the sibling site checkouts, what is in it, and how far
// each one is from `origin/main`.
//
// This exists because two measured failures wore the same costume. A missing
// checkout reported itself as a broken repo, and a STALE checkout reported
// itself as a working one:
//
//   * `no local checkout for X at Y, so its components were not checked` reads
//     as a defect in X. It is not — it is a directory that is not on this
//     machine. And the listing stopped at the first absent site, so a root
//     missing two checkouts reported one of them, leaving the second to be
//     discovered by hand.
//   * A checkout whose `HEAD` differs from `origin/main` said nothing at all.
//     The component check reads `origin/main`; a reviewer reading the working
//     tree is reading `HEAD`. When those differ, "the code says X" is a claim
//     about a tree the check never looked at, which is exactly how a stale
//     checkout gets mistaken for a code defect. Both SHAs go in the report.
//
// Both are MESSAGE problems. Absence stays fatal: a check that could not run
// must not look like one that ran, and that is not up for negotiation here.
// What changes is that the failure now carries the whole picture — every site
// considered, the path each was looked for at, whether that path is there, and
// where its HEAD sits.
//
// Everything here reads the local filesystem and calls `git` with no arguments
// that reach a network: `rev-parse` against refs already on disk. `ls-tree` is
// the caller's business, not this file's.
import { execFileSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");

/** Every sibling checkout the reviewer works from, in report order.
 *
 * Six, not the four `SITES` in `check-site-sync.mjs`: `NFL_Predictor` and
 * `CFB_Predictor` vendor no frontend and have no `predictor-ui/` tree, so they
 * are not checked — but they ARE checkouts the reviewer has open, and a report
 * that lists only four cannot answer "which of my six is gone".
 */
export const SITE_NAMES = [
  "PL_Predictor",
  "Sports_Predictor",
  "NBA_Predictor",
  "F1_Predictor",
  "NFL_Predictor",
  "CFB_Predictor",
];

/** Short SHAs, matching `git ls-remote | cut -c1-12` elsewhere in the repo, so
 *  a SHA in this report can be pasted next to one from `watch.sh` unchanged. */
const SHA_LEN = 12;

const revParse = (repo, rev) =>
  // `--short=N`, not `--short N`: separated, git reads `N` as another revision
  // to resolve and fails with "Needed a single revision" or, worse, resolves it.
  execFileSync("git", ["-C", repo, "rev-parse", `--short=${SHA_LEN}`, rev], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }).trim();

/** A rev, or `null` if it cannot be read. Never throws: an unreadable ref is a
 *  state to report, not an error to propagate out of an inspection. */
const tryRev = (repo, rev) => {
  try {
    return revParse(repo, rev) || null;
  } catch {
    return null;
  }
};

/** Where the sibling checkouts live, or `null` if nowhere up the tree has one.
 *
 * `SITES_ROOT` overrides, and that is what CI uses. Otherwise walk UP from the
 * hub, because the hub is checked out in two shapes — the plain clone
 * (`<root>/predictor-hub`) and a worktree (`<root>/predictor-hub-worktrees/
 * <branch>`) — and `<root>` is the PARENT of the former but the GRANDPARENT of
 * the latter. Inferring from `..` alone is what sent the first attempt to
 * `predictor-hub-worktrees/PL_Predictor`.
 *
 * A directory qualifies on ONE recognised checkout, not all of them. The old
 * rule required every name to be present, which meant a root holding three of
 * the six was not a root at all: discovery climbed past it and the failure came
 * out as "could not find the sibling site checkouts" — a complaint about the
 * setting, when the truth was that two checkouts were absent from a root that
 * was right. Finding it and REPORTING what is missing is the whole fix.
 *
 * Bounded at 5 levels: enough to clear a worktree, shallow enough not to wander
 * into an unrelated ancestor that happens to hold a directory of that name.
 */
export function discoverSitesRoot({ env = process.env, hub = HUB, names = SITE_NAMES, levels = 5 } = {}) {
  const fromEnv = env.SITES_ROOT;
  if (fromEnv) return fromEnv;
  let dir = hub;
  for (let i = 0; i < levels; i++) {
    const parent = dirname(dir);
    if (names.some((n) => existsSync(join(parent, n)))) return parent;
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

/** One checkout's state, as far as it can be read without a network.
 *
 * Three failures kept apart, because they have three different fixes and
 * lumping them is how one of them gets misdiagnosed:
 *
 *   MISSING      the directory is not there        → clone it, or fix the root
 *   NOT A REPO   the directory is there, no `.git` → it is not a clone
 *   STALE        `HEAD` ≠ `origin/main`             → fetch and rebase, or read origin/main
 *
 * `diverged` is tri-state on purpose: `true` means they differ, `false` means
 * they match, and `null` means it could not be determined because there is no
 * `origin/main` ref at all. Collapsing `null` into `false` would report a
 * never-fetched checkout as current, which is the one answer that must never be
 * given by accident.
 */
export function inspectCheckout(name, root) {
  const path = join(root, name);

  if (!existsSync(path)) {
    return {
      name, path, exists: false, isRepo: false,
      head: null, originMain: null, diverged: null,
      problem: `MISSING — no ${name} checkout at ${path}; that path does not exist, so this site's components could not be checked`,
    };
  }
  if (!existsSync(join(path, ".git"))) {
    // A directory with the right NAME that is not a clone. `existsSync` says
    // yes; a naive report says "present"; the failure then surfaces further
    // down as something about the repository, which is the wrong thing again.
    const kind = statSync(path).isDirectory() ? "directory" : "file";
    return {
      name, path, exists: true, isRepo: false,
      head: null, originMain: null, diverged: null,
      problem: `NOT A CHECKOUT — ${path} exists and is a ${kind}, but has no .git: this is not a git checkout of ${name}`,
    };
  }

  const head = tryRev(path, "HEAD");
  const originMain = tryRev(path, "origin/main");

  if (head === null) {
    return {
      name, path, exists: true, isRepo: true,
      head: null, originMain, diverged: null,
      problem: `UNREADABLE — ${path} is a git repository but HEAD could not be read, so it cannot be compared with anything`,
    };
  }
  if (originMain === null) {
    return {
      name, path, exists: true, isRepo: true,
      head, originMain: null, diverged: null,
      problem: `NEVER FETCHED — ${path} has no origin/main ref (HEAD is ${head}), so this checkout cannot be compared with the remote; run git fetch in it`,
    };
  }
  if (head !== originMain) {
    return {
      name, path, exists: true, isRepo: true,
      head, originMain, diverged: true,
      problem: `STALE — ${name} at ${path} is at HEAD ${head}, which is not origin/main ${originMain}; this checkout is stale and "the code says X" from it does not describe what the check reads, which is origin/main`,
    };
  }
  return { name, path, exists: true, isRepo: true, head, originMain, diverged: false, problem: null };
}

/** Every site looked for, in order, with nothing dropped. */
export function inspectSites(root, names = SITE_NAMES) {
  const rows = names.map((n) => inspectCheckout(n, root));
  return { rows, missing: missingCheckouts(rows), stale: staleCheckouts(rows) };
}

export const missingCheckouts = (rows) => rows.filter((r) => !r.exists || !r.isRepo);
export const staleCheckouts = (rows) => rows.filter((r) => r.diverged === true);

/** The whole picture as text: the root, where the root came from, and one line
 *  per site. Used in a failure message, so it must stand alone. */
export function sitesRootReport({
  root = null,
  source = null,
  env = process.env,
  hub = HUB,
  names = SITE_NAMES,
} = {}) {
  if (root === null) root = discoverSitesRoot({ env, hub, names });
  if (root === null) return `no sibling site checkouts found within 5 levels above ${hub}, and SITES_ROOT is unset`;

  const where = source ?? (env.SITES_ROOT ? "SITES_ROOT" : "discovered by walking up from the hub");
  const { rows } = inspectSites(root, names);
  const width = Math.max(...rows.map((r) => r.name.length));
  const lines = [
    `site checkouts — root ${root} (${where})`,
    "",
    `  ${"site".padEnd(width)}  ${"path looked at".padEnd(root.length + 16)}  state`,
  ];
  for (const r of rows) {
    const state = r.problem ? r.problem.split(" — ")[0] : `present, HEAD ${r.head} = origin/main ${r.originMain}`;
    lines.push(`  ${r.name.padEnd(width)}  ${r.path.padEnd(root.length + 16)}  ${state}`);
  }
  for (const r of rows) {
    if (r.problem) lines.push(`  ${r.name}: ${r.problem}`);
  }
  return lines.join("\n");
}