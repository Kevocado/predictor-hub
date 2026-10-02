#!/usr/bin/env node
// Vendor packages/predictor-ui/src into a site:  node scripts/sync-ui.mjs <site-src-dir>
// Verify a site's copy is untouched:             node scripts/sync-ui.mjs --check <site-src-dir>
//
// It refuses to vendor from a hub checkout it cannot vouch for, and refuses to
// delete a file the site already has and the source no longer ships. Both
// refusals are overridable, explicitly, by a flag that names the decision:
//
//   --from <path|sha>    vendor from a named checkout, or at a named commit
//   --vendor-anyway      the checkout is not main/clean/current; I know
//   --allow-deletions    the source no longer ships a file the site has; delete it
//
// Each site builds from its own repo on the VPS, so the shared package is
// copied in rather than installed. Every copied file starts with a
// do-not-edit header, and SYNC.json records a sha256 per file so a hand edit
// in a site fails --check (wire it into the site's tests).
import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { HUB, SRC, contentVersion, read, sha256, shippedFiles, sourceFor, walk } from "./ui-package.mjs";
import { inspectHubSource, reportFindings, resolveSource } from "./hub-source.mjs";

// The shipped-file set and the hash that names it live in ui-package.mjs,
// because check-site-sync.mjs compares every site against the same number this
// writes into SYNC.json. Two copies would drift apart by a changed line, and
// the checker would go on comparing sites against a value nothing produces —
// green forever, and meaningless.
//
// The git-state guards live in hub-source.mjs for the same reason: one reading
// of "is this checkout safe to vendor from", so it cannot differ between the
// path that refuses and the path that does not.

const USAGE = [
  "usage:",
  "  node scripts/sync-ui.mjs [--from <path|sha>] [--vendor-anyway] [--allow-deletions] <site-src-dir>",
  "  node scripts/sync-ui.mjs --check <site-src-dir>",
  "",
  "  --from <path|sha>     vendor from another hub checkout, or at a named commit",
  "  --vendor-anyway        vendor even though the hub checkout is not clean main at origin/main",
  "  --allow-deletions      delete site files the source no longer ships (named individually)",
  "  --check                verify a site's copy is untouched; reads no hub state",
];

function header(file, rev) {
  const text = `Synced from predictor-ui@${rev}. Do not edit here: change predictor-hub/packages/predictor-ui and re-run scripts/sync-ui.mjs.`;
  return file.endsWith(".css") ? `/* ${text} */\n` : `// ${text}\n`;
}

/** What the site has in its vendored folder now: every file, not just the ones
 *  its own manifest names.
 *
 *  The manifest alone is not enough — `sync` removes the folder outright, so a
 *  file someone added by hand is destroyed just as silently as a recorded one,
 *  and with nothing in SYNC.json to give the deletion a name. */
function vendoredFiles(out) {
  if (!existsSync(out)) return [];
  return walk(out).map((f) => relative(out, f).split("\\").join("/"));
}

/** Files the site has that the source does not ship. These are the ones the
 *  write would delete.
 *
 *  SYNC.json is excluded: it is rewritten, not removed. */
function deletions(out, shippedRel) {
  return vendoredFiles(out).filter((rel) => rel !== "SYNC.json" && !shippedRel.has(rel));
}

function sync(siteSrc, { src, opts }) {
  const out = join(siteSrc, "predictor-ui");
  const shipped = shippedFiles(src);
  const shippedRel = new Set(shipped.map((f) => relative(src, f).split("\\").join("/")));

  // Before anything is written. `rmSync` below is unconditional, so this is the
  // only place a deletion can still be stopped.
  const lost = deletions(out, shippedRel);
  if (lost.length && !opts.allowDeletions) {
    console.error(
      `Refusing to delete ${lost.length} file${lost.length === 1 ? "" : "s"} this site already vendors, ` +
        `which the source does not ship:\n${lost.map((f) => `  ${f}`).join("\n")}\n\n` +
        `This is how InstantBlock and bundleFacts left a site once already: a source without them,\n` +
        `and a sync that said nothing. A stale hub is the usual reason and the source guard below\n` +
        `would catch it, but a deliberate removal is a legitimate reason too — so this needs a\n` +
        `decision, not a guess:\n\n` +
        `  * if the removal is intended: --allow-deletions (each file is named above, and again on success)\n` +
        `  * if it is not: fix the source, or --from <path|sha> to vendor from a checkout that has the files\n\n` +
        `Nothing was written. The site is exactly as it was.`,
    );
    return 1;
  }
  if (lost.length) {
    console.error(
      `--allow-deletions: deleting ${lost.length} file${lost.length === 1 ? "" : "s"} from ${out}: ` +
        lost.join(", "),
    );
  }

  rmSync(out, { recursive: true, force: true });
  const rev = contentVersion(shipped, src);
  const files = {};
  for (const file of shipped) {
    const rel = relative(src, file).split("\\").join("/");
    const body = header(rel, rev) + read(file);
    mkdirSync(dirname(join(out, rel)), { recursive: true });
    writeFileSync(join(out, rel), body);
    files[rel] = sha256(body);
  }
  writeFileSync(join(out, "SYNC.json"), JSON.stringify({ source: sourceFor(shipped, src), files }, null, 2) + "\n");
  console.log(`Synced ${Object.keys(files).length} files into ${out} (predictor-ui@${rev})`);
  if (opts.from) console.log(`  source: ${src} (named with --from ${opts.from})`);
  return 0;
}

