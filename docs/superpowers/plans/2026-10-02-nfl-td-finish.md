# Plan: finish NFL TD work (anytime TD fix, QB passing-TD line, pop-out)

**Status: executed — all four tasks shipped.** Corrected 2026-10-04: this plan
carried no status line at all, so its unchecked-looking task headings read as
unstarted work. Checked 2026-10-04 against merged PRs (`gh pr list --state
merged`): Task 1 + Task 2 in NFL_Predictor #26 ("feat: QB passing-TD call on a
per-player model line"), with the serve-side fixes that made it measurable in
NFL_Predictor #27–#31; Task 3 in NFL_Predictor #38 ("feat: record and grade the QB
passing-TD call so the shipped prediction can be evaluated"); Task 4 in
Sports_Predictor #27 ("feat: NFL pop-out — 'Rush or receiving TD' and 'QB passing
TDs' on the model line"), reworded by Sports_Predictor #29. The same anytime-TD
defect was fixed in CFB_Predictor #29. The "Done when" commits that needed a deploy
were NFL_Predictor, Sports_Predictor and CFB_Predictor.

**For the executing agent.** Self-review each task; every new test is red-checked by really removing the fix.
Gates, merge rule and standing rules are in the hand-off prompt on predictor-hub#69. Do not deploy.

**Decisions already made (Kevin, 2026-10-01):** anytime TD = rushing + receiving only (a QB appears only if
rushing makes him likely); passing TDs are a separate market; QB passing-TD call uses a per-player *model line*
(nearest half point to the QB's projection, floor 0.5), labelled "model line", never a sportsbook line;
Poisson-vs-NB is settled (chosen by log loss in the PR) and is not re-opened.

## Task 1 — NFL_Predictor#26: serving must supply every fitted column
Defect (verified): `models/manifest.py:62-65` fits the passing-TD model with `passing_tds_roll` first, but
`features/player_usage.build_features_for_player` never emits it, so serving `fillna(0)`s it.
1. Write the failing test first: build a QB's pregame row through `build_features_for_player` and assert every
   column the passing-TD model was fitted on is present and non-null for a QB with history.
2. Emit `passing_tds_roll` from `build_features_for_player` with the same `shift(1).rolling(5, min_periods=1)`
   discipline as its neighbours. The shift is what keeps the row free of the current week: add a test that the
   value for week N excludes week N's passing TDs.
3. Keep the column in the model. Fix the comment at `manifest.py:157-160` so it describes the code.
4. Audit: for every model in the manifest, assert fitted columns ⊆ served columns, in one parametrised test.
   If expensive, say why in the PR and describe the alternative; do not half-build it.
5. `load_models` reads the passing-TD artefact optionally. Decide: required (fail loudly at startup) or
   optional with a stated reason and a `/health` flag showing it is absent. A silently missing key is not allowed.
6. Gate: `uv run --python 3.11 --extra dev pytest`, red-check, CodeRabbit script, merge.

## Task 2 — anytime TD definition (if not already in #26)
`features/player_usage.py:23-25`: `anytime_td = (rushing_tds + receiving_tds) > 0`. Refit the classifier. Tests:
passing-only QB game is not an anytime TD (red-check by reverting); QB with a rushing TD is; WR/RB unchanged.
Record in the PR that old probabilities (e.g. Rodgers 81%) change and why.

## Task 3 — QB passing-TD model line, record and grading
Per QB: mu -> line = max(0.5, round-to-nearest-half(mu)) -> Poisson/NB P(over), P(under); call = higher side.
Pick record stores line, side, mu, probability. Track record grades over/under on actual passing TDs with the
earliest-pick-per-(game, market) rule. A half-point line cannot push. Tests: line is always a half point >= 0.5
and nearest mu; P(over)+P(under)=1; side = higher probability; grading on a known stat line; record round-trip.

## Task 4 — pop-out in Sports_Predictor (after #26 merges; re-sync hub UI first)
`src/lib/picksPanel.ts`: category "Rush or receiving TD" (kind `probability`, % + bar, top 3, rushers/receivers
only plus QBs whose rushing earns it); category "QB passing TDs" (kind `probability`, rows `Over 2.5 · 64%`,
top 3 QBs ranked by the called side's probability). Rows stay `{key,name,team,detail,value,kind}`; no
provenance, no ±, no record text. Tests: both categories render with 3 rows; a QB never appears in the TD
category on passing alone; CFB panel unchanged. `npm run build` + full vitest.

## Done when
NFL#26 and the Sports PR are merged through the CodeRabbit gate; summary on hub#69 lists the commits that need a
deploy (NFL_Predictor, Sports_Predictor) and notes the model was retrained.
