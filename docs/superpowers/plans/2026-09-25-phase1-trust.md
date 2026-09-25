# Phase 1 · Trust — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Design sub-skill (required on every UI task):** run the named `/impeccable` command for the task: load its reference (`harden.md` or `clarify.md`), then read `reference/craft-floor.md` **before** the first UI edit. After the task's UI is finished, run `impeccable detect --json <changed files>`.

**Goal:** make every predictor site honest and non-hanging. No card claims a result it didn't earn, no count includes picks rebuilt after kickoff, and no failure looks like endless loading.

**Architecture:** these are refinements inside each existing app. Phase 1 **keeps each site's current look** (impeccable's rule for refinement: preserve the incumbent world), because Phase 2 replaces the visual system. Changes are limited to states, copy, counts and plumbing:
- Sports_Predictor (NFL + CFB): same-origin API plus error states.
- PL_Predictor: one pick per card; pre-kickoff-only counts in the API and the UI.
- NBA_Predictor: lead with the favourite; recoverable empty and error states.
- predictor-hub: working links and honest labels.

**Tech stack:** React 19, Vite, Tailwind 4, Vitest 2 and Testing Library (Sports, NBA; added to PL here). FastAPI and pandas with pytest (PL backend). Caddy 2 (Sports image). A static HTML Hub, checked with `node --test`.

**Spec:** [2026-09-25-predictor-frontend-action-plan.md](2026-09-25-predictor-frontend-action-plan.md), Phase 1, steps 1–4, plus the decisions table. Baseline critique: `.impeccable/critique/2026-09-25T07-27-01Z__index-html.md` (18/40).

## Global constraints

- **Branch:** `claude/sports-predictors-frontend-plan-qpab3v` in every repo. Commit once per task.
- **Picks rebuilt after kickoff** (`backfilled = true`) stay visible, labelled **"Rebuilt after kickoff"**, and are **never counted** in any hit rate or "called correctly" figure.
- **One pick per finished PL card.** It is the highest of the home/draw/away probabilities, the same rule the API's `hit` uses (`tracking/store.py::_fixture_hit_table`). ✓/✗ is judged against that pick.
- **Copy rules:**
  - No raw error strings shown to users.
  - Errors say what failed and offer **"Try again"**.
  - Loading text names what is loading.
  - Nothing promises a timing the system can't know.
