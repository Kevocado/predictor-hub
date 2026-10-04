/**
 * Which services receive which credential.
 *
 * This exists because PL silently lost its odds. `pl_predictor` ships a whole
 * sportsbook client -- `data/sportsbook_api.py`, `odds/value_bets.py`,
 * `evaluate/odds_benchmark.py`, and a background refresh loop wired into
 * `main.py` -- and reads `SPORTSBOOK_API_KEY` in all of them. Its compose
 * `environment:` block listed neither that key nor `ODDS_API_KEY`, so the
 * container had no credential, every fetch no-opped, and the site showed no
 * odds. Nothing failed: the code handles an absent key by degrading, which is
 * correct behaviour and exactly why it was invisible.
 *
 * So the rule this file pins is not "the key is in `.env`" -- it was. It is
 * that **a service whose code reads a credential must be handed it**. The
 * stack `.env` is not the delivery mechanism; `environment:` is.
 *
 * Deliberately an explicit per-service table rather than a cross-repo scan for
 * the credential names. A scan would be cleverer and would rot: it needs the
 * sibling checkouts (absent in a bare clone, which is why `SITES_ROOT` gates
 * `site-components.test.mjs`) and it would fail for reasons unrelated to this
 * wiring. The list below is the contract, and it is short.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const compose = readFileSync(join(here, "..", "compose.yml"), "utf8");

/** The `environment:` keys compose passes to one service.
 *
 * Parsed by indentation rather than with a YAML library: the file has no
 * dependency available here, and the block is a flat `KEY: value` list. A
 * service with no `environment:` at all yields an empty set, which is the
 * honest answer and is what `f1` looks like before anyone adds a key.
 */
function envKeysFor(service) {
  // The service's own block runs from `  <service>:` to the next `  <name>:`.
  const start = compose.search(new RegExp(`^  ${service}:$`, "m"));
  if (start === -1) return null; // no such service
  const rest = compose.slice(start + 1);
  const next = rest.search(/^ {2}[a-z][a-z0-9_-]*:$/m);
  const block = next === -1 ? rest : rest.slice(0, next);

  const envAt = block.search(/^ {4}environment:$/m);
  if (envAt === -1) return new Set();
  const after = block.slice(envAt);
  const end = after.slice(1).search(/^ {4}[a-z][a-z0-9_]*:$/m);
  const envBlock = end === -1 ? after : after.slice(0, end + 1);

  const keys = new Set();
  for (const line of envBlock.split("\n")) {
    const m = line.match(/^ {6}([A-Z][A-Z0-9_]*):/);
    if (m) keys.add(m[1]);
  }
  return keys;
}

test("every service in the compose file is a service this file knows", () => {
  // A service is a top-level key that pulls an `image:`. Indentation alone is not
  // enough: the `&logging` anchor's own `driver:` / `options:` keys sit at the
  // same two-space level as a service name.
  const blocks = compose.split(/\n(?= {2}[a-z])/);
  const declared = blocks
    .filter((b) => /^ {2}[a-z][a-z0-9_-]*:\n/.test(b) && /^\s{4}image:/m.test(b))
    .map((b) => b.match(/^ {2}([a-z][a-z0-9_-]*):/)[1]);
  const known = ["caddy", "pl", "f1", "nba", "nfl", "cfb", "sports", "predictor-explainer", "tradehub"];
  assert.ok(declared.length >= known.length - 1, `expected the services in compose.yml, parsed ${declared.length}`);
  for (const svc of declared) {
    assert.ok(known.includes(svc), `compose.yml adds service "${svc}" with no credential decision recorded here`);
  }
});

test("PL receives both odds credentials it reads", () => {
  // `pl_predictor/data/sportsbook_api.py`, `odds/value_bets.py` and
  // `evaluate/odds_benchmark.py` all read SPORTSBOOK_API_KEY; `data/odds_api.py`
  // reads ODDS_API_KEY. Commit 54b721d ("Switch live odds to RapidAPI
  // Sportsbook API") is the switch that made PL depend on it.
  const keys = envKeysFor("pl");
  assert.ok(keys.has("SPORTSBOOK_API_KEY"), "pl must receive SPORTSBOOK_API_KEY");
  assert.ok(keys.has("ODDS_API_KEY"), "pl must receive ODDS_API_KEY");
});

test("NFL receives both odds credentials", () => {
  const keys = envKeysFor("nfl");
  assert.ok(keys.has("ODDS_API_KEY"), "nfl must receive ODDS_API_KEY");
  assert.ok(keys.has("SPORTSBOOK_API_KEY"), "nfl must receive SPORTSBOOK_API_KEY");
});

test("NBA and CFB keep the credentials they already had", () => {
  // Regression guards, not new requirements: these two were the only services
  // wired correctly, and CFB is the only one whose odds cache fills.
  for (const svc of ["nba", "cfb"]) {
    const keys = envKeysFor(svc);
    assert.ok(keys.has("ODDS_API_KEY"), `${svc} must keep ODDS_API_KEY`);
    assert.ok(keys.has("SPORTSBOOK_API_KEY"), `${svc} must keep SPORTSBOOK_API_KEY`);
  }
});

test("F1 is handed no odds credential, because it reads none", () => {
  // The one deliberate omission. `f1_predictor` has no sportsbook or odds client
  // at all, so passing a key would imply a capability the sport does not have.
  const keys = envKeysFor("f1");
  assert.ok(!keys.has("ODDS_API_KEY"), "f1 reads no odds client; it should be handed no key");
  assert.ok(!keys.has("SPORTSBOOK_API_KEY"), "f1 reads no sportsbook client; it should be handed no key");
});