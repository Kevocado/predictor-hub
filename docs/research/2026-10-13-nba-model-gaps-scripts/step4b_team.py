from h import *
F = pd.read_pickle("../F_team.pkl")   # written by step4_team.py (kept; rebuild with that script)
_, cols = base_frame()
DEAD = ["home_power_rating","away_power_rating","power_rating_diff","home_missing_value","away_missing_value"]
H = ["elo_diff_s","home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","home_pace_roll_s","away_pace_roll_s"]
C = ["home_pace_roll_s","away_pace_roll_s","home_ortg_s","away_ortg_s","home_drtg_s","away_drtg_s"]
base = run_arm(F, cols)
y = np.asarray(base["win"]["y"])

# 1. does removing the 5 constant-zero columns (and capping the 99-day rest) change anything by itself?
F2 = F.copy()
for s in ("home","away"):
    F2[f"{s}_rest_days"] = F2[f"{s}_rest_days"].clip(upper=7)
clean = [c for c in cols if c not in DEAD]
X = run_arm(F2, clean)
evaluate(base, X, "X: drop 5 dead columns + cap rest_days at 7 (no new information)")
XH = run_arm(F2, clean + H)
evaluate(base, XH, "XH: X + H(elo + adjusted ratings + pace)")
# 2. calibration noise: bootstrap the 5-bucket max gap itself
rng = np.random.default_rng(SEED)
def gap_ci(p):
    g = []
    for _ in range(1000):
        i = rng.integers(0, len(y), len(y)); g.append(calibration_gap(y[i], p[i], 5))
    return np.percentile(g, [2.5, 50, 97.5]).round(4)
# a perfectly calibrated model of the same spread: draw outcomes from p itself -> expected max-gap from sampling noise alone
def noise_gap(p, reps=500):
    g = []
    for _ in range(reps):
        yy = (rng.random(len(p)) < p).astype(float); g.append(calibration_gap(yy, p, 5))
    return np.percentile(g, [2.5, 50, 97.5]).round(4)
H_arm = run_arm(F, cols + H); C_arm = run_arm(F, cols + C)
for name, arm in (("baseline", base), ("H", H_arm), ("C", C_arm), ("XH", XH)):
    p = np.asarray(arm["win"]["preds"])
    print(f"{name:<9} gap {calibration_gap(y, p, 5):.4f}  bootstrap CI(2.5,50,97.5) {gap_ci(p)}  | gap if the model were PERFECTLY calibrated (outcomes drawn from its own p): {noise_gap(p)}")
# 3. served probability Phi(margin/sigma) for H and baseline
for name, arm in (("baseline", base), ("H", H_arm), ("C", C_arm)):
    pm = np.asarray(arm["margin"]["preds"]); sig = arm["margin"]["mae"] * MAE_TO_SIGMA
    ps = norm.cdf(pm / sig)
    print(f"{name:<9} served Phi(margin/sigma={sig:.2f}): gap {calibration_gap(y, ps, 5):.4f}, logloss {-(y*np.log(ps)+(1-y)*np.log(1-ps)).mean():.4f}, sigma_margin {sig:.2f}, sigma_total {arm['total']['mae']*MAE_TO_SIGMA:.2f}")
# 4. out-of-fold Platt calibrator (repo walk_forward_metrics calibrator='platt'; first 2 windows stay uncalibrated)
c = default_candidates(cols + H)
for name, cc in (("baseline", cols), ("H", cols + H)):
    c = default_candidates(cc)
    o = walk_forward_metrics(F.sort_values("game_date").reset_index(drop=True), model_factory=lambda tr: c["logistic"]["win"](tr), windows=4, calibrator="platt")
    p = np.asarray(o["pooled"]["preds"]); yy = np.asarray(o["pooled"]["y"])
    m = np.zeros(len(p), bool); n_unc = sum(len(w) for w in [0]) 
    cal_from = o["calibrated_from_window"]
    sizes = [w["n_test"] for w in o["windows"]]
    start = sum(sizes[:cal_from]) if cal_from is not None else len(p)
    print(f"{name:<9} platt OOF: calibrated from window {cal_from}; games calibrated {len(p)-start}; gap on calibrated games {calibration_gap(yy[start:], p[start:], 5):.4f}; logloss(all) {o['pooled']['log_loss']:.4f}")
