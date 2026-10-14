# NFL / CFB model gaps: what the data on hand can still buy (2026-10-13)

Research only. Nothing here merges, trains an artifact, or deploys. Every number below was produced by a run
on 2026-10-13 unless it is marked READ (taken from a committed file, with its path). Scripts and raw logs are in
`docs/research/2026-10-13-nfl-cfb-model-gaps.assets/` (they are evidence, not hub code; nothing imports them).

## 0. Summary (one screen)

Kevin asked which models are worst and whether the data we already have can improve them.

**Worst models (skill vs a naive baseline, paired-bootstrap 95% CI, worst first):**

1. **CFB QB passing yards is worse than just using the QB's last-5 average**: MAE 50.83 vs 50.00 naive, skill -0.69 [-1.00, -0.35].
   CFB rushing yards is a tie with naive (-0.06 [-0.17, +0.05]). These two are the weakest models in either repo.
2. **NFL receptions ZINB for WR/TE has no demonstrated skill** (mu MAE 1.511 vs 1.499 naive, -0.012 [-0.023, -0.002]; its committed gate only tests calibration at its own line).
3. Then CFB receiving (1.8%), **NFL total points** (2.0%, +0.22 pts [+0.16, +0.29]) and **NFL passing yards** (2.5%, +1.75 yds [+0.84, +2.65];
   it loses to naive in 2019 and again in 2025), CFB total points (4.4%), NFL rushing / QB rushing (4.9%), anytime-TD and QB passing TDs (5.5-6.1%), NFL receiving (5.9%).
   NFL game outcome and CFB game outcome are the strongest (10% and 22% Brier skill) but the NFL model still loses to the Vegas
   spread by 0.35 pts of margin MAE [+0.27, +0.42].

**Can they improve with data we already have? Yes, in three places; most other ideas do not move anything.**

- **CFB prop regressors: one-line fix, no new data.** They are fit with squared error and judged on the median. Switching the XGBoost
  objective to `reg:absoluteerror` improves MAE by +2.93 yds [+2.74, +3.11] (passing), +1.39 [+1.31, +1.48] (rushing), +1.14 [+1.09, +1.19]
  (receiving), better in 5/5 validation seasons each, and turns the two losing markets into winners vs naive (+1.40 and +1.25 yds).
  Median-coverage gap for rushing 0.203 -> 0.025 and receiving 0.175 -> 0.026 (change CIs exclude widening).
- **NFL 2025 and 2026 player rows are silently excluded from every position-filtered model on this cache.** The nflverse depth-chart/roster
  feed changed schema (no `position` column) for 2025+, so `position` is null for 100% of 2025 (5,377) and 2026 (1,543) rows. The
  "2019-2025" walk-forward actually scores 2019-2024. With positions restored (from `pos_abb`), 2025 can be scored for the first time:
  passing yards **loses to naive in 2025** (MAE 74.80 vs 72.51).
- **NFL passing yards has two pbp-derived leads**: opponent pass/rush EPA allowed + own EPA (+1.04 yds [+0.42, +1.71], better in 6/6 seasons,
  +4.07 in the 2025 holdout) and neutral-script pass rate (+0.44 [+0.10, +0.81]). Both narrow the gap by point estimate (0.048 -> 0.034 / 0.032) but
  the gap-change CI straddles zero, so **they do not ship under the bar**. They are leads, not results.

**Did not help (tested, bar not met):** NFL game-outcome/total-points feature blocks (opp-adjusted EPA, pace, sack/pressure, neutral script, referee),
NFL pressure / red-zone / NGS / practice-status features on every yardage market, CFB explosiveness / run-structure / pace / situational-success
blocks for the win-probability model.

**Bar used (binding):** a candidate "ships" only if the paired-bootstrap 95% CI of the primary-metric improvement has lower bound > 0 AND the
95% CI of the calibration-gap change has upper bound <= 0. Everything else is "does not ship"; points that clear one half are called leads.
Nothing was merged or trained into an artifact.

## 1. Inventory of data on hand

"Referenced in code" = the column name appears as a string literal in the repo's `src/` or `scripts/` (coarse; over-counts columns that are read
only for joins). Command: `python cols.py <repo>/src <label>=<newest-season parquet> ...` (assets/cols.py). Column lists are from the newest season file.

### NFL (`Kevocado/NFL_Predictor`; gitignored cache `data/cache` copied read-only)

