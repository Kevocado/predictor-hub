# Predicted box score + track record rebuild (design)

**Date:** 2026-09-27
**Status:** awaiting Kevin's review.
**Roadmap:** [../plans/2026-09-25-predictor-frontend-action-plan.md](../plans/2026-09-25-predictor-frontend-action-plan.md). This is Phase 5.
**Mode:** Operate. The visitor's job is to read a projected roster and decide whether to trust it. Scanability and honest numbers outrank expression; the broadcast-scoreboard world is inherited unchanged.

## Kevin's asks, verbatim

- "make it like how fan duel does their box score or rather do it as a predicted box score so we can see all predictions for each player"
- "have the main filter choose either team to display and then you can keep the position filters too or rather group the players by their positions in their starter/bench order so that you always see the best information at. glance without having to scroll or decipher the table"
- "once you have built it, show me and then do the same for the NBA fixture detail"
- "make sure the track record is showing the full weeks so far as well as the player predictions stats and can you make do the total yards change as well"
- "redesign the track record pages to show all the information that is already there, as well as recorded information that isnt show as well as potential things we need to build to better show in the model track record to help people with decisions and just inform and allow me to keep track of them"

## Where the code lives

| Surface | Path | Branch |
|---|---|---|
| NFL + CFB fixture detail | `phase4-worktrees/Sports_v2` (`Sports_Predictor`) | `v2-wire` |
| NBA fixture detail | `phase4-worktrees/NBA_drop` (`NBA_Predictor`) | `drop-explain` |
| NFL API | `phase4-worktrees/NFL_Predictor` | `claude/sports-predictors-frontend-plan-qpab3v` |
| CFB API | `phase4-worktrees/CFB_Predictor` | same |
| NBA API | `phase4-worktrees/NBA_drop` (`NBA_Predictor`) | `drop-explain` |
| Shared design system | `predictor-hub-worktrees/v2p3/packages/predictor-ui` | `validator-reads-written-signs` |

`predictor-hub` is the landing page plus the `predictor-ui` package. The sport frontends are in the sport repos; each vendors `predictor-ui` into `src/predictor-ui/` via `scripts/sync-ui.mjs`, and `src/predictor-ui/SYNC.json` records the source commit. **Every shared component is authored in `predictor-hub/packages/predictor-ui` first, then synced.** A component written directly into a sport site is a defect.

## Decisions

| Decision | Choice |
|---|---|
| Box score columns | Exactly what the model predicts. No dashed-out FanDuel columns. |
| Team filter | Three states: Away / Both / Home. Defaults to **Both**. |
| Position handling | Rows grouped into position blocks in starter→bench order. The old position-filter button row is **removed**. |
| Starter source | A real starter flag on the backend. NFL has one available today; CFB is decided by Spike A1. |
| CFB fallback | If no real starter flag exists, rows order by projected volume and the column reads "Projected order", visibly distinct from NFL's "Starter". No shared fiction. |
| Market comparison | In scope. Model vs closing line, edge, and hit rate when the model disagreed. |
| Shared component | One `BoxScore` in `predictor-ui`, reused by NFL, CFB and NBA. |
| Rebuilt-after-kickoff picks (revised 2026-09-28) | **Two records, both shown.** The pre-kickoff record stays the headline. A second figure counts every resolved pick including rebuilt ones, clearly separated and labelled. Every resolved pick is listed with its hit or miss, so nothing is hidden. See B8. |

## What already exists, and what is broken

Verified against the code on 2026-09-27.

### Bug 1 — the NFL anytime-TD calibration section never renders

`NFL_Predictor/src/nfl_predictor/tracking/store.py:353` emits buckets as
`{"bucket": label, "n_resolved": int, "hit_rate": float | None}`.
`Sports_v2/src/types.ts:44` declares `ConfidenceBucket { label, n, hit_rate }`.

