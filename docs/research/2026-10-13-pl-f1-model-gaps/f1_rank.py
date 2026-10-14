"""F1 per-market skill, walk-forward val seasons 2022..2026 (2026 = cached rounds 1-15 only), POST_QUALIFYING tier."""
import sys; sys.path.insert(0,'.')
from f1_lib import *
df = pd.read_pickle('f1_frame.pkl'); cols = json.load(open('f1_cols.json'))
R = run(df, cols, [2022,2023,2024,2025,2026], with_dnf=True); R.to_pickle('f1_preds.pkl')
print('races per season', R.groupby('season').apply(lambda g: g[['round']].nunique().iloc[0], include_groups=False).to_dict())
rows=[]
def add(name, a, b, y, metric='ll'):
    d,lo,hi = compare(R, a, b, y, metric); base = race_sum(R, ll(R[y].values,R[b].values) if metric=='ll' else (R[b].values-R[y].values)**2).mean()
    rows.append(dict(market=name, model=a, baseline=b, metric=metric, base_val=base, diff=d, lo=lo, hi=hi, skill_pct=100*d/base, sig='model better' if lo>0 else ('model WORSE' if hi<0 else 'tie')))
for y,(a,b,c) in {'win':('x_w','e_w','g_w'),'pod':('x_p','e_p','g_p'),'top10':('x_t','e_t','g_t')}.items():
    add(f'{y} logloss','%s'%a,c,y); add(f'{y} logloss',b,c,y); add(f'{y} logloss',a,b,y)
add('win Brier','x_w','g_w','win','br'); add('podium Brier','x_p','g_p','pod','br')
# DNF
R['dnf_']=R.dnf; add('DNF logloss','x_dnf','n_dnf','dnf_')
# expected position MAE / finishing-order
fin = R.pos.notna()
for nm,(a) in {'x_e':'xgb','e_e':'elo','g_e':'grid'}.items(): pass
def mae(c): return pd.Series(np.abs(R[c]-R.pos.fillna(20))).groupby([R.season,R['round']]).mean()
for a,b in [('x_e','g_e'),('e_e','g_e')]:
    d,lo,hi = boot_ci((mae(b)-mae(a)).values); rows.append(dict(market='finish-pos MAE (classified+DNF=20)',model=a,baseline=b,metric='mae',base_val=mae(b).mean(),diff=d,lo=lo,hi=hi,skill_pct=100*d/mae(b).mean(),sig='model better' if lo>0 else ('model WORSE' if hi<0 else 'tie')))
S=pd.DataFrame(rows); pd.set_option('display.width',250); print(S.round(4).to_string()); S.to_csv('f1_rank.csv',index=False)
print('ECE win x/e/g', [round(ece(R[c],R.win),4) for c in ['x_w','e_w','g_w']], 'ECE podium', [round(ece(R[c],R.pod),4) for c in ['x_p','e_p','g_p']], 'ECE dnf', round(ece(R.x_dnf,R.dnf),4), round(ece(R.n_dnf,R.dnf),4))
print('per-season mean winner logloss (repo-style, driver-mean):')
for c in ['x_w','e_w','g_w']: print(c, R.groupby('season').apply(lambda g: ll(g.win.values,g[c].values).mean(), include_groups=False).round(4).to_dict())
