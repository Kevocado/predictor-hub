# Phase 3 + 4: Data Hub parity and the AI match explainer (design)

**Date:** 2026-09-25
**Status:** sections 1–2 approved by Kevin in conversation. Sections 3–4 were written to finish the handoff and have not been reviewed yet; the implementer confirms them with Kevin before building UI.
**Roadmap:** [../plans/2026-09-25-predictor-frontend-action-plan.md](../plans/2026-09-25-predictor-frontend-action-plan.md). This replaces the old Phase 4 ("live Hub ticker"). The ticker can come later and reuse the explainer's facts endpoints.

## Kevin's asks, verbatim

- "for the data hub make sure the player and team data is to the level of pl_predictor"
- "integrate it into the sports predictor page first using the free open router keys we have to [make] the predictions more intuitive when a specific one is selected … something that interprets the model's results in the best way"
- "make sure this is happening for PL and NBA as well as the american football ones and i now have 1000 requests per day"
- "include f1 but make its analysis specific to the context of the race, like if george russell qualified first and the model predicts him winning it can explain that since the f1 stuff already explains why each pick was chosen"

## Decisions

| Decision | Choice |
|---|---|
| Generation | Pre-generate for upcoming games, plus on-demand on first open. Cached. Daily cap. |
| Budget | 1,000 OpenRouter requests a day on one key. Cap of 900, leaving 100 spare. |
| Content | Why the model leans that way · model vs the market · key players to watch · how much to trust it · market-specific |
| Research | Our own data, plus free news headlines (ESPN public news endpoints) |
| Data Hub depth (NFL, CFB) | Advanced: EPA per play, success rate, usage shares, position leaderboards |
| Sports | Explainer: PL, F1, NFL, CFB, NBA. Data Hub parity: NFL and CFB. NBA's gaps are listed, not built. |
| Architecture | One shared explainer service. Each sport API gains one `/facts` endpoint. |

## Sub-project A: Data Hub parity (Phase 3)

PL's hub is the bar. It has:
- per-team efficiency (xG, shots), form trend, streak and recent matches;
- per-player season stats, ratings and sortable leaderboards.

### NFL (`Kevocado/NFL_Predictor`)

**Team stats:** `data/team_efficiency.py` builds these from nflverse play-by-play (`nfl_data_py.import_pbp_data([season])`, cached per season as parquet like the other loaders). Per team:
- **Offence:** EPA per play, success rate (plays with EPA > 0), yards per play, pass rate.
- **Defence:** EPA per play allowed, success rate allowed.
- **Scoring:** points per game for and against, turnover margin.
- **Form:** last 5 results, streak (`W3`), form trend (net points of the last 3 games vs the season average: up if more than 3 better, down if more than 3 worse, else steady; "new" under 3 games), and recent games (date, opponent, home/away, score, result).

**Player stats:** `data/player_season.py` builds season stats from the weekly player data the site already loads (`import_weekly_data`):
- **Volume:** games, passing / rushing / receiving yards and TDs, interceptions, targets, receptions, carries.
- **Usage:** target share, air-yards share (weekly columns, averaged).
- **Efficiency:** EPA (`passing_epa`, `rushing_epa`, `receiving_epa`) and fantasy points PPR.
- **Leaderboards:** top 10 per position for QB, RB, WR and TE by EPA, plus total yards.

**Endpoints:** `GET /hub/teams?season=` and `GET /hub/players?season=`. Both are included in the public snapshot as `hub_teams` and `hub_players`, and in public mode are served from the snapshot.

### CFB (`Kevocado/CFB_Predictor`)

**Team stats:** one CFBD call per season: `cfbd.StatsApi.get_advanced_season_stats(year=season, exclude_garbage_time=True)`. It provides offence/defence PPA (EPA), success rate, explosiveness and rushing/passing splits.
- The call is cached per season on disk and refreshed at most once a day (this respects the 1,000 calls a month quota).
- Form, streak and recent games come from the games data the site already has.

**Player stats:** from the weekly player stats the site already has, the same shape as NFL minus EPA (CFBD player PPA is a separate call: `get_player_season_ppa`, one call a season, cached; include it).

**Endpoints and snapshot:** the same endpoints and snapshot keys as NFL.

### Sports site (`Kevocado/Sports_Predictor`)