So on the NFL site `bucket.n` is `undefined`, the guard
`player_props.anytime_td.confidence_buckets.some((b) => b.n > 0)`
(`TrackRecordPage.tsx:136`) is `false`, and the whole block is skipped.
`CFB_Predictor/.../store.py:313` correctly emits `{"label", "n"}`, so CFB works.
The two sibling APIs have diverged and no test covers the contract.
**Fix in B1, with a test that fails if either drifts again.**

### Bug 2 — the weekly bar encodes a meaningless number

`TrackRecordPage.tsx:102` sets bar width to
`(n_games / max_games) * pct_moneyline_correct * 100`.
That multiplies accuracy by a volume share, so a week with fewer games draws a
shorter bar at a *higher* accuracy. A 100%-accurate week with 3 games reads
weaker than a 50%-accurate week with 16. **Fix in B2.**

### Gap 3 — "full weeks so far" is not derivable

`weekly_trend` contains only weeks that have resolved, tracked games. A week with
no tracked picks is absent, not marked. There is no notion of how many weeks have
elapsed, so the page cannot show the season's shape. **Fix in B3.**

### Gap 4 — recorded but never displayed

- `by_position` (per-position MAE for every yardage market) — computed, never rendered.
- `brier_score` for anytime-TD — computed, never rendered.
- `n_resolved` for every player-prop market — never rendered, so a "±4.2 yd"
  card is unanchored.

### Gap 5 — predicted total and margin are computed, then thrown away

`game_outcome.py:62` produces `predicted_total` and `predicted_margin`.
The tracker table `game_predictions` (`store.py:30`) stores `over_prob` and
`total_hit` but **has no column for either**. So predicted-vs-actual total
points does not exist anywhere in the product. This is the "total yards change"
and it must be built, not just displayed. **Fix in B4.**

### Gap 6 — no model-vs-market comparison

`PRODUCT.md` lists this as an open decision; Kevin has now closed it in favour of
building it. The closing line is already stored (`home_spread_line`, `total_line`),
so only the comparison and the "model disagreed with the line" cohort are new.

## Sub-project A — the predicted box score

### A0 — shared `BoxScore` component (`predictor-ui`)

One component, in `predictor-hub/packages/predictor-ui`, vendored into all three
sites. It is **presentational**. The caller does all data shaping — fetching,
grouping, sorting, choosing columns — and hands over finished groups. The
component owns the *rendering* of that structure: the grid, the position headers,
the starter/bench rail, the team totals rows, and the three starter states. It
never fetches, never reorders, and does not know what a touchdown is.

```ts
export type BoxScoreRow = {
  key: string;               // stable React key
  name: string;
  position: string;          // display group label
  team: string;              // abbreviation
  order: number;             // caller-assigned; lower sorts first
  isStarter: boolean | null; // null = this sport has no real starter data
  values: (number | null)[]; // aligned to `columns`; null renders an em-dash
  emphasisIndex?: number;    // which of `values` is the one number that shouts
};

export type BoxScoreColumn = {
  key: string;
  label: string;
  align?: "left" | "right";
  /** Screen-reader text for a row's cell, since the grid itself is terse. */
  describe?: (value: number | null, row: BoxScoreRow) => string;
};

export type BoxScoreGroup = {
  position: string;
  /** Already grouped, already ordered starters-then-bench. Rendered as given. */
  rows: BoxScoreRow[];
  /** Per-team subtotal for this position, or null when not wanted. */
  subtotals?: BoxScoreTotal[] | null;
};

export type BoxScoreTotal = {
  label: string;             // e.g. "MIA total"
  values: (number | null)[]; // aligned to the same `columns`
  strong?: boolean;          // the projected score: renders at display scale
};
```

`isStarter: null` is the honesty lever. The component renders three distinct
states — starter, bench, and **"Projected order"** with a visible note — so a
sport without real depth-chart data can never be mistaken for one that has it.

### A1 — spike: does CFBD expose a starter flag?

