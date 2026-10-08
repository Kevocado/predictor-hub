# NFL + CFB model improvement: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NFL and CFB game models measurably better and honest about their uncertainty: out-of-fold sigma, scaled linear models, one train/serve feature path, then evidence-gated feature blocks (EPA offence-vs-defence, quarterback, game conditions, college priors).

**Architecture:** Same block framework as the NBA plan (`2026-10-08-nba-feature-pipeline-impl.md`). Features are grouped into blocks; `DEFAULT_BLOCKS=()` keeps production unchanged; a block joins the default only when it clears the evaluation rule below. Serving builds features through the SAME `_assemble` code the training frame uses, so a feature can never be computed one way for training and another for serving.

**Tech Stack:** Python 3.11 (uv), pandas, numpy, scikit-learn, xgboost (existing), nflreadpy/nflverse parquet (existing), CFBD (existing client, 1,000 calls/month), Open-Meteo (free, no key). No new dependencies.

**Spec:** the review findings delivered in chat on 2026-10-08 ("NFL and CFB model review"); the block framework design in `docs/superpowers/plans/2026-10-08-nba-feature-blocks.md`.

**Verified vs drafted:** Tasks 1-6 and 9 were built and run in scratch worktrees against NFL_Predictor `main` and CFB_Predictor `main` (NFL full suite 1153 passed / 20 skipped; CFB full suite 578 passed / 21 skipped). Their code below is the code that ran. Tasks 7, 8, 10, 11, 12 are DRAFTED: real code and tests, but not executed; run them and expect small adjustments. Each task says which it is.

## Global Constraints

- Recorded picks are immutable; nothing here rewrites a stored prediction. Every recorded pick counts in the track record.
- Python 3.11 for NFL and CFB: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider`. Run the FULL suite before reporting anything. Tests never touch the network; data comes from fixtures or injected fakes.
- Every feature for game g uses only games strictly before g (causality test per block). The one stated exception is the QB block's TRAINING value, which names the quarterback who actually started game g, because that is knowable pre-kickoff; serving uses the depth-chart expected starter and Task 10 measures the agreement between the two.
- Train/serve parity: a fitted model is scored only on the columns it was fitted on, rebuilt the way it was fitted. A missing fitted column is a loud error, never a silent zero.
- A block ships (joins `DEFAULT_BLOCKS`) only if the paired-bootstrap 95% interval of the improvement excludes zero on every metric it claims (margin MAE, home-win Brier) AND the 5-bucket calibration gap does not widen, on identical held-out games. Report null and negative results as plainly as wins.
- Never `git add -A`; add files by name. Never push to main; branch and PR. Use a git worktree, never switch branches in a shared clone. Never read, print or commit any API key.
- CFBD budget: 1,000 calls/month. Any CFBD pull is a one-time, committed, resumable batch with a call counter; the evaluation and tests use recorded fixtures only.
- Weather is Open-Meteo only (free, keyless). Forecast for upcoming games, archive for history; a failed fetch means "no conditions", never a guessed value.

## File structure

NFL new: `data/pbp_agg.py`, `features/{epa,qb,conditions}.py`, `features/elo_fit.py`, `tools/block_eval.py`, `tools/qb_agreement.py`. NFL modified: `models/game_outcome.py`, `models/manifest.py`, `evaluate/walk_forward.py`, `features/build.py`, `api/routes.py`, `api/facts.py`.
CFB new: `data/cfbd_advanced.py`, `features/priors.py`, `tools/block_eval.py`. CFB modified: the same six files as NFL (sigma, scaling, unified builder, conference fix).

## PR plan

PR-1 (NFL): Tasks 1-2. PR-2 (CFB): Task 3. PR-3 (NFL blocks, all inert): Tasks 4-8. PR-4 (NFL evaluation + wiring): Tasks 9-10. PR-5 (CFB blocks): Tasks 11-12. After PR-4 and PR-5, run the evaluation on real data, report per block, and only then flip `DEFAULT_BLOCKS` in a separate small PR per block.

---

## Task 1 (NFL, verified): out-of-fold sigma and scaled ridge

**Why:** the margin model's sigma is the residual spread on the data it was fitted on, so win probabilities are over-confident; and an unscaled `Ridge(alpha=1)` penalises features by their units (rest days vs Elo points).

**Files:**
- Modify: `src/nfl_predictor/models/game_outcome.py`, `src/nfl_predictor/evaluate/walk_forward.py`, `src/nfl_predictor/models/manifest.py`
- Test: `tests/test_oof_sigma.py`

**Interfaces:**
- Produces: `sigma_from_residuals(residuals) -> float`; `oof_residuals(folds, candidate, target="margin") -> np.ndarray`; `fit_sigmas(folds, chosen)` in `manifest.py`; `fit_margin_regression` returns a `StandardScaler -> Ridge` pipeline.

- [ ] **Step 1: Write the failing tests** (all six fail on current `main`).

```python
"""Sigma comes from error the model has not been fitted on, and the ridge is invariant to feature units."""
import numpy as np
import pandas as pd
import pytest

from nfl_predictor.evaluate import walk_forward
from nfl_predictor.models import game_outcome, manifest

NOISE = 10.0
COLS = [f"f{i}" for i in range(6)]


def _folds(n_seasons=7, games=80, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for s in range(n_seasons):
        X = pd.DataFrame(rng.normal(size=(games, len(COLS))), columns=COLS)
        X["season"] = 2018 + s
        X["margin"] = 3 * X["f0"] - 2 * X["f1"] + rng.normal(0, NOISE, games)
        X["total_points"] = 45 + 4 * X["f2"] + rng.normal(0, NOISE, games)
        frames.append(X)
    df = pd.concat(frames, ignore_index=True)
    return [
        {"val_season": 2018 + i, "train_df": df[df["season"] < 2018 + i], "val_df": df[df["season"] == 2018 + i], "feature_cols": COLS}
        for i in range(3, n_seasons)
    ], df


def test_in_sample_sigma_understates_and_out_of_fold_sigma_does_not():
    folds, df = _folds()
    train = df[df["season"] < 2024]
    in_sample = game_outcome.residual_sigma(game_outcome.fit_xgb_margin(train[COLS], train["margin"]), train[COLS], train["margin"])
    oof = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "margin"))
    assert in_sample < 0.8 * NOISE, "an overfit model's training error is optimistic: this is the bug"
    assert oof > 1.15 * in_sample
    assert oof == pytest.approx(NOISE, rel=0.25)


def test_the_manifest_sigmas_are_out_of_fold_for_the_margin_and_the_total():
    folds, df = _folds()
    sigma, total_sigma = manifest.fit_sigmas(folds, "ridge")
    assert sigma == pytest.approx(game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "ridge", "margin")))
    assert total_sigma == pytest.approx(game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "total_points")))
    train = df[df["season"] < 2024]
    in_sample_total = game_outcome.residual_sigma(game_outcome.fit_xgb_margin(train[COLS], train["total_points"]), train[COLS], train["total_points"])
    assert total_sigma > in_sample_total


def test_a_folds_sigma_is_the_error_on_the_last_training_season_of_a_model_that_never_saw_it():
    folds, _ = _folds()
    train = folds[-1]["train_df"]
    last = sorted(train["season"].unique())[-1]
    earlier, held_out = train[train["season"] != last], train[train["season"] == last]
    manual = game_outcome.sigma_from_residuals(
        held_out["margin"].to_numpy(float) - game_outcome.fit_xgb_margin(earlier[COLS], earlier["margin"]).predict(held_out[COLS].fillna(0))
    )
    assert walk_forward._honest_sigma("xgb", train, COLS) == pytest.approx(manual)


def test_a_single_training_season_falls_back_to_the_in_sample_spread_and_says_so():
    folds, df = _folds()
    one_season = df[df["season"] == 2018]
    assert walk_forward._honest_sigma("ridge", one_season, COLS) > 0


def test_oof_residuals_refuse_an_unknown_candidate_and_the_elo_total():
    folds, _ = _folds()
    with pytest.raises(ValueError):
        walk_forward.oof_residuals(folds, "nope")
    with pytest.raises(ValueError):
        walk_forward._fit_predict("elo", folds[0]["train_df"], folds[0]["val_df"], COLS, "total_points")


def test_ridge_predictions_do_not_depend_on_the_units_of_a_feature():
    _, df = _folds()
    train, val = df[df["season"] < 2024], df[df["season"] == 2024]
    a = game_outcome.fit_margin_regression(train[COLS], train["margin"]).predict(val[COLS])
    scaled_train, scaled_val = train.copy(), val.copy()
    scaled_train["f0"] *= 1000.0
    scaled_val["f0"] *= 1000.0
    b = game_outcome.fit_margin_regression(scaled_train[COLS], scaled_train["margin"]).predict(scaled_val[COLS])
    np.testing.assert_allclose(a, b, atol=1e-6)
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_oof_sigma.py` Expected: failures/import errors (`sigma_from_residuals`, `oof_residuals` do not exist).

- [ ] **Step 3: Apply the changes.**

```diff
diff --git a/src/nfl_predictor/models/game_outcome.py b/src/nfl_predictor/models/game_outcome.py
index 69bead0..1ceb33a 100644
--- a/src/nfl_predictor/models/game_outcome.py
+++ b/src/nfl_predictor/models/game_outcome.py
@@ -19,6 +19,8 @@ import numpy as np
 import pandas as pd
 from scipy.stats import norm
 from sklearn.linear_model import Ridge
+from sklearn.pipeline import Pipeline, make_pipeline
+from sklearn.preprocessing import StandardScaler
 from xgboost import XGBRegressor
 
 # Points-per-Elo-point conversion for the Elo candidate: derived once from a
@@ -41,8 +43,11 @@ def predict_margin_elo(candidate: dict, rating_diff: float, home_rest_days: floa
     return rating_diff * candidate["points_per_rating_point"] + 0.05 * (home_rest_days - away_rest_days)
 
 
-def fit_margin_regression(X_train: pd.DataFrame, y_margin: pd.Series) -> Ridge:
-    model = Ridge(alpha=1.0)
+def fit_margin_regression(X_train: pd.DataFrame, y_margin: pd.Series) -> Pipeline:
+    """Ridge on STANDARDISED features. The columns arrive in very different units (an Elo near 1500, points near 20,
+    rest days near 7); an L2 penalty on raw columns shrinks the small-unit features hardest, so which feature set
+    "wins" would depend on its units. Standardising inside the model makes predictions invariant to rescaling."""
+    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
     model.fit(X_train.fillna(0), y_margin)
     return model
 
@@ -68,6 +73,19 @@ def residual_sigma(model, X_val: pd.DataFrame, y_val: pd.Series) -> float:
     return float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals) or 1.0)
 
 
+def sigma_from_residuals(residuals) -> float:
+    """Spread of OUT-OF-SAMPLE residuals: the figure every cover/over/win probability divides by.
+
+    A model's error on its own training rows is optimistic (XGBoost most of all), so a sigma fitted there makes
+    every published probability overconfident. This takes residuals that were never fitted on.
+    """
+    r = np.asarray(residuals, dtype=float)
+    r = r[np.isfinite(r)]
+    if len(r) == 0:
+        return 1.0
+    return float(np.std(r, ddof=1)) if len(r) > 1 else float(np.std(r) or 1.0)
+
+
 def _line_or_none(line: float | None) -> float | None:
     """A missing line is NaN as often as it is None. nflverse writes NaN, and `is not None` let it
     through, so a game with no line produced NaN cover/over probabilities instead of none."""
```

```diff
diff --git a/src/nfl_predictor/evaluate/walk_forward.py b/src/nfl_predictor/evaluate/walk_forward.py
index 00a11c0..f3ae90c 100644
--- a/src/nfl_predictor/evaluate/walk_forward.py
+++ b/src/nfl_predictor/evaluate/walk_forward.py
@@ -16,8 +16,8 @@ from ..features.build import build_training_frame
 from ..models import game_outcome
 
 
-def prepare_folds(games_df: pd.DataFrame, min_train_seasons: int = 2) -> list[dict]:
-    df, feature_cols = build_training_frame(games_df)
+def prepare_folds(games_df: pd.DataFrame, min_train_seasons: int = 2, blocks: tuple[str, ...] = (), aux=None) -> list[dict]:
+    df, feature_cols = build_training_frame(games_df, blocks=blocks, aux=aux)
     seasons = sorted(df["season"].unique())
 
     folds = []
@@ -59,27 +59,44 @@ class _EloModelAdapter:
         return _predict_margin_elo_batch(self.candidate, X)
 
 
-def _predict_margins(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str]):
-    X_train, y_train = train_df[feature_cols], train_df["margin"]
-    X_val = val_df[feature_cols]
-
+def _fit_predict(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str], target: str = "margin") -> np.ndarray:
+    """Fit `candidate` on `train_df` and predict `target` for `val_df`. Nothing from `val_df` reaches the fit."""
     if candidate == "elo":
-        model = game_outcome.fit_elo_candidate(train_df)
-        preds = _predict_margin_elo_batch(model, val_df)
-        sigma = game_outcome.residual_sigma(_EloModelAdapter(model), X_train, y_train)
-        return preds, sigma
-
-    if candidate == "ridge":
-        fit_fn = game_outcome.fit_margin_regression
-    elif candidate == "xgb":
-        fit_fn = game_outcome.fit_xgb_margin
-    else:
+        if target != "margin":
+            raise ValueError("the elo candidate predicts the margin only")
+        return _predict_margin_elo_batch(game_outcome.fit_elo_candidate(train_df), val_df)
+    fit_fn = {"ridge": game_outcome.fit_margin_regression, "xgb": game_outcome.fit_xgb_margin}.get(candidate)
+    if fit_fn is None:
         raise ValueError(f"Unknown candidate: {candidate!r}")
+    return fit_fn(train_df[feature_cols], train_df[target]).predict(val_df[feature_cols].fillna(0))
+
+
+def _honest_sigma(candidate: str, train_df: pd.DataFrame, feature_cols: list[str], target: str = "margin") -> float:
+    """Sigma for a fold, from error the model has NOT been fitted on: the last TRAINING season is held out of an
+    inner fit on the seasons before it. A fold with a single training season has nothing to hold out and falls
+    back to the in-sample spread (optimistic; only the smallest folds ever take this branch)."""
+    seasons = sorted(train_df["season"].unique())
+    if len(seasons) < 2:
+        preds = _fit_predict(candidate, train_df, train_df, feature_cols, target)
+        return game_outcome.sigma_from_residuals(train_df[target].to_numpy(float) - preds)
+    inner_train = train_df[train_df["season"] != seasons[-1]]
+    inner_val = train_df[train_df["season"] == seasons[-1]]
+    preds = _fit_predict(candidate, inner_train, inner_val, feature_cols, target)
+    return game_outcome.sigma_from_residuals(inner_val[target].to_numpy(float) - preds)
+
+
+def oof_residuals(folds: list[dict], candidate: str, target: str = "margin") -> np.ndarray:
+    """Every validation season's residuals, each predicted by a model trained only on EARLIER seasons."""
+    pieces = []
+    for fold in folds:
+        preds = _fit_predict(candidate, fold["train_df"], fold["val_df"], fold["feature_cols"], target)
+        pieces.append(fold["val_df"][target].to_numpy(float) - preds)
+    return np.concatenate(pieces) if pieces else np.array([])
 
-    model = fit_fn(X_train, y_train)
-    preds = model.predict(X_val.fillna(0))
-    sigma = game_outcome.residual_sigma(model, X_train, y_train)
-    return preds, sigma
+
+def _predict_margins(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str]):
+    preds = _fit_predict(candidate, train_df, val_df, feature_cols, "margin")
+    return preds, _honest_sigma(candidate, train_df, feature_cols, "margin")
 
 
 def pooled_predictions(folds: list[dict], candidate: str) -> tuple[np.ndarray, np.ndarray]:
```

```diff
diff --git a/src/nfl_predictor/models/manifest.py b/src/nfl_predictor/models/manifest.py
index e2a7334..cf929bc 100644
--- a/src/nfl_predictor/models/manifest.py
+++ b/src/nfl_predictor/models/manifest.py
@@ -102,6 +102,14 @@ def _passing_td_manifest_entry(fitted: dict | None) -> dict | None:
     }
 
 
