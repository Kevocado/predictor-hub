#!/usr/bin/env node
// Vendor packages/predictor-ui/src into a site:  node scripts/sync-ui.mjs <site-src-dir>
// Verify a site's copy is untouched:             node scripts/sync-ui.mjs --check <site-src-dir>
//
// Each site builds from its own repo on the VPS, so the shared package is
// copied in rather than installed. Every copied file starts with a
// do-not-edit header, and SYNC.json records a sha256 per file so a hand edit
// in a site fails --check (wire it into the site's tests).
import { mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { SRC, contentVersion, read, sha256, shippedFiles, sourceFor, walk } from "./ui-package.mjs";

// The shipped-file set and the hash that names it live in ui-package.mjs,
// because check-site-sync.mjs compares every site against the same number this
// writes into SYNC.json. Two copies would drift apart by a changed line, and
// the checker would go on comparing sites against a value nothing produces —
// green forever, and meaningless.

function header(file, rev) {
  const text = `Synced from predictor-ui@${rev}. Do not edit here: change predictor-hub/packages/predictor-ui and re-run scripts/sync-ui.mjs.`;
  return file.endsWith(".css") ? `/* ${text} */\n` : `// ${text}\n`;
}

function sync(siteSrc) {
  const out = join(siteSrc, "predictor-ui");
  rmSync(out, { recursive: true, force: true });
  const shipped = shippedFiles();
  const rev = contentVersion(shipped);
  const files = {};
  for (const file of shipped) {
    const rel = relative(SRC, file).split("\\").join("/");
    const body = header(rel, rev) + read(file);
    mkdirSync(dirname(join(out, rel)), { recursive: true });
    writeFileSync(join(out, rel), body);
    files[rel] = sha256(body);
  }
  writeFileSync(join(out, "SYNC.json"), JSON.stringify({ source: sourceFor(shipped), files }, null, 2) + "\n");
  console.log(`Synced ${Object.keys(files).length} files into ${out} (predictor-ui@${rev})`);
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

const args = process.argv.slice(2);
if (args[0] === "--check" && args[1]) process.exit(check(args[1]));
if (args[0] && !args[0].startsWith("--")) sync(args[0]);
else {
  console.error("usage: sync-ui.mjs <site-src-dir> | --check <site-src-dir>");
  process.exit(2);
}
