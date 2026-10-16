# Shared Track Record kit + cross-site uniformity (plan)

Origin: `/impeccable critique` + ponytail review, 2026-10-16 (dual-agent; detector: 4/5 frontends clean, F1 loads Inter).
Kevin's calls (2026-10-16): build the shared kit first; take on ALL five issues; decide F1's template after the kit exists.
Reference page: the NBA Track Record (`NBA_Predictor/frontend/src/components/TrackRecordPanel.tsx` + `trackRecordViews.tsx`).

## Why
The four record views are rebuilt in four places (NBA `trackRecordViews.tsx`; Sports `TrackRecordPage.tsx`, 1,110 lines + css;
PL `TrackRecordPanel.tsx`; F1 `TrackRecordPage.tsx`). Same data, five dialects. NFL/CFB open on a 240-row table (NFL ~15,700px tall
on mobile, CFB ~26,600px vs NBA ~4 screens). F1 imports nothing from predictor-ui. Hub tabs clip at 375px on PL/NFL/NBA.
Every hub UI change also costs four hand-made resync PRs (see Phase 6).

## Decisions already made (do not re-ask)
- Kit first; all five critique issues are in scope; F1's template is decided after Phase 3 (see Phase 5).
- NBA keeps the pre-tip-off headline (Phase 2). NFL/CFB/PL/F1 use the PRODUCT.md rule (headline = every counted pick, pre-kickoff figure beside it) unless Kevin says otherwise.

## Data contract (adapters, not a rewrite of any backend)
Each site maps its own API to one view-model; the kit only renders it.

