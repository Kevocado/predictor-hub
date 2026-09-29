# Live Odds on the VPS: Design

**Status:** approved in brainstorming on 2026-09-25, ready for an implementation plan.
**Repos touched:** `PL_Predictor`, `NFL_Predictor`, `CFB_Predictor`, `F1_Predictor`, `vps-stack` (this repo, where the specs for cross-repo work live).
**Owner:** Kevin (github.com/Kevocado).

## 1. Problem

All predictor sites now run on one OVHcloud VPS (`40.160.91.131`, 2 vCore / 4 GB / Ubuntu 26.04), served by `vps-stack` (Caddy + Docker Compose). Their *predictions* are still built elsewhere: each repo's `refresh-public-snapshot.yml` GitHub Action rebuilds `data/public_snapshot.json`, commits it, and the container polls it from raw.githubusercontent.com every 5 minutes (`PUBLIC_MODE=true`).

For PL this causes two problems:

1. **The "Refresh odds" button doesn't actually refresh anything.** In public mode `POST /api/refresh-odds/public` only dispatches the GitHub workflow (3–9 min), which commits, and the site picks it up on the next 5-minute poll. The user sees nothing change for 5–15 minutes.
2. **The odds aren't live.** They're only as fresh as the last snapshot run.

Public mode exists because PL's live pipeline OOM-crashed the old free-tier hosts. The VPS has enough memory for it (the whole stack uses ~1.8 GB of 3.7 GB, measured 2026-09-25), so the original reason mostly doesn't apply any more.

Meanwhile NFL and CFB spend paid odds quota on lines ESPN publishes for free, and NFL's The Odds API credits are exhausted, so NFL mostly has no odds at all.

## 2. Goals and non-goals

**Goals**
- PL runs its live pipeline on the VPS. The public site serves live odds, and "Refresh odds" really refreshes within seconds.
- The owner can reach PL's admin features (retrain, backtest, admin odds refresh) at a password-protected address.
- Paid odds quota goes to PL first. NFL/CFB take their lines from ESPN (free) and use paid sources only for the specific games ESPN lacks.
- No site gets slower or less reliable than it is now.

**Non-goals**
- Live in-race F1 updates. The owner doesn't use them; the poller is switched off on the VPS.
- Live compute for F1, NFL or CFB. They stay snapshot-based, built in GitHub Actions.
- Admin addresses for F1, NFL or CFB. Their admin work stays local.
- In-play (during-match) odds, or paid odds tiers.
- Auto-retraining on the VPS. Models keep shipping inside the image.
- NBA changes. NBA shares the Sportsbook key, but its code is untouched; the key-wide safety floor (§4.2) protects its share.

## 3. Constraints (verified 2026-09-25)

| Fact | Source |
|---|---|
| Sportsbook API (RapidAPI `sportsbook-api2`) is capped at **150 requests/day**, and **one request per event**: there's no bulk odds endpoint. | `PL_Predictor/src/pl_predictor/data/sportsbook_api.py` module docstring |
| **PL, CFB and NBA share one Sportsbook key** (identical SHA-256 prefix `2ba5acc8` in all three Azure apps). | `az containerapp secret list`, hashed comparison |
| The Odds API key (NFL, CFB, NBA) is on the free 500 credits/month plan, already used up this month; one call returns every game for a sport (≈ markets × regions credits). | `CFB_Predictor/src/cfb_predictor/config.py` comments |
| ESPN's unofficial scoreboard (`site.api.espn.com/apis/site/v2/sports/football/{nfl,college-football}/scoreboard`) had odds for 15/16 NFL and 70/71 FBS games this week. It has a single provider (DraftKings): `moneyline.{home,away}.{open,close}.odds` (American), `pointSpread`, `total`, `overUnder`, `details`. No player props. | live request, 2026-09-25 |
| PL's cold cache build takes 50–65 s, and the value-bet table about 11 s. The private-mode loop rebuilds the 5-min-TTL caches every 240 s. | `PL_Predictor/src/pl_predictor/api/main.py`, `routes.py` comments |
| PL's frontend times out requests after 20 s and has **no test runner**. | `frontend/src/api/client.ts`, `frontend/package.json` |
| GitHub Actions runners start with an empty disk each run, so nothing persists between snapshot runs. | platform |

