"""direct classifier vs own-trailing-rate Poisson union (the stronger naive), paired bootstrap by team-match, from pl_player_preds.pkl"""
import sys; sys.path.insert(0,'.')
from common import *
R=pd.read_pickle('pl_player_preds.pkl'); rows=[]
for t in R.target.unique():
    D=R[R.target==t]; u=D[D.model=='union_platt'].reset_index(drop=True); d=D[D.model=='direct'].reset_index(drop=True)
    for m in ['brier','ll']:
        a,lo,hi=boot_ci((u[m]-d[m]).values,groups=d.mid.values); rows.append(dict(target=t,metric=m,direct=d[m].mean(),union=u[m].mean(),improvement=a,lo=lo,hi=hi,skill_pct=100*a/u[m].mean()))
S=pd.DataFrame(rows); print(S.round(4).to_string()); S.to_csv('pl_player_rank2.csv',index=False)
print(R.groupby(['target','model']).season.unique().head(3))
