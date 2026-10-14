# NBA model gaps: which models are weakest, and what the data on disk could add

Date 2026-10-13. Research only: nothing here merges or deploys. DRAFT, written section by section; sections marked PENDING are not done yet.

Scope: Kevocado/NBA_Predictor at main `9e97c43`. All numbers below were produced by a rebuild of the (gitignored) training cache from the ESPN caches, see "How the cache was rebuilt".

## 1. Inventory: what data exists, what the models use, what they ignore

Row counts are what I counted on 2026-10-13 from the cache copies in `/Users/sigey/Documents/Projects.nosync/NBA_Predictor/data/cache` (the `/Users/sigey/predictor/NBA_Predictor` copy holds only 6 files: schedule, 4 hub files, injuries_current, no box scores).

| dataset | rows / span | columns | used by features today | UNUSED |
|---|---|---|---|---|
| ESPN team box score `espn/boxscore_<id>.json` | 1,387 games with a box (2025-10-02 to 2026-06-13); 1,760 scoreboard rows incl. unplayed through 2026-11-30 | per team: fgm, fga, fg3m, fg3a, ftm, fta, oreb, dreb, tov (+ final pts from scoreboard) | `fgm fga fg3m tov oreb fta` and the opponent's `dreb` -> four factors (eFG, TOV%, ORB%, FT rate), 10-game rolling mean | `ftm` (dropped at ingest, `BOX_FIELDS` has no ftm); `fg3a` (read only by the display-only matchup facts, not by any model); own `dreb`; **points scored/allowed as a feature** (pts is only a target); possessions/pace/ratings as features (`features/ratings.py` has the functions, the model never calls them; `game_context.py` has pace/opp_adj_net/rest_delta/injury_delta, not wired into `FEATURE_COLUMNS`); steals, blocks, fouls, plus-minus: **not in the cache at all** (the parser keeps nine fields) |
| ESPN player box score `espn/player_boxscore_<id>.json` | 30,613 player-games, 648 players, 1,387 games | player_id, name, team, position (G/F/C; ~100 rows PG/PF/SF/blank), minutes, points, rebounds, assists, fg made-att, 3pt made-att, ft made-att | prop models: 10-game rolling mean of points, rebounds, assists, fg3m, minutes; the matchup-feature variant also fga (usage), opponent, position | `fg3a`, `fta/ftm`, `fgm` (only via usage_trend, which is not in the serving path), **starter flag, plus-minus, steals/blocks/turnovers/fouls (not captured)**; team context (teammates out); game total/spread (blowout risk); the whole data set feeds NO team-model feature (no availability-weighted strength) |
| Scoreboard/schedule `espn/scoreboard_<date>.json`, `schedule/games.json`, `data/public_snapshot.json` schedule | 426 scoreboard days; `games.json` 1,760 rows; snapshot 1,509 rows 2025-10-02 to 2026-10-26 (1,423 completed) | game_id, date, home, away, completed, scores; `tip_off` UTC in the snapshot (1,509/1,509), `null` in `schedule/games.json` | date, home/away -> rest days, back-to-back, streak, travel (opt-in), conference/division, altitude | **tip-off hour** (local start time, rest measured in hours instead of calendar days, afternoon/late games, back-to-back second-night-of-travel); venue/neutral-site flags; season phase (preseason vs regular vs playoffs: the frame mixes preseason from 2025-10-02 with the regular season, no game-type column exists) |
| Injuries `espn/injuries_current.json` | 65 rows, one snapshot (13 Out, 52 Day-To-Day), no history; `injuries/` other files are test fixtures (LeBron stub) | team, player_name, status | the API availability gate at serve time; `home_missing_value` / `away_missing_value` exist but are **constant 0.0 in training** | everything for training: with no dated history there is no way to know who was out on a past night, so injuries cannot be a trained feature from this cache. They could be reconstructed from player box scores (who played, minutes) |
| Hub snapshots `hub/players.json`, `teams.json`, `rankings.json`, `standings.json` | 648 players, 30 teams | per player: rating, live_form_rating, ppg/rpg/apg, fg%, 3p%, ft%, usage_rate, mpg; per team: wins/losses, ppg, opp ppg, net_rating, pace, streak; rankings: power_rating (Elo-like 1500 base) and trend | display only | these are **end-of-season aggregates** (leak if used to predict games inside the same season); `power_rating` in the hub is never fed to the model, and the model's `home_power_rating`/`away_power_rating` columns are constant 0.0 |
| Odds / sportsbook `odds/`, `sportsbook/` | **0 files** locally (both dirs empty); `tracking.db` tables `game_market_predictions`, `odds_timing_snapshots`, `value_picks`, `value_closing_lines` have 0 rows | n/a | n/a | **no market-implied baseline can be computed from anything on disk** |
| `tracking.db` (local copy) | `predictions` 1,511 rows (one batch 2026-09-18 12:02, model v20260918120240); `player_prediction_snapshots` 132,788 (4 stats x 33,197, one batch 2026-09-18 12:02-12:03); `game_player_outcomes` 122,452 | | | these were scored in bulk after the games and on the models' own training rows, so they are in-sample backfill. They are not evidence of skill (same caveat as the ~1,400 "winner pick" rows) |
| `balldontlie/`, `models/`, `features/`, `value_bets/`, `nba_api/` | 1-6 tiny files each | test fixtures (e.g. LeBron 203999, game 0012400001) | none | nothing real; empty or stubs |

### Findings from the inventory (observed, not inferred)

1. **Five of the 22 default `FEATURE_COLUMNS` have zero variance in the rebuilt training frame**: `home_power_rating`, `away_power_rating`, `power_rating_diff`, `home_missing_value`, `away_missing_value` (std 0.000; they are zero-filled by `_OPTIONAL_COLUMNS_DEFAULT_ZERO` because the ingest never supplies them). The served models carry 5 dead columns, and `docs/nba-parity-evaluation` item "Elo beats every ML candidate" is explained in part by this: the win model has no strength rating at all, only 10-game four-factor means, rest, streak.
2. **The team model's whole view of team quality is the four factors over the last 10 games.** Points scored/allowed, margin, pace, opponent strength and schedule strength are not in it.
3. `home_rest_days` has std 9.9: first-in-role games read 99 (and the offseason/preseason gap is unclipped), so the linear models (ridge/logistic) get a few 99-valued rows that dominate the coefficient. Rest is a calendar-day count from the same-role last game by default.
4. Local data = one season (2025-26 incl. preseason). The multi-season frame (4,149 games) used by `tools/compare_margin_average.py` is NOT on this machine; the box scores for earlier seasons would need the free ESPN pull (`pipeline/backfill.py`), which I did not run.

## How the cache was rebuilt

PENDING (step 1 follow-up in the final version).

## 2. Models ranked by weakness (PENDING, step 2)
## 3. Feature proposals for the 3 weakest (PENDING, step 3)
## 4. Tests with the harness (PENDING, step 4)
## 5. Report, recommendations, what could not be measured, commands (PENDING, step 5)
