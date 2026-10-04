# Player-Model Accuracy Remediation — Design Spec

**Date:** 2026-09-27
**Status:** Implemented in part (PL_Predictor). **Corrected 2026-10-04** — the second
half of this line used to read "NFL/CFB/NFL-CFB yardage work specified, not
started", which is no longer true of §5.1's two preconditions. Checked 2026-10-04
against merged PRs (`gh pr list --state merged`):

| §5.1 / §5.2 step | state | evidence |
|---|---|---|
| "stop displaying a number the system cannot compute" | **done** | Sports_Predictor #8 — the team-total-yards figure was decomposed and relabelled rather than deleted |
| CFB backfill + per-game reconciliation | **done** | CFB_Predictor #12 ("add the backfill that was missing", "reconcile per game instead of per team-week"); `src/cfb_predictor/data/team_stats.py` and `scripts/backfill_team_stats.py` are on CFB `origin/main` |
| NFL team-yardage source | partial | NFL_Predictor #9 names "a missing team-yardage source"; `src/nfl_predictor/data/team_stats.py` is on NFL `origin/main` |
| train the **team-total yardage model** (§5.2 step 4) | **unverified — no merged PR found** | neither NFL nor CFB `origin/main` contains a team-level yardage model; not claimed either way |
| re-enable the panel fed by the team model (§5.2 step 5) | **not started** | panel stays decomposed/relabelled per Sports_Predictor #8 |
| §5.3 `manifest.py` selection-bias fix | not started | no merged PR found |

So the §5.2 ordering held for its first step and the CFB backfill landed; the model
it was unblocking has not been traced to a merged PR, and this spec does not claim
it has.

**Origin:** Live forensic audit of all three predictors, 2026-09-27.
**Evidence file:** `/Users/sigey/Documents/Projects.nosync/.superpowers/audit-2026-09-27-total-yards.md`

---

## 1. The problem, stated once

The user-visible symptom is "total yards predictions are pretty off". Traced to its
source, this is **not one bug but a class of bug that all three predictors share**:
each project sums a whole roster's *per-player per-game* projections and labels the
result a team total, while the underlying player models are simultaneously
mis-calibrated, mis-scaled, and unmeasurable.

Measured live on the current deployment (`https://sports.40-160-91-131.sslip.io/?sport=cfb`):

| | CFB (week 5) | NFL (week 3) | Reality |
|---|---|---|---|
| Teams with a "Total Yards" figure | 118 | 32 | — |
| Median figure | **841** | **1110** | 300–450 (CFB) / 330–400 (NFL) |
| Max figure | 1343 | 1452 | — |
| In the realistic band | **0** | **0** | 100% should be |

---

## 2. Root causes, by layer

### Layer 1 — the aggregation is architecturally wrong

`Sports_Predictor/src/lib/playerRank.ts:17`

```ts
export function keyYardage(prop: PlayerPropPrediction): number {
  return prop.passing_yards ?? prop.rushing_yards ?? prop.receiving_yards ?? 0;
}
```

`GameDetailModal.tsx:208-213` sums that over every player whose `recent_team` matches,
i.e. the **entire active roster**, not a projected starting lineup.

Two independent errors compound:

1. **Over-counting.** Philadelphia's 1452 is 4 QBs' passing projections (217 + 199 + 185 + 63) added together. PHI has one starter.
2. **Under-counting the real thing.** `POSITION_MARKETS` gives QB no `rushing_yards`, RB no `receiving_yards`, WR/TE no `rushing_yards`. Verified: 0/112 NFL QBs have `rushing_yards`; 0/204 RBs have `receiving_yards`. Every omitted bucket is a rushing/receiving figure, so a "Total" built this way **cannot represent net yardage even in principle**.

### Layer 2 — there is no yardage model to aggregate

`total_yards` occurs **zero** times across `NFL_Predictor`, `CFB_Predictor`, and
`PL_Predictor`. Neither `/api/games` response carries any yardage field. Nothing sums
to a team total because nothing models a team total.

### Layer 3 — the player models are mis-calibrated

