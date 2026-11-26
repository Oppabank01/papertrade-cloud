#!/usr/bin/env python3
"""Idea 1: Bitkub (Thai exchange). Data: Bitkub public tradingview/history 1h bars (THB pairs) + Binance spot 1h.
A1  Discount convergence, long only ON BITKUB: premium = (coin_THB / USDT_THB on Bitkub) / coin_USDT on Binance - 1 at the hourly close.
    premium <= -thr and the signal bar traded >= minvol THB -> buy the next Bitkub bar's open. Sell at the open after the first hourly close
    with premium >= -0.5%, or after 72 h. Stop 15% checked first on Bitkub lows. Cost 0.25%/side (+0.5%/side spread stress version).
    Controls: (a) the same entry/exit hours on Binance (shows how much is convergence vs market move)  (b) random entries, same coin.
A2  Bitkub listing (first Bitkub bar) -> ride or fade the coin on Binance spot.   A3  Bitkub BTC premium / USDT-THB premium as a BTC signal."""
import sys, glob, numpy as np
from wlib import *
meta = json.load(open(f"{SCR}/bk_meta.json"))
def load_bk(s):
    fn = f"{SCR}/bk_{s}.npy"
    if not os.path.exists(fn): return None
    a = np.load(fn)
    if len(a) < 50: return None
    a = a.copy(); a[:, 0] = (a[:, 0] // H) * H
    keep = np.concatenate([[True], np.diff(a[:, 0]) > 0]); return a[keep]
def load_bn(s):
    fs = glob.glob(f"{SCR}/k_{s}USDT_1h_*.npy")
    if not fs: return None
    a = np.load(max(fs, key=os.path.getsize)); return a if len(a) > 50 else None
U = load_bk("USDT"); UT = U[:, 0]; UC = U[:, 4]
def usdt_at(t):
    """last USDT_THB close at or before hour t (max 6 h stale)"""
    i = np.searchsorted(UT, t, "right") - 1
    ok = (i >= 0) & (t - UT[np.clip(i, 0, len(UT) - 1)] <= 6 * H)
    return np.where(ok, UC[np.clip(i, 0, len(UT) - 1)], np.nan)
def prep(s):
    a = load_bk(s); b = load_bn(s)
    if a is None or b is None: return None
    j = np.searchsorted(b[:, 0], a[:, 0]); jc = np.clip(j, 0, len(b) - 1); has = b[jc, 0] == a[:, 0]
    u = usdt_at(a[:, 0])
    prem = np.where(has, (a[:, 4] / u) / b[jc, 4] - 1, np.nan)
    return a, b, jc, has, prem
def a1(s, P, thr, minvol, exit_at=-0.005, maxh=72, stop=0.15, cost=0.0025):
    a, b, jc, has, prem = P; n = len(a); tr = []
    volthb = a[:, 5] * a[:, 4]
    sig = np.nonzero((prem <= -thr) & (volthb >= minvol) & (prem > -0.5))[0]
    free = -1
    for i in sig:
        if i <= free or i + 2 >= n or a[i + 1, 0] - a[i, 0] > 3 * H or not has[i + 1]: continue
        e = a[i + 1, 1]; be = b[jc[i + 1], 1]; te = a[i + 1, 0]; px = None; kx = None
        for k in range(i + 1, n - 1):
            if a[k, 3] <= e * (1 - stop): px = min(a[k, 1], e * (1 - stop)); kx = k; bx = b[jc[k], 4] if has[k] else np.nan; break
            if (prem[k] == prem[k] and prem[k] >= exit_at) or a[k, 0] - te >= maxh * H:
                px = a[k + 1, 1]; kx = k + 1; bx = b[jc[k + 1], 1] if has[k + 1] else np.nan; break
        if px is None: break
        tr.append((int(te), px / e - 1 - 2 * cost, (bx / be - 1) if bx == bx else np.nan, prem[i], (a[kx, 0] - te) / H, s, volthb[i])); free = kx
    return tr
PRE = {}
for s in sorted(meta):
    if s == "USDT": continue
    P = prep(s)
    if P is not None and np.isfinite(P[4]).sum() > 200: PRE[s] = P
print("coins on both venues:", len(PRE), flush=True)
allp = np.concatenate([P[4][np.isfinite(P[4])] for P in PRE.values()])
print("premium distribution (all coin-hours): p1 %.2f%% p5 %.2f%% p50 %.2f%% p95 %.2f%% p99 %.2f%%  n=%d" % (*[np.percentile(allp, q) * 100 for q in (1, 5, 50, 95, 99)], len(allp)))
def show(name, tr, extra_cost=0.0):
    st = stats([(x[0], x[1] - 2 * extra_cost) for x in tr])
    if st["n"] < 8: print(f"{name:52s} n={st['n']}"); return
    bn = np.array([x[2] for x in tr]); bn = bn[np.isfinite(bn)]
    yrs = collections.defaultdict(list)
    for x in tr: yrs[time.gmtime(x[0] / 1000).tm_year].append(x[1] - 2 * extra_cost)
    top = collections.Counter(x[5] for x in tr).most_common(4)
    print(fmt(name, st), f"| binance same hours (no cost) mean={bn.mean()*100:+.2f} | medhold={np.median([x[4] for x in tr]):.0f}h coins={len(set(x[5] for x in tr))} top={top}",
          "yr " + " ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)

print("=== A1-hedged: buy the Bitkub discount AND short the same coin on Binance for the same hours (1h bars) ===")
print("net = Bitkub leg (0.25%/side) - Binance move - 0.15%/side on the short; funding ignored (holds are hours). Not tradable from a Thai-licensed venue (no shorts).")
def showh(name, tr, extra=0.0):
    hh = [(x[0], x[1] - 2 * extra - x[2] - 0.003) for x in tr if x[2] == x[2]]
    st = stats(hh)
    if st["n"] < 8: print(name, "n", st["n"]); return
    yrs = collections.defaultdict(list)
    for t, r in hh: yrs[time.gmtime(t / 1000).tm_year].append(r)
    print(fmt(name, st), f"| medhold={np.median([x[4] for x in tr]):.0f}h coins={len(set(x[5] for x in tr))}", "yr " + " ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
for thr in (0.015, 0.02, 0.03, 0.05):
    for minvol in (1e5, 1e6, 5e6):
        tr = []
        for s, P in PRE.items(): tr += a1(s, P, thr, minvol)
        showh(f"A1H disc>={thr*100:.1f}% vol>={minvol:,.0f}THB", tr)
        showh(f"    +0.5%/side Bitkub spread stress", tr, 0.005)
tr = []
for s, P in PRE.items(): tr += a1(s, P, 0.02, 1e6)
pickle = __import__("pickle"); pickle.dump(tr, open(f"{SCR}/a1_trades_2pct_1m.pkl", "wb"))
