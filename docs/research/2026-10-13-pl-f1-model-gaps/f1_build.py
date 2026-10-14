import sys; sys.path.insert(0,'.')
import common
sys.path.insert(0,'../F1_Predictor/src')
import f1_predictor, time; print(f1_predictor.__file__)
from f1_predictor.data import jolpica
import pandas as pd
def _safe(fn):
    def w(*a,**k):
        try: return fn(*a,**k)
        except RuntimeError as e: return pd.DataFrame()
    return w
for n in ['fetch_race_results','fetch_qualifying','fetch_sprint_results']: setattr(jolpica,n,_safe(getattr(jolpica,n)))
from f1_predictor.features.build import build_training_frame
t=time.time(); seasons=jolpica.default_seasons(); print(seasons)
df,cols=build_training_frame(seasons=seasons); print(df.shape,len(cols),time.time()-t)
print(df.columns.tolist()); print(df.tier.value_counts()); df.to_pickle('f1_frame.pkl')
import json; json.dump(cols,open('f1_cols.json','w'))
