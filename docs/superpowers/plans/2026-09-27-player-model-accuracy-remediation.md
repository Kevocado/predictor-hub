# Player-Model Accuracy Remediation — Implementation Plan

> **For agentic workers:** execute tasks in order. Each step names the exact command and
> the exact expected condition; treat a mismatch as stop-and-report. Checkboxes are
> tracking only — check one off after its Expected condition is confirmed, not just after
> running the command. Steps that touch a public deployment must not run until the prior
> task's holdout metrics have been read.
>
> **Spec:** `docs/superpowers/specs/2026-09-27-player-model-accuracy-design.md`
> **Evidence:** `/Users/sigey/Documents/Projects.nosync/.superpowers/audit-2026-09-27-total-yards.md`

**Goal:** Make the "Total Yards" figure the product of a real team-level model that
reconciles to the sum of its players, and make every player model measurable and
honest. Today the figure is a whole-roster sum of mis-calibrated per-player projections
and is wrong by 2.2–3.2× on every single team in both American-football leagues.

**Tech stack:** unchanged. XGBoost / scikit-learn / pandas as each repo already uses.
New data sources are read-only, keyless (NFL) or already-funded (CFBD, 1 call per
season-week).

## Global Constraints

- **Do not merge anything to a local `main` that is behind `origin/main`.** As of
  2026-09-27: `PL_Predictor` is 54 behind, `NFL_Predictor` 37, `Sports_Predictor` 25,
  `CFB_Predictor` 33. Branch off `origin/main` in every repo.
- **Do not clobber uncommitted work.** `CFB_Predictor/.github/workflows/deploy-azure-cfb.yml`,
  `PL_Predictor/.github/workflows/deploy-azure.yml` and
  `Sports_Predictor/{.github/workflows/deploy-azure.yml,src/api/client.ts}` are dirty and
  look like in-flight VPS deployment work. `PL_Predictor` also has 4 dirty
  `models/*_xgb.json` binaries from a retrain.
- **Never commit model binaries in a source PR.** In `PL_Predictor` the `models/*.json`
  files are tracked; exclude them or `manifest.json` ships out of sync with them.
- **Respect each project's own promotion rule.** `PL_Predictor` has a two-gate rule:
  improve the walk-forward mean AND hold on the single most recent season. Its ledger
  records three separate tunings that improved the mean and regressed 2025-26, which it
  correctly reads as evidence that 2025-26 is non-stationary. Do not relax this.
- **Never delete a failed experiment from `AI_CONTINUITY.md`.** The repo's own rule:
  negative evidence prevents repeated work.
- **The order of Task 1 → Task 2 is load-bearing.** Fixing the display before the
  players produces a differently-wrong number with more apparent authority.
- **CFBD call budget.** The `X-CallLimit-Remaining` header was observed at ~2,200
  remaining, implying a cap roughly 2× the 1,000/month asserted in
  `CFB_Predictor/src/cfb_predictor/config.py`. The Task 4 backfill is ~330 calls
  **one-time**. It must never run on a schedule. Confirm the remaining budget before
  starting and abort if it is under 400.

---

## Task 1: Stop displaying a number the system cannot compute — **DONE 2026-09-27**

> `Sports_Predictor` commit `b725f36`. The "Team Yardage Predictions" panel summed each
> player's single yardage field and labelled it "Total". Fixed by relabelling and showing
> the components; the correct team-level model is still the real fix and is not built.

**Decision taken, since the owner delegated it: relabel and decompose, do not delete.**
Deleting would have thrown away real model output — projected QB passing, RB rushing and WR
receiving are genuine predictions — while a panel that says "by Market" and states the
caveat keeps the information and removes the false claim.

**Why the number could never have been right**, confirmed against the model rather than
inferred: `models/player_props.py::POSITION_MARKETS` gives each position exactly **one**
yardage market (QB passing, RB rushing, WR/TE receiving). So the "total" added a QB's
passing to a receiving corps's receiving and an RB's rushing. Two further errors compound
it: `keyYardage` returns whichever field exists, so a player projected for two markets
contributes only the first; and the sum covers the whole roster rather than the expected
on-field lineup.

Measured on live CFB week 5 (2112 props): QB mean passing 130.0, RB mean rushing 35.4 over
662 rows, WR mean receiving 32.4 over 1157; Air Force has 18 projected rushers and 3
receivers. Summing a roster the old way reproduces the ~841 median that prompted this work
against a real figure of ~300-450.

What shipped: each market separately with its contributing-player count, heading "by
Market", and an in-panel statement that these are not team total yards and cover the
roster rather than the on-field lineup. 8 new tests, including that the old "Total: 480"
string is gone. Full frontend suite 83 passed, oxlint clean, build clean.

**Still open, and it is the actual fix:** the architecture is project-team-total then
allocate by share. NFL now has a team-week yardage source that reconciles 544/544
(Task 5) but that is *actuals*; a team-level yardage *projection* does not exist. CFB's
equivalent is blocked behind Task 4's player-side reconciliation.

## Task 2: NFL — fix the serving defects that make the number wrong at the source — **DONE 2026-09-27**

> Branch `fix/player-prop-serving-defects` off `origin/main`, worktree `nfl-fix-worktree`.
> Commit `0628c6d`. **208 passed, 15 skipped.**
>
> Four train/serve skews fixed, all with tests:
> 1. `build_features_for_player` used `tail(5)` (includes the latest game) where
>    training used `shift(1).rolling(...)` (excludes it). The repo's own two tests
>    asserted different values for the same player and week — 82 vs 81.5 — and that
>    contradiction *was* the bug.
> 2. No season filter: 416 of 458 non-zero live rows were predicted off 2024 data.
> 3. The fabricated all-zero feature row: 430 of 880 rows (48.9%) were the origin
>    intercept, serving 62.592 passing yards to real quarterbacks. Now skipped.
> 4. `div_game` hardcoded 0 while training filled it from the schedule.

## Task 4: CFB — backfill team-game yardage — **DONE 2026-09-27, BACKFILL RUN 2026-09-28**

> Branch `fix/roster-fallback-feature-keys` off `origin/main`, worktree `cfb-fix-worktree`.
> Commits `28217b2`, `9ca36db`, `c4beaf2`. **243 passed, 16 skipped, 0 xfailed.**
> Pushed to `fix/roster-fallback-feature-keys`.

The blocking bug is found and fixed. **The cause was the join key, not a parsing fault.**

