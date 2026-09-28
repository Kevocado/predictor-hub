# Plan A — predicted box score, track record, and the revised teasers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A predicted box score on every fixture detail; a track record that shows everything it tracks; and hub teasers that follow the next F1 session and show a second pick.

**Architecture:** One presentational `BoxScore` component authored in `predictor-ui` and vendored into each site, because a component written directly into a sport site is a defect. Track-record work is backend-first (the numbers must exist before they can be shown). The teaser changes are hub-only, except A4.1 which needs one new field from the F1 API.

**Tech Stack:** React 19 + Tailwind 4 + Vite (Sports), React + Vite 6 (NBA), Python 3.11+ / FastAPI / pydantic 2.13.5 (APIs), `node --test` (hub), vitest (predictor-ui and the sites).

**Spec:** [../specs/2026-09-27-predicted-box-score-and-track-record-design.md](../specs/2026-09-27-predicted-box-score-and-track-record-design.md) — sections A0–A6 and B1–B8. The spec is the authority; this plan is its argument.

## Global Constraints

- **Author shared components in `predictor-hub/packages/predictor-ui` first, then run `scripts/sync-ui.mjs`.** Each site vendors the result into `src/predictor-ui/`, and `SYNC.json` records the source commit. A component written directly into a sport site is a defect, and a sync that is skipped is a defect.
- **Three APIs declare 9 / 0 / 0 `response_model`s respectively (F1 / NFL / CFB).** F1 returns snapshot dicts *through* pydantic; NFL and CFB return them raw. Any change to a field F1's schemas validate is a 500 risk on four endpoints.
- **pydantic 2.13.5 serialises `NaN` to `null` and rejects `None` for a non-optional `float`.** Widening a schema and sanitising a snapshot are two halves of one change; in that order.
- **NFL's `public_snapshot` accessor `_snapshot_week()` discards the top-level `generated_at`.** It is only reachable via the new `/snapshot-meta` endpoint. Do not widen existing payloads to carry it.
- **nflverse depth charts:** a player is a starter when `depth_team == 1` within their `depth_position`. Verified against Miami 2024 week 19. There is no `backups` column and no within-position ordering — that rule is the source, not a heuristic.
- **`club_code` joins straight onto `recent_team`; both are already abbreviations.** No name mapping.
- **CFBD has no depth-chart field** (`cfbd` 5.31 `RosterPlayer`) and no depth-chart endpoint. A1 settles whether the game box score carries a `starter` flag; if not, CFB renders `isStarter: null` and says so.
- **12 px text floor, 4.5:1 contrast, tabular numerals, no meaning carried by colour alone.**
- **Honesty rules:** only picks made before the event count toward the headline; a rebuilt pick is counted and shown separately (B8) and never hidden; no profit, ROI or "beats the bookies" claim anywhere; no `NaN` ever reaches a rendered number; every pick is displayed with the time it was made.
- **Commit bodies are written for a future AI session:** what changed, why, what was ruled out and why, what the next session must not undo. Explicit project requirement.
- Run hub tests with `node --test "tests/*.test.mjs"` — a bare directory fails on Node 24. Hub suite is at **49 passing** before this plan's tasks.

---

## Execution order and why

```
A0  BoxScore component  ──┬─> A1  CFBD spike ─> A2  NFL depth charts ─> A3  CFB
   (predictor-ui)        │                       └─> A4  Sports frontend ─> show Kevin ─> A5  NBA
                         │
                         └─> A4.3  most-confident pick  (hub, no backend)
                             A4.1  F1 session_datetime (F1 API) ─> A4.2  F1 next session

B1  bucket contract ─> B2  bar ─> B3  weeks ─> B4  totals ─> B5  vs market
                                                          └─> B6  frontend ─> B7  NBA
                                                              └─> B8  the full record
```

**A0 is first** because A4 and A5 both consume it. **A4.1 before A4.2** because the hub cannot implement the session rule without the field — A4.2 is blocked on it, not merely easier after it. **B8 after B6's shape exists** so the new figures land in the page that already displays the old one.

A and B share `predictor-ui` and the `sync-ui.mjs` commit stream, so they must not run concurrently in the same package. A first, show Kevin, then B.

