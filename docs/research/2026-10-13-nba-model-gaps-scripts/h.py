"""Shared harness for the NBA gap research. Run from the nba/ clone with: uv run --python 3.13 python ../<script>.py
Uses the repo's own walk-forward evaluators, candidates, paired bootstrap, calibration_gap and ship_decision.
Single season (2025-26) -> history_df is empty; walk-forward = 4 expanding windows over the last 60% of dates."""
import json, sys, warnings
sys.path.insert(0, "src")
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from scipy.stats import norm
from nba_predictor.features.build import build_training_frame, FEATURE_COLUMNS
from nba_predictor.models.candidate_race import default_candidates
from nba_predictor.models.artifact_gate import calibration_gap
from nba_predictor.models.evaluate.paired_bootstrap import paired_bootstrap
from nba_predictor.models.evaluate.ship_rule import ship_decision
from nba_predictor.models.evaluate.walk_forward_eval import (
    walk_forward_metrics, walk_forward_regression, expanding_windows)
from nba_predictor.models.probability import MAE_TO_SIGMA

N_RES, SEED = 2000, 20261009
RAW = pd.DataFrame(json.load(open("data/cache/training/games.json")))


def base_frame(**kw):
    f, cols = build_training_frame(RAW, **kw)
    f = f.assign(home_margin=f.home_pts - f.away_pts, home_total=f.home_pts + f.away_pts)
    return f.sort_values(["game_date", "game_id"]).reset_index(drop=True), cols


def run_arm(frame, cols, kinds=("win", "margin", "total")):
    """Returns pooled out-of-fold dict per target using the repo's race-winner models (logistic win, ridge margin/total)."""
    out = {}
    c = default_candidates(cols)
    if "win" in kinds:
        out["win"] = walk_forward_metrics(frame, model_factory=lambda tr: c["logistic"]["win"](tr), windows=4)["pooled"]
    if "margin" in kinds:
        out["margin"] = walk_forward_regression(frame, model_factory=lambda tr: c["ridge"]["margin"](tr),
                                                target="home_margin", windows=4)["pooled"]
    if "total" in kinds:
        out["total"] = walk_forward_regression(frame, model_factory=lambda tr: c["ridge"]["total"](tr),
                                               target="home_total", windows=4, fixed_baseline=230.174)["pooled"]
    return out


def naive_arrays(frame):
    """Per-game naive predictions in pooled (window) order, from each window's TRAINING slice only."""
    nw, nm, nt = [], [], []
    for tr, te in expanding_windows(frame["game_date"], 4):
        t = frame.iloc[tr]
        nw.append(np.full(len(te), t.home_win.mean()))
        nm.append(np.full(len(te), t.home_margin.mean()))
        nt.append(np.full(len(te), t.home_total.mean()))
    return np.concatenate(nw), np.concatenate(nm), np.concatenate(nt)


def evaluate(base, cand, label, bar_gap_base=None, verbose=True):
    """Paired bootstrap candidate vs baseline on identical games + ship_decision. base/cand = run_arm outputs."""
    assert np.allclose(base["win"]["y"], cand["win"]["y"]) and np.allclose(base["margin"]["y"], cand["margin"]["y"])
    A = lambda d, k: np.asarray(d[k]["preds"])
    y = np.asarray(base["win"]["y"])
    boot = {
        "win log_loss": paired_bootstrap(y, A(base, "win"), A(cand, "win"), "log_loss", n_resamples=N_RES, seed=SEED),
        "win brier": paired_bootstrap(y, A(base, "win"), A(cand, "win"), "brier", n_resamples=N_RES, seed=SEED),
        "win auc": paired_bootstrap(y, A(base, "win"), A(cand, "win"), "auc", n_resamples=N_RES, seed=SEED),
        "margin mae": paired_bootstrap(np.asarray(base["margin"]["y"]), A(base, "margin"), A(cand, "margin"), "mae", n_resamples=N_RES, seed=SEED),
        "total mae": paired_bootstrap(np.asarray(base["total"]["y"]), A(base, "total"), A(cand, "total"), "mae", n_resamples=N_RES, seed=SEED),
    }
    gb = calibration_gap(y, A(base, "win"), n_buckets=5)
    gc = calibration_gap(y, A(cand, "win"), n_buckets=5)
    dec = ship_decision(boot, gap=gc, baseline_gap=gb)
    if verbose:
        print(f"\n### {label}  (n={len(y)})")
        for k, o in boot.items():
            tag = "IMPROVED" if o["improved"] else ("WORSE" if (o["ci_low"] > 0 if o["lower_is_better"] else o["ci_high"] < 0) else "n.s.")
            print(f"  {k:<13}{o['baseline']:>9.4f}{o['candidate']:>9.4f}{o['difference']:>+9.4f}  [{o['ci_low']:+.4f},{o['ci_high']:+.4f}]  {tag}")
        print(f"  cal gap {gb:.4f} -> {gc:.4f}; auc_ok={dec['auc_ok']} missing={dec['missing']} gap_ok={dec['gap_ok']} => {'SHIPS' if dec['ships'] else 'does NOT ship'}")
    return boot, dec, gb, gc
