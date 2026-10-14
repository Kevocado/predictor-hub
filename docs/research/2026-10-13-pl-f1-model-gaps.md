# PL + F1: which models are weakest, and can data we already hold fix them?

Date: 2026-10-13. Research only. Nothing here is merged or deployed in PL_Predictor or F1_Predictor.

Question (Kevin): "keep researching how the data we have can be made to make features we don't have yet, and which models are the worst and can they improve with the data we have now?"

Method: fresh clones of Kevocado/PL_Predictor (main at b41d5a4) and Kevocado/F1_Predictor, caches copied read-only from `/Users/sigey/predictor/*/data/cache`, every run with sockets blocked (no network, no new data, no post-event data). All scripts, logs and result CSVs are in `docs/research/2026-10-13-pl-f1-model-gaps/` (section 8 has the exact command for every number). Every number in this document was **re-run** in this session unless it is explicitly marked "read".

## 1. One-screen summary

**Worst models (skill = improvement over the naive baseline, paired-bootstrap 95% CI, worst first):**

| # | Model | Naive baseline | Result |
|---|---|---|---|
| 1 | F1 race win and podium probabilities (after qualifying) | grid-position win/podium rate from earlier seasons | **Worse than the lookup**: win log-loss -14.5% (CI excludes 0), podium -14.7%, top-10 -7.3%. Ties plain Elo. |
| 2 | PL player shots and shots-on-target (display hidden) | position-average and own-trailing per-90 | **Worse than both**: shots MAE 0.8387 vs 0.7742 (position average, -8.3%) and 0.7419 (own trailing, -13.0%) |
| 3 | F1 qualifying order | driver's mean of last 3 qualifying positions | **Worse**: MAE 3.66 vs 3.48 places; pole hit-rate 21.5% vs 33.6% |
| 4 | PL BTTS | train base rate | **No skill shown**: Brier skill +0.9%, CI includes 0 |
| 5 | PL Over/Under 2.5 | train base rate; Bet365 opening price | Ties base rate (+1.0%, CI includes 0); **worse than the market** (-1.9%, CI excludes 0) |
| 6 | PL corners | train mean; trailing-10 team rates | Ties both (-1.0% and +0.1%, CIs include 0) |
| 7 | PL 1X2 | league frequency; market | +14.0% RPS skill vs league frequency, but **worse than Bet365 opening (-2.5%) and Pinnacle closing (-3.3%)** |
| - | F1 sprint models | n/a | **Not measurable**: no sprint results in the cache (manifest shows 612 training rows) |

Best: PL anytime goal/assist/G+A (research arm: Brier +10.1% / +5.7% / +14.2% vs prevalence, +2.5% / +1.7% / +2.5% vs the own-rate Poisson union), PL team shots/SoT, exact score (+4.1%), F1 DNF (+2.1%).

**Can they improve with data we hold now? Top 3 findings (all measured):**

1. **F1 win/podium probabilities are fixable without new data.** A 2-parameter calibration layer (temperature on the ranker score plus log of grid position, fitted only on earlier-season out-of-fold scores) improves race-win log-loss by 0.027 [0.016, 0.037], calibration gap 0.0096 -> 0.0085, and beats the grid-position lookup (+0.0099 [0.0036, 0.0161]). Podium: +0.041 [0.025, 0.055] vs the current model, tie vs the lookup. It does **not** help top-10 (worse), so top-10 must stay un-layered or be fit separately.
2. **F1 qualifying improves with data already on disk but unused:** the driver's own recent qualifying positions (`qf3, qf5, qgapf5`). MAE 3.661 -> 3.529 [improvement +0.044, +0.226], pole-probability calibration gap 0.0075 -> 0.0048; with a teammate qualifying-gap form added, MAE 3.467 [+0.109, +0.282]. Both meet the binding bar.
3. **PL player shots: the empirical-Bayes shrunk per-90 rate beats BOTH naive baselines** (evaluation tool only, nothing served): shots MAE 0.7125 vs 0.7742 (position average) and 0.7417 (own trailing), CIs exclude 0 on absolute error, squared error and Poisson NLL; SoT beats both on squared error, NLL and P(SoT>=1) Brier but only **ties** own-trailing on SoT absolute error ([-0.0040, +0.0018]). So the plan's strict gate is not fully met, and its calibration clause fails at the low deciles because the lineup model gives 6% of appearances (who then play 46 minutes on average) under 5 expected minutes. With actual minutes plugged in the shrunk rate is calibrated across all deciles.

**What did not work (do not retry):** none of the seven new PL team-market feature sets (shot quality, opponent-adjusted xG lambda, EB referee rates, set-piece xG share for corners, congestion, market-implied opening probabilities, FPL absence persistence) clears the bar for O/U 2.5, corners or cards; none of the six F1 race feature sets (quali form, teammate-relative, constructor reliability, wet-race skill, race-pace proxy, safety-car proxy) clears the bar for the race model, mostly because the calibration gap widened.

**Biggest unverified items:** sprint models; any feature needing pit stops, laps, tyres or practice (not on disk); ClubElo, odds snapshots, sportsbook, pulselive (empty caches); the PL absence feature only exists for 2020-21 onward (FPL has no team column before that) and the 2026 F1 fold is 15 races (cache stops at round 15, manifest says 17).

## 2. Data inventory

### 2.0 What was actually on disk

| PL cache dir | State on this machine |
|---|---|
| football_data | 12 files, 2014-15..2025-26, 380 rows per season, no gaps |
| understat | 13 files, 2014..2026 (2026 = 50 matches so far) |
| understat_shots | 4,610 per-match files = 117,846 shots, 2014..2026, plus `_aggregate*`/`_fixtures*` files |
| fpl_history | 2016-17..2025-26 plus 2026-27 (610 rows). Team and position columns exist only from 2020-21 |
| other_competitions/cups | 4 CSVs, ALL EMPTY (0 rows) |
| clubelo, odds, odds_snapshots, sportsbook, pulselive, fpl_players, fpl_events, fpl_research | EMPTY directories |

So the brief's `clubelo`, `odds`, `sportsbook`, `pulselive`, `fpl_players` caches contributed nothing: no ClubElo experiment, no odds-snapshot or sportsbook comparison, and no cup-fixture congestion feature (the empty cup files mean `european_fixture_last_4_days` is always 0 here). The market-implied baseline below uses the odds columns inside the football-data CSVs instead (Bet365 opening for all 12 seasons, Pinnacle closing 100% to 2024-25 and 55% in 2025-26, O/U 2.5 odds from 2019-20).

| F1 cache dir | State |
|---|---|
| jolpica | 167 race-result and 167 qualifying JSONs (2019..2026 rounds 1-15), 8 schedules, 2 "latest driver standings" files. No pit-stop, lap-time, sprint-result or constructor-standings files. |
| open_meteo | 175 daily-weather JSONs, 3 fields each |
| fastf1 | an empty HTTP-cache sqlite (0 responses); openf1 dir empty |

The committed manifest says `last_race` = 2026 round 17, but the cache stops at round 15, so the 2026 fold below has 15 races, not 17.

### 2.1 PL datasets: seasons | columns | used by builders | UNUSED

