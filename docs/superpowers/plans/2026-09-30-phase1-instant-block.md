# Phase 1 — Instant Facts Block Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The facts of a fixture — timing badge, verdict line, tiles, probability bar, record strip — render from the site's own bundle with **no request**, before the AI button is pressed; the button then says what it adds; and the sites stop repeating the same figures a second time.

**Architecture:** One new component, `InstantBlock`, in `predictor-ui`, composed by the existing `FixtureExplainer` from data the sites already hold (`extras` + the flow `bundle`). No new endpoints, no new fetches. `FixtureFlow` keeps only the sentences that carry news (in-play score, finished result and pick rightness) and loses the pre-game prose the block now shows as figures. Each site then passes the two things it never passed (`record`, and the timing that decides the badge), deletes its duplicate market section, and — in Sports only — stops rendering two different probabilities for the same pick.

**Tech Stack:** React 18 + TypeScript, Vite, Vitest + Testing Library, `predictor-ui` vendored into each site by `scripts/sync-ui.mjs`.

**Spec:** `docs/superpowers/specs/2026-09-30-fixture-insight-design.md` (§A instant block, §F honesty, decisions 1/2/7/9). Read §A, §F and §H before starting; the plan argues from them.

## Global Constraints

- **Never push to `main`, never merge.** One branch per repo, one PR per repo, cut from a **freshly fetched `origin/main`**. The reviewer merges and deploys.
- **Never hand-edit a vendored `predictor-ui/`.** Change `predictor-hub/packages/predictor-ui`, get Task 1 merged, then in each site run `node <hub>/scripts/sync-ui.mjs <site-src-dir>` and `node <hub>/scripts/sync-ui.mjs --check <site-src-dir>` (must pass before the PR). A site PR's vendored diff is only the re-sync.
- **Test-first, and prove red.** Write the test, watch it fail, implement, watch it pass. For any task that *changes existing behaviour*, then `git stash` **only the implementation** (keep the tests), re-run the named tests, paste the red output into the PR body, `git stash pop`, paste the green output.
- **Tests never touch the network.** No `fetch` to anything but a local stub. Prove it: run the suite with `HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9` on a fresh worktree before opening the PR, and say so in the body.
- **The sites' main checkouts may be dirty or behind.** All findings below were measured with `git show origin/main:<file>`. Work in a fresh worktree: `git worktree add <path> -b <branch> origin/main`. Never touch the existing checkout's local edits.
- **Honesty rules (binding, from the spec §F):** only a pick made before the start counts; a rebuilt pick is shown, labelled, never counted; after kickoff the stored pre-kickoff record is the only thing that may be described as the record; **a summary or a block may never state a figure the page does not carry, and no figure may appear twice with two different values.**
- **Every UI PR carries real-browser screenshots** at desktop width and 390px, taken against a real dev server with the API stubbed in the browser if necessary. Playwright + chromium-headless-shell are installed; keep every script under `/tmp`, never in a repo.
- **PR body starts with `Answers reviewer Phase 1 (task N).`** then: what changed, the red proof, the test counts, `tsc`, the drift check, the screenshots. Do not merge.
- Naming: `Model's top calls` is not in this phase; no wording may claim an edge, a lock, or a guaranteed outcome.

---

## Measured baseline (verified on `origin/main`, 2026-09-30)

| repo | `origin/main` | verified facts |
|---|---|---|
| `predictor-hub` | `f7f4ee8` | `FixtureExplainer.tsx:99-127` renders flow + button, summary only after the request. `FixtureFlow.tsx:139-196` builds the sentences. `ExplainerPanel.tsx:229,238` is the only `StatusBadge` render. `panelFacts.ts` has branches `PL` (:74) and `SP` (:85) only. `index.ts` exports 20 modules. |
| `Sports_Predictor` (NFL + CFB) | `a3d7165` | `GameDetailModal.tsx:312` `<FixtureExplainer>`, `:322` `extras={{ tiles, segments }}` — **no `record`, no `moment`**. `:346` renders `PregamePick` prose. `:394-397` renders the duplicate "Match Markets" section. `:186` fetches `api.gamePrediction` (fresh). `weekCards.ts:86` uses the stored `week.home_win_prob` (snapshot). |
| `PL_Predictor` | `03040e3` | `FixtureModal.tsx:300` `extras={{ tiles, segments, legend }}` — no `record`. `:92` / `:151` render ad-hoc provenance chips (`snapshot` / `reconstructed`). `:436-502` renders "Match result & goals" bars from the same `detail`. Record source: `api.trackRecord()` → `TrackRecordResponse.summary` = `{ n_resolved_fixtures, pct_correct_overall }` (`types.ts:516-538`). |
| `NBA_Predictor` | `22b6857` | `GameDetailModal.tsx:309` `extras={{ tiles, segments }}`; `:177` already computes `pick_timing: detail.rebuilt ? "rebuilt" : undefined`; `:77`/`:272` render `PregamePick` prose; `:218-269` markets table (kept — decision 3). Record source: `api.getTrackRecord()` → `TrackRecord[] { market, total_predictions, correct_predictions, hit_rate }`. |
| `F1_Predictor` | `07305b0` | `SessionTimelinePanel.tsx:191` `<FixtureExplainer>` with **no `extras`**; `:47` already renders `StatusBadge status="rebuilt" moment="the session"`; `:99` sets `pick_timing` from `data.source`. Record source: `api.raceAccuracy()` → `RaceAccuracyEntry[] { win_hits, win_of, podium_hits, podium_of, rebuilt }`. |

### The 68/72 contradiction, measured

`Sports_Predictor` shows two different probabilities for the same pick, because two different endpoints both expose a field called `home_win_prob`:

