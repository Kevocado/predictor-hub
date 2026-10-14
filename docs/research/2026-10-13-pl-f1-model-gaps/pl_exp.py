"""Run one candidate-feature variant through the same 5 walk-forward folds as pl_rank.py. usage: python pl_exp.py VARIANT"""
import sys, json; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../PL_Predictor/src')
from pl_predictor.models import ml_scoreline, market_models
V = sys.argv[1]
df = pd.read_pickle('pl_frame.pkl').reset_index(drop=True); df['mid']=np.arange(len(df)); cols = json.load(open('pl_cols.json'))
N = pd.read_pickle('pl_newfeats.pkl').drop(columns=['d','team_home','team_away']); df = df.merge(N, on='mid', how='left')
extra = {
 'base': [],
 'shotq': [f'{s}_{c}_l10' for s in 'ha' for c in ['xgps','xgps_ag','npxg','npxg_ag','box','box_ag','big','big_ag']],
 'oppadj': ['lam_h','lam_a','lam_tot','h_att','h_def','a_att','a_def'],
 'ref_eb': ['ref_cards_eb','ref_fouls_eb','ref_home_bias_eb','ref_n'],
 'sp_share': [],  # already in frame, excluded from production set
 'congestion': ['games_last_14_days_home','games_last_14_days_away','european_fixture_last_4_days_home','european_fixture_last_4_days_away'],
 'market_open': ['mk_h','mk_d','mk_a','mk_over'],
 'absence': ['h_abs3','a_abs3','h_abs_min','a_abs_min'],
}
if V == 'sp_share': extra['sp_share'] = [c for c in df.columns if 'set_piece_xg_share' in c]
if V == 'absence': df = df.merge(pd.read_pickle('pl_absence.pkl'), on='mid', how='left')
ex = [c for c in extra[V] if c in df.columns]; assert len(ex) == len(extra[V]), (V, set(extra[V]) - set(ex))
cols_v = cols + ex; ml_cols = [c for c in cols_v if 'fouls' not in c]  # ex never contains 'fouls' except ref_fouls_eb -> keep explicitly
if V == 'ref_eb': ml_cols = [c for c in cols if 'fouls' not in c] + [c for c in ex if c != 'ref_fouls_eb'] + ['ref_fouls_eb']
seasons = sorted(df.season.unique()); out = []
for i in range(3, len(seasons)):
    vs = seasons[i]; tr = df[df.season.isin(seasons[:i])]; va = df[df.season == vs]
    hm, am = ml_scoreline.train_goal_regressors(tr[ml_cols].fillna(0), tr.goals_home, tr.goals_away)
    grids = ml_scoreline.predict_grids_batch(hm, am, va[ml_cols].fillna(0))
    r = va[['mid','season','goals_home','goals_away','ftr']].copy()
    r[['p_h','p_d','p_a']] = np.array([[g.home_win, g.draw, g.away_win] for g in grids]); po=[];pb_=[];ps=[]
    for g,(a,b) in zip(grids, zip(va.goals_home, va.goals_away)):
        M=np.asarray(g.grid); M=M/M.sum(); n=M.shape[0]; tot=np.add.outer(np.arange(n),np.arange(n))
        po.append(M[tot>2.5].sum()); pb_.append(M[1:,1:].sum()); ps.append(M[min(a,n-1),min(b,n-1)])
    r['p_over']=po; r['p_btts']=pb_; r['p_score']=ps
    for tgt,name in [('total_corners','corners'),('total_cards','cards')]:
        mdl = market_models.train_lambda_regressor(tr[cols_v].fillna(0), tr[tgt]); r[f'x_{name}']=mdl.predict(va[cols_v].fillna(0)); r[f'a_{name}']=va[tgt].values
    out.append(r); print(V, vs, 'done', flush=True)
pd.concat(out).to_pickle(f'exp_pl_{V}.pkl')
