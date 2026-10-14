"""F1 qualifying model vs naive baselines, walk-forward val 2022..2026 (production session ranker, tuned params)."""
import sys; sys.path.insert(0,'.')
from f1_lib import *
import pandas as pd
from f1_predictor.data import jolpica
from f1_predictor.features import session_build
from f1_predictor.models import session_outcome
def _safe(fn):
    def w(*a,**k):
        try: return fn(*a,**k)
        except RuntimeError: return pd.DataFrame()
    return w
for n in ['fetch_race_results','fetch_qualifying','fetch_sprint_results']: setattr(jolpica,n,_safe(getattr(jolpica,n)))
df, cols = session_build.build_session_training_frame('qualifying', seasons=jolpica.default_seasons())
df = df.sort_values(['season','round']).reset_index(drop=True)
# naive: driver's own mean quali position over last 3 qualifying sessions (shifted), team mean same
df['q_form3'] = df.groupby('driver_id').quali_position.transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
spec = session_outcome.SESSION_SPECS['qualifying']
rows=[]
for vs in [2022,2023,2024,2025,2026]:
    tr=df[df.season<vs]; va=df[df.season==vs]
    rk=session_outcome.train_session_ranker(tr, cols, spec, hyperparams=RANK_P)
    for (s,r),g in va.groupby(['season','round']):
        g=g.reset_index(drop=True); sc=rk.predict(g[cols]); th=np.exp(sc-sc.max()); w,p,t,e=pl_probs(th)
        xp=pd.Series(-sc).rank().values  # ordinal predicted position
        q=g.quali_position.values
        def sp(a): return pd.Series(a).corr(pd.Series(q), method='spearman')
        el=(g.elo_pre_race.fillna(1500)+g.team_strength_pre_race.fillna(1500)).values
        fm=g.form_avg_position_3.fillna(10).values; qf=g.q_form3.fillna(10).values
        rows.append(dict(season=s,round=r,n=len(g),
            mae_x=np.abs(pd.Series(-sc).rank().values-q).mean(), mae_elo=np.abs(pd.Series(-el).rank().values-q).mean(), mae_formrace=np.abs(pd.Series(fm).rank().values-q).mean(), mae_qform=np.abs(pd.Series(qf).rank().values-q).mean(),
            sp_x=sp(-sc), sp_elo=sp(-el), sp_formrace=sp(fm), sp_qform=sp(qf),
            pole_x=int(q[np.argmax(sc)]==1), pole_elo=int(q[np.argmax(el)]==1), pole_qform=int(q[np.argmin(qf)]==1), pole_formrace=int(q[np.argmin(fm)]==1)))
Q=pd.DataFrame(rows); Q.to_csv('f1_quali_races.csv',index=False); print(len(Q),'races')
out=[]
for nm,a,b in [('MAE of predicted grid position','mae_x','mae_qform'),('MAE of predicted grid position','mae_x','mae_elo'),('MAE of predicted grid position','mae_x','mae_formrace'),
               ('Spearman (higher better)','sp_x','sp_qform'),('Spearman (higher better)','sp_x','sp_elo'),('pole hit-rate','pole_x','pole_qform'),('pole hit-rate','pole_x','pole_elo')]:
    if 'mae' in a: d=Q[b]-Q[a]
    else: d=Q[a]-Q[b]
    m,lo,hi=boot_ci(d.values); out.append(dict(metric=nm,model=a,baseline=b,model_val=Q[a].mean(),base_val=Q[b].mean(),improvement=m,lo=lo,hi=hi,sig='model better' if lo>0 else ('model WORSE' if hi<0 else 'tie')))
O=pd.DataFrame(out); pd.set_option('display.width',200); print(O.round(4).to_string()); O.to_csv('f1_quali_rank.csv',index=False)