| Dataset | Seasons / size | Columns present | Used by current feature builders | Unused (candidate fuel) |
|---|---|---|---|---|
| football_data results/stats | 2014-15..2025-26 | date, teams, fthg/ftag, hthg/htag/htr, referee, hs/as, hst/ast, hf/af, hc/ac, hy/ay, hr/ar (100% filled in every season) | goals, shots, SoT, corners, fouls, cards, referee card rate, dates -> rolling last 3/5/10, venue splits, Elo/Pi, H2H, rest | half-time goals/result (`hthg htag htr`) are read by no module |
| football_data odds | opening Bet365/BW/IW/PS/WH/VC all 12 seasons; O/U 2.5, Asian handicap, closing odds from 2019-20 | ~100 odds columns | only the closing-odds benchmark and the value-bet backtest, never a model feature | market-implied probabilities as a feature (tested in 4.1, fails the bar) |
| understat team xG | 2014..2025 full, 2026 (50) | xg_home/away, forecast_w/d/l, goals | rolling xG for/against 5/10, xG-delta 5/10 | `forecast_w/d/l` (Understat's own pre-match probabilities) is never used |
| understat_shots | 2014..2026, 117,846 shots | minute, result, x, y, x_g, player, player_id, h_a, situation (OpenPlay 86k, FromCorner 19k, SetPiece 7k, DirectFreekick 4k, Penalty 1k), shot_type, player_assisted (74% filled), last_action (88%) | set-piece xG share (computed, excluded from the served set) and the player shots/SoT aggregation | shot location, minute, shot_type, last_action, xG per shot, non-penalty xG, box shots, big chances (the first four tested in 4.1) |
| fpl_history | 2016-17..2025-26 + 2026-27 start; 22-30k rows per season. xG/xA/xGI/xGC and `starts` from 2022-23; `defensive_contribution` from 2024-25 | minutes, goals, assists, bps, bonus, ICT, clean sheets, saves, cards, value, selected, transfers, was_home, opponent, scores | player form (per-90 goals/assists/xG/xA, last 3/5/10, minutes EMA, starts), squad continuity, ratings, lineup model | team-level absence-weighted strength (tested in 4.1), `selected`/`transfers_*` sentiment, `value` as a quality prior |
| clubelo, odds, odds_snapshots, sportsbook, pulselive, fpl_players | empty | n/a | n/a | not assessable |

How "used" was determined: `models/manifest.json` feature list (267 columns: rolling goals/shots/SoT/corners/fouls/cards/points for and against at 3/5/10 including venue splits, Elo, Pi, H2H, rest days, first-match flag, referee card rate, xG for/against 5/10, xG delta 5/10, streak, squad continuity) plus grep of `src/pl_predictor/features/*.py`. Computed but excluded from the served set: fixture congestion (`games_last_14_days`, `european_fixture_last_4_days`), table-position stakes, set-piece xG share, each rejected earlier (`docs/RESEARCH_FINDINGS.md` section 2, read).

### 2.2 F1 datasets

| Dataset | Seasons / size | Columns present | Used by builders | UNUSED |
|---|---|---|---|---|
| jolpica race results | 2019..2026 R1-15, 3,368 driver-race rows | position, grid, points, laps, status, finish time, fastest-lap rank + time, constructor | position/points/DNF -> Elo, team strength, rolling form 3/5/10, circuit history, circuit DNF rate; grid | `laps`, finish-time gap, `fastest_lap_rank` (loaded into the frame, never a feature), status text split (mechanical vs collision) |
| jolpica qualifying | same 167 races | q1/q2/q3 times | `quali_position`, `quali_gap_to_pole` (best of q1-q3) | the driver's own qualifying history (tested in 4.2), Q1/Q2/Q3 progression, teammate quali gap (tested) |
| jolpica schedule | 2019..2026 | circuit, lat/long, FP1-3/quali/sprint datetimes | tier logic, weather lookup | sprint-weekend flag |
| standings | only 2024 and 2026 "latest" snapshots | points, wins | championship projection | not usable historically |
| open_meteo | 175 race days | temp max, precip sum, wind max | all three as raw features | interactions such as rain x driver wet-race skill (tested in 4.2) |
| pit stops, lap times, tyre stints, safety cars, practice | NOT on disk | n/a | the production race model has no practice features (`TIER_COLUMNS[post_practice]` is `[]`) | cannot be built from disk |

## 3. Ranking models by weakness

How the numbers were produced. **Paired bootstrap** everywhere: 2,000 resamples, seed 0, 95% percentile CI of (baseline loss minus model loss), resampling matches (PL team markets), team-matches (PL players), appearances clustered by match (shots), or races (F1). Positive = model better. "Skill" = that difference divided by the baseline loss.

**PL team markets**: `h/pl_rank.py` rebuilds the production frame with the repo's `build_training_frame` (8 seasons, 267 features), then for each of 5 walk-forward folds (validate 2021-22..2025-26, train on all earlier seasons, same as `evaluate/walk_forward.prepare_folds`) trains the production `ml_scoreline` (default hyperparameters) and the production XGBoost count models on the full 267 columns with `fillna(0)` exactly like `manifest.train_all`, and scores the 1,900 held-out matches. Corners use the 8-season frame here, not production's 12-season window, so that row can differ slightly from the live model. Baselines use training seasons only. Market baselines are proportional de-vig of the football-data prices. The run is deterministic (a repeat gave identical predictions, max difference 0.0).

### 3.1 PL team markets (re-run, 1,900 matches, 5 folds)

| market | baseline | n | model | baseline value | baseline minus model | 95% CI | skill % | verdict |
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

The 1X2 gap to the market is the key number: the model beats a league-frequency guess by 14% but loses to the Bet365 opening price by 2.5% (CI excludes 0). Calibration: ECE of P(over 2.5) 0.0215, P(BTTS) 0.0160, P(home win) 0.0183.

### 3.2 PL player anytime goal / assist / G+A (re-run, research arm)

These come from the repo's own research code path (`evaluate/goal_contribution_research.py`: `build_goal_contribution_frame`, logistic "direct" classifier with Platt calibration, and the Poisson union of last-10 per-90 rates), not from the live served `predict_player`; the serving construction differs (see `docs/AI_CONTINUITY.md` EXP-2026-28, read). Folds: the repo helper only had data for 2022-23..2025-26, so there are 2 folds (2024-25, 2025-26), 57,362 player-fixture rows including unused substitutes; the prevalence baseline is therefore soft, and the own-rate union is the fairer naive.

| target | model | metric | model | prevalence | prevalence minus model | 95% CI | skill % |
|---|---|---|---|---|---|---|---|
| goal | direct | brier | 0.0288 | 0.0321 | +0.0032 | [+0.0028, +0.0037] | +10.1 |
| goal | direct | ll | 0.1084 | 0.1456 | +0.0373 | [+0.0351, +0.0395] | +25.6 |
| goal | union_platt | brier | 0.0296 | 0.0321 | +0.0025 | [+0.0022, +0.0028] | +7.8 |
| goal | union_platt | ll | 0.1218 | 0.1456 | +0.0238 | [+0.0218, +0.0259] | +16.3 |
| assist | direct | brier | 0.0286 | 0.0303 | +0.0017 | [+0.0014, +0.0021] | +5.7 |
| assist | direct | ll | 0.1122 | 0.1392 | +0.0270 | [+0.0252, +0.0289] | +19.4 |
| assist | union_platt | brier | 0.0291 | 0.0303 | +0.0012 | [+0.0010, +0.0014] | +4.1 |
| assist | union_platt | ll | 0.1252 | 0.1392 | +0.0140 | [+0.0123, +0.0157] | +10.0 |
| goal_contribution | direct | brier | 0.0485 | 0.0565 | +0.0080 | [+0.0072, +0.0089] | +14.2 |
| goal_contribution | direct | ll | 0.1675 | 0.2274 | +0.0599 | [+0.0566, +0.0632] | +26.4 |
| goal_contribution | union_platt | brier | 0.0497 | 0.0565 | +0.0068 | [+0.0061, +0.0074] | +12.0 |
| goal_contribution | union_platt | ll | 0.1834 | 0.2274 | +0.0440 | [+0.0408, +0.0472] | +19.3 |

Direct classifier vs the own-rate Poisson union (the stronger naive):

| target | metric | direct | own-rate Poisson union (Platt) | union minus direct | 95% CI | skill % |
|---|---|---|---|---|---|---|
| goal | brier | 0.0288 | 0.0296 | +0.0007 | [+0.0004, +0.0010] | +2.5 |
| goal | ll | 0.1084 | 0.1218 | +0.0135 | [+0.0118, +0.0151] | +11.1 |
| assist | brier | 0.0286 | 0.0291 | +0.0005 | [+0.0002, +0.0007] | +1.7 |
| assist | ll | 0.1122 | 0.1252 | +0.0130 | [+0.0113, +0.0147] | +10.4 |
| goal_contribution | brier | 0.0485 | 0.0497 | +0.0013 | [+0.0008, +0.0018] | +2.5 |
| goal_contribution | ll | 0.1675 | 0.1834 | +0.0160 | [+0.0138, +0.0183] | +8.7 |

### 3.3 PL player shots and shots-on-target (re-run of the PL#65 tool)

`python h/run_shots_bt.py` runs `evaluate/player_shots_backtest.py` unchanged on 34,448 appearances (2023-24..2025-26). It reproduces PL#65: shots MAE model 0.8387, position-average 0.7742, own-trailing 0.7419; model minus position-average +0.0645 [+0.0467, +0.0813] (PL#65 reported +0.065 [+0.047, +0.081]); minus own-trailing +0.0967 [+0.0825, +0.1110]. 23.4% of appearances get exactly 0 expected shots (log: `shots_bt.log`). Correlation with actual shots 0.380, same as the position average (0.377).

### 3.4 F1 (re-run, walk-forward validation seasons 2022..2026, POST_QUALIFYING tier)

`h/f1_rank.py` rebuilds the production frame (`build_training_frame`), trains the production ranker on earlier seasons' post-qualifying rows with the manifest's tuned hyperparameters (the same protocol as `evaluate/walk_forward.py`), converts scores to Plackett-Luce win/podium/top-10 probabilities (Gumbel-trick simulation, 20,000 draws; with no DNFs, same as the repo's evaluation), and compares with (a) the Elo+team-strength arm, (b) **a grid-position lookup**: P(win | grid slot), P(podium | slot), P(top 10 | slot) from earlier seasons, normalised within each race. Unit of resampling = race (107 races: 22, 22, 24, 24, 15). Sanity check against the committed manifest (read): the Elo arm matches it to within 0.002 in every fold (2022: 0.1417 vs 0.1406; 2023: 0.1006 vs 0.1012; 2024: 0.1493 vs 0.1481; 2025: 0.1397 vs 0.1387), and the XGBoost arm is within 0.007 (2022: 0.1628 vs 0.157; 2023: 0.1259 vs 0.1196; 2024: 0.1427 vs 0.1387; 2025: 0.1219 vs 0.1264; random-seed noise). The grid lookup per-season win log-loss is 0.1402, 0.1224, 0.1274, 0.0995, 0.0932, so the committed manifest's XGBoost fold values (0.157, 0.1196, 0.1387, 0.1264) are worse than a grid lookup in 3 of the 4 comparable seasons. Note `retrain_gate.py` only compares a candidate with the previous model, so a model like this passes the gate however it compares with a lookup.

| market | model arm | baseline | baseline value | baseline minus model | 95% CI | skill % | verdict |
|---|---|---|---|---|---|---|---|
| win logloss | x_w | g_w | 0.1179 | -0.0171 | [-0.0286, -0.0056] | -14.5 | model WORSE |
| win logloss | e_w | g_w | 0.1179 | -0.0192 | [-0.0327, -0.0050] | -16.2 | model WORSE |
| win logloss | x_w | e_w | 0.1371 | +0.0021 | [-0.0092, +0.0131] | +1.5 | tie |
| pod logloss | x_p | g_p | 0.2462 | -0.0362 | [-0.0555, -0.0170] | -14.7 | model WORSE |
| pod logloss | e_p | g_p | 0.2462 | -0.0438 | [-0.0633, -0.0232] | -17.8 | model WORSE |
| pod logloss | x_p | e_p | 0.2900 | +0.0077 | [-0.0099, +0.0242] | +2.6 | tie |
| top10 logloss | x_t | g_t | 0.5208 | -0.0378 | [-0.0718, -0.0054] | -7.3 | model WORSE |
| top10 logloss | e_t | g_t | 0.5208 | -0.0903 | [-0.1347, -0.0487] | -17.3 | model WORSE |
| top10 logloss | x_t | e_t | 0.6111 | +0.0525 | [+0.0135, +0.0879] | +8.6 | model better |
| win Brier | x_w | g_w | 0.0332 | -0.0053 | [-0.0080, -0.0025] | -15.9 | model WORSE |
| podium Brier | x_p | g_p | 0.0740 | -0.0149 | [-0.0218, -0.0079] | -20.1 | model WORSE |
| DNF logloss | x_dnf | n_dnf | 0.4216 | +0.0089 | [+0.0043, +0.0147] | +2.1 | model better |
| finish-pos MAE (classified+DNF=20) | x_e | g_e | 3.6440 | +0.1131 | [+0.0055, +0.2252] | +3.1 | model better |
| finish-pos MAE (classified+DNF=20) | e_e | g_e | 3.6440 | -0.0620 | [-0.2031, +0.0784] | -1.7 | tie |

DNF model: logloss 0.4216 base rate vs model +0.0089 better (+2.1%); ECE of DNF probability 0.0066 (model) vs 0.0021 (base rate). Finishing-order: expected position MAE (DNF counted as 20) +3.1% better than the grid-position lookup, tie with Elo.

F1 qualifying order (`h/f1_quali.py`, production session ranker, tuned hyperparameters, 107 races):

| metric | model | baseline | model value | baseline value | improvement | 95% CI | verdict |
|---|---|---|---|---|---|---|---|
| MAE of predicted grid position | mae_x | mae_qform | 3.6607 | 3.4790 | -0.1817 | [-0.3341, -0.0436] | model WORSE |
| MAE of predicted grid position | mae_x | mae_elo | 3.6607 | 3.6329 | -0.0278 | [-0.1638, +0.1193] | tie |
| MAE of predicted grid position | mae_x | mae_formrace | 3.6607 | 3.8942 | +0.2335 | [+0.0897, +0.3759] | model better |
| Spearman (higher better) | sp_x | sp_qform | 0.6558 | 0.6788 | -0.0230 | [-0.0456, -0.0012] | model WORSE |
| Spearman (higher better) | sp_x | sp_elo | 0.6558 | 0.6573 | -0.0016 | [-0.0244, +0.0208] | tie |
| pole hit-rate | pole_x | pole_qform | 0.2150 | 0.3364 | -0.1215 | [-0.2336, -0.0093] | model WORSE |
| pole hit-rate | pole_x | pole_elo | 0.2150 | 0.2991 | -0.0841 | [-0.1963, +0.0280] | tie |

**Sprint qualifying and sprint**: not measurable. The jolpica cache holds no sprint results, so the sprint targets are empty (the manifest shows 612 training rows for each). Treat them as unvalidated.

### 3.5 Final order, worst first

1. F1 win/podium probability (-14.5% / -14.7% vs a grid lookup)
2. PL player shots/SoT (-8.3% to -13.0%)
3. F1 qualifying (-5.2% MAE vs recent-quali naive)
4. PL BTTS (tie with base rate)
5. PL O/U 2.5 (tie with base rate, -1.9% vs market)
6. PL corners (tie with train mean)
7. PL 1X2 (+14% vs frequency, -2.5% to -3.3% vs market)
8. then cards (+2.1%), F1 DNF (+2.1%), exact score (+4.1%), F1 finishing position (+3.1%), team shots/SoT (+6% to +14%), player anytime (+2% to +14%)

## 4. Candidate features: derivation, leakage check, results

Rule applied (binding, as asked): a candidate **ships only if** the paired-bootstrap 95% CI of the primary-metric improvement is entirely above 0 **and** the calibration gap (ECE for probabilities; decile gap for counts) did not widen versus the baseline, otherwise "does not ship". The calibration rule is applied literally, which is strict: ECE has sampling noise of roughly 0.005-0.01 at these sample sizes, so a "widened" verdict with a tiny change is weak evidence and is shown with its numbers.

### 4.1 PL (feature built from caches, same 5 folds as 3.1, same model code, baseline = the re-run in 3.1)

Weakest three PL models chosen for features: player shots (4.1.1), goal totals O/U 2.5 and BTTS (4.1.2), corners (4.1.3, with cards as the nearest count market). `h/pl_feats.py` and `h/pl_absence.py` build every feature below with `shift(1)` within team/referee (or from prior matches only); `h/pl_exp.py <variant>` retrains `ml_scoreline`, corners and cards with the extra columns; `h/pl_exp_score.py` scores them. The baseline rerun is bit-identical to 3.1.

| Feature set | Derivation | Leakage check | Files to change if it ever ships |
|---|---|---|---|
| `shotq` shot quality | per team: rolling-10 mean of non-penalty xG per shot, non-penalty xG, box shots (x>0.83), big chances (xG>=0.3), each for and against, from `understat_shots` | rolling over prior matches only, `shift(1)`; joined by (team, date); 99.5% of fixtures matched | new `features/shot_quality.py`, `features/build.py::FEATURE_COLUMNS`, serving context |
| `oppadj` Dixon-Coles-style opponent-adjusted lambda | trailing-20 non-penalty xG for/against, shrunk to the prior league mean with 6 pseudo-matches, turned into att x def multipliers and a match-level lambda for each side | trailing and league mean use prior matches only | `features/xg_form.py` or new module, `FEATURE_COLUMNS` |
| `ref_eb` referee tendency | empirical-Bayes (10 pseudo-games) shrunk referee cards/fouls per game, plus home-minus-away card bias, expanding and shifted | referee history before the match only | `features/referee.py` |
| `sp_share` set-piece xG share | existing computed columns (`*_set_piece_xg_share_last_5/10`), added to the served set | shifted rolling, already in the frame | `FEATURE_COLUMNS` |
| `congestion` | existing computed columns (`games_last_14_days_*`, `european_fixture_last_4_days_*`); the cup files are empty here so only league games count | prior fixtures only | `FEATURE_COLUMNS` |
| `market_open` | de-vigged Bet365 opening 1X2 and O/U 2.5 probabilities (O/U odds only exist from 2019-20, missing earlier) | opening price is pre-match, but serving would use a different live feed: train/serve parity needs checking | `features/build.py`, `odds/` plumbing |
| `absence` FPL absence persistence | for each team-match: the 11 players with most minutes in matches t-10..t-4; `abs_min` = share of their expected minutes (average x3) not played in t-3..t-1; `abs3` = share of them with 0 minutes in t-1. Only 2020-21+ (FPL team column), earlier seasons 0 | matches before t only; the starting XI of t itself is never used | `features/squad_change.py` or new |

Results (primary metric marked; the full table including every metric is in `pl_exp_results.csv`):

| variant | metric | primary? | base | candidate | improvement | 95% CI | calibration gap base -> cand | verdict |
|---|---|---|---|---|---|---|---|---|
| absence | O/U 2.5 Brier | **yes** | 0.2446 | 0.2453 | -0.00064 | [-0.00158, +0.00030] | 0.0215 -> 0.0277 (widened) | does not ship |
| congestion | O/U 2.5 Brier | **yes** | 0.2446 | 0.2450 | -0.00041 | [-0.00129, +0.00048] | 0.0215 -> 0.0269 (widened) | does not ship |
| market_open | O/U 2.5 Brier | **yes** | 0.2446 | 0.2438 | +0.00085 | [-0.00075, +0.00245] | 0.0215 -> 0.0248 (widened) | does not ship |
| market_open | 1X2 RPS |  | 0.1998 | 0.1973 | +0.00252 | [+0.00104, +0.00402] | 0.0183 -> 0.0270 (widened) | nan |
| oppadj | O/U 2.5 Brier | **yes** | 0.2446 | 0.2439 | +0.00069 | [-0.00067, +0.00203] | 0.0215 -> 0.0295 (widened) | does not ship |
| ref_eb | cards MAE | **yes** | 1.6671 | 1.6671 | +0.00005 | [-0.01108, +0.01231] | 0.3681 -> 0.4013 (widened) | does not ship |
| shotq | O/U 2.5 Brier | **yes** | 0.2446 | 0.2438 | +0.00083 | [-0.00032, +0.00194] | 0.0215 -> 0.0222 (widened) | does not ship |
| sp_share | corners MAE | **yes** | 2.7557 | 2.7506 | +0.00506 | [-0.01283, +0.02132] | 0.5894 -> 0.5416 | does not ship |

Verdicts: **none of the seven ships.** The nearest miss is `market_open`: it improves 1X2 RPS by +0.00252 [+0.00104, +0.00402], so its point estimate is the only sizeable gain in the whole PL section, but its primary O/U metric does not clear zero ([-0.00075, +0.00245]), and the home-win calibration gap widened (0.0183 -> 0.0270) and it has a train/serve parity problem. `shotq`'s O/U gain is +0.00083 [-0.00032, +0.00194]. These are consistent with the earlier project finding (RESEARCH_FINDINGS section 2, read) that more rolling-form columns add noise: the model already has 267 of them.

Not testable: referee identity at serving time (referees are announced days before kickoff; `referee_card_rate` is already league-average at serve per `features/build.py`), historical FPL availability (FPL status is not archived, so a true "who is injured" feature cannot be backtested; `absence` is only a persistence proxy), ClubElo and cup congestion (empty caches).

#### 4.1.1 PL player shots: empirical-Bayes shrunk per-90 rate (evaluation tool only)

`h/pl_shots_eb.py` implements the plan's Task 2 inside the evaluation: `rate = (cur_shots + k * prior) / (cur_minutes/90 + k)`, where `prior` is the player's prior-season shots per 90 if he played at least 450 minutes then (matched by normalised name, because FPL element ids change across seasons), else the position average per 90. `k` is chosen **separately for shots and SoT** by minimising out-of-sample squared error on seasons before the evaluated one (grid 0.5..40): fitted k = 8 / 5 / 5 for shots and 12 / 12 / 12 for SoT in 2023-24 / 2024-25 / 2025-26. Prediction = rate x min(expected minutes, 90) / 90 using the same lineup-model expected minutes as the baselines. It reads the same appearances and baselines as the PL#65 tool (it merges onto `shots_bt.csv`), so the comparison is on identical rows, with the same paired cluster bootstrap by match. No serving code is touched.

Headline (34,460 appearances; mean shots actual 0.819, EB 0.704, position average 0.681, production 0.893):

| | MAE | RMSE | Poisson NLL | exact-zero share |
|---|---|---|---|---|
| shots: EB shrunk rate | **0.7125** | **1.0634** | **0.8424** | 5.0% |
| shots: position average | 0.7742 | 1.1387 | 0.9260 | 0% |
| shots: own trailing per-90 | 0.7417 | 1.2252 | 1.5429 | 23.4% |
| shots: production model | 0.8384 | 1.4993 | 1.6214 | 23.4% |
| SoT: EB | **0.3403** | **0.5575** | **0.5686** | 8.3% |
| SoT: position average | 0.3628 | 0.5794 | 0.5907 | 0% |
| SoT: own trailing | 0.3414 | 0.6143 | 1.0347 | 40.4% |
| SoT: production model | 0.3759 | 0.7569 | 1.0659 | 40.4% |

P(SoT >= 1) with `1 - exp(-lambda)`: Brier EB 0.1442, position average 0.1527, own trailing 0.1561, production 0.1618.

| target | baseline | metric (EB minus baseline, negative = EB better) | difference | 95% CI | verdict |
|---|---|---|---|---|---|
| shots | position_avg | abs err | -0.0617 | [-0.0659, -0.0576] | EB better |
| shots | position_avg | sq err | -0.1659 | [-0.1806, -0.1516] | EB better |
| shots | position_avg | NLL | -0.0837 | [-0.0908, -0.0771] | EB better |
| shots | own_trailing_per90 | abs err | -0.0292 | [-0.0366, -0.0223] | EB better |
| shots | own_trailing_per90 | sq err | -0.3704 | [-0.5858, -0.1998] | EB better |
| shots | own_trailing_per90 | NLL | -0.7005 | [-0.7802, -0.6269] | EB better |
| shots | production_model | abs err | -0.1259 | [-0.1421, -0.1092] | EB better |
| shots | production_model | sq err | -1.1172 | [-1.5087, -0.8084] | EB better |
| shots | production_model | NLL | -0.7790 | [-0.8578, -0.7039] | EB better |
| SoT | position_avg | abs err | -0.0225 | [-0.0241, -0.0208] | EB better |
| SoT | position_avg | sq err | -0.0248 | [-0.0281, -0.0216] | EB better |
| SoT | position_avg | NLL | -0.0221 | [-0.0274, -0.0166] | EB better |
| SoT | own_trailing_per90 | abs err | -0.0011 | [-0.0040, +0.0018] | tie |
| SoT | own_trailing_per90 | sq err | -0.0665 | [-0.0900, -0.0484] | EB better |
| SoT | own_trailing_per90 | NLL | -0.4662 | [-0.4989, -0.4325] | EB better |
| SoT | production_model | abs err | -0.0355 | [-0.0429, -0.0283] | EB better |
| SoT | production_model | sq err | -0.2621 | [-0.4191, -0.1646] | EB better |
| SoT | production_model | NLL | -0.4974 | [-0.5313, -0.4637] | EB better |
| P(SoT>=1) | position_avg | Brier | -0.0085 | [-0.0093, -0.0076] | EB better |
| P(SoT>=1) | position_avg | logloss | -0.0131 | [-0.0177, -0.0083] | EB better |
| P(SoT>=1) | own_trailing_per90 | Brier | -0.0119 | [-0.0131, -0.0106] | EB better |
| P(SoT>=1) | own_trailing_per90 | logloss | -0.3976 | [-0.4239, -0.3703] | EB better |
| P(SoT>=1) | production_model | Brier | -0.0176 | [-0.0194, -0.0159] | EB better |
| P(SoT>=1) | production_model | logloss | -0.4182 | [-0.4448, -0.3913] | EB better |

**Does it beat BOTH naive baselines with CIs?** Shots: yes on all three metrics against both baselines. SoT: yes against position average on all three and against own-trailing on squared error, NLL and P(SoT>=1) Brier, but **only a tie on SoT absolute error vs own trailing** ([-0.0040, +0.0018]). The plan's Task 5 requires every CI to exclude zero, so the strict gate is not met by that one metric. It also holds by season: shots MAE EB 0.7246 / 0.7123 / 0.7007 vs position average 0.7981 / 0.7705 / 0.7543 and own trailing 0.7464 / 0.7379 / 0.7408; SoT own-trailing is marginally better in 2024-25 (0.3366 vs 0.3408).

Calibration and why the low deciles still miss: by-decile predicted vs actual mean shots (model minutes) is 0.002/0.077, 0.066/0.380, 0.205/0.382, 0.334/0.464, 0.461/0.570, 0.604/0.673, 0.788/0.865, 1.038/1.093, 1.391/1.472, 2.146/2.217, so deciles 0-3 miss the plan's 15%/0.05 rule. The cause is expected minutes, not the rate: 6.0% of appearances have expected minutes under 5 (`predict_lineup` returns `p_start*90 + (1-p_start)*sub_rate_last5*SUB_MINUTES`, which is 0 for anyone with no recent substitute appearance) and those players actually played 45.8 minutes on average and took 0.557 shots. With actual minutes plugged in, the same EB rate is calibrated in every decile (0.003/0.019, 0.071/0.144, 0.217/0.298, 0.363/0.436, 0.499/0.540, 0.653/0.642, 0.876/0.826, 1.206/1.138, 1.683/1.609, 2.648/2.540), and the oracle-minutes accuracy comparison is:

| comparison | metric | EB minus baseline | 95% CI | verdict |
|---|---|---|---|---|
| oracle minutes: shots vs position_avg | abs err | -0.0827 | [-0.0880, -0.0778] | EB better |
| oracle minutes: shots vs position_avg | sq err | -0.1953 | [-0.2131, -0.1785] | EB better |
| oracle minutes: shots vs own_trailing | abs err | -0.0346 | [-0.0420, -0.0278] | EB better |
| oracle minutes: shots vs own_trailing | sq err | -0.3634 | [-0.4973, -0.2611] | EB better |
| oracle minutes: SoT vs position_avg | abs err | -0.0247 | [-0.0267, -0.0228] | EB better |
| oracle minutes: SoT vs position_avg | sq err | -0.0260 | [-0.0299, -0.0221] | EB better |
| oracle minutes: SoT vs own_trailing | abs err | -0.0010 | [-0.0047, +0.0025] | tie |
| oracle minutes: SoT vs own_trailing | sq err | -0.1086 | [-0.1898, -0.0615] | EB better |

So the rate fix works; the remaining shortfall is the minutes model. By experience, players with 0 prior same-season games now get a rate (the prior) instead of a hard 0, but their model-minutes expectation is still near zero (mean 0.029 vs actual 0.611).

### 4.2 F1 (frame from `build_training_frame`, same ranker/DNF hyperparameters and folds as 3.4; unit of resampling = race)

`h/f1_feats.py` builds the features from jolpica results/qualifying and open-meteo, all `shift(1)` within driver/constructor/circuit. `h/f1_exp.py` retrains the race ranker and DNF model per fold with the extra columns; baseline = the same code without them.

| Feature set | Derivation | Leakage check | Files to change if it ever ships |
|---|---|---|---|
| `qform` | driver's mean quali position over last 3 and 5 qualifyings, mean gap to pole last 5, and mean positions gained (grid minus classified finish) last 5 | previous races only | `features/rolling_form.py`, `features/build.py::FEATURE_COLUMNS`, `features/session_build.py::BASE_SESSION_FEATURES` |
| `teammate` | driver's form_avg_position_5 minus teammates' in the same race; rolling-5 mean of own quali position minus teammate's | previous races only (form is already shifted) | `features/team_strength.py` or `rolling_form.py` |
| `reliability` | constructor mechanical-DNF rate last 20 driver-races, and at this circuit (4 pseudo-visits shrunk to the constructor rate); mechanical = DNF whose status is not collision/accident/spun/disqualified/withdrew/retired | prior races only | `features/safety_car.py` |
| `wet_x` | wet-race flag (precipitation >= 1 mm), driver's prior positions gained in wet minus dry races (3 pseudo-races shrink), and their product | prior races; weather is a forecast at serve time | `features/weather.py` |
| `pace` | driver's mean fastest-lap rank over the last 5 races (race-pace proxy) | previous races only | `features/rolling_form.py` |
| `sc_proxy` | share of finishers lapped and collision-DNF share at this circuit in prior visits (no safety-car data on disk, so this is a proxy) | prior visits only | `features/safety_car.py` |

Not buildable from disk: tyre/pit-stop strategy history per circuit, practice pace, true safety-car rate (need laps/pit/race-control data, none cached).

**Race model (post-qualifying tier):**

| variant | metric | primary? | base | candidate | improvement (positive = better) | 95% CI | calibration gap (ECE) base -> cand | verdict |
|---|---|---|---|---|---|---|---|---|
| qform | win logloss | **yes** | 0.1350 | 0.1275 | +0.00752 | [+0.00251, +0.01264] | 0.0096 -> 0.0157 (widened) | does not ship |
| qform | podium logloss |  | 0.2823 | 0.2704 | +0.01194 | [+0.00350, +0.02092] | 0.0461 -> 0.0397 | nan |
| teammate | win logloss | **yes** | 0.1350 | 0.1348 | +0.00023 | [-0.00451, +0.00501] | 0.0096 -> 0.0060 | does not ship |
| teammate | podium logloss |  | 0.2823 | 0.2828 | -0.00047 | [-0.00797, +0.00739] | 0.0461 -> 0.0427 | nan |
| reliability | win logloss |  | 0.1350 | 0.1335 | +0.00152 | [-0.00233, +0.00523] | 0.0096 -> 0.0125 (widened) | nan |
| reliability | podium logloss |  | 0.2823 | 0.2792 | +0.00314 | [-0.00258, +0.00879] | 0.0461 -> 0.0424 | nan |
| reliability | DNF logloss |  | 0.4127 | 0.4128 | -0.00012 | [-0.00070, +0.00042] | 0.0066 -> 0.0065 | nan |
| wet_x | win logloss | **yes** | 0.1350 | 0.1324 | +0.00259 | [-0.00107, +0.00651] | 0.0096 -> 0.0130 (widened) | does not ship |
| wet_x | podium logloss |  | 0.2823 | 0.2827 | -0.00033 | [-0.00728, +0.00635] | 0.0461 -> 0.0368 | nan |
| pace | win logloss | **yes** | 0.1350 | 0.1320 | +0.00294 | [-0.00146, +0.00748] | 0.0096 -> 0.0154 (widened) | does not ship |
| pace | podium logloss |  | 0.2823 | 0.2767 | +0.00569 | [-0.00105, +0.01260] | 0.0461 -> 0.0381 | nan |
| sc_proxy | win logloss |  | 0.1350 | 0.1331 | +0.00191 | [-0.00185, +0.00574] | 0.0096 -> 0.0111 (widened) | nan |
| sc_proxy | podium logloss |  | 0.2823 | 0.2791 | +0.00324 | [-0.00354, +0.00959] | 0.0461 -> 0.0367 | nan |
| sc_proxy | DNF logloss |  | 0.4127 | 0.4129 | -0.00016 | [-0.00065, +0.00028] | 0.0066 -> 0.0055 | nan |

`qform` is the only race candidate whose primary CI clears zero (win log-loss +0.00752 [+0.00251, +0.01264]); it fails the binding bar because the win-probability calibration gap widened (0.0096 -> 0.0157), though podium calibration improved (0.0461 -> 0.0397). The honest reading is "borderline, needs the calibration layer": see the combination below. `reliability` and `sc_proxy` do not move DNF log-loss at all (+/-0.0002), so their DNF hypothesis is rejected.

**Qualifying model (primary: per-race MAE of predicted grid position; production session ranker; `h/f1_quali_exp.py`):**

| variant | base MAE | candidate MAE | improvement | 95% CI | pole-prob log-loss improvement [95% CI] | pole ECE base -> cand | verdict |
|---|---|---|---|---|---|---|---|
| qform | 3.6607 | 3.5292 | +0.1315 | [+0.0436, +0.2256] | +0.0040 [+0.0002, +0.0078] | 0.0075 -> 0.0048 | SHIP-ELIGIBLE |
| teammate | 3.6607 | 3.5909 | +0.0698 | [-0.0082, +0.1474] | +0.0008 [-0.0027, +0.0042] | 0.0075 -> 0.0074 | does not ship |
| pace | 3.6607 | 3.6375 | +0.0232 | [-0.0586, +0.1099] | +0.0035 [-0.0000, +0.0068] | 0.0075 -> 0.0082 | does not ship |
| qform+teammate | 3.6607 | 3.4668 | +0.1939 | [+0.1092, +0.2815] | +0.0023 [-0.0020, +0.0066] | 0.0075 -> 0.0073 | SHIP-ELIGIBLE |

`qform` and `qform+teammate` both pass the binding bar. For reference, the naive "driver's last-3 qualifying positions" had MAE 3.479, so `qform+teammate` (3.467) matches it rather than clearly beating it: this fixes the deficit, it does not add skill beyond the naive form.

**Calibration layer for the race ranker (not a new data feature; `h/f1_calib.py`).** Nested walk-forward: for each validation season, ranker scores for the earlier seasons come from models trained only on seasons before each of them, then (a) a temperature T (theta = exp(T x score)) or (b) T plus a coefficient on log(grid position) is fitted to minimise race-win log-loss on those out-of-fold scores, and applied to the validation season. Fitted T and grid coefficient were stable across folds (T+grid: T 0.54-0.62, grid 1.24-1.37). "Reference" rows = production raw ranker, or the grid lookup.

| calibration layer | metric | compared with | reference | candidate | improvement | 95% CI | ECE ref -> cand | verdict |
|---|---|---|---|---|---|---|---|---|
| T | win logloss | production raw | 0.1350 | 0.1332 | +0.0017 | [+0.0004, +0.0031] | 0.0096 -> 0.0091 | meets bar |
| T | win logloss | grid-position naive | 0.1179 | 0.1332 | -0.0153 | [-0.0276, -0.0032] | 0.0185 -> 0.0091 | does not meet bar |
| T | podium logloss | production raw | 0.2823 | 0.2821 | +0.0002 | [-0.0027, +0.0030] | 0.0461 -> 0.0373 | does not meet bar |
| T | podium logloss | grid-position naive | 0.2462 | 0.2821 | -0.0360 | [-0.0565, -0.0156] | 0.0210 -> 0.0373 | does not meet bar |
| T | top10 logloss | production raw | 0.5586 | 0.5742 | -0.0156 | [-0.0235, -0.0079] | 0.0395 -> 0.0466 | does not meet bar |
| T | top10 logloss | grid-position naive | 0.5208 | 0.5742 | -0.0533 | [-0.0934, -0.0165] | 0.0291 -> 0.0466 | does not meet bar |
| T+grid | win logloss | production raw | 0.1350 | 0.1080 | +0.0270 | [+0.0162, +0.0369] | 0.0096 -> 0.0085 | meets bar |
| T+grid | win logloss | grid-position naive | 0.1179 | 0.1080 | +0.0099 | [+0.0036, +0.0161] | 0.0185 -> 0.0085 | meets bar |
| T+grid | podium logloss | production raw | 0.2823 | 0.2416 | +0.0407 | [+0.0255, +0.0550] | 0.0461 -> 0.0239 | meets bar |
| T+grid | podium logloss | grid-position naive | 0.2462 | 0.2416 | +0.0046 | [-0.0089, +0.0176] | 0.0210 -> 0.0239 | does not meet bar |
| T+grid | top10 logloss | production raw | 0.5586 | 0.5828 | -0.0242 | [-0.0479, -0.0023] | 0.0395 -> 0.0631 | does not meet bar |
| T+grid | top10 logloss | grid-position naive | 0.5208 | 0.5828 | -0.0620 | [-0.1023, -0.0243] | 0.0291 -> 0.0631 | does not meet bar |

With the quali-form columns in the ranker as well (`python h/f1_calib.py qform`):

| calibration layer | metric | compared with | reference | candidate | improvement | 95% CI | ECE ref -> cand | verdict |
|---|---|---|---|---|---|---|---|---|
| T | win logloss | production raw | 0.1275 | 0.1243 | +0.0032 | [+0.0008, +0.0054] | 0.0157 -> 0.0092 | meets bar |
| T | win logloss | grid-position naive | 0.1179 | 0.1243 | -0.0064 | [-0.0186, +0.0061] | 0.0185 -> 0.0092 | does not meet bar |
| T | podium logloss | production raw | 0.2704 | 0.2714 | -0.0010 | [-0.0058, +0.0035] | 0.0397 -> 0.0330 | does not meet bar |
| T | podium logloss | grid-position naive | 0.2462 | 0.2714 | -0.0252 | [-0.0438, -0.0054] | 0.0210 -> 0.0330 | does not meet bar |
| T | top10 logloss | production raw | 0.5440 | 0.5740 | -0.0300 | [-0.0451, -0.0162] | 0.0385 -> 0.0529 | does not meet bar |
| T | top10 logloss | grid-position naive | 0.5208 | 0.5740 | -0.0531 | [-0.0942, -0.0114] | 0.0291 -> 0.0529 | does not meet bar |
| T+grid | win logloss | production raw | 0.1275 | 0.1043 | +0.0232 | [+0.0126, +0.0329] | 0.0157 -> 0.0075 | meets bar |
| T+grid | win logloss | grid-position naive | 0.1179 | 0.1043 | +0.0136 | [+0.0072, +0.0202] | 0.0185 -> 0.0075 | meets bar |
| T+grid | podium logloss | production raw | 0.2704 | 0.2394 | +0.0310 | [+0.0163, +0.0450] | 0.0397 -> 0.0193 | meets bar |
| T+grid | podium logloss | grid-position naive | 0.2462 | 0.2394 | +0.0067 | [-0.0061, +0.0194] | 0.0210 -> 0.0193 | does not meet bar |
| T+grid | top10 logloss | production raw | 0.5440 | 0.5916 | -0.0476 | [-0.0734, -0.0237] | 0.0385 -> 0.0677 | does not meet bar |
| T+grid | top10 logloss | grid-position naive | 0.5208 | 0.5916 | -0.0708 | [-0.1137, -0.0303] | 0.0291 -> 0.0677 | does not meet bar |

Reading: the temperature alone only fixes sharpness (win +0.0018, never reaches the lookup). Adding grid position as an explicit covariate does what the tree ranker fails to do: win log-loss improves by 0.027 and then also beats the lookup, and podium log-loss improves by 0.041 with a lower calibration gap, but top-10 gets worse because the layer is fitted on win only. Quali-form on top adds little once the layer is present (win 0.1043 vs 0.1080).

## 5. Prioritized recommendations

1. **F1: add the grid-aware calibration layer to the race win/podium output, and put a grid-lookup row in the retrain gate.** Evidence: section 4.2 table. Files: `models/race_outcome.py` (a function between `theta_from_xgb_scores` and `simulate_race`), `models/manifest.py` (fit T and the grid coefficient on out-of-fold scores, persist them), `evaluate/walk_forward.py` (nested out-of-fold scores, add a `grid_naive` arm), `retrain_gate.py` (also reject when the candidate loses to the grid arm). Caveats: top-10/points probabilities degrade under the win-fitted layer, so either fit the layer per market or leave top-10 on raw scores; it is validated on post-qualifying only; pre-weekend and post-practice tiers have no grid and are untouched.
2. **F1: give the qualifying model its own history.** Add `qf3, qf5, qgapf5` and the teammate qualifying-gap form to `SESSION_FEATURE_COLUMNS["qualifying"]` (and `BASE_SESSION_FEATURES`). Meets the bar (MAE 3.661 -> 3.467 with both). It is currently worse than the naive, so this is repair, not a gain over naive. Do not add it to the race model's post-qualifying tier (win calibration widened).
3. **PL shots/SoT: ship Task 2 (shrunk rate) after fixing the minutes floor, then re-run Task 5.** Evidence: 4.1.1. Order of work: (a) EB rate in `player_form.py`/`player_goals.predict_player`; (b) a minutes floor in `predict_lineup` (e.g. shrink `sub_rate_last5` to the position/season rate so nobody on the matchday squad gets under 5 minutes); (c) drop one of the two correlated team factors (PL#65 evidence); (d) keep `SHOW_PLAYER_SHOTS = false` until the full Task 5 gate (live-like inputs, SoT absolute error vs own trailing, deciles) passes.
4. **PL goal totals (O/U 2.5, BTTS) and corners: stop adding rolling-form features.** Seven feature sets tried, none passes. The measurable gap is to the **market** (-1.9% O/U, -2.5% 1X2): if the product wants accuracy there, the direction is an explicit, calibrated blend with the live odds the app already fetches (the `market_open` RPS gain +0.0025 [+0.0010, +0.0040] shows the information is there), tested with time-aligned snapshots, which this machine could not do (odds_snapshots empty). Do not claim this as a betting edge: the repo's own backtest yield is -4.6% with a CI spanning zero (read).
5. **Collect free pre-event data so the missing features can be tested:** F1 pit-stop and lap endpoints from jolpica (free) and FastF1/OpenF1 practice and stint data for 2018+/2023+ (all pre-event or historical, no paid source); PL: refill the empty cup, ClubElo, odds-snapshot and FPL availability caches. These are the only way to test tyre/pit strategy, practice pace, safety-car rate and true injury absence, which are the most plausible untested ideas.
6. **Add naive baselines to both repos' standard reports** (grid lookup for F1; base-rate and market for PL goals markets; position-average for player shots). Two of the three worst models above were invisible because their reported metrics had no naive row.

## 6. What could not be measured

- **F1 sprint qualifying and sprint**: no sprint results in the cache.
- **Tyre/pit strategy history, quali-vs-race pace from lap data, practice features, true safety-car rate, pit-stop reliability**: no pit/lap/practice data on disk (jolpica pitstops/laps never cached, FastF1/OpenF1 caches empty).
- **PL ClubElo, odds snapshots, sportsbook, pulselive, cup congestion, FPL player cache**: empty on this machine.
- **True absence/injury weighting**: FPL status is not archived, so only a minutes-persistence proxy was tested, and only for 2020-21 onward (6 of the 8 PL seasons carry it; the first two are filled with 0).
- **Corners at the live 12-season window**: tested on the 8-season frame.
- **Live-served player goal/assist probabilities**: only the research-arm classifiers were re-run, with 2 folds (the repo helper yielded 2022-23..2025-26 only).
- **F1 2026 fold**: 15 races in the cache vs 17 in the manifest.
- **Real expected-goals input for the PL#65 shots tool** (task 5 asks for a re-run with the real scoreline expectation): still the trailing 20-match substitute, availability = 1.0, exactly as in PL#65.
- The ECE-based calibration rule is noisy at these sample sizes; a different tolerance would flip some "does not ship" verdicts (notably F1 `qform` for race wins and `market_open` for 1X2).

## 7. Anything unverified

- The PL#65 tool's `own_trailing_per90` and `position_avg` baselines are used as defined there; I did not re-derive them independently.
- The nested out-of-fold calibration for F1 has only 39 inner races for the 2022 fold; later folds have 61-131.
- The grid-position lookup is normalised within a race to sum to 1 (win), 3 (podium) and 10 (top 10); un-normalised numbers would differ slightly.
- Numbers marked "read": `docs/RESEARCH_FINDINGS.md` and `AI_CONTINUITY.md` claims (rejections of congestion/set-piece/stakes features, betting yield -4.6%), and the committed manifests' walk-forward values (used only as cross-checks).

## 8. Exact commands (every number above)

Layout: put this directory at `<work>/h/` beside fresh clones `<work>/PL_Predictor` and `<work>/F1_Predictor`, each with `data/cache` copied from `/Users/sigey/predictor/<repo>/data/cache`. `PLPY` = `/Users/sigey/predictor/PL_Predictor/.venv/bin/python`, `F1PY` = `/Users/sigey/predictor/F1_Predictor/.venv/bin/python`; every script blocks sockets via `common.py` and prepends the clone's `src` to `sys.path`. Run from `<work>/h`.

| Number | Command | Output |
|---|---|---|
| PL frame | `$PLPY -W ignore pl_build.py` | `pl_frame.pkl` |
| 3.1 PL team markets | `$PLPY -W ignore pl_rank.py && $PLPY -W ignore pl_score.py` | `pl_rank.csv` |
| 3.2 player anytime | `$PLPY -W ignore pl_player_rank.py && $PLPY -W ignore pl_player_rank2.py` | `pl_player_rank.csv`, `pl_player_rank2.csv` |
| 3.3 PL#65 shots re-run | `$PLPY -W ignore run_shots_bt.py` | `shots_bt.log`, `shots_bt.csv` (not committed, 34k rows) |
| 4.1 PL features | `$PLPY -W ignore pl_feats.py; $PLPY -W ignore pl_absence.py; for v in base shotq oppadj ref_eb sp_share congestion market_open absence; do $PLPY -W ignore pl_exp.py $v; done; $PLPY -W ignore pl_exp_score.py` | `pl_exp_results.csv` |
| 4.1.1 EB shots | `$PLPY -W ignore pl_shots_eb.py shots_bt.csv; $PLPY -W ignore pl_shots_eb2.py` | `shots_eb_results.csv`, `shots_eb_oracle_results.csv`, `shots_eb.log` |
| F1 frame | `$F1PY -W ignore f1_build.py` | `f1_frame.pkl` |
| 3.4 F1 race ranking | `$F1PY -W ignore f1_rank.py` | `f1_rank.csv`, `f1_preds.pkl` |
| 3.4 F1 qualifying | `$F1PY -W ignore f1_quali.py` | `f1_quali_rank.csv` |
| 4.2 F1 features | `$F1PY -W ignore f1_feats.py; $F1PY -W ignore f1_exp.py; $F1PY -W ignore f1_quali_exp.py` | `f1_exp_results.csv`, `f1_quali_exp_results.csv` |
| 4.2 calibration layer | `$F1PY -W ignore f1_calib.py; $F1PY -W ignore f1_calib.py qform` | `f1_calib_results.csv`, `f1_calibqform_results.csv` |
| this document | `python3 docgen.py ../predictor-hub/docs/research/2026-10-13-pl-f1-model-gaps.md` (fills tables from the CSVs using `template.md`) | |

Runtime on this machine under heavy load: PL features about 1-2 minutes per variant, shots tool about 30-40 minutes, EB about 5 minutes, F1 scripts about 1-3 minutes each.
