# Hub Picks Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the Predictor hub's `index.html` with a live picks teaser under each of the five existing sport cards, so the landing page answers "what does the model think right now?" without a click.

**Architecture:** The hub stays a build-free static page. Its Caddy block gains five same-origin `handle_path` proxies so a page on the bare domain can read the sport APIs. A new hand-written ES module, `teasers.js`, holds the fetch, the selection rules and the render; it is imported by `index.html` with `<script type="module">` and imported directly by `node --test`, so the selection rules are unit-testable with no build step. Cards are static HTML and never gated on a fetch; teasers hydrate independently into slots that already exist in the markup.

**Tech Stack:** Hand-written HTML + CSS + ES2022 modules (no bundler, no dependencies). Caddy 2 for the proxy. Python 3.11 + FastAPI + starlette 1.7.0 for the two snapshot sanitiser tasks. `node --test` for the hub tests.

**Spec:** [../specs/2026-09-27-hub-picks-page-design.md](../specs/2026-09-27-hub-picks-page-design.md)

## Global Constraints

These apply to every task. Copy them verbatim into any new file or test that needs them.

- **No bundler, no npm dependencies, no build step.** The hub is served straight off disk by Caddy. Adding a build is out of scope.
- **Tokens are hand-inlined and drift-tested.** `tests/hub.test.mjs` asserts the inlined `--color-pr-*`, `--font-pr-*` and `--radius-pr-*` values match `packages/predictor-ui/src/tokens.css` exactly, in both directions. **Any new token must be added to `tokens.css` first**, then mirrored into `index.html`.
- **The inlined accent colours are fixed:** pl `#ff2d78`, f1 `#ff4436`, nfl `#4c8dff`, cfb `#f5b301`, nba `#ff7a1a`, hub `#f3f5f8`. Stage `#0b0d10`, panel `#151920`, panel-2 `#1d232c`, rule `#2b333f`, text `#f3f5f8`, text-dim `#b4bdca`, text-faint `#909aa8`, win `#3ddc84`, loss `#ff6b6b`, lean `#ffc53d`, radius `6px`. Fonts: `Barlow Condensed` display, `Barlow` body.
- **Banned by existing tests, do not reintroduce:** the string `Inter`, `radial-gradient`, any emoji (`\p{Extended_Pictographic}`), and any text under `0.75rem` (12px).
- **`tests/hub.test.mjs` asserts the five cards appear in order** `["pl", "f1", "nfl", "cfb", "nba"]` as `<a class="sport pr-notch" data-sport="X">`, and that the five `<span class="status">` values are exactly `["In season", "In season", "In season", "In season", "Preseason"]`. **Do not add another `.status` span.**
- **Honesty rules, from `PRODUCT.md` and the hub's own strap:** only picks made before the event count; a pick rebuilt afterwards is shown and labelled, never counted; no profit, ROI or "beats the bookies" claim anywhere; uncertainty is shown, not hidden.
- **No `NaN` may reach a rendered number.** Non-finite floats are `null` at the source.
- **Every pick is displayed with the time it was made.** The teaser's freshness line is not optional.
- **Commit bodies are written for a future AI session**, not for a human skim: what changed, why, what was ruled out and why, and what the next session must not undo. This is an explicit project requirement.
- **Run the hub's tests with `node --test "tests/*.test.mjs"`.** Node 24 does not accept a bare directory (`node --test tests/` fails with `MODULE_NOT_FOUND`). Single files work directly: `node --test tests/hub.test.mjs`. The current suite is **21 passing tests** — keep it at 21 or better.

---

## File Structure

| File | Responsibility |
|---|---|
| `index.html` (modify) | Card grid, the five teaser slots, teaser CSS, `<script type="module" src="./teasers.js">`. Cards themselves unchanged. |
| `teasers.js` (create) | All hub behaviour: one exported pure selection function per sport, one shared `pct`/date formatter, and the hydrate entry that fetches and renders. No DOM logic in the selection functions. |
| `tests/teasers.test.mjs` (create) | Unit tests for the selection rules, imported straight from `../teasers.js`. |
| `tests/hub.test.mjs` (modify) | Structural assertions: the five slots exist, the module is loaded, cards are untouched. |
| `vps-stack/Caddyfile` (modify) | Five `handle_path` proxy blocks on the hub's site block. **`vps-stack` is its own git repo** on `main`, separate from `predictor-hub`, and it has **uncommitted changes** to `.env.example`, `bin/set-github-secrets.sh` and `compose.yml` that are not yours. Stage files explicitly; never `git add -A` there. |
| `vps-stack/tests/hub-caddyfile.test.mjs` (create) | Asserts the five proxies exist. `vps-stack` has no `tests/` directory yet, so this creates the first one. |
| `NFL_Predictor/src/nfl_predictor/public_snapshot.py` (modify) | Sanitise non-finite floats; dump with `allow_nan=False` as a guard. |
| `F1_Predictor/src/f1_predictor/public_snapshot.py` (modify) | Same. |
| `F1_Predictor/src/f1_predictor/api/schemas.py` (modify) | `driver_name` on `DriverPrediction`. |

**Why a separate `teasers.js` rather than an inline `<script>`:** the selection rules are the part most likely to be subtly wrong (the coin-flip rule and the strongest-pick rule are both easy to get backwards). Inline in a 330-line HTML file they are untestable without a DOM; as an ES module, `node --test` imports and unit-tests them directly, and the browser loads the same file. No build step either way.

---

### Task 1: Non-finite floats out of the NFL snapshot

**Why first:** the hub cannot fetch NFL predictions at all until this lands. `starlette.responses.JSONResponse.render` passes `allow_nan=False`, so a response containing `NaN` raises `ValueError` and becomes an HTTP 500 — a dead endpoint, not an unparseable body. The sport sites dodge this today only because they request weeks whose rows happen to be clean; a hub fanning out across every week hits it immediately.

**Root cause, verified:** `public_snapshot.py:117` writes `json.dumps(snapshot, indent=2)`. `json.dumps` defaults to `allow_nan=True`, which writes a bare `NaN` token. `jsonable_encoder` on line 116 does not convert `NaN` to `None`. So invalid JSON lands on disk and is served verbatim by `routes.get_predictions_batch` (`return snap["predictions"]`).

**Files:**
- Modify: `src/nfl_predictor/public_snapshot.py`
- Test: `tests/test_public_snapshot_json.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sanitize_floats(value)` — module-level in `public_snapshot.py`. Recursively walks dicts, lists and tuples; converts any `float` that is `nan` or infinite to `None`; returns everything else unchanged. Used by Task 6? No — this is Python, and the hub is JS. It is consumed by `main()` in this file and by nothing else.

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_snapshot_json.py`:

```python
"""A snapshot holding NaN is invalid JSON on disk, whoever reads it.

json.dumps defaults to allow_nan=True, so a single non-finite float used to
be written as a bare NaN token. The public deployment serves that file
verbatim, and starlette renders responses with allow_nan=False -- so the
endpoint 500s rather than returning a body the browser can fail to parse.
"""

import json
import math

import pytest

from nfl_predictor.public_snapshot import sanitize_floats


def test_nan_becomes_null():
    assert sanitize_floats({"home_cover_prob": float("nan")}) == {"home_cover_prob": None}


def test_infinities_become_null():
    assert sanitize_floats({"a": float("inf"), "b": float("-inf")}) == {"a": None, "b": None}


def test_walks_nested_structures():
    payload = {"weeks": {"9": {"predictions": {"g1": {"sigma": float("nan")}}}}}
    assert sanitize_floats(payload) == {"weeks": {"9": {"predictions": {"g1": {"sigma": None}}}}}


