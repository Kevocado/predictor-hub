from h import *
F = pd.read_pickle("../F_team.pkl")   # written by step4_team.py (kept; rebuild with that script)
_, cols = base_frame()
DEAD = ["home_power_rating","away_power_rating","power_rating_diff","home_missing_value","away_missing_value"]
H = ["elo_diff_s","home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","home_pace_roll_s","away_pace_roll_s"]
C = ["home_pace_roll_s","away_pace_roll_s","home_ortg_s","away_ortg_s","home_drtg_s","away_drtg_s"]
base = run_arm(F, cols)
y = np.asarray(base["win"]["y"])

H_ = None
# 4. out-of-fold Platt calibrator (repo walk_forward_metrics calibrator='platt'; first 2 windows stay uncalibrated)
c = default_candidates(cols + H)
for name, cc in (("baseline", cols), ("H", cols + H)):
    c = default_candidates(cc)
    o = walk_forward_metrics(F.sort_values("game_date").reset_index(drop=True), model_factory=lambda tr: c["logistic"]["win"](tr), windows=4, calibrator="platt")
    p = np.asarray(o["pooled"]["preds"]); yy = np.asarray(o["pooled"]["y"])
    cal_from = o["calibrated_from_window"]
    o0 = walk_forward_metrics(F.sort_values("game_date").reset_index(drop=True), model_factory=lambda tr: c["logistic"]["win"](tr), windows=4)
    p0 = np.asarray(o0["pooled"]["preds"])
    sizes = [w["n_test"] for w in o["windows"]]
    start = sum(sizes[:cal_from]) if cal_from is not None else len(p)
    print(f"{name:<9} platt OOF: calibrated from window {cal_from}; games calibrated {len(p)-start}; gap on those games: platt {calibration_gap(yy[start:], p[start:], 5):.4f} vs uncalibrated {calibration_gap(yy[start:], p0[start:], 5):.4f}; logloss on those games platt {float(-(yy[start:]*np.log(p[start:])+(1-yy[start:])*np.log(1-p[start:])).mean()):.4f} vs uncal {float(-(yy[start:]*np.log(p0[start:])+(1-yy[start:])*np.log(1-p0[start:])).mean()):.4f}; logloss(all) {o['pooled']['log_loss']:.4f}")
