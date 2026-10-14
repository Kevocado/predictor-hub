from h import *
import xgboost as xgb
from sklearn.linear_model import Ridge
from nba_predictor.features.player_stats import build_player_feature_frame
from nba_predictor.features.prop_matchup import build_prop_features
from nba_predictor.models.player_props import train_player_stat_model

P = pd.read_pickle("../players.pkl")
F = pd.read_pickle("../F_team.pkl")  # team frame with pace/elo features, keyed by game_id
base, bcols = build_player_feature_frame(P)
base = base.sort_values(["player_id", "game_date", "game_id"]).reset_index(drop=True)
g = base.groupby("player_id")
for s in ("fga", "fg3a", "fta"):
    base[f"{s}_roll"] = g[s].transform(lambda x: x.shift(1).rolling(10, min_periods=1).mean())
base["minutes_sd"] = g["minutes"].transform(lambda x: x.shift(1).rolling(10, min_periods=3).std())
n3m = g["fg3m"].transform(lambda x: x.shift(1).rolling(20, min_periods=1).sum())
n3a = g["fg3a"].transform(lambda x: x.shift(1).rolling(20, min_periods=1).sum())
LG3 = 0.355
base["fg3_pct_shrunk"] = (n3m + 40 * LG3) / (n3a + 40)
base["exp_threes"] = base["fg3a_roll"] * base["fg3_pct_shrunk"]
base["threes_per_min_x_min"] = (n3m / g["minutes"].transform(lambda x: x.shift(1).rolling(20, min_periods=1).sum()).replace(0, np.nan)) * base["minutes_roll"]
dts = pd.to_datetime(base.game_date)
base["p_rest"] = (dts - dts.groupby(base.player_id).shift(1)).dt.days.clip(upper=14).fillna(14)
# repo's matchup block
mb = build_prop_features(P)[["player_id", "game_id", "opp_def_vs_pos", "usage_trend", "minutes_trend"]]
base = base.merge(mb, on=["player_id", "game_id"], how="left")
# game context from the team blocks
tb = F[["game_id", "home_team", "away_team", "home_pace_roll", "away_pace_roll", "home_ortg_roll", "away_ortg_roll",
        "home_drtg_roll", "away_drtg_roll", "elo_diff"]]
base = base.merge(tb, on="game_id", how="left", suffixes=("", "_t"))
ish = (base.team == base.home_team_t) if "home_team_t" in base else (base.team == base.home_team)
home_col = "home_team_t" if "home_team_t" in base else "home_team"
ish = base.team == base[home_col]
base["is_home"] = ish.astype(float)
base["team_pace"] = np.where(ish, base.home_pace_roll, base.away_pace_roll)
base["opp_pace"] = np.where(ish, base.away_pace_roll, base.home_pace_roll)
base["game_pace"] = (base.team_pace + base.opp_pace) / 2
base["opp_drtg"] = np.where(ish, base.away_drtg_roll, base.home_drtg_roll)
base["team_ortg"] = np.where(ish, base.home_ortg_roll, base.away_ortg_roll)
base["abs_elo_diff"] = base.elo_diff.abs() / 100
base["team_elo_adv"] = np.where(ish, base.elo_diff, -base.elo_diff) / 100
base = base.dropna(subset=["game_pace"]).sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
print("rows", len(base))

TARGET = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "fg3m"}
SETS = {
    "P0 current (5 rolls)": bcols,
    "P1 + repo matchup block": bcols + ["opp_def_vs_pos", "usage_trend", "minutes_trend", "p_rest"],
    "P2 + game context (home, pace, opp drtg, blowout risk)": bcols + ["is_home", "game_pace", "opp_drtg", "team_ortg", "abs_elo_diff", "team_elo_adv"],
    "P3 + shot profile (fga/fg3a/fta roll, shrunk 3P%, exp threes)": bcols + ["fga_roll", "fg3a_roll", "fta_roll", "fg3_pct_shrunk", "exp_threes"],
    "P4 all of the above": bcols + ["opp_def_vs_pos", "usage_trend", "minutes_trend", "p_rest", "is_home", "game_pace", "opp_drtg", "team_ortg",
                                    "abs_elo_diff", "team_elo_adv", "fga_roll", "fg3a_roll", "fta_roll", "fg3_pct_shrunk", "exp_threes", "minutes_sd"],
}
win_idx = expanding_windows(base["game_date"], 4)


def fit_predict(kind, cols, tgt, trn, tst):
    Xtr, Xte = trn[cols], tst[cols]
    med = Xtr.median()
    if kind == "xgb":
        return train_player_stat_model(Xtr, trn[tgt]).predict(Xte)
    if kind == "xgb_damped":
        m = xgb.XGBRegressor(n_estimators=120, max_depth=3, learning_rate=0.03, min_child_weight=40, subsample=0.8,
                             colsample_bytree=0.8, reg_lambda=10.0, random_state=7)
        return m.fit(Xtr, trn[tgt]).predict(Xte)
    if kind == "ridge":
        mu, sd = Xtr.fillna(med).mean(), Xtr.fillna(med).std().replace(0, 1)
        m = Ridge(alpha=50.0).fit((Xtr.fillna(med) - mu) / sd, trn[tgt])
        return m.predict((Xte.fillna(med) - mu) / sd)


def cluster_boot(err_a, err_b, groups, n=N_RES, seed=SEED):
    ug, inv = np.unique(groups, return_inverse=True)
    sa = np.bincount(inv, weights=np.abs(err_a)); sb = np.bincount(inv, weights=np.abs(err_b)); c = np.bincount(inv)
    rng = np.random.default_rng(seed); k = len(ug); d = []
    for _ in range(n):
        i = rng.integers(0, k, k); d.append((sb[i].sum() - sa[i].sum()) / c[i].sum())
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(np.abs(err_b).mean() - np.abs(err_a).mean()), float(lo), float(hi)




for mk, tgt in (("threes", "fg3m"),):
    y, gid, trail, d1, d2, d3 = [], [], [], [], [], []
    for tr, te in win_idx:
        tst = base.iloc[te]
        y.append(tst[tgt].to_numpy()); gid.append(tst.game_id.to_numpy()); tr_ = tst["fg3m_roll"].to_numpy(); trail.append(tr_)
        d1.append(tst["exp_threes"].fillna(tst["fg3m_roll"]).to_numpy())
        d2.append(tst["threes_per_min_x_min"].fillna(tst["fg3m_roll"]).to_numpy())
        d3.append((0.5 * tst["threes_per_min_x_min"].fillna(tst["fg3m_roll"]) + 0.5 * tst["exp_threes"].fillna(tst["fg3m_roll"])).to_numpy())
    y, gid, trail = map(np.concatenate, (y, gid, trail))
    for nm, v in (("exp_threes = fg3a_roll10 x shrunk3P%(20,k=40)", d1), ("3PM per minute (20g) x minutes_roll10", d2), ("average of the two", d3)):
        p_ = np.concatenate(v); d = cluster_boot(trail - y, p_ - y, gid)
        print(f"DIRECT {nm:<52} MAE {np.abs(p_-y).mean():.4f} vs trailing-10 mean {d[0]:+.4f} [{d[1]:+.4f},{d[2]:+.4f}] (trailing MAE {np.abs(trail-y).mean():.4f}, n={len(y)})", flush=True)