def test_leaves_real_numbers_and_types_alone():
    payload = {"p": 0.5, "n": 3, "s": "x", "b": True, "none": None, "empty": [], "d": {}}
    assert sanitize_floats(payload) == payload


def test_sanitised_snapshot_survives_a_strict_dump():
    """The regression guard: allow_nan=False is what makes a future NaN loud."""
    snapshot = sanitize_floats({"predictions": {"g1": {"over_prob": float("nan")}}})
    text = json.dumps(snapshot, indent=2, allow_nan=False)
    assert json.loads(text)["predictions"]["g1"]["over_prob"] is None


def test_the_committed_snapshot_is_strict_json():
    """The file on disk must parse with allow_nan=False, not just json.loads."""
    from nfl_predictor.config import PUBLIC_SNAPSHOT_PATH

    if not PUBLIC_SNAPSHOT_PATH.exists():
        pytest.skip("no committed snapshot in this checkout")
    text = PUBLIC_SNAPSHOT_PATH.read_text()
    json.loads(text, parse_constant=_reject)  # parse_constant fires on NaN/Infinity


def _reject(name):
    raise AssertionError(f"snapshot contains a bare {name} token")
```

Note: `json.loads`'s `parse_constant` is called for `NaN`, `Infinity` and `-Infinity`, which is a stricter check than `allow_nan=False` on dump. This test is what would have caught the original bug.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_public_snapshot_json.py -q`

Expected: collection error — `ImportError: cannot import name 'sanitize_floats'`.

- [ ] **Step 3: Implement `sanitize_floats` and use it in `main()`**

In `src/nfl_predictor/public_snapshot.py`, add `import math` to the imports, then add the function above `main()`:

```python
def sanitize_floats(value):
    """Replace every non-finite float with None, recursively.

    The feature pipeline produces NaN for "this market has no line" (an
    unplayed game has no spread, a team with no cover model has no cover
    probability). NaN is not valid JSON, and the public deployment serves
    this file verbatim through a starlette JSONResponse, which renders with
    allow_nan=False and turns a NaN into a 500. Null is the honest
    encoding: the UI already renders a dash for a missing number.
    """
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {k: sanitize_floats(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_floats(v) for v in value]
    return value
```

Then change `main()` so the dump can never silently regress:

```python
def main() -> None:
    previous = json.loads(config.PUBLIC_SNAPSHOT_PATH.read_text()) if config.PUBLIC_SNAPSHOT_PATH.exists() else None
    snapshot = sanitize_floats(jsonable_encoder(build_snapshot(previous)))
    # allow_nan=False is the guard, not the mechanism: sanitize_floats has
    # already replaced every non-finite float, so reaching here means a new
    # one appeared somewhere and the build must fail loudly rather than
    # write invalid JSON again.
    config.PUBLIC_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, allow_nan=False))
    print(f"Wrote {config.PUBLIC_SNAPSHOT_PATH} ({config.PUBLIC_SNAPSHOT_PATH.stat().st_size / 1024:.0f} KB)")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_public_snapshot_json.py -q`

Expected: 6 passed, 1 skipped (the committed-snapshot test skips if this checkout has no snapshot).

- [ ] **Step 5: Run the full suite for regressions**

Run: `.venv/bin/python -m pytest -q`

Expected: all previously-passing tests still pass. The pre-existing pandas/numpy deprecation warnings are expected and are not yours to fix.

- [ ] **Step 6: Regenerate the committed snapshot**

Run: `.venv/bin/python -m nfl_predictor.public_snapshot`

Expected: prints `Building weeks 1-22 ...` and `Wrote .../public_snapshot.json (N KB)`. Then confirm the file is strict JSON:

Run: `.venv/bin/python -c "import json; json.loads(open('data/public_snapshot.json').read(), parse_constant=lambda n:(_ for _ in ()).throw(SystemExit('bare '+n))); print('strict JSON ok')"`

Expected: `strict JSON ok`. If this raises `bare NaN`, `sanitize_floats` is not reaching every path — find which one before continuing.

- [ ] **Step 7: Commit**

```bash
git add src/nfl_predictor/public_snapshot.py tests/test_public_snapshot_json.py data/public_snapshot.json
git commit -F - <<'MSG'
fix: the NFL snapshot wrote bare NaN tokens, which 500s the endpoint

main() called json.dumps(snapshot, indent=2), and json.dumps defaults to
allow_nan=True -- so any non-finite float was written as a bare NaN, which
is not valid JSON. jsonable_encoder does not convert NaN to None, so nothing
upstream caught it.

This is not cosmetic. The public deployment serves data/public_snapshot.json
verbatim, and starlette 1.7.0's JSONResponse.render passes allow_nan=False.
A NaN in the response raises ValueError and becomes a 500. routes.py even
documents this exact hazard in _get_games_live ("Starlette's default
JSONResponse uses json.dumps(..., allow_nan=False), so an unconverted NaN
raises ValueError -> unhandled 500") and sanitises the live path -- but
get_predictions_batch returns the snapshot block untouched, so the snapshot
path was never covered. Week 9's predictions are all-NaN on cover, over and
under.

Why the sport sites work today: they request the current week, whose rows
happen to be clean. A hub fanning out across every week would not survive
its first load.

sanitize_floats() walks the structure and maps non-finite floats to None,
which is the honest encoding -- the feature pipeline produces NaN to mean
"no line for this market", and the UI already renders a dash for a missing
number. main() then dumps with allow_nan=False: that is the guard, not the
mechanism, so a future NaN fails the build loudly instead of quietly
producing invalid JSON a third time.

The committed-snapshot test parses with parse_constant, which fires on NaN,
Infinity and -Infinity -- stricter than json.loads alone.

Next: F1_Predictor has the identical defect at public_snapshot.py:207, and
the hub needs the NBA, PL and F1 payloads to be strict too.
MSG
```

---

### Task 2: Non-finite floats out of the F1 snapshot

**Why:** identical defect, identical fix, different repo. The hub's F1 card reads `predictions[round].predictions[*].expected_position` and `expected_points`, which are `NaN` in the committed snapshot.

**Files:**
- Modify: `src/f1_predictor/public_snapshot.py:207`
- Test: `tests/test_public_snapshot_json.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sanitize_floats(value)` in F1's `public_snapshot.py` — the same signature as Task 1's. The two are independent copies in independent repos; **do not** try to share them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_public_snapshot_json.py` with the same six tests as Task 1, changing only the import to `from f1_predictor.public_snapshot import sanitize_floats` and the snapshot path import to `from f1_predictor.config import PUBLIC_SNAPSHOT_PATH`. Add one F1-specific test:

```python
def test_expected_position_and_points_are_null_not_nan():
    """The two fields the hub's F1 teaser would otherwise render as NaN."""
    row = {"driver_id": "russell", "p_win": 0.15, "expected_position": float("nan"), "expected_points": float("nan")}
    out = sanitize_floats({"predictions": {"1": {"predictions": [row]}}})
    got = out["predictions"]["1"]["predictions"][0]
    assert got["expected_position"] is None
    assert got["expected_points"] is None
    assert got["p_win"] == 0.15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_public_snapshot_json.py -q`

Expected: `ImportError: cannot import name 'sanitize_floats'`.

- [ ] **Step 3: Implement and wire it up**

Add `import math` and the identical `sanitize_floats` to `src/f1_predictor/public_snapshot.py`. Then change line 207's write. Read the surrounding `main()` first and preserve whatever else it does; the only required change is:

```python
    snapshot = sanitize_floats(snapshot)
    config.PUBLIC_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, allow_nan=False))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_public_snapshot_json.py -q`

Expected: 7 passed, 1 skipped.

- [ ] **Step 5: Run the full F1 suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all pass. (Note: this repo has a test that specifically guards against stalls from real network calls — keep it that way.)

- [ ] **Step 6: Regenerate and verify strict JSON**

Run: `.venv/bin/python -m f1_predictor.public_snapshot`

Then run the same `parse_constant` check as Task 1 Step 6 against `data/public_snapshot.json`. Expected: `strict JSON ok`.

- [ ] **Step 7: Commit**

```bash
git add src/f1_predictor/public_snapshot.py tests/test_public_snapshot_json.py data/public_snapshot.json
git commit -F - <<'MSG'
fix: the F1 snapshot wrote bare NaN tokens too, same as NFL

