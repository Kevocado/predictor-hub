# Phase 2f · PL site onto `predictor-ui`: implementation plan

> **For agentic workers:** follow superpowers:executing-plans, test first.
> **Design:** run `/impeccable` typeset and adapt on this site. Finish with `impeccable detect` and one batched desktop and mobile round.

**Goal:** PL (`Kevocado/PL_Predictor`) is the reference the family grammar was taken from (spec, section 2), so this step is mostly a token swap. PL keeps its own dialect:
- club crests;
- the next-fixture hero;
- the labelled home/draw/away bar;
- the likely scoreline;
- value bets;
- the FPL tab.

It drops PL's template tells: the gradient letter tile, Inter and Oswald, the radial purple glow, the "not current" pill, and 9–11 px text.

Phase 1 already fixed PL's honesty (rebuilt picks are never counted; commits c72536d, 6a30512 and 36ea935). This step keeps every one of those tests.

## Tasks

1. **Tokens.**
   - Vendor `predictor-ui`, with a drift test.
   - `index.css` imports the fonts, then tailwindcss, then the tokens.
   - The `pl-*` colours alias onto the family tokens (`@theme inline`, so the PL magenta accent follows `data-sport`).
   - No Inter, no Oswald, no radial gradient.
   - Vitest runs in `America/Chicago`.
2. **Frame.**
   - `AppFrame` with `sport="pl"`.
   - Tabs: Fixtures, Data Hub, FPL, and Model (Calibration in the admin build).
   - Tabs still mount on first visit and then stay mounted.
3. **Gameweek navigator.**
   - `RoundNavigator` (unit "gameweek") carries the pre-kickoff record line.
   - "Jump to current gameweek" replaces the "not current" pill.
   - Kickoff times go through `fmt.kickoff`, which always shows the zone. The hero and the cards say which zone the times are in.
   - Loading, error and empty states use the family `Skeleton`, `ErrorState` (with Try again) and `EmptyState`.
4. **Type floor:** every `text-[9|10|11px]` becomes 12 px, with a test that fails on any regression.
5. **Verify:** run the detector, the visual round and a review, then push. PR #1 carries it.