Cheap, and it decides CFB's path. `cfbd.GamesApi.get_game_player_stats` returns a
nested `game → team → category → type → athlete` tree; the flattener
(`CFB_Predictor/data/player_stats.py:118`) currently reads only `id`, `name` and
`stat`. **Question: does the athlete object carry `starter`?**

Already ruled out, verified against the installed packages:

- `cfbd` 5.31 `RosterPlayer` model fields are
  `id, first_name, last_name, team, height, weight, jersey, year, position,
  home_city, home_state, home_country, home_latitude, home_longitude,
  home_county_fips, recruit_ids` — **no depth-chart field**.
- The `cfbd` package exposes no depth-chart endpoint. (The `depth` matches in the
  package are *passing* depth.)

Outcomes:

- **`starter` present** → A3 sources it from the box score. CFB gets true starters.
- **absent** → CFB uses the honest fallback: `isStarter: null`, rows ordered by
  projected volume, header reads "Projected order (no depth-chart feed)". Recorded
  in the ledger with the evidence, and revisited if a CFB feed is added later.

### A2 — NFL backend: real depth charts

nflverse publishes `depth_charts_{season}.parquet`. Verified live for 2024 —
columns: `season, club_code, week, game_type, depth_team, depth_position,
football_name, position, formation, gsis_id, jersey_number, elias_id,
depth_team, last_name, first_name, full_name`.

**Starter rule, verified against Miami 2024 week 19:** a player is a starter when
`depth_team == 1` for their `depth_position`. That week it yields Tua at QB1,
Tyreek and Jaylen Wright at WR1 (Jaylen is a RB who lines up at slot), and Jonnu
Smith at TE1 — all correct. There is **no** `backups` column and no within-position
ordering to lean on, so `depth_team == 1` is the rule, not a heuristic.

New `data/depth_charts.py`:

- cache-or-fetch per season into `data/cache/depth_charts/{season}.parquet`,
  matching the existing `player_stats` cache pattern;
- `fetch_starter_flags(season, week)` returns the most recent published chart at
  or before `week` (the current depth chart is what an upcoming game will use);
- returns `player_id → { is_starter, depth_slot }` keyed on `gsis_id`, which is
  the same `player_id` the rest of the pipeline already uses;
- `club_code` joins straight onto `recent_team` — both are abbreviations, so no
  name mapping is needed. Confirmed: `player_stats.py:36` renames nflverse's
  `team` to `recent_team` and the frontend matches `prop.recent_team` against
  `game.home_team` directly.

Failure policy: a fetch failure must not break props. Return no flags, log, and
let the UI fall back to "Projected order" — the same state CFB may be in.

`PlayerPropPrediction` gains `is_starter: boolean | null` and
`depth_slot: number | null`, threaded through `_get_player_props_live` and the
public snapshot. Both must reach `public_snapshot.json`, because public mode is
what the VPS serves.

### A3 — CFB backend

Per A1. Same two fields on the prop payload, same snapshot plumbing, same
failure policy. If A1 finds nothing, this task reduces to emitting
`is_starter: null` and documenting it — which is still worth doing explicitly so
the field's absence is a decision on the record rather than an oversight.

### A4 — Sports frontend (NFL + CFB)

Replaces the "Model Player Projections" section of
`Sports_v2/src/components/GameDetailModal.tsx` and retires
`src/lib/playerRank.ts`'s filter UI (its `groupByPosition` and `keyYardage`
helpers move into the new component's callers).

**Columns, per position — the model's own markets, nothing more:**

| Position | Columns |
|---|---|
| QB | Pass yds · TD % |
| RB | Rush yds · Carries · Rec yds · Rec · TD % |
| WR | Rec yds · Rec · TD % |
| TE | Rec yds · Rec · TD % |

**Structure.** Position blocks, each with a sticky header carrying the position
label and its group total. Inside a block, starters first in depth-chart order,
then bench. A hairline separates the two. Each team gets its own totals row; the
projected score is readable straight off the two totals rows without scrolling
back up.

