# PL + F1: which models are weakest, and can data we already hold fix them?

Date: 2026-10-13. Status: DRAFT, written incrementally (steps 1-2 of 5 present; sections marked PENDING are not done yet). Research only: nothing here is merged or deployed in PL_Predictor or F1_Predictor.

Question (Kevin): "keep researching how the data we have can be made to make features we don't have yet, and which models are the worst and can they improve with the data we have now?"

Method: fresh clones of Kevocado/PL_Predictor (main at b41d5a4) and Kevocado/F1_Predictor, caches copied read-only from `/Users/sigey/predictor/*/data/cache`, every run with sockets blocked (no network, no new data). Scripts and raw CSVs for every number are in `docs/research/2026-10-13-pl-f1-model-gaps/`.

## 1. One-screen summary

PENDING (written last).

## 2. Data inventory (step 1)

### 2.0 What was actually on disk (matters for what could be measured)

| Cache dir (PL) | State on this machine |
|---|---|
| football_data | 12 files, 2014-15..2025-26, 380 rows/season |
| understat | 13 files, 2014..2026 (2026 = 50 matches so far) |
| understat_shots | 4,610 per-match files = 117,846 shots, 2014..2026, plus `_aggregate*`/`_fixtures*` files |
| fpl_history | 2016-17..2025-26 + 2026-27 (610 rows) |
| other_competitions/cups | 4 CSVs, ALL EMPTY (0 rows) |
| clubelo, odds, odds_snapshots, sportsbook, pulselive, fpl_players, fpl_events, fpl_research | EMPTY directories |

So the brief's `clubelo`, `odds`, `sportsbook`, `pulselive`, `fpl_players` caches contributed nothing: no ClubElo experiment, no odds-snapshot or sportsbook comparison, and no cup-fixture congestion feature could be tested. The market-implied baseline below uses the odds columns inside the football-data CSVs instead (archived Bet365 opening, Pinnacle closing, 2019-20+ O/U).

| Cache dir (F1) | State |
|---|---|
| jolpica | 167 race results + 167 qualifying JSONs (2019..2026 rounds 1-15), 8 schedules, 2 "latest driver standings" files. No pit-stop, lap-time, sprint-result or constructor-standings files. |
| open_meteo | 175 daily-weather JSONs, 3 fields each (temp max, precipitation sum, wind max) |
| fastf1 | an empty HTTP-cache sqlite (0 responses); openf1 dir empty |

The committed manifest says `last_race` = 2026 R17 but the cache stops at 2026 R15, so the 2026 fold below has 15 races, not 17.

### 2.1 PL datasets: seasons | columns | used by builders | UNUSED

