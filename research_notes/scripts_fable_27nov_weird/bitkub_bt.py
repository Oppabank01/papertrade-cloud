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
print("\n=== A1 discount convergence (buy on Bitkub) ===")
RES = {}
for thr in (0.015, 0.02, 0.03, 0.05):
    for minvol in (1e5, 1e6, 5e6):
        tr = []
        for s, P in PRE.items(): tr += a1(s, P, thr, minvol)
        RES[(thr, minvol)] = tr
        show(f"A1 disc>={thr*100:.1f}% vol>={minvol:,.0f}THB", tr)
        show(f"   same +0.5%/side spread stress", tr, 0.005)
print("\n--- A1 variants on disc>=3% vol>=1e5 ---")
for kw, nm in ((dict(maxh=24), "max24h"), (dict(maxh=168), "max168h"), (dict(exit_at=-0.01), "exit at -1%"), (dict(stop=0.08), "stop 8%")):
    tr = []
    for s, P in PRE.items(): tr += a1(s, P, 0.03, 1e5, **kw)
    show(f"A1 disc>=3% vol>=1e5 {nm}", tr)
print("\n--- A1 random-entry control on the same coins (disc>=3% vol>=1e5 trade count per coin, 72h hold, stop 15%) ---")
base = RES[(0.03, 1e5)]; cnt = collections.Counter(x[5] for x in base); ms = []
for k in range(100):
    rng = np.random.default_rng(k); rr = []
    for s, c in cnt.items():
        a = PRE[s][0]
        for i in rng.integers(10, max(11, len(a) - 80), c):
            x = sim(a, int(i), 1, 72, 0.15, cost=0.0025)
            if x: rr.append(x[1])
    ms.append(np.mean(rr) * 100)
print(f"random control mean {np.mean(ms):+.2f}% (sd {np.std(ms):.2f}) vs signal {np.mean([x[1] for x in base])*100:+.2f}%  p={(np.array(ms) >= np.mean([x[1] for x in base])*100).mean():.3f}")
print("\n--- A1 biggest winners/losers, disc>=3% vol>=1e5 ---")
for x in sorted(base, key=lambda x: x[1])[:8] + sorted(base, key=lambda x: -x[1])[:8]:
    print(f"  {x[5]:8s} {ts(x[0])} prem {x[3]*100:+.1f}% ret {x[1]*100:+.1f}% binance {x[2]*100:+.1f}% hold {x[4]:.0f}h vol {x[6]:,.0f} THB")
print("\n=== A2 Bitkub listing -> Binance spot ===")
EV = []
for s, P in PRE.items():
    a, b = P[0], P[1]; t0 = a[0, 0]
    i = int(np.searchsorted(b[:, 0], t0 + H))
    if i < 24 * 7 or i >= len(b) - 200: continue          # need a week of Binance history before the Bitkub listing
    EV.append((s, i, b[i - 1, 4] / b[i - 72, 4] - 1 if i >= 72 else np.nan))
print("listing events with prior Binance history:", len(EV), "| median 72h run-up before first Bitkub bar: %.1f%%" % (np.nanmedian([e[2] for e in EV]) * 100))
pool = list(PRE)
for off, nm in ((0, "at listing"), (24, "+24h")):
    for hold in (24, 72, 168):
        for side in (1, -1):
            tr = []
            for s, i, _ in EV:
                x = sim(PRE[s][1], i + off, side, hold, 0.25)
                if x: tr.append((x[0], x[1]))
            st = stats(tr); cs = []; ct = []
            for k in range(100):
                rng = np.random.default_rng(k); r1 = []; r2 = []
                for s, i, _ in EV:
                    b = PRE[s][1]; x = sim(b, int(rng.integers(100, len(b) - hold - 1)), side, hold, 0.25)
                    if x: r1.append(x[1])
                    for _ in range(10):
                        s2 = pool[int(rng.integers(len(pool)))]; b2 = PRE[s2][1]; j = int(np.searchsorted(b2[:, 0], b[i + off, 0]))
                        if 100 < j < len(b2) - hold - 1 and b2[j, 0] == b[i + off, 0]:
                            x = sim(b2, j, side, hold, 0.25)
                            if x: r2.append(x[1]); break
                cs.append(np.mean(r1) * 100); ct.append(np.mean(r2) * 100)
            print(fmt(f"A2 {nm} hold{hold}h {'LONG' if side > 0 else 'SHORT'}", st), f"| ctl same-coin {np.mean(cs):+.2f} p={(np.array(cs) >= st['mean']).mean():.2f} | ctl same-time {np.mean(ct):+.2f} p={(np.array(ct) >= st['mean']).mean():.2f}", flush=True)
