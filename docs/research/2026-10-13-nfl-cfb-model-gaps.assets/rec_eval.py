import numpy as np, pandas as pd, sys
from nfl_predictor.models import receptions_zinb as rz
W='/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/nfl/'
f=pd.read_parquet(W+'frame.parquet')
def boot(d,n=2000):
    rng=np.random.default_rng(0); m=rng.choice(d,size=(n,len(d))).mean(1); return d.mean(),np.percentile(m,2.5),np.percentile(m,97.5)
for pos in (('WR','TE'),('RB',)):
    rows=f[f.position.isin(pos)&f.receptions.notna()&(f.week<=18)].sort_values(['player_id','season','week']).reset_index(drop=True)
    out=[]
    for s in (2022,2023,2024):
        tr,te=rows[rows.season<s],rows[rows.season==s]
        if tr.season.nunique()<5: continue
        fit=rz.fit_receptions_zinb(tr,tr.receptions); pi,mun,mu=rz._predict_parts(fit,te)
        out.append(pd.DataFrame({'a':te.receptions.values,'mu':mu,'naive':te.receptions_roll.values,'season':s}))
    o=pd.concat(out).dropna(); e=np.abs(o.mu-o.a); n=np.abs(o.naive-o.a); sq=(o.mu-o.a)**2; sqn=(o.naive-o.a)**2
    m,lo,hi=boot((n-e).values); m2,lo2,hi2=boot((sqn-sq).values)
    print(pos,f'N={len(o)} mu MAE {e.mean():.3f} naive(roll5) {n.mean():.3f} skill {m:+.3f} CI[{lo:+.3f},{hi:+.3f}] | MSE {sq.mean():.3f} naive {sqn.mean():.3f} skill {m2:+.3f} CI[{lo2:+.3f},{hi2:+.3f}]',flush=True)
