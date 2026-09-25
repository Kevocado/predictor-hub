# Phase 2 · Family Design System — Spec

**Date:** 2026-09-25
**Status:** direction pinned by Kevin; this spec records it for review.
**Product truth:** [`PRODUCT.md`](../../../PRODUCT.md) (users, the honesty rule, and "five sports, full depth").
**Roadmap:** [2026-09-25-predictor-frontend-action-plan.md](../plans/2026-09-25-predictor-frontend-action-plan.md), Phase 2 (steps 5–8) and Phase 3 (steps 9–12).

## Kevin's direction

> "The PL predictor's structure had the most potential, so I want something closest to that, and it can change slightly from sport to sport. The tower makes sense for all the F1 stuff, but for the other sports it can be different. I don't want a strict design across all sports; I want a consistent design that can talk to the different sports and be tweaked for each sport's page."

Earlier decisions still stand:
- **Broadcast scoreboard tone.**
- **Trust first.**
- **Rebuilt picks never counted.**
- **Every sport keeps its full Games and Data Hub.**

An impeccable concept roll ran in degraded mode (the roll service is blocked here, so there were no challengers). It assigned a timing-tower direction. Kevin's pinned direction beats the roll. The roll survives only where Kevin placed it: **F1's slate is a timing tower**.

## 1. The system in one line

**One family grammar with sport dialects.** Every site shares:
- the frame;
- the type;
- the neutral stage;
- the state vocabulary;
- the number formatting;
- the core components.

Each sport picks its own slate layout, accent colour and extras.

## 2. Shared grammar (the family)

Built from PL's structure, with PL's template tells removed.

| Layer | Family rule | Taken from PL | Removed from PL |
|---|---|---|---|
| **Frame** | Wordmark **PREDICTOR** · sport name · a sport switcher to the other four sites · page tabs | Header with segmented tabs | The gradient letter tile |
| **Page tabs** | **Games** · **Data Hub** · sport extras · **Model** | Fixtures / Data Hub / FPL / Model | — |
| **Games page** | Round navigator (Gameweek, Week, Round or date-week) with a **record headline** on the same row ("4/7 picks made before kickoff correct"). One **Next up** hero per round, then that round's slate. | `CurrentGameweekSection`, `NextFixtureHero`, card grid | "not current" pill (replaced by "Jump to next round") |
| **Match detail** | A sheet: full width on phones, a dialog on desktop. Order: pick and why, markets, form, head-to-head, then review after the result. | `FixtureModal`, prediction review | The raw enum rows |
| **Data Hub** | Sub-tabs for Teams, Players, Standings or Rankings, and Track Record, rendered as dense `StatTable`s | DataHub sub-tabs | Two-tier cells, 9–10 px text |
| **Type** | One family: **Barlow Condensed** for display (scores, numbers, headers, set in caps like TV graphics) and **Barlow** for body. Tabular figures on every number. | Condensed display for scores | Inter, Oswald, Titillium, Big Shoulders, Manrope |
| **Stage** | A flat near-black ground, one raised panel step, one 1 px rule colour. Dark is chosen for the scene: phones at kickoff, evenings, next to a TV. | Dark ground | Radial purple glow, gradients, neon cyan, glass |
| **Shape** | Radius 6 px. **One clipped corner** (a single notch, like a broadcast graphic) is the family mark, on the hero and match cards only. | `clip-corner` | Clip on every surface |
| **Status** | At most **one** status badge per card, 12 px or larger: *Next up* · *Live* · *Final ✓ Called it* · *Final ✗ Missed* · *No pick yet* · *Rebuilt after kickoff*. Colour always sits next to words. | Called it / Missed | Stacked Backfilled + Leaned draw + Final + verdict |
| **States** | `Skeleton` (named: "Loading picks…"), `EmptyState` with a next step, `ErrorState` with Try again. All carry `aria-live`. | Phase 1 states | — |
| **Numbers** | Every number on screen goes through `fmt` (§5) | — | Raw floats, ISO dates, version ids |
| **Spacing** | 4 / 8 / 12 / 16 / 24 / 32 | — | — |

## 3. Sport dialects

| Sport | Accent (one per site) | Slate layout | Extras kept |
|---|---|---|---|
| **PL** | PL magenta | **Match cards**: crest · score or kickoff · crest, pick line, labelled H/D/A bar | FPL tab, value bets, player picks |
| **F1** | Signal red | **Timing tower**: ranked driver rows, position, team colour chip, win % large, podium/points/DNF small, one-hue intensity | Qualifying / Race / Sprint toggle, Championship, live session |
| **NFL** | Field blue (was "field green": green is the *Called it ✓* status colour, so NFL uses blue to keep status unambiguous) | **Match cards** with spread and total written with a team ("KC −3.5") | Props, power rankings, standings |
| **CFB** | Collegiate gold | NFL's cards; conference filter as one select | Conference filter |
| **NBA** | Court orange | **Match cards**, compact (many games a night), grouped by day, favourite-first | Props, calibration |
| **Hub** | Neutral (white on stage) | A "This weekend" stack: each sport's next-up pick and pre-kickoff record, then the switcher | — |

