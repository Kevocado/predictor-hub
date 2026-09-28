# SDD ledger — plan: docs/superpowers/plans/2026-09-27-player-model-accuracy-remediation.md

Session 2026-09-27/28. Player models across four repos, prompted by a visibly wrong
"total yards" figure in the CFB player panel. Read
`plans/2026-09-27-player-model-accuracy-remediation.md` for the task detail; this file
is the record of what was decided, measured, shipped, retracted, and left open.

Append-only. Add new lines at the end; do not rewrite history above.

---

## The defect class this session established

Every finding across four repos and four adversarial reviews was the same shape:

**a test asserted *that* a value was produced, never *that it was correct*.**

Concretely, these all passed a green suite while shipping a wrong number:

- a join keyed on `(season, week, team)`, which is not unique — two games' players were
  summed and compared against each single game. Produced a 1,620-yard "player total" for
  one 443-yard game (CFB).
- `groupby.sum()` treats an all-NaN column as `0.0`, so a `min_count` presence check on
  the axis sum could never fire, and a *partial* total read as complete (CFB and NFL,
  independently, in code that is the same lineage).
- every offline test built its own fixture with a literal `team` column, so
  `reconcile_against_players` asking for a column only real CFBD data lacks was invisible
  until 42,190 team-games in, as a bare `KeyError` from inside a `groupby` (CFB).
- a CI workflow referenced `ruff`, which was not in `dev`, and whose install fallback only
  runs when the `.[dev]` install *fails* — so the lint step could never pass. Three repos,
  one mistake.
- a coverage guard on a branch that had already been merged and deleted, so it measured
  nothing (CFB, found by review).
- a bare `return` I introduced while documenting a bug, which stopped *game* reconciliation
  when *player* stats were missing. 230 green tests did not catch it, because the only
  existing tick test never entered that branch (NFL, found by me the same commit).

Ruling: mutation-verification is the standing requirement for new tests in this family —
break the source, confirm the test fails, record which mutants survive. A test that
passes when the behaviour is deliberately broken is worse than no test, because it is
counted as coverage. Cost if wrong: some time spent verifying tests that were already fine.

## Shipped

NFL_Predictor — PR #9 (merge `8619539`), tests 231
- `iloc[:-1]` excluded a player's target week from their own feature history, so a
  one-game player got an all-NaN row, which `fillna(0)` turned into the all-zero vector
  the model is never trained on — the origin intercept. Measured: 430 of 880 live rows
  (48.9%) bit-identical, serving 62.592 passing yards to real quarterbacks. This was a
  regression I introduced earlier in the same session; reverted with the evidence.
  Ruling: this defect was reported as still-reachable in review. It was real against the
  code as it stood but an artefact of the `iloc[:-1]` bug. Measured the current behaviour
  (one game → real values; no games → `None`, already skipped) and recorded the
  measurement rather than claiming a fix I had not made. Cost if wrong: none.
- `div_game` was read with `iloc[0]` over a frame that concatenates eight completed
  seasons sorted oldest-first, so a 2026 BUF–MIA game was served `div_game=1` because
  2019's was divisional. I introduced this by replacing a hardcoded `0` with a lookup.
  Ruling: kept the lookup, scoped to the newest season, latest meeting inside it. A
  constant covariate is dead weight against a fitted coefficient, but a confidently wrong
  one is worse than a constant. Cost if wrong: division games served as non-division.
- dev extra had no linter; adding ruff found three real pre-existing bugs (`Path` used in
  `-> "Path"` annotations without import in `injuries.py`, `player_stats.py`,
  `schedules.py`).
- A team-week yardage source did not exist, so a total-yards model was not constructible.

NFL_Predictor — PR #10 (merge `b027e03`), tests 230
- `_compute_hits` guarded on the *line* being present and wrote
  `(home_cover_prob or 0) >= (away_cover_prob or 0)`. A game with a spread and no cover
  probabilities was graded as though the model called `0.0 >= 0.0`, which `>=` resolves to
  the home side. Fabricated in both directions (a hit and a miss) and persisted, on the
  **track record**. Identical defect at identical line numbers in CFB.
- Ruling: `ats_hit` values already written by the old build are NOT repaired here. The
  rows are identifiable (`ats_hit` non-null with a null cover probability) and a backfill
  could null them, but that is a data migration on a live database. Cost if wrong: some
  historical track-record entries stay fabricated.

NFL_Predictor — PR #11 (merge `a50302b`), tests 231
- Verified the nflverse blocker independently rather than on the plan's word:
  `player_stats_2024` → 302, 2025 → 404, 2026 → 404; through the production loader 5597
  rows for 2024 and 0 rows for 2025/2026 **with no exception raised**.
