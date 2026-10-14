"""Anytime goal / assist / G+A: direct classifiers + poisson-union vs prevalence, walk-forward (repo fold logic,
min_train_seasons=2) using the repo's own frame builder and fitters. Paired bootstrap on per-row Brier and log-loss."""
import sys; sys.path.insert(0,'.')
from common import *
sys.path.insert(0,'../PL_Predictor/src')
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from pl_predictor.evaluate import goal_contribution_research as g
frame,_ = g.build_goal_contribution_frame()
frame['goal']=(frame.goals_scored>0).astype(int); frame['assist']=(frame.assists>0).astype(int)
frame = frame[frame.season.notna()]
seasons = sorted(frame.season.unique()); print(seasons, len(frame))
feats = g.BASE_FEATURES + g.ENHANCED_FEATURES + g.OPPONENT_FEATURES
out=[]
for i in range(2, len(seasons)):
    tr = frame[frame.season.isin(seasons[:i])]; te = frame[frame.season==seasons[i]]
    cal_s = seasons[i-1]; fit = tr[tr.season!=cal_s]; cal = tr[tr.season==cal_s]
    for tgt, rate in [('goal','goals_per90_last10'),('assist','assists_per90_last10'),('goal_contribution',None)]:
        yfit, ycal, yte = fit[tgt].values, cal[tgt].values, te[tgt].values
        fn = ['position']+[f for f in feats if f in frame]
        Xf, cols = g._design_matrix(fit, fn); Xc,_ = g._design_matrix(cal, fn, cols); Xt,_ = g._design_matrix(te, fn, cols)
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced')).fit(Xf, yfit)
        pc = m.predict_proba(Xc)[:,1]; pt = g._apply_platt(g._fit_platt(pc, ycal), m.predict_proba(Xt)[:,1])
        if rate: 
            u = lambda d: 1-np.exp(-np.clip(d[rate].values*d.expected_minutes_pre_match.values/90,0,None))
        else: u = g._poisson_union
        pu = g._apply_platt(g._fit_platt(u(cal), ycal), u(te))
        prev = np.full(len(te), yfit.mean())
        for name,p in [('direct',pt),('union_platt',pu),('prevalence',prev)]:
            p=np.clip(p,1e-6,1-1e-6)
            out.append(pd.DataFrame(dict(season=seasons[i],target=tgt,model=name,y=yte,p=p,brier=(p-yte)**2,ll=-(yte*np.log(p)+(1-yte)*np.log(1-p)),
                                          mid=te.team.astype(str).values+'|'+te.kickoff_time.astype(str).str[:10].values if 'team' in te else np.arange(len(te)))))
    print(seasons[i],'done',flush=True)
R=pd.concat(out); R.to_pickle('pl_player_preds.pkl')
rows=[]
for tgt in R.target.unique():
    D=R[R.target==tgt]; pv=D[D.model=='prevalence'].reset_index(drop=True)
    for mdl in ['direct','union_platt']:
        M=D[D.model==mdl].reset_index(drop=True)
        for metric in ['brier','ll']:
            d,lo,hi=boot_ci(pv[metric]-M[metric], groups=M.mid.values)
            rows.append(dict(target=tgt,model=mdl,metric=metric,model_val=M[metric].mean(),prev_val=pv[metric].mean(),diff_prev_minus_model=d,lo=lo,hi=hi,skill_pct=100*d/pv[metric].mean(),base_rate=M.y.mean(),n=len(M)))
S=pd.DataFrame(rows); pd.set_option('display.width',250); print(S.round(4).to_string()); S.to_csv('pl_player_rank.csv',index=False)
