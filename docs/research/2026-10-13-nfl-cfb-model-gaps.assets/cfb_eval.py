"""CFB: test unused CFBD fields as feature blocks with the repo's walk-forward + paired bootstrap. Run from CFB repo root, PYTHONPATH=src."""
import json, sys, numpy as np, pandas as pd
from pathlib import Path
from cfb_predictor.tools import block_eval as be
from cfb_predictor.evaluate import walk_forward as wf
from cfb_predictor.features import epa as epam
from cfb_predictor.features.build import FEATURE_COLUMNS

def raw_rows(years):
    out=[]
    for y in years:
        d=json.load(open(f'data/cfbd/advanced_{y}.json')); by={}
        for r in d: by.setdefault(r['gameId'],[]).append(r)
        for gid,pair in by.items():
            if len(pair)!=2: continue
            for me,opp in (pair,pair[::-1]):
                o,p=me['offense'],opp['offense']  # p = what the opponent offense did to my defense
                def g(b,*ks):
                    for k in ks: b=(b or {}).get(k)
                    return b
                row={'game_id':str(gid),'team':me['team'],'season':me['season'],'week':me['week']}
                for pre,b in (('off',o),('def',p)):
                    row[f'{pre}_expl']=g(b,'explosiveness'); row[f'{pre}_line']=g(b,'lineYards'); row[f'{pre}_stuff']=g(b,'stuffRate'); row[f'{pre}_power']=g(b,'powerSuccess')
                    row[f'{pre}_plays']=g(b,'plays'); row[f'{pre}_drives']=g(b,'drives')
                    row[f'{pre}_sd_succ']=g(b,'standardDowns','successRate'); row[f'{pre}_pd_succ']=g(b,'passingDowns','successRate')
                    row[f'{pre}_epa']=g(b,'ppa'); row[f'{pre}_epa_pass']=g(b,'passingPlays','ppa'); row[f'{pre}_epa_rush']=g(b,'rushingPlays','ppa')
                out.append(row)
    return pd.DataFrame(out)

STATSETS={
 'explosiveness':['off_expl','def_expl'],
 'run_structure':['off_line','off_stuff','off_power','def_line','def_stuff','def_power'],
 'pace':['off_plays','def_plays','off_drives'],
 'situational_success':['off_sd_succ','off_pd_succ','def_sd_succ','def_pd_succ'],
 'opp_adj_epa':['adj_off_epa','adj_def_epa'],
}

def team_ewm_table(games_df, tg):
    tg=tg.copy()
    for pre in ('off','def'): pass
    base_years=tg[tg.season<=2015]
    stats=[c for c in tg.columns if c not in ('game_id','team','season','week')]
    # opponent-adjusted epa: subtract opponent's PRE-game (lagged, shrunk ewm) strength
    long=pd.concat([games_df[['game_id','gameday',f'{s}_team']].rename(columns={f'{s}_team':'team'}) for s in ('home','away')]).drop_duplicates(['game_id','team'])
    long['gameday']=pd.to_datetime(long['gameday'])
    long=long.merge(tg,on=['game_id','team'],how='left').sort_values(['team','gameday','game_id']).reset_index(drop=True)
    for c in ('off_epa','def_epa'):
        long[c+'_pre']=long.groupby('team')[c].transform(lambda s: epam._shrunk_ewm(s,epam.EWM_HALFLIFE,epam.SHRINK_K))
    opp=long[['game_id','team','off_epa_pre','def_epa_pre']].rename(columns={'team':'opp','off_epa_pre':'opp_off_pre','def_epa_pre':'opp_def_pre'})
    # find each team's opponent in the game
    pair=long[['game_id','team']].merge(long[['game_id','team']],on='game_id'); pair=pair[pair.team_x!=pair.team_y].rename(columns={'team_x':'team','team_y':'opp'})
    long=long.merge(pair,on=['game_id','team'],how='left').merge(opp,on=['game_id','opp'],how='left')
    long['adj_off_epa']=long['off_epa']-long['opp_def_pre'].fillna(0)   # offence EPA minus what the opponent's defence usually allows
    long['adj_def_epa']=long['def_epa']-long['opp_off_pre'].fillna(0)
    allstats=stats+['adj_off_epa','adj_def_epa']
    ctr=long[long.season<=2015][allstats].mean()
    for s in allstats:
        long[s+'_ewm']=long.groupby('team')[s].transform(lambda x: epam._shrunk_ewm(x-ctr[s],epam.EWM_HALFLIFE,epam.SHRINK_K))
    return long[['game_id','team']+[s+'_ewm' for s in allstats]]