```ts
interface RecordModel {
  markets: { key: string; label: string; counted: { correct: number; n: number };       // EVERY counted pick (PRODUCT.md, 2026-10-01)
                                       preKickoff?: { correct: number; n: number } }[]; // the subset made before kickoff, shown BESIDE it
  lead: string;                                           // market key for the headline
  headline: "preKickoff" | "counted";                      // which of the two tallies is the big number (NBA: preKickoff)
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
2. **NBA moves onto the kit; its headline stays the PRE-TIP-OFF record** (Kevin, 2026-10-16: for NBA he wants to see the current pre-tip-off
   predictions, not how the model fares on rebuilt picks). So `headline: "preKickoff"` for NBA (the kit takes `headline: "preKickoff" | "counted"`, default `"counted"` per
   PRODUCT.md 2026-10-01). Concretely: the headline number/bar/range stays exactly what it is today (pre-tip subset); the title is corrected to say so
   ("Picks made before tip-off", not "Counted record"); the rebuilt-after-tip-off picks stay out of the headline and live only in the collapsed Backtest block, worded
   as "what the model would have said, not what it called in time" - and the false sentences go ("never enter the record above" at `TrackRecordPanel.tsx:162`,
   "The counted record above only includes picks made before tip-off" at `:215`) because the first contradicts how the other sites count and the second names the
   wrong thing "counted". Net visible change on the page Kevin likes: wording only; numbers unchanged. Parity test pins the structure and every number.
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


---

## Phase task lists (acceptance in italics)

### Phase 1 - kit in `packages/predictor-ui` (hub repo, branch `feat/track-record-kit`)
1. `src/trackRecord/vocabulary.ts`: label maps (market keys -> Moneyline/Spread/Total/Props), `RIGHT`/`WRONG`, timing phrases per sport, market order. *Test: no component contains a hard-coded Called it/Missed/hit/miss/ats/totals.*
2. `src/trackRecord/wilson.ts`: `wilsonInterval(correct, n, z=1.96)`; n=0 returns null (render "no graded picks yet", never 0%). *Tests: known values (25/52 -> 35%-61%), n=0, correct=n, correct=0.*
3. `RecordModel` types + `RecordBlock`, `RecordHeadline` (bar + range), `WeekStrip`, `CalibrationChart`, `RecentPicks`, `HowCounted` (collapsed, shared text parameterised by sport timing word), `HubTabs`. Port markup/classes from NBA `trackRecordViews.tsx` rather than redesigning; tokens only (`pr-*`), no sport accent hard-coded. *Tests: each renders with empty/partial/full model; roles present (tablist/tab/tabpanel, region labels); keyboard: arrows move tabs; 375px: no horizontal page scroll (jsdom width test + a harness screenshot).*
4. Export from `src/index.ts`; bump SYNC; run hub tests; open ONE hub PR. No site changes in this phase.

### Phase 2 - NBA on the kit (`NBA_Predictor`, branch `feat/track-record-on-kit`)
1. Re-vendor predictor-ui (`node scripts/sync-ui.mjs --from <sha> frontend/src`; never `--vendor-anyway`).
2. Write `toRecordModel(rows: TrackRecord[]) -> RecordModel` (adapter) in `frontend/src/lib/`; delete the local copies of what the kit now provides from `trackRecordViews.tsx`; `TrackRecordPanel.tsx` composes kit blocks + the NBA-only blocks (props error block, vs-odds, backtest).
3. Keep `headline: "preKickoff"`. Fix the two false sentences and the Backtest copy as above.
4. *Parity: before touching code, snapshot the current page's text content (live + a mocked-API test) for a fixed fixture; after the change the only diffs allowed are the corrected sentences and the title. Existing 224 frontend tests stay green.*

### Phase 3 - NFL + CFB (`Sports_Predictor`, branch `feat/track-record-on-kit`)
1. Adapter from the NFL/CFB `/track-record` shape (see `src/types.ts` TrackRecord) to `RecordModel`; map market codes with `vocabulary.ts`; resolve game ids to team names (the pick rows already carry both teams - verify, else join through the games feed).
2. Rebuild `src/pages/TrackRecordPage.tsx` on the kit: headline (counted, pre-kickoff beside), week strip, calibration, recent picks (<= 10 rows as rows, not a table), props block closed by default, "How this is counted" once. Per-pick table into a collapsed `<details>` at the bottom. Delete dead code and `track-record.css` rules no longer used.
3. *Acceptance: mobile page height <= 6 screens (~4,800px at 375px) for NFL and CFB with the same fixtures; zero raw ids or `ats`/`totals`/`hit`/`miss` strings (a test greps rendered text); existing Sports tests green; no horizontal page scroll at 375px.*

### Phase 4 - PL (`PL_Predictor`, branch `feat/track-record-on-kit`)
1. Adapter from PL's track-record payload; gameweek grouping becomes the `WeekStrip` variant; keep PL's value-bets/vs-market panel as a plugged-in block.
2. Add `Skeleton`, `ErrorState` with retry, and aria (the panel has none today). Replace "Called it/Missed" with Right/Wrong on the record (cards keep sport-appropriate wording only if `vocabulary.ts` allows it).
3. *Acceptance: ARIA roles asserted in tests; 375px no horizontal scroll; "(4/10)" style text replaced by the headline with range.*

### Phase 5 - F1 (decide, then build) (`F1_Predictor`)
1. After Phase 3 ships, compare NFL's kit page with F1's race-based layout and choose: (a) same kit with a grid-position baseline replacing "against the odds"; (b) keep the race table but adopt vocabulary/states. Write the choice in the PR description.
2. Either way: replace Inter (`frontend/src/index.css:1`), add loading skeleton + error/retry + aria, adopt `HubTabs` (Phase 6). F1 also gains the Data Hub parity PRODUCT.md requires (Teams/Drivers + Model details) - as a separate PR.

### Phase 6 - `HubTabs` everywhere
Replace the four ad-hoc tab bars (NBA `aria-current` buttons, Sports `aria-pressed`, PL strings, F1 `display:none` panels) with the shared component. Order: Games, Teams, Players, Standings/Rankings, Track record. *Acceptance: at 375px every tab is reachable (scroll with a visible fade/cue or wraps), `role=tablist`, arrow keys, active state announced.*

### Phase 7 - end the resync churn (hub repo)
`.github/workflows/resync-sites.yml`: on push to `main` touching `packages/predictor-ui/**`, for each site repo (path map: Sports `src`, PL/NBA/F1 `frontend/src`), open one PR with `node scripts/sync-ui.mjs --from <sha> <path>` using a token with PR rights. *Acceptance: the hub freshness check goes green without hand-made PRs; a dry-run mode lists the four PRs it would open.*
