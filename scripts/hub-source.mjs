// What state is this hub checkout in, and is it safe to vendor from?
//
// THE DEFECT THIS EXISTS FOR. `sync-ui.mjs` vendors `packages/predictor-ui/src`
// from the checkout that contains it. That checkout sat on
// `docs-nfl-players-decision`, which does not contain the newly merged
// `PicksList`, and the script vendored it anyway — silently — DELETING
// `InstantBlock` and `bundleFacts` from a site that shipped them. Nothing warned.
// Three separate branches in one session hit it (PL, NBA, F1); two worked
// around it by syncing from a detached worktree at the right commit.
//
// The reason a guard can fix this is that the bad state is in GIT, not in the
// bytes. A stale branch and a fresh `main` can vendor byte-identical packages,
// and the defect's branch was a *docs* branch, so the vendored output probably
// differed in nothing an agent would think to check. Every finding below comes
// from `git`, and none from the package's contents. A byte-diff would pass the
// exact case that bit three branches.
//
// Findings, each with its own remedy, because lumping them is how one gets
// misdiagnosed (see scripts/sites-root.mjs for the same lesson at larger scale):
//
//   DIRTY       uncommitted changes under the package
//               -> commit or stash them; the vendored copy would carry bytes
//                  that no commit accounts for
//   DETACHED    HEAD is not on a branch
//               -> check out main, or name the commit with --from <sha>
//   NOT_MAIN    on a branch that is not main
//               -> check out main, or --from <sha> / --from <path>
//   NO_ORIGIN   no origin/main ref, so "is this current?" has no answer
//               -> git fetch; never assume a never-fetched checkout is current
//   BEHIND      HEAD is an ancestor of origin/main
//               -> the package here is missing everything merged since
//   AHEAD       HEAD is not on origin/main at all
//               -> the bytes are nobody else's; push, or read origin/main
//
// Every `git` call here is against refs already on disk. No fetch, no network:
// a guard that needed the network would be refused exactly when it is needed.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join, relative, resolve } from "node:path";

/** Short SHAs, matching sites-root.mjs, so a SHA from here sits next to one from
 *  `git ls-remote | cut -c1-12` unchanged. */
const SHA_LEN = 12;

/** A `git` call, or `null` if it failed. Never throws: an unreadable ref is a
 *  state to report, not an exception to propagate out of an inspection.
 *
 *  `stdio` is set so a failed call cannot print git's own error to the caller's
 *  stderr — the findings are the report, and git's noise under them would read
 *  as part of it. */
