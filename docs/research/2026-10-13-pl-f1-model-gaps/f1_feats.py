"""Candidate F1 features from jolpica results/qualifying + open-meteo only. All shift(1) / prior-race only.
Output f1_newfeats.pkl keyed (season, round, driver_id); join onto every tier."""
import sys; sys.path.insert(0,'.')
from common import *
d=pd.read_pickle('f1_frame.pkl'); T=d[d.tier=='post_qualifying'].copy().sort_values(['season','round','driver_id']).reset_index(drop=True)
T['t']=T.season*100+T['round']
T['fin']=T.position.where(~T.dnf)            # classified finish only
T['gain']=T.grid.where(T.grid>0)-T.fin        # positions gained (race conversion), NaN for DNF/pit-lane start
st=T.status.fillna('')
T['coll']=T.dnf & st.str.contains('Collision|Accident|Spun|Damage',case=False)
T['mech']=T.dnf & ~st.str.contains('Collision|Accident|Spun|Damage|Disqualified|Did not start|Withdrew|Retired',case=False)
T['lapped']=(~T.dnf)&(st.str.contains('Lap'))
def roll(g,col,w): return g[col].transform(lambda s:s.shift(1).rolling(w,min_periods=1).mean())
gd=T.groupby('driver_id')
for w in (3,5): T[f'qf{w}']=roll(gd,'quali_position',w)
T['qgapf5']=roll(gd,'quali_gap_to_pole',5); T['conv5']=roll(gd,'gain',5)
T['pace5']=roll(gd,'fastest_lap_rank',5)
# teammate-relative (same constructor, same race)
T['tm_form5']=T.form_avg_position_5-T.groupby(['season','round','constructor_id']).form_avg_position_5.transform(lambda s:(s.sum()-s)/max(len(s)-1,1) if len(s)>1 else np.nan)
T['_qd']=T.quali_position-T.groupby(['season','round','constructor_id']).quali_position.transform(lambda s:(s.sum()-s)/max(len(s)-1,1) if len(s)>1 else np.nan)
T['tm_qgap5']=T.groupby('driver_id')['_qd'].transform(lambda s:s.shift(1).rolling(5,min_periods=1).mean())
# constructor reliability: overall mech-DNF rate last 20 driver-races (EB to league) and at this circuit (EB)
league=T.mech.shift(1).expanding().mean()
cg=T.groupby('constructor_id'); T['con_mech20']=cg['mech'].transform(lambda s:s.shift(1).rolling(20,min_periods=2).mean())
def eb_circ(g):
    s=g.mech.astype(float); n=s.shift(1).expanding().count().fillna(0); x=s.shift(1).expanding().sum().fillna(0)
    prior=g.con_mech20.fillna(0.08); return (x+4*prior)/(n+4)
T['con_circ_mech_eb']=T.groupby(['constructor_id','circuit_id'],group_keys=False).apply(eb_circ,include_groups=False).reindex(T.index) if False else np.nan
tmp=[]
for (c,ci),g in T.groupby(['constructor_id','circuit_id']): tmp.append(eb_circ(g))
T['con_circ_mech_eb']=pd.concat(tmp).reindex(T.index)
# safety-car proxies: circuit lapped-share and collision-rate, expanding prior races at the circuit (per race)
pr=T.groupby(['season','round','circuit_id']).agg(lapped=('lapped','mean'),coll=('coll','mean')).reset_index().sort_values(['circuit_id','season','round'])
pr['circ_lapped']=pr.groupby('circuit_id').lapped.transform(lambda s:s.shift(1).expanding().mean()); pr['circ_coll']=pr.groupby('circuit_id').coll.transform(lambda s:s.shift(1).expanding().mean())
T=T.merge(pr[['season','round','circ_lapped','circ_coll']],on=['season','round'],how='left')
# wet-race skill: driver's prior mean gain in wet races minus dry (shrunk), times wet flag
T['wet']=(T.precipitation_mm.fillna(0)>=1.0).astype(int)
T=T.sort_values(['t','driver_id']).reset_index(drop=True)
def wet_skill(g):
    gain=g.gain.fillna(g.gain.mean()); w=g.wet
    xw=(gain*w).shift(1).expanding().sum().fillna(0); nw=w.shift(1).expanding().sum().fillna(0); xd=(gain*(1-w)).shift(1).expanding().sum().fillna(0); nd=(1-w).shift(1).expanding().sum().fillna(0)
    return ((xw)/(nw+3))-((xd)/(nd+3))
ws=[]
for k,g in T.groupby('driver_id'): ws.append(wet_skill(g).rename('wet_skill'))
T['wet_skill']=pd.concat(ws).reindex(T.index); T['wet_x']=T.wet*T.wet_skill
cols=['qf3','qf5','qgapf5','conv5','pace5','tm_form5','tm_qgap5','con_mech20','con_circ_mech_eb','circ_lapped','circ_coll','wet','wet_skill','wet_x']
T[['season','round','driver_id']+cols].to_pickle('f1_newfeats.pkl'); print(T[cols].describe().T[['count','mean','std']].round(3))