+def fit_sigmas(folds: list[dict], chosen: str) -> tuple[float, float]:
+    """(margin sigma, total sigma) from pooled out-of-fold residuals: the chosen game model for the margin and the
+    XGBoost total model for the total, each predicted on seasons it was never trained on."""
+    sigma = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, chosen, "margin"))
+    total_sigma = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "total_points"))
+    return sigma, total_sigma
+
+
 def train_all(seasons: list[int] | None = None) -> dict:
     """Fit all models, persist their artifacts, and return their manifest."""
     MODELS_DIR.mkdir(exist_ok=True, parents=True)
@@ -130,20 +138,10 @@ def train_all(seasons: list[int] | None = None) -> dict:
     else:
         game_model = game_outcome.fit_xgb_margin(X_train, y_margin)
 
-    if chosen == "elo":
-        margin_preds = train_df.apply(
-            lambda r: game_outcome.predict_margin_elo(
-                game_model, r["rating_diff"], r["home_rest_days"], r["away_rest_days"]
-            ),
-            axis=1,
-        )
-        sigma_model = type("_", (), {"predict": lambda self, X: margin_preds.to_numpy()})()
-        sigma = game_outcome.residual_sigma(sigma_model, X_train, y_margin)
-    else:
-        sigma = game_outcome.residual_sigma(game_model, X_train, y_margin)
-
+    # Sigma from OUT-OF-SAMPLE residuals (the pooled walk-forward folds), never from the training rows the model
+    # was fitted on: an in-sample sigma is optimistic and made every published probability overconfident.
+    sigma, total_sigma = fit_sigmas(folds, chosen)
     total_model = game_outcome.fit_xgb_margin(X_train, y_total)
-    total_sigma = game_outcome.residual_sigma(total_model, X_train, y_total)
 
     _save_pickle(game_model, _artifact_path(GAME_MODEL_FILENAME))
     _save_pickle(total_model, _artifact_path(TOTAL_MODEL_FILENAME))
```

- [ ] **Step 4: Run the new tests, then the full suite.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider` Expected: all pass (1153 passed, 20 skipped on the verified run, which included Task 2).

- [ ] **Step 5: Commit.**

```bash
git add tests/test_oof_sigma.py src/nfl_predictor/models/game_outcome.py src/nfl_predictor/evaluate/walk_forward.py src/nfl_predictor/models/manifest.py
git commit -m "fix: out-of-fold sigma and scaled ridge for the margin model"
```

## Task 2 (NFL, verified): one feature path for training and serving

**Why:** serving built features with a separate function from training and measured rest to today rather than to the game date. One path (`_assemble`) removes the class of bug.

**Files:**
- Modify: `src/nfl_predictor/features/build.py`, `src/nfl_predictor/api/routes.py`, `src/nfl_predictor/api/facts.py`
- Modify (test doubles accept the new `gameday` keyword): `tests/test_api_routes.py`, `tests/test_facts.py`, `tests/test_snapshot_window.py`, `tests/test_fitted_vs_served_columns.py`
- Test: `tests/test_serving_training_parity.py`

**Interfaces:**
- Produces: `build_features_for_game(home, away, games_df, gameday=None, blocks=(), aux=None, starters=None) -> dict`; `feature_columns(blocks)`; `BLOCK_COLUMNS`; `DEFAULT_BLOCKS=()`; `Aux` dataclass (`efficiency`, `qb_games`, `upcoming_starters`).

- [ ] **Step 1: Write the failing test.**

```python
"""A game's served feature row equals the row training builds for the same game (same code path, same values)."""
import numpy as np
import pandas as pd
import pytest

from nfl_predictor.features import build


def _season_games(seed=3, seasons=(2023, 2024, 2025), weeks=14):
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(8)]
    rows = []
    for season in seasons:
        for week in range(1, weeks + 1):
            order = list(rng.permutation(teams))
            n_games = 3 if week % 4 == 0 else 4          # a bye week for some teams every fourth week
            for i in range(0, 2 * n_games, 2):
                home, away = order[i], order[i + 1]
                rows.append({
                    "game_id": f"{season}_{week:02d}_{home}_{away}", "season": season, "week": week,
                    "gameday": pd.Timestamp(f"{season}-09-07") + pd.Timedelta(days=7 * (week - 1)) + pd.Timedelta(days=int(rng.choice([0, 0, 0, 4]))),
                    "home_team": home, "away_team": away,
                    "home_score": int(rng.integers(6, 42)), "away_score": int(rng.integers(6, 42)), "div_game": 0,
                })
    return pd.DataFrame(rows)


def test_the_served_row_equals_the_row_training_builds_for_the_same_game():
    games = _season_games()
    trained, cols = build.build_training_frame(games)
    sample = trained[trained["season"] == 2025].sample(15, random_state=1)
    for _, g in sample.iterrows():
        history = games[pd.to_datetime(games["gameday"]) < pd.Timestamp(g["gameday"])]
        served = build.build_features_for_game(g["home_team"], g["away_team"], history, gameday=g["gameday"])
        np.testing.assert_allclose(served[cols].to_numpy(float), g[cols].to_numpy(float), equal_nan=True, err_msg=g["game_id"])


def test_rest_days_are_measured_to_the_games_own_date_not_to_today():
    games = _season_games()
    last = pd.to_datetime(games["gameday"]).max()
    when = last + pd.Timedelta(days=9)
    team = games.sort_values("gameday").iloc[-1]["home_team"]
    served = build.build_features_for_game(team, "T7" if team != "T7" else "T6", games, gameday=when)
    last_played = pd.to_datetime(games[(games["home_team"] == team) | (games["away_team"] == team)]["gameday"]).max()
    assert served["home_rest_days"] == (when - last_played).days


def test_unplayed_rows_in_the_history_do_not_enter_the_form_or_the_ratings():
    games = _season_games()
    future = games.iloc[[-1]].copy()
    future["game_id"], future["home_score"], future["away_score"] = "future", np.nan, np.nan
    future["gameday"] = pd.Timestamp("2026-01-04")
    with_future = pd.concat([games, future], ignore_index=True)
    a = build.build_features_for_game("T0", "T1", games, gameday="2026-01-11")
    b = build.build_features_for_game("T0", "T1", with_future, gameday="2026-01-11")
    pd.testing.assert_series_equal(a, b)


def test_the_row_has_exactly_the_feature_columns_in_order():
    games = _season_games()
    assert list(build.build_features_for_game("T0", "T1", games, gameday="2026-01-11").index) == build.FEATURE_COLUMNS
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_serving_training_parity.py` Expected: FAIL (`gameday` keyword / parity assertions).

- [ ] **Step 3: Apply the changes.**

```diff
diff --git a/src/nfl_predictor/features/build.py b/src/nfl_predictor/features/build.py
index 576a921..2c13f4c 100644
--- a/src/nfl_predictor/features/build.py
+++ b/src/nfl_predictor/features/build.py
@@ -7,9 +7,12 @@ features/build.py documents.
 
 from __future__ import annotations
 
+import numpy as np
 import pandas as pd
 
-from . import power_ratings, rest_days, rolling_form
+from dataclasses import dataclass
+
+from . import epa, power_ratings, qb, rest_days, rolling_form
 
 FEATURE_COLUMNS = [
     "home_pregame_rating", "away_pregame_rating", "rating_diff",
@@ -20,7 +23,46 @@ FEATURE_COLUMNS = [
 ]
 
 
-def _assemble(games_df: pd.DataFrame) -> pd.DataFrame:
+#: Feature BLOCKS beyond the ten base columns. A block joins DEFAULT_BLOCKS only in the PR that shows it clears the
+#: evaluation bar (paired-bootstrap intervals + calibration gap, on identical held-out games).
+BLOCK_COLUMNS: dict[str, list[str]] = {"epa": epa.epa_columns(), "qb": list(qb.QB_COLUMNS)}
+DEFAULT_BLOCKS: tuple[str, ...] = ()
+
+
+def feature_columns(blocks: tuple[str, ...] = DEFAULT_BLOCKS) -> list[str]:
+    unknown = [b for b in blocks if b not in BLOCK_COLUMNS]
+    if unknown:
+        raise ValueError(f"unknown feature blocks: {unknown}; known: {sorted(BLOCK_COLUMNS)}")
+    cols = list(FEATURE_COLUMNS)
+    for block in blocks:
+        cols += BLOCK_COLUMNS[block]
+    return cols
+
+
+@dataclass
+class Aux:
+    """The extra inputs the blocks read. `efficiency` is pbp_agg.team_game_efficiency(), `qb_games` is
+    pbp_agg.qb_games(), `upcoming_starters` maps (game_id, team) to the expected starting QB's id for games not yet played."""
+
+    efficiency: pd.DataFrame | None = None
+    qb_games: pd.DataFrame | None = None
+    upcoming_starters: dict | None = None
+
+
+def _assemble(games_df: pd.DataFrame, blocks: tuple[str, ...] = (), aux: Aux | None = None) -> pd.DataFrame:
+    df = _assemble_base(games_df)
+    if "epa" in blocks:
+        if aux is None or aux.efficiency is None:
+            raise ValueError("the epa block needs aux.efficiency; refusing to default it to zeros")
+        df = epa.add_epa_features(df, aux.efficiency)
+    if "qb" in blocks:
+        if aux is None or aux.qb_games is None:
+            raise ValueError("the qb block needs aux.qb_games; refusing to default it to a neutral QB")
+        df = qb.add_qb_features(df, aux.qb_games, upcoming_starters=aux.upcoming_starters)
+    return df
+
+
+def _assemble_base(games_df: pd.DataFrame) -> pd.DataFrame:
     df = power_ratings.compute_pregame_ratings(games_df)
     df = rolling_form.add_rolling_form(df)
     df = rest_days.add_rest_days(df)
@@ -33,12 +75,15 @@ def _assemble(games_df: pd.DataFrame) -> pd.DataFrame:
     return df
 
 
-def build_training_frame(games_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
-    df = _assemble(games_df)
+def build_training_frame(
+    games_df: pd.DataFrame, blocks: tuple[str, ...] = DEFAULT_BLOCKS, aux: Aux | None = None,
+) -> tuple[pd.DataFrame, list[str]]:
+    columns = feature_columns(blocks)
+    df = _assemble(games_df, blocks, aux)
     played = df[df["home_score"].notna() & df["away_score"].notna()].reset_index(drop=True)
     played["margin"] = played["home_score"] - played["away_score"]
     played["total_points"] = played["home_score"] + played["away_score"]
-    return played, FEATURE_COLUMNS
+    return played, columns
 
 
 def _div_game_for(games_df: pd.DataFrame, home_team: str, away_team: str) -> int:
@@ -83,68 +128,38 @@ def _div_game_for(games_df: pd.DataFrame, home_team: str, away_team: str) -> int
     return 0 if pd.isna(value) else int(value)
 
 
-def build_features_for_game(home_team: str, away_team: str, games_df: pd.DataFrame) -> pd.Series:
-    """One live feature row for an upcoming home_team vs away_team game,
-    computed from every played game in games_df (ratings/rolling form as of
-    right now)."""
-    ratings = power_ratings.final_ratings(games_df)
-    played = games_df[games_df["home_score"].notna() & games_df["away_score"].notna()]
-
-    def _recent_form(team: str) -> tuple[float, float]:
-        appearances = pd.concat(
-            [
-                played[played["home_team"] == team][["gameday", "home_score", "away_score"]].rename(
-                    columns={"home_score": "scored", "away_score": "allowed"}
-                ),
-                played[played["away_team"] == team][["gameday", "away_score", "home_score"]].rename(
-                    columns={"away_score": "scored", "home_score": "allowed"}
-                ),
-            ]
-        ).sort_values("gameday")
-        recent = appearances.tail(5)
-        if recent.empty:
-            return float("nan"), float("nan")
-        return float(recent["scored"].mean()), float(recent["allowed"].mean())
-
-    def _rest_days(team: str) -> float | None:
-        appearances = pd.concat(
-            [
-                played[played["home_team"] == team][["gameday"]],
-                played[played["away_team"] == team][["gameday"]],
-            ]
-        ).sort_values("gameday")
-        if appearances.empty:
-            return None
-        last_game = pd.to_datetime(appearances.iloc[-1]["gameday"])
-        return float((pd.Timestamp.now().normalize() - last_game).days)
-
-    home_scored, home_allowed = _recent_form(home_team)
-    away_scored, away_allowed = _recent_form(away_team)
-    home_rating = ratings.get(home_team, power_ratings.DEFAULT_START_RATING)
-    away_rating = ratings.get(away_team, power_ratings.DEFAULT_START_RATING)
-    home_rest = _rest_days(home_team)
-    away_rest = _rest_days(away_team)
-
-    # `div_game` is a real modelled feature (FEATURE_COLUMNS) and training fills
-    # it from the schedule, where it toggles for roughly a third of games. It
-    # used to be hardcoded to 0 here, so the model was fitted with the covariate
-    # varying and served with it permanently constant -- the fitted coefficient
-    # was dead weight at inference. Read it from the schedule for this matchup
-    # when the column is present, and fall back to 0 for any games frame that
-    # does not carry it (which is also the training default).
-    div_game = _div_game_for(games_df, home_team, away_team)
-
-    return pd.Series(
-        {
-            "home_pregame_rating": home_rating,
-            "away_pregame_rating": away_rating,
-            "rating_diff": home_rating - away_rating,
-            "home_points_scored_roll": home_scored,
-            "home_points_allowed_roll": home_allowed,
-            "away_points_scored_roll": away_scored,
-            "away_points_allowed_roll": away_allowed,
-            "home_rest_days": home_rest if home_rest is not None else 7.0,
-            "away_rest_days": away_rest if away_rest is not None else 7.0,
-            "div_game": div_game,
-        }
-    )
+def build_features_for_game(
+    home_team: str, away_team: str, games_df: pd.DataFrame, gameday: str | pd.Timestamp | None = None,
+    blocks: tuple[str, ...] = DEFAULT_BLOCKS, aux: Aux | None = None, starters: dict[str, str | None] | None = None,
+) -> pd.Series:
+    """One feature row for an upcoming home_team vs away_team game, built by the SAME code that builds training rows.
+
+    The upcoming game is appended to the PLAYED games (no result, its own date) and the whole frame goes through
+    `_assemble`, so ratings, rolling form and rest days are computed exactly as they are for a training row. This used
+    to be a second, hand-written implementation, and it measured rest as the days from the last game to TODAY, not to
+    the game: a game five days out was served with five fewer rest days than the model was fitted on.
+
+    `gameday` is the game's date; None means today (an ad-hoc "if they played now" request). `starters` maps each team
+    to its expected starting QB id for the `qb` block (never guessed: an unknown starter is a neutral, "new" QB).
+    """
+    played = games_df[games_df["home_score"].notna() & games_df["away_score"].notna()].copy()
+    when = pd.Timestamp(gameday) if gameday is not None else pd.Timestamp.now().normalize()
+    upcoming = {c: np.nan for c in played.columns}
+    upcoming.update({
+        "game_id": "__upcoming__", "gameday": when, "home_team": home_team, "away_team": away_team,
+        "home_score": np.nan, "away_score": np.nan, "div_game": _div_game_for(games_df, home_team, away_team),
+    })
+    if "season" in played.columns and played["season"].notna().any():
+        upcoming["season"] = played["season"].max()
+    frame = pd.concat([played, pd.DataFrame([upcoming])], ignore_index=True)
+    frame["gameday"] = pd.to_datetime(frame["gameday"])
+    if starters:
+        known = dict(aux.upcoming_starters or {}) if aux is not None else {}
+        known.update({("__upcoming__", team): qb_id for team, qb_id in starters.items()})
+        aux = Aux(aux.efficiency if aux else None, aux.qb_games if aux else None, known)
+    row = _assemble(frame, blocks, aux)
+    served = row[row["game_id"] == "__upcoming__"].iloc[0]
+    # What `_assemble` produced, in the declared order. A column declared in FEATURE_COLUMNS but never assembled is
+    # absent here, and `manifest.load_models` compares this against what each model was fitted on and refuses the
+    # mismatch: the declared list is the code's claim, and this is what the code actually builds.
+    return served[[c for c in feature_columns(blocks) if c in served.index]]
```

