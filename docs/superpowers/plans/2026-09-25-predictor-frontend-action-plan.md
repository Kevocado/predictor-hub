# Predictor Frontends — Action Plan (v2)

**Date:** 2026-09-25
**Scope:** frontend design only. All five sites (Hub, PL, F1, NBA, NFL + CFB) are served from the new VPS.
**Inputs:**
- *Predictor Apps — Frontend Design Critique* (Sep 25).
- `/impeccable critique`, run the same day (dual-agent design review plus the detector). Score **18/40**. The snapshot is in `.impeccable/critique/`.

**Decisions (Kevin, 2026-09-25):**

| Question | Decision |
|---|---|
| What comes first | **Trust**: the site must never lie and never hang |
| Visual direction | **Broadcast scoreboard** |
| Scope | **All issues** |
| Picks rebuilt after kickoff | **Left out of the hit rate**. They stay visible and labelled. |

v1 of this plan covered hosting and trade hub integration. Hosting is now settled (everything on the VPS) and the trade hub stays out of scope, so v2 drops both.

---

## North star

Every site answers one question in the first five seconds: **who does the model like, how sure is it, and has it been right?**

One shared unit answers it everywhere. The **Pick Bug** is a broadcast-style score bug:
- the two teams in header order (away @ home, or home v away for PL), each with a team-colour chip;
- the pick in words ("Pick: Villa win");
- the confidence as a big tabular number;
- a probability bar coloured by team, not green/red;
- after the match: the result and a ✓/✗ judged against that same pick.

Scorelines, spreads and props sit under the Pick Bug as supporting detail.

## Visual direction: broadcast scoreboard

This is a starting brief. `/impeccable shape` (step 4) finalises it.

- **Type:** one condensed display face for scores, team codes and headers, used in capitals like TV graphics. One sans body face from the same family if possible (for example Archivo with Archivo Narrow/Condensed). Tabular numbers everywhere. Drop Inter, Oswald, Titillium, Big Shoulders and Manrope; the detector flagged Inter on 4 of the 5 sites.
- **Colour:** near-black stage, one raised panel colour, hard 1px rules. Each sport gets **one** hot accent, used like a network's graphics package:

  | Sport | Accent |
  |---|---|
  | PL | pitch green |
  | F1 | signal red |
  | NBA | court orange |
  | NFL | field navy with white |
  | CFB | collegiate gold |

  Team colours appear only in chips and bars. Remove the purple radial glow, the cyan "neon" text, the F1 radial halo and the coloured box-shadow glows, which the detector flagged as AI-palette tells.