**Interaction.** The three-state team control (Away / Both / Home) sits on the
section's header line, defaulting to **Both**. Switching teams re-groups in
place with no scroll jump. The existing "Team Yardage Predictions" pair of cards
is **removed** — the totals rows replace it, and two encodings of the same number
is exactly the duplication this redesign exists to kill.

**Density.** At 390 px, one team's **starters plus its total** must be readable
without scrolling, and the two team totals must be visible together. Bench rows
sit below the fold; that is the correct trade, because a 22-starter box score
cannot fit a phone screen and pretending otherwise would mean dropping rows.

### A5 — NBA fixture detail

Same `BoxScore` component, NBA markets (points, rebounds, assists, 3PM, and
whatever else the NBA prop feed actually carries — read it before writing the
column list, do not assume parity with the NFL set). NBA has its own depth chart
in its roster feed, so `isStarter` should be real rather than `null`; confirm
before assuming.

### A6 — the hub teasers: F1 next session, and a second row

Added 2026-09-28 after the first deploy. Both are live-page corrections to the
hub, folded in here rather than opened as a separate plan because they are the
same surfaces and the same contracts.

**A6.1 — F1 shows the next session, not the next race.**

Today `selectF1` finds the first incomplete race and shows its race prediction.
Kevin wants the next *event* instead: qualifying first, then the race once the
weekend arrives. That is a real behavioural change, and it needs a small API
addition first.

**Measured, 2026-09-28:** the F1 session payload carries no datetime. A
`qualifying` entry for round 16 has exactly
`{season, round, race_name, session_type, tier, source}` and nothing else. So
nothing in the payload can say *when* qualifying is, and "switch to the race on
Saturday" is not expressible against it. Separately, the snapshot **already
contains race predictions for future rounds** with `source: live` — round 16's
race is there today. So the rule must be clock-based, not availability-based, or
the hub jumps straight to the race and never shows qualifying at all.

So: **`F1_Predictor` gains `session_datetime`** on the session predictions
(race predictions already have `race_datetime` via `RaceSummary`). It is the
same value the routes already compute internally to decide `tier`; expose it
rather than recomputing it. Test the sprint-weekend split — a sprint weekend has
three sessions and a normal one has one, and the weekend order is
`sprint_qualifying → sprint → qualifying → race`.

**Selection rule, once the field exists:** take the next incomplete round, then
walk the sessions in real-world order and show the **earliest one whose
`session_datetime` is still in the future**, falling back to the race. Never
show a session that has already happened, and never fall back to "whatever has a
prediction".

**A6.2 — a second row: the most confident pick.**

Each American-football, PL and NBA teaser grows from one row to two:

- **Row 1, unchanged:** the closest game — `min |home_win_prob − 0.5|`.
- **Row 2, new:** the most confident pick — `max(p, 1 − p)` over the same
  payload.

Both come out of arrays the hub already has, so this is **no backend work at
all**. Label the two so they are not read as one pick: the second is the week's
most confident call, not another coin flip.

**Interaction.** Two rows in one teaser, the existing two-line grid. The second
row is visually subordinate — same type, `--color-pr-text` not the accent — so
the eye still lands on the closest game first. On F1 the teaser keeps its three
drivers, which is its own shape and does not gain a second group.

## Sub-project B — the track record rebuild

### B1 — fix the bucket contract divergence

Both APIs emit `{label, n, hit_rate}`. `Sports_v2/src/types.ts` matches. Add a
test per API asserting the emitted keys, and a frontend test that renders a
non-empty bucket set and asserts the section appears — the gap that let this ship.

### B2 — fix the weekly bar

Accuracy and volume are two different questions and get two different encodings:
a 50%-reference marker on the accuracy scale (as the headline cards already do),
and `n_games` as text beside it. A week is never encoded as a single fused number.

### B3 — every elapsed week, backend

`_summarize_games` returns a row for **every week from 1 to the current week**,
not only weeks that happen to have tracked games. A week with no tracked picks
returns `n_games: 0` and `tracked: false` and renders as "Not tracked" — visibly
a gap in the record, not a silent absence. Each row carries moneyline, ATS and
totals accuracy plus counts, so the week view needs one request, not three.

