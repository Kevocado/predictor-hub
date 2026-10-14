"""Step 2: PL per-market skill vs naive baselines, 5 walk-forward folds (val 2021-22..2025-26),
train = all earlier seasons in the 8-season frame (same as evaluate/walk_forward.prepare_folds).
Usage: python pl_rank.py  -> writes pl_rank.json + pl_preds.pkl"""
import sys, json, time; sys.path.insert(0,'.')
from common import *
sys.path.insert(0, '../PL_Predictor/src')
import penaltyblog as pb
from scipy import stats
from pl_predictor.models import ml_scoreline, market_models
df = pd.read_pickle('pl_frame.pkl'); cols = json.load(open('pl_cols.json'))
ml_cols = [c for c in cols if 'fouls' not in c]
seasons = sorted(df.season.unique()); df = df.reset_index(drop=True)
df['mid'] = np.arange(len(df))
def devig(*o):
    o = np.array(o, float).T; p = 1/o; return p/p.sum(1, keepdims=True)
out = []
for i in range(3, len(seasons)):
    vs = seasons[i]; tr = df[df.season.isin(seasons[:i])]; va = df[df.season == vs]
    Xtr, Xva = tr[ml_cols].fillna(0), va[ml_cols].fillna(0)
    hm, am = ml_scoreline.train_goal_regressors(Xtr, tr.goals_home, tr.goals_away)
    grids = ml_scoreline.predict_grids_batch(hm, am, Xva)
    P = np.array([[g.home_win, g.draw, g.away_win] for g in grids])
    # grid matrix for exact score / BTTS / O/U
    pover = []; pbtts = []; pscore = []
    for g, (a, b) in zip(grids, zip(va.goals_home, va.goals_away)):
        M = np.asarray(g.grid); M = M/M.sum()
        n = M.shape[0]; tot = np.add.outer(np.arange(n), np.arange(n))
        pover.append(M[tot > 2.5].sum()); pbtts.append(M[1:, 1:].sum()); pscore.append(M[min(a, n-1), min(b, n-1)])
    r = va[['mid','season','date','team_home','team_away','goals_home','goals_away','ftr']].copy()
    r[['p_h','p_d','p_a']] = P; r['p_over'] = pover; r['p_btts'] = pbtts; r['p_score'] = pscore
    # naive baselines from TRAIN only
    fr = tr.ftr.value_counts(normalize=True); r[['n_h','n_d','n_a']] = [fr['H'], fr['D'], fr['A']]
    r['n_over'] = ((tr.goals_home+tr.goals_away) > 2.5).mean(); r['n_btts'] = ((tr.goals_home > 0) & (tr.goals_away > 0)).mean()
    lh, la = tr.goals_home.mean(), tr.goals_away.mean()
    r['n_score'] = [stats.poisson.pmf(a, lh)*stats.poisson.pmf(b, la) for a, b in zip(va.goals_home, va.goals_away)]
    # market (de-vigged proportional): opening Bet365 + closing Pinnacle where present
    for tag, c in [('b365', ['b365_h','b365_d','b365_a']), ('pin', ['psch','pscd','psca'])]:
        ok = va[c].notna().all(1)
        m = np.full((len(va), 3), np.nan); m[ok.values] = devig(*[va.loc[ok, k] for k in c])
        r[[f'm{tag}_h', f'm{tag}_d', f'm{tag}_a']] = m
    for tag, (o, u) in {'b365': ('b365>2.5','b365<2.5'), 'pin': ('pc>2.5','pc<2.5'), 'avg': ('avg>2.5','avg<2.5')}.items():
        if o in va:
            ok = va[[o,u]].notna().all(1); m = np.full(len(va), np.nan)
            m[ok.values] = devig(va.loc[ok, o], va.loc[ok, u])[:, 0]; r[f'mou_{tag}'] = m
    # count markets
    for tgt, feat_tr, name in [('total_corners', None, 'corners'), ('total_cards', None, 'cards'), ('home_shots', None, 'hshots'), ('away_shots', None, 'ashots'),
                               ('home_shots_on_target', None, 'hsot'), ('away_shots_on_target', None, 'asot')]:
        trn = tr
        if name == 'corners':
            trn = df[df.season.isin(seasons[:i])]  # 12-season window not available in 8-season frame; documented
        mdl = market_models.train_lambda_regressor(trn[cols].fillna(0), trn[tgt])
        r[f'x_{name}'] = mdl.predict(va[cols].fillna(0)); r[f'a_{name}'] = va[tgt].values; r[f'n_{name}'] = trn[tgt].mean()
    # stronger naive for counts: avg of both teams' trailing-10 own rate + opp-allowed (simple, no model)
    r['t_corners'] = (va.home_last_10_corners_for + va.away_last_10_corners_for + va.home_last_10_corners_against + va.away_last_10_corners_against)/2
    r['t_cards'] = (va.home_last_10_cards_for + va.away_last_10_cards_for + va.home_last_10_cards_against + va.away_last_10_cards_against)/2
    r['t_hshots'] = (va.home_last_10_shots_for + va.away_last_10_shots_against)/2; r['t_ashots'] = (va.away_last_10_shots_for + va.home_last_10_shots_against)/2
    r['t_hsot'] = (va.home_last_10_shots_on_target_for + va.away_last_10_shots_on_target_against)/2; r['t_asot'] = (va.away_last_10_shots_on_target_for + va.home_last_10_shots_on_target_against)/2
    out.append(r); print(vs, 'done', flush=True)
R = pd.concat(out); R.to_pickle('pl_preds.pkl')
