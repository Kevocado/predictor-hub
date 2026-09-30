# Session state — 2026-09-30 ~00:00Z

## Watcher

`/Users/sigey/Documents/Projects.nosync/algo-trade-hub-prod/scripts/repo-watcher.sh`
(PID 66279) is the only watcher. My earlier duplicate is stopped.
`predictor-hub/tools/watch.sh` (pushed `71970f4`) also fixed a real bug in it —
`diff` was handed the snapshot as a *filename*, so it could never detect
anything. Verified working after the fix. Don't run both against one log.

## Merged and deployed by the reviewer

`PL#29` (all-picks + durable record), `PL#30`/`#31`, `hub#41` (validator false
positives), `hub#42` (SITES_ROOT), `hub#44` (landmark/zero/unmount), and the
four re-syncs `F1#17`, `NBA#15`, `Sports#18`, `PL#30`. All four sites redeployed.

## Open PRs from this round

| PR | what | verified |
|---|---|---|
| `hub#43` | F1 `unknown` timing — **was HELD, now addressed** | 525 on py3.11, 326 pkg |
| `hub#45` | bare book reference: "the line"/"the number"/"pick'em" | 550 on py3.11 |
| `F1#18` | two future races served byte-identical predictions | 134 passed |

## Audit items — 1,2,3,4,5 DONE; 6 in progress

1. PL track record — merged. 2. Validator — merged. 3. sites root — merged.
4. predictor-ui — merged. 5. NBA/PL small defects — merged.
6. **Done**: F1 `unknown` timing (#43), NBA wording leak (#45), F1 identical
   predictions (#18). **Still open**:
   - py3.11 CI + py_compile step + `deploy-explainer.sh setup` health check
   - NFL players: **decided — keep the honest empty state** (Sports#17 merged);
     the decision still needs writing into the spec
   - PL CI: 13 backend tests need FPL history; confirm the gate warms the cache
     and say so in the ledger if it silently skips them

## Two findings worth remembering

**A pre-existing false positive in #41, found by a test written for a
different fix.** Bare `total` rejected *"Total commitment from midfield"* and
*"A total of two chances"* — live, ordinary English, reader gets the template
instead of the summary. Fixed by separating `MARKET_WORDS` (contract keys) from
`PROSE_WORDS` (words a sentence uses). This file has now made the "single common
noun as a market trigger" mistake twice: `line` in #41, `total` here.

**F1's identical predictions were one line of data loading.** The cache key was
always round-specific; the model was not, because cross-season circuit history
was never loaded. With the fix, round 17 picks Piastri at Marina Bay.

## Verification habits that earned their keep

Running every mutation rather than assuming they bit found **five** tests that
passed for the wrong reason:

| what | before | after |
|---|---|---|
| `service._answer` band | green | real-service test red |
| panel badge row | green | structural test red |
| template disclosure | — | caught |
| current-season-only loading | — | 3 red |

`ruff` caught `logger` undefined in `jolpica.py` — my own code, missed by me.

## Flaky tests, recorded so nobody re-investigates

`test_goal_contribution_research` and `test_opponent_defence` fail
intermittently on PL (`RuntimeError` on real-data fixtures). Verified flaky by
running twice: one run 4 extra failures, the next matched baseline exactly.
