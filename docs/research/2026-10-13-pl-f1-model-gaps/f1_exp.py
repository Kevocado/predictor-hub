"""F1 candidate features through the production walk-forward (val 2022-2026, POST_QUALIFYING tier, tuned ranker/DNF params).
Ship rule (binding): primary-metric paired-bootstrap (over races) improvement CI lower bound > 0 AND ECE not widened."""
import sys; sys.path.insert(0,'.')
from f1_lib import *
df=pd.read_pickle('f1_frame.pkl'); cols=json.load(open('f1_cols.json'))
N=pd.read_pickle('f1_newfeats.pkl'); df=df.merge(N,on=['season','round','driver_id'],how='left')
V={'qform':['qf3','qf5','qgapf5','conv5'],'teammate':['tm_form5','tm_qgap5'],'reliability':['con_mech20','con_circ_mech_eb'],'wet_x':['wet','wet_skill','wet_x'],'pace':['pace5'],'sc_proxy':['circ_lapped','circ_coll']}
PRIM={'qform':'win','teammate':'win','reliability':'dnf','wet_x':'win','pace':'win','sc_proxy':'dnf'}
VAL=[2022,2023,2024,2025,2026]
base=run(df,cols,VAL,with_dnf=True)
res={}
rows=[]
def per_race(R,c,y): return race_sum(R,ll(R[y].values,R[c].values))
bw=per_race(base,'x_w','win'); bp=per_race(base,'x_p','pod'); bd=per_race(base,'x_dnf','dnf')
bt=per_race(base,'x_t','top10')
for v,ex in V.items():
    R=run(df,cols+ex,VAL,with_dnf=True,dnf_cols=cols+ex); R.to_pickle(f'exp_f1_{v}.pkl')
    for nm,c,y,b,e0 in [('win logloss','x_w','win',bw,ece(base.x_w,base.win)),('podium logloss','x_p','pod',bp,ece(base.x_p,base.pod)),('top10 logloss','x_t','top10',bt,ece(base.x_t,base.top10)),('DNF logloss','x_dnf','dnf',bd,ece(base.x_dnf,base.dnf))]:
        m,lo,hi=boot_ci((b-per_race(R,c,y)).values); e1=ece(R[c],R[y])
        rows.append(dict(variant=v,metric=nm,primary=(nm.startswith(PRIM[v])),base=b.mean(),cand=per_race(R,c,y).mean(),improvement=m,lo=lo,hi=hi,ece_base=e0,ece_cand=e1,ece_widened=e1>e0))
    print(v,'done',flush=True)
S=pd.DataFrame(rows); S['verdict']=np.where(S.primary,np.where((S.lo>0)&(~S.ece_widened),'SHIP-ELIGIBLE',np.where(S.hi<0,'does not ship (worse)','does not ship')),'')
pd.set_option('display.width',250); print(S.round(5).to_string()); S.to_csv('f1_exp_results.csv',index=False); base.to_pickle('exp_f1_base.pkl')
