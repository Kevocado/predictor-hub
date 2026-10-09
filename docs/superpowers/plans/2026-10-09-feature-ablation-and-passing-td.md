# Feature ablation (keep the good part of a failing block) and better passing-TD predictions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) When a feature block fails the evaluation rule, find which sub-features inside it are worth keeping and ship only those. (2) Improve the QB passing-TD model, which today is fitted on only four columns (`passing_tds_roll` and three yardage rolls), using the blocks and signals already merged.

**Architecture:** One selection tool (`tools/ablation.py`): forward selection over named sub-blocks with a paired bootstrap on the SAME held-out games; a sub-block is kept only if the 95% interval of its improvement over the current kept set excludes zero. It is metric-agnostic: the caller supplies `evaluate(columns) -> per-game loss`. Game models use margin error / Brier; the passing-TD model uses per-game negative log-likelihood of its count distribution. Candidate passing-TD features come from the merged EPA, QB and conditions work plus schedule fields; nothing is enabled by default until it clears.

**Tech Stack:** Python 3.11, numpy, scipy (existing), scikit-learn (dev tests only). No new dependencies.

**Spec:** `2026-10-09-nfl-cfb-model-improvement.md` (blocks, decision rule), `2026-10-02-nfl-td-finish.md` (the passing-TD model: Poisson vs negative binomial settled by log loss, 'model line' labelling, anytime-TD = rushing + receiving only).

**Verified vs drafted:** Task 1 (the ablation tool and its 4 tests) was built and run on NFL `main` at `cd15bf6`. Tasks 2-5 are DRAFTED: they say what to build and show the key code, but were not executed.

## Global Constraints

- Everything from the model plan applies: tests never touch the network; causality (features for game g use only earlier games); train/serve parity through one builder; a missing fitted column is a loud error; recorded picks are immutable; every pick counts; never `git add -A`; worktrees only; no deploy.
- A part is kept only if its improvement interval excludes zero on identical held-out rows. A part that fails stays out and the result is written down (a null is a result).
- The calibration rule from the model plan stays: report the reliability gap before and after with a paired interval on the gap difference, not a point comparison.
- The passing-TD market keeps its decisions: a per-player MODEL line (never a sportsbook line), Poisson/negative-binomial chosen by log loss, anytime TD excludes passing.
- Independence note: NFL may read schedule lines as features only if the NFL plan already allows it; this plan does NOT require betting lines. Implied team total is an OPTIONAL sub-block, evaluated and kept only if it clears, and labelled as such. NBA is untouched.

## File structure

NFL new: `src/nfl_predictor/tools/ablation.py`, `src/nfl_predictor/tools/ptd_eval.py` (passing-TD evaluation), `src/nfl_predictor/features/qb_td_features.py` (candidate passing-TD features). NFL modified: `models/manifest.py` (fit/record the chosen columns), `features/player_usage.py` (serve them). CFB copies `ablation.py` verbatim (separate repos).

## PR plan

PR-1: Task 1 (NFL, then the same file in CFB). PR-2: Task 2 (game blocks ablation, report only). PR-3: Tasks 3-4 (passing-TD diagnosis and candidate features, all inert). PR-4: Task 5 (enable only what cleared, if anything).

---

## Task 1 (verified): the ablation tool

**Files:** Create `src/nfl_predictor/tools/ablation.py`; Test `tests/test_ablation.py`.

**Interfaces:** Consumes `tools.block_eval.paired_bootstrap(a, b, n, seed)` (positive = b better). Produces `ablate(evaluate, base_cols, parts, n_boot=2000, seed=0) -> {"kept_parts", "kept_cols", "rounds"}`; each round row is `{part, gain, ci, kept}`.

- [ ] **Step 1: Write the failing tests.**

