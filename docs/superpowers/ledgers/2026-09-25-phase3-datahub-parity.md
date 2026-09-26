# SDD ledger — plan: docs/superpowers/plans/2026-09-25-phase3-datahub-parity.md
Spec: docs/superpowers/specs/2026-09-25-phase3-4-datahub-explainer-design.md (sub-project A)
Executor: executing-plans (inline). Repos: NFL_Predictor, CFB_Predictor, Sports_Predictor, predictor-hub; branch claude/sports-predictors-frontend-plan-qpab3v.
Pre-flight:
- T1→T3: T3 imports team_efficiency_mod.{team_efficiency,load_pbp,PBP_COLUMNS} — matches T1 Produces. OK.
- T2→T3: T3 uses player_season(weekly, season) -> {players, leaderboards} — matches. OK.
- T1/T4→T6: HubTeam type = T1 keys; CFB adds advanced_available on the response. OK.
- T2/T4→T6: HubPlayer = T2 player keys; CFB players carry the same keys (epa_total from PPA). OK.
- T5→T6: StatTable/Column exported from predictor-ui index. OK.
Ruling: task-start/task-done scripts can't resolve ../../subagent-driven-development (skills installed as superpowers-*) — ledger BASE/results by hand — cost if wrong: none, same record
Task 1: complete (commits 4fd4c03..e1c4411, tests: uv run pytest -q → 118 passed; warnings are pre-existing pandas/numpy deprecations)
Task 2: Ruling: EPA/share columns can be object dtype (None) — cast .astype(float) before sum/mean — cost if wrong: none
Task 2: complete (commits e1c4411..8eaa4c9, tests: uv run pytest -q → 120 passed)
Task 3: Ruling: added _get_hub_players_live helper (snapshot calls it) instead of toggling PUBLIC_MODE — cleaner, same behaviour — cost if wrong: none
Task 3: complete (commits e1c4411..de8f967, tests: uv run pytest -q → 122 passed; pushed)
Task 4: Ruling: player PPA API is cfbd.MetricsApi.get_predicted_points_added_by_player_season(year) in cfbd 5.30 (plan named get_player_season_ppa) — use it; total_ppa.all → ppa_total — cost if wrong: player EPA shows dashes
Task 4: Ruling: CFB box scores have no targets (always NaN) and no EPA columns — player rows carry epa_total from PPA only; target_share None — cost if wrong: columns show dashes
Task 4: complete (commits 0f27553..838a5a8, tests: uv run pytest -q → 138 passed; pushed)
Task 5: complete (commits e0a0b70..2b73641 hub + Sports resync, tests: predictor-ui vitest 105/105, tsc ok; Sports vitest 107/107, tsc ok)
Task 6: Ruling: plan's FormStrip is used with a new wrap={false} prop and text raised 11px→12px (craft floor) — needed for one-line table cells — cost if wrong: one prop
Task 6: Ruling: added signedInt/perGame to hubFormat beyond epa/share; optional player columns (targets, target share, INT) are dropped when the feed never fills them (CFB zeros) — cost if wrong: CFB users lose an all-zero column
Task 6: Ruling: StatTable overflow fix (relative wrapper, sticky detail) verified by Playwright page-overflow measurement (390px: 72/390px → 0/0), not a jsdom test — layout isn't observable in jsdom
Task 6: complete (Sports commit above; tests: Sports vitest 106/106, tsc -b ok, oxlint clean, impeccable detect [] ; screenshots 1440/390 no page scroll)
Final review: fresh reviewer subagent (1 Critical, 5 Important, 5 Minor; all suites green before fixes)
Final: fixed C1 NFL hub players read columns the weekly cache drops — test_player_season_runs_on_exactly_the_columns_the_hub_fetch_returns + test_live_players_use_the_hub_weekly_loader RED→GREEN, suite 130/130
Final: fixed I1 pbp/hub weekly frozen at first request — test_current_season_refreshes_when_stale_and_keeps_stale_copy_on_error RED→GREEN, suite 130/130
Final: fixed I2 /hub/teams 500 before pbp exists — test_nothing_published_yet_gives_empty_frame_and_caches_nothing RED→GREEN, suite 130/130
Final: fixed I3 empty snapshot hub served and crashed Teams — NFL+CFB test_empty_snapshot_hub_falls_back_to_live, Sports "treats an empty payload…" RED→GREEN, suites 130/142/109
Final: fixed I4 CFB retried CFBD every request while failing — test_a_failing_cfbd_call_backs_off… + test_backoff_keeps_serving_the_last_good_rows RED→GREEN, suite 142/142
Final: fixed I5 CFB PPA joined by name — test_player_ppa_joins_on_athlete_id_before_name RED→GREEN, suite 142/142
Final: Ruling: M1 (arrow/aria-sort contradict values on negated columns) re-graded Important — sighted users see ↓ over rising numbers too — fixed with Column.firstDir; table.test + TeamHubPage test RED→GREEN, suites 106/109
Final: Ruling: M4 (previous sport's table flashes) re-graded Important — wrong-sport data on screen — fixed; PlayersPage test RED→GREEN, suite 109/109
Final: minor (deferred): M2 CFB snapshot can replace good advanced stats with advanced_available:false after a single CI-time CFBD failure
Final: minor (deferred): M3 CFB player rows send 0 (not null) for completions/attempts/INT/targets; a real zero-INT QB group would lose the INT column
Final: minor (deferred): M5 expand button aria-label repeats the state aria-expanded already announces; add aria-controls
Final: minor (deferred): non-public /hub/* recompute per request (no in-memory TTL); fine while public mode serves the snapshot
