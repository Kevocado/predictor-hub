#!/usr/bin/env node
// Vendor packages/predictor-ui/src into a site:  node scripts/sync-ui.mjs <site-src-dir>
// Verify a site's copy is untouched:             node scripts/sync-ui.mjs --check <site-src-dir>
//
// Each site builds from its own repo on the VPS, so the shared package is
// copied in rather than installed. Every copied file starts with a
// do-not-edit header, and SYNC.json records a sha256 per file so a hand edit
// in a site fails --check (wire it into the site's tests).
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
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

function hubRevision() {
  try {
    return execFileSync("git", ["-C", HUB, "rev-parse", "--short", "HEAD"], { encoding: "utf8" }).trim();
  } catch {
    return "unknown";
  }
}

function header(file, rev) {
  const text = `Synced from predictor-hub@${rev}. Do not edit here: change packages/predictor-ui and re-run scripts/sync-ui.mjs.`;
  return file.endsWith(".css") ? `/* ${text} */\n` : `// ${text}\n`;
}

function sync(siteSrc) {
  const out = join(siteSrc, "predictor-ui");
  rmSync(out, { recursive: true, force: true });
  const rev = hubRevision();
  const files = {};
  for (const file of walk(SRC).filter(isShipped).sort()) {
    const rel = relative(SRC, file).split("\\").join("/");
    const body = header(rel, rev) + readFileSync(file, "utf8");
    mkdirSync(dirname(join(out, rel)), { recursive: true });
    writeFileSync(join(out, rel), body);
    files[rel] = sha256(body);
  }
  writeFileSync(join(out, "SYNC.json"), JSON.stringify({ source: `predictor-hub@${rev}`, files }, null, 2) + "\n");
  console.log(`Synced ${Object.keys(files).length} files into ${out} from predictor-hub@${rev}`);
}

function check(siteSrc) {
  const out = join(siteSrc, "predictor-ui");
  const manifestPath = join(out, "SYNC.json");
  if (!existsSync(manifestPath)) {
    console.error(`No ${manifestPath}; run sync first.`);
    return 1;
  }
  const { files } = JSON.parse(readFileSync(manifestPath, "utf8"));
  const drifted = Object.entries(files).filter(([rel, hash]) => {
    const p = join(out, rel);
    return !existsSync(p) || sha256(readFileSync(p, "utf8")) !== hash;
  });
  if (drifted.length) {
    console.error(`predictor-ui was edited in this site (change it in predictor-hub instead): ${drifted.map(([rel]) => rel).join(", ")}`);
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