print("\n=== A3 Bitkub BTC premium / USDT-THB premium as BTC signal (Binance BTCUSDT 1h) ===")
P = PRE["BTC"]; a, b, jc, has, prem = P
fx = get("https://query1.finance.yahoo.com/v8/finance/chart/THB=X?period1=1514764800&period2=%d&interval=1d" % int(time.time()), cache=True)["chart"]["result"][0]
fxd = {int(t) // 86400 * 86400 * 1000: c for t, c in zip(fx["timestamp"], fx["indicators"]["quote"][0]["close"]) if c}
for nm, series in (("BTC premium z(168h)", prem),):
    for Z in (2, 3):
        for sgn in (1, -1):
            z = np.full(len(a), np.nan)
            for i in range(200, len(a)):
                w = series[i - 168:i]; w = w[np.isfinite(w)]
                if len(w) > 100 and series[i] == series[i]: z[i] = (series[i] - w.mean()) / (w.std() + 1e-9)
            ev = np.nonzero(sgn * z >= Z)[0]
            for hold in (24, 72):
                for side in (1, -1):
                    tr = []; free = -1
                    for i in ev:
                        j = jc[i] + 1
                        if not has[i] or j <= free: continue
                        x = sim(b, j, side, hold, 0.10)
                        if x: tr.append((x[0], x[1])); free = x[2]
                    st = stats(tr)
                    if st["n"] >= 8: print(fmt(f"A3 {nm} {'>=+' if sgn > 0 else '<=-'}{Z} hold{hold}h {'LONG' if side > 0 else 'SHORT'}", st, rand_ctl(b, st["n"], side, hold, 0.10, seeds=200, lo=jc[200], mean_obs=st["mean"])), flush=True)
# USDT/THB on Bitkub vs FX (daily): Thai demand for dollars-on-chain
days = sorted(set(int(t) // D * D for t in UT)); up = {}
for d in days:
    i = np.searchsorted(UT, d + D, "left") - 1
    f = next((fxd[d - k * D] for k in range(0, 4) if d - k * D in fxd), None)
    if i >= 0 and f: up[d] = UC[i] / f - 1
print("USDT-THB premium vs Yahoo THB=X: days", len(up), "median %.2f%% p5 %.2f%% p95 %.2f%%" % (np.median(list(up.values())) * 100, np.percentile(list(up.values()), 5) * 100, np.percentile(list(up.values()), 95) * 100))
BD = klines("BTCUSDT", "1d", 0); ix = {int(t): i for i, t in enumerate(BD[:, 0])}; ds = sorted(up)
for Z in (2,):
    for sgn in (1, -1):
        ev = []
        for d in ds:
            p = [up[d - k * D] for k in range(1, 31) if d - k * D in up]
            if len(p) >= 20 and sgn * (up[d] - np.mean(p)) / (np.std(p) + 1e-9) >= Z: ev.append(d)
        for hold in (3, 7):
            for side in (1, -1):
                tr = []; free = -1
                for d in ev:
                    i = ix.get(d + 2 * D)
                    if i is None or i <= free: continue
                    x = sim(BD, i, side, hold, 0.15)
                    if x: tr.append((x[0], x[1])); free = x[2]
                st = stats(tr)
                if st["n"] >= 8: print(fmt(f"A3 USDT-THB prem z{'>=+' if sgn > 0 else '<=-'}{Z} hold{hold}d {'LONG' if side > 0 else 'SHORT'} BTC", st, rand_ctl(BD, st["n"], side, hold, 0.15, seeds=200, lo=ix.get(ds[0], 30), mean_obs=st["mean"])), flush=True)