| Dataset | Seasons | Cols | Referenced in code | UNUSED columns worth noting |
|---|---|---|---|---|
| nflverse `pbp_YYYY` | 2017-2026 (2026: 13,643 rows so far) | 397 | 55 | `yardline_100`, `score_differential`, `wp`/`vegas_wp`, `shotgun`, `no_huddle`, `ydstogo`, `qtr`, `game_seconds_remaining`, `pass_location`, `run_gap`, `yards_after_catch`, `air_epa`/`yac_epa`, `td_prob`, `first_down_*`, `tackled_for_loss`, `penalty`, `posteam_timeouts_remaining` |
| nflverse `weekly_YYYY` (player-week) | 2017-2024; 2025-26 derived from pbp | 53 | 34 | `wopr`, `racr`, `pacr`, `dakota`, `sacks`, `sack_yards`, `*_fumbles*`, `*_2pt_conversions`, `special_teams_tds` |
| nflverse `schedules_YYYY` | 2017-2026 | 46 | 24 | `home/away_moneyline`, `home/away_spread_odds`, `home/away_qb_id/_name`, `home/away_coach`, `referee`, `overtime` |
| nflverse `ngs_YYYY` (pass/rush/rec stacked) | 2017-2026 | 51 | 17 | `expected_completion_percentage`, `completion_percentage_above_expectation`, `avg_time_to_los`, `percent_attempts_gte_eight_defenders`, `rush_yards_over_expected(_per_att)`, `avg_yac_above_expectation`, `catch_percentage` |
| nflverse `injuries_YYYY` | 2017-2026 | 16 | 9 | `practice_status` (DNP / limited / full), `report_primary_injury` |
| nflverse `rosters_YYYY` | 2017-2024 depth-chart schema; **2025-2026 new schema** (`pos_abb`, `pos_slot`, `pos_rank`, no `position`, no `club_code`) | 15 / 12 | 3 | all of `pos_*`; the schema break is a finding (Section 2b) |
| `depth_charts/` | **2024 only** (37,312 rows) | 15 | 9 | `formation`; one season so depth-chart role features can only train on 2024 |
| `pbp_agg/` participation join | 2000-2026 (27 files) | 38 | 13 | `offense_personnel`, `defense_personnel`, `defenders_in_box`, `number_of_pass_rushers`, `was_pressure`, `time_to_throw`, `defense_man_zone_type`, `defense_coverage_type`, `offense_formation` |
| `team_stats/` | 2024 only | 32 | 32 | none, but one season |
| `schedules/` (slim) | 2000-2026 | 17 | n/a | game-level training source for game_outcome / total_points |
| `player_stats/`, `retrain/player_stats/` | 2018-2024 / 2018-2025 (the latter carries `position` for 2025) | 17 | n/a | legacy slim copies |
| `weather/*.json` | 1,262 per-game files | | used | |
| `odds/`, `injuries/` dirs | EMPTY | | | **no odds-movement snapshots exist in the NFL cache.** Only one `spread_line`/`total_line`/moneyline per game inside `schedules` (closing lines: not allowed as features). |
| `tracking.db` | live pick tracker | | | evaluation only |

Production feature frame, reproduced today: `build_feature_frame(2017-2026)` -> **50,807 x 115** (rows per season 2017..2026: 5319, 5281, 5261,
5447, 5698, 5631, 5653, 5597, 5377, 1543). The quantile models fit on the 38 `FORWARD_FEATURE_COLUMNS`. Built into the frame but NOT in the 38:
`plays_roll`, `pass_share_roll`, `opp_plays_allowed_roll`, `opp_pressure_rate_roll`, `pressure_exposure`, `protection_time`, `gunslinger`,
`rz_carry_share`, `gtg_carry_share`, `route_participation`, `intended_air_yards_qb/recv`, `avg_time_to_throw`, `aggressiveness`,
`teammates_out_doubtful`. The frame also carries `spread_line`, `total_line`, `implied_team_total`, `game_total`: market lines, not eligible as features.

### CFB (`Kevocado/CFB_Predictor`)

| Dataset | Seasons | Content | Used | UNUSED |
|---|---|---|---|---|
| `data/cfbd/advanced_YYYY.json` (committed; 12 API calls) | 2014-2025 (25,754 team-game rows) | per side: overall + passing/rushing plays + passing-downs/standard-downs blocks of {ppa, successRate, explosiveness, totalPPA}; `lineYards`, `secondLevelYards`, `openFieldYards`, `stuffRate`, `powerSuccess`, `drives`, `plays` | 4 fields (`ppa`, `passingPlays.ppa`, `rushingPlays.ppa`, `successRate`), only inside the `epa` block, which is NOT in `DEFAULT_BLOCKS`: **used by no shipped model** | explosiveness, down-type splits, line yards, stuff rate, power success, open field, plays/drives (pace) |
| cache `games/` | 2000-2026 | 14 cols (scores, conference, division, `neutral_site`) | game_outcome, total_points | `neutral_site` |
| cache `player_stats/` | 2018-2026 | 15 cols; positions QB/RB/WR only | props (6 rolling features only) | no opponent, home/away or team context at all |
| cache `rosters/`, `sportsbook/` | 2025-26 / 88 event JSONs | | serving | no history |
| SP+, returning production, recruiting | NOT on disk, not committed | | | cannot be tested (brief limits these to committed data) |

## 2. Models ranked worst-first

Protocol: the repos' own walk-forward (each held-out season scored by a model trained on earlier seasons only); skill = naive error minus model
error, positive is better; CI = paired bootstrap over rows (2,000 resamples, seed 0). % = skill / naive error. "Naive" is stated per row.
No historical prop lines exist, so no skill is measured against the market except the game-level Vegas comparison.

