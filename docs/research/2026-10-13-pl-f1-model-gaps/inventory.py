import glob, json, os, pandas as pd, numpy as np
C='../PL_Predictor/data/cache/'
print('## football_data')
fd=pd.concat([pd.read_csv(f,low_memory=False) for f in sorted(glob.glob(C+'football_data/20*.csv'))])
g=fd.groupby('season')
def cov(c): return g[c].apply(lambda s:s.notna().mean()).round(2) if c in fd else None
print('rows/season', g.size().to_dict())
for c in ['hs','hst','hc','hf','hy','hr','referee','hthg','b365_h','psch','b365>2.5','avg>2.5','ah_ch','max_h','b365_ch']:
    r=cov(c); print(c, None if r is None else r.to_dict())
print('## understat'); us=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(C+'understat/20*.csv'))]); print(us.groupby('season').size().to_dict(), us.xg_home.notna().mean())
print('## understat_shots'); fs=[f for f in glob.glob(C+'understat_shots/*.csv') if os.path.basename(f)[0].isdigit()]; print(len(fs)); 
sh=pd.concat([pd.read_csv(f) for f in fs],ignore_index=True); print(len(sh)); print(sh.groupby('season').match_id.nunique().to_dict()); print(sh.situation.value_counts().to_dict()); print(sh.shot_type.value_counts().to_dict()); print(sh.result.value_counts().to_dict())
print('player_assisted nn', sh.player_assisted.notna().mean(), 'last_action nn', sh.last_action.notna().mean())
print([os.path.basename(f) for f in glob.glob(C+'understat_shots/*') if not os.path.basename(f)[0].isdigit()])
print('## fpl_history')
for f in sorted(glob.glob(C+'fpl_history/*.csv')):
    d=pd.read_csv(f,low_memory=False); print(os.path.basename(f), d.shape, 'xg' if 'expected_goals' in d else '', 'starts' if 'starts' in d else '', 'position' in d.columns)
print('## cups'); [print(f, pd.read_csv(f).shape) for f in glob.glob(C+'other_competitions/cups/*.csv')]