public_snapshot.py:207 called json.dumps(snapshot, indent=2), and
json.dumps defaults to allow_nan=True, so expected_position and
expected_points were written as bare NaN. Not valid JSON, and starlette
renders with allow_nan=False, so serving one is a 500 rather than a body
the browser can fail to parse.

Same fix as NFL_Predictor, same reasoning, separate repo so a separate copy:
sanitize_floats() maps non-finite floats to None, and main() dumps with
allow_nan=False as the guard that makes a future NaN fail the build loudly.

Those two fields are NaN for every driver of every race in the committed
snapshot, which is the shape the hub's F1 teaser reads when it asks for the
next race's top three by p_win. Without this the hub's F1 card is a dead
endpoint on first load.

Do not try to share sanitize_floats with NFL_Predictor. Independent repos,
independent deploys; a third copy is cheaper than a coupling.
MSG
```

---

### Task 3: Proxy the five sport APIs from the hub

**Why:** nothing on the hub can fetch anything until this lands. The hub's site block is `root * /srv/hub` + `file_server` and nothing else, so a page on the bare domain reading the sport subdomains is cross-origin.

**This is the only task that cannot be fully verified from a laptop.** It needs a VPS deploy. Write the structural test, make the change, and state plainly in the PR/commit that live verification is outstanding — do not claim it works.

**Files:**
- Modify: `vps-stack/Caddyfile`
- Test: `vps-stack/tests/hub-caddyfile.test.mjs` (create — `vps-stack` has no `tests/` yet)

**Repo:** this task is committed to the **`vps-stack` repo**, not `predictor-hub`. `vps-stack` is a separate git repo on `main` with **no configured remote**, and its working tree already has unrelated modifications to `.env.example`, `bin/set-github-secrets.sh` and `compose.yml`. Stage only `Caddyfile` and the new test. Do not sweep the others into the commit and do not try to push.

**Interfaces:**
- Consumes: nothing.
- Produces: five same-origin prefixes on the hub's site block: `/pl/*`, `/f1/*`, `/nba/*`, `/nfl/*`, `/cfb/*`. Tasks 5–7 fetch exactly these prefixes.

- [ ] **Step 1: Create the test directory and write the failing test**

`vps-stack` has no `tests/` directory. Create it and add `tests/hub-caddyfile.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

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
    assert.match(caddy, new RegExp(`handle_path\\s+${path.replace("*", "\\*")}\\s*\\{[^}]*reverse_proxy\\s+${upstream}`), path);
  }
});

test("the hub's static file server still works", () => {
  assert.match(caddy, /root \* \/srv\/hub/);
  assert.match(caddy, /file_server/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test tests/hub-caddyfile.test.mjs`

Expected: FAIL on the first proxy.

- [ ] **Step 3: Add the proxy blocks**

In `vps-stack/Caddyfile`, replace the hub's block:

```
{$DOMAIN}, www.{$DOMAIN} {
	import common
	root * /srv/hub
	file_server
}
```

with:

```
{$DOMAIN}, www.{$DOMAIN} {
	import common

	# The picks teasers on the landing page read every sport API. The hub is
	# static and lives on the bare domain while the APIs live on subdomains,
	# so without these the browser is cross-origin and every fetch is blocked.
	# Same pattern as sports.{$DOMAIN} below, and same reason: handle_path
	# strips the prefix and the upstream serves from its own root.
	handle_path /pl/* { reverse_proxy pl:8000 }
	handle_path /f1/* { reverse_proxy f1:8000 }
	handle_path /nba/* { reverse_proxy nba:8000 }
	handle_path /nfl/* { reverse_proxy nfl:8001 }
	handle_path /cfb/* { reverse_proxy cfb:8003 }

	handle {
		root * /srv/hub
		file_server
	}
}
```

The explicit `handle` block matters: Caddy falls back to the most specific matcher, and an explicit block keeps the static file server from being shadowed by a prefix.

- [ ] **Step 4: Validate the config if Caddy is available**

Run: `caddy validate --config Caddyfile --adapter caddyfile 2>&1 || echo "caddy not installed locally"`

Expected: `Valid configuration` or the "not installed" note. If Caddy *is* installed and validation fails, fix the syntax before committing.

- [ ] **Step 5: Run the test to verify it passes**

Run, from `vps-stack/`: `node --test tests/hub-caddyfile.test.mjs`

Expected: 2 passed.

- [ ] **Step 6: Commit — in the `vps-stack` repo, not `predictor-hub`**

```bash
cd /path/to/vps-stack
git add Caddyfile tests/hub-caddyfile.test.mjs
git commit -F - <<'MSG'
feat: proxy the five sport APIs from the hub, so a static page can read them

The hub's site block was root + file_server and nothing else. The page is
served from the bare domain and every sport API lives on a subdomain, so
anything the landing page wanted to fetch was cross-origin. This is the
block Phase 4 step 13 was deferred on, and it is the reason it was deferred.

Five handle_path prefixes, same shape as sports.{$DOMAIN} further down this
file, which already does it for the two American-football APIs. handle_path
strips the prefix and each upstream serves from its own root, so the hub can
address /nfl/api/games exactly as the sports site does.

Wrapped the file server in an explicit handle block. Caddy picks the most
specific matcher, and being explicit keeps a prefix from ever shadowing the
static handler as more prefixes are added.

NOT VERIFIED LIVE. This needs a VPS deploy and a real fetch against
https://<domain>/nfl/api/current-week before the teasers can be called
working. The test asserts the config, not the behaviour. Do not mark the
teaser work done on the strength of this commit alone.
MSG
```

---

### Task 4: F1 driver names on the API

**Why:** the hub's F1 card needs a driver name, and the API only has `driver_id`. The F1 site currently title-cases the id itself, so it shows "Russell" rather than "George Russell". Moving the name to the API fixes the hub and the site at once.

**This task is droppable.** If the hub ships without it, the F1 card title-cases `driver_id` exactly as the F1 site does and the two agree. Do it because a first name is better, not because the hub is blocked.

**Files:**
- Modify: `src/f1_predictor/api/schemas.py` (`DriverPrediction`)
- Modify: `src/f1_predictor/api/routes.py` (where the race prediction is assembled)
- Test: `tests/test_driver_names.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `driver_name: str` on `DriverPrediction`, and `driver_name` on each entry of `predictions[round].predictions[*]` in the snapshot. Task 6's `selectF1` reads `driver_name` and must fall back to title-casing `driver_id` when it is absent, so the hub works whether or not this task has shipped.

- [ ] **Step 1: Find where the driver rows are built**

Run: `grep -rn "driver_id" src/f1_predictor/api/routes.py | head -20` and `grep -rn "_driver_rows" src/f1_predictor/api/facts.py | head`

`facts.py` already builds a `{driver_id: name}` map from the stored race-result rows (`_name_by_driver`). Find the function that assembles the `DriverPrediction` list and see whether those rows are in scope there. If they are not, get names from the same place `facts.py` does rather than inventing a second source.

- [ ] **Step 2: Write the failing test**

```python
def test_race_prediction_carries_a_driver_name():
    """The API returns driver_id only, so the hub shows a raw id like
    'russell'. The site title-cases it; the API should just say the name."""
    payload = _prediction_payload_for_test()
    rows = payload["predictions"]
    assert rows, "no driver rows in the fixture"
    assert all(r.get("driver_name") for r in rows), [r for r in rows if not r.get("driver_name")]


def test_driver_name_falls_back_to_the_id_when_unknown():
    rows = _prediction_payload_for_test()["predictions"]
    assert all(isinstance(r["driver_name"], str) and r["driver_name"] for r in rows)
```

Build `_prediction_payload_for_test()` from the repo's existing test fixtures for a race prediction. **Reuse whatever fixture the existing race-prediction tests already use** — find it with `grep -rln "p_win" tests/` and copy its shape. Do not invent a new one.

- [ ] **Step 3: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_driver_names.py -q`

Expected: FAIL — `driver_name` absent.

- [ ] **Step 4: Implement**

Add to `DriverPrediction` in `schemas.py`:

```python
class DriverPrediction(BaseModel):
    driver_id: str
    # Display name. The site used to title-case driver_id, which turns
    # "russell" into "Russell" and drops the first name. The hub needs the
    # same string the site shows, so it lives here rather than being derived
    # twice. Never null: falls back to the id, so a driver with no name in
    # the results feed still renders as something a human can read.
    driver_name: str
    constructor_id: str | None = None
    p_win: float
    p_podium: float
    p_points_finish: float
    p_dnf: float
    expected_position: float | None = None
    expected_points: float | None = None
    actual_position: int | None = None
    actual_dnf: bool | None = None
```

Note `expected_position` and `expected_points` become `| None = None`. They are `NaN` in practice, and after Task 2 they serialise to `null`, so the schema has to accept null. This is required for the endpoint to stop 500ing on a null.

Then populate `driver_name` where the rows are assembled, using the map `facts.py::_name_by_driver` already builds, and `driver_name = names.get(driver_id) or _title_case(driver_id)`.

Add the fallback helper if it does not exist:

```python
def _title_case(driver_id: str) -> str:
    """Matches what the F1 site renders from a bare id, so the hub and the
    site can never disagree about a driver's name."""
    return driver_id.split("_")[0].upper() + driver_id.split("_")[0][1:] + " " + " ".join(
        p.capitalize() for p in driver_id.split("_")[1:]
    )
```

If `teamColors.ts:46`'s exact behaviour is wanted instead, mirror that function verbatim rather than inventing a second algorithm. **One algorithm, one home.**

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_driver_names.py -q`

Expected: 2 passed.

- [ ] **Step 6: Run the full F1 suite and fix fallout**

Run: `.venv/bin/python -m pytest -q`

Expected: some existing tests may construct `DriverPrediction` without `driver_name` and now fail. Update those fixtures to include a name. This is expected and is not a reason to make the field optional.

- [ ] **Step 7: Commit**

```bash
git add src/f1_predictor/api/schemas.py src/f1_predictor/api/routes.py tests/test_driver_names.py
git commit -F - <<'MSG'
feat: the F1 API returns a driver name, not just a driver id

DriverPrediction had driver_id and nothing else, so every consumer had to
invent a display name. The F1 site title-cases the id
(frontend/src/lib/teamColors.ts:46), which turns "russell" into "Russell" and
drops the first name. The hub needs the same string, and duplicating a
title-caser in a second repo is exactly the drift that the hub's token-parity
test exists to prevent.

driver_name is non-optional and falls back to the title-cased id, so a driver
missing from the results feed still renders as something readable rather than
a raw snake_case token.

expected_position and expected_points become Optional. They are NaN in every
row of the committed snapshot; now that Task 2 serialises NaN to null, the
endpoint returns null and a non-optional float would reject its own response.

Droppable: the hub falls back to title-casing driver_id when driver_name is
absent, so this is a quality improvement, not a blocker.
MSG
```

---

### Task 5: Teaser slots and their styles

**Why:** the slots must exist in the static HTML before any script can fill them. The cards must keep working with every script disabled.

**Files:**
- Modify: `index.html` — the `<ul class="board">` block, and the `<style>` block
- Test: `tests/hub.test.mjs`

**Interfaces:**
- Consumes: nothing.
- Produces: five `<div class="teaser">` elements, one per `<li class="slot">`, each carrying `data-teaser="<sport>"` and `aria-busy="true"`. Tasks 6 and 7 render into them and must remove `aria-busy`.

- [ ] **Step 1: Write the failing test**

Append to `tests/hub.test.mjs`:

```js
test("every card has a picks teaser slot beneath it, not inside it", () => {
  // Kevin asked for the picks "underneath the cards". A teaser with its own
  // links cannot live inside the card's <a> -- nesting interactive content in
  // an anchor is invalid HTML -- so the slot is a sibling in the same <li>.
  const slots = [...html.matchAll(/<div class="teaser" data-teaser="(\w+)" aria-busy="true">/g)].map((m) => m[1]);
  assert.deepEqual(slots, ["pl", "f1", "nfl", "cfb", "nba"]);

  // And the slot must be a sibling of the card, not a descendant: an <a> that
  // still contains "teaser" means someone nested it later.
  for (const anchor of html.match(/<a class="sport pr-notch"[\s\S]*?<\/a>/g) || []) {
    assert.doesNotMatch(anchor, /class="teaser"/, "a teaser was nested inside the card's anchor");
  }
});

test("the cards themselves are untouched by the teasers", () => {
  const cards = [...html.matchAll(/<a class="sport pr-notch" data-sport="(\w+)"/g)].map((m) => m[1]);
  assert.deepEqual(cards, ["pl", "f1", "nfl", "cfb", "nba"]);
  const status = [...html.matchAll(/<span class="status">([^<]+)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(status, ["In season", "In season", "In season", "In season", "Preseason"]);
});

test("the hub loads the teaser module", () => {
  assert.match(html, /<script type="module" src="\.\/teasers\.js"><\/script>/);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `node --test tests/hub.test.mjs`

Expected: FAIL on the first new test — no teaser slots.

- [ ] **Step 3: Add the slots**

Change the board's list items from bare `<li>` to `<li class="slot">`, and add a teaser `<div>` after each card's closing `</a>`. The PL item becomes:

```html
      <li class="slot" data-sport="pl">
        <a class="sport pr-notch" data-sport="pl" href="https://pl.40-160-91-131.sslip.io">
          <span class="sport-head"><span class="code">PL</span><span class="status">In season</span></span>
          <h2>Premier League</h2>
          <p>A pick and a most likely score for every fixture, gameweek by gameweek.</p>
          <span class="open">Open PL →</span>
        </a>
        <div class="teaser" data-teaser="pl" aria-busy="true"></div>
      </li>
```

Repeat for `f1`, `nfl`, `cfb`, `nba`. Do not change the card contents.

- [ ] **Step 4: Add the teaser CSS**

Append inside the existing `<style>`. Every colour is an existing token; **do not introduce a new one** (the token-parity test would fail).

```css
  /* Picks teaser: the live opinion under each card. Sits below the card as a
     sibling, so the card stays one big link and the teaser can hold its own
     links to individual games. */
  .slot { display: flex; flex-direction: column; gap: 0.5rem; }
  .teaser {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    border: 1px solid var(--color-pr-rule);
    border-left: 3px solid var(--color-pr-accent);
    border-radius: var(--radius-pr);
    background: var(--color-pr-panel);
    padding: 0.625rem 0.75rem;
    min-height: 4.5rem;
  }
  .teaser-label {
    font-family: var(--font-pr-display);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--color-pr-text-faint);
  }
  .teaser-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
    font-size: 0.875rem;
    line-height: 1.4;
    color: var(--color-pr-text);
  }
  .teaser-row a { color: inherit; text-decoration: none; }
  .teaser-row a:hover { text-decoration: underline; text-underline-offset: 2px; }
  .teaser-name { font-weight: 600; }
  .teaser-side { color: var(--color-pr-text-dim); }
  .teaser-num {
    font-family: var(--font-pr-display);
    font-size: 1rem;
    font-weight: 700;
    color: var(--color-pr-accent);
  }
  .teaser-note { font-size: 0.75rem; line-height: 1.4; color: var(--color-pr-text-faint); }
  .teaser-edge { font-size: 0.75rem; color: var(--color-pr-lean); }
  /* Reserved, never a spinner that outlives its data. A failed or empty
     teaser collapses to its note rather than leaving a hole in the board. */
  .teaser[aria-busy="true"] { color: var(--color-pr-text-faint); }
