import sys, json; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../F1_Predictor/src')
from f1_predictor.models import race_outcome, dnf as dnf_model
from f1_predictor.features import session_state
M = json.load(open('../F1_Predictor/models/manifest.json'))
RANK_P = M['tuned_ranker_params']; DNF_P = M['tuned_dnf_params']
def pl_probs(theta, n=20000, seed=42):
    """Plackett-Luce via Gumbel trick (same distribution as race_outcome.draw_classification with no DNFs)."""
    rng = np.random.default_rng(seed); lt = np.log(np.asarray(theta, float))
    g = lt[None, :] + rng.gumbel(size=(n, len(lt))); rank = np.argsort(np.argsort(-g, 1), 1) + 1
    return (rank == 1).mean(0), (rank <= 3).mean(0), (rank <= 10).mean(0), rank.mean(0)
def run(df, feature_cols, val_seasons, tier=session_state.TIER_POST_QUALIFYING, ranker_params=None, with_dnf=False, dnf_cols=None, train_tier_only=True):
    """Walk-forward: train on all earlier seasons (all tiers, as production), score `tier` rows of val season.
    Returns one row per driver-race with xgb / elo / grid-naive probabilities."""
    out = []
    for vs in val_seasons:
        tr = df[df.season < vs]; va = df[(df.season == vs) & (df.tier == tier)]
        if tr.empty or va.empty: continue
        rk = race_outcome.train_ranker(tr[tr.tier == tier] if train_tier_only else tr, feature_cols, hyperparams=ranker_params or RANK_P)
        trq = tr[tr.tier == session_state.TIER_POST_QUALIFYING].copy()
        trq['gridc'] = trq.grid.fillna(20).clip(1, 20)
        Wr = trq.groupby('gridc').apply(lambda g: pd.Series({'w': ((g.position == 1).sum()+.5)/(len(g)+10), 'p': ((g.position <= 3).sum()+1)/(len(g)+10), 't': ((g.position <= 10).sum()+2)/(len(g)+10), 'e': g.position.fillna(20).mean()}), include_groups=False)
        if with_dnf:
            clf = dnf_model.train_dnf_model(tr[tr.tier == session_state.TIER_POST_QUALIFYING], dnf_cols or feature_cols, hyperparams=DNF_P)
        for (s, r), race in va.groupby(['season', 'round']):
            race = race.reset_index(drop=True)
            sc = rk.predict(race[feature_cols]); th = np.exp(sc - sc.max())
            w, p, t, e = pl_probs(th)
            el = (race.elo_pre_race.fillna(1500) + race.team_strength_pre_race.fillna(1500)).values
            w2, p2, t2, e2 = pl_probs(10 ** ((el - el.max())/400))
            gc = race.grid.fillna(20).clip(1, 20).values
            # grid naive: normalise within race so probabilities sum to 1 / 3 / 10
            gw = Wr.w.reindex(gc).values; gw = gw/gw.sum()
            gp = Wr.p.reindex(gc).values; gp = gp*3/gp.sum(); gt = Wr.t.reindex(gc).values; gt = gt*10/gt.sum()
            d = pd.DataFrame(dict(season=s, round=r, driver_id=race.driver_id, pos=race.position, dnf=race.dnf.astype(int), grid=race.grid,
                                  win=(race.position == 1).astype(int), pod=(race.position <= 3).astype(int), top10=(race.position <= 10).astype(int),
                                  x_w=w, x_p=p, x_t=t, x_e=e, e_w=w2, e_p=p2, e_t=t2, e_e=e2, g_w=gw, g_p=np.clip(gp,.001,.999), g_t=np.clip(gt,.001,.999), g_e=Wr.e.reindex(gc).values))
            if with_dnf: d['x_dnf'] = clf.predict_proba(race[dnf_cols or feature_cols])[:, 1]; d['n_dnf'] = trq.dnf.mean()
            out.append(d)
    return pd.concat(out, ignore_index=True)
def ll(y, p): p = np.clip(p, 1e-4, 1-1e-4); return -(y*np.log(p) + (1-y)*np.log(1-p))
def ece(p, y, k=10):
    p=np.asarray(p); y=np.asarray(y); b=np.clip((p*k).astype(int),0,k-1); return sum(abs(y[b==i].mean()-p[b==i].mean())*(b==i).mean() for i in range(k) if (b==i).any())
def race_sum(R, loss):  # per-race mean loss -> paired unit = race
    return pd.Series(loss).groupby([R.season.values, R['round'].values]).mean()
def compare(R, a, b, y='win', metric='ll'):
    """improvement of a over b: mean(loss_b - loss_a) per race, bootstrap over races."""
    yy = R[y].values
    la = race_sum(R, ll(yy, R[a].values) if metric == 'll' else (R[a].values - yy)**2); lb = race_sum(R, ll(yy, R[b].values) if metric == 'll' else (R[b].values - yy)**2)
    return boot_ci((lb - la).values)