```python
import numpy as np
import pytest
from sklearn.linear_model import LinearRegression

from nfl_predictor.tools.ablation import ablate


def _data(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    X = {c: rng.normal(size=n) for c in ["base", "good", "good2", "noise1", "noise2"]}
    y = 2.0 * X["base"] + 1.0 * X["good"] + 0.6 * X["good2"] + rng.normal(0, 1.5, n)
    return X, y


def _evaluate_factory(X, y, split=1000):
    def evaluate(cols):
        M = np.column_stack([X[c] for c in cols])
        model = LinearRegression().fit(M[:split], y[:split])
        return (model.predict(M[split:]) - y[split:]) ** 2   # same held-out games every call
    return evaluate


def test_keeps_the_signal_and_drops_the_noise():
    X, y = _data()
    out = ablate(_evaluate_factory(X, y), ["base"], {"good": ["good"], "good2": ["good2"], "junk": ["noise1", "noise2"]})
    assert "good" in out["kept_parts"] and "good2" in out["kept_parts"] and "junk" not in out["kept_parts"]
    assert out["kept_cols"] == ["base", "good", "good2"]


def test_a_block_with_no_good_part_keeps_nothing():
    X, y = _data()
    out = ablate(_evaluate_factory(X, y), ["base"], {"junk1": ["noise1"], "junk2": ["noise2"]})
    assert out["kept_parts"] == [] and out["kept_cols"] == ["base"]


def test_the_best_part_is_tried_first_and_the_trail_is_reported():
    X, y = _data()
    out = ablate(_evaluate_factory(X, y), ["base"], {"good2": ["good2"], "good": ["good"]})
    assert [r["part"] for r in out["rounds"]][0] == "good"
    assert all(r["kept"] for r in out["rounds"][:2])


def test_a_part_scored_on_different_games_is_refused():
    calls = {"n": 0}

    def evaluate(cols):
        calls["n"] += 1
        return np.ones(100 if len(cols) == 1 else 99)

    with pytest.raises(ValueError):
        ablate(evaluate, ["base"], {"p": ["x"]})
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_ablation.py` Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""Find the part of a failing feature block that is good: forward selection over sub-blocks with a paired bootstrap.

