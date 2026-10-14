# NBA model gaps: which models are weakest, and what the data on disk could add

Date 2026-10-13. Research only: nothing here merges or deploys. 

## One-screen summary

**Question:** which NBA models are worst, and can the data we already have improve them?

**Worst first (all re-run 2026-10-13 on a cache rebuilt from the ESPN files, n = 765 out-of-fold games, one season):**

1. **Total (O/U) model**: MAE 16.55, worse than a constant (training mean 16.37; fixed 230.2 gives 16.22, skill -2.0% [-3.5, -0.6]; season-to-date team totals 16.06, skill -3.1% [-5.0, -1.2]).
2. **Player props, all four markets**: the XGBoost projection is worse than the player's own trailing-10 mean it is built from: threes -1.8% [-2.2, -1.3], points -0.8% [-1.1, -0.4], rebounds -0.6% [-1.0, -0.3], assists -0.3% [-0.7, +0.1] (not distinguishable). It does beat the league mean by 21 to 32%, so it is not broken, just no better than "what he averaged lately".
3. **Win model**: beats the home-win-rate baseline (+3.8% log-loss skill [+1.8, +5.7]) but a plain Elo rating beats it by 0.063 log-loss [0.036, 0.089]. Cause: 5 of its 22 columns, including all three power-rating columns, are constant zero, so the model has no idea how good a team is.
4. **Margin/spread**: the only clearly healthy model (+5.7% MAE skill [+3.8, +7.5] over the training mean).

**Can they improve with data on disk? Yes, a lot, with the box scores we already have:**

* Team model: adding causal Elo + opponent-adjusted ratings + rolling pace/efficiency + a lagged-availability proxy (arm HF) improves all five repo metrics with intervals excluding zero: win log-loss 0.6612 -> 0.5782, AUC 0.632 -> 0.754, margin MAE 13.22 -> 11.79, total MAE 16.55 -> 15.29. It passes `ship_decision` as written (gap 0.0578 -> 0.0550). **Caveat that matters:** I designed that combination after looking at ~15 arms on these same games, and the calibration clause is noise-dominated at n = 765, so this says "worth a confirmed ship PR", not "ship". Beats the baseline in every one of four test slices.
* Props: a ridge on game context + matchup features beats the trailing mean for points (-1.4% [-1.7, -1.1]), rebounds (-0.8%), assists (-1.2%) and beats the incumbent XGBoost by 1.3 to 2.1%. For threes the best option needs no model: trailing 3PM-per-minute x minutes is 1.1% better than the trailing mean [0.7, 1.6].
* **Does not help**: rest-by-team, cleaned rest/schedule density, travel/fatigue (measurably harmful after the two bug fixes: AUC -0.0303 [-0.0547, -0.0053]), tip-off-hour rest (hurts the total). No ship.

**Not measurable here:** anything versus the market (no odds on disk), multi-season behaviour (one season only), injury-feed-based availability (single snapshot). The live pre-tip record (5/10, 5/10, 6/10) is n = 10 per market, Wilson 95% intervals about [0.24, 0.76]; it says nothing about skill either way.

Nothing is merged or deployed by this PR; it adds this document and the scripts and logs that produced every number.

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

1. **Five of the 22 default `FEATURE_COLUMNS` have zero variance in the rebuilt training frame**: `home_power_rating`, `away_power_rating`, `power_rating_diff`, `home_missing_value`, `away_missing_value` (std 0.000; they are zero-filled by `_OPTIONAL_COLUMNS_DEFAULT_ZERO` because the ingest never supplies them). The served models carry 5 dead columns, and the parity doc's "Elo beats every ML candidate" is plausibly explained by this (my inference, supported by section 4): the win model has no strength rating at all, only 10-game four-factor means, rest, streak.
2. **The team model's whole view of team quality is the four factors over the last 10 games.** Points scored/allowed, margin, pace, opponent strength and schedule strength are not in it.
3. `home_rest_days` has std 9.9: first-in-role games read 99 (and the offseason/preseason gap is unclipped), so the linear models (ridge/logistic) get a few 99-valued rows that dominate the coefficient. Rest is a calendar-day count from the same-role last game by default.
4. Local data = one season (2025-26 incl. preseason). The multi-season frame (4,149 games) used by `tools/compare_margin_average.py` is NOT on this machine; the box scores for earlier seasons would need the free ESPN pull (`pipeline/backfill.py`), which I did not run.

## How the cache was rebuilt

`data/cache/training/games.json` is gitignored. I rebuilt it offline (no network) from the copied ESPN caches: read every `scoreboard_<date>.json`, joined each completed game to its cached `boxscore_<id>.json` through the repo's own `ingest.enrich_with_boxscores` + `ingest.to_training_frame` (network call patched to raise), and wrote the result. Result: 1,387 games, 2025-10-02 to 2026-06-13, one season including preseason. Player frame: `ingest.to_player_training_frame` over the cached `player_boxscore_*.json` (30,613 player-games; I added `fg3a`, `ftm`, `fta` by re-parsing the same strings). No free one-off pull was made. The earlier seasons (the 4,149-game multi-season frame) are NOT on disk, so `history_df` is empty in every run below; a multi-season rerun needs the free keyless ESPN backfill (`python -m nba_predictor.pipeline.backfill`), roughly 6,000 box-score requests, not done here.