| # | Model | Metric | Model | Naive baseline | Skill [95% CI] | % | Window | Re-ran / read |
|---|---|---|---|---|---|---|---|---|
| 1 | **CFB QB passing yards** (XGB point) | MAE | 50.830 | 50.005 (own roll-5 mean) | **-0.690 [-1.003, -0.354]** | -1.4% | val 2021-25, N=29,865 | RE-RAN `cfb_props_eval.py` |
| 2 | NFL receptions ZINB, WR/TE | MAE of mu | 1.511 | 1.499 (roll-5) | **-0.012 [-0.023, -0.002]** | -0.8% | val 2022-24, N=9,511; MSE skill +0.036 [-0.012, +0.082] (not distinguishable from 0) | RE-RAN `rec_eval.py`; the committed gate only checks calibration at its own line |
| 3 | CFB rushing yards | MAE | 26.316 | 26.951 (roll-5) | **-0.062 [-0.172, +0.050]** | -0.2% | val 2021-25, N=45,586 | RE-RAN |
| 4 | CFB receiving yards | MAE | 22.079 | 22.959 | +0.422 [+0.352, +0.487] | 1.8% | 2021-25, N=84,400 | RE-RAN |
| 5 | NFL total points (ridge) | MAE | 10.874 | 11.098 (train mean) | +0.225 [+0.161, +0.289] | 2.0% | val 2002-25, N=6,499 | RE-RAN `game_eval.py` |
| 6 | NFL passing yards (q50) | MAE | 69.327 | 70.699 (roll-5) | +1.750 [+0.835, +2.645] | 2.5% | val 2019-24, N=4,023 | RE-RAN `player_eval.py`; production script gives 69.40 (READ in manifest) |
| 7 | CFB total points (ridge) | MAE | 13.556 | 14.182 (train mean) | +0.626 [+0.537, +0.714] | 4.4% | val 2016-25, N=7,560 | RE-RAN |
| 8 | NFL rushing yards (q50) | MAE | 21.244 | 22.524 | +1.103 [+0.856, +1.367] | 4.9% | 2019-24, N=8,407 | RE-RAN |
| 9 | NFL QB rushing yards (q50) | MAE | 11.308 | 11.923 | +0.588 [+0.376, +0.787] | 4.9% | 2019-24, N=4,023 | RE-RAN |
| 10 | NFL anytime TD (XGB, 14 feats, QB/RB/WR/TE) | log loss | 0.4817 | 0.5096 (position base rate) | +0.0279 [+0.0256, +0.0304] | 5.5% | val 2019-24, N=32,411; AUC 0.678 vs 0.566 | RE-RAN `td_eval.py` |
| 11 | CFB anytime TD | log loss | 0.5074 | 0.5380 | +0.0305 [+0.0293, +0.0318] | 5.7% | 2021-25, N=159,851 | RE-RAN |
| 12 | NFL receiving yards (q50) | MAE | 20.952 | 22.431 | +1.332 [+1.180, +1.483] | 5.9% | 2019-24, N=19,981 | RE-RAN |
| 13 | NFL QB passing TDs (Poisson, 4 feats) | NLL | 1.3868 | 1.4768 (train mean) | +0.0900 [+0.0773, +0.1029] | 6.1% | 2019-24, N=3,944 | RE-RAN |
| 14 | NFL game outcome (ridge) | Brier | 0.2213 | 0.2462 (home-win rate) | +0.0249 [+0.0216, +0.0281] | 10.1% | 2002-25, N=6,499 | RE-RAN (log loss skill +0.0531 [+0.0460, +0.0602]; margin MAE 10.596 vs 11.313, +0.717 [+0.590, +0.847]) |
| 15 | CFB game outcome | Brier | 0.1896 | 0.2435 | +0.0539 [+0.0500, +0.0583] | 22.1% | 2016-25, N=7,560 | RE-RAN (margin MAE 13.352 vs 16.297) |
| - | CFB QB passing TDs | | in-sample log loss only (NB 1.2459 vs Poisson 1.2510, READ `models/manifest.json`) | | no walk-forward exists | | | NOT MEASURED |

Sorted by the point estimate of %, worst first. Ranks 1-3 are at or below the naive baseline. The ZINB gate (calibration at its own model line, 3 buckets, worst gap 0.037) was re-run and PASSES; the gate does not test skill.

Context checks:
- **NFL model vs the market (context only, spread/total are never features):** model margin MAE minus Vegas-spread MAE = **+0.347 [+0.272, +0.423]**
  (model worse), model total MAE minus Vegas-total MAE = **+0.312 [+0.232, +0.395]**, N=6,499. `game_base.log`.