```

- [ ] **Step 5: Add the module script tag**

Immediately before `</body>`, after the existing inline hostname script:

```html
  <script type="module" src="./teasers.js"></script>
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `node --test tests/hub.test.mjs tests/craft-floor.test.mjs`

Expected: all pass, including the pre-existing token-parity and craft-floor assertions.

- [ ] **Step 7: Commit**

```bash
git add index.html tests/hub.test.mjs
git commit -F - <<'MSG'
feat: five empty picks-teaser slots under the hub's cards

Structure only -- no data yet. The slots are static HTML so the board renders
with every script disabled, which is how the page behaves today and how it
must keep behaving when an API is down.

The teaser is a sibling of the card inside the same <li>, not a descendant.
Kevin asked for the picks "underneath the cards", and it is also the only
valid option: a teaser with its own links to individual games cannot live
inside the card's <a>, because nesting interactive content in an anchor is
invalid HTML. As a sibling, the card stays one large link to the sport and
each teaser row can link to its own game. A test asserts no anchor contains a
teaser, so nobody nests one later.

Every colour is an existing token. The hub inlines its tokens by hand and
hub.test.mjs fails on any drift from predictor-ui's tokens.css in either
direction, so introducing a new token here without adding it to tokens.css
first would break the build. min-height reserves the slot so the board does
not reflow when five teasers hydrate at different speeds.

Cards are untouched: same five, same order, same status words. Two tests pin
that, because the teasers are the kind of change that quietly eats a
sibling's markup.
MSG
```

