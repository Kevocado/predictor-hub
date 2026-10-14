import sys, glob; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../PL_Predictor/src')
from pl_predictor.data.team_names import to_canonical
df=pd.read_pickle('pl_frame.pkl').reset_index(drop=True); df['mid']=np.arange(len(df)); df['d']=pd.to_datetime(df.date).dt.normalize()
fp=pd.concat([pd.read_csv(f,low_memory=False).assign(season=f[-11:-4]) for f in sorted(glob.glob('../PL_Predictor/data/cache/fpl_history/202[0-5]-*.csv'))])
fp['team']=fp.team.map(lambda t:to_canonical(t,source='fpl')); fp['d']=pd.to_datetime(fp.kickoff_time,utc=True).dt.tz_localize(None).dt.normalize()
rows=[]
for (season,team),g in fp.groupby(['season','team']):
    dates=sorted(g.d.unique()); piv=g.pivot_table(index='d',columns='element',values='minutes',aggfunc='sum').reindex(dates).fillna(0)
    M=piv.values
    for t,d in enumerate(dates):
        if t<5: continue   # need history
        lo=max(0,t-10); core_blk=M[lo:t-3] if t-3>lo else M[lo:t]; recent=M[max(t-3,0):t]
        if len(core_blk)==0: continue
        avg=core_blk.mean(0); core=np.argsort(-avg)[:11]
        exp_min=avg[core]*len(recent); got=recent[:,core].sum(0)
        rows.append(dict(team=team,d=d,abs_min=float(1-min(got.sum()/max(exp_min.sum(),1e-9),1)), abs3=float((M[t-1,core]==0).mean())))
A=pd.DataFrame(rows)
H=A.rename(columns={'team':'team_home','abs_min':'h_abs_min','abs3':'h_abs3'}); W=A.rename(columns={'team':'team_away','abs_min':'a_abs_min','abs3':'a_abs3'})
X=df[['mid','d','team_home','team_away']].merge(H,on=['team_home','d'],how='left').merge(W,on=['team_away','d'],how='left')
print('merge rate', X.h_abs_min.notna().mean(), X.a_abs_min.notna().mean(), X.groupby(df.season).h_abs_min.apply(lambda s:s.notna().mean()).round(2).to_dict())
X[['mid','h_abs3','a_abs3','h_abs_min','a_abs_min']].to_pickle('pl_absence.pkl'); print(X[['h_abs3','h_abs_min']].describe().round(3))