## 4. Design

### 4.1 PL "live public" mode

Two settings replace today's single switch. `PUBLIC_MODE` keeps its meaning; `ADMIN_ENABLED` is new:

| Deployment | `PUBLIC_MODE` | `ADMIN_ENABLED` | Behavior |
|---|---|---|---|
| Local dev | unset | unset (defaults to `not PUBLIC_MODE`, so true) | full private app, **unchanged** |
| Snapshot site (rollback) | `true` | unset (so false) | snapshot only, **unchanged** |
| **VPS** | `false` | `false` | live pipeline, admin routes 404 unless they come through the admin proxy (§4.3) |

- `config.py`: add `ADMIN_ENABLED = os.getenv("ADMIN_ENABLED", str(not PUBLIC_MODE)).lower() == "true"` (the same idiom `PUBLIC_MODE` uses) and `ADMIN_PROXY_SECRET = os.getenv("ADMIN_PROXY_SECRET")`.
- `routes.py::_admin_only` takes the `Request` and returns normally when `ADMIN_ENABLED`, **or** when `ADMIN_PROXY_SECRET` is set and `hmac.compare_digest(request.headers.get("X-Admin-Proxy", ""), ADMIN_PROXY_SECRET)`. Otherwise it raises 404, as today.
- Background loops in `main.py` when `PUBLIC_MODE` is false: keep `_initial_sync` (warm-up), `_tracking_loop`, `_lineup_refresh_loop` and `_live_cache_refresh_loop`. **Skip `_auto_retrain_loop`** when `AUTO_RETRAIN_ENABLED` (new, `os.getenv("AUTO_RETRAIN_ENABLED", "true").lower() == "true"`) is false; the VPS sets it false. **Replace `_odds_refresh_loop`** with the scheduler (§4.2).
- `config.py`: `TRACKING_DB_PATH` honors an env override, the same way NBA's does, so the tracking DB can live on a volume.

### 4.2 Odds budget, scheduler, Refresh button (PL)

**Budget counter: `pl_predictor/odds/quota.py`** (new)
- A JSON file `CACHE_DIR/sportsbook_quota.json` holds `{"day": "YYYY-MM-DD" (UTC), "scheduler": int, "button": int, "key_remaining": int|null}`. It resets at 00:00 UTC, and writes go through a lock and an atomic file replace.
- `QuotaLedger.try_spend(pool: Literal["scheduler","button"], n=1) -> bool` checks all of:
  - the scheduler pool's cap: `SPORTSBOOK_DAILY_CAP - SPORTSBOOK_BUTTON_RESERVE` (defaults 120 and 20);
  - the button pool's cap: `SPORTSBOOK_BUTTON_RESERVE`;
  - the key-wide floor: never spend if the last seen `key_remaining < SPORTSBOOK_KEY_FLOOR` (default 15).
- `QuotaLedger.record_response(headers)` stores `x-ratelimit-requests-remaining` after every request.
- `fetch_event_odds_raw` (in `data/sportsbook_api.py`) calls `try_spend` before each network request (a cache hit spends nothing) and `record_response` after. When the spend is refused it serves the cached copy, or `None`, and logs why.

