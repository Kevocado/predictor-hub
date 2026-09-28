// The shipped file set of packages/predictor-ui, and the content hash that
// names it.
//
// Two callers, and they must not have their own copy: `sync-ui.mjs` writes the
// hash into each site's SYNC.json as `source`, and `check-site-sync.mjs` reads
// those manifests back and compares them against the same hash. A second
// implementation here would not fail loudly — it would drift from the writer
// by one changed line, and the checker would go on comparing every site
// against a number nothing ever writes, which is green forever and means
// nothing. One implementation, imported by both.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const HUB = join(dirname(fileURLToPath(import.meta.url)), "..");
export const SRC = join(HUB, "packages", "predictor-ui", "src");

export const sha256 = (text) => createHash("sha256").update(text).digest("hex");

export function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

export const isShipped = (file) => /\.(ts|tsx|css)$/.test(file) && !/\.test\.(ts|tsx)$/.test(file);

// LF everywhere, so a Windows (CRLF) checkout hashes the same as the VPS.
export const read = (file) => readFileSync(file, "utf8").replace(/\r\n/g, "\n");

// The vendor set, sorted so the hash does not depend on readdir order.
export const shippedFiles = (src = SRC) => walk(src).filter(isShipped).sort();

// Stamp a hash of the package's own contents (not the hub commit): a sync
// from an unchanged package is byte-identical, and uncommitted edits can't
// masquerade as a clean commit.
export function contentVersion(files, src = SRC) {
  const h = createHash("sha256");
  for (const file of files) h.update(relative(src, file).split("\\").join("/")).update("\0").update(read(file)).update("\0");
  return h.digest("hex").slice(0, 12);
}

// The string that goes in SYNC.json's `source`, and the one the checker
// compares it against. `src` is a parameter so a test can hash a throwaway
// package; nothing but tests passes it.
export const sourceFor = (files, src = SRC) => `predictor-ui@${contentVersion(files, src)}`;

// What this checkout of the package is, right now.
export const currentSource = () => sourceFor(shippedFiles());
