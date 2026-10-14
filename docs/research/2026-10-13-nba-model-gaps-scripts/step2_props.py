from h import *
import xgboost as xgb
from nba_predictor.features.player_stats import build_player_feature_frame, PLAYER_FEATURE_COLUMNS
from nba_predictor.models.player_props import train_player_stat_model

P = pd.read_pickle("../players.pkl")
frame, fcols = build_player_feature_frame(P)
frame = frame.sort_values(["game_date", "game_id", "player_id"]).reset_index(drop=True)
# per-minute trailing rate x trailing minutes (second naive)
g = frame.groupby("player_id")
for s in ("points", "rebounds", "assists", "fg3m"):
    num = g[s].transform(lambda x: x.shift(1).rolling(10, min_periods=1).sum())
    den = g["minutes"].transform(lambda x: x.shift(1).rolling(10, min_periods=1).sum())
    frame[f"{s}_rate_x_min"] = (num / den.replace(0, np.nan)) * frame["minutes_roll"]
print("player frame", len(frame), "players", frame.player_id.nunique(), "games", frame.game_id.nunique())

TARGET = {"points": "points", "rebounds": "rebounds", "assists": "assists", "threes": "fg3m"}
win_idx = expanding_windows(frame["game_date"], 4)
print("windows (train rows/test rows):", [(len(a), len(b)) for a, b in win_idx])


def cluster_boot(err_a, err_b, groups, n=N_RES, seed=SEED):
    """Paired bootstrap of mean(|err_b|)-mean(|err_a|) resampling GAMES (rows within a game share a game-script)."""
    ug, inv = np.unique(groups, return_inverse=True)
    sa = np.bincount(inv, weights=np.abs(err_a)); sb = np.bincount(inv, weights=np.abs(err_b)); c = np.bincount(inv)
    rng = np.random.default_rng(seed); k = len(ug); d = []
    for _ in range(n):
        i = rng.integers(0, k, k)
        d.append((sb[i].sum() - sa[i].sum()) / c[i].sum())
    lo, hi = np.percentile(d, [2.5, 97.5])
    return float(np.abs(err_b).mean() - np.abs(err_a).mean()), float(lo), float(hi)


res = {}
for subset in ("all rows with features (repo-style)", "played only (minutes>0)"):
    print("\n=====", subset)
    for mk, tgt in TARGET.items():
        preds, y, naive1, naive2, naive0, gid, mins = [], [], [], [], [], [], []
        for tr, te in win_idx:
            trn, tst = frame.iloc[tr], frame.iloc[te]
            m = train_player_stat_model(trn[fcols], trn[tgt])
            preds.append(m.predict(tst[fcols])); y.append(tst[tgt].to_numpy())
            naive1.append(tst[f"{tgt}_roll"].to_numpy())
            naive2.append(tst[f"{tgt}_rate_x_min"].fillna(tst[f"{tgt}_roll"]).to_numpy())
            naive0.append(np.full(len(tst), trn[tgt].mean()))
            gid.append(tst["game_id"].to_numpy()); mins.append(tst["minutes"].to_numpy())
        preds, y, naive1, naive2, naive0, gid, mins = map(np.concatenate, (preds, y, naive1, naive2, naive0, gid, mins))
        keep = np.ones(len(y), bool) if subset.startswith("all") else mins > 0
        e_m, e1, e2, e0 = (preds - y)[keep], (naive1 - y)[keep], (naive2 - y)[keep], (naive0 - y)[keep]
        G = gid[keep]
        out = {}
        for nm_, e in (("player trailing-10 mean", e1), ("trailing rate x trailing minutes", e2), ("league mean (train window)", e0)):
            d, lo, hi = cluster_boot(e, e_m, G)  # model minus naive
            base = np.abs(e).mean()
            out[nm_] = (np.abs(e_m).mean(), base, d, lo, hi)
            print(f"  {mk:<9} n={keep.sum():>6}  model MAE {np.abs(e_m).mean():.4f}  vs {nm_:<34} {base:.4f}  diff {d:+.4f} [{lo:+.4f},{hi:+.4f}]  skill {(-d/base)*100:+.2f}% [{(-hi/base)*100:+.2f}%,{(-lo/base)*100:+.2f}%]")
        res[(subset, mk)] = out
pd.to_pickle(res, "../step2_props.pkl")
