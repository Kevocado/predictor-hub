# Matchup table: home vs away, colour-coded ranks, every sport

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (one fresh subagent per task, review between). Steps use `- [ ]`.

**Goal:** replace the alternating, bar-based Matchup list with a home-left / away-right comparison table whose metric labels sit in the middle and whose cells are rank boxes coloured by thirds (green / yellow / red). One shared component for every sport.

**Requested by Kevin, 2026-10-10**, from the live PL Bournemouth v Sunderland fixture, where the rows alternated sides ("Brighton goals scored #1, Sunderland goals conceded #16, Sunderland recent form #14, Brighton recent form #3 ...") so no team could be read down a column. He dislikes the bars. Wanted: home team on the LEFT and away on the RIGHT matching the team order in the header above; the metrics (goals scored, goals conceded, attack and defence rating, ...) as a list in the MIDDLE; a box at each side holding the team's rank, coloured by position; "make this across the site".

**Architecture:** the data already carries everything needed; no backend change. `packages/predictor-ui` (the single source the four sites vendor) gets a pure pivot function, a `MatchupTable` component and a rank-colour helper; `MatchupBrief` renders the table. Sites re-vendor and redeploy.

**Tech stack:** React + Tailwind (shared tokens), vitest, the hub's harness (`packages/predictor-ui/harness/insight.tsx`), `scripts/sync-ui.mjs`.

**Specs/context:** `docs/superpowers/specs/2026-10-10-matchup-summary-design.md` (duels stay neutral: no "advantage", no arrows, `toward_pick` is null); `PRODUCT.md` (fans on phones first, desktop supported).

## Global constraints

- Home on the LEFT, away on the RIGHT, in every row, in every sport, matching the header order. Never alternate.
- Rank 1 is the BEST everywhere. Verify against real data per sport before relying on it (the explainer already says "rank 30 of 32 = weak rush defence").
- Colours are THREE DISCRETE tiers by thirds of the field, not a gradient (see Task 1 for the exact rule).
- No bars. No "advantage", "favours", arrows or any directional wording.
- Colour is never the only signal: the rank number is printed in the box and the cell has an aria-label with the ordinal and total.
- Text on every box colour meets 4.5:1 contrast in BOTH light and dark themes.
- Mobile first: 375px, three columns, no horizontal scroll, keep the 16px page gutter.
- Missing data: a half-present pair shows an em dash on the missing side; nothing drawable renders nothing (no heading, no placeholder). Keep the `isText`/`isInt` row validation and its regression test from hub#101 (one malformed row never breaks the page).
- Offline tests, REAL data shapes (use the live rows below), TDD red-green. Branch + PR per task, never push to main, read every check line before merge, `scripts/coderabbit.sh` gate exit 0 (never piped).

## What the data gives (verified live 2026-10-10; do not change any backend)

`context.matchups` rows: `{id, attacker, defender, stat, foil, attacker_rank, defender_rank, n_teams, toward_pick: null}`. Every duel id ends in `:home` or `:away`, the ATTACKER's side:

