"""NFL game-level: unused-data feature sets vs baseline, train>=2017, validate 2019-2025. NFL repo root, PYTHONPATH=src."""
import sys, json, numpy as np, pandas as pd
from nfl_predictor.tools import block_eval as be
from nfl_predictor.evaluate import walk_forward as wf
from nfl_predictor.models import game_outcome as go
W='/private/tmp/claude-501/-Users-sigey-Documents-Projects-nosync/56aaa9a5-e5c4-4c7a-a233-23dbe6f9dce8/scratchpad/w/nfl/'
SETS={
 'opp_adj_epa':(['off_pass_epa_roll','off_rush_epa_roll','def_pass_epa_roll','def_rush_epa_roll'],'brier'),
 'pace':(['off_plays_roll','def_plays_roll'],'total'),
 'sack_pressure':(['off_sack_rate_roll','def_sack_rate_roll','def_qbhit_rate_roll'],'brier'),
 'neutral_script':(['off_neutral_pass_rate_roll','off_rz_pass_rate_roll'],'total'),
 'referee_total_dev':(['ref_total_dev'],'total'),
}
def tgap(pred,act,b=5):
    q=np.quantile(pred,np.linspace(0,1,b+1)); i=np.clip(np.searchsorted(q,pred,side='right')-1,0,b-1)
    return max(abs((pred[i==k]-act[i==k]).mean()) for k in range(b) if (i==k).any())
def boot_gap(fn,pa,pb,y,n=300,seed=1):
    rng=np.random.default_rng(seed); N=len(y); d=[]
    for _ in range(n):
        i=rng.integers(0,N,N); d.append(fn(pb[i],y[i])-fn(pa[i],y[i]))
    d=np.array(d); return float(d.mean()),float(np.percentile(d,2.5)),float(np.percentile(d,97.5))
def merge_feats(g):
    t=pd.read_parquet(W+'newfeat_team.parquet'); cols=[c for c in t.columns if c.endswith('_roll')]
    out=g.copy()
    for side in ('home','away'):
        m=t.rename(columns={'team':f'{side}_team',**{c:f'{side}_{c}' for c in cols}})
        out=out.merge(m,on=['season','week',f'{side}_team'],how='left')
    # referee: lagged shrunk mean of (game total - season-agnostic league mean) over refs' previous games
    s=pd.concat([pd.read_parquet(f'{W}cache/nflverse/schedules_{y}.parquet',columns=['game_id','referee']) for y in range(2017,2026)])
    out=out.merge(s.drop_duplicates('game_id'),on='game_id',how='left')
    out=out.sort_values(['gameday','game_id']).reset_index(drop=True); out['_tot']=out.home_score+out.away_score
    lm=out['_tot'].shift(1).expanding().mean()  # league mean to date, lagged
    dev=(out['_tot']-lm)
    def lag_ref(ser):
        l=ser.shift(1); n=l.notna().cumsum(); return l.expanding().mean()*(n/(n+20))
    out['ref_total_dev']=dev.groupby(out['referee']).transform(lag_ref)
    return out
def fold_cols(sname):
    cs=SETS[sname][0]
    return ['ref_total_dev'] if sname=='referee_total_dev' else [f'{s}_{c}' for c in cs for s in ('home','away')]
def per_game(folds,tgt_cols_extra=None):
    r={k:[] for k in ['me','br','p','y','te','tp','ta']}
    for f in folds:
        tr,va,fc=f['train_df'],f['val_df'],f['feature_cols']
        preds,sig=wf._predict_margins('ridge',tr,va,fc); tp=wf._fit_predict('ridge',tr,va,fc,'total_points')
        mg=va['margin'].to_numpy(float); p=np.clip(np.array([go.margin_to_probabilities(m,sig)['home_win_prob'] for m in preds]),1e-6,1-1e-6); y=(mg>0).astype(float)
        r['me'].append(np.abs(preds-mg)); r['br'].append((p-y)**2); r['p'].append(p); r['y'].append(y)
        ta=va['total_points'].to_numpy(float); r['te'].append(np.abs(tp-ta)); r['tp'].append(tp); r['ta'].append(ta)
    return {k:np.concatenate(v) for k,v in r.items()}
def main(sets):
    g,aux=be.load_recent_nfl_data(2000,2025); g=merge_feats(g)
    def mk(extra):
        folds=[f for f in wf.prepare_folds(g) if f['val_season']>=2019]
        for f in folds:
            f['train_df']=f['train_df'][f['train_df'].season>=2017].copy(); f['val_df']=f['val_df'].copy(); f['feature_cols']=list(f['feature_cols'])+extra
            for c in extra:
                mu=f['train_df'][c].mean(); f['train_df'][c]=f['train_df'][c].fillna(mu); f['val_df'][c]=f['val_df'][c].fillna(mu)
        return folds
    B=per_game(mk([])); print('BASELINE (10 feats, train 2017+, val 2019-2025) N=%d'%len(B['y']))
    # naive: train mean
    folds=mk([]); nt=np.concatenate([np.full(len(f['val_df']),f['train_df']['total_points'].mean()) for f in folds]); nm=np.concatenate([np.full(len(f['val_df']),f['train_df']['margin'].mean()) for f in folds]); pn=np.concatenate([np.full(len(f['val_df']),(f['train_df']['margin']>0).mean()) for f in folds])
    def sk(n,m,nv):
        lo,hi=be.paired_bootstrap(nv,m); print(f'  {n}: model {m.mean():.4f} naive {nv.mean():.4f} skill {nv.mean()-m.mean():+.4f} CI[{lo:+.4f},{hi:+.4f}]')
    sk('Brier',B['br'],(pn-B['y'])**2); sk('margin MAE',B['me'],np.abs(B['y']*0+ (nm-np.concatenate([f['val_df']['margin'].to_numpy(float) for f in folds])))); sk('total MAE',B['te'],np.abs(nt-B['ta']))
    res=[]
    for s in sets:
        cols=fold_cols(s); C=per_game(mk(cols))
        br=be.paired_bootstrap(B['br'],C['br']); te=be.paired_bootstrap(B['te'],C['te']); me=be.paired_bootstrap(B['me'],C['me'])
        gb,gc=be.calibration_gap(B['p'],B['y']),be.calibration_gap(C['p'],C['y']); gch=boot_gap(be.calibration_gap,B['p'],C['p'],B['y'])
        tgb,tgc=tgap(B['tp'],B['ta']),tgap(C['tp'],C['ta']); tgch=boot_gap(tgap,B['tp'],C['tp'],B['ta'])
        r=dict(set=s,cols=cols,primary=SETS[s][1],brier_d=float((B['br']-C['br']).mean()),brier_ci=br,tot_d=float((B['te']-C['te']).mean()),tot_ci=te,mae_d=float((B['me']-C['me']).mean()),mae_ci=me,
               wp_gap=[gb,gc,gch],total_gap=[tgb,tgc,tgch])
        print(json.dumps(r,default=float),flush=True); res.append(r)
    json.dump(res,open(W+'game_eval2.json','w'),default=float,indent=1)
main(sys.argv[1].split(','))