def add_cols(games_df, T):
    out=games_df.copy(); k=T.set_index(['game_id','team'])
    for side in ('home','away'):
        idx=pd.MultiIndex.from_arrays([out['game_id'].astype(str),out[f'{side}_team']])
        v=k.reindex(idx)
        for c in k.columns: out[f'{side}_{c}']=v[c].to_numpy()
    return out

def cols_for(sname):
    return [f'{s}_{c}_ewm' for c in STATSETS[sname] for s in ('home','away')]

def run(sets):
    games_df,aux=be.load_recent_cfb_data(2014,2025)
    games_df['game_id']=games_df['game_id'].astype(str)
    tg=raw_rows(range(2014,2026)); T=team_ewm_table(games_df,tg)
    # 'neutral_site' is an unused games column: 1 if neutral venue
    g2=add_cols(games_df,T)
    if 'neutral_site' in g2: g2['neutral_site']=g2['neutral_site'].fillna(0).astype(int)
    base_folds=wf.prepare_folds(g2)
    bm=be._per_game(base_folds,'ridge'); bt=np.concatenate([np.abs(wf._fit_predict('ridge',f['train_df'],f['val_df'],f['feature_cols'],'total_points')-f['val_df']['total_points'].to_numpy(float)) for f in base_folds])
    bg=be._per_fold_gap(base_folds,'ridge')
    ytot=np.concatenate([f['val_df']['total_points'].to_numpy(float) for f in base_folds]); ttr=np.concatenate([np.full(len(f['val_df']),f['train_df']['total_points'].mean()) for f in base_folds])
    ymar=np.concatenate([f['val_df']['margin'].to_numpy(float) for f in base_folds]); mtr=np.concatenate([np.full(len(f['val_df']),f['train_df']['margin'].mean()) for f in base_folds])
    ph=np.concatenate([np.full(len(f['val_df']),(f['train_df']['margin']>0).mean()) for f in base_folds]); yb=(ymar>0).astype(float)
    print('BASELINE (10 features, ridge) N=%d'%len(bm[0]))
    def sk(name,model,naive):
        lo,hi=be.paired_bootstrap(naive,model); print(f'  {name}: model {model.mean():.4f} naive {naive.mean():.4f} skill {naive.mean()-model.mean():+.4f} CI[{lo:+.4f},{hi:+.4f}]')
    sk('margin MAE (pts)',bm[0],np.abs(ymar-mtr)); sk('Brier',bm[1],(ph-yb)**2); sk('total_points MAE',bt,np.abs(ytot-ttr))
    res=[]
    for s in sets:
        cols=cols_for(s) if s in STATSETS else {'neutral_site':['neutral_site']}[s]
        folds=wf.prepare_folds(g2); 
        for f in folds:
            f['feature_cols']=list(f['feature_cols'])+cols
            for d in ('train_df','val_df'): f[d]=f[d].copy(); f[d][cols]=f[d][cols].fillna(0)
        wm=be._per_game(folds,'ridge'); wt=np.concatenate([np.abs(wf._fit_predict('ridge',f['train_df'],f['val_df'],f['feature_cols'],'total_points')-f['val_df']['total_points'].to_numpy(float)) for f in folds])
        wg=be._per_fold_gap(folds,'ridge')
        mae=be.paired_bootstrap(bm[0],wm[0]); br=be.paired_bootstrap(bm[1],wm[1]); tt=be.paired_bootstrap(bt,wt); gp=be.paired_bootstrap_gap(bg,wg)
        auc=be.paired_bootstrap_auc(bm[2],wm[2],bm[3])
        gb,gw=be.calibration_gap(bm[2],bm[3]),be.calibration_gap(wm[2],wm[3])
        r=dict(set=s,cols=cols,mae_d=float((bm[0]-wm[0]).mean()),mae_ci=mae,brier_d=float((bm[1]-wm[1]).mean()),brier_ci=br,tot_d=float((bt-wt).mean()),tot_ci=tt,gap_base=gb,gap_blk=gw,gap_ci=gp,auc=auc[0],auc_ci=auc[1:])
        print(json.dumps(r,default=float),flush=True); res.append(r)
    json.dump(res,open(f'{sys.argv[2] if len(sys.argv)>2 else "cfb_res"}.json','w'),default=float,indent=1)
if __name__=='__main__': run(sys.argv[1].split(','))