| Defect | NFL | CFB | PL |
|---|---|---|---|
| Zero-vector fallback (identical prediction for many players) | **430/880 (48.9%)** | 1497/2112 (71%) | n/a |
| Trained on `target > 0`, served unconditionally | yes | yes | n/a (Poisson) |
| `carries`/`receptions` declared but never trained | yes | yes | n/a |
| Position routing drops yardage | yes | yes | n/a |
| `shift(1)` train/serve skew | **yes** (`player_usage.py:17` vs `:33`) | inherited | n/a |
| No season filter on serving history | **yes** (416/458 rows off 2024 data) | inherited | n/a |
| `div_game` hardcoded 0 at serving | **yes** (`build.py:97`; training mean 0.3427) | inherited | n/a |
| Accuracy ever measured | **no** — 0 resolved | yes (MAE 59.5, signed +31.2) | yes |

**NFL's actual root cause is upstream and was not previously known:** nflverse has
published no `player_stats` file for 2025 or 2026 (both HTTP 404). Consequences:
100% of live rows come from the roster fallback, retraining is impossible, and
`reconcile_player_prop_predictions` returns 0 at its first line every tick.

**NFL's track record also went 30 → 0.** `record_resolved_game_predictions` stamps
`snapshotted_at = now`, and the backfill only ever receives *already-finished* games,
so every backfilled row is necessarily after its own kickoff and is filtered out as
`rebuilt`. The filter is correct; the backfill was never taught to backdate.

### Layer 3b — NFL's empty track record is CORRECT behaviour, not a bug

**Correction, 2026-09-27.** An earlier draft of this spec — following a research pass —
described NFL's `n_resolved: 0` as "a measurement bug, not a modelling result", on the
theory that the backfill stamped `snapshotted_at = now` and was therefore always filtered
out as `rebuilt`. **That framing was wrong, and the proposed fix was worse than the
disease.** It was caught before merge.

What the code actually does is a deliberate, documented decision. From
`docs/superpowers/reports/2026-09-25-predictor-pregame-feed.md` (a shipped PR):

> **Deviation — no `backfilled` column, no legacy classification pass.** The plan added a
> `backfilled INTEGER` column plus a one-time pass over existing rows. PR #1 already
> shipped the better version of that idea as `_snapshotted_after_kickoff(snapshotted_at,
> commence_time)`: pre-game-ness derived live from two columns that always existed,
> **failing closed on an unparseable row**. Reusing it means **the flag cannot drift out
> of step with the timestamps** and a database written before this change needs no
> migration pass at all.

Two tests pin it: `test_legacy_rows_need_no_migration` asserts
`"backfilled" not in cols, "a stored flag is exactly what the rebuilt rule replaced"`, and
`test_track_record_leaves_rebuilt_picks_out_of_every_rate` asserts a backfilled pick is
"shown, never counted".