---

### Task 6: The selection rules, as pure functions

**Why:** the rules are the part most likely to be subtly wrong — the coin-flip rule and the strongest-pick rule are both easy to get backwards — and they must be testable without a DOM.

**Files:**
- Create: `teasers.js`
- Test: `tests/teasers.test.mjs`

**Interfaces:**
- Consumes: the five `.teaser` slots from Task 5 (at render time only; the functions below are pure and touch no DOM).
- Produces, all exported from `teasers.js`:
  - `selectF1(races, predictions) → { label, rows, empty }`
  - `selectPL(payload) → { label, rows, empty }`
  - `selectFootball(games, predictions) → { label, rows, empty }` — shared by NFL and CFB
  - `selectNBA(games) → { label, rows, empty }`
  - `pct(x) → string`, `driverName(id) → string`

  Every selector returns `{ label, rows, empty }`. `rows` is `[]` when `empty` is non-empty, so a caller never has to distinguish "no games" from "a game with no prediction".

- [ ] **Step 1: Write the failing tests**

Create `tests/teasers.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { selectF1, selectPL, selectFootball, selectNBA, pct, driverName } from "../teasers.js";

// --- shared formatting ---

test("pct renders a whole percentage and never NaN", () => {
  assert.equal(pct(0.4812), "48%");
  assert.equal(pct(1), "100%");
  assert.equal(pct(null), "—");
  assert.equal(pct(undefined), "—");
  assert.equal(pct(NaN), "—");
  assert.equal(pct(0), "0%");
});

test("driverName title-cases the id exactly as the F1 site does", () => {
  assert.equal(driverName("russell"), "Russell");
  assert.equal(driverName("max_verstappen"), "Max Verstappen");
  // A real name from the API wins over anything derived.
  assert.equal(driverName("russell", "George Russell"), "George Russell");
  assert.equal(driverName("russell", null), "Russell");
});

// --- F1: top three by p_win ---

const F1_RACES = [
  { season: 2026, round: 3, race_name: "Australian Grand Prix", race_datetime: "2026-03-08T05:00:00Z", completed: true },
  { season: 2026, round: 4, race_name: "Chinese Grand Prix", race_datetime: "2026-03-15T05:00:00Z", completed: false },
];

test("F1 picks the next race, not the last finished one", () => {
  const out = selectF1(F1_RACES, {
    3: { source: "tracked", predictions: [{ driver_id: "a", p_win: 0.9 }] },
    4: { source: "tracked", predictions: [{ driver_id: "b", p_win: 0.2 }] },
  });
  assert.equal(out.label, "Chinese Grand Prix");
  assert.deepEqual(out.rows.map((r) => r.name), ["b"]);
});

test("F1 takes the top three by win probability", () => {
  const out = selectF1(F1_RACES, {
    4: {
      source: "tracked",
      predictions: [
        { driver_id: "russell", p_win: 0.15 },
        { driver_id: "norris", p_win: 0.40 },
        { driver_id: "verstappen", p_win: 0.30 },
        { driver_id: "hamilton", p_win: 0.09 },
        { driver_id: "leclerc", p_win: 0.06 },
      ],
    },
  });
  assert.deepEqual(out.rows.map((r) => r.name), ["Norris", "Verstappen", "Russell"]);
  assert.equal(out.rows.length, 3);
});

test("F1 refuses to present a rebuilt or backtest pick as a pre-race call", () => {
  const out = selectF1(F1_RACES, { 4: { source: "rebuilt", predictions: [{ driver_id: "russell", p_win: 0.5 }] } });
  assert.equal(out.rows.length, 0);
  assert.match(out.empty, /after the session|race/i);
});

test("F1 with no upcoming race says so rather than showing the last one", () => {
  const out = selectF1([F1_RACES[0]], { 3: { source: "tracked", predictions: [{ driver_id: "a", p_win: 0.5 }] } });
  assert.equal(out.rows.length, 0);
  assert.match(out.empty, /season/i);
});

// --- PL: strongest pick ---

test("PL picks the fixture the model is most sure about", () => {
  const out = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: {
      9: {
        gameweek: 9,
        fixtures: [
          { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.44, predicted_draw: 0.25, predicted_away_win: 0.31, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
          { event_id: "2", team_home: "C", team_away: "D", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, predicted_scoreline: "3-0", has_live_odds: false, value_bet_flags: [] },
        ],
      },
    },
  });
  assert.equal(out.rows[0].name, "C v D");
  assert.equal(out.rows[0].value, "86%");
});

test("PL reads a draw as a pick in its own right", () => {
  // A fixture where the draw is the model's call must not be skipped for
  // having no favoured side. PRODUCT.md calls this a toss-up.
  const out = selectPL({
    current_gameweek: 9,
    fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
      { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.36, predicted_draw: 0.40, predicted_away_win: 0.24, predicted_scoreline: "1-1", has_live_odds: false, value_bet_flags: [] },
    ] } },
  });
  assert.equal(out.rows[0].value, "40%");
  assert.match(out.rows[0].pick, /draw/i);
});

test("PL shows an edge only when a real line exists", () => {
  const base = { current_gameweek: 9, fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
    { event_id: "1", team_home: "A", team_away: "B", predicted_home_win: 0.86, predicted_draw: 0.08, predicted_away_win: 0.06, predicted_scoreline: "3-0", has_live_odds: false, value_bet_flags: [] },
  ] } } };
  assert.equal(selectPL(base).rows[0].edge, undefined);
  const withOdds = { current_gameweek: 9, fixtures_by_gameweek: { 9: { gameweek: 9, fixtures: [
    { ...base.fixtures_by_gameweek[9].fixtures[0], has_live_odds: true, value_bet_flags: ["home_win"] },
  ] } } };
  assert.ok(selectPL(withOdds).rows[0].edge, "a real line must produce an edge");
});

// --- NFL / CFB: closest to a coin flip ---

test("the football card picks the game closest to a coin flip", () => {
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: null },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-05T00:00:00", spread_line: -2.5 },
      { game_id: "g3", home_team: "EEE", away_team: "FFF", gameday: "2026-11-05T00:00:00", spread_line: null },
    ],
    {
      g1: { home_win_prob: 0.50, away_win_prob: 0.50 },
      g2: { home_win_prob: 0.62, away_win_prob: 0.38 },
      g3: { home_win_prob: 0.51, away_win_prob: 0.49 },
    },
  );
  assert.equal(out.rows[0].name, "EEE v FFF", "closest to 50% wins, not the first or the biggest favourite");
  assert.equal(out.rows[0].value, "51%");
});

test("the football card is the one that carries the line", () => {
  // Only the closest game is shown, so a line on any other game is irrelevant.
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-05T00:00:00", spread_line: -7 },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-05T00:00:00", spread_line: null },
    ],
    { g1: { home_win_prob: 0.80, away_win_prob: 0.20 }, g2: { home_win_prob: 0.52, away_win_prob: 0.48 } },
  );
  assert.equal(out.rows[0].name, "CCC v DDD");
  assert.equal(out.rows[0].edge, undefined, "the shown game has no line, so no edge is claimed");
});

test("the football card ignores finished games", () => {
  const out = selectFootball(
    [
      { game_id: "g1", home_team: "AAA", away_team: "BBB", gameday: "2026-11-01T00:00:00", home_score: 24, away_score: 10, spread_line: null },
      { game_id: "g2", home_team: "CCC", away_team: "DDD", gameday: "2026-11-08T00:00:00", home_score: null, away_score: null, spread_line: null },
    ],
    { g1: { home_win_prob: 0.50, away_win_prob: 0.50 }, g2: { home_win_prob: 0.70, away_win_prob: 0.30 } },
  );
  assert.equal(out.rows[0].name, "CCC v DDD");
});

test("the football card says so when the week has no games left", () => {
  const out = selectFootball([{ game_id: "g1", home_team: "A", away_team: "B", gameday: "2026-11-01T00:00:00", home_score: 1, away_score: 0 }], {});
  assert.equal(out.rows.length, 0);
  assert.ok(out.empty);
});

// --- NBA: closest to a coin flip ---

test("NBA picks the closest game among those with a prediction", () => {
  const out = selectNBA([
    { game_id: "1", home_team: "NYK", away_team: "BOS", completed: false, prediction: { home_win_prob: 0.55 } },
    { game_id: "2", home_team: "LAL", away_team: "GSW", completed: false, prediction: { home_win_prob: 0.50 } },
    { game_id: "3", home_team: "MIA", away_team: "DAL", completed: false, prediction: null },
    { game_id: "4", home_team: "BOS", away_team: "NYK", completed: true, prediction: { home_win_prob: 0.50 }, home_pts: 110, away_pts: 99 },
  ]);
  assert.equal(out.rows[0].name, "LAL v GSW");
  assert.equal(out.rows[0].value, "50%");
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `node --test tests/teasers.test.mjs`

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `teasers.js`, selectors only**

Create `teasers.js`. **This task writes no DOM code.** Export the six functions above; the render and fetch come in Task 7.

```js
// teasers.js — the picks shown under each card on the Predictor hub.
//
// Two rules govern this file. First, every selector is a pure function over
// plain data: it takes an API payload and returns { label, rows, empty }. It
// touches no DOM and fetches nothing, which is what makes it unit-testable
// without a browser. Second, "no data" is a normal answer, not an error:
// every selector returns { rows: [], empty: "a sentence" } rather than
// throwing, so an offseason sport never breaks the board.
//
// The honesty rules from PRODUCT.md apply to every number rendered here: only
// picks made before the event count, a rebuilt pick is shown and labelled but
// never presented as a call, and no edge is ever shown without a real line
// behind it.

