# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Confirmed by Kevin (2026-09-25), in priority order:

1. **Fans checking picks.** Sports fans, mostly on their phones, just before a game or race. Their job is to find out who the model likes, how sure it is, and whether it has been right, in a few seconds.
2. **Bettors comparing the model with the odds.** People who put the model's probability next to bookmaker prices. They care about value, calibration, and whether the model beats the market.
3. **Portfolio / showcase.** Recruiters, peers and employers judging Kevin's modelling and engineering. Method transparency and a credible record matter more to them than flair.
4. **Kevin himself.** The sites are also his own working tool for checking model output.

## Product Purpose

Predictor publishes model picks for five sports:
- Premier League;
- Formula 1;
- NFL;
- college football (CFB);
- NBA.

Each pick shows its confidence, its reasoning and a public record of how often the model has been right. Success means a visitor gets the pick and a reason to trust it within seconds, on any sport, and the record holds up to scrutiny.

## Positioning

- **An honest track record.** The headline is the pre-kickoff record: every counted pick is locked in before kickoff and scored in public, and picks rebuilt after kickoff never count toward it. They are still counted and shown separately — a second figure over every resolved pick, and a per-pick list with hits and misses in the same table — because a hit rate is only meaningful if the pick existed before the result, and hiding the rest would lose sight of the picks that have already passed.
- **It shows its reasoning.** The model explains why it likes a side (drivers, form, head-to-head, ratings), not just the number.
- **Five sports in one place.** One maker and one way of reading a pick across all five sports. Each sport keeps its **full functionality**: a Games view and a Data Hub (teams, players, standings or rankings, track record, model details). The family shares a product frame; the sites are not collapsed into a single summary page.

## Operating Context

- The five sites plus a Hub run on one VPS, each on its own subdomain. They're currently `*.40-160-91-131.sslip.io`, and a real domain is planned.
- Data is precomputed: scheduled GitHub Actions jobs rebuild each site's `data/public_snapshot.json`, and the APIs serve from it in public mode.
- Picks are read on match days, often on a phone, and are sometimes shared into group chats.
- A separate, private trade hub (`algo-trade-hub-prod`) reads the predictors' APIs to find Kalshi edges. It is **not** part of the public product.

## Capabilities and Constraints

- **The sites:**

  | Site | Repo | Content |
  |---|---|---|
  | PL | `PL_Predictor` | Fixtures, scorelines, player picks, FPL, value bets |
  | F1 | `F1_Predictor` | Race, qualifying and sprint predictions, championship, live sessions |
  | NBA | `NBA_Predictor` | Games, props, standings, calibration |
  | NFL + CFB | `Sports_Predictor` (frontend) with the `NFL_Predictor` and `CFB_Predictor` APIs | Games, props, standings, power rankings, track record |
  | Hub | `predictor-hub` | Links to the sport sites |

- **Every sport keeps its Games and Data Hub.** New shared components must not remove sport-specific depth.
- **Stack:** existing React + Vite + Tailwind apps. PL, F1 and Sports run React 19, Tailwind 4 and Vite 8; NBA runs Vite 6. The Hub is static HTML.
- **Terminology:**
  - "Pick" is the model's single call.
  - "Rebuilt after kickoff" replaces "backfilled" and "reconstructed".
  - "Most likely score" is PL's scoreline.
  - "Toss-up" is used when the models disagree or the margin is under half a point.
- **Free for now.** No login and no paywall today. Monetisation is an **open decision**, so don't design it out, and don't promise "free forever".
- **Name:** **Predictor** is the product wordmark. Each site is "<Sport> Predictor" under it.
- **Open decisions:**
  - a real domain;
  - whether bettor-facing odds and value comparisons appear on every sport;
  - team logos (PL crests only today; the other sports use team-colour chips to avoid licensing questions).

## Brand Commitments

- The name "Predictor".
- The honesty rule above: rebuilt picks never count toward the headline. They are counted and shown separately, and every resolved pick is listed.
- Plain-language copy. No developer terms on public pages.

## Evidence on Hand

- Each site's live track record, from its `/track-record` or `/hub/track-record` endpoint. On 2026-09-25 every settled PL pick was rebuilt after kickoff, so PL has no pre-kickoff record yet.
- F1 Track Record: winners called per race.
- NBA calibration buckets.
- Design critique baseline: `.impeccable/critique/2026-09-25T07-27-01Z__index-html.md` (18/40).
  **Stale, and 18/40 is no longer a fair number for the product.** That critique predates the
  Phase 2 family redesign. Re-measured 2026-09-27: the hub now scores clean on every heuristic
  that critique covers — no sub-12px text, no contrast failures, no small tap targets, no
  horizontal scroll at 1440 or 390, no raw developer values, links on the live VPS hosts. The
  file is kept as the historical record and is not rewritten. The findings that are still real
  are in Task 24 of the phase-4 ledger, and they are on `Sports_Predictor` (the NFL/CFB site),
  not the hub — including the one P0, an error-less permanent "Loading…" on a failed fetch.
- **Absent, and must not be fabricated:** user counts, testimonials, press, betting profit or ROI claims, "beats the bookies" claims.

## Product Principles

1. **Pick first.** Every game surface answers "who, how sure, has it been right" before anything else.
2. **Never overclaim.** Only pre-kickoff picks count. Uncertainty is shown, not hidden ("Toss-up", "No pick yet").
3. **Show the why.** Every pick links to its reasoning and to the model's record.
4. **One product, full depth.** A shared frame and shared components, with each sport's full Games and Data Hub intact.
5. **Works on a phone at kickoff.** Fast, readable, one-handed.

## Accessibility & Inclusion

Target WCAG 2.2 AA:
- 4.5:1 text contrast;
- visible keyboard focus;
- no meaning carried by colour alone (probability bars and verdicts carry text labels);
- status changes announced.
