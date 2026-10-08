# Plan: NBA feature blocks (defence, availability, style matchups) and the AI-summary matchup signal

Approved by Kevin on 2026-10-08: blocks 1-3, the player-box fetch, and style matchups feeding the AI summary.
Runs AFTER calibration and carry-over in the NBA hand-off (calibration is fit inside the walk-forward; carry-over is its
own A/B step). Order of work and all rules are unchanged: one PR per block, test-first, full suites, red-checked tests,
the CodeRabbit gate without pipes, no deploy by the agent. NBA stays an INDEPENDENT model (no betting lines anywhere).

## Inventory (verified on main, 2026-10-08)
24 columns in `features/build.py`. LIVE (17): home/away four factors (eFG, TOV rate, ORB%, FTr; 10-game causal rolling mean,
`shift(1)`), rest days (2), back-to-back (2), streak (2), high altitude, conference game, division game. DEAD (7, all constant 0 in
training because `_OPTIONAL_COLUMNS_DEFAULT_ZERO` is never populated): `home/away_power_rating`, `power_rating_diff`,
`home/away_fatigue_index`, `home/away_missing_value`. The helpers exist but are unwired: Elo and pace in `features/ratings.py`,
`fatigue_index`/`rolling_travel_miles`/`timezone_change_count` in `features/rest_travel.py` (arena lat/lon and timezone in
`data/team_reference.py`), `missing_players_value` in `features/injuries.py`. There are NO defensive features and no opponent
adjustment. Stored team box fields are only `BOX_FIELDS = fgm, fga, fg3m, tov, oreb, dreb, fta`; the parser also reads ftm and
fg3a but the training rows drop them. Player box scores (minutes, pts, reb, ast, shooting splits, position) are available via
`get_player_boxscore` (same ESPN `summary` endpoint) but the multi-season backfill keeps only the team half.

## Protocol for every block (the bar a block must clear to ship)
- Features are added in BLOCKS and scored as a block against the previous best, on the identical 758 out-of-fold games, with
  paired-bootstrap 95% intervals (2,000 resamples, fixed seed) for win log-loss, Brier, AUC, margin MAE and total MAE plus the
  5-bucket max calibration gap. A block ships only if its intervals support the gain on the metrics it claims AND the gap does not
  widen. Never test 30 single features against the same 758: that manufactures false wins. Within a block do an ablation table
  (drop each sub-group) so dead weight is removed.
- CAUSALITY: every feature for game g uses only games strictly before g's date (assert in a test that perturbing any game on or
  after g's date does not change g's features; week 1 of a season uses only prior-season data via the carry-over step).
- TRAIN/SERVE PARITY (the NFL passing-TD lesson: a model trained on a feature that serving never emits ran on `fillna(0)`):
  one test builds the SERVED feature row for an upcoming game through the real serving path and asserts every fitted column is
  present, non-null and equal to what training would have built for that game. Red-check by removing an emit. Also a generic test
  that fitted columns are a subset of served columns for every model in the manifest.
- Retrain through the candidate race on the new frame; report manifest metrics with the holdout named; never claim a metric the
  retrain did not produce.

## Block 1 - wire the dead features (no new data)
- Causal power rating: margin-of-victory Elo (home-court adjustment, K and the carry-over regression weight FIT in walk-forward,
  not hard-coded) computed over the frame in date order; `power_rating`, `power_rating_diff` for each game from ratings BEFORE the game.
