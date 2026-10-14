"""Paired walk-forward test of extra features on the NFL quantile markets. Run from NFL repo root, PYTHONPATH=src."""
import os, sys, json, time, numpy as np, pandas as pd
from nfl_predictor.evaluate import walk_forward as wf
from nfl_predictor.models.training import FORWARD_FEATURE_COLUMNS, MARKET_LABEL_COLUMN
W='/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/nfl/'
QS=[0.05,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,0.95]
SEASONS=list(range(2019,2026))
BASE=list(FORWARD_FEATURE_COLUMNS)

def load():
    f=pd.read_parquet(W+'frame.parquet')
    t=pd.read_parquet(W+'newfeat_team.parquet')
    own=t[['season','week','team']+[c for c in t.columns if c.startswith('off_')]].rename(columns={'team':'recent_team'})
    opp=t[['season','week','team']+[c for c in t.columns if c.startswith('def_')]].rename(columns={'team':'opponent_team'}).rename(columns=lambda c: 'opp_'+c if c.startswith('def_') else c)
    f=f.merge(own,on=['season','week','recent_team'],how='left').merge(opp,on=['season','week','opponent_team'],how='left')
    pl=pd.read_parquet(W+'newfeat_player.parquet'); f=f.merge(pl,on=['player_id','season','week'],how='left')
    f['practice_ord']=f['practice_ord'].fillna(0)
    import os
    if os.environ.get('FIXPOS')=='1':
        pos=[]
        for y in (2025,2026):
            r=pd.read_parquet(W+f'cache/nflverse/rosters_{y}.parquet',columns=['gsis_id','pos_abb']); r=r[r.pos_abb.isin(['QB','RB','WR','TE'])]
            m=r.groupby('gsis_id').pos_abb.agg(lambda s:s.value_counts().index[0]).rename('pos_fix').reset_index(); m['season']=y; pos.append(m)
        pos=pd.concat(pos).rename(columns={'gsis_id':'player_id'})
        f=f.merge(pos,on=['player_id','season'],how='left'); f['position']=f['position'].fillna(f['pos_fix']); f=f.drop(columns='pos_fix')
    return f

SETS={
 'pace_script_existing':['plays_roll','pass_share_roll','opp_plays_allowed_roll'],
 'pressure_existing':['opp_pressure_rate_roll','pressure_exposure','protection_time'],
 'redzone_existing':['rz_carry_share','gtg_carry_share'],
 'ngs_qb_existing':['avg_time_to_throw','intended_air_yards_qb','aggressiveness','intended_air_yards_recv','route_participation'],
 'opp_epa_new':['opp_def_pass_epa_roll','opp_def_rush_epa_roll','off_pass_epa_roll','off_rush_epa_roll'],
 'sack_rate_new':['off_sack_rate_roll','opp_def_sack_rate_roll','opp_def_qbhit_rate_roll'],
 'neutral_script_new':['off_neutral_pass_rate_roll','off_rz_pass_rate_roll'],
 'practice_status_new':['practice_ord'],
}

def gap(p,y,bins=10,min_n=100):
    b=np.clip((p*bins).astype(int),0,bins-1); g=[]
    for i in range(bins):
        m=b==i
        if m.sum()>=min_n: g.append(abs(p[m].mean()-y[m].mean()))
    return max(g) if g else np.nan

def boot_diff(d,n=2000,seed=0):
    rng=np.random.default_rng(seed); m=rng.choice(d,size=(n,len(d)),replace=True).mean(1)
    return d.mean(),np.percentile(m,2.5),np.percentile(m,97.5)

def boot_gap(pa,pb,y,n=300,seed=1):
    rng=np.random.default_rng(seed); N=len(y); out=[]
    for _ in range(n):
        i=rng.integers(0,N,N); out.append(gap(pb[i],y[i])-gap(pa[i],y[i]))
    out=np.array(out); return np.nanmean(out),np.nanpercentile(out,2.5),np.nanpercentile(out,97.5)

def score(f,market,cols,seasons=SEASONS,qs=QS):
    s=wf.walk_forward_quantile(f,markets=[market],seasons=seasons,feature_cols=cols,quantiles=qs)
    return s.dropna(subset=['q50','actual']).reset_index(drop=True)

def compare(base,cand,label):
    assert (base.player_id.values==cand.player_id.values).all() and (base.week.values==cand.week.values).all() and (base.season.values==cand.season.values).all()
    e_b=(base.q50-base.actual).abs().values; e_c=(cand.q50-cand.actual).abs().values; e_n=(base.naive_pred-base.actual).abs().values
    d=e_b-e_c  # positive = candidate better
    mu,lo,hi=boot_diff(d)
    k=base.p_over_exogenous.notna()&cand.p_over_exogenous.notna()
    pa=base.p_over_exogenous[k].values; pb=cand.p_over_exogenous[k].values; y=base.covered_exogenous[k].values.astype(float)
    gb,gc=gap(pa,y),gap(pb,y); gm,glo,ghi=boot_gap(pa,pb,y)
    clears = lo>0 and ghi<=0
    return dict(set=label,n=len(d),mae_base=e_b.mean(),mae_cand=e_c.mean(),mae_naive=e_n.mean(),delta=mu,lo=lo,hi=hi,gap_base=gb,gap_cand=gc,gapchg=gm,gapchg_lo=glo,gapchg_hi=ghi,clears=clears,
      per_season={int(s):float(d[(base.season==s).values].mean()) for s in sorted(base.season.unique())})

if __name__=='__main__':
    markets=sys.argv[1].split(','); sets=sys.argv[2].split(',') if len(sys.argv)>2 else list(SETS)
    f=load(); res=[]
    for m in markets:
        t0=time.time(); lab=MARKET_LABEL_COLUMN[m]
        bc=[c for c in BASE if c!=lab]
        base=score(f,m,bc); print(f'[{m}] base scored n={len(base)} in {time.time()-t0:.0f}s',flush=True)
        eb=(base.q50-base.actual).abs(); en=(base.naive_pred-base.actual).abs()
        kk=en.notna().values; mu,lo,hi=boot_diff((en-eb).values[kk]); print(f'[{m}] BASE q50 MAE {eb.mean():.3f} naive {en.mean():.3f} skill(naive-model) {mu:+.3f} CI[{lo:+.3f},{hi:+.3f}]; gap_exo={gap(base.p_over_exogenous.dropna().values, base.covered_exogenous[base.p_over_exogenous.notna()].values.astype(float)):.3f}',flush=True)
        ps={int(s):(float(((en-eb)[base.season==s]).mean()), float(eb[base.season==s].mean()), float(en[base.season==s].mean())) for s in sorted(base.season.unique())}
        res.append(dict(market=m,kind='base',skill=mu,lo=lo,hi=hi,mae=float(eb.mean()),naive=float(en.mean()),per_season=ps,n=len(base)))
        for sname in sets:
            ex=[c for c in SETS[sname] if c in f.columns and c not in bc]
            cand=score(f,m,bc+ex); r=compare(base,cand,sname); r['market']=m; r['cols']=ex; res.append(r)
            print(f"[{m}] {sname}: dMAE {r['delta']:+.3f} CI[{r['lo']:+.3f},{r['hi']:+.3f}] gap {r['gap_base']:.3f}->{r['gap_cand']:.3f} chg CI[{r['gapchg_lo']:+.3f},{r['gapchg_hi']:+.3f}] clears={r['clears']}",flush=True)
            json.dump(res,open(W+f'player_eval_{sys.argv[1].replace(",","_")}{os.environ.get("FIXPOS","")}.json','w'),default=float,indent=1)
