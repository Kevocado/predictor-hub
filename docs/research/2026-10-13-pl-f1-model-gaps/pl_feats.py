"""Candidate PL features built only from on-disk caches, all strictly pre-match (shift(1) within team/referee).
Writes pl_newfeats.pkl keyed by the production frame's row id (mid)."""
import sys, glob, os; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../PL_Predictor/src')
from pl_predictor.data.team_names import to_canonical
C='../PL_Predictor/data/cache/'
df=pd.read_pickle('pl_frame.pkl').reset_index(drop=True); df['mid']=np.arange(len(df)); df['d']=pd.to_datetime(df.date).dt.normalize()
# ---------- understat shot-level -> team-match
rows=[]
for f in glob.glob(C+'understat_shots/[0-9]*.csv'):
    s=pd.read_csv(f)
    if s.empty: continue
    s=s[s.result!='OwnGoal']
    for ha,g in s.groupby('h_a'):
        team=g.team_home.iloc[0] if ha=='h' else g.team_away.iloc[0]
        opp=g.team_away.iloc[0] if ha=='h' else g.team_home.iloc[0]
        np_=g[g.situation!='Penalty']
        rows.append(dict(team=to_canonical(team,source='odds_api'),opp=to_canonical(opp,source='odds_api'),d=pd.to_datetime(g.date.iloc[0]).normalize(),
            xg=g.x_g.sum(),npxg=np_.x_g.sum(),shots=len(g),npshots=len(np_),op_xg=g[g.situation=='OpenPlay'].x_g.sum(),box=int((g.x>0.83).sum()),big=int((g.x_g>=0.3).sum())))
T=pd.DataFrame(rows)
# opponent's numbers = the "against" side
A=T.rename(columns={c:c+'_ag' for c in ['xg','npxg','shots','npshots','op_xg','box','big']}).rename(columns={'team':'opp','opp':'team'})
T=T.merge(A,on=['team','opp','d'],how='left').sort_values(['team','d']).reset_index(drop=True)
T['xgps']=T.npxg/T.npshots.clip(lower=1); T['xgps_ag']=T.npxg_ag/T.npshots_ag.clip(lower=1)
def roll(col,w): return T.groupby('team')[col].transform(lambda s:s.shift(1).rolling(w,min_periods=3).mean())
for w in (5,10):
    for c in ['xgps','xgps_ag','npxg','npxg_ag','box','box_ag','big','big_ag']: T[f'{c}_l{w}']=roll(c,w)
# shrunk trailing-20 attack/defence for opp-adjusted lambda
lg=T.groupby('d').npxg.mean().sort_index().expanding().mean().shift(1)  # league avg npxg per team-match, prior only
T['lgavg']=T.d.map(lg).fillna(1.2)
k=6
def shr(col):
    s=T.groupby('team')[col].transform(lambda x:x.shift(1).rolling(20,min_periods=1).sum()); n=T.groupby('team')[col].transform(lambda x:x.shift(1).rolling(20,min_periods=1).count())
    return ((s.fillna(0)+k*T.lgavg)/(n.fillna(0)+k))/T.lgavg
T['att']=shr('npxg'); T['def']=shr('npxg_ag')
newcols_team=[c for c in T.columns if c.endswith(('_l5','_l10'))]
H=T[['team','d','att','def']+newcols_team].add_prefix('h_'); H=H.rename(columns={'h_team':'team_home','h_d':'d'})
Aw=T[['team','d','att','def']+newcols_team].add_prefix('a_'); Aw=Aw.rename(columns={'a_team':'team_away','a_d':'d'})
X=df[['mid','d','team_home','team_away']].merge(H,on=['team_home','d'],how='left').merge(Aw,on=['team_away','d'],how='left')
print('understat merge rate home/away', X.h_att.notna().mean(), X.a_att.notna().mean())
# league-average npxg for the match (prior) to turn att/def into lambdas
X['lg']=X.d.map(lg).fillna(1.2)
X['lam_h']=X.lg*X.h_att*X.a_def; X['lam_a']=X.lg*X.a_att*X.h_def; X['lam_tot']=X.lam_h+X.lam_a
# ---------- referee EB
d2=df[['mid','d','referee','hf','af','hy','ay','hr','ar']].sort_values(['d','mid']).copy()
d2['cards']=d2.hy+d2.ay+d2.hr+d2.ar; d2['fouls']=d2.hf+d2.af; d2['hyc']=d2.hy+d2.hr; d2['ayc']=d2.ay+d2.ar
g=d2.groupby('referee')
for c in ['cards','fouls','hyc','ayc']:
    d2['_s']=g[c].transform(lambda s:s.shift(1).expanding().sum()); d2['_n']=g[c].transform(lambda s:s.shift(1).expanding().count())
    lgm=d2[c].shift(1).expanding().mean()
    d2[f'ref_{c}_eb']=((d2._s.fillna(0)+10*lgm)/(d2._n.fillna(0)+10))
d2['ref_home_bias_eb']=d2.ref_hyc_eb-d2.ref_ayc_eb; d2['ref_n']=d2._n.fillna(0)
X=X.merge(d2[['mid','ref_cards_eb','ref_fouls_eb','ref_home_bias_eb','ref_n']],on='mid',how='left')
# ---------- market-implied opening probs
def dv(a,b,c=None):
    o=np.array([a,b] if c is None else [a,b,c],float).T; p=1/o; return p/p.sum(1,keepdims=True)
m=dv(df.b365_h,df.b365_d,df.b365_a); X['mk_h'],X['mk_d'],X['mk_a']=m[:,0],m[:,1],m[:,2]
X['mk_over']=np.where(df['b365>2.5'].notna(),dv(df['b365>2.5'].fillna(2),df['b365<2.5'].fillna(2))[:,0],np.nan)
X.to_pickle('pl_newfeats.pkl'); print(X.describe().T[['count','mean']].round(3).to_string())