| Dataset | Seasons / size | Columns present | Used by current feature builders | Unused (candidate fuel) |
|---|---|---|---|---|
| football_data results/stats | 2014-15..2025-26, 380 rows each, no gaps | date, teams, fthg/ftag, hthg/htag/htr, referee, hs/as, hst/ast, hf/af, hc/ac, hy/ay, hr/ar (all 100% filled every season) | goals, shots, SoT, corners, fouls, cards (yellow+red), referee card-rate, date -> rolling last 3/5/10, venue splits, Elo/Pi, H2H, rest | half-time goals/result (`hthg htag htr`) are not read by any module (grep) |
| football_data odds | opening Bet365/BW/IW/PS/WH/VC for all 12 seasons; O/U 2.5 (b365, Pinnacle, avg, max) + Asian handicap + closing odds from 2019-20; Pinnacle closing 100% to 2024-25, 55% in 2025-26 | ~100 odds columns | only the closing-odds benchmark and the value-bet backtest (evaluation), never a model feature | market-implied probabilities as a feature (see section 5, not tested as a feature: serving has no historical-quality opening price for all fixtures) |
| understat team xG | 2014..2025 full + 2026 (50) | xg_home/away, forecast_w/d/l, goals | rolling xG for/against 5/10, xG-delta (xg - goals) 5/10 | `forecast_w/d/l` (Understat's own pre-match win/draw/lose probability) is never used |
| understat_shots | 2014..2026, 117,846 shots | minute, result (Goal/Saved/Blocked/Missed/Post), x, y, x_g, player, player_id, h_a, situation (OpenPlay 86k, FromCorner 19k, SetPiece 7k, DirectFreekick 4k, Penalty 1k), shot_type, player_assisted (74% filled), last_action (88%) | set-piece xG share (computed, then excluded from the model: helps corners, hurts cards) and the player shots/SoT aggregation | shot location (x,y), minute, shot_type, last_action, shot quality (xG per shot), non-penalty xG, open-play xG, big-chance counts, game-state timing |
| fpl_history | 2016-17..2025-26 + 2026-27 start; 22-30k player-gameweek rows per season. Richer columns only from 2020-21 (xG/xA/xGI/xGC/starts only from 2022-23; defensive_contribution from 2024-25) | minutes, goals, assists, bps, bonus, ict/influence/creativity/threat, clean_sheets, saves, cards, value/selected/transfers, was_home, opponent_team, team scores; 2022-23+: expected_goals/assists/goal_involvements/goals_conceded, starts | player form (goals/assists/xG/xA per 90, last 3/5/10, minutes EMA, starts), squad-continuity (minutes by squad), player ratings, lineup model | team-level absence-weighted strength (minutes-weighted share of the XI missing), `selected`/`transfers_*` market sentiment, `value` (price) as a quality prior, `bps`/`bonus` for the Player Hub only |
| clubelo, odds, odds_snapshots, sportsbook, pulselive, fpl_players | empty | n/a | n/a | not assessable |

How "used" was determined: `models/manifest.json` feature list (267 columns: rolling goals/shots/SoT/corners/fouls/cards/points for/against at 3/5/10 incl. venue splits, Elo, Pi, H2H, rest days, first-match flag, referee card rate, xG for/against 5/10, xG delta 5/10, streak, squad continuity) plus grep of `src/pl_predictor/features/*.py`. Features that are computed but excluded from the served set: fixture congestion (`games_last_14_days`, `european_fixture_last_4_days`), table-position stakes, set-piece xG share, each rejected by earlier PL experiments (see `docs/RESEARCH_FINDINGS.md` section 2).

### 2.2 F1 datasets

| Dataset | Seasons / size | Columns present | Used by builders | UNUSED |
|---|---|---|---|---|
| jolpica race results | 2019..2026 R1-15, 3,368 driver-race rows | position, grid, points, laps, status, finish time (millis), fastest-lap rank + time, constructor | position/points/DNF (status) -> Elo, team strength, rolling form 3/5/10, circuit history, circuit DNF rate; grid | `laps` (completed), finish-time gap to winner, `fastest_lap_rank` (loaded into the frame, never a feature), status text split (mechanical vs collision) |
| jolpica qualifying | same 167 races | q1/q2/q3 times | `quali_position`, `quali_gap_to_pole` (best of q1-q3) | Q1/Q2/Q3 progression, per-driver Q-to-Q improvement, teammate quali gap |
| jolpica schedule | 2019..2026 | circuit, lat/long, FP1/FP2/FP3/quali/sprint datetimes | tier logic, weather lookup | sprint-weekend flag (derivable), race hour/time-of-day |
| standings | only 2024 and 2026 "latest" snapshots | points, wins | championship projection | not usable historically (no per-round snapshots) |
| open_meteo | 175 race days | temp max, precip sum, wind max | all three as raw features | interactions (rain x circuit history), rain-day indicator |
| pit stops, lap times, tyre stints, safety cars, practice | NOT on disk (jolpica pit-stop/lap endpoints never cached; FastF1 and OpenF1 caches empty) | n/a | the production race model has no practice features (`TIER_COLUMNS[post_practice]` is `[]`) | tyre/pit strategy and practice pace cannot be built from disk |

## 3. Ranking models by weakness (step 2)

How these numbers were produced. PL: `h/pl_rank.py` rebuilds the production frame with the repo's `build_training_frame` (8 seasons, 267 features), then for each of the 5 walk-forward folds (validate 2021-22..2025-26, train on all earlier seasons, same as `evaluate/walk_forward.prepare_folds`) trains the production `ml_scoreline` (default hyperparameters) and the production XGBoost count models (`market_models.train_lambda_regressor`) on the full 267 columns with `fillna(0)` exactly like `manifest.train_all`, then scores the 1,900 held-out matches. Paired bootstrap: 2,000 resamples over matches, seed 0, 95% percentile CI of (baseline loss minus model loss); positive = model better; "skill" = that difference divided by the baseline loss. Corners use the 8-season frame here, not production's 12-season window, so the corners row can differ slightly from the live model. All are RE-RUN numbers; the manifest's single-fold values were only read for sanity (this run's 2025-26 slice and manifest agree within noise: e.g. manifest ml_scoreline RPS 0.2086 on the single holdout).

