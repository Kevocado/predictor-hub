"""Follow-up on EB shots: where does the low-decile miscalibration come from (rate vs expected-minutes)? And the plan's Task-5 gate table."""
import sys; sys.path.insert(0,'.')
from common import *
R=pd.read_csv('shots_eb_rows.csv'); R['match']=R.team+'|'+R.date
print('share of appearances with exp_minutes<5:', round((R.exp_minutes<5).mean(),3), ' mean actual minutes in that group:', round(R[R.exp_minutes<5].minutes.mean(),1), ' mean actual shots:', round(R[R.exp_minutes<5].shots.mean(),3))
for lab,c in [('EB (model exp. minutes)','eb_shots'),('EB (oracle minutes)','eb_shots_om'),('position_avg (oracle min)','posavg_shots_om'),('own_trailing (oracle min)','own_shots_om')]:
    e=R[c]-R.shots; print(f'{lab:28s} MAE {e.abs().mean():.4f} RMSE {np.sqrt((e**2).mean()):.4f} mean {R[c].mean():.3f}')
R['dec']=pd.qcut(R.eb_shots_om.rank(method='first'),10,labels=False)
print('oracle-minutes EB decile calibration'); print(R.groupby('dec').agg(pred=('eb_shots_om','mean'),actual=('shots','mean')).round(3).T.to_string())
R['dm']=pd.cut(R.exp_minutes,[-1,5,30,60,80,91],labels=['<5','5-30','30-60','60-80','80+'])
print(R.groupby('dm',observed=True).apply(lambda g:pd.Series({'n':len(g),'eb_pred':g.eb_shots.mean(),'posavg_pred':g.posavg_shots.mean(),'actual':g.shots.mean(),'act_min':g.minutes.mean()}),include_groups=False).round(3).to_string())
def bd(a,b):
    return bt_boot(a,b)
import importlib; 
sys.path.insert(0,'../PL_Predictor/src'); from pl_predictor.evaluate import player_shots_backtest as bt
rows=[]
for nm,eb,base in [('oracle minutes: shots vs position_avg','eb_shots_om','posavg_shots_om'),('oracle minutes: shots vs own_trailing','eb_shots_om','own_shots_om'),('oracle minutes: SoT vs position_avg','eb_sot_om','posavg_sot_om'),('oracle minutes: SoT vs own_trailing','eb_sot_om','own_sot_om')]:
    y='shots' if 'shots vs' in nm else 'sot'
    for ln,fn in [('abs err',lambda p:(p-R[y]).abs()),('sq err',lambda p:(p-R[y])**2)]:
        m,lo,hi=bt.boot_diff(fn(R[eb]),fn(R[base]),R.match); rows.append(dict(comparison=nm,metric=ln,eb_minus_base=m,lo=lo,hi=hi,verdict='EB better' if hi<0 else ('EB worse' if lo>0 else 'tie')))
S=pd.DataFrame(rows); print(S.round(4).to_string()); S.to_csv('shots_eb_oracle_results.csv',index=False)
# per-season consistency of the headline (shots abs err vs both baselines)
for s,g in R.groupby('season'):
    print(s, 'EB MAE %.4f posavg %.4f own %.4f | SoT EB %.4f posavg %.4f own %.4f'%((g.eb_shots-g.shots).abs().mean(),(g.posavg_shots-g.shots).abs().mean(),(g.own_shots-g.shots).abs().mean(),(g.eb_sot-g.sot).abs().mean(),(g.posavg_sot-g.sot).abs().mean(),(g.own_sot-g.sot).abs().mean()))