const tryGitRaw = (hub, args) => {
  try {
    return execFileSync("git", ["-C", hub, ...args], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
  } catch {
    return null;
  }
};
const tryGit = (hub, args) => tryGitRaw(hub, args)?.trim() ?? null;

const short = (hub, rev) => tryGit(hub, ["rev-parse", `--short=${SHA_LEN}`, rev]);

/** How many commits `HEAD` is behind / ahead of `origin/main`, or `null` when it
 *  cannot be counted (no `origin/main`, so no comparison is possible).
 *
 *  `rev-list --count`, not a boolean "is HEAD an ancestor of": a number is what
 *  tells a reader whether they are one merge behind or forty, and the two want
 *  different urgency. */
const distance = (hub, range) => {
  const n = tryGit(hub, ["rev-list", "--count", range]);
  return n === null ? null : Number(n);
};

/** The uncommitted paths under `pkgDir`, relative to the hub, or `[]` when the
 *  tree is clean.
 *
 *  `git status --porcelain -- <dir>`: scoped to the package, because an edit to
 *  `tests/site-components.test.mjs` cannot change a vendored byte, and a guard
 *  that blocks on it would be a guard people disable. Scoping also catches
 *  UNTRACKED files under the package, which is the case that matters most: an
 *  untracked `Sneaky.tsx` would be written into every site with nothing in any
 *  commit to explain it. */
function uncommitted(hub, pkgDir) {
  // NOT `tryGit`: that trims, and porcelain's first column is a status character
  // that is often a space. Trimming the whole output shifts every line left by
  // one and `slice(3)` then reports `ackages/...` for `packages/...` — a path
  // that does not exist, in the one message that has to name the real file.
  const raw = tryGitRaw(hub, ["status", "--porcelain", "--", pkgDir]);
  if (raw === null) return [];
  return raw
    .split("\n")
    .filter((line) => line.trim().length)
    .map((line) => {
      // Porcelain v1: two status columns, one space, then the path.
      const p = line.slice(3).trim();
      // A rename reads `old -> new`; the new name is the one on disk now.
      return p.includes(" -> ") ? p.split(" -> ").pop() : p;
    })
    .map((p) => p.replace(/^"|"$/g, ""));
}

/** Everything known about `hub`, as data. `ok` is the verdict; `findings` is the
 *  whole picture behind it, so a refusal can print everything it found rather
 *  than the first thing it tripped on.
 *
 *  `pkgDir` is the package path relative to the hub, passed in rather than
 *  guessed: deciding what is shipped is ui-package.mjs's business, and this file
 *  asks git about a path it is told about. */
export function inspectHubSource(hub, { pkgDir = "packages/predictor-ui" } = {}) {
  const findings = [];

  const inside = tryGit(hub, ["rev-parse", "--is-inside-work-tree"]);
  if (inside !== "true") {
    findings.push({
      code: "NOT_A_REPO",
      text: `${hub} is not a git working tree, so there is nothing to compare it against; this checkout cannot be vouched for`,
    });
    return { hub, ok: false, findings };
  }

  const head = short(hub, "HEAD");
  if (head === null) {
    findings.push({ code: "UNREADABLE", text: `${hub} is a git repository but HEAD could not be read` });
    return { hub, ok: false, findings };
  }

  // `symbolic-ref` exits non-zero on a detached HEAD, which is the answer, not an
  // error: an empty result here means "not on a branch".
  const branch = tryGit(hub, ["symbolic-ref", "--quiet", "--short", "HEAD"]);
  const dirty = uncommitted(hub, pkgDir);
  const originMain = short(hub, "origin/main");

  if (branch === null) {
    findings.push({
      code: "DETACHED",
      text:
        `HEAD is detached at ${head}, so this checkout cannot be attributed to a branch. ` +
        `A detached HEAD is how two of the three branches that hit this defect worked around it, ` +
        `which is a point in its favour — but it should be a decision, not a default. ` +
        `Check out main, or pass --from ${head} to say you mean this commit`,
    });
  } else if (branch !== "main") {
    findings.push({
      code: "NOT_MAIN",
      text:
        `this checkout is on branch ${branch}, not main. ` +
        `A branch does not carry the components merged since it was cut — ` +
        `this is the state that deleted InstantBlock and bundleFacts from a site — ` +
        `and nothing in the vendored bytes gives the branch away, because a docs branch ` +
        `usually vendors identically to main. Check out main, or pass --from ${branch} to name this commit`,
    });
  }

  if (dirty.length) {
    findings.push({
      code: "DIRTY",
      text:
        `the package has uncommitted changes under ${pkgDir}: ${dirty.join(", ")}. ` +
        `A vendored copy would carry bytes no commit accounts for, so the site and the repo ` +
        `would disagree about what predictor-ui is with nothing to reconcile them. ` +
        `Commit or stash: git -C ${hub} status --porcelain -- ${pkgDir}`,
    });
  }

  if (originMain === null) {
    // Tri-state, not a boolean, and deliberately not folded into "clean": a
    // never-fetched checkout has no origin/main, and treating that as "current"
    // is the one answer that must never be given by accident.
    findings.push({
      code: "NO_ORIGIN",
      text:
        `${hub} has no origin/main ref (HEAD is ${head}), so there is no way to know whether it is ` +
        `current — and "cannot tell" must not be reported as "fine". Run: git -C ${hub} fetch origin`,
    });
  } else {
    const behind = distance(hub, "HEAD..origin/main") ?? 0;
    const ahead = distance(hub, "origin/main..HEAD") ?? 0;
    if (behind > 0) {
      findings.push({
        code: "BEHIND",
        text:
          `this checkout is ${behind} commit${behind === 1 ? "" : "s"} BEHIND origin/main ` +
          `(HEAD ${head}, origin/main ${originMain}). The package here is missing everything merged ` +
          `since, so vendoring from it deletes components the site is supposed to have. ` +
          `Fix: git -C ${hub} checkout main && git -C ${hub} pull --ff-only`,
      });
    }
    if (ahead > 0) {
      findings.push({
        code: "AHEAD",
        text:
          `this checkout is ${ahead} commit${ahead === 1 ? "" : "s"} AHEAD of origin/main ` +
          `(HEAD ${head}, origin/main ${originMain}), so the bytes it would vendor are ones no other ` +
          `checkout can reproduce. Push, or check out origin/main`,
      });
    }
  }

  return { hub, ok: findings.length === 0, findings, head, branch, originMain, dirty };
}

/** The whole picture as text: what was found, and what to do about each thing.
 *  Used in a refusal, so it must stand alone — a message that names a problem
 *  without a remedy makes the reader go and ask a person. */
export function reportFindings(report) {
  const lines = [`Refusing to vendor from ${report.hub}.`, ""];
  for (const f of report.findings) lines.push(`  ${f.code}: ${f.text}`);
  lines.push(
    "",
    "Every one of these is a state of the CHECKOUT, not of the package's bytes — two checkouts",
    "can vendor identical files and one of them still be the wrong one to vendor from.",
    "",
    "How to proceed:",
    "  * point at a checkout of main that is clean:  git -C <hub> checkout main",
    "  * or name the commit you mean:                --from <sha>",
    "  * or name another checkout entirely:          --from <path-to-hub>",
    "  * or say you know and vendor anyway:          --vendor-anyway",
  );
  return lines.join("\n");
}

/** Resolve `--from` to a package directory, or explain why it cannot be.
 *
 *  Two shapes, decided by what exists on disk rather than by guessing at the
 *  string: a directory is a checkout to read, anything else is a commit this
 *  checkout is or is not at. A `--from` that resolved to the wrong one of those
 *  would either read a file called `main` as a revision or silently ignore the
 *  flag. */
export function resolveSource({ from, hub, pkgDir = "packages/predictor-ui" }) {
  if (existsSync(from)) {
    const src = join(resolve(from), pkgDir, "src");
    if (!existsSync(src)) {
      return {
        error:
          `--from ${from} is a directory, but it has no ${pkgDir}/src, so there is no package there to ` +
          `vendor. Point --from at a predictor-hub checkout (the directory holding scripts/ and ${pkgDir}/)`,
      };
    }
    return { src, hub: resolve(from) };
  }
  const head = short(hub, "HEAD");
  if (tryGit(hub, ["rev-parse", "--verify", "--quiet", `${from}^{commit}`]) === null) {
    return {
      error: `--from ${from} is neither a directory nor a commit in ${hub}. It must be a hub checkout path, or a revision this checkout has`,
    };
  }
  if (from !== head && !head?.startsWith(from) && !from.startsWith(head ?? "")) {
    return {
      error:
        `--from ${from} names a commit, but this checkout (${hub}) is at ${head}. Naming a commit ` +
        `this checkout is not at would vendor the files on disk under a label they do not carry, ` +
        `which is the same lie as the defect. Check out ${from}, or --from <path-to-a-checkout-at-it>`,
    };
  }
  // Same checkouts, named: a named commit IS a decision, so the branch,
  // detached and distance findings are settled. DIRTY is not, and NO_ORIGIN is
  // not — a named commit is not the bytes on disk, and there may still be no way
  // to tell whether those bytes are current.
  return { src: null, hub, namedCommit: true };
}