### 3.1 PL, team markets (re-run, 1,900 matches, 5 folds)

| market | baseline | n | model | baseline value | base-minus-model | 95% CI | skill % | verdict |
|---|---|---|---|---|---|---|---|---|
| 1X2 RPS | league freq | 1900 | 0.1998 | 0.2323 | +0.0325 | [+0.0268, +0.0379] | +14.0 | model better |
| 1X2 RPS | market (Bet365 open, de-vig) | 1900 | 0.1998 | 0.1950 | -0.0048 | [-0.0073, -0.0023] | -2.5 | model WORSE |
| 1X2 RPS | market (Pinnacle close, de-vig) | 1730 | 0.1982 | 0.1918 | -0.0064 | [-0.0091, -0.0037] | -3.3 | model WORSE |
| O/U2.5 Brier | train base rate | 1900 | 0.2446 | 0.2470 | +0.0024 | [-0.0008, +0.0057] | +1.0 | tie |
| O/U2.5 Brier | market b365 | 1899 | 0.2446 | 0.2400 | -0.0046 | [-0.0076, -0.0014] | -1.9 | model WORSE |
| O/U2.5 Brier | market pin | 1719 | 0.2447 | 0.2396 | -0.0051 | [-0.0084, -0.0018] | -2.1 | model WORSE |
| O/U2.5 Brier | market avg | 1900 | 0.2446 | 0.2399 | -0.0047 | [-0.0077, -0.0018] | -1.9 | model WORSE |
| BTTS Brier | train base rate | 1900 | 0.2464 | 0.2486 | +0.0021 | [-0.0001, +0.0044] | +0.9 | tie |
| Exact score log-loss | indep. Poisson (train means) | 1900 | 2.9749 | 3.1023 | +0.1274 | [+0.1017, +0.1522] | +4.1 | model better |
| 1X2 log-loss | league freq | 1900 | 0.9764 | 1.0691 | +0.0927 | [+0.0759, +0.1084] | +8.7 | model better |
| corners MAE | train mean | 1900 | 2.7557 | 2.7285 | -0.0271 | [-0.0620, +0.0065] | -1.0 | tie |
| corners MAE | trailing-10 team rates (no model) | 1900 | 2.7557 | 2.7594 | +0.0037 | [-0.0421, +0.0495] | +0.1 | tie |
| cards MAE | train mean | 1900 | 1.6671 | 1.7032 | +0.0361 | [+0.0084, +0.0642] | +2.1 | model better |
| cards MAE | trailing-10 team rates (no model) | 1900 | 1.6671 | 1.6657 | -0.0015 | [-0.0337, +0.0286] | -0.1 | tie |
| hshots MAE | train mean | 1900 | 3.8970 | 4.4438 | +0.5468 | [+0.4280, +0.6695] | +12.3 | model better |
| hshots MAE | trailing-10 team rates (no model) | 1900 | 3.8970 | 3.9697 | +0.0727 | [-0.0121, +0.1595] | +1.8 | tie |
| ashots MAE | train mean | 1900 | 3.5274 | 4.0831 | +0.5557 | [+0.4461, +0.6662] | +13.6 | model better |
| ashots MAE | trailing-10 team rates (no model) | 1900 | 3.5274 | 3.8796 | +0.3522 | [+0.2610, +0.4342] | +9.1 | model better |
| hsot MAE | train mean | 1900 | 1.8826 | 2.0279 | +0.1453 | [+0.0946, +0.1949] | +7.2 | model better |
| hsot MAE | trailing-10 team rates (no model) | 1900 | 1.8826 | 1.8815 | -0.0011 | [-0.0386, +0.0342] | -0.1 | tie |
| asot MAE | train mean | 1900 | 1.7278 | 1.8340 | +0.1063 | [+0.0623, +0.1523] | +5.8 | model better |
| asot MAE | trailing-10 team rates (no model) | 1900 | 1.7278 | 1.8174 | +0.0896 | [+0.0548, +0.1258] | +4.9 | model better |

Reading it: a model "ties" when its CI includes zero.

PENDING: player markets (goal/assist/G+A), player shots, F1 ranking, final ordering.
