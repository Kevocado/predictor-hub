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
| `havoc` | **absent** | CFBD advanced stats do not include havoc rate |
| `explosiveness` | **absent** | CFBD advanced stats do not include explosiveness |
| `line_play` | **absent** | CFBD advanced stats do not include line-play splits |
| `talent_gap` | **absent** | Requires a separate CFBD `/teams/talent` call (Task 12 extension) |

CFBD `_side()` pulls only: `ppa` (→ epa), `passingPlays.ppa`, `rushingPlays.ppa`, `successRate`.
No explosiveness, havoc, or line-play fields are fetched.

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

## Deleted from the catalog

- CFB `havoc` — absent
- CFB `explosiveness` — absent
- CFB `line_play` — absent
- CFB `talent_gap` — absent (requires a separate API call; not in the current pull)

These rows are removed from the signal catalog in the AI summary redesign plan.
