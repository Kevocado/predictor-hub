# Plan: NBA audit follow-up (honesty, coherence, data, model, design)

Source: the 2026-10-06 live audit of nba.40-160-91-131.sslip.io (impeccable audit plus model review), posted on
NBA_Predictor#36. NBA parity Phase A (#37) and Phase B (#39) are merged and deployed (7a6ad42).
**Order matters: P0 before anything else. One PR per task, test-first, every new test red-checked by really
reverting the fix, `uv run --python 3.13 --extra dev pytest` and `npm run build` + full vitest, CodeRabbit script
before merge, no deploy (the reviewer deploys), nothing marked "needs Kevin" is merged without his approval.**

## Evidence (all reproducible on the live site)
- `GET /hub/track-record`, row `game_outcome`: total 1373, correct 1174, `n_rebuilt` 1365, `n_pre_tip` 8 (3 correct).
  The modal labels this "Winner pick made before tip-off 1174/1373".
- `GET /games/week?start=2026-10-05`: MIN 72% labelled "Toss-up"; NYK 53% "by 13.3"; IND 52% "by 8.2"; MIA 84%.
- `GET /manifest`: win log_loss 0.7708, brier 0.2752, auc 0.5495 for the 2026-10-06T17:34 retrain, against the
  Phase A winner's 0.6636 / 0.2351 / 0.6285 (already sent on NBA#39; Task 0 below closes it).
- `GET /value-picks`: 13 picks with edges 0.19-0.28 (already sent; Task 0 below closes it).
- 375px: 12 of 45 interactive elements under 44px (header chips 28px high, section tabs 34px).
- Copy: "Hawks is the pick." and "The pick rightness: the model's pick was wrong."

## Task 0 — close the two live-metric items already raised on NBA#39
(a) Explain or fix why the daily retrain's manifest metrics differ from the Phase A winner: which holdout, which
window, same code path as `models/evaluate/walk_forward.py`? If the served model is truly worse than naive, gate it
(refuse to serve, say so) rather than serve it. (b) Edge ceiling: an edge above 0.15 is "suspect: likely model
error", excluded from `picks`, counted in the payload (`n_suspect`), the 0.05 floor unchanged. Tests: 0.16 excluded
and counted, 0.14 kept, 0.05 boundary unchanged.

## Task 1 (P0) — the record label must be true
Files: `frontend/src/components/GameDetailModal.tsx` (`winnerRecord`, ~line 340-360), the page header line
"N/M picks made before tip-off correct", `frontend/src/lib/*` where it is computed, `tracking/hub_service`.
1. Write failing tests first: given the real live payload shape (total 1373, correct 1174, n_rebuilt 1365, n_pre_tip 8,
   pre_tip.correct 3) the modal must never print "made before tip-off" next to 1174/1373.
2. Show two figures: the counted record with a true label ("Every pick: 1174 of 1373, 1365 of them made after
   tip-off") and the pre-tip record beside it ("Before tip-off: 3 of 8"). Counted picks stay counted (standing rule);
   disclosure replaces exclusion. Never print 0/0.
3. Delete the stale comment claiming the row is pre-tip-only by construction; replace it with the real rule.
4. Grep every NBA surface for "before tip-off" / "pre-tip" and prove each claim against its payload in a test.
5. If a header says "picks made before tip-off", its numerator and denominator must both come from `pre_tip`.

## Task 2 (P0) — win probability and margin must agree
Files: `src/nba_predictor/models/game_outcome.py`, `services/hub_service.py`, `api/routes.py` (`/games`, `/games/week`),
the card label code in `frontend/src` (grep "Toss-up").
1. Failing test first: for every served game, `win_prob`, `margin` and the label come from ONE distribution.
   Property test over a grid of margins: win = Phi(margin / sigma), monotone in margin, 0.5 at margin 0.
2. Serve win from the margin distribution (parity plan Task 6 intent); keep the logistic only if calibration on
   out-of-fold data beats Phi(margin/sigma), and then calibrate the two against each other and cap the disagreement.
3. "Toss-up" is defined by the same number as the percentage (e.g. |margin| < 1.5 or win in [0.45, 0.55]); a card
   can never read 72% and "Toss-up". Add a test that scans the live-shaped payload for any contradiction.
4. Residual sigma must be out-of-fold (pooled walk-forward residuals), not training residuals; test that sigma
   grows when the held-out error is larger than the in-sample error.
5. Re-run the Phase A gates (log-loss, Brier, AUC, max calibration gap, margin MAE, total MAE) and put the table in
   the PR. A gate that fails is reported as failing.

## Task 3 (P1) — more training history (the biggest model lever)
Files: `data/espn.py` and the training-cache loader, `features/build.py`, `models/evaluate/walk_forward.py`.
1. Backfill 3-5 prior seasons of finished games and box scores through the ESPN endpoints already used; cache to the
   same training cache shape; rate-limit and retry; tests never touch the network (fixtures only).
2. Season-boundary carry-over: start each season's ratings at last season's rating regressed toward the mean (fit
   the regression weight in walk-forward, do not hard-code it). Unit-test that week-1 features use only prior-season
   data.
3. Re-run the walk-forward with date-boundary windows (no row-wise cuts) and report pooled out-of-fold
   log-loss/Brier/AUC and MAE against naive. If it does not beat the Phase A numbers, say so and do not ship it.
4. Note the new n in the evaluation doc; the ±0.05 per-bucket calibration gate needs n >= 100 per bucket.

## Task 4 (P1) — model candidates, each ships only if walk-forward beats the current winner
(a) star/minutes-weighted availability from the existing injuries feed; (b) rest, back-to-back and travel
interactions; (c) isotonic or Platt calibration fitted out-of-fold plus a probability ceiling near 0.85;
(d) simple average of Ridge and XGBoost margins instead of winner-take-all; (e) total model from pace x
opponent-adjusted efficiency, kept only if it beats the naive total (16.375). One PR per candidate with the
before/after table. A candidate that does not win is documented in `docs/nba-parity-evaluation-2026-10.md` and not
shipped.

## Task 5 (P1) — copy
Write plain one-line sentences, singular/plural safe: "The model picked the Hawks. The Grizzlies won." Replace
"The pick rightness: ..." everywhere. Scan the whole modal and cards; add a test that no template string produces
"<plural team> is". Use the impeccable `clarify` command for the sweep.

## Task 6 (P2) — touch targets and design context
1. Raise hit areas to 44px without changing visual size (padding or hit-slop pseudo-element): header site chips (28px)
   and the Games / Data Hub / Calibration / Model tabs (34px). Test at 375px with a DOM measurement.
2. Run `/impeccable document` once to create NBA's DESIGN.md, then `/impeccable audit` and
   `impeccable detect frontend/src` and fix findings. Keep: no horizontal overflow, landmarks, lang, reduced-motion.
3. Re-vendor predictor-ui if hub changed; `node scripts/sync-ui.mjs` only, never hand-edit the vendored copy.

## Done when
Tasks 0-2 merged and the live site shows true labels and consistent win/margin; Tasks 3-6 merged or each has a
written reason it did not ship; summary on NBA_Predictor#36 lists commits needing a deploy and the final metric
table. Anything that needs Kevin's decision (e.g. `MAX_MODEL_AGE_DAYS`, whether to hide value picks) is written down and
not guessed.
