# Phase 2e · F1 site onto `predictor-ui`: implementation plan

> **For agentic workers:** follow superpowers:executing-plans, test first.
> **Design:** run `/impeccable` typeset, clarify, adapt and layout on this site, and read `reference/craft-floor.md` before editing UI. Finish with `impeccable detect` and one batched desktop and mobile round.

**Goal:** the F1 site (`Kevocado/F1_Predictor`) joins the family. It keeps its own dialect, the **timing tower**, as Kevin asked ("the tower makes sense for all the F1 stuff"). It also gets the Phase 1 trust fixes it never had.

## Finding that reorders the work: the whole 2026 track record was built after the races

Every resolved row in `data/tracking.db` has a `snapshotted_at` of 2026-08-23, after all 12 races it covers had run. Even so:
- the site served those rows as `source: tracked`, described as "the honest, un-hindsight-biased prediction";
- the Track Record page counted them.

**Fixed in the backend first:**
- `store.made_before_session` decides whether a snapshot came before its session.
- The track record and the per-race accuracy judge only snapshots made before the session. They report `n_rebuilt_sessions` and a `rebuilt` flag per session.
- A completed session whose snapshot came after it is served as `rebuilt`.

## Constraints

- **Honesty:**
  - `rebuilt` and `backtest` sources read "Rebuilt after the session", never "tracked".
  - The record and summary tiles leave rebuilt sessions out and say how many.
- **Tower:**
  - Ranked rows, one per driver.
  - Predicted position, team-colour chip, driver and team.
  - One large number: win %, or pole % for qualifying.
  - Podium, points and DNF (or top 3 and top 10) small, beside it.
  - One-hue intensity in the F1 accent, never a rainbow.
  - Each row expands to show "what's driving it".
- **Phase 1 trust:**
  - Same-origin `/api` by default, with a dev proxy.
  - A 15 s timeout.
  - Every failure gets Try again.
  - No text under 12 px.
  - Every number goes through `fmt`.
- **Tests:** the site had none. Add Vitest and Testing Library, running in `America/Chicago`.

## Tasks

1. **Backend honesty** (done: 5c4db91).
2. **Package:** `Moment` gains `"the session"`, then resync every site.
3. **Tooling:** Vitest, a vendored `predictor-ui` with its drift test, `index.css` (fonts, tokens and the `f1-*` alias), and the client (same-origin, timeout).
4. **Frame:** `AppFrame` with tabs for Races, Championship and Track record. Pages stay mounted, so tab switches never refetch.
5. **Races:**
   - a race list with next-up and completed status in words;
   - a session panel with the date in the viewer's zone and an honest source badge;
   - the `TimingTower` in place of `PredictionTable`.
6. **Championship and Track record:**
   - family tables with a single-hue intensity;
   - "Projected rank 3.4" instead of "rank 3.4";
   - rebuilt sessions labelled and left out of the summary tiles;
   - plain copy;
   - 12 px or larger.
7. **Verify:** run the detector, a visual round against a local API, a fresh review, then push and open a PR.
