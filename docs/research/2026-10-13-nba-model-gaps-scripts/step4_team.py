from h import *
import feats
P = pd.read_pickle("../players.pkl")
frame, cols = base_frame()
TB = feats.team_blocks(RAW)
AV = feats.availability_proxy(P, RAW)
F = frame.merge(TB, on="game_id", how="left").merge(AV, on="game_id", how="left")
# scale to ~unit so unscaled ridge/logistic treat them like the repo's other columns
F["elo_diff_s"] = F.elo_diff / 100; F["elo_mov_diff_s"] = F.elo_mov_diff / 100
for c in ("home_pace_roll", "away_pace_roll"): F[c + "_s"] = (F[c] - 100) / 5
F["pace_sum_s"] = (F.pace_sum_roll - 200) / 10
for s in ("home", "away"):
    for k in ("ortg", "drtg"): F[f"{s}_{k}_s"] = (F[f"{s}_{k}_roll"] - 112) / 5
    for k in ("adj_off", "adj_def"): F[f"{s}_{k}_s"] = F[f"{s}_{k}_roll"] / 5
F["adj_net_diff_s"] = F.adj_net_diff / 5
F["exp_total_s"] = (F.exp_total - 230) / 10
F["home_fg3a_rate_s"] = F.home_fg3a_rate_roll * 10; F["away_fg3a_rate_s"] = F.away_fg3a_rate_roll * 10
print("NaN in new cols:", F[[c for c in F.columns if c.endswith('_s') or 'absent' in c]].isna().sum().sum())
F.to_pickle("../F_team.pkl")

# drop the dead columns? NO - baseline is the repo default as-is.
ARMS = {
  "A elo (W/L, 10-base) -> power_rating block": ["elo_diff_s"],
  "B elo MOV variant": ["elo_mov_diff_s"],
  "C pace + efficiency rolling (ortg/drtg/pace)": ["home_pace_roll_s","away_pace_roll_s","home_ortg_s","away_ortg_s","home_drtg_s","away_drtg_s"],
  "D opponent-adjusted off/def ratings": ["home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","adj_net_diff_s"],
  "E pace x efficiency expected total": ["exp_total_s","pace_sum_s"],
  "F availability proxy (lagged absent rotation share)": ["home_absent_min_share","away_absent_min_share","home_absent_prod_share","away_absent_prod_share"],
  "G rest cleaned: team-based rest capped at 7 + games in last 7d (replaces repo rest cols)": ["home_rest_team","away_rest_team","home_g_last7","away_g_last7"],
  "H elo + adjusted ratings + pace (combined 'power+adjusted+form')": ["elo_diff_s","home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","home_pace_roll_s","away_pace_roll_s"],
}
base = run_arm(F, cols)
res = {}
for name, extra in ARMS.items():
    use = [c for c in cols if not c.startswith(("home_rest","away_rest","home_back","away_back"))] if name.startswith("G") else list(cols)
    arm = run_arm(F, use + extra)
    res[name] = evaluate(base, arm, name)
import pickle; pickle.dump({k: (v[0], v[1], v[2], v[3]) for k, v in res.items()}, open("../step4_team.pkl", "wb"))
