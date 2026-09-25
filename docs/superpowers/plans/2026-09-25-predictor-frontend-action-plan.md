# Predictor Frontends — Action Plan

**Date:** 2026-09-25
**Input:** *Predictor Apps — Frontend Design Critique* (Sep 25, 2026), which reviewed the five live sites on the VPS.
**Related:** the trade hub rollout in `Kevocado/algo-trade-hub-prod`, in `docs/superpowers/specs/2026-09-23-trade-hub-prediction-scope-design.md` §3.2 and `docs/superpowers/plans/2026-09-24-rollout-tracker.md` step 7.

This plan turns the critique into work items for each repo, adds what reading the code turned up, and shows where the work meets the trade hub plan. The critique's phase order stays the same: fix what's broken, then formatting, then the shared system, then VPS features.

---

## 1. What the code confirms and adds

| Critique finding | Cause in the code | Repo |
|---|---|---|
| NFL + CFB show "Failed to fetch" | `src/api/client.ts:99` picks the API base with `hostname.includes("azurecontainerapps.io")`. On `sports.40-160-91-131.sslip.io` that check is false, so the build uses `http://localhost:8001/api` and `:8003`. The tests (`App.test.tsx`, `client.test.ts`) assert the localhost URLs, so they go on passing. | Sports_Predictor |
| Hub links to the old Azure URLs | `index.html:153–174` hard-codes four `*.proudbay-f56b8dfa.eastus2.azurecontainerapps.io` links. | predictor-hub |
| "Refresh odds" is a public button | `PL routes.py:1910` `/refresh-odds/public` is deliberately left open and asks GitHub Actions to run the snapshot early. | PL_Predictor |
| Pages show "Loading…" | Precompute **already exists**: each predictor has a `refresh-public-snapshot.yml` cron that commits `data/public_snapshot.json`, and the API polls it. Pages still render empty and then fetch that data through the API at runtime. | all predictors |

New findings (not in the critique):

- **Seven frontends, not five.** `NFL_Predictor/frontend` and `CFB_Predictor/frontend` are still built into their Docker images (`Dockerfile:1–6`) even though Sports_Predictor is the NFL + CFB site. They are two more code paths to keep consistent and two more ways to fall out of date.
- **Retrain is gated by an env var only on NFL and CFB.** `NFL routes.py:540` `/retrain` is blocked only if `PUBLIC_MODE` is set. The same is true for CFB. PL, F1 and NBA use an admin dependency. When the services moved to the VPS, nothing in any repo carried that env var across, so it needs checking on the box.
- **Stack drift.** PL, F1 and Sports run React 19 + Tailwind 4 + Vite 8. NBA runs Vite 6 + Recharts 2 + react-router. The NFL and CFB standalone frontends use plain CSS. The trade hub War Room (`market_sentiment_tool`) runs React 18 + Tailwind 3 + shadcn. A shared component library can only target the first group for now. Tokens and `fmt` can be shared by all of them.
- **No hosting config for the VPS is in any repo.** The Caddy, systemd and env setup that serves `*.sslip.io` lives only on the box. The trade hub spec (§5) still says to retire the VPS. See decision D1.

---

## 2. Where this meets the trade hub plan

The trade hub stays a **read-only consumer** of the predictors (spec §3.2), and its sports work is **rollout step 7**, which runs after steps 3–6. Most of that step depends on predictor work this plan already includes, so this plan should finish before step 7 is detailed.

| Trade hub step 7 needs | Predictor-side work that provides it | Phase here |
|---|---|---|
| Stable base URLs for each predictor API (spec §3.2 lists only the Azure FQDNs; NBA, PL and F1 are "fill in later") | Same-origin `/api` behind one reverse proxy, then a real domain | 0, 3 |
| `source_url`: a deep link to the predictor's **game page** | A per-game URL on every site (PL fixture, NBA game, NFL/CFB game, F1 race) | 2 |
| Candidate filter: "predictor calibrated within 10 pp in this bucket" | A shared `/track-record` contract with calibration buckets | 2 |
| Leakage check: "each predictor must store pre-game predictions" | The contract carries `predicted_at` and leaves out backfilled rows; PL's "Backfilled" label becomes a data flag | 2 |
| Trustworthy calibration | The NBA data checks: the 70–80% bucket winning 96% looks like in-sample scoring, and margin and win probability disagree | 0 |
| LLM fact pack (drivers, form, head-to-head) | Already exists (NFL/CFB `/verdict`, F1 `/explain`). No change needed. | — |
| Sports tab in the War Room shows the same numbers | Shared `fmt` and tokens, which don't depend on the framework | 1, 2 |

