from h import *
F = pd.read_pickle("../F_team.pkl")
_, cols = base_frame()
H = ["elo_diff_s","home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","home_pace_roll_s","away_pace_roll_s"]
AV = ["home_absent_min_share","away_absent_min_share","home_absent_prod_share","away_absent_prod_share"]
B = run_arm(F, cols); Hh = run_arm(F, cols + H); HF = run_arm(F, cols + H + AV)
sizes = [246, 258, 206, 53, 2]
cuts = np.cumsum([0] + sizes)
y = np.asarray(B["win"]["y"]); ym = np.asarray(B["margin"]["y"]); yt = np.asarray(B["total"]["y"])
ll = lambda y, p: -(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()
print("slice(n)           LL base   LL H    LL HF | margin MAE base  H   HF | total MAE base  H   HF")
for a, b in zip(cuts[:-1], cuts[1:]):
    if b - a < 50: continue
    s = slice(a, b)
    print(f"{a:>4}-{b:<4}({b-a:>3})  {ll(y[s], np.asarray(B['win']['preds'])[s]):.4f}  {ll(y[s], np.asarray(Hh['win']['preds'])[s]):.4f}  {ll(y[s], np.asarray(HF['win']['preds'])[s]):.4f} | "
          f"{np.abs(ym[s]-np.asarray(B['margin']['preds'])[s]).mean():.3f} {np.abs(ym[s]-np.asarray(Hh['margin']['preds'])[s]).mean():.3f} {np.abs(ym[s]-np.asarray(HF['margin']['preds'])[s]).mean():.3f} | "
          f"{np.abs(yt[s]-np.asarray(B['total']['preds'])[s]).mean():.3f} {np.abs(yt[s]-np.asarray(Hh['total']['preds'])[s]).mean():.3f} {np.abs(yt[s]-np.asarray(HF['total']['preds'])[s]).mean():.3f}")
# HF served-probability and sigma
for n_, A in (("baseline", B), ("HF", HF)):
    pm = np.asarray(A["margin"]["preds"]); sig = A["margin"]["mae"] * MAE_TO_SIGMA; ps = norm.cdf(pm / sig)
    print(n_, "served gap", round(calibration_gap(y, ps, 5), 4), "LL", round(ll(y, ps), 4), "sigma_margin", round(sig, 2), "sigma_total", round(A["total"]["mae"] * MAE_TO_SIGMA, 2))
rng = np.random.default_rng(SEED)
p = np.asarray(HF["win"]["preds"]); g = [calibration_gap((rng.random(len(p)) < p).astype(float), p, 5) for _ in range(500)]
print("HF gap if perfectly calibrated (sim): ", np.percentile(g, [2.5, 50, 97.5]).round(4), "observed", round(calibration_gap(y, p, 5), 4))
