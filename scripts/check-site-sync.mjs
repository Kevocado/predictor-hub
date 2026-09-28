#!/usr/bin/env node
// Is every registered site's vendored copy the current one?
//   node scripts/check-site-sync.mjs
//
// Each site builds from its own repo on the VPS, so `packages/predictor-ui` is
// copied into it rather than installed, and every site runs its own drift test
// over that copy. Those tests are worth having and they are not enough: each
// one recomputes every file's sha256 against the site's **own** SYNC.json, so
// it catches a hand edit and is structurally blind to upstream staleness. Both
// `sync-ui.mjs --check` and the site tests destructure only the `files` key;
// `source` is never read. That is how four sites sat at
// `predictor-ui@e4f15576b8e0` while hub `main` was at
// `predictor-ui@9c14c67d91df`, with every suite in every repo green.
//
// So the check belongs here, in the hub, because this is the only place where
// both halves of the pair are visible: the package, and the list of sites.
//
// It must not go in a site. A site cannot know what "current" is: the value is
// a content hash of a repository the site does not have, and it moves on every
// unrelated commit to the package. A site-side guard therefore needs a second
// copy of the expected value, maintained by hand, and it fires on every
// legitimate change across every consumer at the same moment. That is a
// nuisance alarm, and a nuisance alarm is muted — which is the same failure
// this script exists to end.
//
// Outcomes, and they are not the same thing:
//
//   current     the site reads exactly the version this checkout writes.
//   stale       the site is behind, and the fix is a sync PR.
//   unreadable  the manifest could not be read. Never a pass: a check that
//               could not run must not look like one that passed, so this
//               fails the run even while stale sites are only warning.
//
// Stale is a warning rather than a failure while ENFORCE_SITE_SYNC is unset,
// because adoption is a migration: at the first run every site is behind, and a
// check that lands red on main is a check nobody reads. Flip
// ENFORCE_SITE_SYNC to "1" in .github/workflows/site-sync-check.yml once every
// registered site reads the current version — the warning says so itself, and
// the failure output says what to sync.
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { currentSource } from "./ui-package.mjs";

/** Where a site's vendored copy lives, and the manifest that names it.
 *
 * Measured from the repos, not remembered: in each, and in each *default*
 * branch,
 *
 *     git ls-tree -r --name-only origin/main | grep 'predictor-ui/SYNC.json'
 *
 * A site missing from this list is a site nobody checks, and the failure mode
 * of a missing entry is silence. `NFL_Predictor` and `CFB_Predictor` are
 * deliberately absent: they are the API repos behind the Sports site, vendor no
 * frontend, and have no `predictor-ui/` tree at all. Adding a site means adding
 * it here with the path `git ls-tree` reports, and opening a PR — the entry is
 * the whole guard.
 */
export const SITES = [
  { repo: "Kevocado/PL_Predictor", manifest: "frontend/src/predictor-ui/SYNC.json" },
  { repo: "Kevocado/Sports_Predictor", manifest: "src/predictor-ui/SYNC.json" },
  { repo: "Kevocado/NBA_Predictor", manifest: "frontend/src/predictor-ui/SYNC.json" },
  { repo: "Kevocado/F1_Predictor", manifest: "frontend/src/predictor-ui/SYNC.json" },
];

/** The ref a site is read at.
 *
 * `main`, for every site, because that is what each one builds from on the VPS.
 * Reading any other ref to make this green would be the check lying: PL and
 * Sports both reach the current version on their open `v2-wire` branches, and
 * the sites go green here when those branches merge, not before.
 */
export const DEFAULT_REF = "main";

export const CURRENT = "current";
export const STALE = "stale";
export const UNREADABLE = "unreadable";

const MANIFEST_SOURCE = /^predictor-ui@[0-9a-f]{12}$/;

/** The class of "could not read the manifest", kept apart from every other
 * throw so a network error and a missing file read the same way to a caller. */
class ManifestError extends Error {}

/** A site's `source`, or a throw. Nothing here returns a usable value on a
 * partial read: a manifest with no `source`, or one that is not JSON, is not a
 * site that is current, it is a site that was not checked. */
