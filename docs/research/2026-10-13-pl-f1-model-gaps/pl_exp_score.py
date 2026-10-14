"""Score each exp_pl_*.pkl vs exp_pl_base.pkl. Paired bootstrap by match, 2000 resamples. Ship rule (binding): primary-metric
improvement CI lower bound > 0 AND calibration gap (ECE / decile gap) not widened vs base."""
import sys, glob; sys.path.insert(0,'.')
from common import *
B = pd.read_pickle('exp_pl_base.pkl').set_index('mid'); R0 = pd.read_pickle('pl_preds.pkl').set_index('mid')
print('determinism check base vs pl_rank run: max|dp_over|=', float((B.p_over - R0.p_over.reindex(B.index)).abs().max()), ' max|dcorners|=', float((B.x_corners - R0.x_corners.reindex(B.index)).abs().max()))
y3 = B.ftr.map({'H':0,'D':1,'A':2}).values
def rps(P, y): O=np.eye(3)[y]; return ((np.cumsum(P,1)[:, :2]-np.cumsum(O,1)[:, :2])**2).sum(1)/2
def ece(p, o, k=10):
    p=np.asarray(p); o=np.asarray(o); b=np.clip((p*k).astype(int),0,k-1); return sum(abs(o[b==i].mean()-p[b==i].mean())*(b==i).mean() for i in range(k) if (b==i).any())
def dgap(pred, act, k=10):  # decile calibration gap for counts: weighted mean |mean pred - mean act|
    q = pd.qcut(pd.Series(np.asarray(pred)).rank(method='first'), k, labels=False).values; a=np.asarray(act); p=np.asarray(pred)
    return sum(abs(a[q==i].mean()-p[q==i].mean())*(q==i).mean() for i in range(k))
def metrics(R):
    ov=((R.goals_home+R.goals_away)>2.5).astype(float).values; bt=((R.goals_home>0)&(R.goals_away>0)).astype(float).values
    P=R[['p_h','p_d','p_a']].values
    return dict(ou=(R.p_over-ov)**2, btts=(R.p_btts-bt)**2, rps=rps(P,y3), corners=np.abs(R.x_corners-R.a_corners), cards=np.abs(R.x_cards-R.a_cards)), \
           dict(ou=ece(R.p_over,ov), btts=ece(R.p_btts,bt), rps=ece(R.p_h,(y3==0).astype(float)), corners=dgap(R.x_corners,R.a_corners), cards=dgap(R.x_cards,R.a_cards))
mb, cb = metrics(B)
PRIMARY = {'shotq':'ou','oppadj':'ou','ref_eb':'cards','sp_share':'corners','congestion':'ou','market_open':'ou','absence':'ou'}
rows=[]
for f in sorted(glob.glob('exp_pl_*.pkl')):
    v=f[7:-4]
    if v=='base': continue
    R=pd.read_pickle(f).set_index('mid').loc[B.index]; mv, cv = metrics(R)
    for m in ['ou','btts','rps','corners','cards']:
        d,lo,hi = boot_ci((mb[m]-mv[m]).values if hasattr(mb[m],'values') else mb[m]-mv[m])
        rows.append(dict(variant=v, metric=m, primary=(PRIMARY[v]==m), base=float(np.mean(mb[m])), cand=float(np.mean(mv[m])), improvement=d, lo=lo, hi=hi, ece_base=cb[m], ece_cand=cv[m], ece_widened=cv[m]>cb[m]))
S=pd.DataFrame(rows)
S['verdict']=np.where(S.primary, np.where((S.lo>0)&(~S.ece_widened),'SHIP-ELIGIBLE',np.where(S.hi<0,'does not ship (worse)','does not ship')),'')
pd.set_option('display.width',250); print(S.round(5).to_string()); S.to_csv('pl_exp_results.csv',index=False)
