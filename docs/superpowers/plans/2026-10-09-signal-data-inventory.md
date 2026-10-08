# Signal data inventory (Task 0 of the AI summary redesign)

Read-only inventory of what per-match / per-game data actually contains in each repo.
Gates Tasks 7-9 (CFB, PL, NBA duels). Absent rows are deleted from the signal catalog,
not approximated.

## NFL (nfl_predictor)

| Signal | Status | Source |
|---|---|---|
| `pass_off_vs_pass_def:{home,away}` | available | pbp `team_game_efficiency` → `epa_off_pass` / `epa_def_pass` |
| `rush_off_vs_rush_def:{home,away}` | available | pbp `team_game_efficiency` → `epa_off_rush` / `epa_def_rush` |
| `qb_situation` | available | pbp `qb_games` (Task 5 of model plan) |
| `conditions` | available | schedule `roof/temp/wind`; Open-Meteo forecast (Task 7 of model plan) |

PBP columns confirmed present in nflverse parquet (2024 season, 49,492 plays):
`sack`, `qb_hit`, `yards_gained`, `yardline_100`, `down`, `first_down`.

## CFB (cfb_predictor)

| Signal | Status | Source |
|---|---|---|
| `ppa_pass/rush_off_vs_def` | available | CFBD advanced stats → `epa_off_pass` / `epa_def_pass` / `epa_off_rush` / `epa_def_rush` |
| `havoc` | **absent** | CFBD `/stats/game/advanced` (2024, 3,212 rows): not present on offense or defense |
| `line_play` | available in API, not read by loader yet (extend `_side()`) | CFBD `/stats/game/advanced` (2024) carries offense/defense `lineYards`, `lineYardsTotal`, `stuffRate` |
| `explosiveness` | available in API, not read by loader yet (extend `_side()`) | CFBD `/stats/game/advanced` (2024) carries offense/defense `explosiveness`, plus `powerSuccess`, `openFieldYards`, `secondLevelYards`, `successRate` |
| `talent_gap` | separate-call item | Requires a separate CFBD `/teams/talent` call (Task 12 extension) |

Note: availability marked on CFBD's real game-advanced response pulled for CFB#36, not on the loader's `_side()` selection. `powerSuccess`, `stuffRate`, `lineYards`, `explosiveness` exist in the API but are not yet read by the CFB loader.

## PL (pl_predictor)

| Signal | Status | Source |
|---|---|---|
| `attack_vs_defence` | available | Understat xG → `xg_for` / `xg_against` (rolling, per match) |

PL has xG for/against per match (Understat), rolling xG form, and actual-goals-minus-xG delta.
No shots-on-target column is currently loaded; xG is the available underlying metric.

## NBA (nba_predictor)

| Signal | Status | Source |
|---|---|---|
| `four_factors_duel` | available | box scores → `efg_pct_roll`, `tov_rate_roll`, `orb_pct_roll`, `ft_rate_roll` |

All four factors are computed and rolling (Task 9 of the NBA feature-blocks plan).
