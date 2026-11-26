#!/usr/bin/env python3
"""Deployability check of the funding-spike short on Hyperliquid memecoin perps (hl_fetch.py, ~May-Nov 2026, hourly funding).
Signal: trailing 8h funding sum first crosses X at an hourly bar -> short at the next bar open. Same simulator as Binance.
  python3 hl_bt.py <hl.pkl> [seeds=40]"""
import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import perplib as P
D = P.load(sys.argv[1]); SEEDS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
ME = sorted(s for s in D if D[s]["kind"] == "meme"); print("HL memes with data:", len(ME), " ".join(s[:-4] for s in ME))
def f8(d):
    cs = np.r_[0, np.cumsum(d["fr"])]; hi = np.searchsorted(d["ft"], d["t"] + 60000, "right"); lo = np.searchsorted(d["ft"], d["t"] + 60000 - 8 * P.H, "right")
    return cs[hi] - cs[lo]
def first_cross(mask): m = mask.astype(bool); return [int(i) + 1 for i in np.nonzero(m & ~np.r_[False, m[:-1]])[0]]
allf = np.concatenate([f8(D[s])[24:] for s in ME]); print("8h funding sum percentiles 50/90/99/99.9: " + " ".join(f"{np.percentile(allf, q) * 100:.4f}%" for q in (50, 90, 99, 99.9)))
N = 0
for x in (.0005, .001):
    for hold in (24, 72):
        N += 1; ev = {s: [i for i in first_cross(f8(D[s]) >= x) if i >= 48] for s in ME}
        P.report(f"HL short f8>={x:.2%} h{hold} sl15", D, ev, -1, hold, .15, pool=ME, seeds=SEEDS)
for x in (-.0005,):
    N += 1; ev = {s: [i for i in first_cross(f8(D[s]) <= x) if i >= 48] for s in ME}
    P.report(f"HL short f8<={x:.2%} h72 sl15", D, ev, -1, 72, .15, pool=ME, seeds=SEEDS)
N += 1; ev = {s: [i for i in range(48, len(D[s]["t"])) if D[s]["t"][i] % (7 * 86400000) == 4 * 86400000] for s in ME}
P.report("HL short every meme weekly h168 sl30 (drift)", D, ev, -1, 168, .30, pool=ME, seeds=SEEDS)
print("settings tried:", N)
