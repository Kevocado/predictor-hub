"""Empirical-Bayes shrunk per-90 shots/SoT rate, evaluated INSIDE the evaluation tool only (no serving change).
Reuses player_shots_backtest's data loaders; compares against the PL#65 tool's own naive baselines
(position-average x exp minutes, player's own trailing per-90 x exp minutes) and the production predictor, same rows.
usage: python pl_shots_eb.py shots_bt.csv"""
import sys, os, pickle; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../PL_Predictor/src')
from pathlib import Path
from pl_predictor.evaluate import player_shots_backtest as bt
from pl_predictor.data.team_names import to_canonical
cache = Path('../PL_Predictor/data/cache')
if os.path.exists('fpl_attached.pkl'): fpl = pickle.load(open('fpl_attached.pkl','rb'))
else:
    us = bt.load_shots(cache); fpl = {}
    for s in bt.SEASON_FILES:
        d = pd.read_csv(cache/'fpl_history'/f'{s}.csv'); d['season'] = s; d['team'] = d['team'].map(lambda t: to_canonical(t, source='fpl'))
        fpl[s], cov = bt.attach_shots(d, us); print(s, 'matched share', round(cov,3), flush=True)
    pickle.dump(fpl, open('fpl_attached.pkl','wb'))
A = pd.concat(fpl.values(), ignore_index=True)
A = A[A.minutes > 0].copy(); A['kt'] = pd.to_datetime(A.kickoff_time); A['date'] = A.kt.dt.date.astype(str)
A['position'] = A.position.replace({'AM':'MID'}); A['key'] = A.name.map(bt._norm)
A = A.sort_values(['key','kt']).reset_index(drop=True)
g = A.groupby(['key','season'])
for c in ['shots','shots_on_target','minutes']:
    A[f'cur_{c}'] = g[c].cumsum() - A[c]     # strictly before this appearance, same season
tot = A.groupby(['key','season'])[['shots','shots_on_target','minutes']].sum().reset_index()
order = bt.SEASON_FILES; prev = {s: (order[order.index(s)-1] if order.index(s) else None) for s in order}
tot['season_next'] = tot.season.map(lambda s: next((o for o in order if prev[o]==s), None))
P = tot.dropna(subset=['season_next']).rename(columns={'shots':'prev_shots','shots_on_target':'prev_sot','minutes':'prev_min'})[['key','season_next','prev_shots','prev_sot','prev_min']].rename(columns={'season_next':'season'})
A = A.merge(P, on=['key','season'], how='left'); A[['prev_shots','prev_sot','prev_min']] = A[['prev_shots','prev_sot','prev_min']].fillna(0)
def posavg(train_seasons, col):
    t = A[A.season.isin(train_seasons)]; return t.groupby('position').apply(lambda x: x[col].sum()/x.minutes.sum()*90, include_groups=False)
def eb_rate(D, col, k, pa, prior_min_floor=450, shrink_prior=False):
    cur_x, cur_m = D[f'cur_{col}'], D['cur_minutes']; pos = D.position.map(pa)
    prev_x = D['prev_shots'] if col=='shots' else D['prev_sot']; prev_rate = prev_x/D.prev_min.clip(lower=1)*90
    if shrink_prior: prev_rate = (prev_x + k*(D.prev_min/90 >= 0)*0 + k*pos*D.prev_min/D.prev_min.clip(lower=1)*0 + 0)  # placeholder, unused
    prior = np.where(D.prev_min >= prior_min_floor, prev_rate, pos)
    n90 = cur_m/90
    return (cur_x + k*prior)/(n90 + k)       # shots-per-90; (n90*player_rate + k*prior)/(n90+k)
KS = [0.5,1,2,3,5,8,12,20,40]
def fit_k(train_seasons, col):
    pa = posavg([s for s in train_seasons], col); D = A[A.season.isin(train_seasons[1:])]   # first train season only seeds history
    pa = posavg(train_seasons, col); best = None
    for k in KS:
        e = ((eb_rate(D, col, k, pa)*np.minimum(D.minutes,90)/90 - D[col])**2).mean()
        if best is None or e < best[1]: best = (k, e)
    return best[0]