### B4 — predicted total and margin, backend

New nullable columns on `game_predictions`: `predicted_total`, `predicted_margin`
(ALTER TABLE, matching the existing migration style; existing rows stay NULL and
are excluded from these metrics rather than counted as zero). Recorded at
snapshot time from the same response that already produces `over_prob`.

Exposed as:

- total points MAE and signed error, overall;
- the same by week, so the season's total-point drift is visible;
- projected score per game, so "Total yards change" is answerable directly.

### B5 — model vs market, backend + frontend

The closing line is already stored. New:

- **Implied probability from the line.** A closing spread is a margin, so the
  market's implied cover probability is `Φ(spread / σ_league)`, with `σ_league`
  a single named, documented constant per sport (NFL 13.5, CFB 14.0, to be
  pinned in the plan and asserted in a test so it cannot drift silently).
- **Edge**, in percentage points: the model's cover probability minus that
  implied probability, signed toward the model.
- **A disagreement cohort**: games where the model backed the side the line did
  not favour, and the hit rate within it. This is the number that actually
  informs a decision, and no current surface shows it.
- The `σ_league` constant and what "edge" means are stated **in words on the
  page**, not buried in a tooltip. A number nobody can interpret is not a
  decision aid.

Framed as *the model's agreement with a price*, never as a profit claim.
`PRODUCT.md` forbids ROI claims and that constraint holds.

### B6 — frontend redesign

Everything recorded gets shown, and every number carries its `n`:

- **Headline:** moneyline / ATS / totals accuracy, each with games counted and
  the rebuilt-after-kickoff count stated.
- **By week:** all elapsed weeks, three markets, counts, not-tracked states.
- **Player props:** anytime-TD hit rate with `n_called`, Brier score, and the
  calibration buckets (fixed by B1); each yardage market with MAE, signed error
  and `n`.
- **By position:** the `by_position` tables, per market.
- **Totals:** predicted vs actual total points, overall and by week.
- **Vs the market:** the B5 block.

The page becomes longer than a phone screen. That is correct for a reference
page — it is scanned, not read top to bottom — but it gets a sticky section
nav so a visitor can jump, and the headline stays above the fold.

### B7 — NBA track record

NBA's `TrackRecordPanel` is a four-column table over
`/hub/track-record` (`market, total_predictions, correct_predictions, hit_rate,
n_rebuilt`) and is well behind the NFL/CFB bar. Bring it to parity, reusing the
same components. NBA already has a `/calibration` endpoint; check whether its
data is fully surfaced before adding anything new.

### B8 — the full record, beside the pre-kickoff one

Added 2026-09-28 at Kevin's request. Kevin does not want rebuilt-after-kickoff
picks excluded from the record: he wants full tracking, and he wants to see the
picks that have already passed, right and wrong.

**The reasoning behind the shape, because it is easy to misread this as a
reversal of the honesty rule.** A hit rate is only meaningful if the pick
existed before the result. Counting post-kickoff picks toward one headline number
means the number can be inflated by construction — pick the winner after the
fact, score 100% — and it stops carrying information for anyone comparing the
model against a price. That is the brand commitment in `PRODUCT.md`, and it
survives this change. What changes is that **nothing is hidden and everything is
counted**, in two figures instead of one.

**Backend.** `get_track_record` currently drops rebuilt rows from
`_summarize_games` and returns only their count as `n_rebuilt`. Keep that
computation for the headline, and add a sibling that summarises **all** resolved
rows without the exclusion. So:

```
games: {
  ...pre-kickoff headline (unchanged, still excludes rebuilt),
  n_rebuilt,
  all_picks: { n_resolved, pct_moneyline_correct, pct_ats_correct,
               pct_totals_correct },   // rebuilt INCLUDED
  per_pick: [ { game_id, gameday, pick, actual, hit, rebuilt, ... } ],
}
```

