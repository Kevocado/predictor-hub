"""Baseline game-level skill (NFL): model vs naive, paired bootstrap. Run from repo root with PYTHONPATH=src."""
import sys, numpy as np, pandas as pd
from sklearn.metrics import log_loss
from nfl_predictor.tools import block_eval as be
from nfl_predictor.evaluate import walk_forward as wf
from nfl_predictor.models import game_outcome as go

def boot(d, n=2000, seed=0):
    d=np.asarray(d,float); rng=np.random.default_rng(seed)
    m=rng.choice(d,size=(n,len(d)),replace=True).mean(1); return d.mean(), np.percentile(m,2.5), np.percentile(m,97.5)

def run(games_df, aux, start=2000, end=2025, cand="ridge", blocks=()):
    folds = wf.prepare_folds(games_df, blocks=blocks, aux=aux)
    out = {k: [] for k in ["m_err","m_naive","t_err","t_naive","p","y","p_naive","vegas_err","has_line","season","t_vegas_err"]}
    for f in folds:
        tr, va, fc = f["train_df"], f["val_df"], f["feature_cols"]
        preds, sigma = wf._predict_margins(cand, tr, va, fc)
        tp = wf._fit_predict(cand, tr, va, fc, "total_points")
        marg = va["margin"].to_numpy(float); tot = va["total_points"].to_numpy(float)
        p = np.clip(np.array([go.margin_to_probabilities(m, sigma)["home_win_prob"] for m in preds]),1e-6,1-1e-6)
        out["m_err"].append(np.abs(preds-marg)); out["m_naive"].append(np.abs(marg - tr["margin"].mean()))
        out["t_err"].append(np.abs(tp-tot)); out["t_naive"].append(np.abs(tot-tr["total_points"].mean()))
        y=(marg>0).astype(float); out["p"].append(p); out["y"].append(y)
        out["p_naive"].append(np.full(len(va), (tr["margin"]>0).mean()))
        sl = va["spread_line"].to_numpy(float) if "spread_line" in va else np.full(len(va),np.nan)  # nflverse: home margin expected = spread_line
        out["vegas_err"].append(np.abs(sl-marg)); out["has_line"].append(~np.isnan(sl))
        tl = va["total_line"].to_numpy(float) if "total_line" in va else np.full(len(va),np.nan)
        out["t_vegas_err"].append(np.abs(tl-tot))
        out["season"].append(va["season"].to_numpy())
    return {k:np.concatenate(v) for k,v in out.items()}

def report(o, label):
    y=o["y"]; p=o["p"]; pn=o["p_naive"]
    br=(p-y)**2; brn=(pn-y)**2
    ll=-(y*np.log(p)+(1-y)*np.log(1-p)); lln=-(y*np.log(pn)+(1-y)*np.log(1-pn))
    N=len(y); print(f"== {label}: N={N} seasons {int(o['season'].min())}-{int(o['season'].max())}")
    def line(name, model, naive, unit):
        mu,lo,hi = boot(naive-model); print(f"{name}: model={model.mean():.4f} naive={naive.mean():.4f} skill(naive-model)={mu:+.4f} CI[{lo:+.4f},{hi:+.4f}] {unit}")
    line("game_outcome Brier", br, brn, "lower better")
    line("game_outcome logloss", ll, lln, "lower better")
    line("margin MAE", o["m_err"], o["m_naive"], "pts")
    line("total_points MAE", o["t_err"], o["t_naive"], "pts")
    hl=o["has_line"]
    if hl.sum()>0:
        mu,lo,hi=boot(o["m_err"][hl]-o["vegas_err"][hl]); print(f"model margin MAE minus Vegas-spread MAE (context only, N={hl.sum()}): {mu:+.4f} CI[{lo:+.4f},{hi:+.4f}] (positive = model worse than the market)")
        tl=~np.isnan(o["t_vegas_err"]); mu,lo,hi=boot(o["t_err"][tl]-o["t_vegas_err"][tl]); print(f"model total MAE minus Vegas-total MAE (N={tl.sum()}): {mu:+.4f} CI[{lo:+.4f},{hi:+.4f}]")
    for lab,mask in (("2010-2025",o["season"]>=2010),("2019-2025",o["season"]>=2019)):
        if mask.sum()==0: continue
        sub=dict(Brier=(brn[mask]-br[mask]), tot=(o["t_naive"][mask]-o["t_err"][mask]), marg=(o["m_naive"][mask]-o["m_err"][mask]))
        print(f"  [{lab} N={mask.sum()}] "+"; ".join(f"{k} skill {boot(v)[0]:+.4f} [{boot(v)[1]:+.4f},{boot(v)[2]:+.4f}]" for k,v in sub.items()))

if __name__=="__main__":
    g,aux=be.load_recent_nfl_data(2000,2025)
    o=run(g,aux); report(o,"NFL ridge default features (10)")