function check(siteSrc) {
  const out = join(siteSrc, "predictor-ui");
  const manifestPath = join(out, "SYNC.json");
  if (!existsSync(manifestPath)) {
    console.error(`No ${manifestPath}; run sync first.`);
    return 1;
  }
  const { files } = JSON.parse(readFileSync(manifestPath, "utf8"));
  const drifted = Object.entries(files)
    .filter(([rel, hash]) => {
      const p = join(out, rel);
      return !existsSync(p) || sha256(read(p)) !== hash;
    })
    .map(([rel]) => rel);
  // Files added by hand inside the vendored folder are drift too.
  const extra = walk(out)
    .map((file) => relative(out, file).split("\\").join("/"))
    .filter((rel) => rel !== "SYNC.json" && !(rel in files));
  const problems = [...drifted, ...extra];
  if (problems.length) {
    console.error(`predictor-ui was edited in this site (change it in predictor-hub instead): ${problems.join(", ")}`);
    return 1;
  }
  return 0;
}

/** Parse argv into options and a site path. An unrecognised flag is an error
 *  rather than something to skip past, because the old code's `else` branch made
 *  `--force` look like a site path: the flag was dropped, the run continued, and
 *  the thing the flag was supposed to prevent happened with a flag in the shell
 *  history saying otherwise. */
function parse(argv) {
  const opts = { from: null, vendorAnyway: false, allowDeletions: false };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--check" || arg === "--check=true") opts.check = true;
    else if (arg === "--vendor-anyway") opts.vendorAnyway = true;
    else if (arg === "--allow-deletions") opts.allowDeletions = true;
    else if (arg === "--from") {
      if (i + 1 >= argv.length) return { error: "--from needs a path or a commit: --from <path|sha>" };
      opts.from = argv[++i];
    } else if (arg.startsWith("--from=")) opts.from = arg.slice("--from=".length);
    else if (arg.startsWith("-")) return { error: `unknown flag ${arg}` };
    else rest.push(arg);
  }
  if (opts.check) {
    if (rest.length !== 1) return { error: "--check takes exactly one site src dir" };
    return { opts, siteSrc: rest[0] };
  }
  if (rest.length !== 1) return { error: "expected exactly one site src dir" };
  return { opts, siteSrc: rest[0] };
}

/** Judge the checkout, unless the caller named a commit or waved it through.
 *
 *  Order matters for the reader: findings first, then the override that was used
 *  (or not). A refusal that does not say whether an override was available reads
 *  as "this is impossible" rather than "this is a decision". */
function guardSource(opts) {
  if (opts.from === null) {
    const report = inspectHubSource(HUB);
    if (report.ok) return { hub: HUB };
    if (opts.vendorAnyway) {
      console.error(
        `--vendor-anyway: overriding ${report.findings.length} finding(s) about ${HUB}:\n` +
          report.findings.map((f) => `  ${f.code}: ${f.text}`).join("\n") +
          `\n\nVendored from ${HUB} anyway, on request. If it was not main, this may have deleted\n` +
          `components the site should have.`,
      );
      return { hub: HUB };
    }
    console.error(reportFindings(report));
    console.error("\nOr: --vendor-anyway, to override every finding above at once.");
    return { error: true };
  }
  const resolved = resolveSource({ from: opts.from, hub: HUB });
  if (resolved.error) return { error: resolved.error };
  // A named commit settles which bytes; the tree can still be dirty and there can
  // still be no origin/main, and neither is answered by naming a revision.
  const report = inspectHubSource(resolved.hub);
  // ONLY a named commit settles anything. A `--from <path>` is a location, not a
  // decision: it says where to read and nothing about whether what is there is
  // current, so it settles none of these. Filtering them for a path was the
  // original defect one indirection away -- point --from at a checkout on a docs
  // branch and it vendored silently, which is exactly the state that deleted
  // InstantBlock and bundleFacts from a site.
  const unsettled = resolved.namedCommit
    ? report.findings.filter((f) => !SETTLED_BY_A_NAMED_COMMIT.has(f.code))
    : report.findings;
  if (unsettled.length && !opts.vendorAnyway) {
    const filtered = { ...report, findings: unsettled };
    console.error(reportFindings(filtered));
    return { error: true };
  }
  if (unsettled.length) {
    console.error(
      `--vendor-anyway: overriding ${unsettled.length} finding(s) that naming commit ${opts.from} does not answer:\n` +
        unsettled.map((f) => `  ${f.code}: ${f.text}`).join("\n"),
    );
  }
  return { hub: resolved.hub, src: resolved.src ?? undefined };
}

/** Findings a `--from <sha>` settles by itself: the caller has said which commit,
 *  so which branch it sits on, whether it is detached and how far it is from
 *  origin/main are all answered. The two that are not are `DIRTY` (a named
 *  commit is not the bytes on disk) and `NO_ORIGIN` (naming a revision says
 *  nothing about whether there is a remote to compare it to).
 *
 *  Settles only when a COMMIT was named. `--from <path>` does not use this set:
 *  a path is where to read, not which commit, so it answers none of them. */
const SETTLED_BY_A_NAMED_COMMIT = new Set(["DETACHED", "NOT_MAIN", "BEHIND", "AHEAD"]);

const args = process.argv.slice(2);
const parsed = parse(args);
if (parsed.error) {
  console.error(parsed.error);
  for (const line of USAGE) console.error(line);
  process.exit(2);
}

// `--check` reads no hub state: it compares the site against the site's own
// manifest, so it must keep working in a checkout too dirty to vendor from —
// that is exactly when someone needs to ask what the site currently holds.
if (parsed.opts.check) process.exit(check(parsed.siteSrc));

const src = parsed.opts.from === null ? SRC : undefined;
const guarded = guardSource(parsed.opts);
if (guarded.error) {
  if (guarded.error !== true) console.error(guarded.error);
  process.exit(1);
}
process.exit(
  sync(parsed.siteSrc, {
    src: guarded.src ?? src ?? SRC,
    opts: parsed.opts,
  }),
);