- **Shape and motion:** squared or 2–4 px corners, with slabs and lower-third bars instead of glassy cards. A short wipe or slide-in when a result settles. No pulsing dots.
- **Hierarchy:** exactly one number shouts on each card, the confidence (or the final score once finished). Badges are 12 px or larger and limited to one per card. The detector counted 9–10 px badge text 38× on PL, 52× on F1 and 4× on the Hub.
- **Contrast floor:** 4.5:1 for all text, including faint metadata. The detector found 59 failures on NFL/CFB (#6d7684 on #181e27 is 3.6:1) and 55 on F1.

---

## Phase 1 · Trust: nothing lies, nothing hangs

**Status (2026-09-25):** implemented, reviewed and pushed on `claude/sports-predictors-frontend-plan-qpab3v` in Sports_Predictor, PL_Predictor, NBA_Predictor and predictor-hub. Carried over: the "last updated" time in error states and "Odds updated N min ago" need the snapshot's `updated_at`, so they move to the Phase 3 snapshot-first render. The live-VPS check that NBA cards show picks is still open.

**Implementation plan:** [2026-09-25-phase1-trust.md](2026-09-25-phase1-trust.md). Each phase gets its own executable plan (superpowers:writing-plans), and each UI task runs through its `/impeccable` command.

| # | Command | Target | Work | Done when |
|---|---|---|---|---|
| 1 | `/impeccable harden` | Sports_Predictor (NFL + CFB) | **P0.** A failed fetch currently shows "Loading…" and a pulsing bar forever (`GameCard.tsx:21-22,36`). Replace it with a card-level and page-level error state: "Predictions unavailable", a **Retry** button, and the last-updated time, with the schedule kept visible. Replace the hostname sniffing in `src/api/client.ts` with a relative `/api/nfl` and `/api/cfb`, which the VPS Caddy proxies. Add `aria-live` on status text. | Killing the API shows a readable error with a working Retry, and the live VPS site loads the picks |
| 2 | `/impeccable clarify` | PL_Predictor | **P1 trust.** Each card states one pick, and ✓/✗ is judged against that pick. Today "predicted 1-1, finished 1-1" shows MISSED and "predicted 1-1, finished 2-3" shows CALLED IT (`FinishedFixtureCard.tsx:80-88`). Demote the scoreline to "Most likely score 1–1". **Leave rebuilt picks out of the "called correctly" headline** (`CurrentGameweekSection.tsx`), and move the same rule into the API if the count is computed there. Merge BACKFILLED and RECONSTRUCTED into one label, "Rebuilt after kickoff", shown on the card but not counted. Drop "Leaned draw" into a tooltip. | No card can show a verdict that contradicts its own pick, and the headline counts only picks made before kickoff |
| 3 | `/impeccable harden` | PL_Predictor | Remove the "Refreshing official scorers and assists…" line that never resolves (`FinishedFixtureCard.tsx:117`); show nothing, or "Scorers not yet confirmed" once the data is 24 h old. Hide "Refresh odds" and "Refresh live data" in public mode, and show "Odds updated 12 min ago" instead. | No public button triggers backend work |
| 4 | `/impeccable harden` | NBA, F1, Hub | Every empty or error state gets a next step: NBA "No games this week" gets a link to the next game week, and Calibration explains when results will appear. The Hub stops labelling NBA LIVE next to "Work in progress"; use honest status ("Preseason"). Also confirm on the live VPS whether NBA cards show a pick (the local snapshot showed "Pending"). The game pop-up must show the prediction, not only form and head-to-head. | Every NBA game card and pop-up shows a pick |

## Phase 2 · The family system

**Status (2026-09-25):** 2a (the `predictor-ui` package) is done. 2b (the NFL + CFB site) is done and reviewed; it needed backend changes in `NFL_Predictor` and `CFB_Predictor`, which now flag picks rebuilt after kickoff and leave them out of the track record. 2c (NBA) is built. It fixed a larger honesty hole in the NBA backend: the retrain backtest wrote picks for finished games into the live table, and the cards, track record and calibration all judged them. NBA now records each game's tip-off and counts only picks made before it. 2d (Hub restyle) is done; the live "this weekend" ticker stays in Phase 4, step 13, because it needs the sport APIs reachable from the Hub (CORS or a same-origin proxy). 2e (F1, timing tower) is built and reviewed. Its whole 2026 track record turned out to have been snapshotted after the races; it now counts only pre-session snapshots (all 12 current races read as rebuilt). Next up: 2f PL.

| # | Command | Target | Work |
|---|---|---|---|
| 5 | `/impeccable init` | predictor-hub | Write `PRODUCT.md`: audience (sports fans on their phones), the one-question promise, the pre-kickoff honesty rule, five sports and one product. impeccable requires this before `shape`. |
| 6 | `/impeccable shape` | the family system | Finalise the broadcast-scoreboard brief above. It defines: the **app frame** (product wordmark, sport switcher, page tabs, links between sites); the **Pick Bug**; `ProbabilityBar` (team colours, header order); `StatTable` (right-aligned tabular numbers); `StatTile`; `Skeleton` / `EmptyState` / `ErrorState`; `Badge` (one per card); `TeamChip`; and `SportMark` (one SVG mark per sport, also used as the favicon). |
| 7 | `/impeccable document` | predictor-hub | Write `DESIGN.md` with tokens (colour, type scale, 4/8/12/16/24/32 spacing, radius, motion) and component rules. |
| 8 | `/impeccable extract` | new `Kevocado/predictor-ui` | Package `tokens.css`, `fmt.ts` and the React components, consumed by every site as a tagged git dependency. `fmt` owns every number on screen: whole-number %, `<1%` / `>99%`, signed net rating, W3/L1 streaks, "MIA by 4.8", "WAS +4.5" spreads, "Sep 18, 7:02 AM CT" dates, and "Sep 18 model" in place of version ids. |

## Phase 3 · Move each site onto the system

Order: **Sports** (football season is under way, and it's the P0), **NBA** (before the late-October tip-off), **Hub**, **F1**, **PL**. Each site goes through the same four commands. Each run changes that site only.

| # | Command | What it fixes on each site |
|---|---|---|
| 9 | `/impeccable clarify` | Every piece of developer language. NBA Model Summary (`win_probability`, raw floats, ISO timestamp, version id) becomes three StatTiles: "Picks the winner 64% of the time", "Off by ~14 pts on margin", "Off by ~X pts on total". Also: PL `home_win → home_win` becomes "Home win"; PL "RPS / Brier" gets a plain-language gloss; NFL "rest 4d/4d (a/h)" becomes "Both teams on 4 days' rest"; NFL "Spread -3" gets its team; NFL's "from your machine learning models" goes; F1 "rank 1.1" goes; NFL "60% confident" names the team; the repeated raw date on NBA cards goes. |
| 10 | `/impeccable typeset` | Apply the shared type. Tabular, right-aligned number columns. One shouting number per card. No text under 12 px. |
| 11 | `/impeccable adapt` | **The first screen is the next pick, on phones first.** PL opens on the next unplayed gameweek. On F1 mobile the race list becomes a selector and the grid becomes stacked driver rows (win % large; podium, points and DNF small), replacing the 680 px table that shows only WIN. The PL pop-up at 390 px: the score no longer wraps, form pills no longer clip, the "Recommended" chip no longer overlaps. Tabs and games move into the URL on PL, F1 and NFL, so Back, refresh and shared links work (NBA already does this). |
| 12 | `/impeccable layout` | **NFL Hub:** replace the 17,697 px wall of players with position sections, "top 10 + show all", and a jump-to-position control. **CFB:** 13 conference chips become one select. **PL Data Hub:** 4 tabs plus 5 sub-tabs drop to 5 or fewer options at each level. **NFL/CFB:** sport goes in the app frame and Games/Hub are the page tabs. **NBA:** the Data Hub sorts by standings. |

Site-specific items that ride along with that site's pass:

- **Sports (NFL + CFB):**
  - The bar order matches the team row. Today the bar is home-first under an away-first row (`ProbabilityBar.tsx:13-18` vs `GameCard.tsx:25-33`).
  - Kickoff times show their time zone.
  - The CFB conference badge appears once when both teams share a conference.
  - The week control shows that NFL and CFB have separate weeks.
  - Leader names no longer truncate ("JOE B…").
  - "Team yardage: Total 1079" gets a per-game label.
  - The name is the same everywhere (not both "Sports Predictor" and "American Football Predictor").
- **NBA:**
  - Records are filtered to the regular season, or labelled if they include playoffs (they currently exceed 82 games).
  - Streaks show as W/L.
  - Team-colour chips and full team names in the game pop-up.
  - Calibration becomes a reliability chart (predicted vs actual, with the diagonal), built with the dataviz skill.
- **F1:**
  - `/impeccable quieter` on the heat grid: one accent hue at varying intensity for win/podium/points, and DNF becomes a muted plain number.
  - Whole percents, with one decimal only under 10%.
  - "0.0%" becomes "<0.1%".
  - One name format for all drivers.
  - Track Record includes R13 and R14.
  - The race list opens scrolled to the next race.
- **PL:**
  - Model page feature charts render their bars.
  - The season range label is fixed (it shows "2018-2019–2026-2027").
  - Tottenham's crest gets a light plate so it doesn't vanish on the background.
  - "Per match 6.20" becomes 6.2.
  - "6/10 called correctly" is promoted into the header, now counting pre-kickoff picks only.
- **Hub:** its pass is step 13.

## Phase 4 · The Hub becomes the front page

| # | Command | Work |
|---|---|---|
| 13 | `/impeccable shape`, then build | The Hub is a **Persuade** surface. Build a broadcast "tonight / this weekend" ticker of the next pick in each sport (a Pick Bug per sport), with the season hit rate beside each ("F1: Russell 18% to win Baku · 6/12 winners called"), and the sport switcher from the shared app frame. Remove the emoji cards, the four identical LIVE badges, and the filler copy ("walk-forward-validated scoreline model", "no login required", "Work in progress"). Links are the VPS subdomains, or relative paths once everything shares one origin. SportMark favicons and page titles follow the pattern `MIA @ TOR · NBA Predictor`. |
| 14 | `/impeccable delight` (optional) | Broadcast touches only where they add meaning: a result "final" wipe on settle, and a hit-rate ticker. No decoration elsewhere. |

## Phase 5 · Verify

| # | Command | Work |
|---|---|---|
| 15 | `/impeccable audit` | Accessibility and technical pass on all five sites: 4.5:1 contrast; clickable cards become real `<button>` or `<a>` elements that respond to Enter **and** Space (today `div role="button"` responds to Enter only: `FinishedFixtureCard.tsx:64-67`, `GameCard.tsx:15`); visible `:focus-visible` rings; `aria-live` on status text; nothing conveyed by colour alone; no sideways scroll at 390 px. |
| 16 | `/impeccable polish` | A final pass on each site, then re-run `/impeccable critique`. Target **≥ 28/40** (Good). |

### VPS items the frontend depends on

These come in Phase 1 or when each site is migrated, not as a separate phase.

- One Caddy on the VPS serves every site and proxies `/api/<sport>` on the same origin. This fixes step 1 permanently and removes CORS.
- Each page renders straight from its `public_snapshot.json` (already produced by the GitHub Actions crons) and shows "Updated N min ago", so pages don't open on skeletons.
- Per-game URLs (step 11) enable Open Graph share cards later: a server-rendered broadcast-style Pick Bug image per game.

## Tracking

Re-run `/impeccable critique` after each phase and record the score here.

| Date | Phase | Score |
|---|---|---|
| 2026-09-25 | baseline | 18/40 |
