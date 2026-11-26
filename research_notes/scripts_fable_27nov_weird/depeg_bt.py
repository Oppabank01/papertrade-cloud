#!/usr/bin/env python3
"""Idea 5: stablecoin / wrapped-asset depeg buys on Binance spot (1h bars, data-api.binance.vision).
Variant A (market): 1h close < thr -> buy next bar open.  Variant B (resting bid): limit buy at thr, fills at min(open, thr) when low <= thr.
Exit: limit sell at `out` (fills when a LATER bar's high >= out, or same bar if its close >= out), else close after `hold` bars.
No stop (the bet is re-peg) and a -5% stop version. One open trade per pair. Cost 0.15%/side (and 0.075 shown)."""
import sys, numpy as np
from wlib import *
STABLES = "USDCUSDT TUSDUSDT FDUSDUSDT USDPUSDT PAXUSDT BUSDUSDT DAIUSDT USTUSDT SUSDUSDT USDSUSDT USDSBUSDT USDEUSDT USD1USDT XUSDUSDT BFUSDUSDT AEURUSDT EURIUSDT USDTDAI".split()
WRAPS = "WBTCBTC BETHETH WBETHETH BNSOLSOL".split()   # peg = rolling 7d median for accruing ones, 1.0 for WBTC/BETH
K = {}
for s in STABLES + WRAPS:
    a = klines(s, "1h", 0)
    if len(a) > 500: K[s] = a
    print(s, len(a), ts(a[0, 0]) if len(a) else "-", ts(a[-1, 0]) if len(a) else "-", f"min close {a[:,4].min():.4f}" if len(a) else "", flush=True)
def peg_series(s, a):
    if s in ("AEURUSDT", "EURIUSDT"): return None          # not USD pegs
    if s in ("WBETHETH", "BNSOLSOL"):                        # accruing: 7d trailing median of close (lagged 1 bar)
        c = a[:, 4]; p = np.full(len(c), np.nan)
        for i in range(168, len(c)): p[i] = np.median(c[i - 168:i])
        return p
    return np.ones(len(a))
def run(s, a, thr, out, hold, mode, stop, cost):
    peg = peg_series(s, a)
    if peg is None: return [], 0
    tr = []; i = 200; n = len(a); never = 0
    while i < n - 1:
        p = peg[i]
        if not p == p: i += 1; continue
        if mode == "mkt":
            if a[i, 4] / p < thr: e = a[i + 1, 1]; k0 = i + 1
            else: i += 1; continue
            if e / p >= out: i += 1; continue               # already back, no trade
        else:
            if a[i, 3] / p <= thr: e = min(a[i, 1], thr * p); k0 = i
            else: i += 1; continue
        px = None; j = None
        for k in range(k0, min(n, k0 + hold)):
            tgt = out * peg[k] if peg[k] == peg[k] else out * p
            if stop is not None and a[k, 3] <= e * (1 - stop) and not (k == k0 and mode == "lim" and a[k, 4] > e * (1 - stop)):
                px = min(a[k, 1], e * (1 - stop)) if k > k0 else e * (1 - stop); j = k; break
            if (k > k0 and a[k, 2] >= tgt) or (k == k0 and mode == "lim" and a[k, 4] >= tgt) or (k == k0 and mode == "mkt" and a[k, 2] >= tgt):
                px = max(tgt, a[k, 1]) if k > k0 else tgt; j = k; break
        if px is None: j = min(n, k0 + hold) - 1; px = a[j, 4]; never += 1
        tr.append((int(a[k0, 0]), px / e - 1 - 2 * cost, s, (j - k0)))
        i = j + 1
    return tr, never
print("\n=== per setting, all pairs pooled ===")
for grp, names in (("stable", [s for s in STABLES if s in K]), ("wrap", [s for s in WRAPS if s in K])):
    for mode in ("mkt", "lim"):
        for thr in (0.997, 0.995, 0.99, 0.98, 0.97, 0.95):
            for out in (0.999, 0.9975):
                if out <= thr: continue
                for hold, stop in ((720, None), (720, 0.05), (168, None)):
                    for cost in (0.0015,):
                        tr = []; nv = 0
                        for s in names:
                            t, v = run(s, K[s], thr, out, hold, mode, stop, cost); tr += t; nv += v
                        st = stats([(x[0], x[1]) for x in tr])
                        if st["n"] < 8: print(f"{grp} {mode} thr{thr} out{out} hold{hold} stop{stop}: n={st['n']}"); continue
                        pairs = collections.Counter(x[2] for x in tr)
                        yrs = collections.defaultdict(list)
                        for x in tr: yrs[time.gmtime(x[0] / 1000).tm_year].append(x[1])
                        print(fmt(f"{grp} {mode} thr{thr} out{out} hold{hold} stop{stop}", st), f"timeout={nv} medhold={np.median([x[3] for x in tr]):.0f}h pairs={dict(pairs.most_common(6))}",
                              "yr:" + " ".join(f"{y}:{np.mean(v)*100:+.2f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
# detail list for the deep thresholds
print("\n=== trade list: stable lim thr0.98 out0.999 hold720 no stop ===")
for s in [s for s in STABLES if s in K]:
    t, v = run(s, K[s], 0.98, 0.999, 720, "lim", None, 0.0015)
    for x in t: print(s, ts(x[0]), f"{x[1]*100:+.2f}% hold {x[3]}h")
