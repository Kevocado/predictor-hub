# NFL / CFB model gaps: what the data on hand can still buy (2026-10-13)

STATUS: DRAFT, written incrementally. Sections 2-5 are filled in as each step finishes.
Research only: nothing here merges, trains an artifact, or deploys.

## 1. Inventory of data on hand

"Used" below means the column name appears as a string literal in the repo's `src/` or
`scripts/` code (a coarse grep, so it over-counts: a column that is read but only for
joining, or only by a tool that is not a feature builder, still counts as used). Command:
`python cols.py <repo>/src <label>=<parquet>` (a 10-line pyarrow + regex script run from the scratch dir; column lists are from the newest season file).

### NFL (`Kevocado/NFL_Predictor`, gitignored cache `data/cache`, copied read-only)

| Dataset | Seasons | Cols | Referenced in code | UNUSED columns worth noting |
|---|---|---|---|---|
| nflverse `pbp_YYYY` | 2017-2026 (10 files; 13,643 rows in 2026 so far) | 397 | 55 | `yardline_100`, `score_differential`, `wp`/`vegas_wp`, `shotgun`, `no_huddle`, `ydstogo`, `qtr`, `game_seconds_remaining`, `pass_location`, `run_gap`, `yards_after_catch`, `cpoe`/`xyac_*`, `td_prob`, `air_epa`/`yac_epa`, `first_down_*`, `tackled_for_loss`, `penalty`, `posteam_timeouts_remaining` (all pre-kickoff-lagged only if aggregated per team-game and shifted) |
| nflverse `weekly_YYYY` (player-week) | 2017-2024 (2025/26 derived from pbp) | 53 | 34 | `wopr`, `racr`, `pacr`, `dakota`, `sacks`, `sack_yards`, `*_fumbles*`, `*_2pt_conversions`, `special_teams_tds` |
| nflverse `schedules_YYYY` | 2017-2026 (also `schedules/` 2000-2026, 17 cols) | 46 | 24 | `home_moneyline`/`away_moneyline`, `home/away_spread_odds`, `home/away_qb_id`/`_name`, `home/away_coach`, `referee`, `overtime` |
| nflverse `ngs_YYYY` (stacked passing/rushing/receiving) | 2017-2026 | 51 | 17 | `expected_completion_percentage`, `completion_percentage_above_expectation`, `avg_time_to_los`, `percent_attempts_gte_eight_defenders`, `rush_yards_over_expected(_per_att)`, `rush_pct_over_expected`, `avg_yac_above_expectation`, `catch_percentage`, `percent_share_of_intended_air_yards` |
| nflverse `injuries_YYYY` | 2017-2026 | 16 | 9 | `report_primary_injury`, `practice_status` (DNP/limited/full by day: a stronger signal than the game-day `report_status` that is used) |
| nflverse `rosters_YYYY` (weekly) | 2017-2026 | 12 | 3 | `pos_slot`, `pos_rank`, `pos_abb` |
| `depth_charts/` | **2024 only** (37,312 rows) | 15 | 9 | `formation`; one season only, so depth-chart role features can only train on 2024 |
| `pbp_agg/` (participation join) | 2000-2026 (27 files, 38 cols) | 38 | 13 | `offense_personnel`, `defense_personnel`, `defenders_in_box`, `number_of_pass_rushers`, `was_pressure`, `time_to_throw`, `defense_man_zone_type`, `defense_coverage_type`, `offense_formation` |
| `team_stats/` | 2024 only | 32 | 32 | none, but one season |
| `player_stats/`, `retrain/player_stats/` | 2018-2024 / 2018-2025 | 17 | n/a | legacy slim copies |
| `weather/*.json` | 1,262 per-game files (2017+) | | used (temp, wind, precip) | |
| `odds/`, `injuries/` dirs | EMPTY on this machine | | | no odds-movement snapshots exist in the NFL cache; the only lines on disk are the single `spread_line`/`total_line`/moneyline per game inside `schedules` (closing lines: not allowed as features) |
| `tracking.db`, `data/tracking.db` | live pick tracker | | | evaluation only |

The 2026-10-13 production feature frame (reproduced here: `build_feature_frame(2017-2026)` ->
**50,807 x 115**; rows per season 2017..2026 = 5319, 5281, 5261, 5447, 5698, 5631, 5653, 5597, 5377, 1543). The quantile models
fit on the 38 `FORWARD_FEATURE_COLUMNS`; the other 77 columns are labels, ids, raw same-week stats (leakage if used) or
already-built-but-unselected columns. Built but NOT in the 38: `plays_roll`, `pass_share_roll`, `opp_plays_allowed_roll`,
`opp_pressure_rate_roll`, `gtg_carry_share`, `rz_carry_share`, `pressure_exposure`, `protection_time`, `gunslinger`,
`route_participation`, `implied_team_total`, `game_total`, `spread_line`, `total_line`, `intended_air_yards_*`, `avg_time_to_throw`, `aggressiveness`,
`teammates_out_doubtful`. Those last four lines are market lines: not eligible (rule: no closing lines as features).

### CFB (`Kevocado/CFB_Predictor`)

| Dataset | Seasons | Cols | Used | UNUSED |
|---|---|---|---|---|
| `data/cfbd/advanced_YYYY.json` (committed; CFBD `/stats/game/advanced`, team-game, ~3.2k rows/season, 12 API calls) | 2014-2025 (2020 is short: 2.2 MB) | per side offense/defense: overall + passing/rushing plays + passing/standard downs blocks of {ppa, successRate, explosiveness, totalPPA}, plus `lineYards`, `secondLevelYards`, `openFieldYards`, `stuffRate`, `powerSuccess`, `drives`, `plays` | 4 (`ppa`, `passingPlays.ppa`, `rushingPlays.ppa`, `successRate`), only inside the `epa` block, which is NOT in `DEFAULT_BLOCKS` (so used by **no shipped model**) | explosiveness, passing-down / standard-down splits, line yards, stuff rate, power success, open-field yards, plays/drives (pace) |
| cache `games/` | 2000-2026 | 14 (scores, conference, neutral_site, division) | game_outcome, total_points | `neutral_site` |
| cache `player_stats/` | 2018-2026 | 15 (pass/rush/rec yards, tds, targets, carries) | props | |
| cache `rosters/` | 2025-2026 | 4 | props | only 2 seasons |
| cache `sportsbook/` | 88 event JSONs | | live serving | no history |
| SP+, returning production, recruiting | NOT ON DISK, not committed | | | **cannot be tested**: the brief limits these to committed data |