/** A percentage for a visitor. Anything not a finite number is a dash, so a
 *  null or a NaN can never reach the page as "NaN%". */
export function pct(x) {
  if (typeof x !== "number" || !Number.isFinite(x)) return "—";
  return `${Math.round(x * 100)}%`;
}

/** Display name for a driver. Prefers the API's real name; otherwise derives
 *  one the same way the F1 site does, so the hub and the site cannot disagree
 *  about who a driver is. */
export function driverName(driverId, realName) {
  if (realName) return realName;
  return String(driverId || "")
    .split("_")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

const byNumber = (key) => (a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity);

/** A rebuilt or backtest pick was made after the event. Showing it as a call
 *  would be the one thing this product must never do, so it is dropped. */
const isPreEvent = (source) => source === "tracked" || source === "live";

export function selectF1(races, predictions) {
  const race = (races || []).find((r) => !r.completed);
  if (!race) return { label: "Formula 1", rows: [], empty: "No races left this season" };
  const prediction = (predictions || {})[race.round];
  if (!prediction || !isPreEvent(prediction.source)) {
    return { label: race.race_name, rows: [], empty: "No pre-race pick for this race yet" };
  }
  const rows = (prediction.predictions || [])
    .slice()
    .sort(byNumber("p_win"))
    .slice(0, 3)
    .map((d) => ({
      name: driverName(d.driver_id, d.driver_name),
      value: pct(d.p_win),
      sub: `Podium ${pct(d.p_podium)}`,
    }));
  return { label: race.race_name, rows, empty: rows.length ? "" : "No driver predictions yet" };
}

export function selectPL(payload) {
  const week = (payload?.fixtures_by_gameweek || {})[payload?.current_gameweek];
  const fixtures = (week?.fixtures || []).filter((f) => !f.finished);
  if (!fixtures.length) return { label: "Premier League", rows: [], empty: "No fixtures this gameweek" };
  const strongest = fixtures
    .slice()
    .sort(
      (a, b) =>
        Math.max(b.predicted_home_win, b.predicted_draw, b.predicted_away_win) -
        Math.max(a.predicted_home_win, a.predicted_draw, a.predicted_away_win),
    )[0];
  const pick =
    strongest.predicted_draw >= Math.max(strongest.predicted_home_win, strongest.predicted_away_win)
      ? "Draw"
      : strongest.predicted_home_win >= strongest.predicted_away_win
        ? strongest.team_home
        : strongest.team_away;
  const value = Math.max(strongest.predicted_home_win, strongest.predicted_draw, strongest.predicted_away_win);
  const row = {
    name: `${strongest.team_home} v ${strongest.team_away}`,
    value: pct(value),
    pick,
    sub: strongest.predicted_scoreline ? `Most likely score ${strongest.predicted_scoreline}` : "",
  };
  // An edge is only ever shown when the feed says a real price exists.
  if (strongest.has_live_odds && (strongest.value_bet_flags || []).length) {
    row.edge = `Value: ${strongest.value_bet_flags.join(", ").replace(/_/g, " ")}`;
  }
  return { label: "Premier League", rows: [row], empty: "" };
}

export function selectFootball(games, predictions) {
  const upcoming = (games || []).filter((g) => g.home_score == null && g.away_score == null);
  if (!upcoming.length) return { label: "", rows: [], empty: "No games left this week" };
  const closest = upcoming
    .map((g) => ({ game: g, p: (predictions || {})[g.game_id] }))
    .filter((x) => x.p && Number.isFinite(x.p.home_win_prob))
    .sort((a, b) => Math.abs(a.p.home_win_prob - 0.5) - Math.abs(b.p.home_win_prob - 0.5))[0];
  if (!closest) return { label: "", rows: [], empty: "No picks for this week's games yet" };
  const { game, p } = closest;
  const row = {
    name: `${game.home_team} v ${game.away_team}`,
    value: pct(Math.max(p.home_win_prob, p.away_win_prob)),
    pick: p.home_win_prob >= p.away_win_prob ? game.home_team : game.away_team,
    sub: game.gameday ? new Date(game.gameday).toUTCString().slice(0, 22) : "",
  };
  // A line on some other game says nothing about this one.
  if (game.spread_line != null) row.edge = `Line ${game.home_team} ${game.spread_line}`;
  return { label: "", rows: [row], empty: "" };
}

export function selectNBA(games) {
  const open = (games || []).filter(
    (g) => !g.completed && g.prediction && Number.isFinite(g.prediction.home_win_prob),
  );
  if (!open.length) return { label: "NBA", rows: [], empty: "No games with a pick right now" };
  const game = open
    .slice()
    .sort((a, b) => Math.abs(a.prediction.home_win_prob - 0.5) - Math.abs(b.prediction.home_win_prob - 0.5))[0];
  const p = game.prediction;
  return {
    label: "NBA",
    rows: [{
      name: `${game.home_team} v ${game.away_team}`,
      value: pct(Math.max(p.home_win_prob, p.away_win_prob ?? 1 - p.home_win_prob)),
      pick: p.home_win_prob >= 0.5 ? game.home_team : game.away_team,
    }],
    empty: "",
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `node --test tests/teasers.test.mjs`

Expected: all pass. If the F1 `isPreEvent` check rejects a `source` the real API sends, widen it to the actual values rather than deleting the check.

- [ ] **Step 5: Commit**

```bash
git add teasers.js tests/teasers.test.mjs
git commit -F - <<'MSG'
feat: the hub's five selection rules, as pure functions

No DOM, no fetch. Each selector takes an API payload and returns
{ label, rows, empty }, which is what makes them testable under node --test
without a browser or a bundler -- the hub has no build step and never will
without a decision to add one.

These are the rules most likely to be subtly wrong, so they are the part
worth isolating. Two of them are easy to get backwards:

- NFL/CFB/NBA pick the game closest to a coin flip, min |home_win_prob - 0.5|.
  Not the biggest favourite, not the first in the list. A test pins that
  specifically, because "the model likes this one most" is the intuitive
  reading and it is the wrong one for this card.
- PL picks the strongest call, and a draw is a call in its own right. A
  fixture where the draw is the model's answer must not be skipped for having
  no favoured side. PRODUCT.md already calls this a toss-up.

"No data" is a normal return, never a throw: every selector gives
{ rows: [], empty: "a sentence" } so an offseason sport cannot break the board.

F1 drops rebuilt and backtest predictions. Showing a pick made after the race
as a pre-race call is the single thing this product must never do, and F1 is
the sport where the API actually carries that distinction.

Edge appears only where a real line exists -- PL on has_live_odds plus a
non-empty value_bet_flags, NFL/CFB on a non-null spread_line. A missing line
is a normal state and is never rendered as an implied edge.

Task 7 adds the fetch and the render on top of this. Nothing calls these
functions yet.
MSG
```

---

### Task 7: Fetch and render into the slots

**Files:**
- Modify: `teasers.js` — append the hydrate entry
- Modify: `index.html` — nothing, unless Task 5's script tag needs a `defer` equivalent (it does not; `type="module"` is deferred by default)
- Test: `tests/teasers.test.mjs` (append), `tests/hub.test.mjs` (already covers the tag)

**Interfaces:**
- Consumes: the four selectors and the five slots from Tasks 5 and 6; the proxy prefixes from Task 3.
- Produces: on DOM ready, each `.teaser` is filled and loses `aria-busy`.

- [ ] **Step 1: Write the failing test for the render contract**

Rendering needs a DOM, and this repo has no jsdom. Assert the *contract* textually instead, which is what the other hub tests do. Append to `tests/teasers.test.mjs`:

```js
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../teasers.js", import.meta.url), "utf8");

test("every teaser slot ends up with aria-busy removed, on every path", () => {
  // aria-busy is what tells a screen reader the region is still settling. If
  // any return path leaves it set, the region is announced as loading
  // forever -- the exact failure the Phase 1 audit found on the sport sites.
  assert.match(src, /aria-busy/, "aria-busy is never cleared");
  assert.match(src, /setAttribute\(\s*["']aria-busy["']\s*,\s*["']false["']/);
});

test("one failed sport never touches another sport's slot", () => {
  assert.match(src, /catch/, "no catch: a rejected fetch would leave the board half-filled");
  // Each sport is fetched in its own promise, not in one Promise.all, so a
  // single rejection cannot short-circuit the rest.
  assert.doesNotMatch(src, /await Promise\.all/, "Promise.all short-circuits on the first rejection");
});

test("the freshness of every pick is rendered", () => {
  // A pick shown without knowing when it was made is the rebuilt-after-kickoff
  // failure this product exists to avoid, and the hub is the one surface where
  // a visitor has no other context to catch it.
  assert.match(src, /generated_at|from the|snapshot/i);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `node --test tests/teasers.test.mjs`

Expected: the three new tests fail.

- [ ] **Step 3: Append the render to `teasers.js`**

```js
// --- rendering -------------------------------------------------------------

const SPORTS = [
  { sport: "pl", run: plTeaser },
  { sport: "f1", run: f1Teaser },
  { sport: "nfl", run: footballTeaser },
  { sport: "cfb", run: footballTeaser },
  { sport: "nba", run: nbaTeaser },
];

async function getJSON(path) {
  const response = await fetch(path, { headers: { accept: "application/json" } });
  if (!response.ok) throw new Error(`${path} responded ${response.status}`);
  return response.json();
}

/** One teaser row. Text only -- no innerHTML anywhere in this file, because
 *  every string in it comes from an API payload. */
function paintRow(row) {
  const el = document.createElement("div");
  el.className = "teaser-row";
  const name = document.createElement("span");
  name.className = "teaser-name";
  name.textContent = row.name;
  const num = document.createElement("span");
  num.className = "teaser-num";
  num.textContent = row.value;
  el.append(name, num);
  if (row.sub) {
    const s = document.createElement("span");
    s.className = "teaser-note";
    s.textContent = row.sub;
    el.append(s);
  }
  // Edge is rendered only when the selector set it, and the selector sets it
  // only when a real line exists. An absent edge renders nothing at all --
  // there is no "no edge" placeholder, because that would read as a claim.
  if (row.edge) {
    const e = document.createElement("span");
    e.className = "teaser-edge";
    e.textContent = row.edge;
    el.append(e);
  }
  return el;
}

function paintNote(text) {
  const p = document.createElement("p");
  p.className = "teaser-note";
  p.textContent = text;
  return p;
}

function paint(slot, { label, rows, empty }, sub) {
  slot.replaceChildren();
  if (label) {
    const head = document.createElement("span");
    head.className = "teaser-label";
    head.textContent = label;
    slot.append(head);
  }
  for (const row of rows) slot.append(paintRow(row));
  if (empty) slot.append(paintNote(empty));
  if (sub) slot.append(paintNote(sub));
  // Cleared on every path out of this function, including the caller's
  // catch, so no region is ever left announced as loading.
  slot.setAttribute("aria-busy", "false");
}
```

Then the four per-sport fetchers and the entry point:

```js
const freshness = (payload) => {
  const at = payload?.generated_at;
  if (!at) return "";
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? "" : `From the ${d.toISOString().slice(0, 10)} snapshot`;
};

async function plTeaser() {
  const week = await getJSON("/pl/api/fixtures/gameweek");
  const gw = week?.current_gameweek ?? week?.gameweek;
  const full = await getJSON("/pl/api/fixtures");
  const out = selectPL({ ...full, current_gameweek: gw });
  return [out, freshness(full)];
}

async function f1Teaser() {
  const races = await getJSON("/f1/api/races");
  const next = (races || []).find((r) => !r.completed);
  if (!next) return [selectF1(races, {}), ""];
  const prediction = await getJSON(`/f1/api/races/${next.season}/${next.round}/prediction`);
  return [selectF1(races, { [next.round]: prediction }), prediction.source ? `Source: ${prediction.source}` : ""];
}

async function footballTeaser(base) {
  const week = await getJSON(`${base}/api/current-week`);
  const games = await getJSON(`${base}/api/games?season=${week.season}&week=${week.week}`);
  const predictions = await getJSON(`${base}/api/predictions/${week.season}/${week.week}/batch`);
  return [selectFootball(games, predictions), ""];
}

async function nbaTeaser() {
  const games = await getJSON(`/nba/api/games/week?start=${new Date().toISOString().slice(0, 10)}`);
  return [selectNBA(games), ""];
}

function hydrate() {
  for (const { sport, run } of SPORTS) {
    const slot = document.querySelector(`.teaser[data-teaser="${sport}"]`);
    if (!slot) continue;
    // Each sport is its own promise. Promise.all would short-circuit on the
    // first rejection and leave the rest of the board empty, which is the
    // failure this file is written to avoid.
    run(sport)
      .then(([out, sub]) => paint(slot, out, sub))
      .catch((err) => {
        slot.replaceChildren();
        const note = document.createElement("p");
        note.className = "teaser-note";
        note.textContent = "Picks unavailable right now.";
        slot.append(note);
        slot.setAttribute("aria-busy", "false");
        console.warn(`hub teaser ${sport} failed`, err);
      });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", hydrate, { once: true });
} else {
  hydrate();
}
```

**Endpoint paths are the one thing in this task that must be verified against the running APIs before it is trusted.** The prefixes come from Task 3; the paths after them come from each repo's routes. Check them:

- PL: `frontend/src/api/client.ts` shows `/fixtures` and `/fixtures/gameweek`.
- F1: `@router.get("/races")` and `@router.get("/races/{season}/{round_}/prediction")`.
- NFL/CFB: `/current-week`, `/games?season=&week=`, `/predictions/{season}/{week}/batch`.
- NBA: `/games/week?start=`.

If a path 404s in a browser, fix the path here — do not add a new route to an API to make the hub work.

- [ ] **Step 4: Run the tests**

Run: `node --test tests/teasers.test.mjs tests/hub.test.mjs tests/craft-floor.test.mjs`

Expected: all pass.

- [ ] **Step 5: Verify in a real browser**

Serve the hub and the proxies locally — `caddy run --config Caddyfile` from `vps-stack`, or any static server plus five local API ports. Then open the hub and check, in this order:

1. All five cards render with JavaScript disabled.
2. Each teaser fills, and no console errors.
3. Kill one API. Only that one teaser changes to "Picks unavailable right now."
4. Kill all five. The board is still a working index of five sport links.
5. At 390 px, no horizontal scroll.
6. In DevTools, confirm the fetches are same-origin (200, not a CORS error).

Capture a 1440px and a 390px screenshot into `.impeccable/review/` as `desktop.png` and `mobile.png`.

- [ ] **Step 6: Run the mechanical detector**

Run: `/Users/sigey/.config/opencode/skills/impeccable/scripts/impeccable detect --json index.html teasers.js`

Fix anything mechanical it reports, then re-run once.

- [ ] **Step 7: Commit**

```bash
git add teasers.js .impeccable/review/
git commit -F - <<'MSG'
feat: the teasers fetch and render, one independent promise per sport

Each sport is fetched in its own promise rather than a Promise.all, and each
teaser is painted into a slot that already exists in the static HTML. A
rejected promise writes a one-line note into its own slot and touches nothing
else. That is deliberate: Promise.all short-circuits on the first rejection,
so one dead API would leave the other four teasers empty and a visitor would
read that as "the model has no picks" rather than "one site is down".

aria-busy is cleared on every path, including the catch. A region left with
aria-busy set is announced as loading forever, which is the exact P0 the
Phase 1 audit found on the sport sites' game cards.

The cards render from static HTML and are never gated on a fetch, so the page
degrades to what it is today: a working index of five sites. Verified with
every API killed.

Every teaser carries when its numbers were made. A pick shown without its
timing is the rebuilt-after-kickoff failure this product exists to avoid, and
the hub is the one surface where a visitor has no game context to catch it.

Endpoint paths were taken from each repo's own routes and client. If one 404s
in the browser, fix the path here -- do not add a route to an API to make the
hub work.
MSG
```

---

## Self-Review

**1. Spec coverage.** Every requirement in the spec maps to a task:

| Spec item | Task |
|---|---|
| T1 Caddy proxy | 3 |
| T2 `NaN` sanitising (NFL, F1) | 1, 2 |
| T3 teasers in `index.html` | 5, 7 |
| T4 F1 `driver_name` | 4 |
| T5 tests | 5, 6, 7 |
| Five teaser states (loading/content/empty/error/edge) | 6 (empty), 7 (loading, content, error, edge) |
| `isStarter`-style honesty — no edge without a line | 6 (`selectPL`, `selectFootball`) |
| No pick without its timing | 7 (`freshness`) |
| Cards never gated on a fetch | 5 (static slots), 7 Step 5 |
| One failure never touches another | 6, 7 (`Promise.all` test) |
| No `.status` span added | 5 Step 1 |
| Token parity preserved | 5 Step 4 (existing tokens only) |
| Out of scope: odds wiring, ROI claims, build step, cache | honoured — none appear |

**2. Placeholder scan.** No TBD, no "similar to Task N", no "add error handling". The one thing a reader must supply is Task 4 Step 1's instruction to find the existing test fixture — and it says exactly how (`grep -rln "p_win" tests/`) and forbids inventing one.

**3. Type consistency.**
- `pct`, `driverName` — defined in Task 6, used in Tasks 6 and 7. Consistent.
- `selectF1/selectPL/selectFootball/selectNBA` — all return `{ label, rows, empty }`; `paint` in Task 7 destructures exactly that. Consistent.
- `footballTeaser(base)` is called by `SPORTS` as `run(sport)`, so `base` receives `"nfl"`/`"cfb"`. Consistent, and it is why the parameter is named `base` and not `sport`.
- Every row field `paint` reads — `name`, `value`, `sub`, `edge` — is set by at least one selector in Task 6, and every one is optional-guarded. Consistent.

**4. Verified while writing this plan, not assumed:**
- `node --test "tests/*.test.mjs"` passes, **21 tests**, in `predictor-hub`. A bare `node --test tests/` fails on Node 24, so the glob form is a global constraint.
- `vps-stack` is a **separate git repo** on `main` with **no remote** and **no `tests/` directory**, and a dirty working tree. Task 3 is scoped and committed accordingly.
- The five proxy upstreams (`pl:8000`, `f1:8000`, `nba:8000`, `nfl:8001`, `cfb:8003`) are the ones already used by the existing `sports.{$DOMAIN}` block for the two football APIs; the other three are taken from the same file's top-level `reverse_proxy` lines.

---

## Execution Handoff

Plan complete. Recommended: **subagent-driven** — one fresh subagent per task, review between tasks. Seven tasks, four repos, and Task 3 needs a claim review specifically because it cannot be verified locally and must not be reported as working.
