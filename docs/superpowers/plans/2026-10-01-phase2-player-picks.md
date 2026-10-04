# Phase 2 — Model's Top Calls (player picks) Implementation Plan

**Status: executed on four surfaces, then withdrawn on F1.** Checked 2026-10-04
against merged PRs: Sports_Predictor #24 (NFL + CFB, then simplified by #25),
NBA_Predictor #22 with the §D availability gate in #23 (then #25), PL_Predictor #38
(then #40), hub #63, #72 and #69. F1_Predictor #26 shipped the per-market rows and
F1_Predictor #28 removed them, so F1 has no "Model's top calls" block. Spec:
`2026-09-30-fixture-insight-design.md` §H phase 2. The checkboxes below are the plan
as written, not the state of the work.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every fixture modal gains a ranked, visual, provenance-carrying list of the model's own top player calls — three rows per category at most, one category per list, and **an out player removed from the ranking entirely**.

**Architecture:** One new predictor-ui component renders a ranked list with a per-row visual; each sport's backend already produces the model numbers, so most of this phase is *wiring plus honesty*, not new modelling. The exception is NBA, which needs an in-sample MAE computed from data that exists and an availability gate wired from a source that exists — both in this phase, per decision 6.

**Tech Stack:** React 18 + TypeScript, Vite, Vitest + Testing Library, FastAPI + pandas per backend, `predictor-ui` vendored by `scripts/sync-ui.mjs`.

**Spec:** `docs/superpowers/specs/2026-09-30-fixture-insight-design.md` §C (per-sport rows), §D (availability), decision 6 (NBA in phase 2 **with** the gate). Read §C, §D and §F first.

## Global Constraints

Inherits Phase 1's constraints in full: never push to `main`, never merge; one branch and one PR per repo off a freshly fetched `origin/main`; test-first with the red output pasted and a stash-the-fix red proof for behaviour changes; tests never touch the network (hermetic runs under `HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9`); vendored `predictor-ui` is never hand-edited (hub first, then `sync-ui.mjs`, with `--check` green); desktop **and** 390px screenshots; never force-push.

**Phase-2-specific, binding on every task:**

- **The cap is not a quota.** At most three rows per category; fewer when fewer exist; never padded, never a fourth. A category that cannot fill three is not a category.
- **One category per list.** A rebounds row never appears under a points heading.
- **An out player leaves the ranking.** No list, no bar, no tile, no rank position. He appears once, below the lists, attributed and dated. "Flagged in place" is forbidden — see the spec's §D after #50.
- **Say what "confident" means per row, per sport.** A probability, a bucket hit-rate, or a projection ± MAE. Never an implied edge: **no odds feed exists in any repo**, so no row may claim one.
- **Provenance is per row**: a graded record where a ledger genuinely grades that row, an explicit "no graded record yet" where none does. Never a number borrowed from a different unit of analysis (see the PL correction below).
- **Banned wording**: "lock", "guaranteed", "best bet", "edge", "value". The name is **"Model's top calls"**.

---

## Measured baseline — and seven corrections to the spec

Measured on `origin/main`, 2026-09-30. SHAs: predictor-hub `bb91579`, PL_Predictor `f0de077`, NBA_Predictor `085d294`, F1_Predictor `1083389`, Sports_Predictor `f6db10d`, NFL_Predictor `a8e9bad`, CFB_Predictor `cc522c2`.

The spec's §C/§D were written from a stale survey. **Seven claims are wrong, and three of them would have shipped a dishonest number.**

| # | spec says | measured reality | consequence |
|---|---|---|---|
| 1 | PL: "anytime goal/assist/G+A prob (**Platt-calibrated** direct arm)" | Only `anytime_goal_contribution_prob` has a calibrator (`fit_goal_contribution_model`, a `LogisticRegression` Platt scaler). The other two arms are bare `1 - exp(-λ)` Poisson. Serving passes `_serving_blend_weight` = `NEUTRAL_BLEND_WEIGHT = 0.5`, so the G+A value is a **50/50 blend of calibrated and uncalibrated** — the module comment says so itself | PL probability rows **cannot** claim calibration. They show a bucket/brier context or say the arm is uncalibrated |
| 2 | PL: "scorer hit-rate + Brier **where ledger exists**"; per-player record implied | `get_scorer_accuracy()` returns `{snapshot, reconstructed}` — **aggregate only, never per player**. No per-player ledger exists | PL rows carry **no per-player record**. The honest row is the aggregate context, labelled as aggregate, or an explicit "no graded record per player yet" |
| 3 | NFL: "official injury reports + depth-chart flags (**gate props today**)" | `data/injuries.py` exists but is **dead code** — its only references are itself, its test and a plan doc; no route or pipeline calls it. Depth charts are attached but **explicitly refuse to gate** (`routes.py:625-630`: an unavailable chart leaves `is_starter` as `None`, because `False` "would be a different and much worse claim") | NFL's availability gate must be **built** (wire the injuries module), not merely surfaced |
| 4 | CFB: "same ledgers" | CFB's `_summarize_player_props` has **no kickoff filter at all**; NFL excludes snapshots taken at/after kickoff and reports them as `n_rebuilt` | CFB's track record **counts look-forward picks**. Must be fixed or the CFB record must not be shown |
| 5 | NBA: "projections ± in-sample MAE" | `models/player_props.py` is an `XGBRegressor` returning raw `predicted_value`; **no MAE exists anywhere**, and `PlayerPropOut` carries no probability field. `predict_double_double_probability` exists and has **zero callers** | The ± must be **computed** from resolved rows before any NBA row ships |
| 6 | NBA: "official injury report + ESPN (exist, unwired)" | `data/injuries.py` is a **stub returning hardcoded sample data** — a literal fake "LeBron James / Questionable" — and `_fetch_player_stats` returns `{}`. The real source is `data/espn.py::get_injuries()` → `[{team, player_name, status}]`, keyed by **`player_name`** while props are keyed by **`player_id`** | The gate needs an id-resolution join, **and the stub must never be imported by a production path** — see the warning below |
| 7 | F1: no driver news; no odds feed | Confirmed: zero matches for `news` repo-wide; the single `odds` hit is a comment saying there is none | None — the spec was right |

> **LANDMINE, stated plainly:** `NBA_Predictor/src/nba_predictor/data/injuries.py` returns **fabricated data** (a hardcoded injury for a named real player) behind a docstring that reads like a real fetch. If any production path imports it, the site reports an injury that does not exist. Task 2 must either delete it or make it raise, with a test that pins the failure — and must not "wire it up" as if it were a feed.

---

## File map

**`predictor-hub/packages/predictor-ui`** (Task 1 — every site re-syncs from it)
- Create `src/components/PicksList.tsx` — the ranked list: heading per category, ≤3 rows, per-row visual, provenance line, out-player line, empty state.
- Create `src/components/PicksList.test.tsx`.
- Modify `src/index.ts` — export `PicksList` and its types.
- No ranked-list component exists today. `StatTable` is the closest but is a `<table>` with a per-cell render hook; `FactorList` draws a direction triangle and carries no numeric visual. `StatusBadge`'s `nopick` status words as **"No pick yet"** and is the existing empty-state vocabulary.

**`NBA_Predictor`** (Task 2 — the gate and the ±, same phase)
- `src/nba_predictor/models/player_props.py` (MAE alongside each stat), `src/nba_predictor/api/schemas.py` (`mae` on `PlayerPropOut`), `src/nba_predictor/data/espn.py` (id resolution), `src/nba_predictor/data/injuries.py` (stub neutralised), `frontend/src/components/GameDetailModal.tsx`.

**`PL_Predictor`** (Task 3) · **`Sports_Predictor` + `NFL_Predictor`/`CFB_Predictor`** (Task 4) · **`F1_Predictor`** (Task 5) — one PR each.

## Order

Task 1 must merge before 2-5 (sites vendor the package). Tasks 2-5 are separate repos and run in parallel after it. **NBA's two halves are one task on purpose** — decision 6 forbids shipping NBA rows without the gate.

---

### Task 1: `PicksList` in predictor-ui

**Files:** create `packages/predictor-ui/src/components/PicksList.tsx` + `.test.tsx`; modify `src/index.ts`.

**Interfaces — later tasks depend on these exact names:**

```ts
export type PickRow = {
  key: string;            // stable per player+category
  name: string;
  team?: string;
  detail: string;         // the category, e.g. "Anytime TD"
  /** The model's own number for this category. Never derived here. */
  value: number;
  /** "probability" draws a share bar; "projection" draws a key number + ±. */
  kind: "probability" | "projection";
  /** Only for kind==="projection": the error margin, rendered as "± N". */
  margin?: number;
  /** Provenance, verbatim from the caller. Never composed by this component. */
  provenance: string;
  /** True when the row's number is a model probability in [0,1]. */
  out?: boolean;          // if true the row must NOT be passed — see OutPlayer
};
export type OutPlayer = { name: string; team?: string; source: string; dated: string };

export interface PicksListProps {
  title?: string;                     // defaults to "Model's top calls"
  categories: { category: string; rows: PickRow[] }[];
  out?: OutPlayer[];
}
export function PicksList(props: PicksListProps): JSX.Element | null;
```

- [ ] **Step 1: Failing tests first.** Cover, in this order: (1) heading per category with **at most three rows** — a four-row input renders three, and a one-row input renders one and is never padded; (2) a probability row draws a share bar and its percentage; (3) a projection row draws the key number **and** its `± N`, and never a percentage; (4) provenance text renders verbatim on every row; (5) an `out` player in the input is **refused** — the component throws or drops it with a named error, and a test asserts the refusal, because "removed, not flagged" must be enforced in code rather than by convention; (6) the `out` list renders once, below the categories, with source and date; (7) an empty category renders the honest empty state ("No pick yet") and never a fabricated zero; (8) no row ever renders a banned word — pass the banned list as a fixture and assert. Run RED; paste.
- [ ] **Step 2: Implement.** Reuse the real atoms: `ProbabilityBar` (with `minSegmentPx={2}`) for probability rows, `KeyNumberTile` for projection rows, `InstantHead`-style headings. Do **not** compose percentages for projections. Do not add a band chip. Keep the file focused; no fetching, no effects.
- [ ] **Step 3: Green, then the wiring test.** `npx vitest run && npx tsc --noEmit`. Add one test that asserts the harness `fixture.ts` invariant still passes — a picks row whose value disagrees with its category's kind must fail, so a yardage figure can never be rendered as a probability again.
- [ ] **Step 4: Screenshots + PR.** Desktop and 390px, three states (probability lists, projection lists, an out player below the lists). PR title `feat: PicksList — ranked top calls with a per-row visual and provenance`, body starting `Answers reviewer Phase 2 (task 1).` Never merge.

---

### Task 2: NBA — in-sample MAE **and** the availability gate, together

**Files:** `src/nba_predictor/models/player_props.py`, `src/nba_predictor/api/schemas.py`, `src/nba_predictor/data/espn.py`, `src/nba_predictor/data/injuries.py`, `frontend/src/components/GameDetailModal.tsx`, plus tests for each.

- [ ] **Step 1: Failing tests first.** (a) `PlayerPropOut` carries `mae`; the MAE is computed from **resolved** rows only, never from predictions that have no actual; a stat with no resolved rows yields `null` and the UI must then say "no error estimate yet" rather than `± 0`. (b) The gate: seed an ESPN-shaped injury for a player, assert that player's row is **absent from the ranked list** and appears once in the out line with source and date. (c) The name→id join: seed an injury whose `player_name` matches a prop row's `player_id` only via the team roster, and assert it resolves; and assert an unmatched name does **not** remove anyone (a false removal is worse than a missed one). (d) `data/injuries.py` no longer returns fabricated data — a test asserts calling it raises rather than yielding a named real player's injury.
- [ ] **Step 2: Implement.** MAE as a grouped aggregate over resolved rows, served on the props endpoint; no probability anywhere, so every NBA row is `kind: "projection"` and is labelled **"projection, not a probability"** — there is no probability to show, and the spec forbids inventing one. Wire `espn.get_injuries()` through an id resolution built on whatever the repo already has (measure first; if no roster→id map exists on the server, say so and stop rather than guessing a join).
- [ ] **Step 3: Verify.** Full backend suite (`cd src && uv run pytest` or the repo's documented command — read it, do not invent) plus `cd frontend && npx vitest run` (177 passing as of Phase 1) and `npx tsc --noEmit`; hermetic runs for both; stash-the-fix red proof pasted.
- [ ] **Step 4: Screenshots + PR.** Points/rebounds/assists/threes lists at desktop and 390px, each with its `±`, one with an out player removed and shown once below. PR title `feat: NBA top calls — projections ± MAE with the availability gate`, body starting `Answers reviewer Phase 2 (task 2).` **If the id join cannot be built from data that exists, stop and report — NBA rows do not ship without the gate (decision 6).**

---

### Task 3: PL — honest rows without a per-player ledger

**Files:** `frontend/src/components/PlayerScorerList.tsx` (the existing "Likely scorers & assists"), `frontend/src/components/FixtureModal.tsx`, tests.

- [ ] **Step 1: Failing tests first.** Categories are **goals** and **assists** (both fill three). `expected_saves` is **not** a category: it exists only for GK — exactly two rows per fixture — and the cap is not a quota. Rows state that the probability arm is uncalibrated where that is true (correction 1), and the record line is labelled **aggregate**, never presented as that player's own record (correction 2). An unavailable player (FPL status already multiplies the scale to 0) is removed from the ranking and shown once below.
- [ ] **Step 2: Implement** by reusing the data `PlayerRow` already holds — all three probabilities, availability, status, news — so no new endpoint is needed.
- [ ] **Step 3: Verify + screenshots + PR.** As Task 2's step 3-4. PR title `feat: PL top calls with per-arm honesty`, body starting `Answers reviewer Phase 2 (task 3).`

---

### Task 4: NFL and CFB — props rows, and the CFB record defect

**Files:** `NFL_Predictor/src/nfl_predictor/tracking/store.py`, `NFL_Predictor/src/nba_predictor/...` *(none)*, `NFL_Predictor` injuries wiring, `CFB_Predictor/src/cfb_predictor/tracking/store.py`, `Sports_Predictor/src/components/GameDetailModal.tsx` (or a new `PicksPanel`), tests. **One PR in Sports_Predictor for the UI; the backend fixes are one PR each in NFL_Predictor and CFB_Predictor** — three repos, and each says which phase it serves.

- [ ] **Step 1: Failing tests first.**
  - **NFL:** `anytime_td_prob` rows are `kind: "probability"` with the bucket hit-rate from `confidence_buckets` as context; yardage rows are `kind: "projection"` with `mean_absolute_error` as `±`. Categories: QB passing, RB rushing, WR/TE receiving — each fills three from a ~50-row slate.
  - **CFB (correction 4):** a row snapshotted **after** kickoff must not be counted in any market's `n_resolved`, and must be reported the way NFL reports it (`n_rebuilt`), mirroring `NFL_Predictor`'s `_snapshotted_after_kickoff`. Until that lands, **the CFB record must not be shown on a picks row** — assert that too, so the UI cannot show a look-forward-inclusive rate.
  - **Availability (correction 3):** wire `data/injuries.py` into the props path and assert an out player leaves the ranking. Assert that a **missing** depth chart still leaves `is_starter` as `None` and removes nobody — the existing code refuses to guess and that behaviour must survive.
  - **CFB has no injury or depth-chart source at all**: its rows must carry the **"no availability check"** flag (decision 5) and must not claim any player is available.
- [ ] **Step 2: Implement.** No new markets: `targets` is structurally NaN in CFB and must never get one (`models/player_props.py:8`).
- [ ] **Step 3: Verify + screenshots + PR.** Desktop and 390px, NFL and CFB. PR titles `feat: NFL top calls` / `feat: CFB props rows with the no-availability flag` / `feat: NFL+CFB picks panel`, bodies starting `Answers reviewer Phase 2 (task 4).`

---

### Task 5: F1 — per-driver calls, quali-aware

**Files:** `frontend/src/components/SessionTimelinePanel.tsx` and the per-market accuracy data it already fetches, tests.

- [ ] **Step 1: Failing tests first.** Race/sprint sessions list **win**, **podium**, **points finish**; **DNF appears only for race/sprint**, because `SESSION_MARKET_SPEC` defines no `dnf` market for qualifying — assert DNF is absent for a quali session rather than empty. Every row's provenance is the per-market ledger (`by_market[…].brier` / `hit_rate` / `avg_predicted_prob` with `n`). Rows are probabilities, not projections: `p_points_finish` is a probability and `expected_points` is the projection — **never mix the two in one row**, and never render `expected_points` as a percentage.
- [ ] **Step 2: Implement.** Keep the prediction table and ribbon untouched (decision 8).
- [ ] **Step 3: Verify + screenshots + PR.** PR title `feat: F1 top calls per market`, body starting `Answers reviewer Phase 2 (task 5).`

---

## Definition of done

- Every sport: ≤3 rows per category, one category per list, a per-row visual whose kind matches what the number is, provenance on every row, and an out player removed from the ranking and shown once below.
- **NBA ships with its gate, or does not ship.** CFB ships with its "no availability check" flag, and its record stops counting post-kickoff picks or is not shown.
- No row states an edge, a price, or a guarantee; no row borrows a record from a different unit of analysis; no probability is shown for an arm that is not calibrated.
- Hub package merged before any site re-syncs; every suite green, hermetic, drift clean; desktop + 390px screenshots on each PR; nothing merged by the agent.

## Explicitly NOT in Phase 2

Player news surfaces (phase 3), the AI callout rewrite and the validator's non-overlap rule (phase 4), and any probability layer for NBA — `predict_double_double_probability` exists and is unused, and turning it into a served, calibrated probability is a separate piece of work with its own calibration evidence, not a phase-2 side effect.