---

### Task A0 — the shared `BoxScore` component

**Files:**
- Create: `packages/predictor-ui/src/components/BoxScore.tsx`
- Modify: `packages/predictor-ui/src/index.ts` (export it)
- Test: `packages/predictor-ui/src/components/boxscore.test.tsx`
- Then: run `scripts/sync-ui.mjs` to vendor into `Sports_Predictor` and the NBA site

**Interfaces:**
- Consumes: nothing.
- Produces: `BoxScore`, `BoxScoreRow`, `BoxScoreColumn`, `BoxScoreGroup`, `BoxScoreTotal` — the exact types in the spec's A0 section, verbatim. A4 and A5 build their rows against these and must not redefine them.

- [ ] **Step 1: Write the failing test** for the three starter states, the em-dash for a null value, and that a `rows` array is rendered in the order given without reordering. The spec's A0 types are the contract; transcribe them.
- [ ] **Step 2: Run it, watch it fail** — `cd packages/predictor-ui && npx vitest run src/components/boxscore.test.tsx`
- [ ] **Step 3: Implement `BoxScore`** as **presentational**: the caller groups, sorts and chooses columns; the component renders the grid, the position headers, the starter/bench rail, the team totals rows and the three starter states. It never fetches and never reorders — `rows` is rendered as given. `isStarter: null` renders the visible "Projected order" treatment, never a silent blank.
- [ ] **Step 4: Run it, watch it pass**, then the full package suite and `npx tsc --noEmit`.
- [ ] **Step 5: Commit** in `predictor-hub`, then run `scripts/sync-ui.mjs` and commit the vendored copy in each consuming site **separately** — one commit per repo, never mixed.

---

### Task A1 — spike: does CFBD expose a starter flag?

**Why it is first in the backend chain:** it decides CFB's entire shape, and it is cheap.

**Files:** none. This task produces a documented answer, not code.

- [ ] **Step 1: Read `CFB_Predictor/src/cfb_predictor/data/player_stats.py`** and find the athlete objects in the `game → team → category → type → athlete` tree. The flattener at `:118` currently reads only `id`, `name`, `stat`.
- [ ] **Step 2: Determine whether the athlete carries `starter`.** Check the installed `cfbd` 5.31 models for a field on the game-player-stat athlete, and check `tests/` fixtures for a real captured payload. If an API key is available, make one live call. **Do not guess** — an unverified assumption here becomes a fictional depth chart on a public site.
- [ ] **Step 3: Record the finding** in the SDD ledger with the evidence, and branch A3 on it: `starter` present → source it from the box score; absent → `isStarter: null` with the visible "Projected order" treatment, which is already A0's job to render.
- [ ] **Step 4: Commit** the ledger note only if a repo file records it.

---

### Task A2 — NFL depth charts, and a real starter flag