`per_pick` is the "show the correct and wrong picks that already passed" half:
one row per resolved game, hit and miss alike, with `rebuilt` on the row so the
two kinds are distinguishable per pick and not only in aggregate.

**Frontend.** Two figures, side by side and unambiguously labelled — for example
"Made before kickoff" and "All tracked picks". The pre-kickoff one is the
headline; the all-picks one sits beneath it with a one-line explanation of why
they differ. Then the per-pick table, hits and misses in the same list, never
filtered or collapsed by default.

**`PRODUCT.md` must be updated in the same change.** The brand commitment
currently says rebuilt picks "never count toward any hit rate", which this makes
false. Reword it to: the pre-kickoff record is the headline and rebuilt picks
never count toward it; they are counted and shown separately, and every resolved
pick is listed. The honesty *rule* survives; the sentence does not.

## Data contract changes

`PlayerPropPrediction` (Sports):

```ts
+ is_starter: boolean | null   // null = no real depth-chart feed for this sport
+ depth_slot: number | null    // depth-chart slot; null when is_starter is null
```

`TrackRecord` (Sports):

```ts
interface WeeklyRow {
  week: number;
  tracked: boolean;
  n_games: number;
  pct_moneyline_correct: number | null;
  n_moneyline: number;
  pct_ats_correct: number | null;
  n_ats: number;
  pct_totals_correct: number | null;
  n_totals: number;
  pct_total_error: number | null;   // B4
  total_mae: number | null;         // B4
  total_bias: number | null;        // B4
}
+ weekly: WeeklyRow[]               // every elapsed week; replaces weekly_trend
+ totals: { n, mae, bias, weekly }  // B4
+ vs_market: { ... }                // B5
```

`weekly_trend` is **removed**, not kept alongside — two shapes for one fact is how
this page already got into trouble.

## Sequencing

```
A0  BoxScore component ──┬─> A4  Sports frontend ──> show Kevin ──> A5  NBA
                         │
A1  CFBD spike ─> A2 NFL ┘
              └─> A3 CFB
B1  contract fix ─> B2 bar ─> B3 weeks ─> B4 totals ─> B5 vs market ─> B6 frontend ─> B7 NBA
```

A0 is first because A4 and A5 both consume it and A2/A3 are backend work that can
run in parallel with it. B1 is first in B because it is a live bug and it is small.
B may run alongside A; they share `predictor-ui` and will conflict on sync commits,
so **not** simultaneously in the same package — sequence the syncs.

**This spec yields two implementation plans, not one.** Sub-project A (a new
surface, a backend migration, three sites) and sub-project B (a bug fix, two
migrations, a page redesign, three sites) are each a plan's worth of work. They
share `predictor-ui` and the `sync-ui.mjs` commit stream, so running both plans at
once guarantees sync conflicts. Plan A first, show Kevin, then Plan B.

## Risks

- **Depth charts lag the week.** nflverse publishes after games are played, so a
  Week 1 game uses the most recent available chart, which may be the prior season's
  final chart. Correct behaviour; the UI should not imply freshness it does not have.
- **CFBD has no depth chart** (verified). CFB may ship with `is_starter: null`.
  This is a known, recorded outcome, not a blocker.
- **Snapshot staleness.** Public mode serves `public_snapshot.json`. A new field
  is invisible until CI regenerates the snapshot, which can make a correct backend
  change look broken locally.
- **B4 is a schema migration** on a live SQLite file on the Azure Files mount —
  the repo already carries a fix note about file locking on that mount, so the
  migration needs the same care as the existing ALTERs.

## Out of scope

- Any win/profit/ROI claim. `PRODUCT.md` forbids it and nothing here adds one.
- Fumbles, passing attempts/completions, interceptions — the model does not
  predict them, so they do not appear.
- Replacing the broadcast-scoreboard visual world. This is an extension and
  inherits its tokens, type and components unchanged.
- A CFB depth-chart feed. Revisit if one is ever licensed.