`evaluate(columns)` returns the per-game LOSS (lower is better) of a model fitted on `columns`, scored on the SAME
held-out games every call. A sub-block joins the kept set only if the 95% interval of the improvement over the current
kept set excludes zero. Greedy, one sub-block per round, best mean gain first.
"""
from __future__ import annotations

import numpy as np

from .block_eval import paired_bootstrap


def ablate(evaluate, base_cols: list[str], parts: dict[str, list[str]], n_boot: int = 2000, seed: int = 0) -> dict:
    kept_cols = list(base_cols)
    kept_parts: list[str] = []
    cur = np.asarray(evaluate(kept_cols), float)
    n = len(cur)
    rows, remaining = [], dict(parts)
    while remaining:
        trial = {}
        for name, cols in remaining.items():
            loss = np.asarray(evaluate(kept_cols + [c for c in cols if c not in kept_cols]), float)
            if len(loss) != n:
                raise ValueError(f"sub-block {name!r} was scored on {len(loss)} games, the kept set on {n}")
            trial[name] = loss
        best = max(trial, key=lambda k: float((cur - trial[k]).mean()))
        lo, hi = paired_bootstrap(cur, trial[best], n=n_boot, seed=seed)
        gain = float((cur - trial[best]).mean())
        rows.append({"part": best, "gain": gain, "ci": (lo, hi), "kept": bool(lo > 0)})
        if lo <= 0:
            break  # the best remaining part does not clear, so none of the others can
        kept_parts.append(best)
        kept_cols += [c for c in remaining.pop(best) if c not in kept_cols]
        cur = trial[best]
    return {"kept_parts": kept_parts, "kept_cols": kept_cols, "rounds": rows}
```

- [ ] **Step 4: Run.** Expected: 4 passed.
- [ ] **Step 5: Commit.** `git add src/nfl_predictor/tools/ablation.py tests/test_ablation.py && git commit -m "feat: ablation tool, keep only the sub-blocks that clear the paired bootstrap"`. Then copy both files into CFB_Predictor (change the package name in the import) as a separate PR.

## Task 2 (DRAFTED): ablate the three failing/ambiguous game blocks

**Why:** the first honest evaluation (N=6,499) read EPA as worse on MAE, conditions as worse on MAE, and QB as better on MAE and Brier with a 0.0001 gap difference. Those are block-level answers; some sub-features may carry the signal and others the noise.

**Files:** Create `src/nfl_predictor/tools/game_ablation.py`; Test `tests/test_game_ablation.py`.

- [ ] **Step 1: Sub-blocks.** Define named parts over the columns each block already emits (`epa.epa_columns()`, `qb.QB_COLUMNS`, `conditions.CONDITION_COLUMNS`):

```python
PARTS = {
    "epa_pass_off": ["home_epa_off_pass_ewm", "away_epa_off_pass_ewm"],
    "epa_pass_def": ["home_epa_def_pass_ewm", "away_epa_def_pass_ewm"],
    "epa_rush_off": ["home_epa_off_rush_ewm", "away_epa_off_rush_ewm"],
    "epa_rush_def": ["home_epa_def_rush_ewm", "away_epa_def_rush_ewm"],
    "epa_success": ["home_success_off_ewm", "away_success_off_ewm", "home_success_def_ewm", "away_success_def_ewm"],
    "epa_edges": ["home_pass_edge", "home_rush_edge", "away_pass_edge", "away_rush_edge", "epa_net_diff"],
    "qb_epa": ["home_qb_epa_pd", "away_qb_epa_pd"],
    "qb_experience": ["home_qb_games", "away_qb_games"],
    "qb_change": ["home_qb_changed", "away_qb_changed", "home_qb_new", "away_qb_new"],
}
```

(Verify each column name against `features/epa.py` and `features/qb.py` before use; fix the names, not the structure.) Conditions parts are evaluated on TOTALS only: `wx_wind_mph`, `wx_cold`, `wx_dome`, `wx_known`.
- [ ] **Step 2: The evaluator.** `evaluate(cols)` fits the existing scaled ridge through `walk_forward._fit_predict` on the held-out seasons with `feature_cols = BASE + cols`, and returns the per-game ABSOLUTE margin error (or total error for conditions) as a numpy array over the same games every call. Write a test with the epa fixtures that two calls with different columns return arrays of equal length and that identical columns give identical output.
- [ ] **Step 3: Run it on real data (2010+ and 2000+ separately).** Write `reports/game_ablation.md` with the `rounds` table per block: part, gain, interval, kept. The QB run is repeated with the depth-chart EXPECTED starter on the held-out rows (serving-realistic), because training uses the actual starter and serving agreement is about 84-89%.
- [ ] **Step 4: Decide per part, in the report.** A part that clears becomes a registered block (`BLOCK_COLUMNS` entry such as `"qb_core"`); parts that do not clear are listed as 'not kept'. Flipping `DEFAULT_BLOCKS` is a separate PR per block (Task 5 of the model plan), with Kevin's decision.
- [ ] **Step 5: Full suite; commit by name.**

## Task 3 (DRAFTED): diagnose the passing-TD model before changing it

**Why:** the model is a negative-binomial (or Poisson) mean `mu` fitted on `passing_tds_roll` plus three yardage rolls (a QB's rushing and receiving yards add almost nothing). Before adding features, measure how good and how calibrated it is.

**Files:** Create `src/nfl_predictor/tools/ptd_eval.py`; Test `tests/test_ptd_eval.py`.

- [ ] **Step 1: The evaluator.** Walk-forward by season over QB games. For each held-out QB game record `y` (passing TDs), `mu`, and the distribution parameters from `fit_qb_passing_td_model`. Per-game loss = negative log-likelihood under the fitted distribution (`scipy.stats.nbinom`/`poisson`). Also report: MAE of `mu`; reliability of `P(Y >= 1)`, `P(Y >= 2)`, `P(Y >= 3)` in 5 equal-count buckets; and the calibration of the 'over' call at the model line (the product's published number).
- [ ] **Step 2: Failing tests (write first).**

```python
import numpy as np
import pandas as pd
from nfl_predictor.tools.ptd_eval import threshold_reliability, per_game_nll


def test_nll_is_lower_for_the_true_mean():
    y = np.random.default_rng(0).poisson(1.6, 4000)
    assert per_game_nll(y, np.full(4000, 1.6), "poisson").mean() < per_game_nll(y, np.full(4000, 2.6), "poisson").mean()


def test_threshold_reliability_is_calibrated_for_a_correct_model():
    rng = np.random.default_rng(1)
    mu = rng.uniform(0.6, 2.6, 6000)
    y = rng.poisson(mu)
    rel = threshold_reliability(y, mu, "poisson", threshold=2)
    assert rel["max_gap"] < 0.04 and rel["n"] == 6000


def test_nll_refuses_a_zero_mean():
    import pytest
    with pytest.raises(ValueError):
        per_game_nll(np.array([1]), np.array([0.0]), "poisson")
```

- [ ] **Step 3: Implement** `per_game_nll(y, mu, family, alpha=None)`, `threshold_reliability(y, mu, family, threshold, alpha=None, buckets=5)` (returns `{"n", "max_gap", "rows"}`, rows = predicted, observed, n per bucket) with `scipy.stats`. Refuse `mu <= 0`.
- [ ] **Step 4: Run on real data.** Commit `reports/ptd_baseline.md`: NLL, MAE(mu), the reliability tables for thresholds 1, 2, 3, and the model-line over-call. This is the bar every candidate is measured against. State plainly if the current model is already well calibrated (then calibration work is skipped and only features matter).
- [ ] **Step 5: Commit.**

## Task 4 (DRAFTED): candidate passing-TD features, as sub-blocks

**Why:** a QB's expected passing TDs depend on far more than his recent TD count: how many passes he throws, how good the opponent's pass defence is, how good he is per dropback, and the weather. Each candidate below uses data that already exists in the repo or in nflverse; each is evaluated by ablation, not assumed.

**Files:** Create `src/nfl_predictor/features/qb_td_features.py`; modify `features/player_usage.py` (serving) only in Task 5; Test `tests/test_qb_td_features.py`.

Candidate sub-blocks (all pre-game, shifted so game g sees only games before g):

| Part | Columns | Source |
|---|---|---|
| `volume` | `attempts_roll`, `team_pass_rate_roll`, `team_plays_roll` | player stats + pbp aggregate |
| `qb_quality` | `qb_epa_pd` (shrunk), `qb_games` | merged QB block |
| `opp_pass_defence` | `opp_epa_def_pass_ewm`, `opp_pass_defence_rank` | merged EPA block, the opposing team's pass-defence value |
| `script` | `team_implied_total`, `team_is_favourite` | schedule `spread_line`, `total_line` (OPTIONAL; kept only if it clears) |
| `conditions` | `wx_wind_mph`, `wx_cold`, `wx_dome`, `wx_known` | merged conditions block |
| `red_zone` | `rz_pass_share_roll` | pbp `yardline_100 <= 20`, pass plays, shifted |
| `receivers` | `top_receivers_out` | injuries + depth chart (the absence work) |

- [ ] **Step 1: Failing causality test for every part** (write one parametrised test): build the feature frame twice, the second time with every game ON OR AFTER a cut date perturbed; assert all features for games before the cut are identical. Plus a no-constant-column test per part and a test that a missing source gives NaN plus a `*_known` flag, never zero.
- [ ] **Step 2: Implement** each part as a function `add_<part>(qb_games_df, aux) -> DataFrame` keyed by (`game_id`, `team`, `qb_id`), shifted with the same `shift(1)` discipline as `rolling_form`. Reuse `features/epa.py` and `features/qb.py` values; do not recompute them.
- [ ] **Step 3: Ablate.** Using Task 1 and Task 3's evaluator with per-game NLL: `ablate(evaluate_nll, BASE_COLS, PARTS)` where `BASE_COLS = ["passing_tds_roll", "passing_yards_roll"]` and `evaluate_nll(cols)` fits `fit_qb_passing_td_model` on those columns and returns per-game NLL on the same held-out QB games. Commit `reports/ptd_ablation.md` with the rounds table.
- [ ] **Step 4: Calibration, only if needed.** If Task 3 showed a calibration gap that survives the kept features, fit a walk-forward isotonic or Platt map on `P(Y >= k)` using only earlier seasons per fold (the NBA calibration PR is the pattern: leak-free, and report how many held-out games are actually calibrated). If the model is already calibrated, write 'not needed' in the report.
- [ ] **Step 5: Full suite; commit by name.**

## Task 5 (DRAFTED): enable only what cleared, with serving parity

- [ ] **Step 1:** For each kept part, add its columns to the fitted list in `models/manifest._fit_qb_passing_td` and record them in the manifest entry (`feature_blocks`-style: `passing_td_parts: [...]`). `load_models` must derive the expected columns from the manifest, exactly like the game models after #47-#49.
- [ ] **Step 2:** Serve them: `build_features_for_player` emits the kept columns through the same builder used for training (the upcoming-game row appended, same code path); a parity test asserts the training row and the serving row for the same player-game are identical to 1e-9, and that a model fitted on the kept columns refuses to load if one is missing.
- [ ] **Step 3:** If NOTHING cleared, write that in `reports/ptd_ablation.md` and stop: the model stays as is. Do not enable a part that did not clear because it is 'obviously useful'.
- [ ] **Step 4:** Re-run `ptd_eval` on the final model: NLL, reliability and the over-call calibration before and after, with a paired interval on the NLL difference. Put the table in the PR; Kevin decides whether the improved model replaces the shipped one (existing recorded calls are untouched).

## Self-review

Coverage: 'keep the good part of a failing block' (Tasks 1-2, verified tool + game-block ablation incl. serving-realistic QB, totals-only conditions, 2010+ split); 'improve passing-TD predictions' (Tasks 3-5: baseline diagnosis, seven candidate sub-blocks, ablation by NLL, optional calibration, parity-checked enablement). Placeholders: Tasks 2-5 are drafted and labelled; column names in Task 2 must be checked against the modules. Names used consistently: `ablate`, `PARTS`, `per_game_nll`, `threshold_reliability`.