- the **list card** reads the stored pre-kickoff snapshot (`weekCards.ts:86`, from `GET /predictions/{season}/{week}`) — 68%;
- the **modal tile** reads a freshly computed prediction (`GameDetailModal.tsx:186`, `GET /games/{season}/{week}/{id}/prediction`) — 72%, rendered as `win · {team}`, i.e. as the pick.

Phase 1 fixes it at the root (Task 2): for a game that has started, every figure in the instant block comes from the stored snapshot, so the page can print 68% or 72% but never both, and never one as the pick while the other is shown elsewhere as the same pick.

---

## File map

**`predictor-hub/packages/predictor-ui`** (Task 1; sites re-sync from it)
- Create `src/lib/bundleFacts.ts` — bundle parsing shared by the block and the flow: `pickLabel`, `pickProbability`, `pickTiming`, `verdictSentence`.
- Create `src/components/InstantBlock.tsx` — badge-or-chip, verdict, tiles, bar, record.
- Modify `src/index.ts` — export `InstantBlock`, `InstantBlockProps`, and the `bundleFacts` helpers.
- Modify `src/components/FixtureExplainer.tsx` — compose the block, add the promise line under the button.
- Modify `src/components/FixtureFlow.tsx` — delete the pre-game prose; keep in-play and finished sentences.
- Tests: `src/lib/bundleFacts.test.ts`, `src/components/InstantBlock.test.tsx`, and edits to `FixtureFlow.test.tsx` / `FixtureExplainer.test.tsx`.

**Per site** (Tasks 2-5): one modal component + one new parity test file + the re-synced `src/predictor-ui/` (or `frontend/src/predictor-ui/`) + edits to the modal's existing test file.

## Order

Task 1 must be **merged into `predictor-hub` main** before Tasks 2-5 start: each site vendors the package, and the reviewer merges. Tasks 2-5 touch four different repos and can run in parallel once Task 1 is in.

---

### Task 1: `InstantBlock` in predictor-ui, and the flow loses its pre-game prose

**Files:**
- Create: `packages/predictor-ui/src/lib/bundleFacts.ts`, `packages/predictor-ui/src/lib/bundleFacts.test.ts`
- Create: `packages/predictor-ui/src/components/InstantBlock.tsx`, `packages/predictor-ui/src/components/InstantBlock.test.tsx`
- Modify: `packages/predictor-ui/src/index.ts`, `src/components/FixtureExplainer.tsx`, `src/components/FixtureFlow.tsx`, `src/components/FixtureFlow.test.tsx`, `src/components/FixtureExplainer.test.tsx`
- Test: the four test files above (existing ones are edited, never deleted wholesale)

**Interfaces:**
- Consumes: today's `FixtureExtras` (`packages/predictor-ui/src/components/FixtureExplainer.tsx:45-52`: `{ tiles?, segments?, legend?, record?, players?, moment? }`), `MarketTile`, `Segment`, `StatusBadge({ status, moment })`, `RecordStrip({ label, hits, settled })`, `KeyNumberTile({ tile })`, `ProbabilityBar({ segments, legend, minSegmentPx, pick })`, `FlowState`, `pct` from `../fmt`.
- Produces (later tasks rely on these exact names):
  ```ts
  export type Timing = { status: "rebuilt" | "unverified" | "nopick" | "none"; moment: Moment };
  export function pickLabel(bundle: any, sport: string): string | null;
  export function pickProbability(bundle: any): number | null;
  export function pickTiming(bundle: any, sport: string): Timing;
  export function verdictSentence(bundle: any, sport: string): string | null;
  export interface InstantBlockProps {
    sport: string;
    bundle: any;
    extras?: FixtureExtras;
  }
  export function InstantBlock(props: InstantBlockProps): JSX.Element | null;
  export const AI_PROMISE: string; // "AI read: model vs line, trends, who's out."
  ```

- [ ] **Step 1: Create a fresh worktree and branch**

```bash
cd /Users/sigey/Documents/Projects.nosync/predictor-hub
git fetch origin
git worktree add ../predictor-hub-worktrees/phase1 -b feat/instant-block origin/main
cd ../predictor-hub-worktrees/phase1
```

- [ ] **Step 2: Write the failing `bundleFacts` tests**

`packages/predictor-ui/src/lib/bundleFacts.test.ts`:

```tsx
import { describe, expect, it } from "vitest";
import { pickLabel, pickProbability, pickTiming, verdictSentence } from "./bundleFacts";

const PL = { team_home: "Arsenal", team_away: "Chelsea", home_win_prob: 0.57, away_win_prob: 0.2, pick: "Arsenal" };
const NFL = { home_team: "GB", away_team: "ATL", home_win_prob: 0.72, away_win_prob: 0.28, pick: { label: "GB", prob: 0.72 } };
const NBA_REBUILT = { home_team: "BOS", away_team: "MIA", pick: { label: "BOS", prob: 0.64 }, pick_timing: "rebuilt" };
const F1_UNKNOWN = { driver: "Max Verstappen", pick: "Max Verstappen", pick_timing: undefined, session_start: null };

describe("pickLabel", () => {
  it("reads a Sports-style object pick", () => { expect(pickLabel(NFL, "nfl")).toBe("GB"); });
  it("reads a PL string pick", () => { expect(pickLabel(PL, "pl")).toBe("Arsenal"); });
  it("reads an F1 driver pick", () => { expect(pickLabel(F1_UNKNOWN, "f1")).toBe("Max Verstappen"); });
  it("is null when the bundle names no pick", () => { expect(pickLabel({ home_team: "GB" }, "nfl")).toBeNull(); });
});

describe("pickProbability", () => {
  it("prefers the pick's own probability", () => { expect(pickProbability(NFL)).toBe(0.72); });
  it("returns null rather than guessing from a team's win probability", () => {
    // PL's bundle carries the prob on the pick, not on the sides.
    expect(pickProbability({ team_home: "Arsenal", pick: "Arsenal" })).toBeNull();
  });
});

describe("pickTiming", () => {
  it("reports a rebuilt pick, in the sport's own moment", () => {
    expect(pickTiming(NBA_REBUILT, "nba")).toEqual({ status: "rebuilt", moment: "tip-off" });
  });
  it("reports unverified for F1 when the schedule gave no start time", () => {
    expect(pickTiming(F1_UNKNOWN, "f1")).toEqual({ status: "unverified", moment: "the session" });
  });
  it("reports nopick when the bundle names no pick", () => {
    expect(pickTiming({ home_team: "GB", away_team: "ATL" }, "nfl")).toEqual({ status: "nopick", moment: "kickoff" });
  });
  it("reports none for a pick made before the start", () => {
    expect(pickTiming(NFL, "nfl")).toEqual({ status: "none", moment: "kickoff" });
  });
});

describe("verdictSentence", () => {
  it("states the pick and nothing else", () => {
    expect(verdictSentence(NFL, "nfl")).toBe("Green Bay is the pick.");
  });
  it("is null when there is no pick, so the block says nothing", () => {
    expect(verdictSentence({ home_team: "GB" }, "nfl")).toBeNull();
  });
});
```

