"""Score pl_preds.pkl: per-market model vs naive baselines, paired bootstrap by match (2000 resamples, seed 0).
diff = baseline - model on a lower-is-better metric, so POSITIVE diff = model better. skill = diff/baseline."""
import sys; sys.path.insert(0,'.')
from common import *
R = pd.read_pickle(sys.argv[1] if len(sys.argv) > 1 else 'pl_preds.pkl').reset_index(drop=True)
y = R.ftr.map({'H':0,'D':1,'A':2}).values
def rps(P, y):
    O = np.eye(3)[y]; return ((np.cumsum(P,1)[:, :2] - np.cumsum(O,1)[:, :2])**2).sum(1)/2
def row(name, base_name, m, b, mask=None, grp=None):
    if mask is None: mask = np.ones(len(m), bool)
    m, b = np.asarray(m)[mask], np.asarray(b)[mask]
    d, lo, hi = boot_ci(b - m, groups=None)
    return dict(market=name, baseline=base_name, n=int(mask.sum()), model=float(m.mean()), base=float(b.mean()), diff=d, lo=lo, hi=hi, skill_pct=100*d/float(b.mean()))
rows = []
Pm = R[['p_h','p_d','p_a']].values
rows.append(row('1X2 RPS','league freq', rps(Pm,y), rps(R[['n_h','n_d','n_a']].values,y)))
for tag, nm in [('b365','market (Bet365 open, de-vig)'), ('pin','market (Pinnacle close, de-vig)')]:
    M = R[[f'm{tag}_h',f'm{tag}_d',f'm{tag}_a']].values; ok = ~np.isnan(M).any(1)
    Mf = np.where(ok[:,None], M, 1/3)
    rows.append(row('1X2 RPS', nm, rps(Pm,y), rps(Mf,y), mask=ok))
# O/U 2.5 Brier
ov = ((R.goals_home+R.goals_away) > 2.5).astype(float).values
rows.append(row('O/U2.5 Brier','train base rate',(R.p_over-ov)**2,(R.n_over-ov)**2))
for tag in ['b365','pin','avg']:
    c=f'mou_{tag}'
    if c in R:
        ok=R[c].notna().values; rows.append(row('O/U2.5 Brier',f'market {tag}',(R.p_over-ov)**2,(R[c].fillna(.5)-ov)**2,mask=ok))
bt = ((R.goals_home>0)&(R.goals_away>0)).astype(float).values
rows.append(row('BTTS Brier','train base rate',(R.p_btts-bt)**2,(R.n_btts-bt)**2))
rows.append(row('Exact score log-loss','indep. Poisson (train means)',-np.log(R.p_score.clip(1e-9)),-np.log(R.n_score.clip(1e-9))))
rows.append(row('1X2 log-loss','league freq',-np.log(Pm[np.arange(len(y)),y]),-np.log(R[['n_h','n_d','n_a']].values[np.arange(len(y)),y])))
for nm in ['corners','cards','hshots','ashots','hsot','asot']:
    a=R[f'a_{nm}'].values; m=np.abs(R[f'x_{nm}']-a); 
    rows.append(row(f'{nm} MAE','train mean',m,np.abs(R[f'n_{nm}']-a)))
    t=R.get(f't_{nm}'); 
    if t is not None:
        ok=t.notna().values; rows.append(row(f'{nm} MAE','trailing-10 team rates (no model)',m,np.abs(t.fillna(0)-a),mask=ok))
res = pd.DataFrame(rows); res['sig'] = np.where(res.lo>0,'model better',np.where(res.hi<0,'model WORSE','tie'))
pd.set_option('display.width',250); pd.set_option('display.max_columns',20)
print(res.round(4).to_string())
res.to_csv(sys.argv[2] if len(sys.argv) > 2 else 'pl_rank.csv', index=False)
# calibration gaps
def ece(p, o, k=10):
    b = np.clip((np.asarray(p)*k).astype(int),0,k-1); return sum(abs(o[b==i].mean()-np.asarray(p)[b==i].mean())*(b==i).mean() for i in range(k) if (b==i).any())
print('ECE O/U', ece(R.p_over.values, ov), 'ECE BTTS', ece(R.p_btts.values, bt), 'ECE 1X2 home', ece(R.p_h.values,(y==0).astype(float)))
print('per-season n:', R.groupby('season').size().to_dict())