- **Accessibility floor for anything new:** text 12 px or larger; contrast 4.5:1 or better (use each site's existing `*-text` or `*-text-dim` tokens, never `*-faint`, on new copy); loading and status regions use `role="status" aria-live="polite"`; errors use `role="alert"`.
- **Motion:** pulse and skeleton animations get `motion-safe:`.
- No new runtime dependencies. PL gains dev-only test dependencies, pinned to the versions Sports_Predictor already uses.

## Review focus

1. **Every PL fixture in a gameweek is rebuilt.** The headline must not read "0/0 called correctly". It shows "No pre-kickoff picks settled yet".
2. **A PL home/draw/away tie at the top**, for example 0.40 / 0.40 / 0.20. The card's pick must equal the API's pick. Python `max()` keeps the first key in insertion order (home, draw, away), so the frontend must break ties in the same order.
3. **NFL/CFB games load but every prediction call fails.** The schedule stays visible, cards say "No pick yet", and a page notice offers "Try again". No endless "Loading…".
4. **"Try again" after a rejected request actually re-requests.** The Sports client already evicts rejected promises from its cache; the retry test must assert a second `games` call.
5. **NBA prediction at exactly 0.50.** The card must pick one side deterministically (home, matching `>= 0.5` in `GameDetailModal`'s verdict) and never show "50% to win" for both.

---

## File map

| Repo | File | Responsibility |
|---|---|---|
| Sports_Predictor | `src/api/client.ts` | API base URLs from env, defaulting to same-origin `/api/nfl` and `/api/cfb` |
| | `vite.config.ts` | Dev and preview proxy for `/api/nfl` and `/api/cfb` |
| | `Caddyfile` | Production reverse proxy for the same paths |
| | `src/components/GameCard.tsx` | Pick states: loading, ready, unavailable |
| | `src/pages/GamesPage.tsx` | Page error with retry, predictions-failed notice, current-week notice |
| PL_Predictor | `src/pl_predictor/tracking/store.py` | Pre-kickoff-only counts in `get_track_record` and `get_results_by_gameweek` |
| | `frontend/src/lib/pick.ts` (new) | `matchPick()`, one pick per fixture |
| | `frontend/src/components/FinishedFixtureCard.tsx` | Pick, verdict, most-likely score, one badge |
| | `frontend/src/components/CurrentGameweekSection.tsx` | Headline counts pre-kickoff picks only |
| | `frontend/src/components/TrackRecordPanel.tsx`, `frontend/src/types.ts` | Rebuilt count shown, and null-safe |
| | `frontend/src/pages/FixturesPage.tsx`, `frontend/src/pages/DataHubPage.tsx` | Hide public refresh buttons |
| NBA_Predictor | `frontend/src/components/GameCard.tsx`, `frontend/src/components/GameDetailModal.tsx` | Lead with the favourite; margin names the team |
| | `frontend/src/pages/GamesPage.tsx`, `frontend/src/pages/CalibrationPage.tsx` | Recoverable empty and error states |
| predictor-hub | `index.html`, `tests/hub.test.mjs` (new) | VPS links, honest status, plain copy |

---

### Task 1: Sports: same-origin API base (`/impeccable harden`: network plumbing)

**Files:**
- Modify: `Sports_Predictor/src/api/client.ts:96-107`
- Modify: `Sports_Predictor/vite.config.ts`
- Modify: `Sports_Predictor/Caddyfile`
- Test: `Sports_Predictor/src/api/client.test.ts`, `Sports_Predictor/src/App.test.tsx`

**Interfaces:**
- Produces: `export const NFL_BASE_URL: string` and `export const CFB_BASE_URL: string` (defaults `/api/nfl` and `/api/cfb`).

- [ ] **Step 1: Write the failing test.** In `src/api/client.test.ts`:
  - Add `NFL_BASE_URL, CFB_BASE_URL` to the import from `./client`.
  - Replace every `http://localhost:8001/api` with `/api/nfl` and every `http://localhost:8003/api` with `/api/cfb`.
  - Do the same replacement in `src/App.test.tsx`.
  - Append:

```ts
describe("API base URLs", () => {
  it("default to same-origin paths so the page works on any host", () => {
    expect(NFL_BASE_URL).toBe("/api/nfl");
    expect(CFB_BASE_URL).toBe("/api/cfb");
  });
});
```

- [ ] **Step 2: Run it and confirm it fails.** `cd Sports_Predictor && npx vitest run src/api/client.test.ts src/App.test.tsx`. Expected: FAIL (the exports are missing, and the URLs are still localhost).

- [ ] **Step 3: Implement.** Replace `client.ts:96-107` (the `isProd` block through the two `*_BASE_URL` consts) with:

```ts
// Same-origin by default: the Caddy in front of this site (see Caddyfile)
// and the Vite dev/preview server (vite.config.ts) both proxy these paths
// to the NFL and CFB APIs. Override per build with VITE_NFL_API_BASE /
// VITE_CFB_API_BASE only when the APIs live on another origin.
export const NFL_BASE_URL: string = import.meta.env.VITE_NFL_API_BASE ?? "/api/nfl";
export const CFB_BASE_URL: string = import.meta.env.VITE_CFB_API_BASE ?? "/api/cfb";
```

In `vite.config.ts`, add a proxy under `server` and mirror it under `preview`:

```ts
const apiProxy = {
  "/api/nfl": { target: "http://localhost:8001", changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api\/nfl/, "/api") },
  "/api/cfb": { target: "http://localhost:8003", changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api\/cfb/, "/api") },
};
// ...inside defineConfig:
  server: { port: 5174, host: true, proxy: apiProxy },
  preview: { proxy: apiProxy },
```

Replace `Caddyfile` with:

```
:80 {
    handle_path /api/nfl/* {
        rewrite * /api{uri}
        reverse_proxy {$NFL_API_UPSTREAM:nfl-predictor:8001}
    }
    handle_path /api/cfb/* {
        rewrite * /api{uri}
        reverse_proxy {$CFB_API_UPSTREAM:cfb-predictor:8003}
    }
    handle {
        root * /usr/share/caddy
        try_files {path} /index.html
        file_server
    }
}
```

- [ ] **Step 4: Run it and confirm it passes.** Run the same command, then `npx vitest run` (full suite) and `npx tsc -b`. Expected: all PASS, and `tsc` exits 0.
- [ ] **Step 5: Validate the Caddyfile.** Run `docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile" caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile` if Docker is available. Otherwise record "not validated (no docker)" in the report.
- [ ] **Step 6: Commit.** `git add src/api/client.ts src/api/client.test.ts src/App.test.tsx vite.config.ts Caddyfile && git commit -m "fix: call the NFL/CFB APIs on the same origin instead of localhost"`

### Task 2: Sports: pick states on the game card (`/impeccable harden`)

**Files:**
- Modify: `Sports_Predictor/src/components/GameCard.tsx`
- Test: `Sports_Predictor/src/components/GameCard.test.tsx`

**Interfaces:**
- Produces: `GameCard` props gain `predictionsSettled?: boolean` (default `false`). When `prediction === null`:
  - `false` renders "Loading pick…";
  - `true` renders "No pick yet".

- [ ] **Step 1: Write the failing tests.** In `GameCard.test.tsx`, replace the test "shows a loading state when prediction is null" with:

```tsx
  it("shows a named loading state while predictions are still loading", () => {
    render(<GameCard game={game} prediction={null} onClick={() => {}} />);
    expect(screen.getByText("Loading pick…")).toBeInTheDocument();
  });
  it("says there is no pick, instead of loading forever, once predictions have settled", () => {
    render(<GameCard game={game} prediction={null} predictionsSettled onClick={() => {}} />);
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
    expect(screen.queryByText(/Loading/)).not.toBeInTheDocument();
  });
```

- [ ] **Step 2: Run them and confirm they fail.** `npx vitest run src/components/GameCard.test.tsx`. Expected: FAIL with `Unable to find an element with the text: Loading pick…`.
- [ ] **Step 3: Implement.** In `GameCard.tsx`:
  - Change the signature to `export function GameCard({ game, prediction, predictionsSettled = false, onClick }: { game: GameSummary; prediction: GamePrediction | null; predictionsSettled?: boolean; onClick: () => void })`.
  - Replace the `Loading…` badge span with:

```tsx
          <span role="status" className="rounded bg-sp-700/60 px-1.5 py-0.5 text-xs normal-case tracking-normal text-sp-text-dim">
            {predictionsSettled ? "No pick yet" : "Loading pick…"}
          </span>
```

Then replace the bar-fallback `<div className="h-2.5 w-full animate-pulse rounded-full bg-sp-850" />` with:

```tsx
predictionsSettled
  ? <div className="h-2.5 w-full rounded-full bg-sp-850" aria-hidden="true" />
  : <div className="h-2.5 w-full rounded-full bg-sp-850 motion-safe:animate-pulse" aria-hidden="true" />
```

- [ ] **Step 4: Run and confirm it passes.** `npx vitest run src/components/GameCard.test.tsx`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat: game cards say 'No pick yet' instead of loading forever"`

### Task 3: Sports: page-level failure states with retry (`/impeccable harden` + `/impeccable clarify`)

**Files:**
- Modify: `Sports_Predictor/src/pages/GamesPage.tsx`
- Test: `Sports_Predictor/src/pages/GamesPage.test.tsx`

**Interfaces:**
- Consumes: `GameCard`'s `predictionsSettled` (Task 2).

- [ ] **Step 1: Write the failing tests.** Append inside `describe("GamesPage", …)`:

```tsx
  it("shows a readable error with Try again when games fail, and retries on click", async () => {
    games.mockRejectedValueOnce(new Error("502 Bad Gateway"));
    render(<GamesPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load this week's games.");
    expect(alert).not.toHaveTextContent("502");
    const callsBefore = games.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(games.mock.calls.length).toBe(callsBefore + 1));
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("keeps the schedule and says picks are unavailable when every prediction call fails", async () => {
    predictionsBatch.mockRejectedValueOnce(new Error("down"));
    gamePrediction.mockRejectedValue(new Error("down"));
    render(<GamesPage />);
    expect(await screen.findByText("Picks for this week couldn't load. The schedule is below.")).toBeInTheDocument();
    expect(screen.getAllByText("No pick yet")).toHaveLength(2);
    expect(screen.getAllByText("Chiefs").length).toBeGreaterThan(0);
    gamePrediction.mockResolvedValue(pred2);
  });

  it("says when it could not find the current week", async () => {
    currentWeek.mockRejectedValueOnce(new Error("down"));
    render(<GamesPage />);
    expect(await screen.findByText("Couldn't find the current week, so this shows week 1.")).toBeInTheDocument();
  });
```

Also add `fireEvent` to the Testing Library import, and add `beforeEach(() => { vi.clearAllMocks(); })` inside the describe. `vitest` exports `beforeEach`; add it to the import.

- [ ] **Step 2: Run them and confirm they fail.** `npx vitest run src/pages/GamesPage.test.tsx`. Expected: 3 FAIL (no alert copy, no notice, no current-week notice).
- [ ] **Step 3: Implement** in `GamesPage.tsx`:

  1. Add state after `error`:

```tsx
  const [predictionsSettled, setPredictionsSettled] = useState(false);
  const [currentWeekFailed, setCurrentWeekFailed] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
```

  2. In the current-week effect:
     - Set `setCurrentWeekFailed(false);` at the start.
     - Replace `.catch(() => { if (!cancelled) setCurrentWeek(null); })` with `.catch(() => { if (!cancelled) { setCurrentWeek(null); setCurrentWeekFailed(true); } })`.

  3. In the games effect:
     - Add `setPredictionsSettled(false);` to the reset line.
     - After `setPredictions(merged);`, add `setPredictionsSettled(true);`.
     - In `.catch(...)`, replace the body with `if (!cancelled) setError("games");`. This is a sentinel; the raw message is never shown.
     - Change the dependency array to `[api, season, week, reloadKey]`.

  4. Replace the three status lines (`{loading && …}`, `{error && …}`, and the empty-state `<p>`) with:

```tsx
      {currentWeekFailed && (
        <p role="status" className="mb-3 text-sm text-sp-text-dim">Couldn't find the current week, so this shows week 1.</p>
      )}
      {loading && <p role="status" aria-live="polite" className="text-sm text-sp-text-dim">Loading games…</p>}
      {error && (
        <div role="alert" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-loss/40 bg-loss/10 px-4 py-3 text-sm text-sp-text">
          <span>We couldn't load this week's games. Check your connection and try again.</span>
          <button onClick={() => setReloadKey((k) => k + 1)} className="rounded-md border border-sp-border bg-sp-850 px-3 py-1.5 text-xs font-semibold text-sp-text transition hover:border-sp-gold/60">Try again</button>
        </div>
      )}
      {!loading && !error && predictionsSettled && games.length > 0 && Object.keys(predictions).length === 0 && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-sp-border bg-sp-850/70 px-4 py-3 text-sm text-sp-text">
          <span>Picks for this week couldn't load. The schedule is below.</span>
          <button onClick={() => setReloadKey((k) => k + 1)} className="rounded-md border border-sp-border bg-sp-850 px-3 py-1.5 text-xs font-semibold text-sp-text transition hover:border-sp-gold/60">Try again</button>
        </div>
      )}
      {!loading && !error && orderedGames.length === 0 && (
        <p className="text-sm text-sp-text-dim">No games scheduled for this week.</p>
      )}
```

  5. Pass `predictionsSettled={predictionsSettled}` to `<GameCard …/>`.

- [ ] **Step 4: Run and confirm it passes.** Run `npx vitest run`, then `npx tsc -b`. Expected: full suite PASS, and `tsc` exits 0.
- [ ] **Step 5: Commit.** `git commit -am "feat: readable game-load errors with Try again; no silent week-1 fallback"`

### Task 4: PL API: count pre-kickoff picks only (`/impeccable clarify`: the claim behind the copy)

**Files:**
- Modify: `PL_Predictor/src/pl_predictor/tracking/store.py` (`get_track_record` at about line 732, and `get_results_by_gameweek` at about line 812)
- Test: `PL_Predictor/tests/test_tracking.py`

**Interfaces:**
- Produces:
  - `get_track_record()` gains `"n_rebuilt_fixtures": int`. Every rate and count in it (`n_resolved_fixtures`, `pct_correct_*`, `gameweek_trend`, `by_market`) covers only rows with `backfilled == False`.
  - Each `get_results_by_gameweek()` group gains `"n_rebuilt": int`. Its `pct_correct` and `pct_correct_by_market` values cover pre-kickoff rows only and are `None` when there are none. `n_fixtures` counts pre-kickoff rows. The `fixtures` list still contains every fixture.

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_tracking.py`:

```python
def _one_fixture(event_id, home, away, gameweek=1):
    return pd.DataFrame([{
        "event_id": event_id, "team_home": home, "team_away": away,
        "commence_time": pd.Timestamp("2020-01-01T15:00:00Z"), "home_win_prob": 0.6,
        "draw_prob": 0.25, "away_win_prob": 0.15, "over_2_5_prob": 0.4,
        "under_2_5_prob": 0.6, "btts_yes_prob": 0.5, "top_scoreline": "1-0", "gameweek": gameweek,
    }])


def test_track_record_leaves_rebuilt_picks_out_of_every_rate(clean_db):
    store.record_predictions(_one_fixture("live", "Arsenal", "Chelsea"))
    store.record_predictions(_one_fixture("rebuilt", "Spurs", "Villa"), backfilled=True)
    store.reconcile_predictions(pd.DataFrame([
        {"team_home": "Arsenal", "team_away": "Chelsea", "date": pd.Timestamp("2020-01-01"), "goals_home": 0, "goals_away": 1, "ftr": "A"},
        {"team_home": "Spurs", "team_away": "Villa", "date": pd.Timestamp("2020-01-01"), "goals_home": 2, "goals_away": 0, "ftr": "H"},
    ]))

    record = store.get_track_record()

    assert record["n_resolved_fixtures"] == 1
    assert record["n_rebuilt_fixtures"] == 1
    assert record["pct_correct_overall"] == 0.0  # only the live miss counts; the rebuilt hit does not


def test_track_record_with_only_rebuilt_picks_reports_no_rate(clean_db):
    store.record_predictions(_one_fixture("rebuilt", "Spurs", "Villa"), backfilled=True)
    store.reconcile_predictions(pd.DataFrame([
        {"team_home": "Spurs", "team_away": "Villa", "date": pd.Timestamp("2020-01-01"), "goals_home": 2, "goals_away": 0, "ftr": "H"},
    ]))

    record = store.get_track_record()
    groups = store.get_results_by_gameweek()

    assert record["pct_correct_overall"] is None
    assert record["n_resolved_fixtures"] == 0
    assert record["n_rebuilt_fixtures"] == 1
    assert groups[0]["pct_correct"] is None
    assert groups[0]["n_fixtures"] == 0
    assert groups[0]["n_rebuilt"] == 1
    assert len(groups[0]["fixtures"]) == 1  # still listed, just not counted
```

- [ ] **Step 2: Run them and confirm they fail.** `SUPABASE_SERVICE_ROLE_KEY= .venv/bin/python -m pytest tests/test_tracking.py -q -k rebuilt`. Expected: FAIL with `KeyError: 'n_rebuilt_fixtures'`.
- [ ] **Step 3: Implement.** In `get_track_record`:
  - Rename the first line to `all_fixtures = _fixture_market_hit_table()`.
  - Add:

```python
    # Picks rebuilt after kickoff (backfilled) are shown in the UI but never
    # counted: only a prediction captured before the match is evidence.
    n_rebuilt = int(all_fixtures["backfilled"].sum()) if not all_fixtures.empty else 0
    fixtures = all_fixtures[~all_fixtures["backfilled"].astype(bool)] if not all_fixtures.empty else all_fixtures
```

  - Keep the existing `if fixtures.empty: return {...}` branch, adding `"n_rebuilt_fixtures": n_rebuilt,` to its dict.
  - Add `"n_rebuilt_fixtures": n_rebuilt,` to the final return dict.

  In `get_results_by_gameweek`, replace the group dict construction with:

```python
        counted = group[~group["backfilled"].astype(bool)]
        has_counted = not counted.empty
        groups.append(
            {
                "gameweek": gw_value,
                "pct_correct": float(counted["hit"].mean()) if has_counted else None,
                "n_fixtures": int(len(counted)),
                "n_rebuilt": int(len(group) - len(counted)),
                "pct_correct_by_market": {
                    "exact_score": _market_reliability(counted, "exact_score_hit")["pct_correct"] if has_counted else None,
                    "match_result": float(counted["hit"].mean()) if has_counted else None,
                    "over_under_2_5": _market_reliability(counted, "over_under_hit")["pct_correct"] if has_counted else None,
                    "btts": _market_reliability(counted, "btts_hit")["pct_correct"] if has_counted else None,
                },
```

The `"fixtures": [...]` list that follows still iterates over `group`. Leave it unchanged.

- [ ] **Step 4: Run and confirm it passes.** Run `.venv/bin/python -m pytest tests/test_tracking.py -q`, then `.venv/bin/python -m pytest tests -q -x -k "track or gameweek or tracking or api"`. Expected: all PASS. Record any pre-existing failures that don't involve these functions in the report and leave them unfixed.
- [ ] **Step 5: Commit.** `git add src/pl_predictor/tracking/store.py tests/test_tracking.py && git commit -m "fix: leave picks rebuilt after kickoff out of every hit rate"`

### Task 5: PL UI: one pick per card, honest headline (`/impeccable clarify`)

**Files:**
- Create: `PL_Predictor/frontend/src/lib/pick.ts`, `PL_Predictor/frontend/src/lib/pick.test.ts`, `PL_Predictor/frontend/src/test-setup.ts`
- Modify: `PL_Predictor/frontend/package.json` (a test script and dev dependencies), `PL_Predictor/frontend/vite.config.ts` (a test block)
- Modify: `PL_Predictor/frontend/src/components/FinishedFixtureCard.tsx`, `PL_Predictor/frontend/src/components/CurrentGameweekSection.tsx`
- Test: `PL_Predictor/frontend/src/components/FinishedFixtureCard.test.tsx`, `PL_Predictor/frontend/src/components/CurrentGameweekSection.test.tsx`

**Interfaces:**
- Produces: `matchPick(home: number, draw: number, away: number, teamHome: string, teamAway: string): { side: "home_win" | "draw" | "away_win"; label: string; prob: number }`.
  - The label is `"<Home> win"`, `"Draw"` or `"<Away> win"`.
  - Ties resolve in the order home, then draw, then away, matching Python `max()` over `{"home_win","draw","away_win"}`.
- Produces: `prekickoffTally(fixtures): { hits: number; settled: number; rebuilt: number }`, exported from `CurrentGameweekSection.tsx`.

- [ ] **Step 1: Add the test tooling.** Run `cd PL_Predictor/frontend && npm i -D vitest@^2.1.8 jsdom@^25.0.1 @testing-library/react@^16.1.0 @testing-library/jest-dom@^6.6.3`. Add `"test": "vitest run"` to `scripts`.
  - Create `src/test-setup.ts` containing `import "@testing-library/jest-dom/vitest";`.
  - In `vite.config.ts`, change the import to `import { defineConfig } from "vitest/config"` and add `test: { environment: "jsdom", globals: true, setupFiles: "./src/test-setup.ts" },`.

- [ ] **Step 2: Write the failing tests.**

`src/lib/pick.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { matchPick } from "./pick";

describe("matchPick", () => {
  it("picks the most likely side and names it", () => {
    expect(matchPick(0.36, 0.26, 0.38, "Tottenham", "Aston Villa")).toEqual({ side: "away_win", label: "Aston Villa win", prob: 0.38 });
    expect(matchPick(0.57, 0.21, 0.22, "Brentford", "Chelsea").label).toBe("Brentford win");
    expect(matchPick(0.3, 0.4, 0.3, "A", "B").label).toBe("Draw");
  });
  it("breaks ties home, then draw, then away, like the API", () => {
    expect(matchPick(0.4, 0.4, 0.2, "A", "B").side).toBe("home_win");
    expect(matchPick(0.2, 0.4, 0.4, "A", "B").side).toBe("draw");
  });
});
```

`src/components/FinishedFixtureCard.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FinishedFixtureCard } from "./FinishedFixtureCard";

const base = {
  commence_time: "2026-09-19T10:30:00Z", team_home: "Tottenham", team_away: "Aston Villa",
  actual_goals_home: 2, actual_goals_away: 3, predicted_scoreline: "1-1",
  predicted_home_win: 0.36, predicted_draw: 0.26, predicted_away_win: 0.38,
  draw_signal: true, hit: true, backfilled: false, onClick: () => {},
};

describe("FinishedFixtureCard", () => {
  it("states one pick and judges the verdict against it", () => {
    render(<FinishedFixtureCard {...base} />);
    expect(screen.getByText("Pick: Aston Villa win · 38%")).toBeInTheDocument();
    expect(screen.getByText("Called it ✓")).toBeInTheDocument();
    expect(screen.getByText("Most likely score 1–1")).toBeInTheDocument();
    expect(screen.queryByText(/We predicted/)).not.toBeInTheDocument();
    expect(screen.queryByText("Leaned draw")).not.toBeInTheDocument();
  });
  it("labels the home/draw/away split", () => {
    render(<FinishedFixtureCard {...base} />);
    expect(screen.getByText("Home 36% · Draw 26% · Away 38%")).toBeInTheDocument();
  });
  it("marks a rebuilt pick and does not show the stuck scorers line", () => {
    render(<FinishedFixtureCard {...base} backfilled player_events_pending />);
    expect(screen.getByText("Rebuilt after kickoff")).toBeInTheDocument();
    expect(screen.queryByText(/BACKFILLED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Refreshing official scorers/)).not.toBeInTheDocument();
  });
});
```

`src/components/CurrentGameweekSection.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { prekickoffTally } from "./CurrentGameweekSection";

const f = (finished: boolean, hit: boolean | null, backfilled: boolean) => ({ finished, hit, backfilled });

describe("prekickoffTally", () => {
  it("counts only finished picks made before kickoff", () => {
    expect(prekickoffTally([f(true, true, true), f(true, false, false), f(true, true, false), f(false, null, false)]))
      .toEqual({ hits: 1, settled: 2, rebuilt: 1 });
  });
  it("reports zero settled when every finished pick was rebuilt", () => {
    expect(prekickoffTally([f(true, true, true), f(true, false, true)])).toEqual({ hits: 0, settled: 0, rebuilt: 2 });
  });
});
```

- [ ] **Step 3: Run them and confirm they fail.** `npx vitest run`. Expected: FAIL. `./pick` and `prekickoffTally` don't exist yet, and the card text doesn't match.

- [ ] **Step 4: Implement.**

`src/lib/pick.ts`:

```ts
export type PickSide = "home_win" | "draw" | "away_win";

// The one pick a finished card is judged on: the most likely of home/draw/
// away. Mirrors tracking/store.py::_fixture_hit_table, whose Python max()
// keeps the first of equal values in home, draw, away order, so the card's
// verdict and the API's `hit` can never disagree.
export function matchPick(home: number, draw: number, away: number, teamHome: string, teamAway: string): { side: PickSide; label: string; prob: number } {
  let side: PickSide = "home_win";
  let prob = home;
  if (draw > prob) { side = "draw"; prob = draw; }
  if (away > prob) { side = "away_win"; prob = away; }
  const label = side === "home_win" ? `${teamHome} win` : side === "away_win" ? `${teamAway} win` : "Draw";
  return { side, label, prob };
}
```

In `FinishedFixtureCard.tsx`:
  - Import `matchPick` and compute `const pick = matchPick(predicted_home_win, predicted_draw, predicted_away_win, team_home, team_away);` and `const pct = (p: number) => \`${Math.round(p * 100)}%\`;`.
  - Remove the `draw_signal` badge span. Keep the `draw_signal` prop in `Props` so callers compile, and move its explanation into the card's `title`: `title={draw_signal ? "The scoreline model also leaned towards a draw." : undefined}` on the root div.
  - Replace the `backfilled` span with:

```tsx
          {backfilled && (
            <span
              title="Rebuilt from the model after this match finished. Shown for reference; not counted in the hit rate."
              className="rounded border border-pl-border px-1.5 py-0.5 text-xs font-semibold normal-case tracking-normal text-pl-text-dim"
            >
              Rebuilt after kickoff
            </span>
          )}
```

  - Delete the `{player_events_pending && (…Refreshing official scorers and assists…)}` block. Keep the prop in `Props`.
  - Replace the footer `<div className="flex items-center justify-between border-t …">…</div>` with:

```tsx
      <div className="flex flex-col gap-1 border-t border-pl-border/70 pt-2.5 text-xs text-pl-text-dim">
        <div className="flex items-center justify-between gap-2">
          <span className="font-semibold text-pl-text">Pick: {pick.label} · {pct(pick.prob)}</span>
          {predicted_scoreline && <span>Most likely score {predicted_scoreline.replace("-", "–")}</span>}
        </div>
        <span>Home {pct(predicted_home_win)} · Draw {pct(predicted_draw)} · Away {pct(predicted_away_win)}</span>
      </div>
```

  - The `hit ? "Called it ✓" : "Missed ✗"` verdict stays. It comes from the API's argmax, which is the same pick. Change its class to add `text-xs`, so nothing on the card is under 12 px.

In `CurrentGameweekSection.tsx`, add and export:

```ts
export function prekickoffTally(fixtures: { finished: boolean; hit: boolean | null; backfilled: boolean }[]) {
  const finished = fixtures.filter((f) => f.finished);
  const counted = finished.filter((f) => !f.backfilled);
  return { hits: counted.filter((f) => f.hit).length, settled: counted.length, rebuilt: finished.length - counted.length };
}
```

Replace the `nCompleted`/`nHit` lines with `const tally = prekickoffTally(data.fixtures);`, and replace the header `<span>` contents with:

```tsx
          {data.fixtures.length} fixture{data.fixtures.length === 1 ? "" : "s"}
          {tally.settled > 0 && ` · ${tally.hits}/${tally.settled} picks made before kickoff correct`}
          {tally.settled === 0 && tally.rebuilt > 0 && " · No pre-kickoff picks settled yet"}
```

Change that span's class from `text-pl-text-faint` to `text-pl-text-dim`. Also check that `CurrentGameweekFixture` in `types.ts` has `backfilled: boolean`. The API sends it (`routes.py:954`); add it to the type if it's missing.

- [ ] **Step 5: Run and confirm it passes.** `npx vitest run && npx tsc -b`. Expected: all PASS, and `tsc` exits 0.
- [ ] **Step 6: Commit.** `git add -A frontend && git commit -m "feat: one stated pick per PL card; headline counts pre-kickoff picks only"`

### Task 6: PL UI: track record shows rebuilt picks separately; no public refresh buttons (`/impeccable clarify` + `/impeccable harden`)

**Files:**
- Modify: `PL_Predictor/frontend/src/types.ts` (the track-record summary type at about line 517, and the gameweek group type)
- Modify: `PL_Predictor/frontend/src/components/TrackRecordPanel.tsx:60-90,140-156`
- Modify: `PL_Predictor/frontend/src/pages/FixturesPage.tsx:62-69`, `PL_Predictor/frontend/src/pages/DataHubPage.tsx:108-114`
- Test: `PL_Predictor/frontend/src/components/TrackRecordPanel.test.tsx`

**Interfaces:**
- Consumes: Task 4's `n_rebuilt_fixtures`, `n_rebuilt` and nullable group `pct_correct`.

- [ ] **Step 1: Write the failing test.** Before writing it, read `TrackRecordPanel.tsx`'s prop type and `types.ts`, and build a minimal typed fixture object from them. Assert:
  - with `n_rebuilt_fixtures: 3` and `pct_correct_overall: null`, `n_resolved_fixtures: 0`, the text "3 picks rebuilt after kickoff are shown but not counted." renders;
  - the "Correct overall" stat shows "—";
  - a gameweek group with `pct_correct: null` renders "No pre-kickoff picks" instead of "NaN" or "0%".
- [ ] **Step 2: Run and confirm it fails.** `npx vitest run src/components/TrackRecordPanel.test.tsx`
- [ ] **Step 3: Implement.**
  - Add `n_rebuilt_fixtures: number` to the summary type, and `n_rebuilt: number` plus `pct_correct: number | null` to the group type.
  - In the panel:
    - Change "Correct overall" to render `summary.pct_correct_overall === null ? "—" : …existing…`.
    - Below the stat grid, add `{summary.n_rebuilt_fixtures > 0 && <p className="text-xs text-pl-text-dim">{summary.n_rebuilt_fixtures} pick{summary.n_rebuilt_fixtures === 1 ? "" : "s"} rebuilt after kickoff {summary.n_rebuilt_fixtures === 1 ? "is" : "are"} shown but not counted.</p>}`.
    - In each group header, render `group.pct_correct === null ? "No pre-kickoff picks" : \`${pct(group.pct_correct)} correct (${Math.round(group.pct_correct * group.n_fixtures)}/${group.n_fixtures})\``.
    - Guard the chart's `pct_correct` bars by filtering out null entries.
  - In `FixturesPage.tsx`, wrap the "Refresh odds" button in `{!PUBLIC_MODE && (…)}`.
  - In `DataHubPage.tsx`, wrap the "Refresh live data" button in `{!PUBLIC_MODE && (…)}`. `PUBLIC_MODE` is already imported in both files.
- [ ] **Step 4: Run and confirm it passes.** `npx vitest run && npx tsc -b && VITE_PUBLIC_MODE=true npx vite build`. Expected: PASS, and the build succeeds.
- [ ] **Step 5: Commit.** `git commit -am "feat: track record shows rebuilt picks separately; hide refresh buttons in public mode"`

### Task 7: NBA: lead with the favourite; recoverable states (`/impeccable clarify` + `/impeccable harden`)

**Files:**
- Modify: `NBA_Predictor/frontend/src/components/GameCard.tsx`, `NBA_Predictor/frontend/src/components/GameDetailModal.tsx:140-157`
- Modify: `NBA_Predictor/frontend/src/pages/GamesPage.tsx`, `NBA_Predictor/frontend/src/pages/CalibrationPage.tsx`
- Test: `NBA_Predictor/frontend/src/components/GameCard.test.tsx`, `NBA_Predictor/frontend/src/pages/GamesPage.test.tsx`, `NBA_Predictor/frontend/src/pages/CalibrationPage.test.tsx`

**Interfaces:**
- Produces: `export function favourite(p: Prediction, home: string, away: string): { team: string; prob: number }`, exported from `GameCard.tsx`. It picks home when `home_win_probability >= 0.5`.

- [ ] **Step 1: Write the failing tests.** Add to `GameCard.test.tsx`:

```tsx
  it("leads with the favourite, even when that is the away team", () => {
    const awayFav: Game = { ...baseGame, prediction: { home_win_probability: 0.47, predicted_margin: -4.8, predicted_total: 220 } };
    render(<GameCard game={awayFav} onSelect={() => {}} />);
    expect(screen.getByText("53%")).toBeInTheDocument();
    expect(screen.getByText("MIA to win")).toBeInTheDocument();
  });
  it("picks home at exactly 50%", () => {
    const even: Game = { ...baseGame, prediction: { home_win_probability: 0.5, predicted_margin: 0, predicted_total: 220 } };
    render(<GameCard game={even} onSelect={() => {}} />);
    expect(screen.getByText("BOS to win")).toBeInTheDocument();
  });
  it("says 'No pick yet' rather than 'Pending' and drops the raw date", () => {
    render(<GameCard game={{ ...baseGame, prediction: null }} onSelect={() => {}} />);
    expect(screen.getByText("No pick yet")).toBeInTheDocument();
    expect(screen.queryByText("Pending")).not.toBeInTheDocument();
    expect(screen.queryByText("2026-11-01")).not.toBeInTheDocument();
  });
```

Add to `GamesPage.test.tsx`:

```tsx
  it("offers Try again when games fail and next week when a week is empty", async () => {
    vi.mocked(api.getSeasonFirstWeek).mockResolvedValue({ first_week_start: "2026-02-09" });
    vi.mocked(api.getGamesWeek).mockRejectedValueOnce(new Error("x")).mockResolvedValueOnce([]).mockResolvedValue([]);
    render(<GamesPage />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We couldn't load this week's games.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No games this week.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next week →" }));
    await waitFor(() => expect(vi.mocked(api.getGamesWeek)).toHaveBeenLastCalledWith("2026-02-16"));
  });
```

Check `CalibrationPage.test.tsx`'s mocking pattern first, then assert that the empty state reads "Not enough finished games to check calibration yet. This fills in as the season is played." and that an error shows "Try again".

- [ ] **Step 2: Run and confirm they fail.** `cd NBA_Predictor/frontend && npx vitest run`
- [ ] **Step 3: Implement.**

In `GameCard.tsx`:

```tsx
export function favourite(p: Prediction, home: string, away: string): { team: string; prob: number } {
  return p.home_win_probability >= 0.5 ? { team: home, prob: p.home_win_probability } : { team: away, prob: 1 - p.home_win_probability };
}
```

  - Import `Prediction` from `../api/client`.
  - Delete the `{game.game_date}` line; the day header already carries the date.
  - In the prediction branch, render `favourite(...)`: the big number is `{Math.round(fav.prob * 100)}%`, and the caption is `{fav.team} to win`.
  - Replace the `Pending` div with `<div className="text-xs text-[var(--color-net-dim)]">No pick yet</div>`.

In `GameDetailModal.tsx`, in the prediction block:
  - Use `favourite` for the first stat: value `{Math.round(fav.prob*100)}%`, caption `{fav.team} to win`.
  - The margin stat uses the file's existing `favoredTeam(detail.prediction.predicted_margin, detail.home_team, detail.away_team)`: value `{m.team} by {m.value.toFixed(1)}`, caption `Projected margin`.
  - The total stat keeps its value, with caption `Projected total points`.

In `GamesPage.tsx`:
  - Add `const [reloadKey, setReloadKey] = useState(0);` and add `reloadKey` to the games effect's dependencies.
  - Replace the three status lines with:

```tsx
      {error && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded border border-[var(--color-line)] p-3 text-sm">
          <span>We couldn't load this week's games. Check your connection and try again.</span>
          <button onClick={() => setReloadKey((k) => k + 1)} className="rounded border border-[var(--color-line)] px-3 py-1 text-xs font-semibold hover:border-[var(--color-hardwood)]">Try again</button>
        </div>
      )}
      {!error && games === null && <p role="status" aria-live="polite">Loading games…</p>}
      {!error && games !== null && games.length === 0 && (
        <div className="flex items-center gap-3 text-sm">
          <span>No games this week.</span>
          <button onClick={() => setWeekStart((w) => addDays(w ?? mondayOf(new Date()), 7))} className="rounded border border-[var(--color-line)] px-3 py-1 text-xs font-semibold hover:border-[var(--color-hardwood)]">Next week →</button>
        </div>
      )}
```

In `CalibrationPage.tsx`:
  - Add a `reloadKey` in the same way, and render the error as a `role="alert"` block with the message "We couldn't load calibration data." and a "Try again" button.
  - The empty state reads "Not enough finished games to check calibration yet. This fills in as the season is played."

- [ ] **Step 4: Run and confirm it passes.** `npx vitest run && npx tsc -b`. Expected: all PASS.
- [ ] **Step 5: Commit.** `git commit -am "feat: NBA cards lead with the favourite; recoverable empty and error states"`

### Task 8: Hub: working links, honest status (`/impeccable clarify` + `/impeccable harden`)

**Files:**
- Modify: `predictor-hub/index.html`
- Create: `predictor-hub/tests/hub.test.mjs`

- [ ] **Step 1: Write the failing test.** Create `tests/hub.test.mjs`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

test("links point at the VPS sites, not the retired Azure apps", () => {
  assert.doesNotMatch(html, /azurecontainerapps\.io/);
  for (const sub of ["pl", "f1", "sports", "nba"]) {
    assert.match(html, new RegExp(`href="https://${sub}\\.40-160-91-131\\.sslip\\.io"`));
  }
});

test("status labels are honest and copy is plain", () => {
  assert.doesNotMatch(html, /Work in progress/);
  assert.doesNotMatch(html, /walk-forward/);
  assert.doesNotMatch(html, /no login required/i);
  assert.match(html, /<span class="badge soon">Preseason<\/span>/);
  assert.equal((html.match(/class="badge live"/g) || []).length, 3);
});

test("badge text is at least 12px", () => {
  const badge = html.match(/\.badge\s*\{[^}]*font-size:\s*([\d.]+)rem/);
  assert.ok(badge && parseFloat(badge[1]) >= 0.75, `badge font-size ${badge && badge[1]}rem is under 0.75rem`);
});
```

- [ ] **Step 2: Run and confirm it fails.** `cd predictor-hub && node --test tests/`
- [ ] **Step 3: Implement** in `index.html`:
  - Replace the four `href`s with `https://pl.40-160-91-131.sslip.io`, `https://f1.40-160-91-131.sslip.io`, `https://sports.40-160-91-131.sslip.io` and `https://nba.40-160-91-131.sslip.io`. Change `target="_blank"` to same-tab: remove `target` and `rel`.
  - NBA badge: `<span class="badge soon">Preseason</span>`.
  - Set `.badge { font-size: 0.75rem; }`.
  - New card copy:

    | Card | Copy |
    |---|---|
    | PL | "Match picks and likely scores for every Premier League fixture, with a running record of how often the model is right." |
    | F1 | "Win, podium and points chances for every driver, before each race and during live sessions." |
    | Sports | Rename the card heading to "NFL + CFB Predictor". Copy: "Weekly NFL and college football picks with confidence, spreads and player props." |
    | NBA | "Game picks, projected margins and totals. Picks start with the regular season." |

  - Header copy: "Model picks for Premier League, Formula 1, NFL, college football and NBA."
  - Delete the `<footer>` element.
- [ ] **Step 4: Run and confirm it passes.** `node --test tests/`. Expected: 3 pass.
- [ ] **Step 5: Commit.** `git add index.html tests/hub.test.mjs && git commit -m "fix: hub links to the VPS sites with honest status and plain copy"`

### Task 9: Design verification (`impeccable detect`, then a batched visual check)

- [ ] **Step 1: Detector.** Run `~/.claude/skills/impeccable/scripts/impeccable detect --json <changed files>` in each repo, passing the TSX files and `index.html` changed in Tasks 1–8. Fix any finding introduced by this plan's lines, such as under-12 px text or low contrast on new copy. Leave pre-existing findings for Phase 2.
- [ ] **Step 2: One batched visual round.** Build and run each changed site locally (as in the baseline critique) and capture 1440×900 and 390×844 screenshots of:
  - the NFL page with the API stopped: error plus Try again;
  - the NFL page with only predictions failing: notice plus "No pick yet";
  - a PL finished gameweek: Pick line, one badge, labelled split, honest headline;
  - PL Track Record: the rebuilt-picks note;
  - NBA games: favourite-first, and an empty week showing "Next week →";
  - the Hub.

  Check the craft floor (contrast, 12 px floor, focus, states), fix everything in one batch, and allow at most one confirm round.
- [ ] **Step 3: Whole-branch review** with superpowers:requesting-code-review against this plan and spec. Fix any findings.
- [ ] **Step 4: Push** each repo: `git push -u origin claude/sports-predictors-frontend-plan-qpab3v`.
- [ ] **Step 5: Tracking.** Add a Phase 1 row to the spec's tracking table after re-running `/impeccable critique` (target: heuristics 1, 2 and 9 rise; overall ≥ 22/40).

---

## Self-review (done)

- **Spec coverage:**

  | Spec step | Covered by |
  |---|---|
  | 1 | Tasks 1–3 |
  | 2 | Tasks 4–5 (pick, verdict, rebuilt label, count excluded in API and UI, "Leaned draw" moved to the tooltip) |
  | 3 | Task 5 (stuck line removed) and Task 6 (refresh buttons hidden) |
  | 4 | Task 7 (NBA states and favourite) and Task 8 (Hub status) |

  The live NBA "is there a pick" check needs the VPS; Task 9's local run cannot confirm it, and the report must say so.
- **Placeholder scan:** Task 6 Step 1 and Task 7's calibration test point at existing prop and test shapes to copy, not TBDs. The assertion strings are given.
- **Type consistency:**
  - `predictionsSettled` in Tasks 2–3.
  - `matchPick` and `prekickoffTally` in Task 5.
  - `n_rebuilt_fixtures` and `n_rebuilt` in Tasks 4 and 6.
  - `favourite` in Task 7.
- **Review focus:** each line has a test.

  | Focus item | Test |
  |---|---|
  | 1 | `prekickoffTally` zero-settled test, and the API only-rebuilt test |
  | 2 | `matchPick` tie test |
  | 3 | GamesPage all-predictions-fail test |
  | 4 | Retry asserts a second `games` call |
  | 5 | NBA exact-50% test |
