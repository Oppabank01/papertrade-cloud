#!/usr/bin/env python3
"""Can a POLLING bot (no resting order, capital parked elsewhere) capture the fiat-stablecoin dips, or does it need the resting bid?
Uses the cached merged timelines from depeg_deep.py (1m bars inside every dip window). Fiat-backed pairs only.
Poll every P minutes: if the last 1m close < thr -> market buy at the next minute's open (pay 0.15% + the open price, whatever it is),
then limit sell at 0.999 (later bars only) or market after 720 h. Compare with the resting bid at the same level."""
import sys, numpy as np
from wlib import *
FIAT = "USDCUSDT TUSDUSDT FDUSDUSDT USDPUSDT PAXUSDT BUSDUSDT USD1USDT".split()
TL = {s: np.load(f"{SCR}/tl_{s}.npy") for s in FIAT if os.path.exists(f"{SCR}/tl_{s}.npy")}
def poll(a, thr, P, out=0.999, maxh=720):
    tr = []; i = 100; n = len(a)
    while i < n - 2:
        is1m = a[i + 1, 0] - a[i, 0] <= 60000
        if is1m and a[i, 4] < thr and (int(a[i, 0]) // 60000) % P == P - 1:
            e = a[i + 1, 1]; t0 = a[i + 1, 0]
            if e >= out - 0.004: i += 1; continue                 # already back: no trade worth the fee
            px = None; j = None
            for k in range(i + 2, n):
                if a[k, 0] - t0 > maxh * H: px = a[k, 1]; j = k; break
                if a[k, 2] > out: px = max(out, a[k, 1]); j = k; break
            if px is None: j = n - 1; px = a[j, 4]
            tr.append((int(t0), px / e - 1 - 0.003, e)); i = j + 1
        else: i += 1
    return tr
for thr in (0.99, 0.985, 0.98, 0.97):
    for P in (1, 5, 15):
        tr = []
        for s, a in TL.items(): tr += poll(a, thr, P)
        st = stats([(x[0], x[1]) for x in tr])
        if st["n"] < 8: print(f"poll{P}m close<{thr}: n={st['n']}"); continue
        yrs = collections.defaultdict(list)
        for x in tr: yrs[time.gmtime(x[0] / 1000).tm_year].append(x[1])
        print(fmt(f"POLL every {P}m, 1m close<{thr}, mkt buy", st), f"avg entry px {np.mean([x[2] for x in tr]):.4f}", "yr " + " ".join(f"{y}:{np.mean(v)*100:+.2f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