What stays separate:
- **The public Hub does not show Kalshi edges.** The trade hub is a private manual-trading tool. The public product shows picks and track records only.
- **The Hub's cross-sport track record reads the predictors' `/track-record` contract, not the trade hub `predictions` ledger.** The ledger is keyed by Kalshi ticker and settles against Kalshi results, so it only covers games that have a Kalshi market. The critique's "one predictions table" is met by one shared *contract*, not one table.

---

## 3. Decisions needed

**D1 — Hosting (conflict between the two plans).** The predictor sites are live on the VPS, and the critique's Phase 3 builds on it. The trade hub spec §5 and the step-5 plan still say "Azure scale-to-zero, retire the VPS", and the step-7 outline points at the Azure predictor URLs.
*Recommendation:* the VPS hosts the public predictor product (sites and APIs behind one Caddy, with a real domain). The trade hub keeps its verified step-5 plan (Azure jobs and API). Amend spec §5 from "retire the VPS" to "VPS serves the predictor sites and the crypto worker", and change the step-7 base URLs to `https://<domain>/api/<sport>`. Always-on hosting is also what removes cold starts, and cold starts cause many of the "Loading…" states.

**D2 — How the design system is shared.** *Recommendation:* create a small `Kevocado/predictor-ui` repo with three parts:
- `tokens.css`: CSS variables, no framework;
- `fmt.ts`: plain TypeScript;
- React components.

Consume it as a tagged git dependency (`"predictor-ui": "github:Kevocado/predictor-ui#v0.x"`, prebuilt `dist/` committed). The War Room imports only `tokens.css` and `fmt.ts`. A monorepo would be cleaner but means moving five repos, and that isn't worth it for this.

**D3 — Retire the NFL and CFB standalone frontends.** *Recommendation:* ship NFL_Predictor and CFB_Predictor as API-only (drop the `frontend-build` stage) and redirect their roots to the Sports site. That leaves five frontends to migrate instead of seven.

---

## 4. Phases

Effort estimates come from the critique where it gave one.

### Phase 0 · Today: every site loads for a stranger on a phone

| # | Task | Repo | Done when |
|---|---|---|---|
| 0.1 | Replace the hostname sniffing in `src/api/client.ts` with `import.meta.env.VITE_NFL_API ?? "/api/nfl"` (and the same for CFB). Add `handle_path /api/nfl/*` and `/api/cfb/*` `reverse_proxy` blocks to the VPS Caddy. Update the two test files to expect relative URLs. | Sports_Predictor, VPS | `curl https://sports.…/api/nfl/current-week` returns 200, and the page shows the current week, not Week 1 |
| 0.2 | Point the four Hub cards at the VPS subdomains. Remove "Work in progress" and "no login required". | predictor-hub | No `azurecontainerapps.io` in `index.html` |
| 0.3 | Emoji SVG favicon in every `index.html`, plus a per-route `document.title` using the critique's title pattern | all frontends | Each tab shows its sport icon and a page-specific title |
| 0.4 | On the VPS, confirm `PUBLIC_MODE` is set for NFL and CFB (or gate `/retrain` behind the same admin dependency the other three use), and that admin keys carried over. `POST /retrain` from outside should return 403. | NFL, CFB, VPS | Every write endpoint returns 401 or 403 from outside |
| 0.5 | Commit the VPS Caddyfile and service definitions to a repo (for example `predictor-hub/deploy/`) | predictor-hub | The box can be rebuilt from git |
| 0.6 | NBA data checks, done now because trade hub step 7 relies on them: (a) the margin sign against the win side (MIA @ TOR: TOR 47% but −4.8); (b) whether calibration is scored out of sample; (c) records over 82 games (filter to the regular season or label it). | NBA_Predictor | Each has a test or a written finding; calibration uses held-out games only |

### Phase 1 · This week: no raw decimal, snake_case key or ISO timestamp on any page

