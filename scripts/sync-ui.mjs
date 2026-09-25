#!/usr/bin/env node
// Vendor packages/predictor-ui/src into a site:  node scripts/sync-ui.mjs <site-src-dir>
// Verify a site's copy is untouched:             node scripts/sync-ui.mjs --check <site-src-dir>
//
// Each site builds from its own repo on the VPS, so the shared package is
// copied in rather than installed. Every copied file starts with a
// do-not-edit header, and SYNC.json records a sha256 per file so a hand edit
// in a site fails --check (wire it into the site's tests).
import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(HUB, "packages", "predictor-ui", "src");
const sha256 = (text) => createHash("sha256").update(text).digest("hex");

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

const isShipped = (file) => /\.(ts|tsx|css)$/.test(file) && !/\.test\.(ts|tsx)$/.test(file);

// LF everywhere, so a Windows (CRLF) checkout hashes the same as the VPS.
const read = (file) => readFileSync(file, "utf8").replace(/\r\n/g, "\n");

// Stamp a hash of the package's own contents (not the hub commit): a sync
// from an unchanged package is byte-identical, and uncommitted edits can't
// masquerade as a clean commit.
function contentVersion(files) {
  const h = createHash("sha256");
  for (const file of files) h.update(relative(SRC, file).split("\\").join("/")).update("\0").update(read(file)).update("\0");
  return h.digest("hex").slice(0, 12);
}

function header(file, rev) {
  const text = `Synced from predictor-ui@${rev}. Do not edit here: change predictor-hub/packages/predictor-ui and re-run scripts/sync-ui.mjs.`;
  return file.endsWith(".css") ? `/* ${text} */\n` : `// ${text}\n`;
}

function sync(siteSrc) {
  const out = join(siteSrc, "predictor-ui");
  rmSync(out, { recursive: true, force: true });
  const shipped = walk(SRC).filter(isShipped).sort();
  const rev = contentVersion(shipped);
  const files = {};
  for (const file of shipped) {
    const rel = relative(SRC, file).split("\\").join("/");
    const body = header(rel, rev) + read(file);
    mkdirSync(dirname(join(out, rel)), { recursive: true });
    writeFileSync(join(out, rel), body);
    files[rel] = sha256(body);
  }
  writeFileSync(join(out, "SYNC.json"), JSON.stringify({ source: `predictor-ui@${rev}`, files }, null, 2) + "\n");
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