- NFL/CFB: `rush_off_vs_rush_def:home`, `pass_off_vs_pass_def:away`, ...
- PL: `strength_attack_vs_defence:home|away`, `goals_attack_vs_defence:home|away`, plus an UNSUFFIXED `form` row whose attacker is the HOME team and whose defender is the AWAY team (the same stat on both sides).
- NBA: `rating`, `reb`, `fg3_pct`, `fg_pct`, `pace` with the same suffix (check whether `pace` is a single both-sides row, and treat any unsuffixed row like PL's `form`: attacker = home).

For a duel type T (the id before the colon):

- `T:home` -> home OFFENCE rank = `attacker_rank` (label = `stat`); away DEFENCE rank = `defender_rank` (label = `foil`).
- `T:away` -> away OFFENCE rank = `attacker_rank`; home DEFENCE rank = `defender_rank`.

Rows arrive "strongest first", which is what makes the sides alternate today. Never rely on row order.

Team names for the column headers come from the rows (attacker of a `:home` row = home team; attacker of an `:away` row = away team). Do not match names against the site bundle: names differ across sources.

Live example (PL, Bournemouth v Sunderland, event `ockw-Aksg-QRth`), the test fixture for Task 1:

```
strength_attack_vs_defence:home | Bournemouth attack strength 11 vs Sunderland defence strength 3
goals_attack_vs_defence:home    | Bournemouth goals scored per match 11 vs Sunderland goals conceded per match 16
strength_attack_vs_defence:away | Sunderland attack strength 19 vs Bournemouth defence strength 16
form                            | Bournemouth recent form (points per match) 17 vs Sunderland recent form (points per match) 14
goals_attack_vs_defence:away    | Sunderland goals scored per match 11 vs Bournemouth goals conceded per match 10   (n_teams 20 on every row)
```

Expected table (home | metric | away), n = 20:

```
Bournemouth            |                                  | Sunderland
11                     | Attack strength                  | 19
16                     | Defence strength                 | 3
11                     | Goals scored per match           | 11
10                     | Goals conceded per match         | 16
17                     | Recent form (points per match)   | 14
```

(Home DEFENCE comes from the `:away` row's `defender_rank`; away DEFENCE from the `:home` row's `defender_rank`.)

F1 has no home/away: `context.form_rows` `{id, subject, label, value, rank, n}` render as a plain list with the same coloured rank box at the right (rank of n), no columns.

## Task 1: pivot, colour tiers, table component (hub)

**Files:**
- Create: `packages/predictor-ui/src/lib/pivotMatchups.ts`, `packages/predictor-ui/src/lib/rankTier.ts`, `packages/predictor-ui/src/components/MatchupTable.tsx`
- Modify: `packages/predictor-ui/src/components/MatchupBrief.tsx` (render the table), `packages/predictor-ui/src/index.ts` (exports), shared tokens file (add the three rank colours, light + dark), `packages/predictor-ui/harness/insight.tsx` (cases)
- Tests: `packages/predictor-ui/src/lib/pivotMatchups.test.ts`, `rankTier.test.ts`, `src/components/matchupTable.test.tsx`; update `matchupSection.test.tsx`

**Interfaces:**
- Produces: `pivotMatchups(rows: MatchupRow[]): { home: string; away: string; rows: { key: string; label: string; homeRank: number | null; awayRank: number | null; n: number }[] } | null` (null when nothing drawable); `rankTier(rank: number, n: number): "good" | "mid" | "bad"`; `<MatchupTable pivot={...} />`.
- Consumes: `MatchupRow` / `FormRow` types already exported (hub#100/#101).

### Colour rule (the user's choice: thirds)

Let `third = Math.ceil(n / 3)`. Then:

- `rank <= third` -> **good** (green)
- `rank <= 2 * third` -> **mid** (yellow)
- otherwise -> **bad** (red)

n = 20: green 1-7, yellow 8-14, red 15-20. n = 32: green 1-11, yellow 12-22, red 23-32. n = 30: 1-10 / 11-20 / 21-30. Ranks outside 1..n are not drawn (validation already drops them).

- [ ] **Step 1: failing tests for the pivot.** Feed the five live PL rows above; assert the exact expected table (home left on every row, no alternation), including the home-defence-from-`:away` mapping, label casing, row order (types in first-appearance order, offence then defence, unsuffixed rows last), and the header names. Add: an NFL three-row case; a one-sided case (only `:home`) giving an em-dash/null on the missing side; a malformed row dropped; empty input returns null; row order shuffled gives the same table.
- [ ] **Step 2: failing tests for `rankTier`.** The boundary ranks for n = 20, 30, 32 and n = 2 and 3 (tiny fields); rank 1 is always good, rank n always bad.
- [ ] **Step 3: implement `pivotMatchups` and `rankTier`** (pure functions, no I/O) and make the tests pass.
- [ ] **Step 4: failing component tests.** Home name left / away name right in the header; the three columns per row; each rank box shows only the number; aria-label "Bournemouth: 11th of 20 for goals scored per match"; tier class per box; no bar/progress elements in the DOM; a half-present row shows an em dash; nothing drawable renders nothing.
- [ ] **Step 5: tokens + `MatchupTable`.** Three colour tokens (`--pr-rank-good`, `--pr-rank-mid`, `--pr-rank-bad`) with text-colour pairs, light and dark, hand-picked so every pair meets 4.5:1. Rounded box, tabular numerals, the number only inside. Middle column wraps to two lines on 375px.
- [ ] **Step 6: contrast test.** Compute contrast for all 3 tiers x 2 themes from the token values and assert >= 4.5.
- [ ] **Step 7: wire `MatchupBrief`** to render `MatchupTable`, and the F1 `form_rows` list with the same coloured rank box (rank of n) when ranks exist. Remove `RankDuel` from this section (delete the component only if nothing else, including vendored copies and the harness, uses it).
- [ ] **Step 8: harness cases** (insight.tsx): the PL case with the exact live rows, an NFL case, one-sided, malformed, F1 form rows; render the harness and look at 375px and desktop in a browser (screenshots for the PR description).
- [ ] **Step 9: run** vitest + tsc + the hub node tests; the "Vendored UI is current" check will report the sites behind (expected; Task 2 clears it). Open the PR.

## Task 2: re-vendor into the four sites (after Task 1 merges)

**Files:** `<site>/predictor-ui/**` and `SYNC.json` in Sports_Predictor (`src/`), NBA_Predictor, PL_Predictor, F1_Predictor (`frontend/src/`). No site code changes are needed: `FixtureExplainer` already renders `MatchupBrief` (hub#100).

- [ ] For each site: fresh clone, branch `chore/resync-matchup-table`, `node scripts/sync-ui.mjs --from <hub checkout at merged main> <site-src>/predictor-ui` (pattern: NBA_Predictor PR #60 / #65), run the site's frontend tests + tsc + build, open one PR.
- [ ] The reviewer gates, merges and deploys (Sports/NBA/F1 via `predictor-hub/scripts/deploy-site.sh`, then `prune-images`; PL/CFB/NFL deploy from CI).

## Task 3: verify live (reviewer)

- [ ] PL fixture detail (e.g. a Bournemouth v Sunderland style fixture), on a 375px phone width and desktop: home team in the left column on every row, matching the header order; three colours by thirds (n = 20: ranks 1-7 green, 8-14 yellow, 15-20 red); no bars.
- [ ] An NFL game (n = 32) and a CFB game (FBS only): same layout; offence and defence rows paired.
- [ ] NBA (once teams have 5+ games, so rows exist) and F1 (the coloured form list).
- [ ] Capture screenshots; check the AI read still sits below the table and never repeats the ranks as directional claims.

## Definition of done

For the live PL rows above the table reads down as in the expected table, never alternating; the tier boundaries match the thirds rule for n = 20, 30 and 32; the contrast test passes for all tiers in both themes; all four sites' suites are green and deployed; screenshots (desktop and 375px) of PL and NFL are on the PR; nothing else on the fixture detail changed.

## Out of scope

Any change to how duel rows are produced or ordered; directional or "advantage" wording; the AI summary; NFL "Players to watch"; adding new metrics.
