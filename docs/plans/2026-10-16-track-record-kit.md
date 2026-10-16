# Shared Track Record kit + cross-site uniformity (plan)

Origin: `/impeccable critique` + ponytail review, 2026-10-16 (dual-agent; detector: 4/5 frontends clean, F1 loads Inter).
Kevin's calls (2026-10-16): build the shared kit first; take on ALL five issues; decide F1's template after the kit exists.
Reference page: the NBA Track Record (`NBA_Predictor/frontend/src/components/TrackRecordPanel.tsx` + `trackRecordViews.tsx`).

## Why
The four record views are rebuilt in four places (NBA `trackRecordViews.tsx`; Sports `TrackRecordPage.tsx`, 1,110 lines + css;
PL `TrackRecordPanel.tsx`; F1 `TrackRecordPage.tsx`). Same data, five dialects. NFL/CFB open on a 240-row table (NFL ~15,700px tall
on mobile, CFB ~26,600px vs NBA ~4 screens). F1 imports nothing from predictor-ui. Hub tabs clip at 375px on PL/NFL/NBA.
Every hub UI change also costs four hand-made resync PRs (see Phase 6).

## Data contract (adapters, not a rewrite of any backend)
Each site maps its own API to one view-model; the kit only renders it.

```ts
interface RecordModel {
  markets: { key: string; label: string; counted: { correct: number; n: number };       // EVERY counted pick (PRODUCT.md, 2026-10-01)
                                       preKickoff?: { correct: number; n: number } }[]; // the subset made before kickoff, shown BESIDE it
  lead: string;                                           // market key for the headline
  weeks?: { weekStart: string; n: number; correct: number; tracked: boolean }[];
  calibration?: { bucket: string; n: number; correct: number }[];
  recent?: { id: string; label: string; pick: string; actual: string; hit: boolean | null; when: string; madeBeforeKickoff: boolean }[]; // names, never ids
  all?: same shape;                                       // collapsed <details>, never first
  error?: Partial<Record<"market" | "props" | "calibration", boolean>>;            // isolated failures
}
```

Plausible range = Wilson 95% interval on (correct, n); one shared helper, unit-tested, used for every headline.

## Components (packages/predictor-ui, NBA's `trackRecordViews.tsx` is the source)
`RecordHeadline` (number + bar + "could plausibly be a%–b%"), `RecordBlock` (question heading + one-line caption),
`WeekStrip`, `CalibrationChart`, `RecentPicks` (built on `PicksList`-style rows), `HowCounted` (collapsed details, one shared text),
`HubTabs` (tablist, scroll-fade cue), `vocabulary.ts` (below). Skeleton/Empty/Error come from the existing shared states.

## Vocabulary (one set, everywhere)
pick; **Right / Wrong** (not Called it/Missed/hit/miss/called); Spread / Total / Moneyline (never `ats`, `totals`);
"made before kickoff" / "rebuilt after kickoff" (F1: "after the session"; NBA: "tip-off" where the sport says so);
team names, never game ids. Market order fixed: lead market first, then Moneyline, Spread, Total, Props.

## Phases (each = one PR per repo; hub first)
0. **Plan + vocabulary constants** (this PR + `vocabulary.ts`).
1. **Kit in predictor-ui** with the view-model, Wilson helper, tests (render + a11y roles + 375px no-horizontal-scroll). No site changes.
2. **NBA moves onto the kit** and adopts the 2026-10-01 rule: headline = ALL counted picks, pre-kickoff figure beside it, backtest copy
   corrected (today it still says "never enter the record above"; `TrackRecordPanel.tsx:215` too). Pixel/structure parity test against today's page
   except the headline number. NOTE: this changes the headline figure on the page Kevin likes (game_outcome counted n=1,417, 1,365 rebuilt) - confirm before merge.
3. **NFL + CFB** (`Sports_Predictor/src/pages/TrackRecordPage.tsx`): rebuild on the kit; per-pick table into a collapsed section; recent picks as rows; ids -> team names;
   props behind a closed section; delete the dead code. Target: <= 6 mobile screens.
4. **PL** onto the kit (keep its gameweek grouping as the `WeekStrip` variant). Add `ErrorState`/`Skeleton`/aria.
5. **F1: decide the template after Phase 3** (same kit with a grid-position baseline in place of "against the odds", or its own layout), then migrate off its private `f1-*` tokens; replace Inter (detector: overused-font, `F1_Predictor/frontend/src/index.css:1`).
6. **Shared `HubTabs`** across all five (roving tabindex, scroll-fade, same order: Games, Teams, Players, Standings/Rankings, Track record; F1 gains Teams/Drivers + Model details tabs per PRODUCT.md).
7. **Stop the resync churn**: one hub workflow that opens the vendoring PR in each site when `packages/predictor-ui` changes (sites: Sports `src/`, PL/NBA/F1 `frontend/src/`).

## Rules for whoever builds it
Never lower a test/gate to pass; add the test that fails first; do not change a backend contract (adapters only); 375px AND desktop verified once in a batched round;
commit by explicit path (never `git add -A` in a worktree with a symlinked cache); one PR per phase; do not merge/deploy.

## Done when
Every sport's Track Record is the same kit with sport-specific blocks plugged in, one vocabulary, tabs never clip at 375px, and a hub UI change no longer needs hand-made PRs.