`verdictSentence` maps a short team label to the full name where the bundle carries both (`home_team: "GB"` + `pick.label: "GB"` → "Green Bay"), because a verdict that says only "GB" is not a sentence a reader can act on. Keep the mapping to the team-name helper the package already exports; if the bundle has no full name, return the label as-is.

- [ ] **Step 3: Run them — they must fail**

```bash
cd packages/predictor-ui && npx vitest run src/lib/bundleFacts.test.ts
```
Expected: FAIL — `Cannot find module './bundleFacts'`. This is the red proof for the parser; keep the output.

- [ ] **Step 4: Implement `bundleFacts.ts`**

```ts
/** Parsing of the flow bundle that both the instant block and the flow need.
 *
 *  The bundle shape differs per site (PL names `team_home`/`pick` as a string,
 *  Sports names `home_team`/`pick` as an object, F1 names a `driver`). These
 *  four helpers are the ONE place that knows those differences, so the block
 *  and the flow cannot disagree about what the bundle says — the failure mode
 *  that produced 68 on one part of a page and 72 on another.
 *
 *  Nothing here derives a probability: a bundle without a pick probability
 *  yields null, and the caller renders nothing rather than a number nobody
 *  stored.
 */
import type { Moment, Status } from "../components/StatusBadge";

export type Timing = { status: Status; moment: Moment };

const MOMENT_OF: Record<string, Moment> = { f1: "the session", nba: "tip-off" };

export function pickLabel(bundle: any, sport: string): string | null {
  const pick = bundle?.pick;
  if (typeof pick === "string" && pick) return pick;
  if (pick && typeof pick === "object" && typeof pick.label === "string" && pick.label) {
    return fullTeamName(bundle, sport, pick.label);
  }
  return null;
}

/** The full name for a short label, when the bundle carries both. */
function fullTeamName(bundle: any, sport: string, label: string): string {
  const home = bundle?.home_team ?? bundle?.team_home;
  const away = bundle?.away_team ?? bundle?.team_away;
  if (home === label) return bundle?.home_team_full ?? home;
  if (away === label) return bundle?.away_team_full ?? away;
  return label;
}

export function pickProbability(bundle: any): number | null {
  const p = bundle?.pick?.prob;
  return typeof p === "number" && Number.isFinite(p) && p >= 0 && p <= 1 ? p : null;
}

export function pickTiming(bundle: any, sport: string): Timing {
  const moment = MOMENT_OF[sport] ?? "kickoff";
  const label = pickLabel(bundle, sport);
  if (bundle?.pick_timing === "rebuilt") return { status: "rebuilt", moment };
  if (!label) return { status: "nopick", moment };
  if (bundle?.pick_timing === "unknown") return { status: "unverified", moment };
  return { status: "none", moment };
}

export function verdictSentence(bundle: any, sport: string): string | null {
  const label = pickLabel(bundle, sport);
  return label ? `${label} is the pick.` : null;
}
```

- [ ] **Step 5: Run the parser tests — green**

```bash
npx vitest run src/lib/bundleFacts.test.ts
```
Expected: PASS.

- [ ] **Step 6: Write the failing `InstantBlock` tests**

`packages/predictor-ui/src/components/InstantBlock.test.tsx`. Assert, in this order:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InstantBlock } from "./InstantBlock";

