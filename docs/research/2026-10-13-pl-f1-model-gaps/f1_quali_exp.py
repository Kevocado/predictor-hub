"""Qualifying ranker + candidate features (walk-forward val 2022-2026). Primary: per-race MAE of predicted grid position.
Calibration: ECE of pole probability (Plackett-Luce) must not widen. Same ship rule."""
import sys; sys.path.insert(0,'.')
from f1_lib import *
from f1_predictor.data import jolpica
from f1_predictor.features import session_build
from f1_predictor.models import session_outcome
def _safe(fn):
    def w(*a,**k):
        try: return fn(*a,**k)
        except RuntimeError: return pd.DataFrame()
    return w
for n in ['fetch_race_results','fetch_qualifying','fetch_sprint_results']: setattr(jolpica,n,_safe(getattr(jolpica,n)))
df,cols=session_build.build_session_training_frame('qualifying',seasons=jolpica.default_seasons())
N=pd.read_pickle('f1_newfeats.pkl'); df=df.merge(N,on=['season','round','driver_id'],how='left').sort_values(['season','round']).reset_index(drop=True)
spec=session_outcome.SESSION_SPECS['qualifying']
V={'base':[],'qform':['qf3','qf5','qgapf5'],'teammate':['tm_qgap5'],'pace':['pace5'],'qform+teammate':['qf3','qf5','qgapf5','tm_qgap5']}
res={}
for v,ex in V.items():
    c=cols+ex; rows=[]
    for vs in [2022,2023,2024,2025,2026]:
        tr=df[df.season<vs]; va=df[df.season==vs]; rk=session_outcome.train_session_ranker(tr,c,spec,hyperparams=RANK_P)
        for (s,r),g in va.groupby(['season','round']):
            g=g.reset_index(drop=True); sc=rk.predict(g[c]); w,p,t,e=pl_probs(np.exp(sc-sc.max())); q=g.quali_position.values
            rows.append(pd.DataFrame(dict(season=s,round=r,mae=np.abs(pd.Series(-sc).rank().values-q),pole=(q==1).astype(int),p_pole=w,top3=(q<=3).astype(int),p_top3=p,sp=pd.Series(-sc).corr(pd.Series(q),method='spearman'))))
    res[v]=pd.concat(rows,ignore_index=True); print(v,'done',flush=True)
def pr(R,col): return R.groupby(['season','round'])[col].mean()
out=[]
b=res['base']
for v in V:
    if v=='base': continue
    R=res[v]; m,lo,hi=boot_ci((pr(b,'mae')-pr(R,'mae')).values); e0=ece(b.p_pole,b.pole); e1=ece(R.p_pole,R.pole)
    m2,lo2,hi2=boot_ci((race_sum(b,ll(b.pole.values,b.p_pole.values))-race_sum(R,ll(R.pole.values,R.p_pole.values))).values)
    out.append(dict(variant=v,base_mae=pr(b,'mae').mean(),cand_mae=pr(R,'mae').mean(),improvement=m,lo=lo,hi=hi,pole_ll_improvement=m2,pole_lo=lo2,pole_hi=hi2,ece_pole_base=e0,ece_pole_cand=e1,ece_widened=e1>e0,verdict='SHIP-ELIGIBLE' if (lo>0 and e1<=e0) else 'does not ship'))
S=pd.DataFrame(out); pd.set_option('display.width',250); print(S.round(4).to_string()); S.to_csv('f1_quali_exp_results.csv',index=False)
print('base MAE',pr(b,'mae').mean())