The rule is also substantively right. `record_resolved_game_predictions`'s docstring puts
the burden on the caller: *"Each game dict's prediction fields must already come from
strictly pre-game information (the caller's job)"*. In practice `routes.py` recomputes
the prediction at backfill time from the **current** model weights and the **current**
data. That is a reconstruction, not a frozen pre-game pick, and excluding it is honest.
Counting it — which is what a `backfilled` column would do — would have inflated the
track record with numbers that were never actually made before kickoff.

**So `n_resolved: 0` is the correct answer to the question the metric asks.** The real
defects are upstream of the metric:

1. **Deployment.** The container scales to zero. The tracking loop only ticks on startup
   and every `_TRACKING_INTERVAL_SECONDS` thereafter, so after a scale-down it misses the
   pre-kickoff window entirely and snapshots nothing. Live evidence: the VPS reports
   `n_resolved 0 / n_rebuilt 33` while an older warm container still reports 30 resolved
   for the same 33 games (`30 + 3 = 33`). The split is purely "was the container up".
2. **No input data.** nflverse publishes no `player_stats` for 2025 or 2026, so
   `reconcile_player_prop_predictions` returns 0 at its first line and prop accuracy is
   unmeasurable regardless of uptime.

Neither is a code fix. Task 3 is therefore an **operations** task, not a schema change.

### Layer 4 — the metric is selection-biased (PL)

`manifest.py:272` selects the model with `min(candidates, key=...)` on the **same**
380-fixture `val_df` whose metrics are published at line 369. The reported RPS
`0.20778410803471484` and `market_metrics.ml_scoreline.rps`
`0.20778410803471487` agree to 14 significant figures. The published headline is the
minimum of four noisy estimates, with no selection-aware interval (the bootstrap CI
it does publish is 0.0234 wide — 8× the entire inter-candidate spread).

---

## 3. The data that would make this correct (verified)

The decisive finding is that the correct approach is **project the team total, then
allocate it by share** — because the share constraint is an *exact identity*, not an
approximation.

| Sport | Source | Rows | Cost | Identity verified |
|---|---|---|---|---|
| NFL | `nflverse-data/stats_team/week/{y}.parquet` (138 cols, **not wrapped by any `nfl_data_py` function**) | 14,531 team-games 1999–2025, zero nulls | ~0.2–0.5 MB/season, no key | 511/512 exact, mean diff −0.0098 yds |
| CFB | `cfbd.GamesApi.get_game_team_stats(year, week)` — `totalYards` | ~19,000 FBS team-games 2004–2025 | **1 call per (season, week)** ≈ 330 calls one-time | 355/356 exact, median 0.00 |
| PL | Understat `rosters` block — per-player `time`, `xG`, `xA`, `key_passes` | already fetched, **discarded** | **zero extra requests** | expected, unchecked |

`Σ_p(rushing + receiving) == team totalYards` holds to the yard. **A roster sum that
misses by 2.6× is not a noisy estimate — it is a category error.**

Also verified and currently unused:

- `nflverse` `snap_counts/{y}.parquet` — snap share, 2012+, 0.5 s/season.
- Understat `rosters` — per-player minutes and xG/xA, in the response
  `understat_shots.py` already fetches and drops.
- football-data.co.uk `hthg`/`htag`/`htr` — in every cached season CSV, read by no feature module.
- FPL archive: **26 of 46 columns unused**, including `opponent_team` (the cheapest
  available player-model upgrade — every player-rate feature is currently opponent-blind),
  `xP`, `total_points`, `value`, `selected`, `expected_goals_conceded`.

**Blocked:** FBRef (possession, passing, pass attempts) is behind a Cloudflare
challenge — 403 to plain *and* TLS-impersonating clients. Do not build on it.

---

## 4. What was implemented (2026-09-27)

All in `PL_Predictor`, TDD, with regression tests in
`tests/test_player_goals_serving_defects.py` (7 tests, all passing).

### 4.1 `was_home` was dropped on the floor — the served model was not the validated model

`predict_goal_contribution` took no `is_home`. `was_home` *is* in `BASE_FEATURES` and
*is* fitted, but neither `blended_current_form` nor `current_start_features` emits that
key, so the `or 0.0` default scored **every home player with `was_home = 0.0`**. The
fitted home-advantage coefficient contributed a constant offset, not an effect.

Fixed by adding an explicit `is_home` parameter and special-casing the key, mirroring
the pattern `predict_player` already used for its position-rate models
(`player_goals.py:283`).

### 4.2 `max()` is not a sound combiner — replaced with a fitted mixture

```python
pred["anytime_goal_contribution_prob"] = max(
    direct_contribution, pred["anytime_goal_prob"], pred["anytime_assist_prob"])
```

Three problems: it mixes an event with its own components; `max(a,b) = (a+b)/2 + |a-b|/2`
so the upward bias is **half the inter-model disagreement** — it shrinks least toward
the base rate exactly for the players the models are least sure about; and it has no
fitted parameter, so nothing about it was ever validated.

Replaced with `blend_contribution(direct, union, weight)` — a convex mixture whose
weight is grid-searched on the held-out calibration season by `_fit_blend_weight`,
minimising Brier. The Poisson union is Platt-calibrated on the same slice so neither
side of the mixture is privileged. A mixture can land below either component, which is
information about which model to trust where.

Behaviour when the direct model is unavailable (`None`) is unchanged — it returns the
union, exactly as before.

### 4.3 `shots_scale` was dead code

`predict_player` reads a `context` object to scale shot estimates, but
`rank_team_players` had no `context` parameter and `_rank_fixture_players` never passed
one. So `shots_scale == 1.0` on **every live call** and `expected_shots` /
`expected_shots_on_target` were never scaled by the team's own shot volume. This is the
direct cause of the observed `anytime_shot_on_target_prob = 0.9781` on a defender —
the missing divisor was the only thing damping it.

Fixed by threading `context` from `models.get("context")` in `routes.py`.

**Blast radius, corrected after review:** `shots_scale` multiplies into `lam_shots` and
`lam_shots_on_target`, so it moves **three** served fields, not two: `expected_shots`,
`expected_shots_on_target`, and `anytime_shot_on_target_prob` (via
`anytime_probability(lam_shots_on_target)`). The third is exactly the field the 0.9781
defect was observed in, so it is easy to omit — an earlier draft of this spec named only
the first two.
`test_context_scale_reaches_exactly_three_fields_and_no_others` now pins all three as
moving and asserts the other six served fields are bit-identical.

### 4.4 Reverted the decayed O/U 2.5 override

`MARKET_MODEL_OVERRIDES = {"over_2_5": "covariate_poisson"}` → `{}`.

On the live 2026-09-14 manifest the O/U 2.5 ordering **reversed** relative to the study
that installed it:

| model | over_2_5 log loss | Brier | rank |
|---|---|---|---|
| bivariate_poisson | **0.683763** | **0.245133** | 1st |
| dixon_coles | 0.684296 | 0.245331 | 2nd |
| ml_scoreline | 0.689441 | 0.248157 | 3rd |
| covariate_poisson *(was serving)* | 0.689638 | 0.248153 | **4th** |

Every O/U 2.5 prediction was coming from the worst of four candidates, worse than
`ml_scoreline` by 0.000197 — the reverse of the study's ordering — and behind BP by
0.00588, about 20× the original study's margin in the opposite direction. The original
comment said to revisit on a stronger or more consistent result; one appeared.

The per-market override **mechanism** is kept and still tested. A new test pins the
empty default so the revert cannot silently regress.

---

## 5. What was NOT implemented, and why

### 5.1 Correct team-total yardage models (NFL, CFB) — needs the backfill, not a patch

The architecture is settled and cheap; it is a build, not a tune. Not started because
each needs a data backfill that must be run and validated before any model is fitted,
and because the *display* fix is worth doing first.

**Must come first — stop displaying a number the system cannot compute.** The
"Team Yardage Predictions" panel should either be removed or relabelled with its real
meaning, until a team-level model exists. Shipping a corrected yardage model while
leaving the roster-sum panel in place would still show the wrong number.

### 5.2 The dashboard aggregation — deliberately not yet changed

It is the highest-visibility bug, but fixing the *sum* without fixing the *inputs*
produces a differently-wrong number. Ordering that must hold:

1. Remove/relabel the panel (honesty fix, no model needed).
2. Fix NFL's `shift(1)` skew, season filter, and `div_game` hardcode.
3. Add NFL prop backfill + fix the backfill timestamp so accuracy becomes measurable.
4. Train the team-total model; allocate by share.
5. Re-enable the panel fed by the team model.

### 5.3 The selection-bias fix in `manifest.py`

Real and quantified, but changing which metric is published invalidates
`manifest_history.jsonl` comparability and the frontend headline. Needs a decision on
what the number should mean, not just a code change.

---

## 6. Recommended next experiments, PL (screened against the rejected list)

The PL ledger (`docs/AI_CONTINUITY.md`, 21 experiments) has already rejected
player-aggregate features for the **match** model twice — EXP-2026-03 (16 projected
aggregates, regressed all 5 folds) and EXP-2026-21 (8 role-unit fields, worse in 4/5).
Neither rejection transfers to the **G+A classifier**, whose 29 features contain no
team-level term at all. The settings are structurally different: 2,700 rows and 234
collinear form columns versus a well-identified linear model on ~10⁴–10⁵ rows.

Ranked by expected value:

1. **`opponent_team` adjustment for player rates** — the archive column is present and
   entirely unused. Every current player feature is opponent-blind. Zero new data.
2. **Understat `rosters` allocation** — per-player `time`/`xG`/`xA` from a response
   already being fetched and discarded. Enables exact xG reconciliation and a real
   minutes model. Zero new requests.
3. **`opponent_team` × `was_home` interaction in the G+A classifier** — the first
   genuine team-context term that model has ever seen.
4. **Absolute set-piece xG for/against** (not the rejected *share*) crossed with the
   opponent's set-piece concession rate — a different hypothesis about a different
   quantity, with 100% coverage from 2014-15.
5. **Attack×defence product added to `covariate_poisson`, not `ml_scoreline`** — that
   model already has a full attack-team × defence-team interaction structure, so new
   covariates enter linearly with none of the tree-structure/overfitting risk that
   killed the equivalent XGBoost attempts.
6. **Half-time goal features** (`hthg`/`htag`/`htr`) — already in every cached CSV, read
   by nothing, 100% coverage, trivially leak-safe with the existing `shift(1)` idiom.

Every candidate must clear the project's own **two-gate rule**: improve the walk-forward
mean *and* hold on the single most recent season. The ledger records that three separate
tunings converged on the same failure signature, which is itself evidence 2025-26 is
non-stationary.

---

## 7. Carried-forward corrections to earlier findings

Recorded so they are not re-introduced:

- **The CFB conference "corruption" finding was a false positive and is retracted.**
  Verified against the live CFBD API: Big Ten 18, ACC 17, SEC 16, Big 12 16, Sun Belt
  14, American 14, Mid-American 13, Mountain West 10, C-USA 10, Pac-12 8, FBS
  Independents 2 — correct for 2026 after the realignment. USC/UCLA/Washington/Oregon
  really are Big Ten; Stanford/California really are ACC; the Pac-12 really did rebuild
  around Oregon State, Washington State, Boise State, SDSU, Fresno State, Utah State,
  Colorado State and Texas State. The original "ground truth" was a stale
  pre-realignment map. Odd conference *names* in the raw payload (`Michigan`,
  `Wisconsin`, `Ohio`, `Minnesota`, `So. Cal.`) are genuine DIII conferences.
  **No fix needed.**
- **The NFL "non-`_roll` keys" bug does not exist.** Both local HEAD and `origin/main`
  build the fallback as `pd.Series({col: 0.0 for col in PLAYER_FEATURE_COLUMNS})`,
  correctly. That bug is **CFB-only** (`CFB_Predictor/src/cfb_predictor/api/routes.py:501`),
  where the fallback dict is written with un-suffixed keys.
- **NFL's real unlisted bug is the `shift(1)` train/serve skew** in
  `player_usage.py:17` (training: `shift(1).rolling(...)`, excluding the latest game)
  vs `:33-34` (serving: `history.tail(5)`, including it). Same column name, different
  quantity. Quantified on Aaron Rodgers: served 254.00, training-consistent 249.00.
- **PL does have a player-minutes model, a player-xG/xA model, and a fantasy-points
  model** — all three serve live numbers. The "absent" claims were wrong; what is
  genuinely absent is a **clean-sheet model** and **opponent-scaled keeper saves**.
- **`PL_Predictor/.github\nF1_Predictor` is a real directory, not a symlink**, whose name
  contains a literal backslash-n, holding a 5-deep chain of empty dirs. Untracked,
  unignored, invisible to `ls`/`find`/`git status`. Harmless but a footgun; fix with
  `rm -rf '.github\nF1_Predictor'`.
- **`PL_Predictor` main is 54 commits behind `origin/main`** and the tree is dirty. Any
  PR must branch off `origin/main` and exclude the 4 tracked `models/*_xgb.json`
  binaries, which are dirty from a retrain and would ship out of sync with
  `manifest.json`.

---

## 8. Prompt for a fresh Claude Code review session

The full self-contained review prompt lives at:

**`predictor-hub/docs/superpowers/plans/2026-09-27-player-model-review-prompt.md`**

Copy everything below the divider in that file into a new session. It is written
to need no prior context from the session that produced the work: it carries the
repo layout, the four-layer problem statement, the live measurements, exactly
what was implemented and why, the retracted findings the reviewer must not
re-litigate, the project's own promotion conventions, the environment gotchas
(stale local `main`s, uncommitted work, worktree conflicts, the VPS-vs-Azure
deployment split), and the four things we most want challenged.
