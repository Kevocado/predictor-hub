"""Derive NEW pre-kickoff NFL features from pbp already on disk. Output: nfl/newfeat_team.parquet, nfl/newfeat_player.parquet.
Every team feature for game g is a mean over that team's previous ROLL games (shift(1)), carrying across seasons."""
import pandas as pd, numpy as np, glob
ROLL=6
cols=['season','week','season_type','game_id','posteam','defteam','epa','qb_dropback','sack','pass','rush','wp','down','qtr','yardline_100','play_type','qb_hit']
p=pd.concat([pd.read_parquet(f,columns=cols) for f in sorted(glob.glob('nfl/cache/nflverse/pbp_20*.parquet'))],ignore_index=True)
p=p[p.posteam.notna()&p.defteam.notna()&(p.season_type.isin(['REG','POST']))]
db=p[(p.qb_dropback==1)&p.epa.notna()]
ru=p[(p['rush']==1)&p.epa.notna()&(p.play_type=='run')]
neutral=p[(p.down.isin([1,2]))&(p.wp.between(0.2,0.8))&(p.qtr<=3)&(p.play_type.isin(['pass','run']))]
rz=p[(p.yardline_100<=20)&(p.play_type.isin(['pass','run']))]
k=['season','week','game_id']
def g(df,side,name,col):
    return df.groupby(k+[side])[col].mean().rename(name).rename_axis(k+['team'])
rz=rz.assign(is_pass=(rz.play_type=='pass').astype(float))
parts_off=[g(db,'posteam','off_pass_epa','epa'), g(ru,'posteam','off_rush_epa','epa'),
  g(db,'posteam','off_sack_rate','sack'), g(neutral,'posteam','off_neutral_pass_rate','pass'),
  g(rz,'posteam','off_rz_pass_rate','is_pass')]
plays=p[p.play_type.isin(['pass','run'])].groupby(k+['posteam']).size().rename('off_plays').rename_axis(k+['team'])
plays_d=p[p.play_type.isin(['pass','run'])].groupby(k+['defteam']).size().rename('def_plays').rename_axis(k+['team'])
parts_off.append(plays)
parts_def=[plays_d, g(db,'defteam','def_pass_epa','epa'), g(ru,'defteam','def_rush_epa','epa'),
  g(db,'defteam','def_sack_rate','sack'), g(db,'defteam','def_qbhit_rate','qb_hit')]
T=pd.concat(parts_off+parts_def,axis=1).reset_index().sort_values(['team','season','week'])
feat=[c for c in T.columns if c.startswith(('off_','def_'))]
for c in feat:
    T[c+'_roll']=T.groupby('team')[c].transform(lambda s:s.shift(1).rolling(ROLL,min_periods=2).mean())
T=T[['season','week','team']+[c+'_roll' for c in feat]].drop_duplicates(['season','week','team'])
T.to_parquet('nfl/newfeat_team.parquet',index=False)
# player practice status
inj=pd.concat([pd.read_parquet(f) for f in sorted(glob.glob('nfl/cache/nflverse/injuries_20*.parquet'))])
m={'Full Participation in Practice':0,'Limited Participation in Practice':1,'Did Not Participate In Practice':2}
inj['practice_ord']=inj.practice_status.map(m)
pl=inj.dropna(subset=['practice_ord']).groupby(['gsis_id','season','week'],as_index=False)['practice_ord'].max().rename(columns={'gsis_id':'player_id'})
pl.to_parquet('nfl/newfeat_player.parquet',index=False)
print(T.shape,pl.shape); print(T.describe().T[['count','mean','std']])
