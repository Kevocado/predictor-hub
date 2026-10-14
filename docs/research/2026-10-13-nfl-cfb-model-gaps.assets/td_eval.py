"""QB passing TDs (Poisson) and anytime-TD (XGB classifier) walk-forward vs naive. NFL repo root, PYTHONPATH=src."""
import sys, numpy as np, pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score
from nfl_predictor.models import qb_passing_td as qt
from nfl_predictor.models.player_props import fit_anytime_td_classifier
from nfl_predictor.features.player_usage import ALL_PLAYER_FEATURE_COLUMNS, with_passing_tds_roll, anytime_td_actual
sys.path.insert(0,'.'); import importlib.util
spec=importlib.util.spec_from_file_location('pe','/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/player_eval.py'); pe=importlib.util.module_from_spec(spec); spec.loader.exec_module(pe)
SEASONS=list(range(2019,2026))
f=pe.load().sort_values(['player_id','season','week']).reset_index(drop=True)

def calgap(p,y,b=5):
    q=np.quantile(p,np.linspace(0,1,b+1)); i=np.clip(np.searchsorted(q,p,side='right')-1,0,b-1); return max(abs(p[i==k].mean()-y[i==k].mean()) for k in range(b) if (i==k).any())
def bci(d): return pe.boot_diff(np.asarray(d,float))

def qb():
    q=with_passing_tds_roll(f[(f.position=='QB')&f.passing_tds.notna()].copy())
    cols=qt.MU_FEATURE_COLUMNS+['passing_tds_roll']; q=q.dropna(subset=['passing_tds_roll']); q[cols]=q[cols].fillna(0)
    return q,cols
def run_qb(extra=()):
    q,cols=qb(); rows=[]
    for s in SEASONS:
        tr,va=q[q.season<s],q[q.season==s]
        if va.empty: continue
        fit=qt.fit_qb_passing_td_model(tr[cols+list(extra)],tr.passing_tds)
        mu=np.clip(fit['model'].predict(va[cols+list(extra)].fillna(0).to_numpy(float)),1e-6,None)
        rows.append(pd.DataFrame({'season':s,'y':va.passing_tds.values,'mu':mu,'mu_naive':tr.passing_tds.mean(),'mu_roll':np.clip(va.passing_tds_roll.values,0.1,None)}))
    return pd.concat(rows,ignore_index=True)
def nll(y,mu): return -stats.poisson.logpmf(y,mu)

def anytime(extra=()):
    d=f[f.position.isin(['QB','RB','WR','TE'])&f.rushing_tds.notna()&f.receiving_tds.notna()].copy()
    d['y']=anytime_td_actual(d.rushing_tds,d.receiving_tds).astype(int); cols=list(ALL_PLAYER_FEATURE_COLUMNS)+list(extra)
    rows=[]
    for s in SEASONS:
        tr,va=d[d.season<s],d[d.season==s]
        if va.empty: continue
        m=fit_anytime_td_classifier(tr[cols],tr.y); p=np.clip(m.predict_proba(va[cols].fillna(0))[:,1],1e-4,1-1e-4)
        base=tr.groupby('position').y.mean(); pn=va.position.map(base).values
        rows.append(pd.DataFrame({'season':s,'y':va.y.values,'p':p,'pn':pn,'pid':va.player_id.values,'wk':va.week.values}))
    return pd.concat(rows,ignore_index=True)
def ll(y,p): return -(y*np.log(p)+(1-y)*np.log(1-p))
if __name__=='__main__':
    r=run_qb(); print('== QB passing TDs, Poisson on 4 feats, walk-forward 2019-2025 N=%d'%len(r))
    m=nll(r.y,r.mu); n=nll(r.y,r.mu_naive); n2=nll(r.y,r.mu_roll)
    print(f' NLL model {m.mean():.4f} | naive(train mean) {n.mean():.4f} skill {bci(n-m)[0]:+.4f} CI[{bci(n-m)[1]:+.4f},{bci(n-m)[2]:+.4f}] | naive(own rolling mean) {n2.mean():.4f} skill {bci(n2-m)[0]:+.4f} CI[{bci(n2-m)[1]:+.4f},{bci(n2-m)[2]:+.4f}]')
    mae=np.abs(r.mu-r.y); maen=np.abs(r.mu_naive-r.y); print(f' MAE(mean) model {mae.mean():.4f} naive {maen.mean():.4f} skill {bci(maen-mae)[0]:+.4f} CI[{bci(maen-mae)[1]:+.4f},{bci(maen-mae)[2]:+.4f}]')
    p2=1-stats.poisson.cdf(1,r.mu.values); y2=(r.y>=2).astype(float).values; print(f' P(>=2 TD) 5-bucket max gap {calgap(p2,y2):.3f}')
    a=anytime(); print('== anytime TD (rush+rec>0), XGB 14 feats, QB/RB/WR/TE, 2019-2025 N=%d base rate %.3f'%(len(a),a.y.mean()))
    m=ll(a.y.values,a.p.values); n=ll(a.y.values,a.pn.values); print(f' logloss model {m.mean():.4f} naive(position base rate) {n.mean():.4f} skill {bci(n-m)[0]:+.4f} CI[{bci(n-m)[1]:+.4f},{bci(n-m)[2]:+.4f}]; AUC {roc_auc_score(a.y,a.p):.4f} (naive pos-rate AUC {roc_auc_score(a.y,a.pn):.4f}); gap5 {calgap(a.p.values,a.y.values.astype(float)):.3f}')
    a.to_parquet(pe.W+'anytime_base.parquet'); r.to_parquet(pe.W+'qbtd_base.parquet')