- **Data Hub sub-tabs:** Teams, Players, Standings, Track record. "Player Hub" and "Team Hub" become Players and Teams.
- **Teams page:** a sortable `StatTable` with Team, Record, Off EPA/play, Def EPA/play, Success rate, Points for/against per game, Turnover margin, Form (strip), and trend arrow with words.
- **Team detail:** expanding a team row shows its stat chips and recent games, as PL's TeamHub does.
- **Players page:**
  - a position filter (All, QB, RB, WR, TE);
  - search;
  - a sortable table (Player, Team, Pos, Games, the position's key yards and TDs, EPA, Target share or Carries);
  - leaderboards above the table (top 5 by EPA per position);
  - this week's prop projections kept as a column: "Projected this week".
- **Numbers:** EPA is shown to 2 decimals, signed with a true minus. Shares are shown as whole %.
- **Missing values:** a dash, never 0.

### NBA (not built here; gaps noted)

NBA already has team net rating, pace, PPG and streak, and player per-game stats with rating and live form. Missing compared with PL:
- the form trend arrow;
- recent games in team detail;
- position leaderboards;
- sortable columns with tooltips.

These go on the Phase 3 follow-up list.

## Sub-project B: the AI match explainer (Phase 4)

### Section 1: architecture (approved)

```
Browser (any sport site)
   │  GET /api/explain/{sport}/{id}          (same-origin; each site's Caddy/FastAPI proxies to the service)
   ▼
Explainer service  predictor-hub/services/explainer   (FastAPI container on the VPS)
   ├─ 1. Facts bundle   ← GET {SPORT_API}/facts/{id}      (new read-only endpoint in each sport API)
   ├─ 2. Headlines      ← ESPN public news per team (free, keyless)
   ├─ 3. Cache          SQLite, key = sport + id + sha256(facts + headlines + PROMPT_VERSION + model)
   ├─ 4. OpenRouter     key and model from env; ledger caps requests per UTC day
   └─ 5. Fallback       deterministic template from the same facts
Scheduler in the same service: every 3 h, pre-generate for events in the next 72 h
```

- **IDs:**
  - PL, NFL, CFB and NBA use the game or event id.
  - F1 uses `{season}-{round}-{session}`, where the session is `race`, `qualifying` or `sprint`.
- **Upcoming events:** each sport API also exposes `GET /facts/upcoming?hours=72`, which returns the ids to pre-generate.
- **Environment:**
  - `OPENROUTER_API_KEY`;
  - `EXPLAINER_MODEL` (default `deepseek/deepseek-chat-v3-0324:free`);
  - `EXPLAINER_FALLBACK_MODEL` (default `meta-llama/llama-3.3-70b-instruct:free`);
  - `EXPLAINER_DAILY_CAP` (default 900);
  - `SPORT_API_{PL,F1,NFL,CFB,NBA}` (base URLs);
  - `EXPLAINER_DB` (SQLite path).
- **Key safety:** the key lives only in the service. It never reaches a browser or a GitHub secret.

### The facts bundle (the contract)

Every sport returns this shape:

```json
{
  "sport": "nfl",
  "id": "2026_05_KC_BAL",
  "title": "Chiefs at Ravens",
  "starts_at": "2026-10-05T00:20:00Z",
  "status": "upcoming | live | final",
  "pick_timing": "pre_kickoff | rebuilt | none",
  "pick": {"label": "BAL", "prob": 0.62},
  "markets": [
    {"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}, "line": {"BAL": -150}, "implied": {"BAL": 0.58}},
    {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5", "model_cover_prob": 0.56},
    {"market": "total", "model_total": 47.8, "line": 45.5, "model_over_prob": 0.61}
  ],
  "drivers": [{"name": "Rating gap", "value": "+2.1 pts", "direction": "BAL"}],
  "context": {"weather": "72°F, 8 mph wind", "rest": "Rest 6 v 7 days", "injuries": ["KC WR out"]},
  "players": [{"name": "Lamar Jackson", "team": "BAL", "projection": "248 pass yds, 52 rush yds"}],
  "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66},
  "result": {"score": "BAL 27–20", "pick_won": true}
}
```

- **Field rules:**
  - Each sport fills only what it has. `markets` uses sport-specific market names:
    - PL: `result` (home/draw/away), `handicap`, `total_goals`, `btts`;
    - NBA: `moneyline`, `spread`, `total`;
    - F1: `win`, `podium`, `points`, `dnf`.
  - `result` appears only for finals.
- **Honesty:** `pick_timing` comes from each site's existing honesty flags (`rebuilt` / `backfilled` / the F1 `source`). A rebuilt pick is labelled `rebuilt` and its `result.pick_won` is omitted.
- **F1 bundle:**
  - `title` is "Italian Grand Prix · Race";
  - `drivers` lists the top 8 by headline chance, each with grid, win, podium, points and DNF, plus up to 5 contributors from the existing `/explain` output (strength and DNF) for the top 3 and for the biggest mover (the largest gap between grid position and predicted rank);
  - `context` has circuit, weather, whether it's a sprint weekend, and the tier.

### Section 2: prompt, guardrails and output (approved)

**System prompt rules** (one shared frame, plus a per-sport vocabulary block):
1. Use only the numbers and facts in `FACTS` and the dated headlines in `NEWS`. Never invent injuries, odds, results or quotes.
2. No betting advice: no "lock", "bet", "value play" or "hammer". Disagreement with the market is information ("the model rates BAL 4 points better than the line does").
3. If `pick_timing` is `rebuilt`, say the pick was built after the game or session started and isn't counted. Never call it a prediction.
4. Explain uncertainty in plain terms ("62% still loses about 4 times in 10").
5. PL uses UK English; NFL, CFB and NBA use US English; F1 uses UK English.
6. F1 only: tell the race story. Tie the grid to the headline chance ("starts from pole, and grid is the model's strongest signal"), name who can move up and why, and cite the contributors given.

**Output** is JSON only, validated:

```json
{"headline": "≤ 18 words",
 "sections": [{"market": "result|spread|total|players|trust|race|…", "title": "≤ 6 words", "text": "≤ 60 words", "numbers_used": ["62%", "-2.5"]}]}
```

- **Validation (the main anti-hallucination guard):**
  - Every numeric token in `headline` and `text` must appear in the rendered facts (numbers normalised: `62%` ↔ `0.62`, true minus ↔ hyphen, ±0.05 rounding tolerance).
  - Total length is 120–220 words.
  - There are 3–6 sections.
  - No banned words.
- **Retries and fallback:** a failed validation retries once with the fallback model, then uses the template.
- **Settings:** temperature 0.3, max_tokens 700, timeout 25 s. Requests carry the `HTTP-Referer` and `X-Title: Predictor` headers, as OpenRouter asks.
- **Cache:** the result is stored with `model`, `prompt_version`, `generated_at` and `source` (`llm` or `template`).

### Section 3: UI (not yet reviewed by Kevin)

- **Placement:** an "In plain English" panel sits at the top of each site's detail view:
  - Sports: `GameDetailModal`;
  - PL: `FixtureModal`;
  - NBA: `GameDetailModal`;
  - F1: the session panel, above the timing tower, collapsed to the headline with "Read the race story".
- **Content:** the headline, then the sections as short labelled paragraphs.
- **Footer:** "AI summary of the model's numbers · {model} · {time ago}". When `source=template` it reads "Summary written from the model's numbers" (no AI label).
- **Rebuilt picks:** the panel repeats the "Rebuilt after kickoff" status and wording.
- **States:**
  - Loading: `Skeleton` "Writing the summary…".
  - Error: `ErrorState` with Try again.
  - The panel never blocks the rest of the modal.
- **Components:** a shared component in `predictor-ui`, `ExplainerPanel({ data, loading, error, onRetry })`, synced to every site. Each site fetches `/api/explain/{sport}/{id}` with the family 15 s timeout.

### Section 4: testing and rollout (not yet reviewed by Kevin)

- **Service tests (pytest):**
  - cache hit and miss;
  - the ledger stops at the cap and rolls over at UTC midnight;
  - the number validator (accepts, rejects, normalises);
  - banned words;
  - retry then template;
  - the rebuilt wording;
  - a headline fetch failure still explains;
  - the scheduler picks upcoming ids.
  
  OpenRouter and ESPN are always mocked (`respx` or `httpx.MockTransport`); tests never call the network.
- **Facts endpoint tests (pytest), in each sport repo:**
  - the schema keys;
  - `pick_timing` for pre-kickoff, rebuilt and none;
  - public mode reads the snapshot and triggers no live model work;
  - `result` only for finals.
- **UI tests (vitest):**
  - `ExplainerPanel` states and the AI label;
  - the rebuilt copy;
  - each site's modal fetches and renders it.
- **Rollout:**
  1. Service and NFL facts, behind `EXPLAINER_ENABLED`.
  2. CFB, PL and NBA facts.
  3. F1 facts and the race story.
  4. Turn on pre-generation.

  Watch the ledger for a week.
- **VPS:** one container, `predictor-explainer`, on port 8090. Each site's reverse proxy adds `/api/explain/* → predictor-explainer:8090`. Docs sit in `services/explainer/README.md`.

## Out of scope

- Paid web search (`:online`).
- Chat or follow-up questions.
- Explaining the Data Hub or the track record.
- NBA Data Hub parity (listed above).
- The Hub "this weekend" ticker (a later phase that can reuse `/facts/upcoming`).