- Fatigue: for each team and game, miles travelled in the prior 7 days (haversine over the team's real previous arenas), timezone
  changes, rest days -> `fatigue_index` via the existing formula; also expose travel miles and timezone shift as their own columns.
- Replace `home/away_missing_value` with the Block 3 availability features (do not leave a constant-zero column anywhere:
  add a test that fails if any FEATURE_COLUMNS entry has zero variance on the training frame).
- Drop-test `streak`, `conference_game`, `division_game`, `is_high_altitude` in the ablation; remove any that do not earn their place.

## Block 2 - defence, pace and opponent adjustment
- Keep more box fields: extend `BOX_FIELDS` and the parser/cache to store fg3a, ftm, fta, ast, stl, blk, pf, pts (a NEW cache key or
  version so old cached boxscores are re-read, not silently reused without the new fields); re-run the backfill (resumable) and report
  the missing-data rate per new field.
- Per team, causal rolling (windows 5/10/20 and an EWMA): offensive rating, defensive rating, net rating, pace (possessions/48),
  opponent-allowed eFG, TOV rate forced, DREB%, FT rate allowed, 3PA rate; home/away splits as separate columns.
- Opponent-adjusted ratings (SRS-style, solved causally per date) for offence and defence.
- Matchup-ready outputs are produced here, not in the UI (see Block 5).

## Block 3 - availability from player minutes (the player-box fetch)
- Backfill: add `--with-players` to `pipeline/backfill.py` (resumable, same global rate floor, ~4,000 extra requests): cache the
  player rows per event (minutes, starter flag, points, rebounds, assists, position). Tests use fixtures only and never the network.
- Features (all causal): per team, each rotation player's rolling 10-game minutes and per-minute production; for each game
  - `minutes_lost`: sum of rolling-minutes share of players who did NOT play,
  - `star_presence`: share of the team's top-3 (by rolling production) who played,
  - `starters_missing`: count of usual starters absent, plus `rotation_continuity` (share of minutes from the usual top 8).
- TRAIN/SERVE SKEW (state it, do not hide it): training uses who actually played (includes rest and coach decisions); serving only has
  the ESPN injury list (current, no history). Define the serving analogue from "Out" statuses only (Day-To-Day is a flag, never a
  number), measure the agreement between reported-Out and actual-DNP on the games where both exist, report it in the PR, and make the
  served value use the same definition the model was trained on or document the gap and its measured size.

## Block 5 - style matchups (features AND a new AI-summary signal)
- Features for margin/total/win: pace mismatch and expected possessions = f(home pace, away pace); each team's 3PA rate x the
  opponent's 3P% allowed; ORB% vs opposing DREB%; FT rate vs the opponent's foul-prone defence; TOV forced vs TOV committed;
  pace-adjusted efficiency interaction. The total model gets expected possessions x efficiency as its main input; add a league
  scoring-environment term (league average points per game over the trailing 30 days) because scoring drifts through a season.
- AI summary (spec amendment, hub): add a fifth signal kind `matchup` to `docs/superpowers/specs/2026-10-01-fixture-signals-design.md`
  (section 3 contract, section 4 table): "what the model sees in how these two teams play", computed, instant, no model call. Example
  content: "Pace: BOS 101.4 vs MIA 96.8 possessions, model expects 98.9 (BOS usually 101.4)"; "MIA allow 38% from three, BOS take 44%
  of shots from three". Rules: figures only from the team's own computed stats with sample size and date range (`n`, `source`,
  `as_of`); NEVER a roster-sum team figure (spec section 4 correction stands); a matchup row appears only when the gap is large
  enough to matter (an adapter-set `strength`, tested), never filler; a sport/game with no data shows no row. Visual `compare_bars`
  (home vs away, one stat per row). Add it to the shared `Signal` type and `SignalRows` in `packages/predictor-ui`; design the
  component with the impeccable skill (desktop + 390px, every state) in a HUB PR with tests, merge it, then re-sync NBA with
  `node scripts/sync-ui.mjs` (never hand-edit vendored files). NBA adapter: `signals/matchup.py` and the `/signals/{game_id}`
  endpoint include it. The AI "so what" step may cite ONLY figures present in the signal payloads (existing validator rule), so the
  explainer gains matchup facts without new unchecked numbers; extend the validator tests with a rejected invented matchup figure.
- Order: the hub signal + visual PR can start in parallel with Blocks 1-3 (it only needs the contract); the NBA adapter needs
  Block 2's stored stats.

## Out of scope / decided
Betting lines as a feature or benchmark (NBA is independent); lineup/on-off or tracking data (no free ESPN source); injury history
(derive from minutes instead); anything that would change recorded picks (immutable).

## Done when
Each block merged (or documented as not clearing the bar) with its A/B + bootstrap + calibration tables on the identical 758,
the parity and causality tests green, the matchup signal live on NBA fixture pages with the AI summary citing it, and a short
summary posted with measured numbers and anything for Kevin to decide.