R = pd.read_csv(sys.argv[1]); R['date'] = R.date.astype(str)
out = []
for s in sorted(R.season.unique()):
    tr = order[max(0,order.index(s)-4):order.index(s)]; r = R[R.season==s]
    D = A[A.season==s][['element','date','cur_shots','cur_shots_on_target','cur_minutes','prev_shots','prev_sot','prev_min']]
    r = r.merge(D, on=['element','date'], how='left', suffixes=('','_d')); r = r.merge(A[A.season==s][['element','date','position']].drop_duplicates(['element','date']).rename(columns={'position':'pos2'}), on=['element','date'], how='left')
    r['key'] = 0
    ks = {c: fit_k(order[:order.index(s)], c) for c in ['shots','shots_on_target']}
    print(s, 'fitted k (shots, SoT):', ks, flush=True)
    for col, kk, tag in [('shots','shots','eb_shots'),('shots_on_target','shots_on_target','eb_sot')]:
        pa = posavg(order[:order.index(s)], col); Dm = r.assign(position=r.pos2.fillna(r.position))
        rate = eb_rate(Dm, col, ks[kk], pa)
        r[tag] = rate*np.minimum(r.exp_minutes,90)/90; r[tag+'_om'] = rate*np.minimum(r.minutes,90)/90
        r['k_'+col] = ks[kk]
    out.append(r)
R2 = pd.concat(out, ignore_index=True); R2.to_csv('shots_eb_rows.csv', index=False)
R2['match'] = R2.team + '|' + R2.date
print('rows', len(R2), 'missing eb', R2.eb_shots.isna().mean())
def mae(c, y): return (R2[c]-R2[y]).abs()
res = []
for tgt, y, eb, base in [('shots','shots','eb_shots',{'position_avg':'posavg_shots','own_trailing_per90':'own_shots','production_model':'pm_shots'}),
                         ('SoT','sot','eb_sot',{'position_avg':'posavg_sot','own_trailing_per90':'own_sot','production_model':'pm_sot'})]:
    print(f'\n=== {tgt} ===  EB mean pred {R2[eb].mean():.3f}  actual {R2[y].mean():.3f}  exact-zero share EB {(R2[eb]<1e-9).mean():.3f}  corr {np.corrcoef(R2[eb],R2[y])[0,1]:.3f}')
    for nm, c in {**{'EB':eb}, **base}.items():
        e = R2[c]-R2[y]; print(f'{nm:20s} MAE {e.abs().mean():.4f} RMSE {np.sqrt((e**2).mean()):.4f} NLL {bt.pois_ll(R2[y].values, R2[c].values).mean():.4f} mean pred {R2[c].mean():.3f} zero-share {(R2[c]<1e-9).mean():.3f}')
    for nm, c in base.items():
        for lname, fn in [('abs err', lambda p: (p-R2[y]).abs()), ('sq err', lambda p: (p-R2[y])**2), ('NLL', lambda p: pd.Series(bt.pois_ll(R2[y].values, p.values)))]:
            m, lo, hi = bt.boot_diff(fn(R2[eb]), fn(R2[c]), R2.match)
            res.append(dict(target=tgt, baseline=nm, metric=lname, eb_minus_base=m, lo=lo, hi=hi, verdict='EB better' if hi<0 else ('EB worse' if lo>0 else 'tie')))
yb = (R2.sot>=1).astype(float).values
for nm, c in {'EB':'eb_sot','position_avg':'posavg_sot','own_trailing_per90':'own_sot','production_model':'pm_sot'}.items():
    p = 1-np.exp(-R2[c].values); b, l = bt.prob_losses(yb, p); print(f'P(SoT>=1) {nm:20s} Brier {b.mean():.4f} logloss {l.mean():.4f} mean p {p.mean():.3f}')
for nm, c in {'position_avg':'posavg_sot','own_trailing_per90':'own_sot','production_model':'pm_sot'}.items():
    for i, mname in enumerate(['Brier','logloss']):
        m, lo, hi = bt.boot_diff(bt.prob_losses(yb, 1-np.exp(-R2.eb_sot.values))[i], bt.prob_losses(yb, 1-np.exp(-R2[c].values))[i], R2.match)
        res.append(dict(target='P(SoT>=1)', baseline=nm, metric=mname, eb_minus_base=m, lo=lo, hi=hi, verdict='EB better' if hi<0 else ('EB worse' if lo>0 else 'tie')))
S = pd.DataFrame(res); pd.set_option('display.width',200); print(S.round(4).to_string()); S.to_csv('shots_eb_results.csv', index=False)
# calibration by decile + by experience
R2['dec'] = pd.qcut(R2.eb_shots.rank(method='first'), 10, labels=False)
print(R2.groupby('dec').agg(pred=('eb_shots','mean'), actual=('shots','mean'), n=('shots','size')).round(3).T.to_string())
R2['exp'] = pd.cut(R2.games_before, [-1,0,4,9,99], labels=['0','1-4','5-9','10+'])
print(R2.groupby('exp', observed=True).apply(lambda g: pd.Series({'n':len(g),'eb_mae':(g.eb_shots-g.shots).abs().mean(),'posavg_mae':(g.posavg_shots-g.shots).abs().mean(),'own_mae':(g.own_shots-g.shots).abs().mean(),'eb_pred':g.eb_shots.mean(),'actual':g.shots.mean()}), include_groups=False).round(3).to_string())