- **Team identity:** PL crests stay. Other sports use a `TeamChip` (team colour plus abbreviation); there are no logos.
- **Accent contrast:** each accent must reach 3:1 on the stage for UI elements. Text on an accent fill must reach 4.5:1. Tests enforce both.

## 4. Package and distribution

- The package lives at `predictor-hub/packages/predictor-ui/`. Kevin chose this over a separate repo for now.
- Its contents are `tokens.css` (CSS variables plus a Tailwind v4 `@theme` mapping), `fmt.ts` and the React components.
- **Distribution is vendoring.**
  - `scripts/sync-ui.mjs` copies the package source into each site at `src/predictor-ui/`.
  - Each copy starts with a `// synced from predictor-hub@<sha> — do not edit` header.
  - Each site has a test that fails if its copy is edited by hand, by comparing it against a checksum written by the sync.
- **Why vendoring:**
  - Each site builds in its own Docker image, from its own repo, on the VPS.
  - A git or tarball dependency would need the hub repo to be reachable at build time.
  - Vendored source also compiles against each site's own React and Tailwind versions (NBA is on Vite 6).
- The API matches a future npm package, so switching later means changing import paths only.

## 5. `fmt`, the one owner of on-screen numbers

| Function | Input → output |
|---|---|
| `pct(p)` | `0.47` → `47%`; `0.004` → `<1%`; `0.996` → `>99%` |
| `pctFine(p)` | whole % above 10%, one decimal below it: `0.064` → `6.4%` |
| `stat(x)` | one decimal: `16.51` → `16.5` |
| `signed(x)` | `1.5` → `+1.5`; `-1.5` → `−1.5` (true minus sign) |
| `streak(n)` | `-1` → `L1`; `3` → `W3` |
| `margin(home, away, x)` | x = home − away: `("TOR","MIA",−4.8)` → `MIA by 4.8`; `\|x\| < 0.5` → `Toss-up` |
| `spread(team, line)` | `("KC", -3.5)` → `KC −3.5`; `0` → `KC PK` |
| `record(hits, n)` | `(4, 7)` → `4/7`; `n = 0` → `—` |
| `kickoff(iso, tz?)` | → `Sat 3 Oct · 7:30 PM CDT` (always shows the zone) |
| `modelDate(id)` | `v20260918120240` → `Sep 18 model` |

Unit tests pin every row.

## 6. Components

The core set is shared. Sports opt in to the rest.

| Component | Used by |
|---|---|
| `AppFrame`, `SportSwitcher`, `PageTabs` | All sites |
| `RoundNavigator` (with the record headline slot) | All except the Hub |
| `NextUpHero` | PL, NFL, CFB, NBA, F1 (the next race) |
| `MatchCard` with `ProbabilityBar` (two-way or three-way, **labelled**, in team colours, header order) | PL, NFL, CFB, NBA |
| `TimingTower` | F1 |
| `StatusBadge`, `TeamChip`, `StatTile`, `StatTable` | All |
| `Skeleton`, `EmptyState`, `ErrorState` | All |
| `DetailSheet` | All match detail |

## 7. Rollout order (unchanged from the roadmap)

1. **2a:** the package (tokens, `fmt`, core components, sync script).
2. **2b:** move the NFL + CFB site onto it. That site is live in football season.
3. **2c:** NBA, before the late-October tip-off.
4. **2d:** Hub.
5. **2e:** F1, the timing tower.
6. **2f:** PL, the reference; mostly a token swap.

Each step is its own superpowers plan and runs through impeccable. In each migration:
- `typeset` covers the type;
- `clarify` covers the copy;
- `adapt` covers phones first;
- `layout` covers density.

Each migration is followed by a detector run and a batched desktop and mobile check.

## 8. Success

- A screenshot of any two sites reads as the same product.
- Each sport still reads as its own sport (the F1 tower, NBA's compact nightly slate).
- No Inter, no radial glow, no badges under 12 px, no raw floats.
- The detector is clean on every migrated site. Re-running `/impeccable critique` scores **28/40 or higher**, up from 18.

## 9. Open decisions (not for the builder to invent)

- The final accent hex values. They are proposed in `tokens.css` and must pass the contrast tests; Kevin reviews them on the first migrated site.
- A real domain (it affects the frame's sport-switcher links).
- Whether bettor-facing odds and value comparisons appear on every sport, or stay PL and NFL only.
