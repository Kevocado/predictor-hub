import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

const caddy = readFileSync(new URL("../Caddyfile", import.meta.url), "utf8");

// The hub is a static page on the bare domain with a root + file_server block
// and no proxy, so a page there cannot read the sport subdomains. These five
// prefixes are what make the picks teasers possible.
const PROXIES = [
  ["/pl/*", "pl:8000"],
  ["/f1/*", "f1:8000"],
  ["/nba/*", "nba:8000"],
  ["/nfl/*", "nfl:8001"],
  ["/cfb/*", "cfb:8003"],
];

test("the hub proxies every sport API on its own origin", () => {
  for (const [path, upstream] of PROXIES) {
    assert.match(
      caddy,
      new RegExp(`handle_path\\s+${path.replace("*", "\\*")}\\s*\\{[^}]*reverse_proxy\\s+${upstream}`),
      path,
    );
  }
});

test("the hub's static file server still works", () => {
  assert.match(caddy, /root \* \/srv\/hub/);
  assert.match(caddy, /file_server/);
});

// This test exists because a real one shipped. An earlier version of this file
// asserted only that the text "handle_path /pl/* {" and "reverse_proxy pl:8000"
// both appeared somewhere, and the config was written as
//
//     handle_path /pl/* { reverse_proxy pl:8000 }
//
// on one line. Both strings were present, so the test passed -- and Caddy
// refused the file outright:
//
//     Error: adapting config using caddyfile: Unexpected next token after '{'
//     on same line
//
// It was caught only by running `caddy validate` against a real binary on the
// VPS, after the config had already been written. A Caddyfile block is opened
// with '{' and its directives live on their own lines; a one-line block is not
// valid syntax. This assertion is the cheap half of that lesson: it fails on
// the shape, before anyone ships it.
test("no Caddyfile block puts directives on the same line as its brace", () => {
  // Matches a '{' that is followed, on the same line, by something other than
  // the end of the line. Comments are excluded because "# ... {" is prose.
  //
  // Two things must be handled before looking for that brace. Site blocks open
  // with a hostname template -- "pl.{$DOMAIN} {" -- whose own '{' is a
  // placeholder, not a block, and rewrite placeholders like "/explain{uri}"
  // are not blocks either. Both are stripped first, so the only '{' left is a
  // real block opener, and the last one on the line is the one that matters.
  //
  // The strip is deliberately /\{[^\s{}]*\}/ -- no whitespace inside the
  // braces. A looser /\{[^}]*\}/ swallows the whole body of a one-line block,
  // because "{ reverse_proxy pl:8000 }" is itself a match: the line is left
  // with no '{' at all and gets skipped. That makes the test blind to exactly
  // the bug it exists to catch, which is how the first version of this file
  // let a config Caddy rejects through. Placeholders are never
  // whitespace-separated; block bodies always are.
  const offenders = caddy
    .split("\n")
    .map((line, i) => [i + 1, line])
    .filter(([, raw]) => {
      const line = raw.replace(/\{[^\s{}]*\}/g, ""); // drop {...} placeholders only
      if (line.trimStart().startsWith("#")) return false;
      const brace = line.lastIndexOf("{");
      if (brace === -1) return false;
      return line.slice(brace + 1).trim() !== "";
    })
    .map(([n, line]) => `Caddyfile:${n}: ${line.trim()}`);
  assert.deepEqual(offenders, [], `one-line Caddy blocks:\n${offenders.join("\n")}`);
});

// The half of the lesson that needs a real Caddy. Skipped when no binary is
// available, because the shape test above is the portable guard and this is
// the authoritative one. It is not optional in spirit: run it wherever Caddy
// exists, which on this project means the VPS.
//
// DOMAIN is required because the site blocks are "pl.{$DOMAIN}" templates. With
// it unset, Caddy expands them to "pl." and refuses the config on certificate
// eligibility -- a failure that says nothing about this file's syntax. The
// value is overridden from the environment so the test tracks .env rather than
// hardcoding a hostname.
const DOMAIN = process.env.DOMAIN ?? "40-160-91-131.sslip.io";

test("the Caddyfile passes caddy validate", (t) => {
  let tool;
  try {
    tool = execFileSync("sh", ["-c", "command -v caddy || command -v docker"], {
      encoding: "utf8",
    })
      .trim()
      .split("\n")[0];
  } catch {
    tool = "";
  }
  if (!tool) return t.skip("neither caddy nor docker on PATH");

  const file = new URL("../Caddyfile", import.meta.url).pathname;
  const cmd = tool.endsWith("docker")
    ? `docker run --rm -v ${file}:/etc/caddy/Caddyfile:ro -e DOMAIN=${DOMAIN} caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile`
    : `caddy validate --config ${file} --adapter caddyfile`;
  try {
    execFileSync("sh", ["-c", cmd], { encoding: "utf8", stdio: "pipe" });
  } catch (e) {
    assert.fail(`caddy validate failed:\n${e.stdout || ""}${e.stderr || ""}`);
  }
});
