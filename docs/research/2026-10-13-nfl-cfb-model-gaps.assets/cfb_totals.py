"""CFB total_points: unused-CFBD blocks (and union) with total-calibration. CFB repo root, PYTHONPATH=src:stubs."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0,'/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w')
import cfb_eval as ce
from cfb_predictor.tools import block_eval as be
from cfb_predictor.evaluate import walk_forward as wf
def tgap(pred,act,b=5):
    q=np.quantile(pred,np.linspace(0,1,b+1)); i=np.clip(np.searchsorted(q,pred,side='right')-1,0,b-1)
    return max(abs((pred[i==k]-act[i==k]).mean()) for k in range(b) if (i==k).any())
def boot_gap(pa,pb,y,n=300,seed=1):
    rng=np.random.default_rng(seed); N=len(y); d=[]
    for _ in range(n):
        i=rng.integers(0,N,N); d.append(tgap(pb[i],y[i])-tgap(pa[i],y[i]))
    d=np.array(d); return float(d.mean()),float(np.percentile(d,2.5)),float(np.percentile(d,97.5))
games_df,aux=be.load_recent_cfb_data(2014,2025); games_df['game_id']=games_df['game_id'].astype(str)
T=ce.team_ewm_table(games_df,ce.raw_rows(range(2014,2026))); g2=ce.add_cols(games_df,T)
def tot(cols):
    folds=wf.prepare_folds(g2); P=[];A=[];Y=[]
    for f in folds:
        f['feature_cols']=list(f['feature_cols'])+cols
        for d in ('train_df','val_df'): f[d]=f[d].copy(); f[d][cols]=f[d][cols].fillna(0)
        P.append(wf._fit_predict('ridge',f['train_df'],f['val_df'],f['feature_cols'],'total_points')); A.append(f['val_df']['total_points'].to_numpy(float)); Y.append(f['val_df']['season'].to_numpy())
    return np.concatenate(P),np.concatenate(A),np.concatenate(Y)
pb,ya,sea=tot([]); eb=np.abs(pb-ya); print('base total MAE %.4f gap %.3f N=%d'%(eb.mean(),tgap(pb,ya),len(ya)))
U={'pace':ce.cols_for('pace'),'situational_success':ce.cols_for('situational_success'),'opp_adj_epa':ce.cols_for('opp_adj_epa')}
U['union_pace+sit+oppadj']=U['pace']+U['situational_success']+U['opp_adj_epa']
res=[]
for n,c in U.items():
    pc,_,_=tot(c); ec=np.abs(pc-ya); d=eb-ec; lo,hi=be.paired_bootstrap(eb,ec); gch=boot_gap(pb,pc,ya)
    per={int(s):float(d[sea==s].mean()) for s in np.unique(sea)}
    r=dict(set=n,mae_base=float(eb.mean()),mae_cand=float(ec.mean()),delta=float(d.mean()),ci=[lo,hi],gap_base=tgap(pb,ya),gap_cand=tgap(pc,ya),gapchg=gch,per_season=per,seasons_better=int(sum(v>0 for v in per.values())),n_seasons=len(per))
    print(json.dumps(r),flush=True); res.append(r)
json.dump(res,open('/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/cfb/totals.json','w'),indent=1)
