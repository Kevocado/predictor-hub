from h import *
d=pd.read_pickle("../step2_team_preds.pkl"); y=d['y']
rng=np.random.default_rng(SEED)
for k in ('pw','ps','pe'):
    p=d[k]; pt=roc_auc=None
    from sklearn.metrics import roc_auc_score as A
    bs=[]
    for _ in range(N_RES):
        i=rng.integers(0,len(y),len(y)); bs.append(A(y[i],p[i]))
    print(k, round(A(y,p),4), np.percentile(bs,[2.5,97.5]).round(4))
# wilson
from math import sqrt
def w(k,n,z=1.96):
    p=k/n; c=(p+z*z/(2*n))/(1+z*z/n); h=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n); return round(c-h,3),round(c+h,3)
for k in (5,6): print(k,10,w(k,10))