| # | Task | Repo |
|---|---|---|
| 1.1 | Create `predictor-ui` with `fmt.ts` (the critique's `stat`, `pct`, `signed`, `streak`, `date`, plus `margin(team, x)` giving "MIA by 4.8" and `version(id)` giving "Sep 18 model") and unit tests for every row of the critique's formatting table. Add `.num { font-variant-numeric: tabular-nums; text-align: right }`. | predictor-ui (new) |
| 1.2 | NBA: props as one row per player, grouped by team, with PTS / REB / AST / 3PM columns; Model Summary as three StatTiles plus the training date; calibration as a reliability chart with the diagonal (use the dataviz rules); lead each game card with the favourite; remove the repeated date. | NBA_Predictor |
| 1.3 | F1: one-hue heat map across all columns; whole percents, with one decimal under 10%; open the race list at the next race; fix name truncation and the grid-note overflow at 800 px. | F1_Predictor |
| 1.4 | PL: a labelled Home / Draw / Away bar; one status badge per card, with "Backfilled" and "Leaned draw" moved into a tooltip; move "6/10 called correctly" into the header; fix the "Refreshing official scorers…" line that never resolves on finished matches. | PL_Predictor |
| 1.5 | Replace every on-screen developer string (`win_probability`, `mae`, raw version ids, "Failed to fetch") with plain labels, using `fmt` or a small label map per site | all |

### Phase 2 · Next: a screenshot of any two sites looks like the same product

| # | Task | Repo |
|---|---|---|
| 2.1 | Pull tokens from PL into `predictor-ui/tokens.css`: one neutral dark base, one surface step, one border colour, one accent per sport, 6–8 px radius, a 4/8/12/16/24/32 spacing scale, Barlow Condensed for display and one body font, no glows or glass. | predictor-ui |
| 2.2 | Components: `AppShell` (product name, sport switcher, page tabs), `GameCard`, `ProbabilityBar`, `StatTable`, `StatTile`, `Skeleton`, `EmptyState`, `ErrorState`, `Badge` (at most one per card), `TeamChip` (team colour and abbreviation), and `SportMark` (monochrome SVG per sport, also used as the favicon). | predictor-ui |
| 2.3 | **The `/track-record` contract** (backend; small). Every predictor returns `{sport, model_version, n, accuracy, brier, buckets: [{lo, hi, n, predicted_mean, actual_rate}], updated_at}`, counting only predictions with `predicted_at < start_time` and excluding backfilled rows. PL and NBA map their existing `/hub/track-record`; F1, NFL and CFB map `/track-record`. | all predictors |
| 2.4 | **Per-game URLs** on every site (`/game/:id`, `/race/:season/:round`, `/fixture/:id`), each with its own title. | all frontends |
| 2.5 | Move the sites onto the system in this order: **Sports** (football season is under way, and it's the most broken), **NBA** (before the late-October tip-off), **Hub**, **F1**, **PL** (already closest to the target). Move NBA to Vite 8, Recharts 3 and Tailwind 4 as part of its migration. | Sports, NBA, hub, F1, PL |
| 2.6 | Rebuild the Hub as the product's front page: for each sport, the next game with its pick and the season record from 2.3. The four VPS services share one origin (Phase 3), so this is a static page reading `/api/<sport>/…`. | predictor-hub |
| 2.7 | Retire the NFL and CFB standalone frontends (D3). | NFL, CFB |

### Phase 3 · After: pages load finished and a shared link unfurls as a card

| # | Task | Notes |
|---|---|---|
| 3.1 | A real domain with Caddy automatic HTTPS: `<sport>.domain` for each site and `domain/api/<sport>` for each API | Unblocks the trade hub step-7 base URLs (D1) |
| 3.2 | Pages load already rendered: Caddy serves each `public_snapshot.json` as a static file that the page reads first (no API cold path), with "Updated 12 min ago" from `updated_at`. Keep the GitHub Actions snapshot crons, since they're free and already running. Only move to systemd timers if the snapshots need VPS-local data. | Replaces the PL "Refresh odds" button; remove `/refresh-odds/public` |
| 3.3 | Open Graph share cards per game (a server-rendered PNG with teams, probability and the sport accent) | Depends on 2.4 |
| 3.4 | SSE from F1 `/live/current` for live sessions | F1 only at first |
| 3.5 | `/health` per service drives the Hub's LIVE badges | NFL, CFB and F1 need a `/health` route (PL and NBA already have one) |
| 3.6 | Self-hosted Umami | Decide what to polish next from real usage |

---

## 5. Proposed amendments to the trade hub docs

These belong in `algo-trade-hub-prod`, and the owner should apply them there. Its tracker contract bars implementing agents from editing the spec.

1. **Spec §5 / rollout tracker step 5:** per D1, the VPS stays up for the predictor sites and is no longer retired.
2. **Spec §3.2 and tracker step 7:** replace the Azure predictor URLs with `https://<domain>/api/<sport>`. Add to "before detailing": *this plan's Phase 2 items 2.3 (track-record contract) and 2.4 (per-game URLs) are merged, and Phase 0 item 0.6 (NBA calibration) is resolved*.
3. **Tracker "Parked: remaining frontend cleanup (old roadmap Phase 10)":** the Sports tab and Track Record view import `predictor-ui/tokens.css` and `fmt.ts`, so the trade hub formats probabilities, margins and dates the same way the predictor sites do.

## 6. Not doing

- Team logos for NBA and NFL. Team-colour chips avoid licensing questions. PL keeps its crests.
- Moving the five repos into a monorepo (see D2).
- Porting the War Room to React 19 or Tailwind 4 to share components. Tokens and `fmt` are enough.
- Moving the snapshot crons off GitHub Actions, unless 3.2 needs it.