- Ruling: it fails silently — `hub_cache.cached_frame` returns an empty frame by design
  (dashes, not an error), so `n_resolved: 0` sits four hops from a 404 with no log line
  above the default threshold. `hub_cache` keeps its own failure at INFO (per season per
  tick; WARNING would flood) and the tick reports the consequence at WARNING once per
  tick. Cost if wrong: one extra log line per tick.
- Ruling: Task 3 Step 1 reclassified from "blocked" to "your decision". I had filed all
  three of that task's steps as blocked on upstream; Steps 2 and 3 were actionable and are
  now done. Step 1 is an operations choice with a cost, and it is the **binding
  constraint** — with `min-replicas: 0` there is no genuine pre-game snapshot to resolve,
  so fixing the 404 alone would still give `n_resolved: 0`. Cost if wrong: prop accuracy
  stays unmeasurable one season longer.
- Ruling: no prop backfill. A backfill recomputes at backfill time from current weights,
  which is a reconstruction, not a frozen pre-game pick. An earlier `backfilled` column
  for this purpose was reverted when three tests turned out to pin the documented rule.
  Cost if wrong: a gap in the record that cannot be honestly filled.

CFB_Predictor — PR #12 (merge `6ab8e1`), tests 251
- Reconciliation re-keyed from `(season, week, team)` to `(game_id, team)`. CFBD labels
  **every** bowl `week: 1`, so week 1 of 2023 spans 2023-08-26 → 2024-01-09 and a third of
  the frame got the wrong week. On the same cached data: week-keyed 58/272 exact, median
  336, max 1177; game-keyed 161/272, median 0.00, max 29.
- Requiring a week the join never read cost 31% of the frame. `attach_schedule_weeks` drops
  any game absent from the schedule, and the schedule is FBS-filtered, so FCS games — real
  games with real box scores — were excluded for a property of the schedule. 272 → 356 rows
  at the same quality.
- `scripts/backfill_team_stats.py` shipped. A script, not a route, deliberately: CFBD is
  metered, the reconciliation has no serving caller, and a `GET` that quietly spends ~330
  calls is a foot-gun with an HTTP trigger. Dry-run by default.

CFB_Predictor — PR #13 (merge `7697c0`), tests 259
- Same `_compute_hits` / `get_game_verdict` verdict bug as NFL #10.
- Ruling: the first version of that fix had **no read-path test**, and mutation-verifying
  showed reverting the read-path guard alone left all 22 tests green. Added a test that
  writes a legacy row directly. The deployed database already holds rows the old build
  graded this way, so the read path is not hypothetical. Cost if wrong: a fabricated
  `predicted` side printed beside a stored `hit` flag.
- `reconcile_against_players` asked for a `team` column that `player_stats.KEEP_COLUMNS`
  calls `recent_team`. Every offline test supplied its own frame, so it was invisible until
  real data. Ruling: the name is CFBD's and it misleads — the value is filled from the
  *game's* team stanza in the payload nesting, so attribution is per-game and correct.
  Cost if wrong: none.
- Backfill run: **351 CFBD calls, 42,190 team-games across 21,095 games, 2004-2025**
  (152s). Plus 436,801 player-game rows over 22 seasons for the comparison. Quota
  2,116 → ~1,765.
- Empty weeks are now tombstoned rather than skipped. Skipping looked harmless and was not:
  no cache file means the next run re-requests, and most seasons end before week 15 (2023
  has no week 16), so every retry of an interrupted backfill re-bought every dead week.
  Writing the tombstone then exposed a latent bug: `_read_cache` requires `requested_week`,
  which `KEEP_COLUMNS` does not list, so the first tombstone was rejected by its own
  staleness gate and re-requested anyway — the fix did nothing, silently.
  Ruling: a pre-existing test asserted `list(_flatten([]).columns) == KEEP_COLUMNS`, which
  passed *by being the shape that did not match* a real frame. Changed to assert a populated
  frame's columns are a **subset** of the empty frame's — the invariant that holds for
  every input, since a real frame only carries the categories its game had. Cost if wrong:
  none.

## RETRACTED — both CFB, both caused by measuring on one week of one season

Ruling: recorded here rather than quietly corrected, because the same error is likely to
be made again by anyone who measures a tolerance on a single sample.

1. **The reconciliation tolerance.** PR #12 committed "≥95% within 10 yards, median 0,
   max ≤35" from 2023 week 1. At 22 seasons (42,172 comparable team-games): **60.0% exact,
   92.3% within 10, 98.3% within 35, median 0.00, mean 3.77, p90/p99 8.00/54.00, max
   550.0.** Two of three bounds were false; the median held. Per-season exactness runs
   44.6% (2004) to 69.2% (2024).
