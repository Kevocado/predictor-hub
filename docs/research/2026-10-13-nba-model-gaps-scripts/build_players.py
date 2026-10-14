import json,glob,sys,os
sys.path.insert(0,'src')
import pandas as pd
from nba_predictor.pipeline import ingest
games=[]
for f in sorted(glob.glob('data/cache/espn/scoreboard_*.json')): games+=json.load(open(f))['games']
games=[g for g in games if g['completed']]
pb={}
for f in glob.glob('data/cache/espn/player_boxscore_*.json'):
    gid=f.split('_')[-1][:-5]; pb[gid]=json.load(open(f))['rows']
df=ingest.to_player_training_frame(games,pb)
# also fta / 3pa which the frame drops
rows=[]
for gid,rs in pb.items():
    for r in rs:
        a=lambda s:ingest._parse_made_attempted(s)
        rows.append((gid,r['player_id'],a(r['three_made_attempted'])[1],a(r['ft_made_attempted'])[0],a(r['ft_made_attempted'])[1]))
ex=pd.DataFrame(rows,columns=['game_id','player_id','fg3a','ftm','fta'])
df=df.merge(ex,on=['game_id','player_id'],how='left')
df.to_pickle('../players.pkl')
print(len(df),df.player_id.nunique(),df.game_id.nunique(),df.game_date.min(),df.game_date.max())
print(df.describe().T[['count','mean','50%','max']])
print(df.position.value_counts(dropna=False))
print((df.minutes==0).sum(),'zero-minute rows (DNP)')