- **NFL passing yards by season** (production script, 19 quantiles, READ from today's `run_quantile.log`): q50 MAE vs naive 2019 72.83 vs 72.02
  (**loses**), 2020 71.58 vs 72.14, 2021 69.88 vs 71.41, 2022 65.67 vs 68.03, 2023 68.53 vs 70.27, 2024 67.93 vs 70.53; 5 of 6 beat naive.
  Rushing, receiving and QB rushing beat naive in all 6 seasons.
- **Production calibration gate re-run today (exogenous line):** PASS, worst bucket gap 0.027 (0.4-0.5, n=4,008). The non-binding own-median
  diagnostic still MISSes in the upper tail (0.9-1.0 bucket gap 0.306, n=703).
- READ, `NFL_Predictor/docs/nfl_block_eval_results.md` / `output/block_eval_overall.txt` (not re-run): NFL blocks all "Clears: No": epa MAE delta
  -0.0506 [-0.0928, -0.0066]; qb +0.0726 [+0.0198, +0.1256] (Brier +0.0034 [+0.0020, +0.0047] but gap does not narrow); conditions -0.0150.
- READ, `CFB_Predictor/output/cfb_block_eval.txt` (not re-run; my baseline reproduces its N=7560): epa MAE delta +0.0042 [-0.0533, +0.0611]; priors Brier -0.00003
  [-0.00022, +0.00015], AUC delta -0.00027 [-0.00075, +0.00018], gap 0.02568 -> 0.02950: does not ship.

### 2b. Finding: NFL 2025/2026 rows have no position on this cache

`position` is null for 100% of 2025 (5,377 rows) and 2026 (1,543 rows) and 0% for 2017-2024. Cause: `season_pull.fill_positions` reads
`rosters["position"]`, but the 2025/2026 `rosters_YYYY.parquet` files are the new nflverse weekly-roster schema (`pos_abb`, `pos_slot`, no `position`),
so the fill returns the frame unchanged. Every market filters by `position`, so 2025-26 rows are dropped from every quantile market's training and
scoring. Today's production run prints `scored 36434 rows ... seasons [2019..2025]`, but its MAE table has no 2025 rows; the manifest's
`trained_seasons: 2017-2026` is true of the frame, not of the rows the models see. (Unverified: whether the VPS cache has the same schema. The
manifest MAE for passing yards, 69.40, matches my 2019-2024 reproduction, 69.33, which is consistent with it.)

Restoring positions from `pos_abb` (QB/RB/WR/TE only; `FIXPOS=1 player_eval.py`) lets 2025 be a true held-out season for the first time (train 2017-2024):

| Market | 2025 MAE | 2025 naive | 2025 skill | 2019-24 range of per-season skill |
|---|---|---|---|---|
| passing_yards | 74.80 | 72.51 | **-1.02 (loses)** | +0.33 to +2.68 |
| rushing_yards | 22.22 | 22.49 | +0.15 | +0.66 to +1.42 |
| receiving_yards | 19.74 | 20.97 | +1.08 | +1.05 to +1.48 |
| qb_rushing_yards | 10.93 | 11.60 | +0.52 | +0.13 to +0.98 |

The 2025 passing-yards result is one season (N about 660) so it is a warning, not a verdict.

### 2c. Receptions ZINB

The committed gate scores P(over) at the model's **own** line (`model_line(mu)`), so a model that is merely unbiased passes. It does not show skill vs naive.
Measured (`rec_eval.py`, walk-forward 2022-24, mu vs the player's roll-5 receptions): WR/TE N=9,511, MAE 1.511 vs 1.499, skill -0.012 [-0.023, -0.002]; MSE 4.000 vs
4.035, skill +0.036 [-0.012, +0.082]. RB (not served; the gate fails there): N=3,983, MAE 1.238 vs 1.241 (+0.004 [-0.012, +0.019]), MSE skill +0.162 [+0.104, +0.224]. So the ZINB's mean is
indistinguishable from a rolling average for WR/TE; the model's value would be in the distribution (P(over)), which this check does not test.

## 3. Proposed features for the weakest models (derivable from data on disk)

Common leakage rule used for every feature below: a value for team-game g is an aggregate over that team's previous N games only (`shift(1)` before the
rolling mean, carrying across seasons), or a pre-kickoff status published for week g. Nothing from game g's own plays, score or closing line.
Files that would change are in the repos (nothing was changed).

### NFL

**N1. NFL passing yards (also feeds rushing/receiving)**
- *Opponent-adjusted efficiency*: for QB row in game g, `opp_def_pass_epa_roll` = opponent's mean EPA/dropback allowed over its previous 6 games; `opp_def_rush_epa_roll`
  the same on runs; own `off_pass_epa_roll`, `off_rush_epa_roll`. Derived from `pbp_YYYY` (`epa`, `qb_dropback`, `rush`, `posteam`, `defteam`).
  Leakage check: games strictly before g (`shift(1)`), regular+post season ordered by (season, week); verified with `assets/new_features.py`.
- *Neutral-script pass rate*: `off_neutral_pass_rate_roll` = team pass share on 1st/2nd down, win probability 0.2-0.8, quarters 1-3 over previous 6 games;
  plus `off_rz_pass_rate_roll` (pass share inside the 20). Uses `wp`, `down`, `qtr`, `yardline_100` (all unused columns).
- Files: `scripts/train_quantile_props.py::build_feature_frame` (merge a team-week table), `src/nfl_predictor/models/training.py::FORWARD_FEATURE_COLUMNS`,
  `src/nfl_predictor/features/interactions.py::add_pbp_features` (natural home), serving path `tracking/forward_tick.py`.

**N2. NFL total points**
- *Pace*: `off_plays_roll`, `def_plays_roll` (plays per game, previous 6).
- *Referee scoring tendency*: `ref_total_dev` = referee's shrunk (n/(n+20)) lagged mean of (game total minus league mean to date); `schedules.referee` is unused.
- *Sack/pressure*: `off_sack_rate_roll`, `def_sack_rate_roll`, `def_qbhit_rate_roll`.
- *Opp-adjusted EPA* as in N1, at team level. Files: `src/nfl_predictor/features/build.py` (new block), `tools/block_eval.py`.
- Not tested: **injury-weighted lineup strength** (needs a per-position value model; the 2024-only depth chart limits it), **depth-chart role changes** (one season of
  charts), **odds movement** (no snapshots on disk), **matchup products** (the repo's `interactions.py` already has some).

**N3. NFL rushing / QB rushing yards (RB 4.9%, QB 4.9%)**
- Red-zone/goal-line shares (`rz_carry_share`, `gtg_carry_share`, already built), run-gap and `rush_yards_over_expected` from NGS rushing (unused), `practice_status`
  (DNP/limited, a pre-kickoff report).

### CFB

**C1. CFB QB passing yards and rushing yards**
- The prop model has six features and no context. Derivable: opponent defence EPA (pass/rush) from `data/cfbd`, own offence EPA, own and opponent pace
  (`plays`), home/neutral flag from `games/` (`neutral_site`, unused). Matching player rows to games on (season, week, team) covers 71.5% of rows.
- Zero-data fix: median objective (see 4b).
- Files: `src/cfb_predictor/models/player_props.py::fit_yardage_regressor`, `features/player_usage.py`.

**C2. CFB total points**
- Opponent-adjusted EPA: `adj_off_epa` = team offence EPA in a game minus the opponent's shrunk-EWM defence EPA before that game (and the mirror for defence), then the
  repo's own shrunk EWM (half-life 6, k=4) lagged one game. Pace (`plays`, `drives`), situational success (standard/passing-downs success rate).
- Files: `src/cfb_predictor/features/epa.py`, `features/build.py` (total model only), `data/cfbd_advanced.py::_side` (extra fields).

## 4. Tests

Harnesses: NFL player markets = `evaluate/walk_forward.walk_forward_quantile` (XGBoost quantile, same `_TREE_PARAMS`) with 11 quantiles
(0.05..0.95) instead of 19 for speed, identical for base and candidate; NFL game level = `evaluate/walk_forward.prepare_folds` + ridge + the repo's `paired_bootstrap`;
CFB game level = `tools/block_eval` machinery; CFB props = `fit_yardage_regressor` / `fit_anytime_td_classifier` walk-forward. Calibration gap definitions:
quantile markets = max 10-bin |predicted - empirical| of P(over) at the repo's exogenous line (n>=100 bins), change CI by 300 row-bootstraps; NFL/CFB win probability = `block_eval.calibration_gap` (5 buckets);
totals and CFB point props = max |mean bias| per predicted-total quintile (pts) or max |P(actual > pred) - 0.5| per quintile. These last two are my definitions, because those models emit no probability.
Each candidate is compared to the base on identical rows. **"Ships" requires primary CI lower bound > 0 and gap-change CI upper bound <= 0.**

### 4a. NFL quantile markets, 8 feature sets x 4 markets (`player_eval.py`, 2019-2024 effective; Delta MAE positive = better)

Sets: *pace_script_existing* (`plays_roll`, `pass_share_roll`, `opp_plays_allowed_roll`), *pressure_existing* (`opp_pressure_rate_roll`, `pressure_exposure`, `protection_time`),
*redzone_existing* (`rz_carry_share`, `gtg_carry_share`), *ngs_qb_existing* (`avg_time_to_throw`, `intended_air_yards_qb/recv`, `aggressiveness`, `route_participation`),
*opp_epa_new*, *sack_rate_new*, *neutral_script_new*, *practice_status_new* (definitions in Section 3).

| Market (base MAE / naive) | Set | Delta MAE [95% CI] | Gap base -> cand | Gap-change 95% CI | Verdict |
|---|---|---|---|---|---|
| passing_yards (69.327 / 70.699) | **opp_epa_new** | **+1.043 [+0.421, +1.713]** | 0.048 -> 0.034 | [-0.035, +0.020] | does not ship (gap CI unresolved); lead; better in 6/6 seasons |
| passing_yards | **neutral_script_new** | **+0.444 [+0.104, +0.814]** | 0.048 -> 0.032 | [-0.038, +0.030] | does not ship; lead; 5/6 seasons |
| passing_yards | pace_script_existing | +0.229 [-0.060, +0.508] | 0.048 -> 0.048 | [-0.028, +0.023] | does not ship |
| passing_yards | pressure_existing | +0.096 [-0.086, +0.277] | 0.048 -> 0.060 | [-0.016, +0.034] | does not ship |
| passing_yards | redzone_existing | +0.105 [-0.031, +0.243] | 0.048 -> 0.065 | [-0.013, +0.034] | does not ship |
| passing_yards | ngs_qb_existing | -0.090 [-0.451, +0.283] | 0.048 -> 0.085 | [-0.011, +0.068] | does not ship |
| passing_yards | sack_rate_new | +0.159 [-0.203, +0.535] | 0.048 -> 0.049 | [-0.028, +0.040] | does not ship |
| passing_yards | practice_status_new | +0.000 [0, 0] | 0.048 -> 0.056 | [-0.008, +0.017] | no effect (non-zero for about 2% of QB rows) |
| rushing_yards (21.244 / 22.524) | pace_script / pressure / redzone / ngs | -0.004 / -0.006 / -0.003 / +0.011 (all CIs include 0) | | | does not ship |
| rushing_yards | opp_epa_new | -0.043 [-0.080, -0.005] | 0.053 -> 0.059 | [-0.011, +0.023] | hurts |
| rushing_yards | sack_rate_new / neutral_script_new / practice_status_new | -0.019 / -0.026 / -0.003 (CIs include 0) | | | does not ship |
| receiving_yards (20.952 / 22.431) | pace / redzone / opp_epa / neutral / practice | +0.011 / +0.000 / +0.005 / +0.010 / +0.005 (CIs include 0) | | | does not ship |
| receiving_yards | ngs_qb_existing | -0.045 [-0.074, -0.016] | | | hurts |
| receiving_yards | sack_rate_new | -0.020 [-0.039, -0.002] | | | hurts |
| qb_rushing_yards (11.308 / 11.923) | all 8 sets | between -0.041 and +0.037, every CI includes 0 | | | does not ship |

**Replication with 2025 as a true holdout (positions restored, `FIXPOS=1`, 2019-2025):** passing_yards base 70.102 vs naive 70.956 (+1.357 [+0.473, +2.297]);
opp_epa_new +1.472 [+0.849, +2.068], gap 0.055 -> 0.046 [-0.039, +0.023]; neutral_script_new +0.831 [+0.444, +1.227], gap 0.055 -> 0.043 [-0.049, +0.029].
2025 alone: +4.07 and +3.18 yds (base loses to naive by 1.02). Other markets unchanged in verdict (rushing opp_epa -0.029 [-0.068, +0.009]; receiving neutral_script
+0.025 [+0.004, +0.046] with gap 0.056 -> 0.041 [-0.023, +0.002]: statistically positive but 0.1% of MAE, not worth a feature).

Why passing yards cannot clear the gap half at this sample: 4,023-4,687 QB rows spread over 10 bins; the bootstrap CI of a max-bucket gap is about +/-0.03 wide, larger than the
0.014 point-estimate improvement. A confirmation needs either the forward test accumulating more QB games or a smoother gap statistic.
Multiple testing: 32 (set, market) tests; two passing-yards sets clearing the MAE half at 95% is more than chance (about 0.8 expected false positives
across 32 at a two-sided 95% CI, but both are in one market, the one with the largest signal, and both hold in the 2025 holdout).

### 4b. CFB prop regressors (`cfb_props_eval.py`; val 2021-2025; N passing 29,865, rushing 45,586, receiving 84,400)

| Market | Change | Delta MAE [95% CI] | Median-coverage gap base -> cand [change CI] | Seasons better | vs naive roll-5 after change | Verdict |
|---|---|---|---|---|---|---|
| passing_yards | **objective -> absolute error (no new data)** | **+2.927 [+2.743, +3.112]** | 0.396 -> 0.396 [-0.010, +0.012] | 5/5 | +1.397 (was -0.690) | MAE clears; gap change CI upper bound +0.012 > 0, so strictly does not ship on the bar (MAE lead only) |
| passing_yards | 50/50 blend with roll-5 | +1.207 [+1.056, +1.354] | 0.396 -> 0.396 [+0.000, +0.001] | 5/5 | +0.626 | gap not narrowed |
| passing_yards | venue (is_home, neutral) | +0.148 [+0.112, +0.181] | 0.396 -> 0.381 [-0.021, -0.004] | 5/5 | -0.583 | ships (but 0.3% of MAE) |
| passing_yards | pace (own plays, opp plays allowed) | +0.127 [+0.060, +0.193] | 0.396 -> 0.330 [-0.074, -0.048] | 5/5 | -0.596 | ships (0.25%) |
| passing_yards | opp defence EPA / opp defence structure | -0.111 [-0.168, -0.051] / -0.188 [-0.235, -0.141] | | 2/5 / 0/5 | | hurts |
| rushing_yards | **objective -> absolute error** | **+1.394 [+1.311, +1.483]** | **0.203 -> 0.025 [-0.189, -0.169]** | 5/5 | +1.248 (was -0.062) | **ships** |
| rushing_yards | pace / venue | +0.134 [+0.104, +0.165] / +0.107 [+0.091, +0.124] | 0.203 -> 0.192 [-0.018, -0.006] / 0.194 [-0.016, -0.003] | 4/5 / 5/5 | | ships (0.5%) |
| rushing_yards | opp defence EPA / structure | -0.076 / -0.113 | | 1/5 | | hurts |
| receiving_yards | **objective -> absolute error** | **+1.139 [+1.090, +1.191]** | **0.175 -> 0.026 [-0.155, -0.142]** | 5/5 | +1.453 (was +0.422) | **ships** |
| receiving_yards | pace / venue | +0.068 [+0.061, +0.076] / +0.036 [+0.031, +0.041] | change CIs [-0.002, +0.004] / [-0.003, +0.002] | 5/5 | | MAE only; does not ship |
| receiving_yards | opp defence EPA / structure | -0.031 / -0.060 | | | | hurts |
| anytime_td | opp defence EPA | log loss +0.0017 [+0.0014, +0.0021] (0.3%) | not measured | | | cannot ship (no gap measured) |
| anytime_td | own offence EPA / pace / venue | +0.0011 / +0.0003 / +0.0004 (CIs above 0, tiny) | not measured | | | cannot ship |

Interpretation: the absolute-error objective is the large lever and uses no new data; the team-context features are real but 0.2-0.5% of MAE.
Opponent-defence features hurt the yardage regressors (the opponent signal is noisy at 6 features and 71.5% match coverage; unmatched rows were zero-filled).
Caveats: validated against the player's roll-5 mean and realised yards, not against book lines (none on disk); the QB population includes backups with near-zero
yards (hence the 0.396 passing gap in every row); not integrated into serving.

### 4c. CFB game-level blocks (`cfb_eval.py`, ridge, val 2016-2025, N=7,560)

| Set (unused CFBD field) | Brier delta [CI] | AUC delta [CI] | Win-prob gap base -> block (per-fold change CI) | Verdict |
|---|---|---|---|---|
| explosiveness | +0.00003 [-0.00027, +0.00033] | -0.00017 [-0.00094, +0.00057] | 0.0257 -> 0.0238 | does not ship |
| run_structure (line yards, stuff, power) | +0.00009 [-0.00063, +0.00078] | +0.00073 | 0.0257 -> 0.0293 | does not ship |
| pace (plays, drives) | -0.00021 [-0.00051, +0.00011] | -0.00022 | 0.0257 -> 0.0330 | does not ship |
| situational success (std/passing downs) | 0.00000 [-0.00082, +0.00082] | +0.00045 | 0.0257 -> 0.0386 | does not ship |
| opp-adjusted EPA | +0.00091 [-0.00002, +0.00189] | +0.00234 [-0.00003, +0.00467] | 0.0257 -> 0.0486 | does not ship |
| **neutral_site** (`games/`, one column) | **+0.00090 [+0.00039, +0.00138]** | **+0.00232 [+0.00099, +0.00363]** | 0.0257 -> 0.0259 (per-fold CI [-0.0002, +0.0176]) | Brier and AUC clear; gap flat but strict gap CI lower bound is -0.0002: **borderline, does not strictly ship** |

### 4d. CFB total points (`cfb_totals.py`; same folds; gap = max per-quintile |bias| in points; base 13.556 MAE, gap 1.847)

| Set | Delta MAE [95% CI] | Gap base -> cand (pts) | Gap-change 95% CI | Seasons better | Verdict |
|---|---|---|---|---|---|
| **opp-adjusted EPA** (4 cols) | **+0.158 [+0.091, +0.227]** | 1.847 -> 0.506 | **[-1.948, -0.180]** | 8/10 | **ships** (1.2% of MAE) |
| situational success | +0.159 [+0.082, +0.236] | 1.847 -> 0.875 | [-1.816, +0.143] | | MAE clears; gap CI includes widening: does not ship |
| pace | +0.135 [+0.050, +0.220] | 1.847 -> 1.603 | [-1.121, +0.791] | | does not ship |
| union of the three | +0.187 [+0.075, +0.300] | 1.847 -> 3.292 | [+0.212, +2.535] (widens) | | does not ship |
| explosiveness (from 4c) | -0.111 [-0.167, -0.054] | | | | hurts |

The only candidate that is both statistically positive and calibration-safe by the bar is opp-adjusted EPA for the CFB total model. It is the one winner out of
9 CFB sets tested for totals/win-prob, so treat the 95% CI with a multiplicity discount; it has no untouched holdout (all seasons were used).

### 4e. NFL game-level blocks (`game_eval2.py`; train 2017+, val 2019-2025, N=1,960; base Brier 0.2225 vs naive 0.2496, total MAE 10.818 vs 10.995, +0.177 [+0.054, +0.303])

| Set | Primary metric | Delta [95% CI] | Verdict |
|---|---|---|---|
| opp-adjusted EPA (pass/rush, 6-game) | Brier | -0.0008 [-0.0025, +0.0008] | does not ship |
| pace | total MAE | -0.014 [-0.071, +0.043] | does not ship |
| sack / pressure rates | Brier | -0.0017 [-0.0036, +0.0003] | does not ship |
| neutral-script pass rate | total MAE | -0.048 [-0.126, +0.035] | does not ship |
| referee total deviation | total MAE | -0.005 [-0.019, +0.009] | does not ship |

The NFL game-level model absorbs nothing from these; consistent with the READ block_eval results.

## 5. Recommendations (value vs effort)

| # | Action | Value | Effort | Evidence |
|---|---|---|---|---|
| 1 | CFB `fit_yardage_regressor`: `objective="reg:absoluteerror"`, retrain props, re-run the gate | High (two losing markets become winners) | 1 line + retrain | 4b |
| 2 | NFL: fix the 2025/2026 position fill (use `pos_abb` or `retrain/player_stats/`), then re-run the quantile gate with 2025 scored | High (adds the current season to training and to the gate; exposes the 2025 passing-yards loss) | Low | 2b |
| 3 | NFL passing yards: add `opp_epa_new` (and maybe `neutral_script_new`) derived from pbp; judge on the forward test, not this walk-forward | Medium (about +1 yd, 1.5%), the only lead on the weakest market | Medium (team-week table + serving path) | 4a |
| 4 | CFB total-points model: add the 4 opp-adjusted EPA columns (total model only) | Low-medium (0.16 pts of 13.6) | Low | 4d |
| 5 | CFB game model: `neutral_site` | Low (Brier +0.0009) | Trivial | 4c |
| 6 | Do NOT spend time on: NFL pressure / red-zone / NGS / practice-status, NFL game-level EPA/pace/referee, CFB explosiveness / run structure / situational success for win-prob | | | 4a, 4c, 4e |
| 7 | Add a real skill check to the receptions gate (vs naive and at an exogenous line); today it only checks calibration at its own line | Medium | Low | 2c |

## 6. Commands (exact)

All run from fresh clones in `$S/r/` with caches copied to `$S/w/{nfl,cfb}/cache` and symlinked to `data/cache`; Python = the NFL venv (`pyarrow 18`). `W` = the assets dir.
`cfbd` is not installed in that venv, so CFB runs put a one-line empty stub package on `PYTHONPATH` (`stubs/cfbd/__init__.py`); no CFBD API call was made and no network access was used.

| Number | Command |
|---|---|
| NFL frame 50,807 x 115, production MAE table, calibration gate, receptions gate | `cd NFL_Predictor && PYTHONPATH=src python scripts/train_quantile_props.py --seasons 2017-2026 --validate 2019-2025 --out-dir $S/w/nfl/cache/nflverse --dump-feature-frame $S/w/nfl/frame.parquet` (log `assets/nfl/run_quantile.log`, 65 min) |
| Inventory | `python cols.py NFL_Predictor/src pbp=... weekly=... ...` and `python inv.py <cache>` |
| New team features | `python new_features.py` (from `$S/w`) |
| NFL game/total baselines and Vegas context | `cd NFL_Predictor && PYTHONPATH=src python game_eval.py` (`assets/nfl/game_base.log`) |
| NFL quantile base skill and sets 4a | `PYTHONPATH=src python player_eval.py <market>` for the four markets (`assets/nfl/pe_*.log`, JSON in `assets/nfl/res/`) |
| 2025 holdout / replication | `FIXPOS=1 PYTHONPATH=src python player_eval.py <market> opp_epa_new,neutral_script_new` (`pefix_*.log`) |
| NFL anytime TD, QB passing TDs | `PYTHONPATH=src python td_eval.py` (`td_eval.log`) |
| NFL game-level blocks 4e | `PYTHONPATH=src python game_eval2.py opp_adj_epa,pace,sack_pressure,neutral_script,referee_total_dev` (`ge2.log`) |
| CFB baseline and 4c | `cd CFB_Predictor && PYTHONPATH=src:stubs python cfb_eval.py explosiveness,run_structure,pace,situational_success,opp_adj_epa,neutral_site res` |
| CFB totals 4d | `PYTHONPATH=src:stubs python cfb_totals.py` |
| CFB props 4b, anytime TD | `PYTHONPATH=src:stubs python cfb_props_eval.py` |
| Receptions skill | `PYTHONPATH=src python rec_eval.py` |

## 7. What I could not measure / caveats

- No historical prop lines or odds snapshots exist on disk, so nothing is a profitability or edge-vs-market claim. Skill is vs a naive baseline; the one market comparison (NFL margin/total vs Vegas) is game-level.
- Odds movement, SP+, returning production, recruiting: not on disk / not committed; not tested. Injury-weighted lineup strength and depth-chart role changes: not tested (depth charts exist for 2024 only; no value model built).
- CFB QB passing TDs: no walk-forward exists and I did not build one. CFB anytime-TD feature tests have no calibration measurement.
- NFL quantile tests use 11 quantiles, not the production 19; base MAE reproduces the production figure to 0.07 yds (69.33 vs 69.40), the paired comparison is like-for-like, but a final decision should be re-run with 19.
- The calibration-gap bootstraps for max-bucket statistics are noisy (about +/-0.03 on 4-5k rows); the "gap-change CI upper <= 0" half of the bar is hard to clear for QB markets whatever the feature. Totals and CFB-prop gap definitions are mine.
- CFB team features cover 71.5% of player rows (team-name/week matching); the rest were zero-filled, which understates the context features and probably explains the opponent-defence features hurting.
- No untouched holdout: every season was used for model selection in these tests (NFL: 2025 only for the position-restored replication). About 80 tests were run in total; treat single 95% CIs with that in mind.
- The NFL position finding is from this cache; whether the VPS cache has the same schema is unverified.
- Receptions ZINB: only the mean was checked against naive (2c); its P(over) skill is unmeasured.