2. **The cause given for the residual.** PR #12 said the player sum systematically
   *exceeded* the team total and blamed a net-rushing treatment of sacks. Checked row by
   row against the **unflattened** response, that is not it: Campbell vs Monmouth (2023 wk
   3, game 401540313) has team box 182 rushing / 184 net passing and player box 133 /
   172. Not a flattening fault, not a dropped row, and not one-directional — which is why
   the 2023 wk-1 "11 of 12 offenders run the same way" was a coincidence of that week.

Ruling: CFBD's team and player box scores are two independent imperfect records of the same
game, and this reconciliation measures their disagreement. It is a good sanity check with a
tolerance and a bad exactness test. The `max <= 35` assertion was **removed, not loosened** —
a bound the source does not honour is not a weaker assertion but a false one that passes on
a lucky week. Cost if wrong: a yardage model is validated against a looser bar than believed.

Sports_Predictor — PR #8 (merge `162094`), tests 142
- The panel showed a "team total yards" figure no model in the repo computes. Ruling:
  decomposed and relabelled rather than deleted — deleting a long-standing field is a
  product decision, not a bug fix, and it would have discarded real projections. The
  team-level figure is gone from the API response as a top-level field, because anything
  reading it is reading a value with no model behind it. Cost if wrong: the panel looks
  different; reversible.
- Sports_Predictor had **no test CI at all** — only `deploy-azure.yml`, which fires on push
  to main. Ruling: the plan's "CI: nothing gates any commit in any of the three repos" was
  recorded done without checking this repository. Added `tests.yml` whose build step is
  also the typecheck (`tsc -b`), because vitest does not typecheck and the six lying types
  this PR deletes were only ever visible to the compiler. Cost if wrong: none.

PL_Predictor — PR #7 (open at time of writing), tests 489
- Opponent defensive strength added as the first team-context feature on the G+A
  classifier. Two adapters, one rating function; they agree **exactly** on 2024-25 (max
  difference 0.0000, correlation 1.0000), which is the property that matters — a feature
  computed two ways at fit and serve time is a train/serve skew wearing a disguise.
  18 of 20 clubs comparable; Man Utd and Tottenham drop out on naming, not arithmetic.
  Promoted: both gates pass 4/4 folds, log loss 0.179683 → 0.178896 (−0.000787), gate 2
  0.162624 vs 0.163033, brier 4/4.
- Amended two-gate rule in code (`evaluate/promotion_rule.py`): gate 1b requires the
  improvement on a **majority** of folds, not one; gate 1c requires it to exceed the
  **measured** noise. Ruling: `noise` is a required input with no default, because a
  default lets the threshold be chosen after seeing the result, which is the failure the
  exercise exists to prevent. Cost if wrong: a candidate is promoted on noise.
- Selection bias measured at **+0.002242** optimism; walk-forward mean is the headline.
  The more useful number: inter-candidate spread within a fold (0.0156–0.0252) ≈ the noise
  itself (CI half-width 0.018736) at n=380. Single-fold RPS comparisons are unresolved.
- `a55e6e5` reverted a decayed market override. Ruling: an earlier ledger note claimed the
  "reverted override" won 2 of 5 folds. The 2-of-5 count was true of `bivariate_poisson`;
  it had been conflated with `covariate_poisson`, which won 3 of 5. Two of this repo's own
  findings were a misattribution. Cost if wrong: none.
- `de3c222` a `NaT` fixture date leaked future matches — a club conceding 1,1,1,1 then
  0,0,0,0 returns 1.0 for a real date and **0.0** for a `NaT` one, leaked from later
  matches.
- `21ea82d` stopped applying a blend weight fitted against a different union than it is
  applied to. `_fit_blend_weight` minimises Brier against a **Platt-calibrated**
  `_poisson_union`; serving passes an **uncalibrated** `anytime_probability(lam_goals +
  lam_assists)`. Ruling: record the fitted value as `fitted_blend_weight` and serve a
  neutral 0.5. The structural win is unaffected — a convex mixture beats `max(...)` at any
  weight, because the order-statistic bias comes from the `max`, not the share — so only a
  refinement was lost, and it was fitted against a quantity serving never computes. A test
  pins `NEUTRAL_BLEND_WEIGHT != 0.70` so the distinction cannot be quietly erased. Cost if
  wrong: the blend's fitted share stays unusable until the constructions are unified.
- `36bfc72` **six** date-keyed join sites assumed a datetime resolution that depends on who
  wrote the parquet cache. CI failed with `MergeError: incompatible merge keys [1]
  dtype('<M8[us]') and dtype('<M8[s]')` on a cold cache while a warm local cache passed.
  Ruling: fix in code (`features/date_keys.as_date_key`, applied to **both** sides of every
  join) rather than pinning pandas, because a pin makes this machine and CI agree and
  leaves the next cache written by another version free to disagree. `pandas>=2.0` is a
  floor only — resolution inference does not exist before it. Cost if wrong: a CI failure
  that looks like a flaky test.
  Note: the first fix caught **one** of the six sites. The new test still failed and pointed
  at `xg_form.py`, whose docstring already said "same contract as `match_dominance`".
  Enumerating rather than fixing-until-green found the rest.
