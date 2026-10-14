import sys; sys.path.insert(0, '..'); 
from common import *
import time; t=time.time()
sys.path.insert(0, '../PL_Predictor/src')
from pl_predictor.data import football_data
from pl_predictor.features.build import build_training_frame
seasons = football_data.default_completed_seasons()
m = football_data.load_training_data(seasons=seasons)
df, cols = build_training_frame(matches_df=m)
df.to_pickle('pl_frame.pkl'); import json; json.dump(cols, open('pl_cols.json','w'))
print(df.shape, len(cols), time.time()-t)
print(list(df.columns)[:30])