const NFL = {
  home_team: "GB", home_team_full: "Green Bay", away_team: "ATL",
  home_win_prob: 0.72, away_win_prob: 0.28, pick: { label: "GB", prob: 0.72 },
};
const TILES = [{ market: "moneyline", label: "moneyline", value: "72%", sub: "win · GB" }];
const SEGMENTS = [{ label: "GB", prob: 0.72, market: "moneyline" }, { label: "ATL", prob: 0.28, market: "moneyline" }];
```

1. "renders the verdict from the bundle without any request" — no `request` prop exists; assert `screen.getByText("Green Bay is the pick.")` and that no fetch spy was called (pass a `global.fetch` spy that throws; assert it was not called).
2. "renders the tiles and the bar from the extras" — `screen.getByTestId("tile-moneyline")`, `screen.getByTestId("pbar-fill")`.
3. "renders the record strip when the site passes a record" — `getByTestId("record-fill")` with `record: { label: "Picks made before kickoff", hits: 11, settled: 15 }`.
4. "renders no record strip when the site passes none" — `queryByTestId("record-fill")` is null.
5. "shows the rebuilt badge and says the pick is not counted" — with `pick_timing: "rebuilt"`: `getByText(/after tip-off/i)` and `getByText(/not counted/i)`.
6. "shows the quiet chip for a pick made before the start" — with `NFL`: `getByText("Made before kickoff")` and **no** `StatusBadge` element.
7. "shows the unverified badge when F1's schedule gave no start time" — `getByText(/did not provide the start time/i)`.
8. "says there is no pick, and still shows the numbers" — with `{ home_team: "GB", away_team: "ATL", home_win_prob: 0.5 }` and the tiles/segments passed: `getByText(/no pick/i)` **and** `getByTestId("tile-moneyline")`.
9. "renders no tiles and no bar when the site passes none (F1's reduced rule)" — `queryByTestId("pbar-fill")` null, and the verdict still renders.
10. "renders nothing at all when the bundle has no pick and no extras" — `container.firstChild` is null.

- [ ] **Step 7: Run them — red**

```bash
npx vitest run src/components/InstantBlock.test.tsx
```
Expected: FAIL — `Cannot find module './InstantBlock'`. Keep the output.

- [ ] **Step 8: Implement `InstantBlock.tsx`**

```tsx
/** The facts, rendered before anything is asked for.
 *
 *  Every figure here comes from the site's own bundle or its `extras`. There
 *  is no request, no state and no effect: press the button or do not, this
 *  block is already true. That is the whole point of it — a reader should not
 *  have to spend a request to learn the probability the site already had.
 *
 *  Order is fixed: timing, verdict, tiles, bar, record. The timing row comes
 *  first because it governs how every number below it should be read, and the
 *  record comes last because it is about past picks, not this fixture.
 */
import { KeyNumberTile, type MarketTile } from "./KeyNumberTile";
import { ProbabilityBar, type Segment } from "./ProbabilityBar";
import { RecordStrip } from "./RecordStrip";
import { StatusBadge } from "./StatusBadge";
import { pickTiming, verdictSentence } from "../lib/bundleFacts";
import type { FixtureExtras } from "./FixtureExplainer";

export interface InstantBlockProps {
  sport: string;
  bundle: any;
  extras?: FixtureExtras;
}

const STARTED = {
  kickoff: "after kickoff",
  "tip-off": "after tip-off",
  "the session": "after the session started",
} as const;

export function InstantBlock({ sport, bundle, extras }: InstantBlockProps) {
  const timing = pickTiming(bundle, sport);
  const verdict = verdictSentence(bundle, sport);
  const tiles = extras?.tiles ?? [];
  const segments = extras?.segments;
  if (!verdict && tiles.length === 0 && !segments) return null;

  return (
    <div className="flex flex-col gap-3" data-testid="instant-block">
      {timing && timing.status === "none" && (
        <p className="flex items-center gap-2 text-sm text-pr-text-dim">
          <span className="inline-flex items-center whitespace-nowrap rounded-pr border border-pr-rule px-1.5 py-0.5 font-pr-display text-xs font-semibold uppercase tracking-wide">
            Made before {timing.moment === "the session" ? "the session" : timing.moment === "tip-off" ? "tip-off" : "kickoff"}
          </span>
        </p>
      )}
      {timing?.status === "rebuilt" && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-pr-text-dim">
          <StatusBadge status="rebuilt" moment={timing.moment} />
          <span>This pick was made {STARTED[timing.moment]}, so it is shown for reference and not counted.</span>
        </p>
      )}
      {timing?.status === "unverified" && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-pr-text-dim">
          <StatusBadge status="unverified" moment={timing.moment} />
          <span>The schedule did not provide the start time, so this pick cannot be shown as made before the start.</span>
        </p>
      )}
      {verdict && <p className="max-w-[70ch] text-lg font-medium leading-snug">{verdict}</p>}
      {timing?.status === "nopick" && (
        <p className="text-sm text-pr-text-dim">No pick was made for this fixture.</p>
      )}
      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {tiles.map((t) => <KeyNumberTile key={t.market} tile={t} />)}
        </div>
      )}
      {segments && segments.length > 0 && (
        <ProbabilityBar segments={segments} legend={extras?.legend} minSegmentPx={2} />
      )}
      {extras?.record && (
        <RecordStrip label={extras.record.label} hits={extras.record.hits} settled={extras.record.settled} />
      )}
    </div>
  );
}

export const AI_PROMISE = "AI read: model vs line, trends, who's out.";
```

Note the deliberate omissions: no `players` list (that is Phase 2's ranking, not a fact about this fixture), no band chip (the band belongs to the AI answer), and no import of `pct` — tiles arrive already formatted by the adapter, so the block formats nothing itself.

- [ ] **Step 9: Run the block tests — green**

```bash
npx vitest run src/components/InstantBlock.test.tsx
```
Expected: PASS (10 tests).

- [ ] **Step 10: Compose it in `FixtureExplainer`, and add the promise line**

In `FixtureExplainer.tsx`: import `InstantBlock`, `AI_PROMISE`; add `promise?: string` to the props (defaulting to `AI_PROMISE`); replace the body with:

```tsx
return (
  <div className="flex flex-col gap-3" data-testid="fixture-explainer">
    {panelState === "summary" && summary && <SummaryView summary={summary} extras={extras} />}
    <InstantBlock sport={sport} bundle={bundle} extras={extras} />
    <FixtureFlow sport={sport} state={state} bundle={bundle} request={request} />
    {panelState !== "summary" && (
      <div className="flex flex-col gap-1">
        <SummaryButton
          request={request}
          onSummary={handleSummary}
          onUnavailable={handleUnavailable}
          label={panelState === "unavailable" ? "Try again" : "Get the AI summary"}
        />
        <p className="max-w-[70ch] text-xs text-pr-text-faint" data-testid="ai-promise">{promise}</p>
      </div>
    )}
  </div>
);
```

In `FixtureExplainer.test.tsx`, add two tests and update the ones that assert the old arrangement:
- "shows the facts before the button, with no request" — pass `bundle` + `extras`, assert `getByTestId("instant-block")` appears **before** `getByTestId("summary-button")` (`compareDocumentPosition`), and `expect(request).not.toHaveBeenCalled()`.
- "names what the AI adds" — assert `getByTestId("ai-promise")` has the text `AI read: model vs line, trends, who's out.`
- Update "defaults to the flow state and makes no request": it now also renders the block. Keep the `not.toHaveBeenCalled()` assertion.
- Update "draws the site's figures under the summary when extras are passed": the tiles now render in the instant block too, so scope those assertions to `within(screen.getByTestId("fixture-summary"))` **and** add an assertion that the block carries them before the request.