- PL CI: the cache key was `run_id`, which is unique per run, and a cache entry is immutable
  once written — so every run restored the newest prefix match and then wrote a fresh full
  copy of the same ~100MB. Now keyed on the UTC date.
- PL CI: added `timeout-minutes`, then **measured it wrong and created a deadlock.** A warm
  run is ~13 min; a cold run does not finish in 30. Set 30, the job was killed at 30m14s,
  and `Post Restore upstream caches` was **skipped** — a job that fails does not save its
  cache. So cold → timeout → no cache → cold → timeout, permanently. Now 60.
  Ruling: a timeout on a cache-warming gate is not automatically a safety improvement; if it
  is set below the cold-run cost it is the opposite. Cost if wrong: the gate is red forever.

## Re-scoped, not built

PL Task 8 Step 2 (per-player minutes). The original premise — minutes are free from a
response already fetched — was **rejected**: `penaltyblog.scrapers.Understat` has no roster
method, `get_shots` hits a JSON shots endpoint, and the 2,112 cached CSVs contain shot rows
only. Minutes would cost new HTTP requests.

Ruling: the real gap is narrower and is a **P(minutes) model**, not minutes data. Verified
in `models/player_goals.py`: `STARTER_MINUTES = 82.9` and `SUBSTITUTE_MINUTES = 39.9` are
hard-coded constants, so a starter withdrawn at 60' and one who plays 90 both get 82.9.
`minutes_fraction` **multiplies** `lam_goals` and `lam_assists`, so a 10% error is a 10%
error in every lambda — a real lever, not cosmetic. The archive supports it: 254,510
player-games over 11 seasons with `minutes` non-null throughout.

Not started, and deliberately: the obvious role column is **not** `element` — it holds
numeric FPL player ids, not `"Starter"`/`"Substitute"`. Fitting on a mislabelled role would
produce a plausible, wrong model of exactly the kind this session has been removing. This is
a fresh modelling project needing the role mapping, a walk-forward fit, and evaluation
under the amended rule. Ruling: given noise 0.0187 and within-fold spread 0.0156–0.0252, an
honest expectation is that this is **at the edge of resolvability** and may be rejected.
That is a legitimate outcome, not a failure. Cost if wrong: none.

## Open — needs a decision, not work

- **PL blend union unification** (`EXP-2026-28`). Unify `_poisson_union` and serving's
  `anytime_probability(lam_goals + lam_assists)`, then re-evaluate under the amended rule.
  The neutral weight is a holding position, not a resolution.
- **NFL pre-kickoff window** (Task 3 Step 1). Options: (a) `min-replicas: 1` through the
  season — costs money; (b) a timer-triggered pre-kickoff tick; (c) accept it. This is the
  binding constraint on prop accuracy.
- **CFB container starts cold.** The 351-call backfill populated a *local* cache;
  `data/cache/` is gitignored and the Dockerfile creates the cache dirs empty, so it does
  **not** reach production. Seeding the VPS needs either an operator step or an idempotent
  startup job. Also: the Azure workflow does not pass `CFBD_API_KEY` and does not invoke
  the script. Nothing blocks, since the reconciliation has no serving caller — but a reader
  could easily assume the backfill reached production.
- **PL gate depends on three third parties** (FPL, ClubElo, football-data.co.uk). An upstream
  outage turns it red for a reason unrelated to the change under review. `timeout-minutes`
  makes that fast and legible; it does not make it correct. The fix is to mark the
  network-dependent tests so the existing `-m "not network"` split stops selecting nothing.
- **The `ats_hit` data migration** in NFL and CFB (see above).

## Standing cautions for whoever picks this up

1. **Do not measure a tolerance on one week.** Two of this session's retractions came from
   exactly that, and a third defect (a stale cache) was invisible for the same reason.
2. **Mutation-verify every new test** and record which mutants survive. The read-path guard
   in CFB passed 22 green tests while doing nothing.
3. **A `KeyError` from inside pandas is a symptom, not a cause.** Twice this session the
   real defect was two hops upstream of the message.
4. **A threshold with a default will be set after seeing the result.** `noise` in the
   promotion rule is a required input for that reason.
5. **Check that a test's fixture can actually fail.** Every offline test supplied its own
   `team` column, which is why a function that had never run on real data was fully green.
6. **A timeout on a job that warms a cache can deadlock it.** See PL.
