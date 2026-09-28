# Handoff: player-model accuracy remediation (session of 2026-09-27/28)

You are picking up work on the **player models** across the Predictor sports sites. Read
this to know what is already done, what is deliberately not done, and what would be a
mistake to redo.

**Read next, in this order:**

1. `docs/superpowers/ledgers/2026-09-28-player-model-accuracy-remediation.md` — the record.
   Every ruling, measurement, retraction and open decision, with the reasoning.
2. `docs/superpowers/plans/2026-09-27-player-model-accuracy-remediation.md` — the task list
   and the measured tables behind each task. **16 of 19 items done, 3 open.**
3. `PL_Predictor/docs/AI_CONTINUITY.md` — the PL repo's own long-running ledger
   (entries `EXP-2026-24` … `EXP-2026-28`). The cross-repo ledger above points at it
   rather than duplicating it.

## What prompted this

A visibly wrong **"total yards"** figure in the CFB player panel. Chasing it found that
the number was wrong in the frontend, that the *check* meant to catch it was joining on a
non-unique key, and that a quarter of the frame was being dropped for a property of the
schedule rather than of the data. It did not stop there — the same defect shape turned up
in all four repos.

## The one thing to understand

Every finding, in all four repos and across four adversarial reviews, was:

> **a test asserted *that* a value was produced, never *that it was correct*.**

So: a join on a key that is not unique. A `min_count` guard that could not fire because
`groupby.sum()` turns an all-NaN column into `0.0`. A function asking for a column that
only its hand-built fixtures had. A lint step that could never pass because the linter was
not installed. A `KeyError` from inside pandas that was two hops from the actual cause.

The one that should change how you work: in CFB, the first version of a fix **passed 22
green tests while doing nothing**, because the read-path guard had no test. Mutation
verification found it. Nothing else would have.

## Where things stand

| Repo | PRs | Tests | State |
|---|---|---|---|
| NFL_Predictor | #9, #10, #11 | 231 | merged |
| CFB_Predictor | #12, #13 | 259 | merged |
| Sports_Predictor | #8 | 142 | merged |
| PL_Predictor | #7 | 489 | **open, CI cold-running** |

All CI-gated, squash-merged. No `main` was pushed by hand. Every deploy workflow is
`workflow_dispatch`-only, so merging does not deploy.

**Your uncommitted work was not touched** in any repo — the VPS cutover
(`Sports_Predictor/src/api/client.ts`, the `deploy-azure*.yml` edits in CFB and
Sports_Predictor) and PL's `323114e` terminology refactor are all still as they were.

## Do not redo these

- **Do not measure a tolerance on one week.** Two retractions this session came from exactly
  that. A committed "95% within 10 yards, max ≤35" was measured on 2023 week 1 and is
  actually 92.3% and **550** across 22 seasons. If a number is going in a docstring as a
  property of a source, it needs the whole source.
- **Do not re-attempt the NFL `backfilled` column.** It was implemented, reverted, and the
  reason is sound: a backfill recomputes from current weights, which is a reconstruction,
  not a frozen pre-game pick, and the repo's tracking rule excludes exactly that. Three
  tests pin the decision.
- **Do not treat the prop-accuracy `n_resolved: 0` as a tracking bug.** It is nflverse
  returning 404 for the current season, verified, and it now says so in the log. See
  `NFL_Predictor/docs/player-prop-accuracy-blocker.md`.
- **Do not re-add a `bivariate_poisson` O/U 2.5 override** (plan Task 7b).
- **Do not go looking for the CFB backfill script.** It exists, it ran, and the numbers are
  in the ledger. But note it populated a *local* gitignored cache and did **not** reach
  production.

## Open, and genuinely a decision rather than work

1. **NFL pre-kickoff window.** `min-replicas: 0` means the next tick can land after
   kickoff, so no genuine pre-game snapshot exists. This is the **binding constraint** on
   prop accuracy — fixing the 404 alone changes nothing. (a) min-replicas 1 (costs money),
   (b) a timer-triggered pre-kickoff tick, (c) accept it.
2. **CFB container starts cold.** Needs an operator step or an idempotent startup job.
   Related: the Azure workflow does not pass `CFBD_API_KEY` and does not invoke the script.
3. **PL gate depends on three third parties.** FPL, ClubElo and football-data.co.uk. The
   `-m "not network"` split in the workflow currently selects nothing because no test
   carries the marker, so the gate runs everything and an upstream outage turns it red for
   an unrelated reason.

Also open and unstarted: **PL blend union unification** (`EXP-2026-28`) and the
**P(minutes) model** (Task 8 Step 2). Both are written up in the ledger with what is known,
what is not, and why neither should be attempted without the measurement first.

## Test commands

```bash
# NFL
cd NFL_Predictor && PYTHONPATH=src ../NFL_Predictor/.venv/bin/python -m pytest tests/ -q -m "not network"

# CFB — the reconciliation test needs a key and SPENDS METERED CFBD QUOTA (~1,765 calls left)
cd CFB_Predictor && set -a && . ./.env && set +a
PYTHONPATH=src ../CFB_Predictor/.venv/bin/python -m pytest tests/ -q -m "not network"

# Sports_Predictor
cd Sports_Predictor && npx vitest run && npm run build && npm run lint

# PL — the full suite is ~14 min and network-bound; prefer targeted files
cd PL_Predictor && PYTHONPATH=src .venv/bin/python -m pytest tests/test_features.py \
  tests/test_promotion_rule.py tests/test_blend_validation.py -q
```

Ruff is in `dev` in all three Python repos and is a gating step. It found three real
pre-existing bugs the moment it was installed in NFL, and one in a file written earlier the
same day in PL.

## If you touch a test

Mutation-verify it: break the source, confirm the test fails, and write down which mutants
survive. A test that passes when the behaviour is deliberately broken is worse than no test,
because it counts as coverage. Three tests in this session's work have known surviving
mutants, each documented in place with why the assertion is honest about it — read those
comments before "fixing" them.
