import json,glob,sys
sys.path.insert(0,'src')
import os; os.environ['ESPN_MIN_REQUEST_INTERVAL_SECONDS']='0'
from nba_predictor.pipeline import ingest
games=[]
for f in sorted(glob.glob('data/cache/espn/scoreboard_*.json')):
    games+=json.load(open(f))['games']
# cache-only enrich: no network
import nba_predictor.data.espn as espn
espn._fetch_json=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('network blocked'))
en=ingest.enrich_with_boxscores(games)
df=ingest.to_training_frame(en).sort_values(['game_date','game_id'])
print(len(df),df.game_date.min(),df.game_date.max(),list(df.columns))
json.dump(df.to_dict('records'),open('data/cache/training/games.json','w'))
