# The hub picks page (design)

**Date:** 2026-09-27
**Status:** **not started**, and awaiting Kevin's review of the design. Re-checked
2026-10-04 — still not started, and the check is against merged PRs this time:
the sibling specs on this page that also said "awaiting review" had in fact
shipped, so the claim is traceable to an absence.

- `git grep` on `predictor-hub` `origin/main` finds no picks page, no landing page
  and no card grid; `index.html` has no `picks` id, href or `picks.html`. The only
  "picks" occurrences there are inside the teasers added by predictor-hub #23,
  which are five sport cards on the Home tab — not this page.
- The one merged PR that touches this scope is predictor-hub #23 ("Live teasers on
  the hub, a Home tab, and clickable rows"), which covers the live-picks teaser
  half of roadmap Phase 4 step 13 and no more.
- The landing page is still unpublished: predictor-hub #5, "publish the landing
  page to the VPS on merge to main", is **open**, not merged.

Unlike those two siblings, this one is genuinely a proposal.
**Roadmap:** [../plans/2026-09-25-predictor-frontend-action-plan.md](../plans/2026-09-25-predictor-frontend-action-plan.md). This is Phase 4 step 13 — the "live hub ticker" that plan deferred — plus the comprehensive landing page.
**Mode:** mixed. The card grid is **Operate** (scan and choose a sport). The page as a whole is the product's front door, so it also has to survive being the first thing a visitor and a recruiter ever see.
**Sibling spec:** [2026-09-27-predicted-box-score-and-track-record-design.md](2026-09-27-predicted-box-score-and-track-record-design.md) (Phase 5). Shared: the honesty rules and the tokens. Not shared: this page has no build step, and `predictor-ui` is not consumed as a package — its tokens are hand-inlined and drift-tested.

## Kevin's ask, verbatim

- "can we also add a home page that is a more comprehensive landing page that kind of shows a few predictions from each underneath the cards of each that already exist, like for f1 it should be the top 3, for pl the best edge bet and nfl, cfb and nba show the closest matchup (i.e.) the biggest game or best edge as well?"

## Decisions

| Decision | Choice |
|---|---|
| Page | Extend the existing hub `index.html`. Not a new route. |
| Card content | Strongest pick. Edge is added **only where a real line exists**, and the card says which it is showing. |
| "Closest matchup" | Closest to a coin flip — the smallest gap from 50%. Not the highest total. |
| Placement | The teaser sits **below** the card, as a sibling in the same `<li>`, not inside the `<a>`. |
| Edge availability | Not a blocker. A missing line is a normal state, not an error. |
| Client cache | None. Five same-origin reads behind one proxy is not a load problem. |

## Feasibility, as measured on 2026-09-27

This is the part that decides the design, so it is recorded with the evidence.

| Sport | Source | Teaser data | Gap |
|---|---|---|---|
| F1 | `predictions` in `public_snapshot.json`; live `/races/{season}/{round}/prediction` | `p_win`, `p_podium`, `constructor_id`, `source` | **No driver names in the API.** The site derives a surname from the id; see T4. |
| PL | `fixtures_by_gameweek[n].fixtures` | `predicted_home_win` / `_draw` / `_away_win`, `predicted_scoreline` | Predictions fine. `has_live_odds: false` and `value_bet_flags: []` on every fixture, so **no edge today**. |
| NFL | `weeks[n].games` + `.predictions` | `home_win_prob`, `gameday` | Predictions fine. Only **64 of 272** games carry a `spread_line`, and the current week's `home_cover_prob` / `over_prob` are all `NaN`. |
| CFB | same shape | same | same |
| NBA | `GET /games/week?start=YYYY-MM-DD` | `prediction` (`GameOut.prediction`) | The NBA snapshot's `schedule` block holds **results only — no predictions at all**. The hub must call the live endpoint with a date. |

**Consequence.** "Best edge bet" is not available for PL, NFL or CFB right now. `ODDS_API_KEY` is read from the environment (`NFL_Predictor/src/nfl_predictor/config.py:25`) and there is no `.env` in the repo, only `.env.example`; the 64 games that do carry lines suggest the feed ran at some point and is not running now. So edge is a **progressive enhancement**, never the default. Every card leads with something that always exists.

## What each card shows

Selection rules, exactly. Each is deterministic and testable.

**F1 — top 3.** The next race's predictions sorted by `p_win`, first three. Row: driver name, constructor, win %, podium %. Skip predictions where `source` is `rebuilt` or `backtest`; if the best remaining rows are all rebuilt, say so rather than presenting a post-hoc pick as a pre-race call.