- [ ] **Step 11: Delete the pre-game prose from `FixtureFlow`**

In `FixtureFlow.tsx`, remove from the **pre-game** branch only: the `Win probabilities: …` line (`:166`), the `The pick was made …` line (`:157` and `:168`), and the `The model picks …` lines (`:153`, `:174`, `:175`) plus the `The market's line is …` line for pre-game. Keep the heading row for pre-game only if it is the fixture name (`${home} vs ${away}`) — the block's verdict replaces the claim, but the fixture name is not a claim and is useful. Keep **in-play** (score, race state, line) and **finished** (result, rightness) untouched, and keep F1's session sentences: decision 8 leaves F1's per-race flow as it is.

Then make `FixtureFlow` use the shared helpers so the two cannot drift: import `pickLabel`, `pickProbability`, `pickTiming` from `../lib/bundleFacts` and delete its private `pickProb`/`MOMENT`/`whenMade` duplicates (`FixtureFlow.tsx:26-33,49,58`), keeping `MOMENT` only if a sentence still needs it.

- [ ] **Step 12: Update `FixtureFlow.test.tsx` — the deletions must be asserted, not assumed**

Change the pre-game tests to assert absence, and keep every in-play/finished assertion as it is:
- "PL: says the pick and stops" → becomes "PL: says no pick sentence before the button" — `expect(screen.queryByText(/The model picks/)).toBeNull()`, `expect(screen.queryByText(/Win probabilities/)).toBeNull()`.
- "Sports: two moneyline segments, no line tile" → keep the no-line-tile assertion, add the two absence assertions.
- "F1: draws no market-line tile and no split-bar market row" → keep; add the absence assertion for `The model picks`.
- Leave the in-play tests (`:266`, `:274`, `:281`) and the finished tests (`:292`, `:299`, `:306`) **unchanged**. If any of them fail after Step 11, the deletion went too far: restore that sentence.

- [ ] **Step 13: Export the new surface**

In `src/index.ts`, add:

```ts
export * from "./lib/bundleFacts";
export { InstantBlock, InstantBlockProps, AI_PROMISE } from "./components/InstantBlock";
```

- [ ] **Step 14: Full package verification**

```bash
cd packages/predictor-ui
npx vitest run          # expect: all files pass, including the edited flow/explainer suites
npx tsc --noEmit       # expect: clean
npm run build          # expect: built
```

- [ ] **Step 15: Screenshot the component**

Add an `instant` case to `packages/predictor-ui/harness/insight.tsx` that renders `<InstantBlock>` for the NFL bundle and one for F1's reduced shape, re-run the harness preview and capture desktop + 390px with the same script used for the other cases (`/tmp/shot/shoot.js`, ids appended to its `ids` array). Attach both to the PR.

- [ ] **Step 16: Red proof for the deletions**

The tests in Steps 2, 6 and 12 were each observed failing before their implementation existed; paste the three red outputs in the PR body. Additionally:

```bash
git stash push -- packages/predictor-ui/src/components/FixtureExplainer.tsx packages/predictor-ui/src/components/FixtureFlow.tsx
npx vitest run src/components/FixtureExplainer.test.tsx src/components/FixtureFlow.test.tsx   # expect: FAIL
git stash pop
npx vitest run src/components/FixtureExplainer.test.tsx src/components/FixtureFlow.test.tsx   # expect: PASS
```

Paste both outputs.

- [ ] **Step 17: Hermetic check, then commit and open the PR**

```bash
HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 npx vitest run
git add -A packages/predictor-ui
git commit -m "feat: instant facts block — badge, verdict, tiles, bar and record with no request"
```

PR to `predictor-hub`, title `feat: instant facts block renders from the bundle before the AI button`, body starting `Answers reviewer Phase 1 (task 1).` Include: what changed, the four red outputs, test counts, `tsc`, the two screenshots. **Do not merge** — the reviewer merges, and Tasks 2-5 depend on it.

---

### Task 2: Sports_Predictor — instant block for NFL and CFB, one probability per page

**Files:**
- Modify: `src/components/GameDetailModal.tsx` (`FixtureExplainer` call at `:312`, `extras` at `:322`, `PregamePick` at `:346`, "Match Markets" at `:394-397`)
- Create: `src/components/GameDetailModal.instant.test.tsx`
- Modify: `src/components/GameDetailModal.test.tsx` (assertions that pin the removed prose and the removed section)
- Re-sync: `src/predictor-ui/` (from merged Task 1 only)

**Interfaces:**
- Consumes: `InstantBlock` via `FixtureExplainer` (Task 1), `RecordStrip`'s `{ label, hits, settled }`, `weekPrediction.home_win_prob` and `weekPrediction.rebuilt` (already in the modal — used by `PregamePick` at `:346`).
- Produces: nothing other tasks consume.