**Files:**
- Create: `src/nfl_predictor/data/depth_charts.py`
- Modify: `src/nfl_predictor/api/routes.py` (`_get_player_props_live`), `public_snapshot.py`
- Test: `tests/test_depth_charts.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `fetch_starters(season, week) -> dict[str, dict]` returning `{player_id: {is_starter, depth_slot}}` keyed on `gsis_id`; and on each player prop, `is_starter: boolean | None` plus `depth_slot: int | None`, threaded through the public snapshot. A4 reads both.

- [ ] **Step 1: Failing test** for the starter rule: given a depth chart frame, `depth_team == 1` within a `depth_position` is a starter. Use a real-shaped fixture — Miami 2024 week 19 returns Tua at QB1 and Tyreek and Jaylen Wright both at WR1, and Jaylen appears at RB1 *and* WR1, which is the case that proves the rule keys on `depth_position` and not on the player.
- [ ] **Step 2: Watch it fail.**
- [ ] **Step 3: Implement** `data/depth_charts.py` as cache-or-fetch per season into `data/cache/depth_charts/{season}.parquet`, matching the existing `player_stats` cache pattern. Resolve to the most recent published chart at or before `week` — the current depth chart is what an upcoming game will use, and that may be last season's. **A fetch failure must not break props**: log, return no flags, and let the UI fall back to "Projected order", the same state CFB may be in.
- [ ] **Step 4: Thread the fields** through `_get_player_props_live` and into the snapshot. Both must reach `public_snapshot.json` — public mode is what the VPS serves, and a field missing there is invisible in production.
- [ ] **Step 5: Regenerate the snapshot**, run the full suite, commit.
- [ ] **Step 6: Verify on the VPS path** that `/api/players/{season}/{week}/props` returns `is_starter`.

---

### Task A3 — CFB starter flag, per A1's finding

**Files:** `src/cfb_predictor/data/player_stats.py`, `api/routes.py`, `public_snapshot.py`; test in `tests/`.

Same shape as A2 minus the depth-chart source. If A1 found no `starter` flag, this task still runs and still emits `is_starter: None` — explicitly, so the absence is a decision on the record rather than an oversight, and so A4's fallback is exercised by CFB from day one.

---

### Task A4 — the Sports (NFL + CFB) fixture detail

**Files:** `Sports_Predictor/src/components/GameDetailModal.tsx`; `src/lib/playerRank.ts`; new `src/lib/boxScoreRows.ts` (the caller-side shaping, so the presentational component stays presentational). Tests alongside each.

**Interfaces:**
- Consumes: `BoxScore` and its types from A0; `is_starter`/`depth_slot` from A2/A3.
- Produces: the box score replacing the "Model Player Projections" list.

- [ ] **Step 1: Failing test** for the column sets per position, the three-state team control defaulting to **Both**, and that rows order starters-then-bench in depth-chart order.
- [ ] **Step 2: Implement** in `boxScoreRows.ts`: group by position, order by `isStarter` then `depth_slot`, build the two-line rows. Columns exactly the model's markets — QB `Pass yds · TD %`; RB `Rush yds · Carries · Rec yds · Rec · TD %`; WR and TE `Rec yds · Rec · TD %`. **No dashed-out FanDuel columns.**
- [ ] **Step 3: Wire it in**, retiring the position-filter button row (the grouping replaces it) and removing the "Team Yardage Predictions" cards, which the totals rows supersede.
- [ ] **Step 4: Run** the site suite, `tsc -b`, and the impeccable detector on the changed files. Fix what it reports.
- [ ] **Step 5: Screenshot** the detail at 1440 and 390 into `.impeccable/review/`. **Then measure, do not eyeball** — `getBoundingClientRect` on the rows against their container. A live render on this feature already hid a panel that was 10–28px shorter than its content, and a screenshot alone did not catch it either; the measurement did.
- [ ] **Step 6: Commit**, and show Kevin before A5.

### Task A4.1 — `session_datetime` on the F1 API

**Files:** `F1_Predictor/src/f1_predictor/api/schemas.py`, `api/routes.py`, `public_snapshot.py`; test in `tests/`.

- [ ] **Step 1: Failing test** for the session payload carrying a datetime, and for the weekend ordering helper: on a sprint weekend the order is `sprint_qualifying → sprint → qualifying → race`; on a normal weekend it is `qualifying → race`. `_session_types_for` in `public_snapshot.py:70` already encodes the *set*; the order is new.
- [ ] **Step 2: Implement.** The routes already compute session timing internally to choose `tier` (`_pick_timing`); **expose that value, do not recompute it.** Widen any schema that validates these payloads in the same commit — pydantic rejects `None` for a non-optional field, and a new field on a `response_model` is a validation risk on four endpoints.
- [ ] **Step 3: Regenerate the snapshot**, run the full suite, commit.

### Task A4.2 — the hub's F1 teaser follows the next session

**Files:** `predictor-hub/teasers.js`, `tests/teasers.test.mjs`.

- [ ] **Step 1: Failing test.** Given a round with qualifying in the past and the race in the future, the teaser shows the race. Given a round with qualifying in the future, it shows qualifying. Given a round with a race prediction already computed but the race still in the future, it must **not** show the race — the availability-based shortcut is the bug this test exists to prevent, because the snapshot ships future race predictions with `source: live`.
- [ ] **Step 2: Implement.** `selectF1` takes the next incomplete round, walks sessions in real-world order, and shows the earliest whose `session_datetime` is still in the future, falling back to the race. Reuse the existing `isPreEvent` whitelist — a session prediction that is `rebuilt` or `backtest` is still not a call.
- [ ] **Step 3: Run** `node --test "tests/*.test.mjs"`, expecting 49 + the new tests.
- [ ] **Step 4: Commit, deploy the hub, and verify in a browser.** Confirm on the live page that the F1 card names a *session* rather than always a race, and measure for overflow rather than trusting the text.

### Task A4.3 — a second row: the most confident pick

**Files:** `predictor-hub/teasers.js`, `tests/teasers.test.mjs`. **No backend work** — both rows come out of arrays the hub already has.

- [ ] **Step 1: Failing test** that the American-football, PL and NBA teasers return two rows: row 1 the closest game (`min |p − 0.5|`), row 2 the most confident (`max(p, 1 − p)`), and that they are **not the same game** unless it genuinely is both. A test that passes when the two are identical is not testing anything.
- [ ] **Step 2: Implement.** Keep the existing return contract `{ label, rows, empty }` and let `rows` carry two entries. Label them so they are not read as one pick. F1 is unchanged — its three drivers are a different shape and gain no second group.
- [ ] **Step 3: Run** the full suite, commit, deploy, and check the live page at 1440 and 390.

### Task A4.4 — a teaser row links to its game

**Scope, measured 2026-09-28 — read before estimating.** This is per-site work, not a hub change:

- `Sports_Predictor` (NFL + CFB) reads `?sport=` but has **no `?game=`**. `selectedGame` is internal state at `GamesPage.tsx:216`. Add: read a game identifier on load, and open that game's detail when it matches.
- `NBA_Predictor` has **no query-param support** in `App.tsx` or `GameCard.tsx`. Add the same, with its own parameter name.
- PL and F1 route by path. **Read their route tables before choosing a URL** — do not invent a shape the site does not serve.

- [ ] **Step 1: Failing test per site** that a game identifier on the URL opens that game's detail, and that an unknown identifier degrades to the normal list rather than an error.
- [ ] **Step 2: Implement** the parameter handling in each site, one commit per repo.
- [ ] **Step 3: Hub side.** `paintRow` emits a real `<a>` when the row carries an href, and a plain row when it does not — so a site without deep-link support shows a row that plainly is not clickable rather than one that looks clickable and goes nowhere. The accessible name must contain the game.
- [ ] **Step 4: Verify in a browser, per sport.** Click through and confirm the right game opens. A link that 404s or opens the wrong game is worse than no link.

---

### Task A5 — NBA fixture detail

Same `BoxScore` component. **Read the NBA prop feed before writing the column list** — points, rebounds, assists and 3PM are the likely set, but do not assume parity with the NFL columns. Confirm whether NBA has real starter data before assuming `isStarter` is non-null; if it does not, `null` is the correct value and the component already renders it honestly.

---

## Sub-project B — the track record

### Task B1 — fix the bucket contract divergence

**This is a live bug, not an enhancement.** `NFL_Predictor/.../store.py:353` emits `{bucket, n_resolved}`; `Sports_v2/src/types.ts:44` declares `{label, n}`. So `bucket.n` is `undefined`, the guard `some((b) => b.n > 0)` at `TrackRecordPage.tsx:136` is `false`, and **the anytime-TD calibration section has never rendered on the NFL site.** CFB emits the matching keys and works.

Fix by making both APIs emit `{label, n, hit_rate}`. Add a test per API asserting the emitted keys, and a frontend test that renders a non-empty bucket set and asserts the section appears — the gap that let this ship.

### Task B2 — fix the weekly bar

`TrackRecordPage.tsx:102` sets bar width to `(n_games / max_games) * pct_moneyline_correct * 100`, which multiplies accuracy by a volume share, so a week with fewer games draws a *shorter* bar at a *higher* accuracy. Accuracy and volume are two different questions and get two different encodings: a 50% reference marker on the accuracy scale, and `n_games` as text beside it.

### Task B3 — every elapsed week

`_summarize_games` returns rows only for weeks that happen to have tracked games, so a week with no picks vanishes instead of reading "not tracked". Return a row for every week from 1 to the current one, each carrying moneyline, ATS and totals accuracy with counts, and `tracked: false` where there was nothing. One request, not three.

### Task B4 — predicted total and margin

New nullable columns on `game_predictions` for `predicted_total` and `predicted_margin`, recorded at snapshot time from the response that already produces `over_prob`. `ALTER TABLE` matching the existing migration style; existing rows stay `NULL` and are **excluded** from these metrics, never counted as zero. Expose total MAE, signed error, and both by week.

**This is the "total yards change", and it does not exist today** — the model computes both (`game_outcome.py:62`) and the tracker drops them. Note the migration runs on the live SQLite file on the Azure Files mount, where the repo already carries a fix for file locking; treat it with the same care as the existing ALTERs.

### Task B5 — model vs the market

Implied probability from a closing line is `Φ(spread / σ_league)`, with `σ_league` a single named constant per sport, asserted in a test so it cannot drift. Edge is model cover probability minus that, in points. Plus a **disagreement cohort**: games where the model backed the side the line did not favour, and the hit rate within it. `σ_league` and what "edge" means are stated in words on the page. Framed as agreement with a price, never as profit.

### Task B6 — the track record frontend

Everything recorded gets shown, and every number carries its `n`: headline accuracy with games counted and the rebuilt count stated; every elapsed week across three markets; anytime-TD hit rate with `n_called`, Brier score and the calibration buckets (needs B1); each yardage market with MAE, signed error and `n`; the `by_position` tables, which are computed today and never rendered; predicted vs actual totals, overall and by week; and the B5 block. The page gets a sticky section nav, because it is scanned rather than read.

### Task B7 — NBA track record

`TrackRecordPanel` is a four-column table over `/hub/track-record` and is well behind the NFL/CFB bar. Bring it to parity reusing the same components. NBA has a `/calibration` endpoint — check whether its data is already fully surfaced before adding anything.

### Task B8 — the full record, beside the pre-kickoff one

**Backend.** `get_track_record` currently drops rebuilt rows from `_summarize_games` and returns only `n_rebuilt`. Keep that for the headline; add a sibling summarising **all** resolved rows with rebuilt included, plus a `per_pick` list — one row per resolved game, hit and miss alike, with `rebuilt` on each row.

**Frontend.** Two figures, unmistakably labelled — "Made before kickoff" as the headline, "All tracked picks" beneath it with one line on why they differ. Then the per-pick table, hits and misses in the same list, never filtered or collapsed by default. Kevin's ask was to stop losing sight of the picks that have already passed; this is the shape that delivers it without letting a post-hoc 100% stand in for skill.

**`PRODUCT.md` changes in the same commit.** Its brand commitment currently says rebuilt picks "never count toward any hit rate", which B8 makes false. Reword to: the pre-kickoff record is the headline and rebuilt picks never count toward it; they are counted and shown separately, and every resolved pick is listed. The honesty rule survives; the sentence does not.

---

## Risks

- **CFBD has no depth chart** (verified). CFB may ship with `isStarter: null`. A recorded outcome, not a blocker.
- **Depth charts lag.** nflverse publishes after games are played, so a week-1 game uses the most recent available chart, possibly last season's. Correct behaviour; the UI must not imply freshness it lacks.
- **F1 session timing is a new field on a validated payload** (A4.1). Get the widening and the field in one commit or four endpoints 500.
- **Snapshot staleness.** Public mode serves `public_snapshot.json`; a new field is invisible until CI regenerates it, which makes a correct backend change look broken locally.
- **B4 is a migration** on a live SQLite file on a mount with a known locking problem.
- **A box score cannot fit a phone screen.** 22 starters will not fit 390px. The acceptance test is one team's starters plus its total, with bench below the fold — stated so nobody "fixes" it by dropping rows.

## Out of scope

- Any win, profit or ROI claim.
- Fumbles, attempts, completions, interceptions — not modelled, so not shown.
- Replacing the broadcast-scoreboard visual world. This extends it.
- A CFB depth-chart feed.
- Client-side caching on the hub.