```diff
diff --git a/src/nfl_predictor/api/routes.py b/src/nfl_predictor/api/routes.py
index a64a23f..14c0d8d 100644
--- a/src/nfl_predictor/api/routes.py
+++ b/src/nfl_predictor/api/routes.py
@@ -157,8 +157,9 @@ def _load_models_cached() -> dict:
 def _predict_game_from_models(
     models: dict, home: str, away: str, games_df: pd.DataFrame,
     spread_line: float | None = None, total_line: float | None = None,
+    gameday=None,
 ) -> dict:
-    feature_row = feature_build.build_features_for_game(home, away, games_df)
+    feature_row = feature_build.build_features_for_game(home, away, games_df, gameday=gameday)
     feature_cols = models["feature_cols"]
     X = feature_row.reindex(feature_cols).fillna(0)
 
@@ -379,6 +380,7 @@ def _get_game_prediction_live(season: int, week: int, game_id: str):
     prediction = _predict_game_from_models(
         models, game["home_team"], game["away_team"], history,
         spread_line=game.get("spread_line"), total_line=game.get("total_line"),
+        gameday=game.get("gameday"),
     )
     return prediction
 
@@ -408,6 +410,7 @@ def _get_predictions_batch_live(season: int, week: int) -> dict:
             predictions[game["game_id"]] = _predict_game_from_models(
                 models, game["home_team"], game["away_team"], game_history,
                 spread_line=game.get("spread_line"), total_line=game.get("total_line"),
+                gameday=game.get("gameday"),
             )
         except Exception:
             logger.exception("batch prediction failed for game_id=%s", game.get("game_id"))
@@ -1132,6 +1135,7 @@ def background_tracking_tick(season: int, week: int) -> None:
                 pred = _predict_game_from_models(
                     models, game["home_team"], game["away_team"], history,
                     spread_line=game.get("spread_line"), total_line=game.get("total_line"),
+                    gameday=game.get("gameday"),
                 )
                 predictions.append(
                     {
@@ -1243,6 +1247,7 @@ def background_tracking_tick(season: int, week: int) -> None:
                         pred = _predict_game_from_models(
                             models, game["home_team"], game["away_team"], history_excl,
                             spread_line=game.get("spread_line"), total_line=game.get("total_line"),
+                            gameday=game.get("gameday"),
                         )
                         backfill_games.append({
                             "game_id": game["game_id"], "home_team": game["home_team"], "away_team": game["away_team"],
```

```diff
diff --git a/src/nfl_predictor/api/facts.py b/src/nfl_predictor/api/facts.py
index adf8c08..de4a128 100644
--- a/src/nfl_predictor/api/facts.py
+++ b/src/nfl_predictor/api/facts.py
@@ -355,7 +355,7 @@ def _drivers(game: dict, season: int, home_team: str, away_team: str, live_ok: b
         try:
             history = routes._load_game_history(season)
             history = history[history["game_id"] != game["game_id"]]
-            row = routes.feature_build.build_features_for_game(home_team, away_team, history)
+            row = routes.feature_build.build_features_for_game(home_team, away_team, history, gameday=game.get("gameday"))
             rating_diff = _num(row.get("rating_diff"))
             home_rest = _num(row.get("home_rest_days"))
             away_rest = _num(row.get("away_rest_days"))
```

Widen the test doubles (the callers now pass `gameday=`):

```diff
diff --git a/tests/test_api_routes.py b/tests/test_api_routes.py
index 848d0fc..89f8125 100644
--- a/tests/test_api_routes.py
+++ b/tests/test_api_routes.py
@@ -41,7 +41,7 @@ def client(monkeypatch):
     )
     monkeypatch.setattr(
         routes, "_predict_game_from_models",
-        lambda models, home, away, games_df, spread_line=None, total_line=None: {
+        lambda models, home, away, games_df, spread_line=None, total_line=None, gameday=None: {
             "home_win_prob": 0.6, "away_win_prob": 0.4, "home_cover_prob": 0.55, "away_cover_prob": 0.45,
             "over_prob": 0.52, "under_prob": 0.48,
         },
@@ -80,7 +80,7 @@ def test_predict_game_from_models_includes_sigma_and_total_sigma(monkeypatch):
 
     monkeypatch.setattr(
         routes.feature_build, "build_features_for_game",
-        lambda home, away, games_df: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
+        lambda home, away, games_df, gameday=None: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
     )
     models = {
         "feature_cols": ["rating_diff", "home_rest_days", "away_rest_days"],
@@ -385,7 +385,7 @@ def test_get_predictions_batch_skips_one_failing_game_without_failing_the_rest(c
         ),
     )
 
-    def flaky_predict(models, home, away, games_df, spread_line=None, total_line=None):
+    def flaky_predict(models, home, away, games_df, spread_line=None, total_line=None, gameday=None):
         if home == "BAL":
             raise ValueError("feature build blew up")
         return {"home_win_prob": 0.6, "away_win_prob": 0.4}
```

```diff
diff --git a/tests/test_facts.py b/tests/test_facts.py
index e6d8998..f0f1649 100644
--- a/tests/test_facts.py
+++ b/tests/test_facts.py
@@ -458,7 +458,7 @@ def live(monkeypatch):
     # under it. The real builder emits all ten.
     monkeypatch.setattr(
         facts_mod.routes.feature_build, "build_features_for_game",
-        lambda home, away, history: pd.Series(
+        lambda home, away, history, gameday=None: pd.Series(
             {c: float(i + 1) for i, c in enumerate(facts_mod.routes.feature_build.FEATURE_COLUMNS)}
             | {"rating_diff": 7.0, "home_rest_days": 6, "away_rest_days": 6},
             dtype=float,
```

```diff
diff --git a/tests/test_snapshot_window.py b/tests/test_snapshot_window.py
index 9956531..1c3ee7f 100644
--- a/tests/test_snapshot_window.py
+++ b/tests/test_snapshot_window.py
@@ -115,7 +115,7 @@ def test_predict_game_from_models_reports_model_version(monkeypatch):
 
     monkeypatch.setattr(
         routes.feature_build, "build_features_for_game",
-        lambda home, away, games_df: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
+        lambda home, away, games_df, gameday=None: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
     )
     models = {
         "feature_cols": ["rating_diff", "home_rest_days", "away_rest_days"],
```

```diff
diff --git a/tests/test_fitted_vs_served_columns.py b/tests/test_fitted_vs_served_columns.py
index aa8b5f8..304ceb3 100644
--- a/tests/test_fitted_vs_served_columns.py
+++ b/tests/test_fitted_vs_served_columns.py
@@ -207,7 +207,9 @@ def _blank_fitted_record(artefact, *, drop: bool):
         blanked.get_booster().feature_names = [] if drop else None
         return blanked
     blanked = artefact
-    blanked.feature_names_in_ = np.array([], dtype=object) if drop else None
+    # A scaled Ridge is a Pipeline whose `feature_names_in_` is read from its first step.
+    holder = blanked.steps[0][1] if hasattr(blanked, "steps") else blanked
+    holder.feature_names_in_ = np.array([], dtype=object) if drop else None
     return blanked
```

- [ ] **Step 4: Run the full suite.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider` Expected: all pass.

- [ ] **Step 5: Commit.**

```bash
git add src/nfl_predictor/features/build.py src/nfl_predictor/api/routes.py src/nfl_predictor/api/facts.py tests/test_serving_training_parity.py tests/test_api_routes.py tests/test_facts.py tests/test_snapshot_window.py tests/test_fitted_vs_served_columns.py
git commit -m "fix: serve through the training feature path; rest measured to the game date"
```

## Task 3 (CFB, verified): the same fixes, plus the conference_game bug

**Why:** CFB had the same in-sample sigma and unscaled ridge, and serving hard-coded `conference_game = 0`, so every live pick was scored as a non-conference game.

**Files:**
- Modify: `src/cfb_predictor/models/game_outcome.py`, `evaluate/walk_forward.py`, `models/manifest.py`, `features/build.py`, `api/routes.py`, `api/facts.py`, and the three test doubles `tests/test_api_routes.py`, `tests/test_facts.py`, `tests/test_snapshot_window.py`
- Test: `tests/test_oof_sigma.py`, `tests/test_serving_training_parity.py`

- [ ] **Step 1: Write the failing tests.**

```python
"""Sigma comes from error the model has not been fitted on, and the ridge is invariant to feature units."""
import numpy as np
import pandas as pd
import pytest

from cfb_predictor.evaluate import walk_forward
from cfb_predictor.models import game_outcome, manifest

NOISE = 10.0
COLS = [f"f{i}" for i in range(6)]


def _folds(n_seasons=7, games=80, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for s in range(n_seasons):
        X = pd.DataFrame(rng.normal(size=(games, len(COLS))), columns=COLS)
        X["season"] = 2018 + s
        X["margin"] = 3 * X["f0"] - 2 * X["f1"] + rng.normal(0, NOISE, games)
        X["total_points"] = 45 + 4 * X["f2"] + rng.normal(0, NOISE, games)
        frames.append(X)
    df = pd.concat(frames, ignore_index=True)
    return [
        {"val_season": 2018 + i, "train_df": df[df["season"] < 2018 + i], "val_df": df[df["season"] == 2018 + i], "feature_cols": COLS}
        for i in range(3, n_seasons)
    ], df


def test_in_sample_sigma_understates_and_out_of_fold_sigma_does_not():
    folds, df = _folds()
    train = df[df["season"] < 2024]
    in_sample = game_outcome.residual_sigma(game_outcome.fit_xgb_margin(train[COLS], train["margin"]), train[COLS], train["margin"])
    oof = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "margin"))
    assert in_sample < 0.8 * NOISE, "an overfit model's training error is optimistic: this is the bug"
    assert oof > 1.15 * in_sample
    assert oof == pytest.approx(NOISE, rel=0.25)


def test_the_manifest_sigmas_are_out_of_fold_for_the_margin_and_the_total():
    folds, df = _folds()
    sigma, total_sigma = manifest.fit_sigmas(folds, "ridge")
    assert sigma == pytest.approx(game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "ridge", "margin")))
    assert total_sigma == pytest.approx(game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "total_points")))
    train = df[df["season"] < 2024]
    in_sample_total = game_outcome.residual_sigma(game_outcome.fit_xgb_margin(train[COLS], train["total_points"]), train[COLS], train["total_points"])
    assert total_sigma > in_sample_total


def test_a_folds_sigma_is_the_error_on_the_last_training_season_of_a_model_that_never_saw_it():
    folds, _ = _folds()
    train = folds[-1]["train_df"]
    last = sorted(train["season"].unique())[-1]
    earlier, held_out = train[train["season"] != last], train[train["season"] == last]
    manual = game_outcome.sigma_from_residuals(
        held_out["margin"].to_numpy(float) - game_outcome.fit_xgb_margin(earlier[COLS], earlier["margin"]).predict(held_out[COLS].fillna(0))
    )
    assert walk_forward._honest_sigma("xgb", train, COLS) == pytest.approx(manual)


def test_a_single_training_season_falls_back_to_the_in_sample_spread_and_says_so():
    folds, df = _folds()
    one_season = df[df["season"] == 2018]
    assert walk_forward._honest_sigma("ridge", one_season, COLS) > 0


def test_oof_residuals_refuse_an_unknown_candidate_and_the_elo_total():
    folds, _ = _folds()
    with pytest.raises(ValueError):
        walk_forward.oof_residuals(folds, "nope")
    with pytest.raises(ValueError):
        walk_forward._fit_predict("elo", folds[0]["train_df"], folds[0]["val_df"], COLS, "total_points")


def test_ridge_predictions_do_not_depend_on_the_units_of_a_feature():
    _, df = _folds()
    train, val = df[df["season"] < 2024], df[df["season"] == 2024]
    a = game_outcome.fit_margin_regression(train[COLS], train["margin"]).predict(val[COLS])
    scaled_train, scaled_val = train.copy(), val.copy()
    scaled_train["f0"] *= 1000.0
    scaled_val["f0"] *= 1000.0
    b = game_outcome.fit_margin_regression(scaled_train[COLS], scaled_train["margin"]).predict(scaled_val[COLS])
    np.testing.assert_allclose(a, b, atol=1e-6)
```

```python
"""A game's served feature row equals the row training builds for the same game, including its conference flag."""
import numpy as np
import pandas as pd

from cfb_predictor.features import build

CONF = {"T0": "A", "T1": "A", "T2": "A", "T3": "A", "T4": "B", "T5": "B", "T6": "B", "T7": "B"}


def _season_games(seed=3, seasons=(2023, 2024, 2025), weeks=12):
    rng = np.random.default_rng(seed)
    teams = list(CONF)
    rows = []
    for season in seasons:
        for week in range(1, weeks + 1):
            order = list(rng.permutation(teams))
            for i in range(0, 8, 2):
                home, away = order[i], order[i + 1]
                rows.append({
                    "game_id": f"{season}_{week:02d}_{home}_{away}", "season": season, "week": week,
                    "gameday": pd.Timestamp(f"{season}-08-30") + pd.Timedelta(days=7 * (week - 1)),
                    "home_team": home, "away_team": away,
                    "home_score": int(rng.integers(3, 52)), "away_score": int(rng.integers(3, 52)),
                    "home_conference": CONF[home], "away_conference": CONF[away],
                    "conference_game": CONF[home] == CONF[away],
                    "home_division": "fbs", "away_division": "fbs",
                })
    return pd.DataFrame(rows)


def test_the_served_row_equals_the_row_training_builds_for_the_same_game():
    games = _season_games()
    trained, cols = build.build_training_frame(games)
    sample = trained[trained["season"] == 2025].sample(15, random_state=1)
    for _, g in sample.iterrows():
        history = games[pd.to_datetime(games["gameday"]) < pd.Timestamp(g["gameday"])]
        served = build.build_features_for_game(g["home_team"], g["away_team"], history, gameday=g["gameday"], conference_game=g["conference_game"])
        np.testing.assert_allclose(served[cols].to_numpy(float), g[cols].to_numpy(float), equal_nan=True, err_msg=g["game_id"])


def test_conference_game_is_served_as_the_real_value_not_a_constant_zero():
    games = _season_games()
    same = build.build_features_for_game("T0", "T1", games, gameday="2026-09-05")
    cross = build.build_features_for_game("T0", "T5", games, gameday="2026-09-05")
    assert same["conference_game"] == 1 and cross["conference_game"] == 0


def test_an_explicit_schedule_value_overrides_the_derived_one():
    games = _season_games()
    assert build.build_features_for_game("T0", "T5", games, gameday="2026-09-05", conference_game=True)["conference_game"] == 1


def test_rest_days_are_measured_to_the_games_own_date_not_to_today():
    games = _season_games()
    last = pd.to_datetime(games["gameday"]).max()
    when = last + pd.Timedelta(days=9)
    team = games.sort_values("gameday").iloc[-1]["home_team"]
    other = "T7" if team != "T7" else "T6"
    served = build.build_features_for_game(team, other, games, gameday=when)
    last_played = pd.to_datetime(games[(games["home_team"] == team) | (games["away_team"] == team)]["gameday"]).max()
    assert served["home_rest_days"] == (when - last_played).days


def test_the_row_has_the_feature_columns_in_order():
    assert list(build.build_features_for_game("T0", "T1", _season_games(), gameday="2026-09-05").index) == build.FEATURE_COLUMNS
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_oof_sigma.py tests/test_serving_training_parity.py` Expected: FAIL.

- [ ] **Step 3: Apply the changes.**

```diff
diff --git a/src/cfb_predictor/models/game_outcome.py b/src/cfb_predictor/models/game_outcome.py
index 75b457b..c1a3773 100644
--- a/src/cfb_predictor/models/game_outcome.py
+++ b/src/cfb_predictor/models/game_outcome.py
@@ -18,6 +18,8 @@ import numpy as np
 import pandas as pd
 from scipy.stats import norm
 from sklearn.linear_model import Ridge