- [ ] **Step 1: Worktree and branch**

```bash
cd /Users/sigey/Documents/Projects.nosync/Sports_Predictor
git fetch origin
git worktree add ../Sports_Predictor-worktrees/phase1 -b feat/instant-block origin/main
```

- [ ] **Step 2: Re-sync predictor-ui (Task 1 must be merged first)**

```bash
node /Users/sigey/Documents/Projects.nosync/predictor-hub/scripts/sync-ui.mjs src/predictor-ui
node /Users/sigey/Documents/Projects.nosync/predictor-hub/scripts/sync-ui.mjs --check src/predictor-ui   # expect: clean
git add src/predictor-ui   # vendored files only in this commit
```

- [ ] **Step 3: Write the failing parity test**

`src/components/GameDetailModal.instant.test.tsx`. The parity rule for every sport: **the block renders from the bundle with the network blocked.** Stub `global.fetch` to reject, render the modal with a started game, and assert the figures are still on screen.

```tsx
// Cases:
// 1. "renders the block from the bundle with the network blocked" — fetch throws
//    on every call; assert tile-moneyline, pbar-fill, instant-block and the
//    record strip are present, and that fetch was called only for the game's
//    own data (no request to the explainer endpoint).
// 2. "shows only the stored pre-kickoff probability once the game has started" —
//    weekPrediction.home_win_prob = 0.68, api.gamePrediction resolves 0.72.
//    Assert the page shows "68%" and that "72%" is nowhere in the block
//    (getByText(/72%/) === null, queryByText too).
// 3. "shows the model's own number before kickoff" — not started: the tile
//    shows 72% and no record-honesty line is needed.
// 4. "no longer repeats the markets below the panel" — assert
//    queryByText("Match Markets") is null.
// 5. "no longer prints the flow's pick sentences" —
//    queryByText(/Win probabilities/) and queryByText(/The model picks/) are null.
// 6. "carries the record" — record strip shows hits/settled from the week tally.
// 7. "shows the rebuilt badge and does not count the pick" — weekPrediction.rebuilt
//    is true: badge text present, "not counted" present.
// 8. CFB parity: the same test file's assertions run with sport="cfb".
```

- [ ] **Step 4: Run them — red**

```bash
npx vitest run src/components/GameDetailModal.instant.test.tsx
```
Expected: FAIL — no `instant-block` in the tree before any request, "Match Markets" still present, both 68% and 72% present. Keep the output.

- [ ] **Step 5: Fix the 68/72 root cause — one source per number**

In `GameDetailModal.tsx`, choose the source **once**, by timing, and use it for the whole block:

```tsx
/** One number per pick, chosen by when the game started.
 *
 *  The list card reads the stored pre-kickoff snapshot; the modal used to read
 *  today's freshly computed prediction, so the same pick read 68% on the card
 *  and 72% in the tile. The record judges the snapshot, so once a game has
 *  started the snapshot is the only figure that may be called the pick. Before
 *  kickoff there is no snapshot to disagree with, and the live model number is
 *  the pick. `started` reuses the card's own rule (weekCards.ts:76:
 *  `final || kickoffMs(game) <= now`) so the two surfaces cannot define
 *  "started" differently — that divergence is the bug.
 */
function pickProbability(game: GameSummary, prediction: GamePrediction | null, week: WeekPrediction | null): number | null {
  const started = isFinal(game) || parseKickoff(game.gameday).getTime() <= Date.now();
  if (started) {
    const snap = week && week.status !== "untracked" ? week.home_win_prob ?? null : null;
    if (snap != null) return snap;
  }
  return prediction?.home_win_prob ?? null;
}
```