**Scheduler: `pl_predictor/odds/scheduler.py`** (new)
- The pure function `desired_max_age(kickoff: datetime, now: datetime, lineups_confirmed_at: datetime|None) -> timedelta|None` picks the tier (`None` means don't fetch):

| Time to kickoff | Max odds age |
|---|---|
| > 7 days | None |
| 24 h – 7 days | 24 h |
| 90 min – 24 h | 6 h |
| 0 – 90 min | 30 min; plus one forced refresh once lineups are confirmed, if the last fetch was before that |
| kicked off | None |

- `plan_refresh(fixtures, odds_fetched_at: dict[event_id, datetime], now) -> list[event_id]` returns the stale fixtures, **soonest kickoff first**.
- The `main.py` loop runs every 5 minutes: `plan_refresh`, then fetch each event from the `"scheduler"` pool until one is refused, then clear the `fixtures_df` and `value_bet_table` caches if anything changed.
- The event list (`fetch_epl_events_raw`) is cached for 12 h and spends from the scheduler pool.
- Expected spend is about 7 requests per fixture, announcement to kickoff, so about 70 per 10-match gameweek spread over several days.

**Refresh button**
- `POST /api/refresh-odds/public`, when not in public mode:
  - takes the existing global lock and 5-minute cooldown (`PUBLIC_REFRESH_COOLDOWN_SECONDS`);
  - selects current-gameweek fixtures with odds older than 10 minutes, soonest first, at most 10;
  - starts the refresh in a background thread using the `"button"` pool;
  - returns **202** `{"status": "started", "started_at": iso}`.
  - Refusals: **429** during the cooldown (`detail` says how long to wait) and **429** when the button pool or key floor is exhausted (`detail`: "Today's odds budget is used up; refreshes resume at 00:00 UTC").
  - The admin path (via the proxy) skips the cooldown but not the pools.
- `GET /api/odds/status` (new) returns `{"last_refresh_at": iso|null, "refreshing": bool, "per_fixture": {event_id: fetched_at}, "budget": {"scheduler_left": int, "button_left": int, "key_remaining": int|null, "resets_at": iso}}`.
- The fixtures payload gains `odds_updated_at` per fixture.

**Frontend (PL)**
- `api/client.ts::refreshOddsPublic` handles 202: it polls `GET /odds/status` every 3 s for up to 60 s until `refreshing` is false and `last_refresh_at` ≥ `started_at`, then calls `clearReadCache()` and reloads fixtures and value bets.
- A 429 shows its `detail` text on the button.
- Fixture cards show "odds updated HH:MM" from `odds_updated_at`.

### 4.3 Admin address (PL only)

- **Backend:** `GET /api/session` returns `{"admin": bool}`, using the same check as `_admin_only`.
- **Frontend:** `lib/publicMode.ts` keeps the build-time `PUBLIC_MODE` constant, but admin-control visibility comes from a `useSession()` hook that reads `/api/session` once per page load. Admin controls show when `!PUBLIC_MODE || session.admin`. One image serves both addresses.
- **Caddy** (`vps-stack/Caddyfile`):

```caddyfile
pl.{$DOMAIN} {
	import common
	reverse_proxy pl:8000 {
		header_up -X-Admin-Proxy
	}
}

admin.pl.{$DOMAIN} {
	import common
	basic_auth {
		{$PL_ADMIN_USER} {$PL_ADMIN_PASSWORD_HASH}
	}
	reverse_proxy pl:8000 {
		header_up X-Admin-Proxy {$PL_ADMIN_PROXY_SECRET}
	}
}
```

- **`.env` additions:**
  - `PL_ADMIN_USER`;
  - `PL_ADMIN_PASSWORD_HASH` (made with `docker compose exec caddy caddy hash-password`);
  - `PL_ADMIN_PROXY_SECRET` (`openssl rand -hex 32`).

  The compose `pl` service gets `ADMIN_PROXY_SECRET: ${PL_ADMIN_PROXY_SECRET}`.
- Direct access to `pl:8000` isn't possible from outside: only Caddy publishes ports.
- `admin.pl.40-160-91-131.sslip.io` resolves via sslip.io's wildcard, so this works before a domain is bought.

### 4.4 ESPN-first odds (NFL and CFB)

**New module `data/espn_odds.py`** in each repo:
- `fetch_espn_odds(season: int, week: int) -> pd.DataFrame` reads the scoreboard and returns the repo's existing long odds format. For NFL that's the `data/odds_api.py::fetch_game_odds` columns: `event_id, commence_time, home_team, away_team, bookmaker, market, outcome_name, price` plus `point` where the market has one.
- The new column `source` is `"espn"` and `bookmaker` is `"draftkings"`.
- Markets: `h2h` from `moneyline.{home,away}.close.odds`, and `spreads` and `totals` from `pointSpread` / `total` (close line and price). American odds convert to decimal.
- ESPN team names are normalized with the repo's existing name matching (CFB: `data/sportsbook_api.py::_team_name_matches`; NFL: team abbreviations via `data/teams.py`).
- Parse failures return an empty frame and log a warning; they never raise.

**New `fetch_game_odds(...)`**
- NFL: `odds/combined.py`; CFB: the same path. It replaces the direct source calls in `api/routes.py` and `public_snapshot.py`:
  1. `espn = fetch_espn_odds(...)`.
  2. `missing` = games in the week's schedule with no ESPN row, or missing any of `h2h`, `spreads`, `totals`.
  3. Fill the gaps:
     - **CFB:** `sportsbook_api.fetch_event_odds_raw` for each missing game, at most `SPORTSBOOK_MAX_PER_RUN` (default 5), stopping below `SPORTSBOOK_KEY_FLOOR` (default 15) from the response header. These rows get `source="sportsbook"`.
     - **NFL:** one `odds_api.fetch_game_odds()` call **only if `missing` is non-empty**, filtered to the missing games. These rows get `source="odds_api"`.
  4. Return `concat(espn, fills)`. Games that are still missing simply have no odds, as today.
- The snapshot records `odds_sources: {"espn": n, "sportsbook": n, "odds_api": n, "missing": n}` for visibility.
- The CFB per-run cap replaces a daily counter because GitHub Actions has no disk that survives between runs.

### 4.5 F1

- `config.py`: `LIVE_POLLER_ENABLED = os.getenv("LIVE_POLLER_ENABLED", "true").lower() == "true"`.
- `api/main.py` starts `live_poller.run_poller()` only when it's enabled.
- The VPS sets it `false`. Nothing else changes.

### 4.6 VPS (`vps-stack`)

- **`compose.yml`, service `pl`:** add these environment variables:
  - `PUBLIC_MODE: "false"`, `ADMIN_ENABLED: "false"`, `AUTO_RETRAIN_ENABLED: "false"`;
  - `ODDS_API_KEY`, `SPORTSBOOK_API_KEY`, `FOOTBALL_DATA_KEY`;
  - `SPORTSBOOK_DAILY_CAP`, `SPORTSBOOK_BUTTON_RESERVE`, `SPORTSBOOK_KEY_FLOOR`;
  - `ADMIN_PROXY_SECRET`;
  - `TRACKING_DB_PATH: /app/data/state/tracking.db`.

  And these volumes: `./volumes/pl-cache:/app/data/cache` and `./volumes/pl-state:/app/data/state`. Set `mem_limit` to 1.5 × the peak measured in rollout step 1, keeping the stack total under about 3.2 GB.
- **Seed `volumes/pl-state/tracking.db`** from the image's `/app/data/tracking.db` on first switch (`docker compose cp`), so the track record carries over.
- **Service `f1`:** `LIVE_POLLER_ENABLED: "false"`.
- **Caddyfile:** §4.3.
- **`bin/deploy`:** the `pl` health path stays `/api/health`.
- **README:** add an "Admin" section with the hash/secret commands, and a "Live PL" rollback note.
- **`FOOTBALL_DATA_KEY`** isn't in Azure's secrets; the owner adds it to `.env` if PL's live mode needs it (the spike in rollout step 1 checks).

## 5. Rollout

Each step ships on its own:

| # | Step | Repo | Done when |
|---|---|---|---|
| 1 | **Spike (throwaway):** run the current PL image with `PUBLIC_MODE=false` on the VPS alongside the stack; record peak RSS, the CPU used by the 240 s refresh, and whether any key besides the odds keys is required | vps-stack | numbers written into this spec's §7 |
| 2 | `ADMIN_ENABLED` / `ADMIN_PROXY_SECRET` / `AUTO_RETRAIN_ENABLED` / `TRACKING_DB_PATH` settings, `_admin_only` change, `/api/session`, `useSession()` | PL | tests in §6 pass; local dev unchanged |
| 3 | Budget counter, scheduler, button changes, `/api/odds/status`, `odds_updated_at`, frontend polling | PL | tests in §6 pass |
| 4 | VPS switch: compose/Caddy/.env changes, seed the tracking DB, deploy; watch one full matchday | vps-stack | §6 live checks pass |
| 5 | ESPN-first odds | NFL, CFB | tests in §6 pass; the next snapshot shows `odds_sources.espn > 0` |
| 6 | Live-poller switch | F1 | poller not started on the VPS |
| 7 | PL `refresh-public-snapshot.yml`: remove the `schedule:` triggers, keeping `workflow_dispatch` so the rollback snapshot can still be rebuilt | PL | no scheduled runs |

**Rollback:** PL sets `PUBLIC_MODE=true` in `/opt/stack/.env` and runs `bin/deploy deploy pl <current sha>`, bringing the snapshot site back (run the snapshot workflow manually first if the last snapshot is stale). NFL/CFB/F1 revert their commit.

## 6. Testing

All tests use pytest with no live network; external responses are recorded JSON fixtures under `tests/fixtures/`.

- **PL admin check:** a parametrized table over `PUBLIC_MODE` × `ADMIN_ENABLED` × header {valid, wrong, missing} × secret {set, unset}, asserting 404 vs allowed for `/api/retrain` and the `admin` value of `/api/session`. Wrong-secret requests must 404, not 403.
- **PL budget counter:**
  - UTC day rollover resets the counts;
  - each pool's cap refuses spending past it;
  - the key floor refuses spending once `key_remaining < floor`;
  - a cache hit spends nothing;
  - two threads can't overspend (a concurrency test with a barrier).
- **PL scheduler:** `desired_max_age` at every tier boundary with a fixed `now` (e.g. exactly 90 min, 24 h, 7 days); the lineup-confirmed forced refresh; `plan_refresh` ordering and exclusion of kicked-off fixtures.
- **PL Refresh button:**
  - 202 on first call, 429 with wait time during the cooldown, 429 budget message when the button pool is exhausted;
  - the admin header bypasses the cooldown but not the pool;
  - `/api/odds/status` reflects a completed refresh.

  Extend the existing `tests/test_refresh_odds_public.py`.
- **PL frontend:** there's no test runner (don't add one for this). Verify with `npm run build` (typecheck) and a browser check: click Refresh, see the status change to "odds updated HH:MM", and confirm admin controls appear only on the admin address.
- **NFL/CFB ESPN parser:** tested against a recorded real scoreboard response (the fixture JSON is committed). Check the American→decimal conversion, the three markets, and name normalization. A "format changed" test feeds a response without `odds` and expects an empty frame and a warning, not an exception.
- **NFL/CFB gap-filling:** stub sources cover ESPN complete (no paid calls), ESPN missing 2 games (exactly 2 CFB Sportsbook calls / 1 NFL Odds API call, filtered), the per-run cap reached, and the floor reached. Assert the `odds_sources` counts.
- **F1:** with the poller setting off, the lifespan doesn't create the poller task.
- **Live checks after step 4:**
  - `curl https://pl.<domain>/api/retrain -X POST` returns 404;
  - the admin address asks for a password and `/api/session` there returns `admin: true`;
  - over 48 h spanning a matchday, the ledger's `scheduler + button` never exceeds 120 and `key_remaining` never drops below 15;
  - `docker stats` stays under the memory budget.

## 7. Open questions and measurements

- Spike results (rollout step 1): PL live-mode peak RSS, CPU of the 240 s refresh, and required keys. *Fill in before step 4.*
- Whether NBA's own Sportsbook usage leaves PL enough headroom. It shows up as `key_remaining` in `/api/odds/status`. If PL is regularly held back by the floor, lower NBA's usage in a separate change.
