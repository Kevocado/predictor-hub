# Phase 2c · NBA site onto `predictor-ui`: implementation plan

> **For agentic workers:** follow superpowers:executing-plans one task at a time, test first.
> **Design sub-skills:** run `/impeccable` typeset, clarify, adapt and layout on this site, and read `reference/craft-floor.md` before editing UI. Finish with `impeccable detect` and one batched desktop and mobile round.

**Goal:** before the late-October tip-off, move the NBA site (`Kevocado/NBA_Predictor`) onto the shared family design. It gets:
- the shared frame;
- a week navigator that carries an honest record;
- NBA's own dialect: compact match cards grouped by day, with real team colours.

It keeps Data Hub, Calibration and Model.

**Spec:** [../specs/2026-09-25-phase2-family-design-system.md](../specs/2026-09-25-phase2-family-design-system.md), sections 2, 3 (the NBA row), 6 and 7 (2c).

## Finding that reorders the work: NBA counts picks made after the game

`pipeline/ingest.py::score_and_store_predictions` backtests every completed game, and it writes those rows into the same `predictions` table as live picks, with `created_at` set to the time the backtest ran. Three places then read the latest row per game:
- the cards;
- the track record (`hub_service._settle_game_outcome`);
- calibration.

So once a retrain has run, every final shows a pick that was built after the game, and all three count it. That breaks the rule Kevin set: rebuilt picks are never counted. **This is fixed in the backend first.**

**The tip-off cutoff:**
- ESPN's scoreboard carries each game's start time (`event.date`, in UTC). The schedule gains `tip_off` from it.
- Scoreboards cached before this change have no `tip_off`. For those games the cutoff is **12:00 US Eastern on `game_date`** (ESPN's `dates` parameter is the Eastern date). No NBA game tips before noon Eastern, so a pick made before that time is always pre-game.

## Global constraints

- Keep every Phase 1 behaviour and its tests:
  - request timeout;
  - Try again on the Games and Calibration pages;
  - the empty week offers the next week;
  - the favourite leads;
  - the margin line never contradicts the pick.
- **Team identity:** NBA has no logos. `TeamChip` uses each team's real primary colour, from a site map of all 30 teams. Never hash-derived.
- **Wording:** basketball says **tip-off**, not kickoff. The package takes a `moment` word, so status and record lines read "Rebuilt after tip-off" and "picks made before tip-off correct".
- No text under 12 px. No Big Shoulders, Manrope or raw floats on rebuilt surfaces.

## Tasks

### Task 1: backend honesty (`NBA_Predictor`, pytest)

- `data/espn.py`: add `tip_off` (the ESPN `event.date` value) to each game.
- `tracking/timing.py` (new):
  - `pick_cutoff(game)` returns `tip_off` when it is present, otherwise 12:00 America/New_York on `game_date`, as a UTC datetime.
  - `made_before_tip(created_at, game)` returns False on any parse error, so a pick is never counted by accident.
- `api/routes.py::_game_out`:
  - `prediction` is the latest **pre-tip** prediction, falling back to the latest prediction;
  - `rebuilt` is true when the prediction shown was made at or after the cutoff;
  - `tip_off` is passed through.
  - Schemas: add `GameOut.rebuilt: bool = False` and `GameOut.tip_off: str | None`.
- `services/hub_service.py`:
  - `_settle_game_outcome` settles only the latest pre-tip prediction per game;
  - h2h market rows are filtered the same way;
  - `TrackRecordOut` gains `n_rebuilt: int = 0` (the number of final games whose only picks were made after tip-off).
- `services/calibration_service.py`: bins use only pre-tip predictions.
- Tests:
  - a backtest row alone makes a final `rebuilt`, and it is left out of the record and calibration;
  - a pre-tip row beats a later rebuilt row;
  - the noon-Eastern fallback;
  - an unparseable timestamp is not counted.

### Task 2: package changes (predictor-hub), then resync every site

- `StatusBadge` / `statusWords` take `moment` (default `"kickoff"`).
- `MatchCard` and `RoundNavigator` pass `moment` through.
- `MatchCard` gains `compact`: tighter padding and a smaller score, for nights with 10 or more games.
- Tests come first. Resync Sports_Predictor too, so its drift test stays green.

### Task 3: vendor, fonts, tokens, palette alias (NBA frontend)

- Vendor the package and add a sync drift test.
- Import `fonts.css`, then tailwindcss, then `tokens.css`.
- Alias `--color-court-*`, `--color-line`, `--color-hardwood*`, `--color-net*`, `--color-win` and `--color-shotclock` to the `pr` tokens.
- `index.html` drops the Big Shoulders and Manrope links.
- Vitest runs with `TZ=America/Chicago`.

### Task 4: the family frame, with router tabs

- `App` uses `AppFrame`, with `sport="nba"` and `sportName="NBA"`.
- Tabs are Games · Data Hub · Calibration · Model. Each tab maps to the existing route, and the active tab comes from the location.
- `lib/sites.ts` links to the other sites; NFL and CFB go to `sports…?sport=`.

### Task 5: the Games page (`lib/nightCards.ts` mapper plus the page)

- `toCardModel(game, now, tz)`:
  - **Teams:** away on the left, home on the right, as coloured `TeamChip`s.
  - **Centre:** the score on a final; otherwise the local tip time, or "at" when the time is unknown.
  - **Pick:** the favourite, with home winning an exact 50% (the existing rule).
  - **Bar:** away, then home.
  - **Meta:** the margin line (shared with the modal, so it never contradicts the pick), then `Total 224.5`.
  - **Status:**
    - final: `nopick`, `rebuilt`, or `called`/`missed`;
    - started: `live`, until about 3.5 h past tip-off;
    - started and past that: "Awaiting result";
    - not started: `next` for the earliest tip still to come in the current week.
- `weekTally(games)` counts only pre-tip picks and reports rebuilt ones separately.
- The page:
  - `RoundNavigator` labelled with the week range, with its record and "Jump to current week";
  - day headers;
  - a compact card grid;
  - "Tip-off times in CDT";
  - Phase 1's states and their copy.

### Task 6: Data Hub and model surfaces

- **Track record:**
  - rows show picks made before tip-off;
  - the rebuilt note;
  - `fmt.pct`;
  - plain market names.
- **Calibration:** says it uses pre-tip picks only.
- **Model:** `fmt.modelDate` and a readable trained date; metrics through `fmt.stat`.
- **Hub sub-tabs:** scroll on phones; `aria-current`.
- **Modal:** the pick section says whether the pick was made before tip-off or rebuilt; for a rebuilt pick, the verdict says it isn't counted.

### Task 7: clean up and verify

- Delete `GameCard`, once `favourite` has moved to `lib/pick.ts`.
- Run `tsc` and vitest.
- Run the detector.
- Visual round: seed a scratch tracking DB with pre-tip, rebuilt and missing picks, capture desktop and mobile, and fix everything in one batch.
- Run a fresh whole-branch review. Fix every Critical and Important finding.
- Push, and update PR #1.

## Review focus

1. A final with only a backtest row reads "Rebuilt after tip-off", is not counted, and never shows Called it or Missed.
2. A week of 50 games stays readable at 390 px, and the grid is compact on desktop.
3. Games with no `tip_off` (old cache) show the date only, no fake time, and nothing is marked Next up.
4. The track-record hit rate matches the week records: pre-tip picks only.