+from sklearn.pipeline import Pipeline, make_pipeline
+from sklearn.preprocessing import StandardScaler
 from xgboost import XGBRegressor
 
 ELO_POINTS_PER_RATING_POINT = 1.0 / 25.0
@@ -31,8 +33,11 @@ def predict_margin_elo(candidate: dict, rating_diff: float, home_rest_days: floa
     return rating_diff * candidate["points_per_rating_point"] + 0.05 * (home_rest_days - away_rest_days)
 
 
-def fit_margin_regression(X_train: pd.DataFrame, y_margin: pd.Series) -> Ridge:
-    model = Ridge(alpha=1.0)
+def fit_margin_regression(X_train: pd.DataFrame, y_margin: pd.Series) -> Pipeline:
+    """Ridge on STANDARDISED features. The columns arrive in very different units (an Elo near 1500, points near 20,
+    rest days near 7); an L2 penalty on raw columns shrinks the small-unit features hardest, so which feature set
+    "wins" would depend on its units. Standardising inside the model makes predictions invariant to rescaling."""
+    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
     model.fit(X_train.fillna(0), y_margin)
     return model
 
@@ -54,6 +59,19 @@ def residual_sigma(model, X_val: pd.DataFrame, y_val: pd.Series) -> float:
     return float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals) or 1.0)
 
 
+def sigma_from_residuals(residuals) -> float:
+    """Spread of OUT-OF-SAMPLE residuals: the figure every cover/over/win probability divides by.
+
+    A model's error on its own training rows is optimistic (XGBoost most of all), so a sigma fitted there makes
+    every published probability overconfident. This takes residuals that were never fitted on.
+    """
+    r = np.asarray(residuals, dtype=float)
+    r = r[np.isfinite(r)]
+    if len(r) == 0:
+        return 1.0
+    return float(np.std(r, ddof=1)) if len(r) > 1 else float(np.std(r) or 1.0)
+
+
 def margin_to_probabilities(
     predicted_margin: float,
     sigma: float,
```

```diff
diff --git a/src/cfb_predictor/evaluate/walk_forward.py b/src/cfb_predictor/evaluate/walk_forward.py
index 8eb8634..b5db1c3 100644
--- a/src/cfb_predictor/evaluate/walk_forward.py
+++ b/src/cfb_predictor/evaluate/walk_forward.py
@@ -58,27 +58,44 @@ class _EloModelAdapter:
         return _predict_margin_elo_batch(self.candidate, X)
 
 
-def _predict_margins(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str]):
-    X_train, y_train = train_df[feature_cols], train_df["margin"]
-    X_val = val_df[feature_cols]
-
+def _fit_predict(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str], target: str = "margin") -> np.ndarray:
+    """Fit `candidate` on `train_df` and predict `target` for `val_df`. Nothing from `val_df` reaches the fit."""
     if candidate == "elo":
-        model = game_outcome.fit_elo_candidate(train_df)
-        preds = _predict_margin_elo_batch(model, val_df)
-        sigma = game_outcome.residual_sigma(_EloModelAdapter(model), X_train, y_train)
-        return preds, sigma
-
-    if candidate == "ridge":
-        fit_fn = game_outcome.fit_margin_regression
-    elif candidate == "xgb":
-        fit_fn = game_outcome.fit_xgb_margin
-    else:
+        if target != "margin":
+            raise ValueError("the elo candidate predicts the margin only")
+        return _predict_margin_elo_batch(game_outcome.fit_elo_candidate(train_df), val_df)
+    fit_fn = {"ridge": game_outcome.fit_margin_regression, "xgb": game_outcome.fit_xgb_margin}.get(candidate)
+    if fit_fn is None:
         raise ValueError(f"Unknown candidate: {candidate!r}")
+    return fit_fn(train_df[feature_cols], train_df[target]).predict(val_df[feature_cols].fillna(0))
+
+
+def _honest_sigma(candidate: str, train_df: pd.DataFrame, feature_cols: list[str], target: str = "margin") -> float:
+    """Sigma for a fold, from error the model has NOT been fitted on: the last TRAINING season is held out of an
+    inner fit on the seasons before it. A fold with a single training season has nothing to hold out and falls
+    back to the in-sample spread (optimistic; only the smallest folds ever take this branch)."""
+    seasons = sorted(train_df["season"].unique())
+    if len(seasons) < 2:
+        preds = _fit_predict(candidate, train_df, train_df, feature_cols, target)
+        return game_outcome.sigma_from_residuals(train_df[target].to_numpy(float) - preds)
+    inner_train = train_df[train_df["season"] != seasons[-1]]
+    inner_val = train_df[train_df["season"] == seasons[-1]]
+    preds = _fit_predict(candidate, inner_train, inner_val, feature_cols, target)
+    return game_outcome.sigma_from_residuals(inner_val[target].to_numpy(float) - preds)
+
+
+def oof_residuals(folds: list[dict], candidate: str, target: str = "margin") -> np.ndarray:
+    """Every validation season's residuals, each predicted by a model trained only on EARLIER seasons."""
+    pieces = []
+    for fold in folds:
+        preds = _fit_predict(candidate, fold["train_df"], fold["val_df"], fold["feature_cols"], target)
+        pieces.append(fold["val_df"][target].to_numpy(float) - preds)
+    return np.concatenate(pieces) if pieces else np.array([])
 
-    model = fit_fn(X_train, y_train)
-    preds = model.predict(X_val.fillna(0))
-    sigma = game_outcome.residual_sigma(model, X_train, y_train)
-    return preds, sigma
+
+def _predict_margins(candidate: str, train_df: pd.DataFrame, val_df: pd.DataFrame, feature_cols: list[str]):
+    preds = _fit_predict(candidate, train_df, val_df, feature_cols, "margin")
+    return preds, _honest_sigma(candidate, train_df, feature_cols, "margin")
 
 
 def pooled_predictions(folds: list[dict], candidate: str) -> tuple[np.ndarray, np.ndarray]:
```

```diff
diff --git a/src/cfb_predictor/models/manifest.py b/src/cfb_predictor/models/manifest.py
index e6a233d..9459392 100644
--- a/src/cfb_predictor/models/manifest.py
+++ b/src/cfb_predictor/models/manifest.py
@@ -123,6 +123,14 @@ def _fbs_teams_by_season(seasons: list[int]) -> dict[int, set[str]]:
     return {season: set(games_data.fetch_fbs_teams(season)["team"]) for season in seasons}
 
 
+def fit_sigmas(folds: list[dict], chosen: str) -> tuple[float, float]:
+    """(margin sigma, total sigma) from pooled out-of-fold residuals: the chosen game model for the margin and the
+    XGBoost total model for the total, each predicted on seasons it was never trained on."""
+    sigma = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, chosen, "margin"))
+    total_sigma = game_outcome.sigma_from_residuals(walk_forward.oof_residuals(folds, "xgb", "total_points"))
+    return sigma, total_sigma
+
+
 def train_all(seasons: list[int] | None = None) -> dict:
     """Fit all models, persist their artifacts, and return their manifest."""
     MODELS_DIR.mkdir(exist_ok=True, parents=True)
@@ -152,20 +160,10 @@ def train_all(seasons: list[int] | None = None) -> dict:
     else:
         game_model = game_outcome.fit_xgb_margin(X_train, y_margin)
 
-    if chosen == "elo":
-        margin_preds = train_df.apply(
-            lambda r: game_outcome.predict_margin_elo(
-                game_model, r["rating_diff"], r["home_rest_days"], r["away_rest_days"]
-            ),
-            axis=1,
-        )
-        sigma_model = type("_", (), {"predict": lambda self, X: margin_preds.to_numpy()})()
-        sigma = game_outcome.residual_sigma(sigma_model, X_train, y_margin)
-    else:
-        sigma = game_outcome.residual_sigma(game_model, X_train, y_margin)
-
+    # Sigma from OUT-OF-SAMPLE residuals (the pooled walk-forward folds), never from the training rows the model
+    # was fitted on: an in-sample sigma is optimistic and made every published probability overconfident.
+    sigma, total_sigma = fit_sigmas(folds, chosen)
     total_model = game_outcome.fit_xgb_margin(X_train, y_total)
-    total_sigma = game_outcome.residual_sigma(total_model, X_train, y_total)
 
     _save_pickle(game_model, _artifact_path(GAME_MODEL_FILENAME))
     _save_pickle(total_model, _artifact_path(TOTAL_MODEL_FILENAME))
```

```diff
diff --git a/src/cfb_predictor/features/build.py b/src/cfb_predictor/features/build.py
index ad10d94..0b642bf 100644
--- a/src/cfb_predictor/features/build.py
+++ b/src/cfb_predictor/features/build.py
@@ -17,6 +17,7 @@ spent beating an FCS opponent.
 
 from __future__ import annotations
 
+import numpy as np
 import pandas as pd
 
 from . import power_ratings, rest_days, rolling_form
