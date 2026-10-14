"""Shared offline harness bits (no network)."""
import socket, sys, os
def _blocked(*a, **k): raise RuntimeError("network blocked (offline research run)")
socket.socket.connect = _blocked; socket.create_connection = _blocked
import numpy as np, pandas as pd
def boot_ci(d, n=2000, seed=0, groups=None):
    """paired bootstrap of mean(d); resample by group (match) if given."""
    rng = np.random.default_rng(seed); d = np.asarray(d, float)
    if groups is None:
        idx = rng.integers(0, len(d), (n, len(d))); m = d[idx].mean(1)
    else:
        g = pd.Series(d).groupby(np.asarray(groups)).agg(['sum','count']); s=g['sum'].values; c=g['count'].values
        k = len(s); idx = rng.integers(0, k, (n, k)); m = s[idx].sum(1)/c[idx].sum(1)
    return float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))
