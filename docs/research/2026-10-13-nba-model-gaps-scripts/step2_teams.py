from h import *
from sklearn.metrics import log_loss, brier_score_loss, roc_auc_score

frame, cols = base_frame()
print("frame", len(frame), "cols", len(cols))
arm = run_arm(frame, cols)
y = np.asarray(arm["win"]["y"]); n = len(y)
print("pooled n", n, "dates", frame.game_date.min(), frame.game_date.max())

nw, nm, nt = naive_arrays(frame)

# --- trailing-form naives, strictly pre-game, from the same RAW games (every team game before this one)
raw = RAW.sort_values(["game_date", "game_id"]).reset_index(drop=True)
hist = {}  # team -> list of (margin, total)
rows = {}
for r in raw.itertuples():
    for team, sgn in ((r.home_team, 1), (r.away_team, -1)):
        h = hist.setdefault(team, [])
    h_h, h_a = hist[r.home_team], hist[r.away_team]
    def tr(h, k):
        return np.mean([x for x in h[-k:]], axis=0) if h else (np.nan, np.nan)
    rows[r.game_id] = dict(hm10=tr(h_h, 10)[0], am10=tr(h_a, 10)[0], ht10=tr(h_h, 10)[1], at10=tr(h_a, 10)[1],
                           hms=tr(h_h, 999)[0], ams=tr(h_a, 999)[0], hts=tr(h_h, 999)[1], ats=tr(h_a, 999)[1])
    hist[r.home_team].append((r.home_pts - r.away_pts, r.home_pts + r.away_pts))
    hist[r.away_team].append((r.away_pts - r.home_pts, r.home_pts + r.away_pts))
tf = pd.DataFrame.from_dict(rows, orient="index")
ids = []
for tr_i, te_i in expanding_windows(frame["game_date"], 4):
    ids += frame.iloc[te_i].game_id.tolist()
T = tf.loc[ids]
mean_m = nm  # training-window mean margin (= home advantage)
naive_trail_m = mean_m + (T.hm10 - T.am10).fillna(0).to_numpy()
naive_season_m = mean_m + (T.hms - T.ams).fillna(0).to_numpy()
naive_trail_t = ((T.ht10 + T.at10) / 2).fillna(pd.Series(nt, index=T.index)).to_numpy()
naive_season_t = ((T.hts + T.ats) / 2).fillna(pd.Series(nt, index=T.index)).to_numpy()

def bs(yv, a, b, metric):
    return paired_bootstrap(np.asarray(yv), np.asarray(a), np.asarray(b), metric, n_resamples=N_RES, seed=SEED)

def line(name, o, extra=""):
    print(f"  {name:<44}model {o['candidate']:>8.4f}  naive {o['baseline']:>8.4f}  diff(model-naive) {o['difference']:+.4f} "
          f"[{o['ci_low']:+.4f},{o['ci_high']:+.4f}]  skill {(-o['difference']/o['baseline'])*100:+.2f}% "
          f"[{(-o['ci_high']/o['baseline'])*100:+.2f}%,{(-o['ci_low']/o['baseline'])*100:+.2f}%] {extra}")

pw = np.asarray(arm["win"]["preds"])
print("\n== WIN (logistic, race winner) vs naive home rate (train-window)")
for m in ("log_loss", "brier"):
    line(f"win {m}", bs(y, nw, pw, m))
a = bs(y, nw, pw, "auc"); line("win auc (naive 0.5)", a)
print("  max cal gap model", calibration_gap(y, pw, 5), " naive", calibration_gap(y, nw, 5))

# served win = Phi(ridge margin / sigma)
pm = np.asarray(arm["margin"]["preds"]); ym = np.asarray(arm["margin"]["y"])
sig = float(arm["margin"]["mae"]) * MAE_TO_SIGMA
ps = norm.cdf(pm / sig)
print(f"\n== WIN as SERVED: Phi(ridge margin / sigma={sig:.2f}) vs naive home rate")
for m in ("log_loss", "brier"):
    line(f"served win {m}", bs(y, nw, ps, m))
line("served win auc", bs(y, nw, ps, "auc"))
print("  max cal gap", calibration_gap(y, ps, 5))
# Elo reference and logistic vs served
c = default_candidates(cols)
pe = np.asarray(walk_forward_metrics(frame, model_factory=lambda tr: c["elo"]["win"](tr), windows=4)["pooled"]["preds"])
print("\n== WIN: Elo reference (not served) vs naive home rate")
for m in ("log_loss", "brier"):
    line(f"elo {m}", bs(y, nw, pe, m))
line("elo auc", bs(y, nw, pe, "auc"))
print("  max cal gap", calibration_gap(y, pe, 5))
print("\n== logistic vs Elo (paired)")
for m in ("log_loss", "auc"):
    line(f"logistic-vs-elo {m} (naive column = elo)", bs(y, pe, pw, m))

print("\n== MARGIN (ridge) MAE")
line("vs training-mean margin", bs(ym, nm, pm, "mae"))
line("vs fixed -3 (repo's old naive; sign convention home-margin +)", bs(ym, np.full(n, 3.0), pm, "mae"))
line("vs trailing-10 team net margins", bs(ym, naive_trail_m, pm, "mae"))
line("vs season-to-date team net margins", bs(ym, naive_season_m, pm, "mae"))
print("== TOTAL (ridge) MAE")
yt = np.asarray(arm["total"]["y"]); pt = np.asarray(arm["total"]["preds"])
line("vs training-mean total", bs(yt, nt, pt, "mae"))
line("vs fixed league avg 230.174", bs(yt, np.full(n, 230.174), pt, "mae"))
line("vs trailing-10 team totals avg", bs(yt, naive_trail_t, pt, "mae"))
line("vs season-to-date team totals avg", bs(yt, naive_season_t, pt, "mae"))
# cover/over as served = Phi(pred - line/sigma): no lines on disk -> not scoreable
print("\nmargin sigma", sig, "total sigma", float(arm["total"]["mae"]) * MAE_TO_SIGMA)
print("margin mae", arm["margin"]["mae"], "total mae", arm["total"]["mae"])
# random-chance coverage sanity: sd of targets
print("sd margin", ym.std(), "sd total", yt.std())
pd.to_pickle(dict(y=y, pw=pw, ps=ps, pe=pe, nw=nw, ym=ym, pm=pm, nm=nm, yt=yt, pt=pt, nt=nt), "../step2_team_preds.pkl")
