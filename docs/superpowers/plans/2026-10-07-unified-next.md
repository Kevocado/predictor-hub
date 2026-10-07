# Unified next steps (2026-10-07) — one session runs all of this

Supersedes the scattered hand-offs. Read this, then the plans it points to. Verified against GitHub on 2026-10-07 04:20 UTC;
re-verify any "state" line before acting on it (agents' summaries have been wrong about merge state and CI more than once).

## 1. State

**Live on the VPS (all six sites return 200):** NFL `b3331be`+ (counted record, QB passing-TD record, forward test, closing-line
capture; receptions refused by the calibration gate), CFB (QB passing-TD model, anytime TD no longer counts passing TDs, trust badge),
PL (counted record, absence signal + fixture row), F1 (counted record, trust badge, top calls removed), Sports (trust badge, NFL pop-out),
NBA `9c0e807` (Phase A/B/C merged; retrain now serves the race winners logistic/ridge/ridge; edge ceiling 0.15 with `n_suspect`).
Hub: SignalRows + absence_strip, negative-projection guard, tests workflow, VPS credential forwarding.

**Open PRs (all NBA_Predictor):**
- #43 honest record label ("Every pick 1174/1373, 1365 after tip-off | Before tip-off 3/8"): substance right, CI green, tested on the live
  payload shape. Blocked by 2 CodeRabbit Majors: the *vendored* `ExplainerPanel` record prop type and `InstantBlock FixtureExtras.record` lack
  the new `rebuilt`/`preTip` fields. Fix in the hub (`packages/predictor-ui`), merge, re-sync with `node scripts/sync-ui.mjs`; never hand-edit vendored files.
- #44 win from margin (`win = Phi(margin / sigma)`, sigma from walk-forward residuals): CI green, **not mergeable**: (a) the manifest's win
  log-loss/Brier/AUC still describe the logistic, not the served Phi(margin/sigma), so evaluate the served probability walk-forward and report those;
  (b) no game-level test that a card's win prob and margin agree; (c) two silent fallbacks (no sigma -> logistic; ValueError -> MAE*scale): make them loud or
  label the manifest; (d) existing stored predictions keep the old numbers: state how they are regenerated.
- #45 live-defects bundle: overlaps #43/#44; its label change only hides an empty section, which is not the honesty fix. Keep only what is not a duplicate, or close.
- Stale: hub#5, NBA#5, F1#6 (old "deploy on merge" PRs). Close them with a reason.

**Known live facts (NBA):** win log-loss 0.6904, Brier 0.2481 (always-home is 0.2466), AUC 0.5587; margin walk-forward MAE 12.66 (beats naive 13.9);
total 16.52 (loses to naive 16.375). About one season of training data. Phase A's 0.6636 / 0.2351 / 0.6285 is NOT reproduced: explain why with numbers.

## 2. Order of work

**A. Land the NBA live-defect fixes (P0).** #43 (via the hub type PR), #44 (with the three gaps above), reconcile #45. Then deploy NBA and verify on the live site:
no card shows a win probability that contradicts its margin; the modal never says "made before tip-off" beside a number that includes post-tip picks.
**B. NBA model + design (P1), in `2026-10-06-nba-audit-followup.md` Tasks 3-6:** multi-season backfill scored on the identical 758 Phase A games, candidates
(availability, rest/travel, calibration + ceiling ~0.85, Ridge/XGB averaging, pace/efficiency total), copy fixes, 44px touch targets, `/impeccable document`.
Also: remove the user-visible "Projected standings endpoint not yet implemented" text; fix the 2 failing GameDetailModal heading tests and add `npm test` to CI;
profile `/hub/track-record` (2.4 s vs <0.25 s elsewhere).
**C. Model improvements from the 2026-10-06 review (all must beat the current winner in walk-forward on identical held-out games):**
1. NFL/CFB: `sigma` is an in-sample training residual (`models/manifest.py`, `evaluate/walk_forward.py`): use out-of-fold residuals, then heteroscedastic sigma. Check CFB separately.
2. NFL/CFB: fit Elo parameters (K, home field, points per rating) by walk-forward; add `wind`/`temp`/`roof` (already in schedules) to the total model; average Ridge/XGB instead of winner-take-all.
3. F1: teammate head-to-head from the existing Plackett-Luce simulation (calibration only; no odds feed); DNF Platt/beta calibration (not isotonic, positives are scarce).
4. PL: xG-per-90 + penalty-taker input to `player_goals.py` (Understat shots already ingested); referee assignments feed only if one is found.
5. Extend closing-line capture (NFL done) to the other sports that store lines; CLV needs an append-only closing column that never feeds a model.
**D. Fixture signals (`2026-10-02-fixture-signals-phases-1-4.md`):** verify which phases are really done (post_game, the "so what" step + validator); finish the rest; the old factor-prose summary retires only after all five served sports are verified.
**E. NFL deferred:** receptions needs a count-appropriate calibration (research); grade week 5 once played; weather forecast at tick time; clean up stale worktrees/branches.
**F. Ops:** add CI deploy workflows for NBA and F1 (NFL/CFB/Sports/PL have them); keep the 04:30 prune cron healthy (disk was 100% twice); never leave a PR open that nothing owns.

## 3. Rules (hard-won; every one broke at least once)

- **Never push to main**; branch + PR even for a one-line test fix. Never force-push.
- **Use a git worktree per task**, never switch branches in a clone another session is using, never `git add -A` (it swept an embedded repo into a commit). Add files by name.
- **Gate before every merge, no pipes:** wait until the CodeRabbit check is no longer pending *and* CI is not pending (a pending review reports 0 findings), then
  `scripts/coderabbit.sh R N >/dev/null && gh pr merge N -R R --merge --match-head-commit <sha>`. Piping the script into `head`, or wrapping `gh pr checks` in
  `pipefail`, merged PRs with open Majors/pending CI twice. A PR marked "do not merge without Kevin's approval" waits for Kevin, whatever CI says.
- **Report only what GitHub/the live site shows.** Check merge state, CI and the live payload before saying "merged", "fixed" or "deployed". Run the FULL suite
  (`uv run --python 3.13 --extra dev pytest` for NBA; 3.11 for NFL/PL/explainer; 3.10 for F1 excluding the two network tests) and `npm run build` + vitest, not a subset.
- **Every new test is red-checked** by really reverting the fix. Tests never touch the network. Do not weaken a gate to make a number pass; report failing gates as failing.
- Standing product rules: every recorded pick counts, earliest per (game, market) is the counted one, recorded picks are immutable, a post-tip pick is labelled, never hidden
  or shown as pre-game; betting-price buckets stay pre-kickoff; the 5% edge floor stays, edges above 15% are "suspect" and excluded.
- Never read, print or commit secrets (the OpenRouter key lives only in `/etc/predictor/explainer.env`). Vendored UI is changed in the hub and re-synced only.
- Keep reports short; put decisions needing Kevin in the summary instead of guessing.

## 4. Deploy (the session may do this itself)

Sites are built on the VPS: `scripts/deploy-site.sh` (usage and per-site arguments in its header). CI deploys NFL/CFB/Sports/PL on merge to main; NBA and F1 are manual.
After deploying: curl the real routes (not guesses; unknown `/api/...` paths return the SPA HTML with 200), read the live payload for the thing you changed, and run
`/opt/stack/bin/prune-images` if the disk is above ~75%. Deploying main ships every merged commit: read the diff since the deployed tag first. PL/F1 serve a committed
public snapshot polled every 5 minutes, so a data change can take ~10 minutes to appear.

## 5. Done when
A through C1 merged and deployed with live evidence pasted; the rest merged or each with a written reason; stale PRs closed; a short summary posted on
`predictor-hub` with: what merged (repo, PR, commit), what is deployed, measured numbers (holdout named), what is left and why, and anything for Kevin to decide.