Then pass that one probability into `panelFacts` — build the prediction object the adapter reads with the chosen probability, and pass `pick_timing: week?.rebuilt ? "rebuilt" : undefined` in the flow bundle so the block badges it. Where the fresh model number is still worth showing (the spread tile's `sub`), keep it, but never as `win · {team}` — the `win ·` sub is what made 72% look like the pick.

If `week.home_win_prob` is absent for a started game, the block must show the `nopick`/unknown path, never the fresh number wearing the pick's label.

- [ ] **Step 6: Pass the record, and delete the duplicates**

- `extras` at `:322` becomes:
  ```tsx
  extras={{
    tiles: panel.tiles,
    segments: panel.segments,
    record: {
      label: `Picks made before ${moment} correct`,
      hits: weekTally?.hits ?? null,
      settled: weekTally?.settled ?? 0,
    },
    moment,
  }}
  ```
  where `moment` is `"tip-off"` for NBA-shaped sports and `"kickoff"` here, and `weekTally` is the `{ hits, settled, rebuilt }` object `src/lib/weekCards.ts:124-131` already builds — reuse it (import it or lift it into a shared lib file), do not fetch it twice. If the modal does not already have the week summary, add the one fetch `GET /predictions/{season}/{week}` and pass `week` into it; **the parity test must still pass with fetch blocked, so seed the week data in the test rather than fetching it there.**
- Delete the whole "Match Markets" section (`:394-370` per the merged file) — its rows are the same `prediction.*` the tiles already draw.
- Delete the `PregamePick` prose at `:346`; the badge and the verdict line replace it. Keep the function only if another caller uses it; otherwise delete it and its test.
- The two plain lines above the score were `FixtureFlow`'s, deleted in Task 1 — assert their absence (case 5).

- [ ] **Step 7: Update the existing modal tests**

In `GameDetailModal.test.tsx`: replace any assertion that "Match Markets" exists with one that it does not; replace any assertion on the removed `PregamePick` sentence with the badge assertion. Run the file and fix only what genuinely changed — if an unrelated test fails, that is a bug in this task, not a test to relax.

- [ ] **Step 8: Verify, with the proof the reviewer asked for**

```bash
npx vitest run                                   # expect: all files pass
npx tsc -b && git status --porcelain             # expect: clean (checkout tsconfig.app.tsbuildinfo if it dirties)
npx vitest run src/predictor-ui.sync.test.ts     # drift check: expect pass
git stash push -- src/components/GameDetailModal.tsx     # implementation only
npx vitest run src/components/GameDetailModal.instant.test.tsx   # expect: FAIL
git stash pop
npx vitest run src/components/GameDetailModal.instant.test.tsx   # expect: PASS
HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 npx vitest run
```

Paste the red and green outputs, the counts, `tsc`, and the drift check into the PR body.

- [ ] **Step 9: Screenshots, desktop + 390px**

Against the dev server with the API stubbed in the browser: (a) pre-kickoff modal with the block and the promise line, (b) a started modal showing 68% and no 72% anywhere, (c) 390px of each. Script under `/tmp`.

- [ ] **Step 10: Commit and open the PR**

Two commits: the re-sync (vendored files only) and the change. PR title `feat: instant facts block for NFL and CFB; one probability per page`, body starting `Answers reviewer Phase 1 (task 2).` **Do not merge.**

---

### Task 3: PL_Predictor — instant block, provenance becomes a badge, duplicate bars go

**Files:**
- Modify: `frontend/src/components/FixtureModal.tsx` (`extras` at `:300`, provenance chips at `:92` and `:151`, duplicate market bars at `:436-502`)
- Create: `frontend/src/components/FixtureModal.instant.test.tsx`
- Modify: `frontend/src/components/FixtureModal.test.tsx`
- Re-sync: `frontend/src/predictor-ui/`

**Interfaces:**
- Consumes: `InstantBlock` via `FixtureExplainer`; `review.provenance` (`"snapshot" | "reconstructed" | undefined`) already fetched at `:252`; record from `api.trackRecord()` → `TrackRecordResponse.summary`.
- Produces: nothing other tasks consume.

- [ ] **Step 1: Worktree, branch, re-sync** — same three commands as Task 2, with `frontend/src/predictor-ui` and the `PL_Predictor-worktrees/phase1` path.

- [ ] **Step 2: Write the failing parity test** — `frontend/src/components/FixtureModal.instant.test.tsx`, with these cases (same rules as Task 2, PL's three-way market):

1. "renders the block from the bundle with the network blocked" — `fetch` rejects; `instant-block`, `tile-result`, `pbar-fill` present.
2. "keeps the three-way legend" — the market row renders because `legend` is passed (`ProbabilityBar` draws it only when the legend covers every outcome).
3. "shows the pre-match snapshot as a badge, not an ad-hoc chip" — `review.provenance === "snapshot"` → the block's quiet chip; `queryByText("Pre-match snapshot")` is null.
4. "shows the rebuilt badge for a reconstructed review and does not count it" — `provenance === "reconstructed"` → badge + "not counted".
5. "no longer repeats the market bars below the panel" — `queryByText("Match result & goals")` is null.
6. "carries the record" — with `trackRecord` seeded as `{ summary: { n_resolved_fixtures: 71, pct_correct_overall: 0.535 } }`, the strip shows `38/71`. State the arithmetic in a comment: `hits = Math.round(pct_correct_overall * n_resolved_fixtures)`, `settled = n_resolved_fixtures`. Both fields are pre-kickoff-only by the `TrackRecordSummary` comment at `types.ts:517-521` — say so in the test name.
7. "shows no record strip when the track record has not resolved anything" — `n_resolved_fixtures: 0` → `record-hit` dash, no invented 0%.

- [ ] **Step 3: Run — red.** Keep the output.

- [ ] **Step 4: Implement**

- Put `review.provenance` into the flow bundle as `pick_timing`: `"snapshot"` → no flag (a pre-match snapshot **is** a pre-kickoff pick); `"reconstructed"` → `"rebuilt"`. Add it to the `flowBundle` `useMemo` (`:213-227`).
- `extras` at `:300` gains `record` and `moment: "kickoff"`, with the arithmetic from case 6, computed in a `useMemo` and `null` while the track record is still loading (the strip must not flash 0/0).
- Delete the duplicate bars at `:436-502`; keep anything in that range that is **not** a repeat of a tile or the bar (the final-score header at `:324` and the player-call review at `:151` stay).
- Delete the provenance chips at `:92` and `:151` **only** where they duplicate the badge; the player-call review keeps its own heading.
- Add the track-record fetch if the modal does not have it (`api.trackRecord()` already exists at `api/client.ts:181`); one fetch at mount, guarded by the same `cancelled` flag the file already uses.

- [ ] **Step 5: Verify + red proof + hermetic run** — as Task 2 Step 8, with `cd frontend && npx vitest run`.

- [ ] **Step 6: Screenshots** — pre-match modal (block + promise line), reconstructed/rebuilt modal, 390px of each.

- [ ] **Step 7: Commit + PR** — title `feat: instant facts block for PL`, body starts `Answers reviewer Phase 1 (task 3).` Do not merge.

---

### Task 4: NBA_Predictor — verdict and record join the tiles NBA already has

**Files:**
- Modify: `frontend/src/components/GameDetailModal.tsx` (`extras` at `:309`, `pick_timing` at `:177`, `PregamePick` at `:77`/`:272`)
- Create: `frontend/src/components/GameDetailModal.instant.test.tsx`
- Modify: `frontend/src/components/GameDetailModal.test.tsx`
- Re-sync: `frontend/src/predictor-ui/`

**Interfaces:** consumes `InstantBlock`; `api.getTrackRecord()` → `TrackRecord[] { market, total_predictions, correct_predictions, hit_rate }`; `detail.rebuilt` (already at `:177`). Produces: nothing.

- [ ] **Step 1: Worktree, branch, re-sync** (as Task 2, `NBA_Predictor-worktrees/phase1`).

- [ ] **Step 2: Failing parity test** — `frontend/src/components/GameDetailModal.instant.test.tsx`:

1. "renders the block from the bundle with the network blocked" — `fetch` rejects; the **existing** tiles are still there (`instant-block`, `tile-moneyline`) plus the new verdict and record.
2. "keeps the markets table" — decision 3: `detail.markets` table still renders. Assert it, so a later de-duplication cannot quietly delete it.
3. "replaces the PregamePick sentence with the timing badge, and never both" — `detail.rebuilt === true` → badge + "not counted", and `queryByText(/Rebuilt after tip-off/)` (the prose at `:84`) is null.
4. "shows the quiet chip for a pick made before tip-off" — `rebuilt` false → "Made before tip-off".
5. "carries the moneyline record" — track record seeded with `{ market: "moneyline", total_predictions: 40, correct_predictions: 22 }` → strip shows `22/40`; when no moneyline row exists → dash, never 0/0.

- [ ] **Step 3: Run — red.**

- [ ] **Step 4: Implement**

- `extras` at `:309` gains `record` and `moment: "tip-off"`, built from the moneyline row of `api.getTrackRecord()`; `null` while loading.
- The block's verdict comes from the bundle's `pick` (`:177` already sets `pick_timing`); ensure `flowBundle.pick` is `{ label, prob }` so `verdictSentence` can state it, and that `pick_timing: detail.rebuilt ? "rebuilt" : undefined` reaches the block. Delete the `PregamePick` prose at `:84` — the badge says it, once.
- Do **not** touch the markets table, the box score's team split, or the panel's tiles.

- [ ] **Step 5-7:** verify + red proof (`cd frontend && npx vitest run`), screenshots (desktop + 390px, pre-tip and rebuilt), commit, PR titled `feat: instant facts block for NBA`, body starts `Answers reviewer Phase 1 (task 4).` Do not merge.

---

### Task 5: F1_Predictor — badge and record, no tiles, no bar

**Files:**
- Modify: `frontend/src/components/SessionTimelinePanel.tsx` (`FixtureExplainer` at `:191` with **no** `extras`, badge at `:47`, `pick_timing` at `:99`)
- Create: `frontend/src/components/SessionTimelinePanel.instant.test.tsx`
- Modify: `frontend/src/components/SessionTimelinePanel.test.tsx`
- Re-sync: `frontend/src/predictor-ui/`

**Interfaces:** consumes `InstantBlock`; `api.raceAccuracy()` → `RaceAccuracyEntry[] { win_hits, win_of, podium_hits, podium_of, rebuilt }`. Produces: nothing.

- [ ] **Step 1: Worktree, branch, re-sync** (`F1_Predictor-worktrees/phase1`).

- [ ] **Step 2: Failing parity test** — `frontend/src/components/SessionTimelinePanel.instant.test.tsx`:

1. "renders the block from the bundle with the network blocked" — `fetch` rejects; `instant-block` present with the verdict.
2. "draws no tiles and no bar" — `queryByTestId("tile-moneyline")` null, `queryByTestId("pbar-fill")` null. F1's reduced rule (spec §A).
3. "keeps the unverified badge when the schedule gave no start time" — the hub#43 behaviour survives: `getByText(/did not provide the start time/i)`.
4. "carries the session record and excludes rebuilt sessions" — `raceAccuracy` seeded with two entries, one `rebuilt: true` (`win_hits: 1, win_of: 1`) and one `rebuilt: false` (`win_hits: 3, win_of: 4`) → the strip shows `3/5`. Assert the rebuilt session is **not** counted; that is the whole point of the `rebuilt` field.
5. "shows no record strip when nothing has resolved" — empty array → dash.

- [ ] **Step 3: Run — red.**

- [ ] **Step 4: Implement**

- Pass `extras={{ record: { label: "Picks made before the session", hits, settled }, moment: "the session" }}` where `hits = Σ win_hits` and `settled = Σ win_of` over entries with `rebuilt === false`. `null` while loading.
- Leave the prediction table, the `ExplainRibbon` and their probability bars exactly as they are (decision 8: F1's insight stays per-race).
- The existing badge at `:47` and the block's badge must not both appear: if `:47` renders in the same view as the panel, delete `:47` and let the block own it. Check the rendered output, do not assume — if they are in different views (e.g. one on the session row, one in the panel), say so in the PR body and keep both.

- [ ] **Step 5-7:** verify (`cd frontend && npx vitest run`), red proof, screenshots (session panel desktop + 390px), commit, PR titled `feat: instant session record for F1`, body starts `Answers reviewer Phase 1 (task 5).` Do not merge.

---

## Definition of done for Phase 1

- `predictor-hub`: `InstantBlock` + `bundleFacts` exported; pre-game flow prose gone; in-play and finished sentences intact; full package suite + `tsc` green; two screenshots in the PR.
- Every site: the block renders from the bundle with the network blocked; the duplicate market section is gone; the timing is stated once, as a badge or the quiet chip; the record carries only pre-start picks; **Sports shows one probability per pick**; every suite green under `HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9`; drift check clean; desktop + 390px screenshots attached.
- No PR merged by the agent. No site hand-edits a vendored file. No test touches the network.

## Explicitly NOT in Phase 1

Player picks and their ranking (Phase 2, and NBA's availability gate with them), player news (Phase 3), the AI callout rewrite and the validator's non-overlap rule (Phase 4), the NBA probability layer, and the aggregate endpoint. Phase 1 changes **what a reader sees before asking**; it does not add a single new model number or endpoint.