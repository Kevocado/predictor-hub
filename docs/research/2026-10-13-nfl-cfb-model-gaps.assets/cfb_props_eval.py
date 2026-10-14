"""CFB player props: add unused-CFBD/game-context features to the 6-feature XGB regressors. CFB repo root, PYTHONPATH=src:stubs."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0,'/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w')
import cfb_eval as ce
from cfb_predictor.tools import block_eval as be
from cfb_predictor.features.player_usage import _add_rolling, PLAYER_FEATURE_COLUMNS, anytime_td_actual
from cfb_predictor.models.player_props import fit_yardage_regressor, fit_anytime_td_classifier
CACHE='data/cache/'
games_df,aux=be.load_recent_cfb_data(2014,2025); games_df['game_id']=games_df['game_id'].astype(str)
T=ce.team_ewm_table(games_df,ce.raw_rows(range(2014,2026)))
rows=[]
for side,opp in (('home','away'),('away','home')):
    rows.append(pd.DataFrame({'game_id':games_df.game_id,'season':games_df.season,'week':games_df.week,'team':games_df[f'{side}_team'],'opp':games_df[f'{opp}_team'],'is_home':int(side=='home'),'neutral':games_df.get('neutral_site',0)}))
L=pd.concat(rows).drop_duplicates(['season','week','team'])
L['neutral']=L['neutral'].fillna(0).astype(int); L.loc[L.neutral==1,'is_home']=0
Tm=T.rename(columns={c:'own_'+c for c in T.columns if c.endswith('_ewm')})
To=T.rename(columns={'team':'opp',**{c:'opp_'+c for c in T.columns if c.endswith('_ewm')}})
L=L.merge(Tm,on=['game_id','team'],how='left').merge(To,on=['game_id','opp'],how='left')
ps=pd.concat([pd.read_parquet(f'{CACHE}player_stats/{y}.parquet') for y in range(2018,2026)],ignore_index=True)
ps=_add_rolling(ps).rename(columns={'recent_team':'team'}).merge(L,on=['season','week','team'],how='left')
print('rows',len(ps),'matched to a game',ps.game_id.notna().mean().round(3))
SETS={'opp_defense_epa':['opp_def_epa_pass_ewm','opp_def_epa_rush_ewm'],'own_offense_epa':['own_off_epa_pass_ewm','own_off_epa_rush_ewm'],
      'pace':['own_off_plays_ewm','opp_def_plays_ewm'],'venue':['is_home','neutral'],'opp_defense_structure':['opp_def_stuff_ewm','opp_def_line_ewm','opp_def_expl_ewm']}
MK={'passing_yards':'QB','rushing_yards':'RB','receiving_yards':'WR'}
VAL=[2021,2022,2023,2024,2025]
def covgap(p,a,b=5):
    q=np.quantile(p,np.linspace(0,1,b+1)); i=np.clip(np.searchsorted(q,p,side='right')-1,0,b-1)
    return max(abs(((a[i==k]>p[i==k]).mean())-0.5) for k in range(b) if (i==k).any())
def bgap(pa,pb,a,n=300,seed=1):
    rng=np.random.default_rng(seed); N=len(a); dd=[]
    for _ in range(n):
        i=rng.integers(0,N,N); dd.append(covgap(pb[i],a[i])-covgap(pa[i],a[i]))
    dd=np.array(dd); return float(dd.mean()),float(np.percentile(dd,2.5)),float(np.percentile(dd,97.5))
from xgboost import XGBRegressor
def fit_abs(X,y):
    m=XGBRegressor(n_estimators=150,max_depth=3,learning_rate=0.05,random_state=42,objective='reg:absoluteerror'); m.fit(X.fillna(0),y); return m
def wf(market,extra,fit=None,blend=False):
    d=ps[(ps.position==MK[market])&ps[market].notna()].copy(); cols=PLAYER_FEATURE_COLUMNS+extra; out=[]
    for s in VAL:
        tr,va=d[d.season<s],d[d.season==s]
        if va.empty or tr.empty: continue
        m=(fit or fit_yardage_regressor)(tr[cols],tr[market]); p=m.predict(va[cols].fillna(0)); nn=va[f'{market}_roll'].values
        if blend: p=np.where(np.isnan(nn),p,0.5*p+0.5*nn)
        out.append(pd.DataFrame({'season':s,'a':va[market].values,'p':p,'n':nn}))
    return pd.concat(out,ignore_index=True)
res=[]
for mk in MK:
    b=wf(mk,[]); eb=np.abs(b.p-b.a); en=np.abs(b.n-b.a); k=en.notna().values
    lo,hi=be.paired_bootstrap(en[k],eb[k]); print(f'[{mk}] BASE N={len(b)} MAE {eb.mean():.3f} naive(roll5) {en.mean():.3f} skill {en[k].mean()-eb[k].mean():+.3f} CI[{lo:+.3f},{hi:+.3f}]',flush=True)
    res.append(dict(market=mk,kind='base',n=len(b),mae=float(eb.mean()),naive=float(en.mean()),skill=float(en[k].mean()-eb[k].mean()),ci=[lo,hi]))
    print(f'   base median-coverage gap {covgap(b.p.values,b.a.values):.3f}')
    VARS=[(sn,cols,None,False) for sn,cols in SETS.items()]+[('objective_absoluteerror_(no new data)',[],fit_abs,False),('blend_50_50_with_roll5_(no new data)',[],None,True),('abs_objective+venue+pace',SETS['venue']+SETS['pace'],fit_abs,False)]
    for sn,cols,fit,bl in VARS:
        c=wf(mk,cols,fit,bl); ec=np.abs(c.p-c.a); lo2,hi2=be.paired_bootstrap(eb,ec); d=(eb-ec).values
        per={int(s):float(d[(b.season==s).values].mean()) for s in VAL}; g=bgap(b.p.values,c.p.values,b.a.values)
        print(f'[{mk}] {sn}: dMAE {d.mean():+.3f} CI[{lo2:+.3f},{hi2:+.3f}] covgap {covgap(b.p.values,b.a.values):.3f}->{covgap(c.p.values,c.a.values):.3f} chg CI[{g[1]:+.3f},{g[2]:+.3f}] seasons+ {sum(v>0 for v in per.values())}/5 | naive-vs-cand skill {(np.abs(c.n-c.a)[k].mean()-ec[k].mean()):+.3f}',flush=True)
        res.append(dict(market=mk,set=sn,cols=cols,delta=float(d.mean()),ci=[lo2,hi2],per_season=per,gap=[covgap(b.p.values,b.a.values),covgap(c.p.values,c.a.values),g],cand_mae=float(ec.mean()),skill_vs_naive=float(np.abs(c.n-c.a)[k].mean()-ec[k].mean())))
# anytime TD
d=ps[ps.position.isin(['QB','RB','WR'])&ps.rushing_tds.notna()&ps.receiving_tds.notna()].copy(); d['y']=anytime_td_actual(d.rushing_tds,d.receiving_tds).astype(int)
def ll(y,p): return -(y*np.log(p)+(1-y)*np.log(1-p))
def atd(extra):
    cols=PLAYER_FEATURE_COLUMNS+extra; o=[]
    for s in VAL:
        tr,va=d[d.season<s],d[d.season==s]; m=fit_anytime_td_classifier(tr[cols],tr.y); p=np.clip(m.predict_proba(va[cols].fillna(0))[:,1],1e-4,1-1e-4)
        o.append(pd.DataFrame({'y':va.y.values,'p':p,'pn':va.position.map(tr.groupby('position').y.mean()).values,'season':s}))
    return pd.concat(o,ignore_index=True)
b=atd([]); lb=ll(b.y.values,b.p.values); ln=ll(b.y.values,b.pn.values); lo,hi=be.paired_bootstrap(ln,lb)
print(f'[anytime_td] BASE N={len(b)} logloss {lb.mean():.4f} naive(pos rate) {ln.mean():.4f} skill {ln.mean()-lb.mean():+.4f} CI[{lo:+.4f},{hi:+.4f}]',flush=True)
res.append(dict(market='anytime_td',kind='base',n=len(b),ll=float(lb.mean()),naive=float(ln.mean()),skill=float(ln.mean()-lb.mean()),ci=[lo,hi]))
for sn in ('opp_defense_epa','own_offense_epa','pace','venue'):
    c=atd(SETS[sn]); lc=ll(c.y.values,c.p.values); lo2,hi2=be.paired_bootstrap(lb,lc); print(f'[anytime_td] {sn}: dLogloss {(lb-lc).mean():+.4f} CI[{lo2:+.4f},{hi2:+.4f}]',flush=True)
    res.append(dict(market='anytime_td',set=sn,delta=float((lb-lc).mean()),ci=[lo2,hi2]))
json.dump(res,open('/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/cfb/props.json','w'),indent=1)