`reconcile_against_players` grouped both frames on `(season, week, team)`. That key is
not unique — a team can play twice in one week, and CFBD's `week` request argument
over-returns — so the player frame summed *several games'* players into one figure and
each individual game was then compared against the whole lot. `_flatten_player_game_stats`
already keyed rows on `(game_id, player_id)` but **dropped `game_id` on the way out**, which
is precisely what forced the week key.

Measured on cached 2023 week-1 responses, 272 team-games after dropping 84 unplaceable
non-FBS games (0 further API calls):

| | before (week-keyed) | after (game-keyed) |
|---|---|---|
| exact | 58 / 272 | 161 / 272 |
| within 5 yards | - | 252 / 272 (92.6%) |
| within 10 yards | 80 / 272 | 260 / 272 (95.6%) |
| median abs diff | 336.00 | **0.00** |
| max abs diff | 1177.0 | **29.0** |
| team-games surviving the join | 272 / 272 | 272 / 272 |

**Two things deliberately not claimed.** The identity is *not* now exact: 11 of the 12
residual offenders run the same direction (player sum exceeds the team's `totalYards`),
pointing at a definitional difference in CFBD's team total — net-rushing treatment of
sacks being the obvious candidate. NFL's equivalent is still 544/544 exact, so this is a
CFB-source property, not a shared bug. And the test's old docstring claimed "355 of 356";
that was measured on the week-keyed join and was **false** (58 of 272 on the same week).

The network test is no longer `xfail`, with a tolerance reflecting what CFBD supports
(>=95% within 10 yards, median 0, max <= 35). The deterministic guard is the new offline
`test_reconcile_keys_on_the_game_not_the_week`, which needs no live API. The join also
moved to `how="left"` — an inner join was silently dropping team-games whose players were
not returned, and a dropped row reads as "reconciled" in any count.

- [x] **The backfill is built and has run** — `01f1726` shipped
      `scripts/backfill_team_stats.py`; the run completed 2026-09-28 at **351 CFBD
      calls** for 2004-2025, yielding **42,190 team-games across 21,095 games**
      (152s, 2.3 calls/s). See Task 4c for what the 22-season data then falsified.

      A script rather than a route, deliberately: CFBD's API is metered, the
      reconciliation has no serving caller, and a `GET` that quietly spends ~330
      calls is a foot-gun with an HTTP trigger. It dry-runs by default.

      Making it re-runnable for free turned out to be load-bearing. An empty week
      used to be *skipped* rather than recorded, so it was re-requested forever —
      and most seasons end before week 15, so every retry of an interrupted backfill
      re-bought every dead week. Empty weeks are tombstoned now.

- [ ] **Open, and deliberately not done: the container still starts cold.**
      `Dockerfile` creates `data/cache/{games,teams,player_stats,odds}` and nothing
      seeds them, and `data/cache/` is gitignored — so this backfill populated a
      *local* cache and does **not** reach production. A seeded warm cache on the VPS
      is a separate change: it needs either a one-off operator step on the host or a
      startup job, and the second has to be idempotent about a metered API. Also
      unaddressed: the Azure workflow does not pass `CFBD_API_KEY` at all, and does
      not invoke the script. Neither blocks anything, since the reconciliation has no
      serving caller — but a reader could easily assume the backfill reached
      production, so it is written down.

## Task 4b: CFB — review findings, and the week machinery that is now load-bearing for nothing

> Follow-up to Task 4 after an adversarial review of commit `6938fee`. Two critical and
> three important findings, all fixed and pushed. One design smell remains open.

**Fixed — the `game_id` fix never reached production.** `player_stats.fetch_weekly_player_stats`
read its parquet cache with a bare `read_parquet` and no column check, so every cache written
before `game_id` joined `KEEP_COLUMNS` came back without it and the reconciliation fell
through to `(season, week, team)` — the exact bug the commit fixed, silently. Verified:
`CFB_Predictor/data/cache/player_stats/` holds nine parquet files of 12k–34k rows and **none**
has `game_id`. The commit's numbers had been produced by calling the private flatteners
directly, which always emit it, so **the test proved the fix on a path production never
takes.** Now: `player_stats._read_cache` validates `KEEP_COLUMNS` and refetches on mismatch
(the same lesson already applied to `team_stats._read_cache`), `reconcile_against_players`
**raises** without `game_id` unless `allow_week_key=True`, and the network test goes through
the production loader.

**Fixed — a `min_count` guard that never fired.** `groupby.sum()` treats an all-NaN column as
0, so a game where no player had a `receiving_yards` value produced a *real zero* and the
`min_count=len(summed)` on the axis sum saw two populated values and never objected. A game
with only rushing rows reported `player_total_yards = 90.0` instead of missing — a partial
figure that looks complete, which is worse than an absent one. Found by mutating that
`min_count` to 1 and finding the offline suite did not care. Latent on real data (0 missing
sums before and after; live numbers unchanged), but real.

**Fixed — `attach_schedule_weeks` still back-filled `requested_week` on the cold-start path**,
which is the stacking bug the rest of the function prevents, and returned without the
`dropped_unplaceable` attribute every other path sets. It now raises.

**Fixed — uniqueness now enforced**, not assumed. It held empirically (272/272 week 1;
600/600 across weeks 1+2 with zero `game_id` overlap) but a repeated stanza would duplicate
the output row and double-count downstream rather than fan out, so nothing would have
looked wrong.

**Fixed — three false measurements in the docstrings**, corrected against measurement with the
retraction left in place: the team-side identity is 271/272 (not 355/356), the player
reconciliation is 161/272 exact (not "355 of 356, median error 0.00, sole outlier Robert
Morris at -14"), and the 42 absent games are **FCS-vs-FCS** because
`get_games(classification="fbs")` matches games with at least one FBS team — so the earlier
"Air Force vs Robert Morris is one of them" was wrong, and that game reconciles normally.

**Fixed — the offline guard did not guard its own mutation.** `keys = ["game_id"]`, dropping
`team`, turned 161/272 exact into 0/272 with a median error of 369 yards and all offline tests
passed, because every fixture used one team per game. All four surviving mutants are now
caught, verified by mutation.

- [x] **The week is no longer required, and the frame is 31% bigger for it** — `da0f787`.

      Since the join is keyed on `game_id`, the week was never consulted, but
      `reconcile_against_players` still demanded one, so callers had to run
      `attach_schedule_weeks` — which drops any game absent from the schedule.
      Measured on the same cached 2023 week-1 responses:

      | team frame | rows | exact | within 10 | median | max |
      |---|---|---|---|---|---|
      | via `attach_schedule_weeks` | 272 | 161 | 260 (95.6%) | 0.00 | 29.0 |
      | raw, no week attachment | **356** | **216** | **338 (94.9%)** | **0.00** | 30.0 |

      78 more team-games for the same quality. The dropped rows were the FCS games —
      real games with real box scores, excluded only because they are absent from an
      *FBS-filtered schedule*, which is a property of the schedule rather than of the
      data. The week is now required only on the week-keyed path, which is the
      non-unique path `game_id` exists to replace. `attach_schedule_weeks` is unchanged
      for callers that do need a week, though its own contract is the weaker of the two:
      CFBD labels **every** bowl `week: 1`, so the cached 2023 schedule's week 1 spans
      2023-08-26 to 2024-01-09 and the week it recovers is wrong for a third of the frame.

## Task 5: NFL — add the team-week yardage source — **DONE 2026-09-27**

> Commit `9e7e465` on `fix/player-prop-serving-defects`. **218 passed, 15 skipped**
> offline; both network tests pass.
>
> `data/team_stats.py`, 10 tests. Target is `passing_yards + rushing_yards`;
> `receiving_yards` deliberately excluded because it is already inside
> `passing_yards`, and adding it would inflate a team total by ~200.
>
> **Identity verified on real data, two sources:**
> - `stats_team_week` vs `stats_player_week` (same release family):
>   **544/544 exact, max |diff| 0.0**
> - `stats_team_week` vs `player_stats` via nfl_data_py: 543/544, one 13-yard
>   exception at IND 2024 week 8
>
> Both pinned as tests. `KEEP_COLUMNS` was written from the real asset after a
> guessed list was caught by the schema guard — there is no `turnovers` or
> `fumbles_lost` column, only per-phase `*_fumbles_lost` and `fumbles_lost_total`.
>
> **The NFL side is unblocked and the CFB side is not.** A team-level yardage model
> is buildable now for NFL; it should wait for CFB until the join is fixed.

## Task 6: CFB — fix the roster-fallback feature-row bug — **DONE 2026-09-27**

> Commit `68b0813`. 221 passed, 16 skipped at the time of commit.
>
> Two faults, not one. The placeholder was keyed `passing_yards` etc. while
> `predict_props` reads `passing_yards_roll` etc., so every key missed and
> `reindex().fillna(0)` produced the origin — 1497 of 2112 rows (71%) shared one
> `anytime_td_prob`. And re-keying alone would still have produced a row of zeros,
> which is the origin whatever it is keyed with. Both fixed; keys now derive from
> `PLAYER_FEATURE_COLUMNS` so they cannot drift again.
>
> Divergence from the sibling NFL route, which now *skips* such players rather than
> substituting anything: skipping is more honest and is recorded as the preferred
> direction, but changing CFB's served row count is a visible contract change and was
> not made unilaterally.

## Task 3: NFL — make accuracy measurable at all — **STEPS 2+3 DONE, STEP 1 IS YOUR CALL**

> **Correction, 2026-09-27.** This task was originally written to add a `backfilled`
> column so backfilled rows would count. That column, plus a widened
> `get_track_record` filter, was implemented — and then **reverted**. Three existing
> tests failed and turned out to be pinning a deliberate, documented decision in
> `docs/superpowers/reports/2026-09-25-predictor-pregame-feed.md`.
>
> The repo's reasoning is sound: derive pre-game-ness from `snapshotted_at` versus
> `commence_time` rather than storing a flag, because **a stored flag can drift out of
> step with the timestamps**. The rule is also substantively correct —
> `record_resolved_game_predictions`'s docstring requires the caller's prediction to
> come from strictly pre-game information, and `routes.py` in fact recomputes it at
> backfill time from current weights and current data. That is a reconstruction, not a
> frozen pre-game pick. Counting it would inflate the track record with numbers that
> were never actually made before kickoff.
>
> **So `n_resolved: 0` is the correct answer.** The defects sit upstream of the metric
> and neither is a code change. Do not re-attempt the schema change.

**Files:** none in `src/`. This is now an operations + documentation task.

- [ ] **Step 1: Stop the container missing the pre-kickoff window** — **YOUR DECISION, not
      blocked.** Re-classified 2026-09-28: I had filed all three of this task's steps as
      "blocked on upstream", which was wrong for two of them. Step 1 is an operations
      choice with a real cost, and it is the **binding constraint** on prop accuracy
      (see Step 2's evidence) — the 404 is not. Nothing is blocking it except the
      decision itself, so the useful next step is for you to pick (a), (b) or (c).

> **RETRACTED 2026-09-28 — do not act on this step, and do not pick (a), (b) or (c).** The
> "binding constraint" ruling above is wrong: `min-replicas: 0` does not describe the live
> deployment, which is a Compose service that cannot scale to zero, and pre-kickoff
> capture is demonstrably working (14 resolved on 2026 week 3). This step is a no-op.
> See "Correction 2026-09-28" at the end of this plan.

The tracking loop runs on startup and every `_TRACKING_INTERVAL_SECONDS` after. On Azure
Container Apps with min-replicas 0, a scale-down means the next tick happens after
kickoff, so nothing is snapshotted. Options, cheapest first:

- (a) Set `min-replicas: 1` through the season. Costs money.
- (b) Add a timer-triggered job that ticks the API before each gameweek's first kickoff.
- (c) Accept it, on the grounds that the rule is right and the alternative is counting
  reconstructions.

Reproduce against: the VPS reported `n_resolved 0 / n_rebuilt 33` while an older warm
container reported 30 resolved for the same 33 games.

- [x] **Step 2: Document the upstream data blocker so it is not re-investigated** — done
      2026-09-28, NFL #11. Re-verified independently rather than on the plan's word:

      ```
      player_stats_2024.parquet -> 302    2025 -> 404    2026 -> 404
      season 2024: 5597 rows | season 2025: 0 rows | season 2026: 0 rows  (no exception)
      ```

      It **fails silently** — `hub_cache.cached_frame` returns an empty frame by design
      (dashes, not an error), so `n_resolved: 0` is four hops from a 404 with no log
      line above the default threshold. The tick now reports it at WARNING once per
      tick, so the track record has a stated cause rather than only a document.

      `docs/player-prop-accuracy-blocker.md` records the URLs, the verified behaviour,
      and why a prop backfill is the wrong fix (a reconstruction, not a frozen pre-game
      pick — the same rule that reverted the earlier `backfilled` column).

      **The window, not the file, is the binding constraint.** Even with the data
      published, `min-replicas: 0` means no genuine pre-game snapshot exists to resolve,
      so fixing the 404 alone would produce `n_resolved: 0` still. Sequence matters:
      Step 1 first, then let real snapshots accumulate for a gameweek, then prop accuracy
      exists. Do not backfill to fill the gap.

> **RETRACTED 2026-09-28.** The paragraph above inverts the constraint order: the 404 *is*
> the binding constraint, and the window it describes is not the live deployment. Fix the
> 404 first — which is what this step's own measurement says — then let snapshots
> accumulate. See "Correction 2026-09-28" at the end of this plan.

nflverse returns 404 for `player_stats_2025.parquet` and `player_stats_2026.parquet`
(re-verified independently 2026-09-27). `reconcile_player_prop_predictions` therefore
returns 0 at its first line every tick, and prop accuracy is unmeasurable however warm
the container is. Record both URLs in `docs/` and add a pointer comment at the call site.

- [x] **Step 3: Do NOT add a prop backfill path on the current data** — reaffirmed, and
      now evidenced rather than asserted: `docs/player-prop-accuracy-blocker.md` records
      why. A reconstruction is not a pre-game pick, so a backfill would inflate the
      track record with numbers never made before kickoff.

An earlier draft proposed backfilling props the way games are backfilled. Withheld
deliberately: props cannot be snapshotted at all while nflverse has no current-season
data, and once it does, a backfill would still be a reconstruction that the same rule
excludes. Revisit only if genuine pre-kickoff prop snapshots are missed for a reason
other than missing data.

## Task 7: PL — evaluate the blend change before it goes live — **DONE 2026-09-27**

> **Outcome: gate 1 PASS, gate 2 mixed. Not promoted to a validated change; shipped as a
> correctness fix with a favourable but underpowered evaluation.** Full write-up is
> `PL_Predictor/docs/AI_CONTINUITY.md` EXP-2026-24.
>
> Walk-forward mean, blend vs the `max(...)` incumbent it replaced:
> brier **0.047969** vs 0.048912, log loss **0.168174** vs 0.169001, average precision
> **0.286966** vs 0.277357, ECE 0.009534 vs 0.013127. Better on all four, in 2 of 2
> folds. On the most recent season it wins brier, AP and ECE (35% better) but
> **loses log loss by 0.000269**.
>
> **The binding limitation is fold count.** `build_goal_contribution_frame` yields only
> 4 seasons (2022-23..2025-26) because FPL's xG/xA fields start in 2022-23, so the
> G+A model can produce at most **2 folds** against the match model's 5. Gate 2 is one
> of those 2, so the two gates are not independent. A 2-fold mean is not the evidence
> standard this project set for itself.
>
> Unblocking condition, named: more seasons of FPL xG/xA coverage, or a genuine
> prospective track. Until then this is a *cannot-yet-confirm*, not a rejection and not
> a validation.

**Files:** `PL_Predictor/src/pl_predictor/evaluate/blend_validation.py` (new),
`PL_Predictor/tests/test_blend_validation.py` (new, 8 tests),
`PL_Predictor/docs/AI_CONTINUITY.md` (EXP-2026-24)

**This is the most important unfinished item in the remediation.** The `was_home` and
`blend_contribution` changes are implemented and unit-tested, but **no walk-forward
evaluation was run.** Worse, the direct G+A classifier is currently *dark* in
production — 0 of 160 live rows come from it, because
`_get_ready_goal_contribution_model()` returns `None` until the 24h warm-up completes.
It becomes live the moment the cache warms.

> **Review feedback applied 2026-09-27.** The in-code comment calls the calibration
> season "held-out". It is not held out three times over: `_fit_blend_weight` fits the
> union's Platt calibrator, grid-searches the blend weight, **and** scores by Brier on
> the same slice that one function up fitted the direct model's own Platt calibrator.
> Three fits, one slice, no further holdout. A walk-forward comparison on *other* folds
> is therefore required before the fitted weight can be trusted to generalise — not
> merely as hygiene, but because nothing about the blend has been scored on data that
> did not shape it.

- [x] **Step 1: Record the current blend weight**

```bash
cd /Users/sigey/Documents/Projects.nosync/PL_Predictor
PYTHONPATH=src .venv/bin/python -c "
from pl_predictor.models.player_goals import fit_goal_contribution_model
m = fit_goal_contribution_model()
print('blend_weight =', m.get('blend_weight'))
"
```

- [x] **Step 2: Add four arms to `_evaluate_fold`, not three**

Score `direct_enhanced`, `poisson_union_calibrated`, the old `max(...)` composite, and
the new `blend_contribution(...)` on the same folds with `_metrics` (brier, log loss,
average precision, ece). **The old `max` must be a scored baseline arm** — a
comparison against the union alone cannot answer whether the mixture is an improvement.

> **Harness written 2026-09-27:** `src/pl_predictor/evaluate/blend_validation.py`, with
> 8 tests in `tests/test_blend_validation.py`. A **separate module** rather than an edit
> to `goal_contribution_research.py`, so that module's already-reported numbers stay
> reproducible. It splits the calibration season chronologically in half — calibrators
> on the first half, blend weight grid-searched on the second, score only on the
> untouched test season — so nothing about the reported number shaped it. The incumbent
> arm reproduces production's `max(...)` verbatim, including the raw uncalibrated Poisson
> components `predict_player` serves. The tests pin the harness, not the result: that
> `_poisson_components` and `_poisson_union` agree, that the grid reaches both endpoints,
> and that `incumbent_max` really is a max.

- [x] **Step 3: Fit the weight on `calibration`, score on `test` — never the same rows**

This is the specific change the review forces. `_evaluate_fold` already splits
`train` / `calibration` / `test`. The blend weight must be fitted on `calibration` and
applied to `test`. If the production `_fit_blend_weight` cannot express that split, say
so in the write-up rather than reporting a number that is in-sample of its own
selection.

- [x] **Step 4: Apply the two-gate rule**

Log to `AI_CONTINUITY.md` as a new `EXP-2026-2x` entry with per-fold numbers, whether
the walk-forward mean improves, and whether the newest season holds. **Do not promote on
a walk-forward mean alone.**

- [x] **Step 5: Keep the change behind a gate until this lands**

`blend_contribution` is live-safe relative to `max()` — with the direct model absent it
returns the union exactly as before — but it must not be *endorsed* until Step 4 passes.

- [x] **Step 6: `was_home` precedence — resolved, do not revisit**

`is_home` wins over a `was_home` in `rates`, deliberately. Provenance: `is_home`
describes the fixture being predicted and is known exactly, whereas any `was_home` in
the feature dicts was built by `blended_current_form` from the player's *historical*
rows and describes a past match. This is the **opposite** precedence to
`predict_player`'s `dict.get` default, and
`test_was_home_argument_overrides_a_conflicting_rates_value` pins it with a genuinely
conflicting value. The earlier version of that test passed `rates={}` and therefore
tested nothing; it has been replaced, and a mutation check confirms all three
`was_home` tests fail when the fix is removed.

---

## Task 7b: PL — do NOT re-add a bivariate_poisson O/U 2.5 override

**Raised by review 2026-09-27, investigated, closed.** Recorded so the question is not
re-opened from the single-holdout table again.

The review correctly observed that the same `models/manifest.json` table justifying the
`covariate_poisson` revert also shows `bivariate_poisson` beating `ml_scoreline` on
O/U 2.5 by 0.0057 log loss — 29× the margin by which `covariate_poisson` trailed — and
asked whether a *different* override is now indicated by the same evidence.

**It is not.** Re-ran `python -m pl_predictor.evaluate.model_selection_by_segment` on
2026-09-27 (post-OPS-2026-03 xG fix, so these are current numbers, not the stale
2026-08-25 CSV). `overall` segment, `over_2_5`:

| val season | ml_scoreline | dixon_coles | bivariate_poisson | ml − bp |
|---|---|---|---|---|
| 2021-22 | 0.698568 | 0.673820 | 0.673966 | **+0.024603** |
| 2022-23 | 0.682316 | 0.696717 | 0.696310 | −0.013995 |
| 2023-24 | 0.665695 | 0.707683 | 0.706427 | **−0.040732** |
| 2024-25 | 0.676198 | 0.681429 | 0.681470 | −0.005272 |
| 2025-26 | 0.690289 | 0.682013 | 0.681907 | +0.008383 |
| **mean** | **0.682613** | 0.688332 | 0.688016 | **+0.005403** |

Brier: `ml_scoreline` 0.244842 vs `bivariate_poisson` 0.247338 — ml better by 0.002495.
BP wins log loss in only **2 of 5 folds**.

**This is a textbook two-gate split, and BP fails the gate that matters:**

| gate | requirement | result |
|---|---|---|
| 1 — walk-forward mean | must improve | **FAILS.** ml better by 0.005403 |
| 2 — most recent season | must hold | passes. BP better on 2025-26 by 0.008383 |

The rule requires **both**. Passing gate 2 on one season while losing gate 1 by 0.0054
across five is the same non-monotonic signature that sank EXP-2026-16's original
candidate, inverted — and the rule is symmetric in the only way that matters: both
gates must clear.

This also reconciles the apparent conflict the review flagged. EXP-2026-14's
"ml_scoreline wins every market" and the holdout table's "bivariate_poisson wins
O/U 2.5" were never in conflict — different sample sizes, and the larger one favours
`ml_scoreline`. On the fresh run `ml_scoreline` is also best on the `overall` segment
for RPS (0.199654 vs 0.209671 / 0.209729), 1X2 Brier, log loss, ECE (0.037 vs 0.055 /
0.059), exact-scoreline log loss, and BTTS.

**Action:** none. `MARKET_MODEL_OVERRIDES = {}` stands. If a future retrain puts
`bivariate_poisson` ahead on the *walk-forward mean* as well as the newest season, that
is a different claim and warrants its own experiment — argued from the 5-fold, never
from the holdout alone.

---

## Task 8: PL — the unused-data features — **STEP 1 DONE, REST SCOPED**

Six candidates, screened against the rejected list so none repeats EXP-2026-03 /
04 / 11 / 17 / 21. Step 1 is built and evaluated; Steps 2-7 are not. Each needs its
own two-gate evaluation and the ledger's own history is a record of batches
regressing, so they must not be bundled.

**Verified available and unused, 2026-09-27:** `opponent_team` exists in the FPL
archive and is referenced **once** in all of `src/` -- as a validation check in
`data/fpl_api.py:235`, never as a model input. Every player-rate feature is
therefore opponent-blind.

- [x] **Step 1 (highest value): opponent defensive strength for player rates** -- **BUILT,
  EVALUATED AND PROMOTED 2026-09-27.** Both two-gate rules PASS on 4 folds, winning 4/4 on
  log loss and 4/4 on brier. Ledger: EXP-2026-25.

  Chosen construction: a team-level defensive rating from the FPL archive's *own* fixture
  results, joined to each player-game via `opponent_team`. `opponent_defence_last{3,5,10}`
  = the opponent's goals conceded minus its own goals scored over **prior** matches only.

  **This avoided the cross-source join the plan expected, and that is the main design
  finding.** The archive already ships `team_h_score`/`team_a_score` on every player row,
  always from the fixture's own perspective, so `was_home` attributes them correctly with no
  second source -- no `to_canonical` mapping whose coverage has to be measured. Measured
  2024-25: 760 team-fixture keys (exactly 2 x 380), zero conflicting score pairs.
  `opponent_team` is a season-local integer appearing only as somebody's opponent, so it is
  recovered offline as "the club that never meets this id" -- verified a complete,
  unambiguous bijection on all 6 completed seasons. Ambiguous or non-bijective seasons are
  dropped whole, because a partial map is indistinguishable from a correct one until it
  quietly mis-rates players.

  Result: log loss 0.179683 -> **0.178896** walk-forward mean, winning **4 of 4 folds** on
  both log loss and brier. Gate 1 PASS. Gate 2 (2025-26: 0.162624 vs 0.163033) PASS. This is
  the first G+A experiment with more than 2 folds -- 6 seasons are usable because the feature
  needs no FPL xG coverage -- and it beats the rejected bivariate_poisson override's 2-of-5.

  **Step 1b (the part that actually mattered) is also done.** Passing the gate was never the
  blocker; servability was. The design is now **one rating function, two adapters**:
  `rate_team_matches` is the only place a rating is computed, over a generic
  `(season, team, date, goals_for, goals_against)` frame. Fitting feeds it the FPL archive;
  serving feeds it `rolling_form.to_team_perspective`. `rate_opponents` does not reimplement
  the rating for an upcoming fixture -- it appends a placeholder row and lets the same function
  rate it, so a second definition cannot exist.

  The two adapters were measured against each other on 2024-25: **max per-club difference
  0.0000 goals/match, correlation 1.0000.** Only 18 of 20 clubs are comparable, and the two
  that drop out are Man Utd and Tottenham, both `to_canonical` misses -- which is the whole
  argument for the archive-only fitting path.

  Three real defects were found while making it servable, all fixed and all tested:
  (1) a placeholder dated the same as a real match sorted *after* it and therefore **saw** the
  match being rated -- asking about a played match leaked it; (2) a **season-boundary skew**,
  where serving grouped by club across seasons so gameweek 1 inherited last season's rating,
  a value the fitted model has never seen an example of -- both sides now group by season and
  the season comes from the fixture's own kickoff date; (3) `_get_matches_df` mixes season
  label formats (`"2024-25"` from raw CSVs, `"2026-2027"` from `fetch_current_season_partial`).

  Production: 37 fitted columns, 3 of them opponent terms, verified by assertion rather than
  assumed. 9 serving-path tests.

  **Gate amendments made** (see EXP-2026-27 and Task 11): gate 1 now also requires a
  **majority of folds** and, the gate that actually does the work, a **noise margin** --
  the improvement must exceed the metric's own measured noise. This experiment's paired
  half-width is 0.000161 against an improvement of 0.000787, and every fold individually
  exceeds its own half-width, so it clears both comfortably.

  **Correction worth recording:** an earlier note here cited the rejected
  bivariate_poisson override as "2 of 5 folds" and claimed a majority rule would have caught
  it. EXP-2026-16's own table shows **3 of 5** (losing 2023-24 and 2024-25), so a majority
  rule would *not* have caught it. The noise margin is the gate that does. Retracted in
  EXP-2026-27.

- [ ] **Step 2: per-player minutes — PREMISE REJECTED 2026-09-27, re-scope before building**

  The plan previously said: *"per-player `time` (minutes), `xG`, `xA`, `key_passes` from a
  response `understat_shots.py` already fetches and discards (it reads only `data["shots"]`).
  **Zero extra HTTP requests.**"*

  **Both halves of that are wrong**, verified against the installed library rather than assumed:

  - `penaltyblog.scrapers.Understat` has **no roster method at all**. Its full method set is
    `get_fixtures`, `get_shots`, `get_fixture_info`, `get_player_season`, `get_player_shots`.
  - `get_shots` hits `https://understat.com/getMatchData/{id}` — a **JSON shots endpoint**, not
    the HTML match page. Confirmed by the cached responses: 2,112+ CSVs whose columns are
    `id, competition, season, datetime, minute, result, x, y, x_g, player, h_a, player_id,
    situation, shot_type, match_id, team_home, team_away, goals_home, goals_away, date,
    player_assisted, last_action` — shot rows only, **no roster and no minutes**.
  - `get_fixture_info` fetches the HTML page but parses only the `match_info` variable, not
    Understat's `rosters` variable. And the project never calls it anyway.

  So minutes would cost **new HTTP requests**, not zero.

  **And the need is narrower than the plan claimed.** The FPL archive already carries `minutes`
  per player-game, and `build_historical_player_form` rolls it extensively. What is genuinely
  missing is not minutes data but a **P(minutes) model**: there is a P(start) classifier and no
  model of how many minutes a starter actually plays. The extra value Understat's `rosters`
  would add is bench minutes for players who did not appear at all — which is a *cold-start*
  refinement, not the core gap.

  Re-scope before building: the honest version of this step is a P(minutes) model fitted on the
  archive's existing `minutes`, evaluated under the amended rule in
  `src/pl_predictor/evaluate/promotion_rule.py`. Only if that is rejected should Understat
  `rosters` be considered, and then as a priced cost, not a free one.

  **Re-scope, 2026-09-28 — the gap is confirmed and located, the build is not started.**
  The claim "there is a P(start) classifier and no model of how many minutes a starter plays"
  is **verified in `models/player_goals.py`**:

  ```python
  STARTER_MINUTES = 82.9
  SUBSTITUTE_MINUTES = 39.9
  expected_minutes = probability_start * STARTER_MINUTES + (1 - probability_start) * probability_sub * SUBSTITUTE_MINUTES
  ```

  So it is a **two-point mixture with two hard-coded constants**. A starter withdrawn at
  60' and one who plays the full 90 both receive 82.9, and a substitute's expected
  minutes ignores how long substitutes actually last.

  **Why it is a real lever, not cosmetic:** `minutes_fraction` multiplies

  ```
  lam_goals   = goals_estimate   * strength_multiplier * minutes_fraction * availability
  lam_assists = assists_estimate * strength_multiplier * minutes_fraction * availability
  ```

  so a 10% error in `minutes_fraction` is a 10% error in every lambda the player model
  produces. There is no averaging-out across terms.

  **Archive confirmed usable:** 254,510 player-games across 11 seasons of
  `data/cache/fpl_history/*.csv`, with `minutes` present and non-null on 254,510 of
  them (mean 29.5, median 0, p75 83, p90 90 — the zeros are non-appearances, so the
  column is "minutes if played", not "minutes on the pitch").

  **Not done, and why:** splitting starters from substitutes needs the role label, and
  the obvious column is **not** it — `element` holds numeric FPL player ids, not
  `"Starter"`/`"Substitute"`. So the first task is to find the real role column (or
  derive the role from `minutes` plus the fixture's starting-XI) before anything can be
  fitted. That mapping is not guessed at, because fitting a minutes model on a
  mislabelled role would produce a plausible, wrong model of exactly the kind this
  whole remediation has been removing.

  This is now a **fresh modelling project, not a loose end** — it needs the role
  mapping, a walk-forward fit, and evaluation under the amended rule with a measured
  noise figure. Given the measured noise (CI half-width 0.0187 on RPS at n=380) and
  the inter-candidate spread within a fold (0.0156-0.0252), an honest expectation is
  that this is *at the edge of resolvability* and may well be rejected. That is a
  legitimate outcome, not a failure.

- [x] **Step 3: Do NOT add a prop backfill path on the current data** — reaffirmed, and
      now evidenced rather than asserted: `docs/player-prop-accuracy-blocker.md` records
      why. A reconstruction is not a pre-game pick, so a backfill would inflate the
      track record with numbers never made before kickoff.

An earlier draft proposed backfilling props the way games are backfilled. Withheld
deliberately: props cannot be snapshotted at all while nflverse has no current-season
data, and once it does, a backfill would still be a reconstruction that the same rule
excludes. Revisit only if genuine pre-kickoff prop snapshots are missed for a reason
other than missing data.

## Session state, 2026-09-28 — what shipped and what is still open

**Merged to `main`** (all squash-merged, all CI-gated, no `main` pushed by hand):

| Repo | PRs | Tests |
|---|---|---|
| NFL_Predictor | #9 serving skews + team-yardage source + CI, #10 missing-probability verdict, #11 prop-accuracy blocker | 231 |
| CFB_Predictor | #12 game-keyed reconciliation + backfill, #13 same verdict bug + two retractions | 259 |
| Sports_Predictor | #8 yardage panel relabelled and decomposed, + the missing test CI | 142 |
| PL_Predictor | #7 opponent defence + amended promotion rule (gate: 60-min cold run pending) | 427 |

**CI now exists in all four repos.** Sports_Predictor had **none** — only a deploy
workflow that fires on push to `main`. The plan's "CI: nothing gates any commit in
any of the three repos" was recorded done without checking this repository, and the
three Python predictors had `tests.yml` only on their branches.

**Two systemic CI defects, both found by adding the linter the lint step already
required.** `ruff` was not in `dev` in CFB or PL, and the install line's fallback
only runs when `.[dev]` fails — so `ruff check ... || exit 1` could never pass. Three
repos, one mistake. Adding it immediately found a real bug in a file written earlier
this session: an annotation naming `np` where the import was function-local.

**Retracted** (both in CFB, both caused by measuring on one week of one season):
the reconciliation tolerance (≥95% within 10, max ≤35 → actually 92.3% and 550), and
its stated cause (a net-rushing convention → CFBD's team and player box scores simply
disagree, in both directions).

**The recurring defect class is unchanged and still the headline.** Across four repos
and four adversarial reviews, the same thing kept happening: a test asserted *that* a
value was produced, never *that it was correct*. Instances found this session — a
week-keyed join, an inert `min_count`, a `KeyError` reachable only on real data
because every fixture supplied its own frame, a coverage guard on a branch that had
already been merged and deleted, and a bare `return` I introduced myself that 230
green tests did not catch. Mutation-verification found the last two; nothing else
would have.

## Task 4c: the 22-season backfill, and two retractions it forced — **DONE 2026-09-28**

`scripts/backfill_team_stats.py` shipped in #12 and the backfill ran: **351 CFBD
calls, 42,190 team-games across 21,095 games, 2004-2025**, plus 436,801 player-game
rows over the same 22 seasons. Quota went 2,116 -> ~1,765. This is a research and
verification cost, not a serving one: the reconciliation has no serving caller, and
`data/cache/` is gitignored, so a local backfill does not reach the container. The
container still starts cold (`Dockerfile` creates the cache dirs empty and nothing
seeds them) — see the open item below.

### Retraction 1 — the reconciliation tolerance was measured on one week

#12 committed "≥95% within 10 yards, median 0, max ≤35", from **2023 week 1**. The
backfill makes the real distribution measurable, and two of the three bounds are
false:

| | 22 seasons (42,172 comparable) | 2023 wk 1 |
|---|---|---|
| exact | 60.0% | 59.2% |
| within 10 | **92.3%** | 95.6% |
| within 35 | 98.3% | 99.3% |
| median | 0.00 | 0.00 |
| mean | 3.77 | 1.62 |
| p90 / p99 | 8.00 / 54.00 | 5.00 / 12.00 |
| **max** | **550.0** | 29.0 |

Per-season exactness runs 44.6% (2004) to 69.2% (2024); 2004-2008 are the worst
cohort and 2021-2025 the best. One week of one season was never enough to claim a
bound.

### Retraction 2 — the cause given for the residual was wrong

#12 said the player sum systematically *exceeded* the team total and blamed a
net-rushing treatment of sacks. Checked row by row against the **unflattened** CFBD
response, that is not it. Campbell vs Monmouth (2023 wk 3, game 401540313): team box
reports 182 rushing / 184 net passing, player box reports 133 rushing / 172
receiving. Not a flattening fault, not a dropped row, and **not one-directional** —
which is why the 2023 wk-1 "11 of 12 offenders run the same way" observation was a
coincidence of that week.

So CFBD's team and player box scores are two independent imperfect records of the
same game. The reconciliation measures their disagreement: a good sanity check with
a tolerance, a bad exactness test. The `max <= 35` assertion is **removed, not
loosened** — a bound the source does not honour is not a weaker assertion but a false
one that passes on a lucky week.

### The reconciliation had never run on real data at all

`player_stats.KEEP_COLUMNS` names its team column `recent_team`; the team box score
uses `team`. Every offline test supplied its own frame with a literal `team`, so the
suite was green and the function raised `KeyError: 'team'` from inside a `groupby` at
42,190 team-games in. Fixed in #13, with an explicit error for a frame carrying
neither spelling.

## Task 9: PL — the selection-bias problem in the published metric — **MEASURED AND RESOLVED 2026-09-27**

> Ledger: EXP-2026-26. `evaluate/scoreline_selection.py`, 12 tests. The question was
> quantified rather than argued, and the answer was not the expected one.

`manifest.py` selects with `min(candidates)` on the same `val_df` it reports. Quantified
over 5 folds, 2021-22 through 2025-26, all four candidates on identical folds:

| quantity | RPS |
|---|---|
| published today (`min()` per fold) | 0.198727 |
| the same, on the folds nested selection can score | 0.199376 |
| nested selection, uncontaminated | 0.201618 |
| **measured optimism in the published number** | **+0.002242** |
| `ml_scoreline` walk-forward mean (the adopted headline) | **0.199654** |

- [x] **Step 1: Quantify it** — done. The bias is real, **+0.002242**, and about an eighth
  of the per-fold bootstrap CI half-width of 0.018736. The published number is flattering
  but not materially misleading — the opposite of the suspicion.

- [x] **Step 2: Options (a) and (b) adopted, (c) reserved.**
  - **(a) Walk-forward mean as the headline.** `ml_scoreline` 0.199654 over 5 folds,
    against the 0.206594 single-fold figure currently reported.
  - **(b) Self-describing number.** `manifest["scoreline"]["selection"]` records
    `holdout_selected_on_this_fold: true`, every candidate's RPS on that fold, the chosen
    model's RPS CI, and the measured optimism. The CI and per-candidate RPS were already
    computed in the same retrain, so this cost no extra compute. Additive — no existing
    key renamed, because `CalibrationPage.tsx` reads `scoreline.<model>.metrics.rps`.
  - **(c) Untouched holdout.** Not available; 2026-27 is in progress and is now explicitly
    reserved as the only thing that can settle finding 1.

- [x] **Step 3: Report the finding that outranks the question asked.** The inter-candidate
  spread within a fold (0.0156-0.0252) is the same size as, or smaller than, the noise on
  a single fold (CI half-width 0.018736). **The four candidates are not distinguishable at
  n=380, so any single-fold RPS comparison in this project is unresolved in either
  direction** — including comparisons this ledger has treated as evidence. The two-gate
  rule was the right instinct for exactly this; this says its resolution limit is 380
  fixtures.

- [x] **Step 4: Caching, honestly.** Diagnostics go to `models/selection_walk_forward.json`,
  deliberately gitignored — a stale committed headline is worse than an absent one. A
  retrain on a fresh checkout reports `walk_forward_status: "not_computed"` and omits
  `headline_rps` rather than inventing or resurrecting a figure. Regenerate with
  `python -m pl_predictor.evaluate.scoreline_selection`.

**The model choice does not change.** `ml_scoreline` wins the walk-forward mean and is
what `min()` already picks; nested selection converges on it for 3 of the 4 folds it
scores. The choice was never the problem. The reported quantity was.

## Task 10: CI — nothing gates any commit in any of the three repos — **DONE 2026-09-27**

> All three repos' workflows were deploy-only, so nothing gated a commit. That is how
> two contradicting assertions about the same feature value survived in NFL's own test
> suite — the train/serve skew fixed in `0628c6d`.
>
> - `NFL_Predictor` commit `986d2a5`, `CFB_Predictor` commit `b11d17f`,
>   `PL_Predictor` commit `391b3b1`.
> - Offline suite gates (`-m "not network"`), so CI depends on neither nflverse nor
>   CFBD being reachable nor on metered quota. Network tests run only on
>   `workflow_dispatch` and are explicitly non-gating.
> - ruff scoped to `E9,F63,F7,F82` only — the import-breaking class. No repo here has
>   a ruff config, and enabling every default rule at once would bury real failures.
> - `dev = [..., "httpx2"]` fixed in NFL: `httpx2` is not a real PyPI package, so
>   `pip install -e ".[dev]"` failed outright. FastAPI's TestClient needs `httpx`.
> - The workflows set `PYTHONPATH` explicitly, because the editable install silently
>   no-ops on this machine — verified again this session when a run without it failed
>   collection on a test that passes with it.

## Correction 2026-09-28 — Task 3: `hub_cache` is not the mechanism, and the window is not the constraint

> **Read this before acting on Task 3 Step 1 or Step 2.** Two claims in Task 3 were
> retracted after re-verification in NFL_Predictor against `origin/main` and the live VPS.
> The full reasoning is in the ledger
> (`ledgers/2026-09-28-player-model-accuracy-remediation.md`, section "Correction
> 2026-09-28 (after the ledger merge) — two retractions of *reasoning*"), which is the
> record of decision. This is the pointer; the ledger is the argument.

**1. The empty frame is `player_stats`'s own, not `hub_cache`'s.** Step 2's claim

> "It **fails silently** — `hub_cache.cached_frame` returns an empty frame by design
> (dashes, not an error), so `n_resolved: 0` is four hops from a 404 with no log line
> above the default threshold."

names the wrong function. `src/nfl_predictor/data/player_stats.py` does not import
`hub_cache`; the empty frame comes from its own bare `except Exception` at line 64, which
logs at `logger.info` on line 65, `continue`s on line 66, and falls through to
`return pd.DataFrame(columns=KEEP_COLUMNS)` on line 72. The level and the consequence were
both right, so only the owner was wrong. `hub_cache.cached_frame` does log at INFO on
`hub_cache.py:27` and does return an empty frame on its own nflverse path — a different
function on a different path, which is exactly why the claim survived a review round.

**2. Step 1 is not the binding constraint; the 404 is.** Step 1's claim

> "**The window, not the file, is the binding constraint.** Even with the data published,
> `min-replicas: 0` means no genuine pre-game snapshot exists to resolve, so fixing the
> 404 alone would produce `n_resolved: 0` still."

rests on a deployment that is switched off. `deploy-azure-nfl.yml` is deleted from NFL
`origin/main`; the only `--min-replicas 0` left is `deploy.yml:91,103`, inside a job gated
`if: vars.DEPLOY_AZURE == 'true'` (`deploy.yml:72`), and `DEPLOY_AZURE` is unset. The live
service is a Compose service under `restart: unless-stopped` — it cannot scale to zero.
Production `/api/track-record` for 2026 week 3 currently reports `n_resolved: 14`
(0.786 / 0.714 / 0.571) with `n_rebuilt: 33` counted separately, and every one of the 14
is a pre-kickoff snapshot. Pre-kickoff capture is working. **Task 3 Step 1 is a no-op, not
an open decision** — options (a), (b) and (c) are not to be executed; there is no
`min-replicas` knob on the deployment that is live.

**3. What is *not* resolved, and must not be recorded as resolved.** Whether next-week
inclusion in `_games_to_snapshot` (`ee1d3ef`) closed the Thursday-night gap is still open.
The single backfilled week-3 game *is* the Thursday night game (`2026_03_ATL_GB`), and it
kicked off 45.6h before that commit landed, so it is evidence about pre-fix code. Week 4's
Thursday game, `2026_04_PIT_CLE`, reports `pre_kickoff` but has not kicked off, and an
ungraded upcoming game reports `pre_kickoff` by construction. It is the first clean test
and the result is not in.

**The outcome is unchanged.** nflverse still 404s on `player_stats_2025` and
`player_stats_2026`; prop accuracy is still unmeasurable; Step 2 is still the first thing
that has to happen. Only the mechanism and the constraint ordering were wrong.