export function manifestSource(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (cause) {
    throw new ManifestError(`SYNC.json is not JSON: ${cause.message}`);
  }
  const source = parsed?.source;
  if (typeof source !== "string" || !MANIFEST_SOURCE.test(source)) {
    throw new ManifestError(`SYNC.json has no usable 'source' (got ${JSON.stringify(source)})`);
  }
  return source;
}

/** The manifest's text at a ref, or a throw naming why not. */
export async function readManifest({ site, ref, token, fetchImpl }) {
  const url = `https://api.github.com/repos/${site.repo}/contents/${site.manifest}?ref=${encodeURIComponent(ref)}`;
  const res = await fetchImpl(url, {
    headers: {
      authorization: `Bearer ${token}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      "user-agent": "predictor-hub-site-sync-check",
    },
  });
  if (!res.ok) {
    // The API's own `message` is the useful half: "Not Found" for a wrong path
    // or a private repo, "This API returns blobs up to 1 MB" for something else.
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.message) detail += ` ${body.message}`;
    } catch { /* an error body that is not JSON is not worth failing twice over */ }
    throw new ManifestError(detail);
  }
  const body = await res.json();
  if (body?.type !== "file" || body?.encoding !== "base64" || typeof body?.content !== "string") {
    throw new ManifestError(`expected a file, got ${JSON.stringify(body?.type)}`);
  }
  return Buffer.from(body.content, "base64").toString("utf8");
}

/** One site, one verdict. Never throws: an unreadable site is a result. */
export async function checkSite(site, { ref = DEFAULT_REF, token, fetchImpl, want }) {
  const row = { repo: site.repo, ref, manifest: site.manifest, want, have: null, status: UNREADABLE, detail: "" };
  try {
    row.have = manifestSource(await readManifest({ site, ref, token, fetchImpl }));
    row.status = row.have === want ? CURRENT : STALE;
  } catch (err) {
    row.detail = err instanceof ManifestError ? err.message : `${type(err).__name__}: ${err.message}`;
  }
  return row;
}

// The vendored folder's parent, so the warning can say what to sync rather
// than only that something is wrong: `frontend/src/predictor-ui/SYNC.json` →
// `frontend/src`, which is what `sync-ui.mjs` takes.
const siteSrcDir = (site) => dirname(dirname(site.manifest));

/** Run it. Returns `{ code, rows, want, skipped }`; `code` is the exit code. */
export async function main({
  env = process.env,
  out = (line) => console.log(line),
  fetchImpl = fetch,
  sites = SITES,
  want = currentSource(),
  enforce = env.ENFORCE_SITE_SYNC === "1",
} = {}) {
  const say = (line = "") => out(line);
  const warn = (title, message) => say(`::warning title=${title}::${message}`);
  const error = (title, message) => say(`::error title=${title}::${message}`);
  const pad = (text, width) => String(text).padEnd(width);

  // In preference order. All six site repos are public, so an anonymous read
  // works (verified: curl with no Authorization header returns 200), and
  // Actions provides GITHUB_TOKEN to every job. A token is still required
  // rather than optional, because anonymous requests are capped at 60 an hour
  // per IP and Actions runners share IPs — a run that 403s for a reason
  // unrelated to staleness turns this into a flaky check.
  //
  // `SITE_REPOS_TOKEN` is the escape hatch and nothing more: an installation
  // token is scoped to this repository, and whether GitHub honours one for a
  // *different* public repository is not something a local run can answer. If
  // the job reports every site unreadable, put a token with `contents: read`
  // on the site repos into the repository secret `SITE_REPOS_TOKEN` and this
  // picks it up with nothing else changed.
  const token = env.SITE_REPOS_TOKEN || env.GITHUB_TOKEN || env.GH_TOKEN;
  if (!token) {
    // Loud, and explicitly not a pass. Actions provides GITHUB_TOKEN to every
    // job, so this fires in local runs and in any future non-Actions runner —
    // which is exactly when a silent pass would be believed.
    const reason = "no credential to read the site repositories with: SITE_REPOS_TOKEN, "
      + "GITHUB_TOKEN and GH_TOKEN are all unset. Nothing was compared: this is a skip, not a "
      + "pass. In GitHub Actions GITHUB_TOKEN is provided automatically; locally, run "
      + "SITE_REPOS_TOKEN=$(gh auth token) node scripts/check-site-sync.mjs.";
    warn("Vendored UI freshness SKIPPED", reason);
    say(`site-sync: SKIPPED — 0 of ${sites.length} sites compared. ${reason}`);
    return { code: 0, rows: [], want, skipped: reason };
  }

  const rows = [];
  for (const site of sites) {
    rows.push(await checkSite(site, { ref: site.ref ?? DEFAULT_REF, token, fetchImpl, want }));
  }

  const behind = rows.filter((r) => r.status === STALE);
  const broken = rows.filter((r) => r.status === UNREADABLE);
  const fresh = rows.filter((r) => r.status === CURRENT);

  say();
  say(`The hub's packages/predictor-ui, as of this commit: ${want}`);
  say();
  const widths = { repo: 0, ref: 0, have: 0 };
  for (const r of rows) {
    widths.repo = Math.max(widths.repo, r.repo.length);
    widths.ref = Math.max(widths.ref, r.ref.length);
    widths.have = Math.max(widths.have, (r.have ?? "—").length);
  }
  say(`  ${pad("site", widths.repo)}  ${pad("ref", widths.ref)}  ${pad("site has", widths.have)}  state`);
  for (const r of rows) {
    const state = r.status === UNREADABLE ? `UNREADABLE — ${r.detail}` : r.status;
    say(`  ${pad(r.repo, widths.repo)}  ${pad(r.ref, widths.ref)}  ${pad(r.have ?? "—", widths.have)}  ${state}`);
  }
  say();

  // Unreadable is a hard failure in both modes. It is the difference between
  // "the sites are current" and "nobody found out", and a check that reports
  // the second as the first is worse than no check.
  for (const r of broken) {
    error(`Vendored UI unreadable — ${r.repo}`,
      `Could not read ${r.manifest} at ${r.ref} — ${r.detail}. This is not a pass. `
      + "Check the path in scripts/check-site-sync.mjs's SITES, that the ref exists, "
      + "and that the token can read the repo (a 401 means the credential is present and "
      + "wrong; a 404 usually means the path or the repo).");
  }
  if (broken.length) {
    say(`site-sync: FAIL — ${broken.length} of ${rows.length} sites could not be read, so this run checked nothing about them.`);
    return { code: 1, rows, want, skipped: null };
  }

  if (!behind.length) {
    say(`site-sync: PASS — ${fresh.length} of ${rows.length} sites are at ${want}.`);
    return { code: 0, rows, want, skipped: null };
  }

  for (const r of behind) {
    const site = sites.find((s) => s.repo === r.repo);
    warn(`Vendored UI behind — ${r.repo}`,
      `Vendored from ${r.have}, the hub is at ${want}. The site's own drift test cannot see this — `
      + `it compares the copy against the site's own SYNC.json. Re-vendor and open a PR: `
      + `node scripts/sync-ui.mjs <checkout>/${siteSrcDir(site)}`);
  }
  if (enforce) {
    say(`site-sync: FAIL — ${behind.length} of ${rows.length} sites are behind the hub.`);
    return { code: 1, rows, want, skipped: null };
  }
  say(`site-sync: BEHIND — ${behind.length} of ${rows.length} sites are behind, reported as a warning.`);
  say("This is the migration state, not a pass: adoption is a migration, and a check that lands");
  say("red on main is a check nobody reads. Re-vendor each site above (one PR each), then set");
  say('ENFORCE_SITE_SYNC: "1" in .github/workflows/site-sync-check.yml. Until then this warns and');
  say("cannot fail the build — which also means it cannot catch a site falling behind after today.");
  return { code: 0, rows, want, skipped: null };
}

const invokedDirectly = process.argv[1]
  && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedDirectly) {
  process.exit((await main()).code);
}