After `build_training_frame` drops rows with NaN rolling features the frame has 1,365 games. Walk-forward = the repo's `expanding_windows(dates, 4)`: first 40% of dates train only (through 2026-01-08), then date-aligned test windows (the `windows=4` argument yields 5 slices of 246, 258, 206, 53 and 2 games because of integer division), pooled out-of-fold **n = 765 games**, test dates 2026-01-09 to 2026-06-13. Phase A reported n=758 on a 1,390-game cache; ours is 1,387/1,365 games, so numbers differ in the third decimal (baseline win log-loss 0.6612 here, 0.6636 there).

## 2. Models ranked by weakness

All numbers in this section were **re-run by me on 2026-10-13** on the rebuilt cache, scripts in the appendix (`step2_teams.py`, `step2_props.py`). Paired bootstrap, 2,000 resamples, seed 20261009 (the seed of the repo's compare tools); props resample whole games (rows in a game share a game script), the team metrics resample games as the repo does. "Skill" = (naive - model) / naive, positive = model better; the bracket is the 95% interval of that skill, derived from the paired bootstrap of the metric difference. The naive for each model is leak-free: computed from each window's TRAINING slice (or from games strictly before the game, for the trailing-form baselines).

| rank (worst first) | model | metric | model | best naive baseline | skill vs that baseline [95% CI] | verdict |
|---|---|---|---|---|---|---|
| 1 | **total** (ridge) | MAE | 16.549 | season-to-date team totals avg 16.055 (also: training mean 16.369, fixed 230.174 -> 16.224) | **-3.07% [-4.95, -1.16]** (vs training mean -1.10% [-2.35, +0.20]) | loses to every naive; CI excludes zero against 3 of 4 |
| 2 | **threes prop** (xgb) | MAE | 0.9129 | player trailing-10 mean 0.8969 | **-1.78% [-2.24, -1.33]** | loses to its own input feature |
| 3 | **points prop** | MAE | 4.6743 | player trailing-10 mean 4.6386 | **-0.77% [-1.11, -0.43]** | loses |
| 4 | **rebounds prop** | MAE | 1.9419 | player trailing-10 mean 1.9303 | **-0.60% [-0.96, -0.26]** | loses |
| 5 | **assists prop** | MAE | 1.3782 | player trailing-10 mean 1.3737 | -0.33% [-0.72, +0.07] | not distinguishable from the trailing mean |
| 6 | **win** (logistic, race winner) | log-loss | 0.6612 | home win rate 0.6872 | +3.79% [+1.84, +5.72] | beats naive, **but loses to Elo (0.5984): logistic - Elo = +0.0628 [+0.0363, +0.0891]** |
| 6b | win as served (Phi(ridge margin / sigma 16.57)) | log-loss | 0.6566 | home win rate 0.6872 | +4.46% [+2.64, +6.26] | beats naive; max calibration gap 0.0645, **above the 0.0591 bar** |
| 7 | **margin / spread** (ridge) | MAE | 13.220 | training mean 14.011 | +5.65% [+3.83, +7.54] | beats naive; beats trailing-10 net margins (15.368) and season-to-date net margins (14.398) too |

Other numbers behind that table (all re-run, same command):

* Win AUC: logistic 0.6322 [0.594, 0.670]; served Phi(margin) 0.6464 [0.607, 0.687]; Elo reference 0.7418 [0.705, 0.776]; constant naive = 0.5 by definition. Calibration (5 buckets, max gap): logistic 0.0578, served 0.0645, Elo 0.1154, home-rate naive 0.0673.
* Margin MAE vs the old fixed +3.0: 13.220 vs 13.928, skill +5.09% [+3.20, +6.98].
* Total MAE vs training mean 16.369 diff +0.180 [-0.033, +0.384].
* Props, "played only (minutes>0)" variant (n=16,801 rows): same sign everywhere (points -0.69% [-1.03, -0.35], rebounds -0.51% [-0.86, -0.17], assists -0.28% [-0.67, +0.11], threes -1.72% [-2.17, -1.27]). Against the league mean every prop model wins by 21 to 32%, so the models are not broken, they just add nothing over the trailing mean they are built on. The "trailing per-minute rate x trailing minutes" baseline gives the same picture (points 4.6413, threes 0.8972).
* Prop sample: 29,965 feature rows after the first-game NaN drop, 628 players, 1,379 games; test windows 5,525 / 5,643 / 4,536 / 1,193 rows (the last window is the playoffs tail).
* **Spread cover, total over and moneyline-vs-market cannot be scored here**: there are no betting lines or odds history on disk (odds/ and sportsbook/ caches empty, tracking.db market tables 0 rows). No market-implied baseline exists, so "does the model beat the market" is unanswered. The cover and over probabilities are Phi((pred - line)/sigma) of the same margin/total models, so they inherit the margin skill (+5.65%) and the total's lack of any.
* Read, not re-run: the live manifest in `data/public_snapshot.json` (generated 2026-10-13T22:11Z, model v20261012203810, trained on 1,139 games, holdout 284): win log-loss 0.6824 / Brier 0.2444 / AUC 0.5809 (n=702), margin walk-forward MAE 12.74, total walk-forward MAE 16.56, residual sigma 15.97 and 20.76. Those use a different frame and window than my re-run; they point the same direction (win barely better than a coin flip at 0.6824 vs 0.6931, total at 16.56 is no better than a constant).
* Read, not re-run, and not verified by me (given in the task): the live counted pre-tip record as of 2026-10-12 was moneyline 5/10, spread 5/10, total 6/10. At n=10 the Wilson 95% intervals are [0.24, 0.76] for 5/10 and [0.31, 0.83] for 6/10, so this is consistent with any skill from none to large; it is not evidence for or against these models. The ~1,400 "winner pick" rows are mostly rebuilt after tip-off and are not evidence of skill; the local tracking.db backfill (predictions of 2026-09-18 12:02, scored after the games on the training rows) is the same kind of row.

**Ranking logic.** Worst = the one whose point estimate is furthest below the naive it should beat, with the interval excluding zero: total, then the four prop markets (threes worst), then the win model (positive over naive but dominated by a plain Elo), with margin the only clearly healthy model. "Can they improve with the data we have now" is the section 3/4 question: the total and the props lose to trivial baselines, so the first thing to try is not a new feature but shrinking the models toward the baseline (see section 3).

## 3. Feature proposals for the weakest models

The three weakest are the **total** (loses to every constant), the **threes prop** and the **points prop** (rebounds and assists are the same pipeline, so every prop proposal applies to all four). The win/margin pair is added because the ship rule scores win, margin and total together and because the biggest single gap found is that the win model has no strength rating at all (Elo beats it by 0.063 log-loss).

Common rules for every feature below: value for game G is computed from games strictly before G in `(game_date, game_id)` order and read BEFORE G's own result is folded into any state; same-night games involve disjoint teams, so a same-night game cannot enter another's state; nothing uses odds, post-tip data or the injury feed; first-game NaNs are filled with the league-to-date mean (expanding, lagged). The one known impurity: a team's very first game with NaN history on the very first date falls back to the full-sample mean (a handful of rows, flagged in the code, not material).

| id | feature | exact derivation | leakage check | files to change (NBA repo) |
|---|---|---|---|---|
| T1 | **Causal Elo** (fills the dead `home_power_rating`, `away_power_rating`, `power_rating_diff`) | ratings start 1500; per game record `R_home`, `R_away` first; `E = 1/(1+10^(-(R_h-R_a)/400))`; `R_h += 20*(win-E)`, `R_a -= 20*(win-E)`; feature `(R_h - R_a)/100`. MOV variant: K multiplied by `0.7*ln(|margin|+1)+0.5`, with a +50 home prior inside E | recorded before the update; verified by reading the order in `features` code; walk-forward test games use the rating as of their own date | new `features/power.py`; `features/build.py` (supply the power columns instead of the zero fill); `pipeline/ingest.py` + `api` serving must replay the same function over all completed games before tip. Note: `candidate_race.elo_probability_factory` uses `scale ** (-(d)/scale)` (base 400, not 10), a different, much steeper curve than standard Elo; it is only a reference but worth knowing when comparing to "Elo" numbers |
| T2 | **Pace and efficiency, rolling 10** | `poss = fga - oreb + tov + 0.44*fta` (the repo's `compute_possessions`); game possessions = mean of both teams'; `ortg = pts/poss*100`, `drtg = opp_pts/poss*100`, `pace = poss`; each shift(1).rolling(10).mean(). `exp_total = mean(pace_h,pace_a) * ((ortg_h+drtg_a)+(ortg_a+drtg_h)) / 200` | shift(1) per team; fed from `home_pts/away_pts` of prior games only | `features/ratings.py` already has the pieces; wire into `build.py` (this is the plan's `form` block) |
| T3 | **Opponent-adjusted offence/defence** | per team-game: `adj_off = ortg - opp's season-to-date mean drtg` and `adj_def = drtg - opp's season-to-date mean ortg` (opp's means taken BEFORE this game, league mean if none), then 10-game rolling mean; `adj_net_diff = (adj_off-adj_def)_home - (adj_off-adj_def)_away` | opponent state read before update | `features/` (plan's `adjusted` block) |
| T4 | **Availability proxy (lagged)** | rotation = a team's top 8 by season-to-date minutes before G; `absent_min_share` = rotation minutes belonging to players who did NOT play in the team's PREVIOUS game; `absent_prod_share` same weighted by `pts + 1.2*reb + 1.5*ast` | uses only the previous game's box score; needs no injury feed, so it is available in training, where the feed has no history | `features/availability.py` (does not exist; audit followup 4(a)); at serve time replace/augment with the injury feed (`espn.get_injuries`), which cannot be back-tested here |
| T5 | **Rest/schedule done properly** | (a) the repo's `rest_by_team=True` (rest from the team's last game in any role); (b) team-based rest capped at 7 days (no 99s) + games in the last 7 days | last-game dates by team, strictly earlier | `build.py` already has (a) behind a flag; (b) new |
| T6 | **Travel/fatigue (repo, after the two bug fixes)** | `include_travel_fatigue=True` (10 columns) | `team_game_venues` appended after the row is built | exists, opt-in |
| T7 | **Tip-off timing** | rest in hours = (this tip - team's previous tip) - 2.5h, capped 96h, plus an afternoon-start flag | tips are scheduled before the game; the snapshot has `tip_off` for 1,509/1,509 schedule rows | `schedule_repository`/`to_training_frame` must carry `tip_off` into the training file (today `schedule/games.json` has `tip_off = null` and `to_training_frame` drops it) |
| P1 | **Game context for props** | `is_home`, `game_pace = mean(team pace roll, opp pace roll)`, `opp_drtg` (opponent's rolling points allowed per 100), `team_ortg`, blowout risk `abs(elo_diff)/100`, `team_elo_adv` | team-level rolls as T1/T2, shift(1) | `features/prop_matchup.py` + `pipeline/ingest.py` (`to_player_training_frame` already carries opponent and home/away) |
| P2 | **Player matchup block (repo)** | `opp_def_vs_pos` (opponent's points per 36 conceded to the position group, date-grouped 10-date window, `min_periods=3`), `usage_trend` (share of team FGA, 10-game), `minutes_trend`, player `rest_days` | the repo's date-grouped window excludes the whole night | exists in `prop_matchup.py`, **not in the serving path** |
| P3 | **Shot profile and shrunk shooting** | `fga_roll`, `fg3a_roll`, `fta_roll` (10); `fg3_pct_shrunk = (3PM_20 + 40*0.355)/(3PA_20 + 40)` over the player's last 20 games; `exp_threes = fg3a_roll * fg3_pct_shrunk`; also `threes_per_min * minutes_roll` | shift(1) before the rolling sums | `features/player_stats.py` (`fg3a` must be added to `to_player_training_frame`; it is dropped today) |
| P4 | **Minutes volatility** | `minutes_sd` = sd of the last 10 minutes values (min 3) | shift(1) | `player_stats.py` |
| P5 | **Model type** | the XGBoost prop regressors (200 trees, depth 4, 5 features) lose to the trailing mean they are built from; try a ridge on standardised features (alpha 50) and a 50/50 blend with the trailing mean | n/a | `models/player_props.py` |

What cannot be derived from data on disk, and why: (i) true availability-weighted strength from the injury feed: `injuries_current.json` is a single snapshot (65 rows), so who was out on a past night is unknowable; T4 is the box-score-only substitute. (ii) starter flags, plus-minus, steals/blocks/fouls: not captured by the parser (nine team fields, nine player fields). (iii) spread-based blowout risk and prop-line-based minutes expectations: no lines on disk.

## 4. Tests with the harness

Method, identical for every team-level arm: the repo's `build_training_frame` columns as the baseline (22 default columns, the race winners logistic/ridge/ridge), candidate = baseline columns + the new ones (or replacing, where stated), same 765 out-of-fold games, `paired_bootstrap` (2,000 resamples, seed 20261009) for log-loss, Brier, AUC, margin MAE, total MAE, `calibration_gap` (5 buckets) before and after, and the repo's `ship_decision` verbatim (AUC lower bound >= 0; the other four each improved with an interval excluding zero; gap <= 0.0591 and not wider than the baseline's 0.0578). Baseline: log-loss 0.6612, Brier 0.2342, AUC 0.6322, margin MAE 13.2197, total MAE 16.5488, gap 0.0578. Differences are candidate minus baseline; for AUC positive is better, for the rest negative is better. New columns are scaled to roughly unit size because the repo's ridge/logistic are unscaled.

### 4.1 Team-model blocks (win / margin / total)

| arm | win log-loss | win Brier | win AUC | margin MAE | total MAE | gap | `ship_decision` |
|---|---|---|---|---|---|---|---|
| **A** Elo (win/loss, K=20, base-10), 1 column | -0.0731 [-0.0951, -0.0506] | -0.0330 [-0.0425, -0.0231] | +0.1136 [+0.0771, +0.1506] | -1.282 [-1.659, -0.911] | -0.024 [-0.128, +0.081] n.s. | 0.0886 | **does not ship**: total not improved, gap wider |
| **B** MOV Elo variant | -0.0750 [-0.0969, -0.0526] | -0.0337 [-0.0434, -0.0239] | +0.1159 [+0.0793, +0.1536] | -1.270 [-1.639, -0.914] | -0.043 [-0.151, +0.069] n.s. | 0.0755 | **does not ship**: total not improved, gap wider |
| **C** pace + ortg + drtg rolling-10 (6 cols) | -0.0516 [-0.0707, -0.0310] | -0.0230 [-0.0318, -0.0135] | +0.0846 [+0.0470, +0.1214] | -0.889 [-1.191, -0.582] | **-1.215 [-1.628, -0.809]** | 0.1161 | **does not ship**: gap 0.1161 only |
| **D** opponent-adjusted off/def (5 cols) | -0.0500 [-0.0674, -0.0315] | -0.0227 [-0.0308, -0.0142] | +0.0868 [+0.0507, +0.1227] | -0.838 [-1.119, -0.563] | -0.418 [-0.597, -0.229] | 0.0772 | **does not ship**: gap only |
| **E** pace x efficiency expected total (2 cols) | +0.0003 n.s. | +0.0002 n.s. | -0.0020 [-0.0091, +0.0045] | +0.013 n.s. | **-1.121 [-1.483, -0.760]** | 0.0763 | **does not ship**: only total moves, AUC bound below 0, gap wider |
| **F** availability proxy, lagged (4 cols) | -0.0263 [-0.0382, -0.0150] | -0.0120 [-0.0174, -0.0068] | +0.0515 [+0.0271, +0.0777] | -0.603 [-0.860, -0.358] | +0.001 n.s. | 0.0648 | **does not ship**: total not improved, gap above the bar |
| **G** rest cleaned: team-based rest capped at 7 + games in last 7 days, replacing the repo rest/back-to-back columns | +0.0048 n.s. | +0.0024 n.s. | **-0.0228 [-0.0436, -0.0023]** worse | +0.021 n.s. | **+0.142 [+0.013, +0.272]** worse | 0.1005 | **does not ship** |
| **H** A + D + pace (7 cols) | -0.0760 [-0.0993, -0.0527] | -0.0336 [-0.0440, -0.0233] | +0.1162 [+0.0784, +0.1540] | -1.322 [-1.720, -0.942] | -1.176 [-1.570, -0.787] | 0.0931 | **does not ship**: all five improve; gap 0.0931 is above the bar and wider than 0.0578 |
| **X** drop the 5 constant-zero columns + cap rest_days at 7 (no new information) | +0.0022 n.s. | +0.0011 n.s. | -0.0087 [-0.0195, +0.0019] | +0.021 n.s. | -0.006 n.s. | 0.0516 | does not ship (nothing improves; harmless clean-up, but not a ship under this rule) |
| **XH** X + H | -0.0745 [-0.0974, -0.0508] | -0.0330 [-0.0431, -0.0223] | +0.1154 [+0.0773, +0.1538] | -1.310 [-1.709, -0.923] | -1.156 [-1.557, -0.755] | 0.0698 | **does not ship**: gap only |
| **HF** H + availability proxy F (11 cols) vs baseline | **-0.0830 [-0.1072, -0.0572]** | **-0.0356 [-0.0462, -0.0242]** | **+0.1214 [+0.0837, +0.1601]** | **-1.434 [-1.884, -0.985]** | **-1.259 [-1.697, -0.825]** | **0.0550** | **SHIPS under the rule as written** (see caveats below) |
| HF vs H (is F worth adding on top?) | -0.0070 [-0.0147, -0.0001] | -0.0020 n.s. | +0.0052 n.s. | -0.112 n.s. | -0.083 n.s. | 0.0931 -> 0.0550 | does not ship vs H: the availability proxy is mostly absorbed by the rating block |
| **I** tip-off: rest in hours tip-to-tip (cap 4 days) + afternoon-start flag, replacing day-count rest | +0.0022 n.s. | +0.0012 n.s. | -0.0090 [-0.0222, +0.0054] | -0.003 n.s. | **+0.142 [+0.041, +0.242]** worse | 0.0789 | **does not ship** |
| **I2** same, added to the existing rest columns | +0.0035 n.s. | +0.0017 n.s. | -0.0117 [-0.0234, +0.0007] | +0.005 n.s. | **+0.169 [+0.075, +0.266]** worse | 0.0398 | **does not ship** |
| **R** `rest_by_team=True` (repo flag; tool `compare_rest_by_team.py`) | +0.0027 [-0.0013, +0.0067] n.s. | +0.0014 n.s. | -0.0145 [-0.0288, +0.0001] | +0.045 n.s. | **+0.191 [+0.072, +0.315]** worse | 0.0356 | **does not ship** |
| **T** travel/fatigue, `include_travel_fatigue=True` (repo tool, after the two bug fixes) | **+0.0111 [+0.0020, +0.0201]** worse | **+0.0053 [+0.0010, +0.0095]** worse | **-0.0303 [-0.0547, -0.0053]** worse | +0.058 n.s. | **+0.224 [+0.063, +0.391]** worse | 0.0606 | **does not ship** |

All rows re-run by me on 2026-10-13 (n = 765 each). Read straight from the logs in `2026-10-13-nba-model-gaps-scripts/logs/`.

**The HF row needs a careful reading.**

* It is the only arm that satisfies `ship_decision` exactly as `ship_rule.py` states it: AUC lower bound +0.0837 (>= 0), all four other metrics improved with intervals excluding zero, gap 0.0550 <= 0.0591 and < 0.0578.
* **It was found after looking at about 15 arms on these same 765 games**, and HF in particular was assembled after seeing that H failed only on the gap clause and that F helped. Treat "passes" as "passes on the data used to design it". It is a hypothesis, not a clearance. Nothing was tuned within an arm (all hyperparameters are the repo's), but the choice of arm was.
* **The gap clause is mostly sampling noise at this n.** If I draw outcomes from each model's own probabilities (a perfectly calibrated model of the same spread), the 5-bucket max gap has median 0.056 (95% range 0.025 to 0.108) for HF and 0.060 (0.021 to 0.110) for the baseline: the 0.0591 bar sits at the median of what a perfect model produces on 765 games. H's gap of 0.0931 and HF's 0.0550 are both inside that noise. The bootstrap interval of the observed gap is wide too (baseline [0.041, 0.148], H [0.057, 0.167]). So the arms that "failed on gap only" (C, D, H, XH) do not demonstrably have worse calibration, and HF does not demonstrably have better. An out-of-fold Platt calibrator (the repo's own, `calibrator="platt"`, applicable only to the last 261 games) leaves log-loss unchanged (baseline 0.6416 -> 0.6443, H 0.5522 -> 0.5515) and gaps 0.1430 -> 0.1428 baseline, 0.1147 -> 0.0991 H on those 261 games, which again says that bucket gaps at n of a few hundred are not informative.
* **It is consistent across the test period**, which is some protection against one lucky window. Log-loss baseline / H / HF by test slice: 0.6956 / 0.6585 / 0.6550 (246 games), 0.6482 / 0.5486 / 0.5335 (258), 0.6374 / 0.5265 / 0.5248 (206), 0.6611 / 0.6482 / 0.6448 (53); margin MAE 12.75 / 12.08 / 11.97, 12.76 / 11.16 / 10.96, 14.22 / 12.20 / 12.21, 14.21 / 13.81 / 13.68; total MAE 17.26 / 15.84 / 15.80, 15.57 / 14.92 / 14.93, 16.66 / 15.60 / 15.30, 17.02 / 14.42 / 14.51. H and HF beat the baseline in every slice for every target. (The 2-game last slice is omitted.)
* **It is not independent of the reference Elo finding**: the repo's own frozen-rating Elo scored log-loss 0.5984 / AUC 0.7418 on the same games with different code, so the size of the Elo effect is not an artifact of my implementation.
* Served probability (Phi(margin / sigma)): baseline log-loss 0.6566, gap 0.0645, sigma_margin 16.57, sigma_total 20.74; HF log-loss 0.5757, gap 0.0494, sigma_margin 14.77, sigma_total 19.16. A smaller sigma matters for the cover/over probabilities the site shows: they are currently too wide.
* Single season, single machine, no market comparison. 765 games, one NBA season including preseason. The sensible confirmation is the multi-season backfill (n around 2,400) or the 2026-27 season as it is played, with the feature spec frozen first.

### 4.2 Player-prop features

`ship_decision` needs a win AUC, so it cannot be applied to a prop model. I applied its logic to MAE: a candidate counts only if the paired interval of (candidate - comparator) MAE excludes zero on the improving side, against BOTH the current model and the trailing-10 mean. Resampling is by game (rows in a game share a game script), 2,000 resamples. Walk-forward windows as in section 2. 29,781 player-game rows with the game-context features (the section 2 table used 29,965: the extra rows lack a team pace history). Because the current XGBoost 5-feature model is the incumbent and the trailing mean is the honest naive, both comparisons are shown. "vs trailing" and "vs current" are differences in MAE (candidate minus comparator, negative = candidate better).

| market | current XGB (5 rolls) MAE | trailing-10 mean MAE | best candidate | candidate MAE | vs trailing-10 mean | vs current model |
|---|---|---|---|---|---|---|
| points | 4.6795 | 4.6453 | ridge on P4 (all features) | 4.5809 | **-0.0644 [-0.0791, -0.0498]** (-1.4%) | **-0.0986 [-0.1149, -0.0826]** (-2.1%) |
| rebounds | 1.9380 | 1.9268 | ridge on P5 (matchup + game context, no shot profile) | 1.9121 | **-0.0147 [-0.0211, -0.0085]** (-0.8%) | ridge P4: **-0.0250 [-0.0310, -0.0188]** (-1.3%) |
| assists | 1.3763 | 1.3730 | ridge on P5 | 1.3562 | **-0.0167 [-0.0212, -0.0125]** (-1.2%) | ridge P4: **-0.0194 [-0.0243, -0.0147]** (-1.4%) |
| threes | 0.9126 | 0.8963 | **no model**: trailing 20-game 3PM per minute x trailing-10 minutes | 0.8865 | **-0.0098 [-0.0140, -0.0060]** (-1.1%) | -0.026 (point estimate only, CI not computed) |

Feature-set results, in detail (all in `logs/step4_props.log` and `logs/step4b_props.log`), MAE difference vs the trailing-10 mean:

| set | points | rebounds | assists | threes |
|---|---|---|---|---|
| XGB P0 current | +0.0342 [+0.0186, +0.0507] worse | +0.0112 [+0.0037, +0.0183] worse | +0.0033 n.s. | +0.0163 [+0.0119, +0.0204] worse |
| XGB + P1 repo matchup block | +0.0003 n.s. | +0.0004 n.s. | -0.0032 n.s. | +0.0128 [+0.0085, +0.0168] worse |
| XGB + P2 game context | -0.0041 n.s. | +0.0007 n.s. | -0.0051 n.s. | +0.0134 worse |
| XGB + P3 shot profile | +0.0134 n.s. | +0.0125 worse | +0.0057 worse | +0.0047 [+0.0001, +0.0091] worse |
| XGB + P4 all | **-0.0361 [-0.0563, -0.0159]** | -0.0086 [-0.0168, +0.0001] n.s. | -0.0069 [-0.0128, -0.0010] | +0.0031 n.s. |
| XGB damped (120 trees, depth 3, lambda 10) P0 | +0.0496 worse | +0.0130 worse | +0.0040 n.s. | +0.0214 worse |
| ridge P0 (same 5 features, linear) | +0.0088 n.s. | +0.0035 n.s. | -0.0005 n.s. | +0.0246 worse |
| ridge + P1 | -0.0328 [-0.0461, -0.0200] | -0.0057 n.s. | -0.0066 [-0.0105, -0.0027] | +0.0152 worse |
| ridge + P2 | -0.0289 [-0.0414, -0.0162] | -0.0085 [-0.0144, -0.0028] | -0.0137 [-0.0180, -0.0097] | +0.0179 worse |
| ridge + P3 | -0.0274 [-0.0403, -0.0147] | +0.0045 n.s. | -0.0014 n.s. | +0.0020 n.s. |
| ridge + P4 | **-0.0644 [-0.0791, -0.0498]** | -0.0138 [-0.0206, -0.0077] | -0.0161 [-0.0207, -0.0119] | -0.0018 [-0.0057, +0.0019] n.s. |
| blend 0.5 damped-XGB(P4) + 0.5 trailing mean | -0.0297 [-0.0382, -0.0215] | -0.0081 [-0.0124, -0.0040] | -0.0076 [-0.0104, -0.0049] | -0.0021 [-0.0043, +0.0001] n.s. |
| direct: exp_threes = fg3a_roll10 x shrunk 3P% (20 games, 40-attempt prior at 0.355) | | | | -0.0062 [-0.0094, -0.0032] |
| direct: 3PM per minute (20 games) x minutes_roll10 | | | | **-0.0098 [-0.0140, -0.0060]** |

What the prop results say, in order of confidence:

1. **The incumbent XGBoost is the problem, not a missing feature.** The same five features through a linear model are statistically no worse than the trailing mean for points, rebounds and assists (threes is still worse), and every context feature that helps does so most cleanly through a ridge. A 200-tree depth-4 booster on 13k to 29k training rows fits noise in the 5 rolling means; damping the booster (120 trees, depth 3, lambda 10) did not fix it.
2. **Points, rebounds and assists have signal in data already on disk**: game context (home/away, pace, opponent defensive rating, blowout risk from the Elo gap) and the repo's matchup block carry most of it; shot-profile features add almost nothing for them (P5 without shot profile is as good as P4). Gains are small in relative terms (0.8 to 1.4% over the trailing mean, 1.3 to 2.1% over the incumbent) but the intervals exclude zero.
3. **Threes: the best model is no model.** 3PM-per-minute over 20 games times expected minutes beats the trailing-10 3PM mean by 1.1% [0.7, 1.6] and beats the incumbent by about 2.9%, with nothing to fit. Using more attempts-history and a shrunk rate is what helps (more attempts per estimate). No fitted model, XGB or ridge, cleared the trailing mean for threes.
4. **Caveats**: 9 model/feature-set combinations per market on the same rows, intervals not multiplicity-adjusted; 4 test windows of one season; MAE only, no calibration or hit-rate (no prop lines on disk); the context features need the serving path to supply opponent and home/away at prediction time (`to_player_training_frame` has them, `score_upcoming_player_props` is untested for it here). Ridge alpha 50 was set once, not tuned.

## 5. Recommendations, limits, and how to reproduce

### 5.1 Prioritised recommendations (nothing here is shipped by this PR)

1. **Give the team model a strength rating and a scoring model (HF block: causal Elo, opponent-adjusted offence/defence, rolling pace, lagged availability).** Largest effect found: win log-loss 0.6612 -> 0.5782, AUC 0.632 -> 0.754, margin MAE 13.22 -> 11.79, total MAE 16.55 -> 15.29 (the total finally beats a constant, by 6.6% against the training-mean baseline), and the served sigmas shrink (margin 16.57 -> 14.77, total 20.74 -> 19.16), which tightens every cover/over probability. It satisfies `ship_decision`, but see 4.1: designed on the evaluation games, single season. Before flipping `DEFAULT_BLOCKS`, (a) freeze the spec, (b) run the free multi-season backfill so the same rule is evaluated at n around 2,400 where the calibration clause can actually resolve, (c) re-run `compare_*` on that. This is the plan's `power` + `form` + `adjusted` + `availability` blocks; the framework (`DEFAULT_BLOCKS`) is described in the plan docs but is not in NBA main at `9e97c43`, so these arms were built in a harness instead.
2. **Stop serving the XGBoost prop projections as they are.** They lose to the player's trailing-10 mean on points, rebounds and threes (CI excludes zero). Cheapest honest move needing no new data: serve the trailing mean (or a ridge on the existing 5 features, which ties it). Better, from data already on disk: ridge on game context + matchup features for points/rebounds/assists, and the 3PM-per-minute x minutes formula for threes.
3. **Remove or replace the dead columns.** `home_power_rating`, `away_power_rating`, `power_rating_diff`, `home_missing_value`, `away_missing_value` are constant 0.0 in training; cap `home_rest_days`/`away_rest_days` at 7 (99 for a team's first game). Alone this changes nothing measurable (arm X: all n.s.), so it is hygiene, not a ship, but recommendation 1 fills the power columns for real.
4. **Do not spend more time on rest/travel/tip-hour features at this sample size.** Rest-by-team, cleaned rest, travel/fatigue and tip-to-tip rest hours are all non-improving; travel/fatigue is measurably harmful after the two bug fixes (AUC -0.0303 [-0.0547, -0.0053], total MAE +0.224 [+0.063, +0.391]); the earlier conclusion survives the fixes. Revisit on the multi-season frame, not before.
5. **Spec question for Kevin: the calibration clause.** At 5 buckets and n=765 a perfectly calibrated model has a median max-gap of about 0.056, the bar is 0.0591. The clause rejects good models about half the time and passes bad ones about half the time at this n. Options: evaluate it only at n >= 2,000, use bucket CIs instead of a point gap, or compare calibrated log-loss. This is a decision for Kevin, not something I changed.
6. **Spec question for Kevin: per-target ship rule.** The rule requires win, margin and total to all improve. Block C (and E) is a clear win for the total (-1.2 MAE) and does nothing bad elsewhere, but under the rule it can only ship together with a win/margin improvement. If total were scoped separately, `exp_total` (arm E, 2 columns) would have cleared it for the total alone.
7. **Capture more of what ESPN already sends.** Starter flag, plus-minus, steals, blocks, fouls are in the ESPN payload class but not parsed; `ftm`, `fg3a`, `fta` are parsed and dropped for players; `tip_off` exists in the snapshot but not in `schedule/games.json` or the training file. None of these was needed for the gains above, none was tested.
8. **Start recording odds now.** No market baseline exists on disk (odds/sportsbook caches empty, market tables in tracking.db have 0 rows), so "does the model beat the closing line" is unanswerable, and without it the record of 5/10, 5/10, 6/10 cannot be interpreted. The `odds_timing_snapshots` and `value_closing_lines` tables exist and are empty.

### 5.2 What could not be measured

* **Anything against the market**: no odds, lines, or closing lines on disk; spread-cover and over/under hit rates and edge cannot be scored; prop lines are absent, so prop MAE is the only prop metric.
* **Multi-season behaviour**: one season (2025-26 incl. preseason) on disk, `history_df` empty everywhere. The 4,149-game frame of `compare_margin_average.py` was not rebuilt (about 6,000 free keyless ESPN requests; not run).
* **Injuries**: the feed has one snapshot (65 rows), so availability-weighted strength from the injury report could not be tested; only the box-score proxy (F) was. The proxy is lagged and cannot see a late scratch.
* **Starters/minutes projections**, plus-minus, steals/blocks/fouls: not in the cache.
* **Live record**: the 5/10, 5/10, 6/10 pre-tip counts are quoted from the task, not recomputed by me; the local tracking.db has only in-sample bulk backfill rows.
* **Calibration at serving**: the OOF Platt check covers 261 games; the repo's isotonic variant and the served-probability ceiling were not explored.
* **`tools/compare_phase_a.py`** crashes on an empty history frame on this machine (pandas "Grouper for 'team' not 1-dimensional"), so the Phase A number reproduction in that tool was not run; I used the other compare tools and my own harness.
* **Statistical caveats**: team-level arms were chosen after viewing results on the same 765 games (about 15 arms, see 4.1); prop arms: 9 combinations per market; no multiplicity correction anywhere; AUC naive baseline is the constant 0.5 (the pooled naive predictions are window-specific constants, which is why a naive pooled AUC can print as 0.469).

### 5.3 Commands (run from the NBA clone `Kevocado/NBA_Predictor@9e97c43`, with the ESPN caches copied to `data/cache/espn`; scripts are in `docs/research/2026-10-13-nba-model-gaps-scripts/`, they expect to sit one directory above the clone as `../script.py` and write pickles/logs to `../`)

| what | command | logs |
|---|---|---|
| rebuild training cache (offline) | `uv run --python 3.13 python ../build_cache.py` | n/a |
| rebuild player frame | `uv run --python 3.13 python ../build_players.py` | n/a |
| section 2, team models vs naive, Elo, served win, calibration | `uv run --python 3.13 python ../step2_teams.py` | `logs/step2_teams.log` |
| section 2, props vs trailing mean | `uv run --python 3.13 python ../step2_props.py` | `logs/step2_props.log` |
| arms R and T (repo tools, unmodified) | `uv run --python 3.13 python tools/compare_rest_by_team.py` and `.../compare_travel_fatigue.py` | `logs/rest_by_team.log`, `logs/travel_fatigue.log` |
| arms A to H (also writes `../F_team.pkl`, needed by later scripts) | `uv run --python 3.13 python ../step4_team.py` | `logs/step4_team.log` |
| arms X, XH, gap noise simulation, served-probability gaps | `uv run --python 3.13 python ../step4b_team.py` (its Platt tail crashes on a variable bug; the X/XH/noise/served parts printed first and are what is quoted) | `logs/step4b_team.log` |
| out-of-fold Platt check | `uv run --python 3.13 python ../step4d_platt.py` | `logs/step4d_platt.log` |
| arms I, I2 (tip-off) | `uv run --python 3.13 python ../step4c_tip.py` | `logs/step4c_tip.log` |
| arm HF vs H and vs baseline | `uv run --python 3.13 python ../step4e_hf.py` | `logs/step4e_hf.log` |
| per-slice consistency, HF served gap, HF noise gap | `uv run --python 3.13 python ../step4f_consistency.py` | `logs/step4f_consistency.log` |
| prop feature sets, XGB/ridge/blend | `uv run --python 3.13 python ../step4_props.py` | `logs/step4_props.log` |
| prop ridge ablation | `uv run --python 3.13 python ../step4b_props.py` (its `DIRECT exp_threes` line printed NaN because of unfilled first-game rows; the corrected number comes from the next row) | `logs/step4b_props.log` |
| direct threes formulas | `uv run --python 3.13 python ../step4d_threes.py` | `logs/step4d_threes.log` |

Feature code: `feats.py` (Elo, pace/efficiency, adjusted ratings, availability proxy, rest cleaned). Shared harness: `h.py` (the repo's `walk_forward_*`, `default_candidates`, `paired_bootstrap`, `calibration_gap`, `ship_decision`). Dates of runs: all 2026-10-13.