**PL — strongest pick.** From the current gameweek, the fixture maximising `max(predicted_home_win, predicted_draw, predicted_away_win)`. Row: the two teams, the pick in words, its probability, and `predicted_scoreline` labelled "Most likely score" (PL's term, per `PRODUCT.md`). Edge is appended only when `has_live_odds` is true and `value_bet_flags` is non-empty.

**NFL — closest to a coin flip.** From the current week, the game minimising `|home_win_prob − 0.5|`. Row: the two teams, the pick in words, its confidence, kickoff (with zone). Edge appended only when `spread_line` is non-null.

**CFB — identical to NFL**, against the CFB API.

**NBA — closest to a coin flip.** `GET /games/week?start=<today>`, the game minimising `|p_home − 0.5|` over games with a `prediction` and not `completed`. Row: the two teams, the pick, its confidence, tip-off.

Every card's teaser carries the source's `generated_at`, in words ("from the Sep 24 snapshot"). A pick shown without knowing when it was made is precisely the "rebuilt after kickoff" failure the product exists to avoid, and the hub is the one surface where a visitor has no other context to catch it.

### When there is nothing to show

Offseason, pre-season, or an API with no upcoming games is a **normal** state, not an error. The card keeps its link and status badge; the teaser area says which case it is ("No races left this season", "No games this week"). It never shows a spinner that never resolves — the exact P0 the Phase 1 audit found on the sport sites.

## Infrastructure

### T1 — proxy the sport APIs from the hub

`vps-stack/Caddyfile` currently serves the hub as:

```
{$DOMAIN}, www.{$DOMAIN} {
	import common
	root * /srv/hub
	file_server
}
```

No proxy at all, so a static page on the bare domain cannot read the subdomains. Add `handle_path` blocks for all five, using the pattern already proven twice in the same file:

```
	handle_path /pl/*  { reverse_proxy pl:8000 }
	handle_path /f1/*  { reverse_proxy f1:8000 }
	handle_path /nba/* { reverse_proxy nba:8000 }
	handle_path /nfl/* { reverse_proxy nfl:8001 }
	handle_path /cfb/* { reverse_proxy cfb:8003 }
```

Same-origin, so no CORS change on any API. This is a VPS change and needs a deploy; it is the only piece that cannot be finished from a laptop.

### T2 — sanitise `NaN` out of the snapshots

The NFL and F1 snapshot JSON contains bare `NaN` tokens. `JSONResponse.render` in the installed starlette 1.7.0 passes `allow_nan=False`, so a response containing one raises `ValueError` and becomes an HTTP 500 — it is not a body the browser can fail to parse, it is a dead endpoint. The sport sites dodge this today only because they happen to request weeks whose rows are clean; the hub fans out across everything and would hit it.

Fix at the source, in each snapshot builder: non-finite floats become `null`. Not at the edge, and not by catching it in the page — a snapshot containing `NaN` is invalid JSON and invalid on disk regardless of who reads it.

## Markup

The teaser is a **sibling** of the card, inside the same `<li>`:

```html
<li class="slot" data-sport="nfl">
  <a class="sport pr-notch" data-sport="nfl" href="…">…unchanged…</a>
  <div class="teaser" data-teaser="nfl" aria-busy="true">…</div>
</li>
```

Kevin said "underneath the cards", and this is also the only valid option: a teaser with its own links cannot live inside the existing `<a>`, and nesting interactive content in an anchor is invalid HTML. As a sibling, each teaser row can be its own link to that specific game, and the card keeps its own link to the sport.

Consequences for `tests/hub.test.mjs`, all of them intended:

- the card regex (`<a class="sport pr-notch" data-sport="(\w+)"`) still matches, in the same order — cards are untouched;
- the `.status` list assertion still sees exactly five spans in the same words. **The teaser must not introduce another `.status` span**, or the test needs a deliberate update;
- the token-parity test still holds. Any new token goes into `packages/predictor-ui/src/tokens.css` first, because the test fails on drift in both directions.

New tests: one per sport asserting the selection rule picks the right rows from a fixture payload (the coin-flip rule and the strongest-pick rule are both easy to get subtly wrong), one asserting a failed fetch leaves the card intact and the teaser honest, and one asserting `NaN` never reaches a rendered number.

## Failure and honesty policy

- **Cards render first, teasers hydrate after.** The grid is static HTML and is never gated on a fetch. If every API is down, the page is still a working index of five sites — which is what it is today.
- **One sport failing never affects another.** Each teaser fetches independently; a rejected promise writes into that one slot.
- **A missing line is not an error.** It is simply not shown. The card never implies an edge it did not compute.
- **A missing driver name is never shown as a raw id.** The F1 teaser title-cases `driver_id` exactly as the F1 site does, so the hub and the site never disagree. `"russell"` is not a thing a visitor should read.
- **No pick is presented without its timing.** `generated_at` and, for F1, `source`, are part of every teaser.

## Tasks

| # | Where | Work |
|---|---|---|
| T1 | `vps-stack/Caddyfile` | Five `handle_path` proxy blocks. Needs a VPS deploy to verify. |
| T2 | `NFL_Predictor`, `F1_Predictor` snapshot builders | Non-finite floats → `null`. Test that a snapshot round-trips through `json.dumps(allow_nan=False)`. |
| T3 | `predictor-hub/index.html` | The teasers, the inline fetch and render, the five states (loading / content / empty / error / edge), the freshness line. |
| T4 | `F1_Predictor` | **Optional.** Add a real `driver_name` to `DriverPrediction` and the snapshot's prediction rows, so the hub and the F1 site can both show "George Russell" instead of a surname. Not a blocker: the F1 site derives the surname itself (`F1_drop/frontend/src/lib/teamColors.ts:46` title-cases `driver_id`, turning `"russell"` into `"Russell"`), so the hub can do the same with no backend change and match the site exactly. T4 upgrades both surfaces; skipping it costs nothing but a first name. |
| T5 | `predictor-hub/tests/hub.test.mjs` | Per-sport selection-rule tests, failure isolation, no-`NaN`, and the `.status` assertion. |

T1, T2 and T4 are independent and can run in parallel. T3 needs T1 to verify and T2/T4 to be worth building.

## Out of scope

- **Wiring the odds feed.** Edge appears where a line already exists. Turning on `ODDS_API_KEY` across the sports is its own piece of work with its own key and its own failure modes, and this design does not wait on it.
- Any profit, ROI or "beats the bookies" claim. `PRODUCT.md` forbids it.
- Deep per-game pages on the hub. A teaser row links to the sport site, not to a hub-rendered game detail.
- A client-side cache, and a build step for the hub. The page stays hand-written HTML with inlined tokens, because that is what the drift test is built around.
