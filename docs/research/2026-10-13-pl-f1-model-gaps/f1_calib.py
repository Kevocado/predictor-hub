"""F1 post-hoc calibration of the production ranker's scores: (a) scalar temperature T, (b) T plus log(grid) covariate,
both fitted ONLY on out-of-fold scores of earlier seasons (nested walk-forward). Not a new data feature; the ranker is unchanged."""
import sys; sys.path.insert(0,'.')
from f1_lib import *
from scipy.optimize import minimize
df=pd.read_pickle('f1_frame.pkl'); cols=json.load(open('f1_cols.json'))
TAG=sys.argv[1] if len(sys.argv)>1 else ''
if TAG=='qform':
    df=df.merge(pd.read_pickle('f1_newfeats.pkl'),on=['season','round','driver_id'],how='left'); cols=cols+['qf3','qf5','qgapf5','conv5']
Q=df[df.tier==session_state.TIER_POST_QUALIFYING]
def scores_for(u):
    tr=Q[Q.season<u]; va=Q[Q.season==u]; rk=race_outcome.train_ranker(tr,cols,hyperparams=RANK_P)
    o=va[['season','round','driver_id','grid','position']].copy(); o['s']=rk.predict(va[cols]); o['win']=(o.position==1).astype(int); o['lg']=np.log(o.grid.fillna(20).clip(1,20)); return o
OOF={u:scores_for(u) for u in [2020,2021,2022,2023,2024,2025,2026]}
def nll(par, O, use_grid):
    T=par[0]; a=par[1] if use_grid else 0.0; tot=0; n=0
    for _,g in O.groupby(['season','round']):
        z=T*g.s.values - a*g.lg.values; z=z-z.max(); lp=z-np.log(np.exp(z).sum()); w=g.win.values
        if w.sum()==1: tot-=lp[w==1][0]; n+=1
    return tot/n
rows=[]
for v in [2022,2023,2024,2025,2026]:
    inner=pd.concat([OOF[u] for u in range(2020,v)]); 
    fits={}
    for nm,ug in [('T',False),('T+grid',True)]:
        r=minimize(nll,x0=[1.0,0.0] if ug else [1.0],args=(inner,ug),method='Nelder-Mead' if ug else 'Nelder-Mead'); fits[nm]=r.x
    print(v,'fitted',{k:np.round(x,3).tolist() for k,x in fits.items()},'inner races',inner.groupby(['season','round']).ngroups,flush=True)
    va=OOF[v]
    for (s,r_),g in va.groupby(['season','round']):
        out=dict(season=s,round=r_,driver_id=g.driver_id.values,win=g.win.values,pod=(g.position<=3).astype(int).values,top10=(g.position<=10).astype(int).values)
        for nm,ug in [('T',False),('T+grid',True),('raw',None)]:
            T=1.0 if nm=='raw' else fits[nm][0]; a=fits[nm][1] if ug else 0.0
            z=T*g.s.values-a*g.lg.values; th=np.exp(z-z.max()); w,p,t,e=pl_probs(th); out[f'{nm}_w']=w; out[f'{nm}_p']=p; out[f'{nm}_t']=t
        rows.append(pd.DataFrame(out))
R=pd.concat(rows,ignore_index=True)
# grid naive from base preds for comparison
B=pd.read_pickle('f1_preds.pkl')[['season','round','driver_id','g_w','g_p','g_t']]; R=R.merge(B,on=['season','round','driver_id'])
R.to_pickle(f'exp_f1_calib{TAG}.pkl')
out=[]
for nm in ['T','T+grid']:
    for y,sfx,lab in [('win','w','win logloss'),('pod','p','podium logloss'),('top10','t','top10 logloss')]:
        for ref,rl in [('raw','production raw'),('g','grid-position naive')]:
            m,lo,hi=boot_ci((race_sum(R,ll(R[y].values,R[f'{ref}_{sfx}'].values))-race_sum(R,ll(R[y].values,R[f'{nm}_{sfx}'].values))).values)
            out.append(dict(candidate=nm,metric=lab,vs=rl,base=race_sum(R,ll(R[y].values,R[f'{ref}_{sfx}'].values)).mean(),cand=race_sum(R,ll(R[y].values,R[f'{nm}_{sfx}'].values)).mean(),improvement=m,lo=lo,hi=hi,
                            ece_base=ece(R[f'{ref}_{sfx}'],R[y]),ece_cand=ece(R[f'{nm}_{sfx}'],R[y])))
S=pd.DataFrame(out); S['verdict']=np.where((S.lo>0)&(S.ece_cand<=S.ece_base),'meets bar','does not meet bar'); pd.set_option('display.width',250); print(S.round(5).to_string()); S.to_csv(f'f1_calib{TAG}_results.csv',index=False)