@@ -80,69 +81,55 @@ def build_training_frame(
     return played, FEATURE_COLUMNS
 
 
-def build_features_for_game(home_team: str, away_team: str, games_df: pd.DataFrame) -> pd.Series:
-    """One live feature row for an upcoming home_team vs away_team game,
-    computed from every played game in games_df (ratings/rolling form as of
-    right now). conference_game defaults to 0 here -- api/routes.py knows
-    the real value from the live schedule row for a specific upcoming game
-    but this function only has the two team names, the same limitation
-    NFL's build_features_for_game already had for div_game (not fixed here,
-    to stay a near-verbatim port rather than a scope expansion)."""
-    ratings = power_ratings.final_ratings(games_df)
-    played = games_df[games_df["home_score"].notna() & games_df["away_score"].notna()]
-
-    def _recent_form(team: str) -> tuple[float, float]:
-        appearances = pd.concat(
-            [
-                played[played["home_team"] == team][["gameday", "home_score", "away_score"]].rename(
-                    columns={"home_score": "scored", "away_score": "allowed"}
-                ),
-                played[played["away_team"] == team][["gameday", "away_score", "home_score"]].rename(
-                    columns={"away_score": "scored", "home_score": "allowed"}
-                ),
-            ]
-        ).sort_values("gameday")
-        recent = appearances.tail(5)
-        if recent.empty:
-            return float("nan"), float("nan")
-        return float(recent["scored"].mean()), float(recent["allowed"].mean())
-
-    def _rest_days(team: str) -> float | None:
-        appearances = pd.concat(
-            [
-                played[played["home_team"] == team][["gameday"]],
-                played[played["away_team"] == team][["gameday"]],
-            ]
-        ).sort_values("gameday")
-        if appearances.empty:
-            return None
-        last_game = pd.to_datetime(appearances.iloc[-1]["gameday"])
-        # Real CFBD gamedays parse as tz-aware (UTC) timestamps; test
-        # fixtures use tz-naive ones. Strip tz so both compare cleanly
-        # against the tz-naive "now" below -- confirmed against real data
-        # in Task 17 (TypeError: Cannot subtract tz-naive and tz-aware).
-        if last_game.tzinfo is not None:
-            last_game = last_game.tz_localize(None)
-        return float((pd.Timestamp.now().normalize() - last_game).days)
-
-    home_scored, home_allowed = _recent_form(home_team)
-    away_scored, away_allowed = _recent_form(away_team)
-    home_rating = ratings.get(home_team, power_ratings.DEFAULT_START_RATING)
-    away_rating = ratings.get(away_team, power_ratings.DEFAULT_START_RATING)
-    home_rest = _rest_days(home_team)
-    away_rest = _rest_days(away_team)
-
-    return pd.Series(
-        {
-            "home_pregame_rating": home_rating,
-            "away_pregame_rating": away_rating,
-            "rating_diff": home_rating - away_rating,
-            "home_points_scored_roll": home_scored,
-            "home_points_allowed_roll": home_allowed,
-            "away_points_scored_roll": away_scored,
-            "away_points_allowed_roll": away_allowed,
-            "home_rest_days": home_rest if home_rest is not None else 7.0,
-            "away_rest_days": away_rest if away_rest is not None else 7.0,
-            "conference_game": 0,
-        }
-    )
+def build_features_for_game(
+    home_team: str, away_team: str, games_df: pd.DataFrame,
+    gameday: str | pd.Timestamp | None = None, conference_game: bool | int | None = None,
+) -> pd.Series:
+    """One feature row for an upcoming home_team vs away_team game, built by the SAME code that builds training rows.
+
+    The upcoming game is appended to the PLAYED games (no result, its own date) and run through `_assemble`, so
+    ratings, rolling form and rest are computed exactly as for a training row. This used to be a second, hand-written
+    implementation with two defects: rest was measured from the last game to TODAY rather than to the game, and
+    `conference_game` was hard-coded to 0 although training fits it from the schedule (a dead coefficient at inference).
+
+    `gameday` is the game's date (None = today). `conference_game` is the schedule's value for this game; when it is
+    not supplied it is derived from the two teams' conferences in `games_df`, and falls back to 0 only when neither
+    is known.
+    """
+    played = games_df[games_df["home_score"].notna() & games_df["away_score"].notna()].copy()
+    when = pd.Timestamp(gameday) if gameday is not None else pd.Timestamp.now().normalize()
+    if when.tzinfo is not None:
+        when = when.tz_localize(None)
+    if conference_game is None:
+        conference_game = _same_conference(home_team, away_team, games_df)
+    upcoming = {c: np.nan for c in played.columns}
+    upcoming.update({
+        "game_id": "__upcoming__", "gameday": when, "home_team": home_team, "away_team": away_team,
+        "home_score": np.nan, "away_score": np.nan, "conference_game": bool(conference_game),
+    })
+    if "season" in played.columns and played["season"].notna().any():
+        upcoming["season"] = played["season"].max()
+    frame = pd.concat([played, pd.DataFrame([upcoming])], ignore_index=True)
+    frame["gameday"] = pd.to_datetime(frame["gameday"], utc=True).dt.tz_localize(None)
+    row = _assemble(frame)
+    served = row[row["game_id"] == "__upcoming__"].iloc[0]
+    # What `_assemble` produced, in the declared order; `manifest.load_models` refuses any model whose fitted
+    # columns differ from this.
+    return served[[c for c in FEATURE_COLUMNS if c in served.index]]
+
+
+def _same_conference(home_team: str, away_team: str, games_df: pd.DataFrame) -> bool:
+    """Whether the two teams share a conference, read from the most recent row that names each team's conference."""
+    if not {"home_conference", "away_conference"} <= set(games_df.columns):
+        return False
+
+    def conference(team: str):
+        rows = games_df[(games_df["home_team"] == team) | (games_df["away_team"] == team)]
+        for _, r in rows.iloc[::-1].iterrows():
+            c = r["home_conference"] if r["home_team"] == team else r["away_conference"]
+            if isinstance(c, str) and c:
+                return c
+        return None
+
+    h, a = conference(home_team), conference(away_team)
+    return h is not None and h == a
```

```diff
diff --git a/src/cfb_predictor/api/routes.py b/src/cfb_predictor/api/routes.py
index b2630bc..2e9a030 100644
--- a/src/cfb_predictor/api/routes.py
+++ b/src/cfb_predictor/api/routes.py
@@ -355,8 +355,9 @@ def _lines_for_game(odds_df: pd.DataFrame, home_team: str, away_team: str) -> tu
 def _predict_game_from_models(
     models: dict, home: str, away: str, games_df: pd.DataFrame,
     spread_line: float | None = None, total_line: float | None = None,
+    gameday=None, conference_game=None,
 ) -> dict:
-    feature_row = feature_build.build_features_for_game(home, away, games_df)
+    feature_row = feature_build.build_features_for_game(home, away, games_df, gameday=gameday, conference_game=conference_game)
     feature_cols = models["feature_cols"]
     X = feature_row.reindex(feature_cols).fillna(0)
 
@@ -505,6 +506,7 @@ def _get_game_prediction_live(season: int, week: int, game_id: str):
     prediction = _predict_game_from_models(
         models, game["home_team"], game["away_team"], history,
         spread_line=spread_line, total_line=total_line,
+        gameday=game.get("gameday"), conference_game=game.get("conference_game"),
     )
     return prediction
 
@@ -551,6 +553,7 @@ def _get_predictions_batch_live(season: int, week: int) -> dict:
             predictions[game["game_id"]] = _predict_game_from_models(
                 models, game["home_team"], game["away_team"], game_history,
                 spread_line=spread_line, total_line=total_line,
+                gameday=game.get("gameday"), conference_game=game.get("conference_game"),
             )
         except Exception:
             # One bad game must not fail the whole batch -- mirrors
@@ -1009,6 +1012,7 @@ def background_tracking_tick(season: int, week: int) -> None:
                 pred = _predict_game_from_models(
                     models, game["home_team"], game["away_team"], history,
                     spread_line=spread_line, total_line=total_line,
+                    gameday=game.get("gameday"), conference_game=game.get("conference_game"),
                 )
                 predictions.append(
                     {
@@ -1094,6 +1098,7 @@ def background_tracking_tick(season: int, week: int) -> None:
                         pred = _predict_game_from_models(
                             models, game["home_team"], game["away_team"], history_excl,
                             spread_line=spread_line, total_line=total_line,
+                            gameday=game.get("gameday"), conference_game=game.get("conference_game"),
                         )
                         backfill_games.append({
                             "game_id": game["game_id"], "home_team": game["home_team"], "away_team": game["away_team"],
```

```diff
diff --git a/src/cfb_predictor/api/facts.py b/src/cfb_predictor/api/facts.py
index 2013374..a9c18de 100644
--- a/src/cfb_predictor/api/facts.py
+++ b/src/cfb_predictor/api/facts.py
@@ -321,7 +321,9 @@ def _drivers(game: dict, season: int, home_team: str, away_team: str, live_ok: b
         try:
             history = routes._load_game_history(season)
             history = history[history["game_id"].astype(str) != str(game["game_id"])]
-            row = routes.feature_build.build_features_for_game(home_team, away_team, history)
+            row = routes.feature_build.build_features_for_game(
+                home_team, away_team, history, gameday=game.get("gameday"), conference_game=game.get("conference_game"),
+            )
             rating_diff = _num(row.get("rating_diff"))
         except Exception:
             logger.info("driver features unavailable for game_id=%s", game.get("game_id"))
```

```diff
diff --git a/tests/test_api_routes.py b/tests/test_api_routes.py
index ee5fb1b..11e45ae 100644
--- a/tests/test_api_routes.py
+++ b/tests/test_api_routes.py
@@ -49,7 +49,7 @@ def client(monkeypatch):
     )
     monkeypatch.setattr(
         routes, "_predict_game_from_models",
-        lambda models, home, away, games_df, spread_line=None, total_line=None: {
+        lambda models, home, away, games_df, spread_line=None, total_line=None, gameday=None, conference_game=None: {
             "home_win_prob": 0.4, "away_win_prob": 0.6, "home_cover_prob": 0.45, "away_cover_prob": 0.55,
             "over_prob": 0.52, "under_prob": 0.48,
         },
@@ -106,7 +106,7 @@ def test_predict_game_from_models_includes_sigma_and_total_sigma(monkeypatch):
 
     monkeypatch.setattr(
         routes.feature_build, "build_features_for_game",
-        lambda home, away, games_df: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
+        lambda home, away, games_df, gameday=None, conference_game=None: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
     )
     models = {
         "feature_cols": ["rating_diff", "home_rest_days", "away_rest_days"],
@@ -489,7 +489,7 @@ def test_get_predictions_batch_one_bad_game_does_not_fail_the_rest(client, monke
         ]),
     )
 
-    def flaky_predict(models, home, away, games_df, spread_line=None, total_line=None):
+    def flaky_predict(models, home, away, games_df, spread_line=None, total_line=None, gameday=None, conference_game=None):
         if home == "Broken":
             raise ValueError("feature build blew up for this one game")
         return {"home_win_prob": 0.4, "away_win_prob": 0.6}
```

```diff
diff --git a/tests/test_facts.py b/tests/test_facts.py
index 63d901a..907dbf2 100644
--- a/tests/test_facts.py
+++ b/tests/test_facts.py
@@ -476,7 +476,7 @@ def _stub_live_rating_gap(monkeypatch, rating_diff=7.0):
     )
     monkeypatch.setattr(
         facts_mod.routes.feature_build, "build_features_for_game",
-        lambda home, away, history: pd.Series({"rating_diff": rating_diff}),
+        lambda home, away, history, gameday=None, conference_game=None: pd.Series({"rating_diff": rating_diff}),
     )
```

```diff
diff --git a/tests/test_snapshot_window.py b/tests/test_snapshot_window.py
index b10e1de..f9cf346 100644
--- a/tests/test_snapshot_window.py
+++ b/tests/test_snapshot_window.py
@@ -113,7 +113,7 @@ def test_predict_game_from_models_reports_model_version(monkeypatch):
 
     monkeypatch.setattr(
         routes.feature_build, "build_features_for_game",
-        lambda home, away, games_df: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
+        lambda home, away, games_df, gameday=None, conference_game=None: pd.Series({"rating_diff": 50.0, "home_rest_days": 7.0, "away_rest_days": 7.0}),
     )
     models = {
         "feature_cols": ["rating_diff", "home_rest_days", "away_rest_days"],
```

- [ ] **Step 4: Run the full suite.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider` Expected: 578 passed, 21 skipped.

- [ ] **Step 5: Commit** (add by name; do not commit `uv.lock` if it is untracked).

```bash
git add src/cfb_predictor/models/game_outcome.py src/cfb_predictor/evaluate/walk_forward.py src/cfb_predictor/models/manifest.py src/cfb_predictor/features/build.py src/cfb_predictor/api/routes.py src/cfb_predictor/api/facts.py tests/test_oof_sigma.py tests/test_serving_training_parity.py tests/test_api_routes.py tests/test_facts.py tests/test_snapshot_window.py
git commit -m "fix(cfb): out-of-fold sigma, scaled ridge, one feature path, conference_game at serving"
```

## Task 4 (NFL, verified): play-by-play aggregation and the EPA offence-vs-defence block

**Why:** the model has Elo and scoring form but no per-play efficiency. EPA/play and success rate, split by pass and rush and by offence and defence, are the strongest public predictors of future margin. The matchup edges (home pass offence against away pass defence, and so on) are the "offence versus defence" signal; they also become AI-summary facts (see the AI plan).

**Files:**
- Create: `src/nfl_predictor/data/pbp_agg.py`, `src/nfl_predictor/features/epa.py`, `tests/epa_fixtures.py`
- Test: `tests/test_epa_qb_features.py` (EPA half; the QB half is Task 5)

- [ ] **Step 1: Write the fixtures and tests.**

```python
"""Synthetic NFL games and play-by-play shaped like nflverse's, deterministic and offline."""
import numpy as np
import pandas as pd

from nfl_predictor.data.pbp_agg import PBP_AGG_COLUMNS

TEAMS = [f"T{i}" for i in range(8)]


def make_games(seed=3, seasons=(2023, 2024, 2025), weeks=14) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for season in seasons:
        for week in range(1, weeks + 1):
            order = list(rng.permutation(TEAMS))
            n_games = 3 if week % 4 == 0 else 4
            for i in range(0, 2 * n_games, 2):
                home, away = order[i], order[i + 1]
                rows.append({
                    "game_id": f"{season}_{week:02d}_{home}_{away}", "season": season, "week": week,
                    "gameday": pd.Timestamp(f"{season}-09-07") + pd.Timedelta(days=7 * (week - 1)),
                    "home_team": home, "away_team": away,
                    "home_score": int(rng.integers(6, 42)), "away_score": int(rng.integers(6, 42)), "div_game": 0,
                })
    return pd.DataFrame(rows)


def qb_ids(team: str) -> tuple[str, str]:
    return f"{team}-QB1", f"{team}-QB2"


def make_pbp(games: pd.DataFrame, seed=5, plays_per_side=50) -> pd.DataFrame:
    """Plays for every game. Each team has a latent offence and defence level; its QB1 starts ~85% of games and
    QB2 starts the rest (QB2 also takes ~15% of dropbacks in games QB1 starts)."""
    rng = np.random.default_rng(seed)
    off = {t: rng.normal(0.0, 0.08) for t in TEAMS}
    dfn = {t: rng.normal(0.0, 0.08) for t in TEAMS}
    rows = []
    for _, g in games.iterrows():
        for posteam, defteam in ((g["home_team"], g["away_team"]), (g["away_team"], g["home_team"])):
            qb1, qb2 = qb_ids(posteam)
            starter = qb1 if rng.random() < 0.85 else qb2
            for _ in range(plays_per_side):
                is_pass = rng.random() < 0.58
                epa = off[posteam] - dfn[defteam] + rng.normal(0.0, 1.2) + (0.05 if is_pass else -0.03)
                qb = starter if rng.random() < 0.85 else (qb2 if starter == qb1 else qb1)
                rows.append({
                    "game_id": g["game_id"], "season": g["season"], "week": g["week"], "posteam": posteam, "defteam": defteam,
                    "play_type": "pass" if is_pass else "run", "epa": epa, "success": float(epa > 0),
                    "qb_dropback": 1 if is_pass else 0, "passer_player_id": qb if is_pass else None,
                    "passer_player_name": f"Name {qb}" if is_pass else None,
                })
    return pd.DataFrame(rows, columns=PBP_AGG_COLUMNS)


def perturb_pbp_from(pbp: pd.DataFrame, games: pd.DataFrame, cut_date: str, seed=9) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    late = set(games[pd.to_datetime(games["gameday"]) >= pd.Timestamp(cut_date)]["game_id"])
    out = pbp.copy()
    mask = out["game_id"].isin(late)
    out.loc[mask, "epa"] = out.loc[mask, "epa"] + rng.normal(0, 3.0, mask.sum())
    return out
```

```python
"""EPA and starting-QB features: hand-checked numbers, shrinkage, causality, the matchup edges."""
import numpy as np
import pandas as pd
import pytest

from nfl_predictor.data import pbp_agg
from nfl_predictor.features import epa, qb
from epa_fixtures import make_games, make_pbp, perturb_pbp_from, qb_ids


def _play(game, posteam, defteam, kind, e, success=0.0, dropback=0, passer=None):
    return {"game_id": game, "season": 2025, "week": 1, "posteam": posteam, "defteam": defteam, "play_type": kind, "epa": e,
            "success": success, "qb_dropback": dropback, "passer_player_id": passer, "passer_player_name": passer}


def _mini():
    return pd.DataFrame([
        _play("g1", "A", "B", "pass", 0.4, 1.0, 1, "qa"),
        _play("g1", "A", "B", "run", -0.2, 0.0),
        _play("g1", "B", "A", "pass", 0.1, 1.0, 1, "qb"),
        _play("g1", "A", "B", "punt", 5.0),               # not a scrimmage play: ignored
        _play("g1", "A", "B", "pass", np.nan, 0.0, 1, "qa"),  # no EPA value: ignored
    ])


def test_offence_and_defence_efficiency_with_hand_numbers():
    eff = pbp_agg.team_game_efficiency(_mini()).set_index("team")
    assert eff.loc["A", "epa_off"] == pytest.approx(0.1)
    assert eff.loc["A", "epa_off_pass"] == pytest.approx(0.4) and eff.loc["A", "epa_off_rush"] == pytest.approx(-0.2)
    assert eff.loc["A", "success_off"] == pytest.approx(0.5)
    # what A's defence allowed is what B's offence did against it
    assert eff.loc["A", "epa_def"] == pytest.approx(0.1) and eff.loc["A", "epa_def_pass"] == pytest.approx(0.1)
    assert eff.loc["B", "epa_def"] == pytest.approx(0.1)             # A's offence averaged 0.1 against B


def test_the_starting_qb_is_the_passer_with_the_most_dropbacks():
    pbp = pd.DataFrame([
        _play("g1", "A", "B", "pass", 0.5, 1, 1, "starter"), _play("g1", "A", "B", "pass", 0.1, 0, 1, "starter"),
        _play("g1", "A", "B", "pass", -0.5, 0, 1, "backup"),
    ])
    row = pbp_agg.qb_games(pbp).iloc[0]
    assert row["qb_id"] == "starter" and row["dropbacks"] == 2 and row["epa_sum"] == pytest.approx(0.6)


def test_a_dropback_tie_goes_to_the_lowest_id_so_the_choice_is_deterministic():
    pbp = pd.DataFrame([_play("g1", "A", "B", "pass", 0.2, 1, 1, "z"), _play("g1", "A", "B", "pass", 0.2, 1, 1, "a")])
    assert pbp_agg.qb_games(pbp).iloc[0]["qb_id"] == "a"


def test_an_empty_play_by_play_gives_empty_tables_not_an_error():
    assert pbp_agg.team_game_efficiency(pd.DataFrame()).empty and pbp_agg.qb_games(pd.DataFrame()).empty


def test_a_teams_rolling_epa_is_shrunk_toward_zero_by_how_little_we_have_seen():
    games = make_games(seasons=(2025,), weeks=6)
    eff = pbp_agg.team_game_efficiency(make_pbp(games))
    out = epa.add_epa_features(games, eff)
    team = games.sort_values("gameday").iloc[0]["home_team"]
    own = eff[eff["team"] == team].merge(games[["game_id", "gameday"]], on="game_id").sort_values("gameday")
    second_game = own.iloc[1]["game_id"]
    row = out[out["game_id"] == second_game].iloc[0]
    side = "home" if row["home_team"] == team else "away"
    assert row[f"{side}_epa_off_ewm"] == pytest.approx(own.iloc[0]["epa_off"] * (1 / (1 + epa.SHRINK_K)))


def test_epa_features_never_read_the_game_itself_or_anything_later():
    games = make_games()
    pbp = make_pbp(games)
    cut = sorted(games["gameday"].unique())[30]
    a = epa.add_epa_features(games, pbp_agg.team_game_efficiency(pbp))
    b = epa.add_epa_features(games, pbp_agg.team_game_efficiency(perturb_pbp_from(pbp, games, cut)))
    earlier = pd.to_datetime(games["gameday"]) <= pd.Timestamp(cut)
    cols = epa.epa_columns()
    pd.testing.assert_frame_equal(a[earlier][cols].reset_index(drop=True), b[earlier][cols].reset_index(drop=True))


def test_the_matchup_edges_are_offence_minus_the_opposing_defence():
    games = make_games()
    out = epa.add_epa_features(games, pbp_agg.team_game_efficiency(make_pbp(games))).dropna(subset=epa.epa_columns())
    np.testing.assert_allclose(out["home_pass_edge"], out["home_epa_off_pass_ewm"] - out["away_epa_def_pass_ewm"])
    np.testing.assert_allclose(out["away_rush_edge"], out["away_epa_off_rush_ewm"] - out["home_epa_def_rush_ewm"])
    np.testing.assert_allclose(
        out["epa_net_diff"], (out["home_epa_off_ewm"] - out["home_epa_def_ewm"]) - (out["away_epa_off_ewm"] - out["away_epa_def_ewm"]),
    )


def test_no_epa_column_is_constant():
    games = make_games()
    out = epa.add_epa_features(games, pbp_agg.team_game_efficiency(make_pbp(games))).dropna(subset=epa.epa_columns())
    assert [c for c in epa.epa_columns() if out[c].nunique() <= 1] == []


# ---- the QB ---------------------------------------------------------------------------------------------------

def _qb_table():
    return pd.DataFrame([
        {"game_id": "g1", "team": "A", "qb_id": "q1", "qb_name": "Q1", "dropbacks": 100, "epa_sum": 20.0},
        {"game_id": "g2", "team": "A", "qb_id": "q1", "qb_name": "Q1", "dropbacks": 50, "epa_sum": -5.0},
        {"game_id": "g3", "team": "A", "qb_id": "q2", "qb_name": "Q2", "dropbacks": 40, "epa_sum": 8.0},
        {"game_id": "g1", "team": "B", "qb_id": "b1", "qb_name": "B1", "dropbacks": 30, "epa_sum": 3.0},
        {"game_id": "g2", "team": "B", "qb_id": "b1", "qb_name": "B1", "dropbacks": 30, "epa_sum": 3.0},
        {"game_id": "g3", "team": "B", "qb_id": "b1", "qb_name": "B1", "dropbacks": 30, "epa_sum": 3.0},
    ])


def _qb_games_frame():
    return pd.DataFrame([
        {"game_id": f"g{i}", "gameday": f"2025-09-{7 * i:02d}", "home_team": "A", "away_team": "B"} for i in (1, 2, 3)
    ] + [{"game_id": "g4", "gameday": "2025-10-05", "home_team": "A", "away_team": "B"}])


def test_a_qbs_rating_is_his_prior_epa_per_dropback_shrunk_toward_the_prior():
    out = qb.add_qb_features(_qb_games_frame(), _qb_table()).set_index("game_id")
    # g2: q1 has 100 prior dropbacks and 20 EPA: 20 / (100 + 200)
    assert out.loc["g2", "home_qb_epa_pd"] == pytest.approx(20.0 / 300.0)
    # g1: nothing prior: exactly the prior
    assert out.loc["g1", "home_qb_epa_pd"] == pytest.approx(qb.PRIOR_EPA_PER_DROPBACK)


def test_experience_new_and_changed_flags():
    out = qb.add_qb_features(_qb_games_frame(), _qb_table()).set_index("game_id")
    assert out.loc["g2", "home_qb_games"] == 1 and out.loc["g2", "home_qb_new"] == 1.0 and out.loc["g2", "home_qb_changed"] == 0.0
    assert out.loc["g3", "home_qb_changed"] == 1.0           # q2 replaced q1 in A's lineup
    assert out.loc["g3", "home_qb_games"] == 0               # q2 has no earlier games


def test_a_rating_never_includes_the_game_it_is_for():
    t = _qb_table()
    a = qb.add_qb_features(_qb_games_frame(), t).set_index("game_id").loc["g2", "home_qb_epa_pd"]
    t2 = t.copy()
    t2.loc[(t2["game_id"] == "g2") & (t2["team"] == "A"), "epa_sum"] = 999.0
    b = qb.add_qb_features(_qb_games_frame(), t2).set_index("game_id").loc["g2", "home_qb_epa_pd"]
    assert a == b


def test_an_upcoming_game_uses_the_expected_starter_and_unknown_means_the_prior():
    out = qb.add_qb_features(_qb_games_frame(), _qb_table(), upcoming_starters={("g4", "A"): "q1", ("g4", "B"): None}).set_index("game_id")
    assert out.loc["g4", "home_qb_epa_pd"] == pytest.approx(15.0 / (150.0 + 200.0))
    assert out.loc["g4", "home_qb_games"] == 2 and out.loc["g4", "home_qb_changed"] == 1.0   # q2 started A's last game
    assert out.loc["g4", "away_qb_games"] == 0 and out.loc["g4", "away_qb_new"] == 1.0 and out.loc["g4", "away_qb_epa_pd"] == qb.PRIOR_EPA_PER_DROPBACK


def test_expected_starters_skip_reported_out_and_sort_the_depth_slot_numerically():
    chart = pd.DataFrame([
        {"club_code": "A", "position": "QB", "depth_team": "2", "gsis_id": "second"},
        {"club_code": "A", "position": "QB", "depth_team": "1", "gsis_id": "first"},
        {"club_code": "A", "position": "QB", "depth_team": "10", "gsis_id": "tenth"},
        {"club_code": "A", "position": "WR", "depth_team": "1", "gsis_id": "wr"},
        {"club_code": "B", "position": "QB", "depth_team": "1", "gsis_id": "only"},
    ])
    assert qb.expected_starters(chart) == {"A": "first", "B": "only"}
    assert qb.expected_starters(chart, out_ids={"first"}) == {"A": "second", "B": "only"}
    assert qb.expected_starters(chart, out_ids={"first", "second", "tenth"})["A"] is None
    assert qb.expected_starters(pd.DataFrame()) == {}


def test_real_shaped_data_gives_varied_qb_features():
    games = make_games()
    qbg = pbp_agg.qb_games(make_pbp(games))
    out = qb.add_qb_features(games, qbg)
    assert out["home_qb_epa_pd"].nunique() > 20 and out["home_qb_changed"].sum() > 0 and out["home_qb_new"].sum() > 0
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_epa_qb_features.py` Expected: ImportError.

- [ ] **Step 3: Write the modules.**

```python
"""Per-team-game efficiency and per-game starting QB, aggregated from nflverse play-by-play.

Two small tables are all the game model needs from the ~50,000 plays a season: one row per team per game (offence
and defence EPA, split pass/rush, success rate) and one row per team per game naming the starting QB (the passer with
the most dropbacks) with his EPA. Both are cached per season so training reads kilobytes, not play-by-play.
"""
from __future__ import annotations

import pandas as pd

from ..config import CACHE_DIR, CURRENT_SEASON
from .hub_cache import cached_frame

PBP_AGG_COLUMNS = [
    "game_id", "season", "week", "posteam", "defteam", "play_type", "epa", "success",
    "qb_dropback", "passer_player_id", "passer_player_name",
]
PBP_AGG_CACHE_DIR = CACHE_DIR / "pbp_agg"

EFFICIENCY_COLUMNS = [
    "game_id", "team", "epa_off", "epa_off_pass", "epa_off_rush", "success_off",
    "epa_def", "epa_def_pass", "epa_def_rush", "success_def",
]
QB_GAME_COLUMNS = ["game_id", "team", "qb_id", "qb_name", "dropbacks", "epa_sum"]


def _import_pbp(years: list[int], columns: list[str]) -> pd.DataFrame:
    import nfl_data_py as nfl

    return nfl.import_pbp_data(years, columns=columns)


def load_pbp_agg(season: int) -> pd.DataFrame:
    """The play-by-play columns the aggregates need, one season, cached (the current season is refreshed)."""
    return cached_frame(
        PBP_AGG_CACHE_DIR / f"pbp_agg_{season}.parquet",
        lambda: _import_pbp([season], PBP_AGG_COLUMNS), PBP_AGG_COLUMNS, current=season == CURRENT_SEASON,
    )


def _plays(pbp: pd.DataFrame) -> pd.DataFrame:
    """Scrimmage plays with an EPA value. Penalties, kickoffs, punts and two-point tries carry no pass/run type here."""
    if pbp is None or pbp.empty:
        return pd.DataFrame(columns=PBP_AGG_COLUMNS)
    return pbp[pbp["play_type"].isin(["pass", "run"]) & pbp["epa"].notna()]


def team_game_efficiency(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team): what the team's OFFENCE did and what its DEFENCE allowed, per play."""
    plays = _plays(pbp)
    if plays.empty:
        return pd.DataFrame(columns=EFFICIENCY_COLUMNS)

    def side(group_col: str, prefix: str) -> pd.DataFrame:
        g = plays.groupby(["game_id", group_col])
        out = pd.DataFrame({
            f"epa_{prefix}": g["epa"].mean(),
            f"success_{prefix}": g["success"].mean(),
            f"epa_{prefix}_pass": plays[plays["play_type"] == "pass"].groupby(["game_id", group_col])["epa"].mean(),
            f"epa_{prefix}_rush": plays[plays["play_type"] == "run"].groupby(["game_id", group_col])["epa"].mean(),
        })
        out.index = out.index.set_names(["game_id", "team"])
        return out

    merged = side("posteam", "off").join(side("defteam", "def"), how="outer").reset_index()
    return merged[EFFICIENCY_COLUMNS]


def qb_games(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per (game, team): the QB with the most dropbacks that game, how many, and his total EPA on them."""
    plays = _plays(pbp)
    if plays.empty:
        return pd.DataFrame(columns=QB_GAME_COLUMNS)
    db = plays[(plays["qb_dropback"] == 1) & plays["passer_player_id"].notna()]
    if db.empty:
        return pd.DataFrame(columns=QB_GAME_COLUMNS)
    per_qb = (
        db.groupby(["game_id", "posteam", "passer_player_id"])
        .agg(dropbacks=("epa", "size"), epa_sum=("epa", "sum"), qb_name=("passer_player_name", "first"))
        .reset_index()
    )
    per_qb = per_qb.sort_values(["game_id", "posteam", "dropbacks", "passer_player_id"], ascending=[True, True, False, True])
    starter = per_qb.drop_duplicates(["game_id", "posteam"], keep="first")
    return starter.rename(columns={"posteam": "team", "passer_player_id": "qb_id"})[QB_GAME_COLUMNS].reset_index(drop=True)
```

```python
"""Team efficiency (EPA per play) as pre-game features, plus the offence-versus-defence matchup edges.

EPA is roughly zero-sum across the league, so a team's rolling value is shrunk toward ZERO by n/(n+k) (n = prior games
with data): two games of data do not make an offence elite. Every value for game g uses only games before g.
"""
from __future__ import annotations

import pandas as pd

EWM_HALFLIFE = 6.0
SHRINK_K = 4.0
STATS = [
    "epa_off", "epa_def", "epa_off_pass", "epa_off_rush", "epa_def_pass", "epa_def_rush", "success_off", "success_def",
]
EDGE_COLUMNS = ["home_pass_edge", "home_rush_edge", "away_pass_edge", "away_rush_edge", "epa_net_diff"]


def epa_columns() -> list[str]:
    return [f"{side}_{s}_ewm" for s in STATS for side in ("home", "away")] + EDGE_COLUMNS


def _shrunk_ewm(series: pd.Series, halflife: float, k: float) -> pd.Series:
    lagged = series.shift(1)
    n = lagged.notna().cumsum()
    return lagged.ewm(halflife=halflife, min_periods=1).mean() * (n / (n + k))


def add_epa_features(games_df: pd.DataFrame, efficiency: pd.DataFrame, halflife: float = EWM_HALFLIFE, k: float = SHRINK_K) -> pd.DataFrame:
    """Add `{home,away}_<stat>_ewm` for each stat in STATS and the matchup edges. `efficiency` is team_game_efficiency()."""
    rows = []
    for side in ("home", "away"):
        rows.append(games_df[["game_id", "gameday", f"{side}_team"]].rename(columns={f"{side}_team": "team"}))
    long = pd.concat(rows, ignore_index=True).drop_duplicates(["game_id", "team"])
    long["gameday"] = pd.to_datetime(long["gameday"])
    long = long.merge(efficiency, on=["game_id", "team"], how="left").sort_values(["team", "gameday", "game_id"]).reset_index(drop=True)
    for stat in STATS:
        long[f"{stat}_ewm"] = long.groupby("team")[stat].transform(lambda s: _shrunk_ewm(s, halflife, k))
    keyed = long.set_index(["game_id", "team"])[[f"{s}_ewm" for s in STATS]]
    out = games_df.copy()
    for side in ("home", "away"):
        idx = pd.MultiIndex.from_arrays([out["game_id"], out[f"{side}_team"]])
        vals = keyed.reindex(idx)
        for s in STATS:
            out[f"{side}_{s}_ewm"] = vals[f"{s}_ewm"].to_numpy()
    out["home_pass_edge"] = out["home_epa_off_pass_ewm"] - out["away_epa_def_pass_ewm"]
    out["home_rush_edge"] = out["home_epa_off_rush_ewm"] - out["away_epa_def_rush_ewm"]
    out["away_pass_edge"] = out["away_epa_off_pass_ewm"] - out["home_epa_def_pass_ewm"]
    out["away_rush_edge"] = out["away_epa_off_rush_ewm"] - out["home_epa_def_rush_ewm"]
    out["epa_net_diff"] = (out["home_epa_off_ewm"] - out["home_epa_def_ewm"]) - (out["away_epa_off_ewm"] - out["away_epa_def_ewm"])
    return out
```

- [ ] **Step 4: Run.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_epa_qb_features.py` Expected: pass.

- [ ] **Step 5: Commit.**

```bash
git add src/nfl_predictor/data/pbp_agg.py src/nfl_predictor/features/epa.py tests/epa_fixtures.py tests/test_epa_qb_features.py
git commit -m "feat: EPA block with offence-vs-defence matchup edges (inert)"
```

## Task 5 (NFL, verified): the quarterback block

**Why:** the single biggest known swing in NFL spreads is the starting QB. Training uses the quarterback who actually started (most dropbacks); serving uses the depth-chart expected starter, skipping anyone reported Out. A shrunk EPA-per-dropback, games of experience, a "QB changed" flag and a "new QB" flag let the model price a backup starting.

**Files:**
- Create: `src/nfl_predictor/features/qb.py`
- Test: the QB tests already in `tests/test_epa_qb_features.py` (Task 4)

- [ ] **Step 1: Run the QB tests** (already written in Task 4). Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_epa_qb_features.py -k qb` Expected: FAIL (module missing).

- [ ] **Step 2: Write the module.**

```python
"""The starting quarterback as a feature: his career EPA per dropback (shrunk), experience, and whether he changed.

Training uses the QB who actually started (the passer with the most dropbacks). Serving has no result, so it uses the
EXPECTED starter: the depth chart's first QB who is not reported Out. That skew is real and is measured by
`tools/qb_starter_agreement.py`, not assumed away. A QB's own past games are the only data his rating reads.
"""
from __future__ import annotations

import pandas as pd

SHRINK_K = 200.0        # dropbacks of prior worth: a QB with 200 dropbacks is half his own record, half the prior
PRIOR_EPA_PER_DROPBACK = 0.0
NEW_QB_GAMES = 3        # fewer career games than this in the data = a new / unproven starter
QB_COLUMNS = [f"{side}_{c}" for c in ("qb_epa_pd", "qb_games", "qb_changed", "qb_new") for side in ("home", "away")]


def _history(qb_games_df: pd.DataFrame, games_df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.concat([
        games_df[["game_id", "gameday"]],
    ]).drop_duplicates("game_id")
    h = qb_games_df.merge(dates, on="game_id", how="left")
    h["gameday"] = pd.to_datetime(h["gameday"])
    return h.sort_values(["gameday", "game_id"]).reset_index(drop=True)


def add_qb_features(
    games_df: pd.DataFrame, qb_games_df: pd.DataFrame,
    upcoming_starters: dict[tuple[str, str], str | None] | None = None,
    k: float = SHRINK_K, prior: float = PRIOR_EPA_PER_DROPBACK, new_games: int = NEW_QB_GAMES,
) -> pd.DataFrame:
    """Add `{home,away}_qb_epa_pd / qb_games / qb_changed / qb_new` for every game.

    A completed game uses its actual starter. A game with no QB row (upcoming) uses `upcoming_starters[(game_id, team)]`,
    and a game with neither gets the prior, zero games and "new": the honest "we do not know who starts".
    """
    upcoming_starters = upcoming_starters or {}
    hist = _history(qb_games_df, games_df)
    hist["cum_db"] = hist.groupby("qb_id")["dropbacks"].cumsum() - hist["dropbacks"]
    hist["cum_epa"] = hist.groupby("qb_id")["epa_sum"].cumsum() - hist["epa_sum"]
    hist["cum_games"] = hist.groupby("qb_id").cumcount()
    hist["prev_qb"] = hist.groupby("team")["qb_id"].shift(1)
    by_game = hist.set_index(["game_id", "team"])
    # What each QB has accumulated through his LAST game: the starting point for a game that has not been played.
    totals = hist.groupby("qb_id").agg(db=("dropbacks", "sum"), epa=("epa_sum", "sum"), games=("dropbacks", "size"))
    last_qb_of_team = hist.groupby("team")["qb_id"].last()

    out = games_df.copy()
    for side in ("home", "away"):
        epa_pd, n_games, changed, new = [], [], [], []
        for game_id, team in zip(out["game_id"], out[f"{side}_team"]):
            key = (game_id, team)
            if key in by_game.index:
                r = by_game.loc[key]
                epa_pd.append((r["cum_epa"] + k * prior) / (r["cum_db"] + k))
                n_games.append(float(r["cum_games"]))
                changed.append(float(isinstance(r["prev_qb"], str) and r["prev_qb"] != r["qb_id"]))
            else:
                qb = upcoming_starters.get(key)
                if qb is not None and qb in totals.index:
                    t = totals.loc[qb]
                    epa_pd.append((t["epa"] + k * prior) / (t["db"] + k))
                    n_games.append(float(t["games"]))
                    changed.append(float(team in last_qb_of_team.index and last_qb_of_team[team] != qb))
                else:
                    epa_pd.append(prior)
                    n_games.append(0.0)
                    changed.append(0.0)
            new.append(float(n_games[-1] < new_games))
        out[f"{side}_qb_epa_pd"], out[f"{side}_qb_games"] = epa_pd, n_games
        out[f"{side}_qb_changed"], out[f"{side}_qb_new"] = changed, new
    return out


def expected_starters(depth_chart: pd.DataFrame, out_ids: set[str] | None = None) -> dict[str, str | None]:
    """{team: gsis_id} of each team's expected starting QB: the first QB on its depth chart who is not reported Out.

    `depth_chart` is the nflverse chart for the week (columns club_code, position, depth_team (a STRING '1','2',...),
    gsis_id). A team with no usable QB maps to None, never to a guess.
    """
    out_ids = set(out_ids or ())
    if depth_chart is None or depth_chart.empty:
        return {}
    qbs = depth_chart[depth_chart["position"] == "QB"].copy()
    qbs["slot"] = pd.to_numeric(qbs["depth_team"], errors="coerce")
    result: dict[str, str | None] = {}
    for team, grp in qbs.groupby("club_code"):
        ordered = grp.sort_values("slot")
        pick = next((g for g in ordered["gsis_id"] if isinstance(g, str) and g not in out_ids), None)
        result[team] = pick
    return result
```

- [ ] **Step 3: Run.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_epa_qb_features.py` Expected: 14 passed.

- [ ] **Step 4: Commit.**

```bash
git add src/nfl_predictor/features/qb.py
git commit -m "feat: quarterback block (shrunk EPA/dropback, change and new-QB flags; inert)"
```

## Task 6 (NFL, verified): block wiring and serving parity

The `BLOCK_COLUMNS`, `Aux` and `_assemble` changes are already in the Task 2 diff to `build.py`. This task adds the guard that proves a block-fitted model is served with exactly its columns, and that the block columns are not constant.

**Files:**
- Test: `tests/test_blocks_serving_parity.py`

- [ ] **Step 1: Add the test.**

```python
"""With the EPA and QB blocks on, a game's served row still equals the row training builds for it."""
import numpy as np
import pandas as pd
import pytest

from nfl_predictor.data import pbp_agg
from nfl_predictor.features import build
from epa_fixtures import make_games, make_pbp

BLOCKS = ("epa", "qb")


def _aux(games, upto=None):
    pbp = make_pbp(games)
    if upto is not None:
        ids = set(games[pd.to_datetime(games["gameday"]) < upto]["game_id"])
        pbp = pbp[pbp["game_id"].isin(ids)]
    return build.Aux(pbp_agg.team_game_efficiency(pbp), pbp_agg.qb_games(pbp))


def test_the_served_row_equals_the_trained_row_with_both_blocks():
    games = make_games()
    full_aux = _aux(games)
    trained, cols = build.build_training_frame(games, blocks=BLOCKS, aux=full_aux)
    assert cols == build.feature_columns(BLOCKS) and len(cols) == 10 + len(build.BLOCK_COLUMNS["epa"]) + len(build.BLOCK_COLUMNS["qb"])
    qb_actual = full_aux.qb_games.set_index(["game_id", "team"])["qb_id"]
    sample = trained[trained["season"] == 2025].dropna(subset=cols).sample(12, random_state=2)
    for _, g in sample.iterrows():
        when = pd.Timestamp(g["gameday"])
        history = games[pd.to_datetime(games["gameday"]) < when]
        starters = {g["home_team"]: qb_actual[(g["game_id"], g["home_team"])], g["away_team"]: qb_actual[(g["game_id"], g["away_team"])]}
        served = build.build_features_for_game(
            g["home_team"], g["away_team"], history, gameday=when, blocks=BLOCKS, aux=_aux(games, upto=when), starters=starters,
        )
        np.testing.assert_allclose(served[cols].to_numpy(float), g[cols].to_numpy(float), equal_nan=True, err_msg=g["game_id"])


def test_a_block_with_no_data_refuses_instead_of_defaulting():
    games = make_games()
    with pytest.raises(ValueError, match="aux.efficiency"):
        build.build_training_frame(games, blocks=("epa",))
    with pytest.raises(ValueError, match="aux.qb_games"):
        build.build_training_frame(games, blocks=("qb",), aux=build.Aux(efficiency=pd.DataFrame()))


def test_unknown_blocks_are_an_error_and_the_default_feature_list_is_unchanged():
    with pytest.raises(ValueError, match="unknown feature blocks"):
        build.feature_columns(("nope",))
    assert build.FEATURE_COLUMNS == build.feature_columns(()) and len(build.FEATURE_COLUMNS) == 10


def test_an_unknown_starter_is_a_neutral_new_qb_not_a_guess():
    games = make_games()
    aux = _aux(games)
    row = build.build_features_for_game("T0", "T1", games, gameday="2026-09-10", blocks=("qb",), aux=aux, starters={"T0": None})
    assert row["home_qb_new"] == 1.0 and row["home_qb_games"] == 0.0 and row["home_qb_epa_pd"] == 0.0
```

- [ ] **Step 2: Run.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider` Expected: full suite passes.

- [ ] **Step 3: Commit.** `git add tests/test_blocks_serving_parity.py && git commit -m "test: block-fitted models are served with exactly their columns"`

## Task 7 (NFL, DRAFTED): the conditions block

**Why:** totals and passing games move with wind, cold and dome. The schedule already carries `roof`, `temp` (F) and `wind` (mph) for played games; for upcoming games the same fields come from the Open-Meteo forecast (Task 7b in the frontend plan serves the icon from the same data). Missing weather is NaN-then-imputed with an explicit `wx_known` flag, never zero.

**Files:**
- Create: `src/nfl_predictor/features/conditions.py`
- Modify: `src/nfl_predictor/features/build.py` (add `"conditions": conditions.CONDITION_COLUMNS` to `BLOCK_COLUMNS`; call `add_condition_features` in `_assemble` when the block is selected)
- Test: `tests/test_conditions.py`

- [ ] **Step 1: Write the failing test.**

```python
import pandas as pd
from nfl_predictor.features.conditions import add_condition_features, CONDITION_COLUMNS


def _games(**kw):
    base = {"game_id": "g1", "roof": "outdoors", "temp": 30.0, "wind": 22.0}
    base.update(kw)
    return pd.DataFrame([base])


def test_cold_windy_outdoor_game():
    row = add_condition_features(_games()).iloc[0]
    assert row["wx_known"] == 1 and row["wx_dome"] == 0
    assert row["wx_wind_mph"] == 22.0 and row["wx_cold"] == 1 and row["wx_windy"] == 1


def test_dome_neutralises_weather():
    row = add_condition_features(_games(roof="dome", temp=20.0, wind=30.0)).iloc[0]
    assert row["wx_dome"] == 1 and row["wx_wind_mph"] == 0.0 and row["wx_cold"] == 0 and row["wx_windy"] == 0


def test_missing_weather_is_flagged_not_zeroed():
    row = add_condition_features(_games(temp=None, wind=None)).iloc[0]
    assert row["wx_known"] == 0 and row["wx_wind_mph"] == 0.0 and row["wx_cold"] == 0


def test_columns_declared():
    assert set(CONDITION_COLUMNS) <= set(add_condition_features(_games()).columns)
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_conditions.py` Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""Game conditions as features: dome, wind, cold. Missing weather is flagged (`wx_known=0`), never silently zero."""
from __future__ import annotations

import pandas as pd

COLD_F = 35.0
WINDY_MPH = 15.0
ROOFED = {"dome", "closed"}
CONDITION_COLUMNS = ["wx_known", "wx_dome", "wx_wind_mph", "wx_cold", "wx_windy"]


def add_condition_features(games_df: pd.DataFrame) -> pd.DataFrame:
    out = games_df.copy()
    dome = out["roof"].astype(str).str.lower().isin(ROOFED)
    temp = pd.to_numeric(out["temp"], errors="coerce")
    wind = pd.to_numeric(out["wind"], errors="coerce")
    known = (temp.notna() & wind.notna()) | dome
    outside = known & ~dome
    out["wx_known"] = known.astype(float)
    out["wx_dome"] = dome.astype(float)
    out["wx_wind_mph"] = wind.where(outside, 0.0).fillna(0.0)
    out["wx_cold"] = ((temp < COLD_F) & outside).astype(float)
    out["wx_windy"] = ((wind >= WINDY_MPH) & outside).astype(float)
    return out
```

- [ ] **Step 4: Run, then the full suite.** Expected: pass.

- [ ] **Step 5: Serving.** For an upcoming game `games_df` has no `temp`/`wind`. In `routes.py`, where `aux` is loaded, fill `temp`/`wind` on the upcoming row from `weather_for_games` (`data/weather_cache.py`) using the forecast fetch added in the frontend plan's Task 1 (`fetch_forecast`); a failed fetch leaves NaN, which the block turns into `wx_known=0`. Add a test in `tests/test_conditions.py` that the upcoming-row builder with a fake forecast yields `wx_known == 1`, and with a raising fake yields `0`.

- [ ] **Step 6: Commit.** `git add src/nfl_predictor/features/conditions.py src/nfl_predictor/features/build.py tests/test_conditions.py && git commit -m "feat: conditions block (dome, wind, cold; inert)"`

## Task 8 (NFL, DRAFTED): fitted Elo constants

**Why:** Elo uses `K=20`, home field 65 and a points-per-rating constant that were chosen by hand. A small grid on training seasons only, scored out-of-sample, replaces folklore with measurement. It changes the Elo feature the other models rely on, so it is evaluated like a block.

**Files:**
- Create: `src/nfl_predictor/features/elo_fit.py`
- Test: `tests/test_elo_fit.py`

- [ ] **Step 1: Write the failing test.**

```python
import numpy as np
import pandas as pd
from nfl_predictor.features.elo_fit import fit_elo_constants


def _season(n_teams=8, weeks=14, seed=0, hfa_pts=2.5):
    rng = np.random.default_rng(seed)
    skill = rng.normal(0, 5, n_teams)
    rows, gid = [], 0
    for w in range(weeks):
        order = rng.permutation(n_teams)
        for a, b in zip(order[::2], order[1::2]):
            margin = skill[a] - skill[b] + hfa_pts + rng.normal(0, 10)
            rows.append({"game_id": f"g{gid}", "gameday": pd.Timestamp("2024-09-01") + pd.Timedelta(days=7 * w),
                         "home_team": f"T{a}", "away_team": f"T{b}", "margin": margin})
            gid += 1
    return pd.DataFrame(rows)


def test_fit_returns_grid_members_and_is_deterministic():
    games = _season()
    a, b = fit_elo_constants(games), fit_elo_constants(games)
    assert a == b
    assert set(a) == {"k", "home_field"}
    assert 5 <= a["k"] <= 40 and 0 <= a["home_field"] <= 100


def test_fit_never_uses_the_scored_game():
    games = _season()
    shifted = games.copy()
    shifted.loc[shifted.index[-1], "margin"] += 50  # only the LAST game changes
    assert fit_elo_constants(games.iloc[:-1]) == fit_elo_constants(shifted.iloc[:-1])
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""Pick Elo K and home-field by out-of-sample log loss on past games only."""
from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd

from .power_ratings import ELO_SCALE, compute_pregame_ratings

K_GRID = (10.0, 15.0, 20.0, 25.0, 30.0)
HFA_GRID = (30.0, 45.0, 65.0, 80.0)


def _log_loss(games: pd.DataFrame, k: float, hfa: float) -> float:
    rated = compute_pregame_ratings(games, k=k, home_field=hfa)
    diff = rated["home_elo"] - rated["away_elo"] + hfa
    p = np.clip(1.0 / (1.0 + 10 ** (-diff / ELO_SCALE)), 1e-6, 1 - 1e-6)
    y = (games["margin"] > 0).astype(float).to_numpy()
    burn = len(games) // 4  # early games are rated off the start rating; score the settled part
    return float(-np.mean(y[burn:] * np.log(p[burn:]) + (1 - y[burn:]) * np.log(1 - p[burn:])))


def fit_elo_constants(games: pd.DataFrame) -> dict:
    ordered = games.sort_values(["gameday", "game_id"]).reset_index(drop=True)
    best = min(product(K_GRID, HFA_GRID), key=lambda kh: (_log_loss(ordered, *kh), kh))
    return {"k": best[0], "home_field": best[1]}
```

NOTE for the implementer: `compute_pregame_ratings` is in `features/power_ratings.py`; read its signature and the column names it returns (`home_elo`/`away_elo` above are the expected names) and adjust the two lines that use them. Do not change its behaviour.

- [ ] **Step 4: Run, then the full suite.** Expected: pass.

- [ ] **Step 5: Commit.** `git add src/nfl_predictor/features/elo_fit.py tests/test_elo_fit.py && git commit -m "feat: fit Elo K and home-field by out-of-sample log loss"`

## Task 9 (NFL, DRAFTED): the block evaluation tool

**Why:** one tool applies the decision rule to every block, so no block ships on a single point estimate.

**Files:**
- Create: `tools/block_eval.py`
- Test: `tests/test_block_eval.py`

**Interfaces:**
- Consumes: `prepare_folds(games_df, blocks=..., aux=...)`, `pooled_predictions(folds, candidate)`, `_predict_margins(candidate, train_df, val_df, feature_cols)`.
- Produces: `paired_bootstrap(a, b, n=2000, seed=0) -> (lo, hi)` for mean(a-b); `calibration_gap(probs, y, buckets=5) -> float`; `evaluate_block(games_df, aux, block, candidate) -> dict` with keys `mae_delta`, `brier_delta`, `mae_ci`, `brier_ci`, `gap_base`, `gap_block`, `clears`.

- [ ] **Step 1: Write the failing test.**

```python
import numpy as np
from tools.block_eval import paired_bootstrap, calibration_gap


def test_bootstrap_interval_excludes_zero_for_a_real_gain():
    rng = np.random.default_rng(1)
    base = rng.normal(10, 2, 800)
    better = base - 0.8 + rng.normal(0, 0.5, 800)
    lo, hi = paired_bootstrap(base, better)
    assert lo > 0


def test_bootstrap_interval_spans_zero_for_noise():
    rng = np.random.default_rng(2)
    a = rng.normal(10, 2, 800)
    lo, hi = paired_bootstrap(a, a + rng.normal(0, 0.5, 800))
    assert lo < 0 < hi


def test_calibration_gap_is_zero_for_perfect_buckets():
    p = np.repeat([0.1, 0.3, 0.5, 0.7, 0.9], 1000)
    y = np.concatenate([np.r_[np.ones(int(1000 * q)), np.zeros(1000 - int(1000 * q))] for q in (0.1, 0.3, 0.5, 0.7, 0.9)])
    assert calibration_gap(p, y) < 1e-9
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.

- [ ] **Step 3: Write the tool.**

```python
"""Decide whether a feature block earns its place. Paired bootstrap on identical held-out games."""
from __future__ import annotations

import numpy as np

from nfl_predictor.evaluate import walk_forward as wf


def paired_bootstrap(a, b, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% interval of mean(a - b). Positive means b is better when lower is better."""
    d = np.asarray(a, float) - np.asarray(b, float)
    rng = np.random.default_rng(seed)
    means = rng.choice(d, size=(n, len(d)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def calibration_gap(probs, y, buckets: int = 5) -> float:
    probs, y = np.asarray(probs, float), np.asarray(y, float)
    edges = np.quantile(probs, np.linspace(0, 1, buckets + 1))
    idx = np.clip(np.searchsorted(edges, probs, side="right") - 1, 0, buckets - 1)
    gaps = [abs(probs[idx == b].mean() - y[idx == b].mean()) for b in range(buckets) if (idx == b).any()]
    return float(max(gaps))


def _per_game(folds, candidate):
    errs, briers, probs, ys = [], [], [], []
    for fold in folds:
        preds, sigma = wf._predict_margins(candidate, fold["train_df"], fold["val_df"], fold["feature_cols"])
        margin = fold["val_df"]["margin"].to_numpy()
        p = np.array([wf.game_outcome.margin_to_probabilities(m, sigma)["home_win_prob"] for m in preds])
        errs.append(np.abs(preds - margin))
        y = (margin > 0).astype(float)
        briers.append((p - y) ** 2)
        probs.append(p)
        ys.append(y)
    return tuple(np.concatenate(x) for x in (errs, briers, probs, ys))


def evaluate_block(games_df, aux, block: str, candidate: str = "ridge") -> dict:
    base = _per_game(wf.prepare_folds(games_df), candidate)
    withb = _per_game(wf.prepare_folds(games_df, blocks=(block,), aux=aux), candidate)
    mae_ci, brier_ci = paired_bootstrap(base[0], withb[0]), paired_bootstrap(base[1], withb[1])
    gap_base, gap_block = calibration_gap(base[2], base[3]), calibration_gap(withb[2], withb[3])
    return {
        "block": block, "n_games": int(len(base[0])),
        "mae_delta": float(base[0].mean() - withb[0].mean()), "mae_ci": mae_ci,
        "brier_delta": float(base[1].mean() - withb[1].mean()), "brier_ci": brier_ci,
        "gap_base": gap_base, "gap_block": gap_block,
        "clears": bool(mae_ci[0] > 0 and brier_ci[0] > 0 and gap_block <= gap_base),
    }
```

NOTE: `prepare_folds` returns folds whose `val_df` rows are identical with and without the block only if the block does not drop rows; assert `len(base[0]) == len(withb[0])` inside `evaluate_block` and raise if not (a block that drops games is not comparable). Add that line and a test for it.

- [ ] **Step 4: Run, then the full suite.** Expected: pass.

- [ ] **Step 5: Run it on real data (the deliverable of this plan).** `uv run --python 3.11 python -m tools.block_eval --blocks epa qb conditions` (add a thin `__main__` that loads games and `Aux` the way `routes.py` does and prints one JSON line per block). Paste the table into the PR. Do NOT flip `DEFAULT_BLOCKS` in this PR.

- [ ] **Step 6: Commit.** `git add tools/block_eval.py tests/test_block_eval.py && git commit -m "feat: block evaluation with paired bootstrap and calibration gap"`

## Task 10 (NFL, DRAFTED): QB starter agreement and serving wiring

**Why:** training names the QB who started; serving names the depth-chart expected starter. If those disagree too often the QB block is trained on information the server cannot have. Measure it before shipping the block.

**Files:**
- Create: `tools/qb_agreement.py`
- Modify: `src/nfl_predictor/api/routes.py` (load `Aux` once per request batch: pbp aggregates via `load_pbp_agg`, `qb_games`, depth-chart `expected_starters` with injury Out ids)
- Test: `tests/test_qb_agreement.py`

- [ ] **Step 1: Write the failing test.**

```python
import pandas as pd
from tools.qb_agreement import agreement


def test_agreement_counts_expected_equals_actual():
    actual = {("g1", "A"): "q1", ("g1", "B"): "q2", ("g2", "A"): "q1"}
    expected = {("g1", "A"): "q1", ("g1", "B"): "q9", ("g2", "A"): "q1"}
    out = agreement(actual, expected)
    assert out["n"] == 3 and out["agree"] == 2 and abs(out["rate"] - 2 / 3) < 1e-9


def test_games_without_an_expected_starter_are_reported_not_counted_as_agreement():
    out = agreement({("g1", "A"): "q1"}, {})
    assert out["n"] == 1 and out["agree"] == 0 and out["no_expectation"] == 1
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.

- [ ] **Step 3: Write the tool.**

```python
"""How often does the pre-game expected starter equal the quarterback who actually started?"""
from __future__ import annotations


def agreement(actual: dict, expected: dict) -> dict:
    n = len(actual)
    agree = sum(1 for k, q in actual.items() if expected.get(k) == q)
    return {"n": n, "agree": agree, "rate": agree / n if n else 0.0,
            "no_expectation": sum(1 for k in actual if expected.get(k) is None)}
```

Then a `__main__` that, for each past week, builds `expected_starters(depth_chart_for_that_week, out_ids)` from nflverse depth charts + that week's injury report and compares to `qb_games` starters. Target for shipping the QB block: agreement of at least 90% of games; below that, report which teams/weeks disagree and fix the expected-starter rule first.

- [ ] **Step 4: Wire serving.** In `routes.py`, build `Aux(efficiency=..., qb_games=..., upcoming_starters={(game_id, team): gsis_id})` and pass `blocks=manifest["feature_blocks"]`, `aux=aux` into `build_features_for_game`. The manifest already records `feature_blocks`; legacy models (`feature_blocks == []`) pass `blocks=()` and behave exactly as before. Add a route test with a manifest listing `["epa"]` asserting the model receives the EPA columns and a legacy manifest receives none.

- [ ] **Step 5: Run the full suite; commit.** `git add tools/qb_agreement.py tests/test_qb_agreement.py src/nfl_predictor/api/routes.py && git commit -m "feat: QB starter agreement tool; serve blocks from the manifest"`

## Task 11 (CFB, DRAFTED): CFBD advanced-stats loader (one-time batch)

**Why:** CFB has no per-play efficiency. CFBD's game-level advanced stats (PPA/EPA per play, success rate, by pass/rush, offence/defence) are the CFB analogue of Task 4. The monthly budget is 1,000 calls, so the pull is ONE committed batch (one call per season for 2014-2025 is about 12 calls; per-week fallbacks stay far under budget), resumable, with a counter.

**Files:**
- Create: `src/cfb_predictor/data/cfbd_advanced.py`, `tests/fixtures/cfbd_advanced_sample.json`, `tests/test_cfbd_advanced.py`

**Interfaces:**
- Produces: `fetch_season_advanced(client, year) -> list[dict]` (injected `client.get(path, params)`), `to_team_game_frame(rows) -> pd.DataFrame` with columns `game_id, team, epa_off, epa_def, epa_off_pass, epa_off_rush, epa_def_pass, epa_def_rush, success_off, success_def`; `pull_all(client, years, out_dir, budget=40) -> int` returns calls used and raises `BudgetExceeded` before exceeding `budget`.

- [ ] **Step 1: Record the fixture.** Read `data/cfbd_client` (or the existing client module under `src/cfb_predictor/data/`) to see how the app calls CFBD. Make ONE real call for a single week, `GET /stats/game/advanced?year=2024&week=1`, redact nothing sensitive (it is public data; the key is a header and is never in the output) and save a trimmed two-game response to `tests/fixtures/cfbd_advanced_sample.json`. The field names used below (`offense.ppa`, `offense.passingPlays.ppa`, `offense.rushingPlays.ppa`, `offense.successRate`, and the same under `defense`) are from CFBD's documented schema; confirm them against the recorded response and change the mapping, not the test, if they differ.

- [ ] **Step 2: Write the failing tests.**

```python
import json
from pathlib import Path
import pytest
from cfb_predictor.data.cfbd_advanced import BudgetExceeded, pull_all, to_team_game_frame

FIX = json.loads((Path(__file__).parent / "fixtures" / "cfbd_advanced_sample.json").read_text())


def test_frame_has_one_row_per_team_game_with_all_columns():
    df = to_team_game_frame(FIX)
    assert df.groupby(["game_id", "team"]).size().max() == 1
    assert {"epa_off", "epa_def", "epa_off_pass", "epa_off_rush", "success_off", "success_def"} <= set(df.columns)


def test_defence_columns_come_from_the_opponents_offence():
    df = to_team_game_frame(FIX).set_index(["game_id", "team"])
    (gid, a), (_, b) = list(df.index)[:2]
    assert df.loc[(gid, a), "epa_def"] == pytest.approx(df.loc[(gid, b), "epa_off"])


class FakeClient:
    def __init__(self):
        self.calls = 0

    def get(self, path, params):
        self.calls += 1
        return FIX


def test_budget_is_enforced_before_the_call(tmp_path):
    client = FakeClient()
    with pytest.raises(BudgetExceeded):
        pull_all(client, years=range(2014, 2026), out_dir=tmp_path, budget=3)
    assert client.calls <= 3


def test_pull_is_resumable(tmp_path):
    client = FakeClient()
    pull_all(client, years=[2023, 2024], out_dir=tmp_path, budget=10)
    first = client.calls
    pull_all(client, years=[2023, 2024], out_dir=tmp_path, budget=10)
    assert client.calls == first  # files exist, nothing refetched
```

- [ ] **Step 3: Run to verify failure.** Expected: ImportError.

- [ ] **Step 4: Write the module.**

```python
"""CFBD game-level advanced stats as a committed, resumable, budgeted batch."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class BudgetExceeded(RuntimeError):
    pass


def _side(block: dict) -> dict:
    return {
        "epa": block.get("ppa"),
        "epa_pass": (block.get("passingPlays") or {}).get("ppa"),
        "epa_rush": (block.get("rushingPlays") or {}).get("ppa"),
        "success": block.get("successRate"),
    }


def to_team_game_frame(rows: list[dict]) -> pd.DataFrame:
    by_game: dict = {}
    for r in rows:
        by_game.setdefault(r["gameId"], []).append(r)
    out = []
    for gid, pair in by_game.items():
        if len(pair) != 2:
            continue  # a game with one side missing cannot give defence columns; skip, do not guess
        for me, opp in (pair, pair[::-1]):
            o, d_ = _side(me["offense"]), _side(opp["offense"])  # my defence = what the opponent's offence did to me
            out.append({
                "game_id": str(gid), "team": me["team"],
                "epa_off": o["epa"], "epa_off_pass": o["epa_pass"], "epa_off_rush": o["epa_rush"], "success_off": o["success"],
                "epa_def": d_["epa"], "epa_def_pass": d_["epa_pass"], "epa_def_rush": d_["epa_rush"], "success_def": d_["success"],
            })
    return pd.DataFrame(out)


def fetch_season_advanced(client, year: int) -> list[dict]:
    return client.get("/stats/game/advanced", {"year": year})


def pull_all(client, years, out_dir, budget: int = 40) -> int:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    used = 0
    for year in years:
        target = out_dir / f"advanced_{year}.json"
        if target.exists():
            continue
        if used + 1 > budget:
            raise BudgetExceeded(f"{used} calls used; budget {budget}")
        target.write_text(json.dumps(fetch_season_advanced(client, year)))
        used += 1
    return used
```

- [ ] **Step 5: Run, then the full suite.** Expected: pass.

- [ ] **Step 6: The real pull (human-run, once).** Kevin or the agent runs `pull_all` with the real client for 2014-2025 (about 12 calls), commits `data/cfbd/advanced_*.json`, and records the call count in the PR. Never run it in CI.

- [ ] **Step 7: Commit.** `git add src/cfb_predictor/data/cfbd_advanced.py tests/fixtures/cfbd_advanced_sample.json tests/test_cfbd_advanced.py && git commit -m "feat(cfb): CFBD advanced-stats loader (budgeted, resumable)"`

## Task 12 (CFB, DRAFTED): EPA block and preseason priors

**Why:** college rosters turn over every year, so early-season ratings start from nothing. Two priors fix that: the last season's final rating regressed toward the conference mean, and CFBD returning production / recruiting talent. Both are known before the season starts.

**Files:**
- Create: `src/cfb_predictor/features/epa.py` (a copy of the NFL module's logic over `to_team_game_frame` output: same `STATS`, shrunk EWMA, matchup edges), `src/cfb_predictor/features/priors.py`
- Modify: `src/cfb_predictor/features/build.py` (`BLOCK_COLUMNS` gains `"epa"` and `"priors"`, mirroring NFL Task 2/4)
- Test: `tests/test_cfb_epa.py`, `tests/test_priors.py`

- [ ] **Step 1:** Port `features/epa.py` and its causality, shrinkage, matchup-edge and no-constant tests from the NFL files shown in Task 4 (same names; the data frame is the CFB `to_team_game_frame` output, keyed `game_id, team`). Run to confirm they fail, then copy the module, adjust imports, run, pass.

- [ ] **Step 2: Write the priors test.**

```python
import pandas as pd
from cfb_predictor.features.priors import preseason_prior


def test_prior_regresses_last_final_rating_toward_conference_mean():
    finals = pd.DataFrame({"team": ["A", "B", "C"], "season": [2023] * 3, "rating": [1800.0, 1500.0, 1200.0],
                           "conference": ["X", "X", "X"]})
    p = preseason_prior(finals, season=2024, regress=0.4).set_index("team")["prior"]
    mean = 1500.0
    assert abs(p["A"] - (mean + 0.6 * 300)) < 1e-9 and abs(p["C"] - (mean - 0.6 * 300)) < 1e-9


def test_new_team_gets_the_conference_mean_not_zero():
    finals = pd.DataFrame({"team": ["A", "B"], "season": [2023, 2023], "rating": [1600.0, 1400.0], "conference": ["X", "X"]})
    p = preseason_prior(finals, season=2024, regress=0.4, new_teams={"Z": "X"}).set_index("team")["prior"]
    assert p["Z"] == 1500.0


def test_only_prior_seasons_are_used():
    finals = pd.DataFrame({"team": ["A", "A"], "season": [2023, 2024], "rating": [1700.0, 1000.0], "conference": ["X", "X"]})
    p = preseason_prior(finals, season=2024, regress=0.0).set_index("team")["prior"]
    assert p["A"] == 1700.0  # the 2024 final must not leak into the 2024 preseason
```

- [ ] **Step 3: Write the module.**

```python
"""Preseason prior: last season's final rating, regressed toward its conference mean. Known before kickoff of week 1."""
from __future__ import annotations

import pandas as pd


def preseason_prior(finals: pd.DataFrame, season: int, regress: float = 0.4, new_teams: dict | None = None) -> pd.DataFrame:
    prev = finals[finals["season"] == season - 1]
    if prev.empty:
        prev = finals[finals["season"] < season].sort_values("season").groupby("team").tail(1)
    conf_mean = prev.groupby("conference")["rating"].mean()
    rows = []
    for _, r in prev.iterrows():
        mean = conf_mean[r["conference"]]
        rows.append({"team": r["team"], "prior": mean + (1 - regress) * (r["rating"] - mean)})
    for team, conf in (new_teams or {}).items():
        rows.append({"team": team, "prior": float(conf_mean.get(conf, prev["rating"].mean()))})
    return pd.DataFrame(rows)
```

- [ ] **Step 4:** Returning-production and recruiting priors are an extension: one CFBD call per season each (`/player/returning`, `/teams/talent`), fetched with the Task 11 `pull_all` pattern and the same fixture-only tests. Add them only if `block_eval` shows the Elo prior alone does not clear the rule; do not build them speculatively.

- [ ] **Step 5: Run the CFB `block_eval` (a port of Task 9 with the CFB module names) on `epa` and `priors`; paste the table into the PR; do not flip defaults.**

- [ ] **Step 6: Commit** by name with `feat(cfb): EPA and preseason-prior blocks (inert)`.

---

## Rollout and decision log

1. Merge PR-1 and PR-2 (honest sigma, scaling, parity, conference fix). These change probabilities slightly by design; retrain, deploy, and note it in the changelog. Existing recorded picks are untouched.
2. Merge PR-3/4/5 inert. Run `block_eval` per block on real data; the PR description carries the table.
3. For each block that clears the rule, one small PR flips `DEFAULT_BLOCKS` for that block, retrains, and records the manifest. A block that fails stays inert and the result is written down here (append a dated row: block, sport, n_games, MAE delta + CI, Brier delta + CI, gap before/after, decision).
4. NFL spread/total models: the conditions block is claimed for TOTALS only; evaluate it on total MAE, not on the win-probability metrics.

## Self-review

Spec coverage: sigma (T1, T3), scaling (T1, T3), parity and conference bug (T2, T3), EPA offence-vs-defence (T4, T11-12), QB with training/serving asymmetry measured (T5, T10), conditions (T7), fitted Elo (T8), CFB priors and CFBD budget (T11-12), decision rule (T9, rollout). Placeholders: Tasks 7-12 are drafted code, labelled as not executed, with the specific lines to adjust called out. Type names (`Aux`, `BLOCK_COLUMNS`, `feature_columns`, `build_features_for_game`, `oof_residuals`, `fit_sigmas`) are used consistently with Tasks 1-2.
