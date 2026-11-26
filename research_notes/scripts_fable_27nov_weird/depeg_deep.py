#!/usr/bin/env python3
"""Deeper check of the resting-bid depeg rule with 1-minute bars around every dip.
Timeline per pair = 1h bars, but every hour whose low <= 0.992 (and the 72 h after it) is replaced by 1m bars.
Rule: resting limit BUY at thr. Fill only when a bar trades STRICTLY below thr (fill price = min(open, thr)). Then limit SELL at out,
filled only when a LATER bar trades strictly above out (never the fill bar). Else sell at market after `maxh` hours. Optional stop.
Cost 0.15%/side. Reports fill-minute quote volume (how much size really traded at/below the bid)."""
import sys, numpy as np
from wlib import *
FIAT = "USDCUSDT TUSDUSDT FDUSDUSDT USDPUSDT PAXUSDT BUSDUSDT USD1USDT".split()
OTHER = "USTUSDT SUSDUSDT USDEUSDT USDSUSDT USDSBUSDT XUSDUSDT BFUSDUSDT USDTDAI".split()
def k1m(sym, start, n_req=5):
    fn = f"{SCR}/m_{sym}_{start}.npy"
    if os.path.exists(fn): return np.load(fn)
    out = []; s = start
    for _ in range(n_req):
        k = json.loads(raw(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1m&limit=1000&startTime={s}", tries=4))
        if not k: break
        out += [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])) for x in k]
        s = k[-1][0] + 1; time.sleep(0.05)
        if len(k) < 1000: break
    a = np.array(out, dtype=np.float64) if out else np.zeros((0, 6)); np.save(fn, a); return a
def timeline(sym):
    fn = f"{SCR}/tl_{sym}.npy"
    if os.path.exists(fn): return np.load(fn)
    a = klines(sym, "1h", 0); parts = []; i = 0; n = len(a); nwin = 0
    while i < n:
        if a[i, 3] <= 0.992 and i > 100:
            m = k1m(sym, int(a[i, 0])); nwin += 1
            if len(m):
                parts.append(m); tend = m[-1, 0] + 60000
                while i < n and a[i, 0] < tend: i += 1
                continue
        parts.append(a[i:i + 1]); i += 1
    tl = np.vstack(parts); np.save(fn, tl); print(sym, "1h bars", n, "1m windows", nwin, "timeline rows", len(tl), flush=True); return tl
TL = {}
for s in FIAT + OTHER:
    if len(klines(s, "1h", 0)) > 500: TL[s] = timeline(s)
def run(a, thr, out, maxh, stop):
    tr = []; i = 100; n = len(a)
    while i < n - 1:
        if a[i, 3] < thr:
            e = min(a[i, 1], thr); t0 = a[i, 0]; vol = a[i, 5]; px = None; j = None; why = "limit"
            for k in range(i + 1, n):
                if a[k, 0] - t0 > maxh * H: px = a[k, 1]; j = k; why = "timeout"; break
                if stop is not None and a[k, 3] <= e * (1 - stop): px = min(a[k, 1], e * (1 - stop)); j = k; why = "stop"; break
                if a[k, 2] > out: px = max(out, a[k, 1]); j = k; break
            if px is None:                      # data ended (delisting) before any exit: mark at the last close (v1 dropped these = hid UST)
                j = n - 1; px = a[j, 4]; why = "delisted" if a[j, 0] < time.time() * 1000 - 3 * D else "open"
            tr.append((int(t0), px / e - 1 - 0.003, (a[j, 0] - t0) / H, vol, why, e)); i = j + 1
        else: i += 1
    return tr
def show(name, tr):
    st = stats([(x[0], x[1]) for x in tr])
    if st["n"] < 8: print(f"{name:58s} n={st['n']}", [f"{ts(x[0])} {x[1]*100:+.1f}" for x in tr]); return st
    yrs = collections.defaultdict(list)
    for x in tr: yrs[time.gmtime(x[0] / 1000).tm_year].append(x[1])
    w = collections.Counter(x[4] for x in tr)
    print(fmt(name, st), f"exit={dict(w)} medhold={np.median([x[2] for x in tr]):.1f}h p90hold={np.percentile([x[2] for x in tr], 90):.0f}h fillvol med=${np.median([x[3] for x in tr]):,.0f} p10=${np.percentile([x[3] for x in tr], 10):,.0f}",
          "| yr " + " ".join(f"{y}:{np.mean(v)*100:+.2f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
    return st
for grp, names in (("FIAT-backed", FIAT), ("OTHER(algo/synthetic/new)", OTHER), ("ALL", FIAT + OTHER)):
    print(f"\n=== {grp}: {[s for s in names if s in TL]} ===")
    for thr in (0.99, 0.985, 0.98, 0.975, 0.97, 0.96, 0.95):
        for out in (0.999, 0.995):
            for maxh, stop in ((720, None), (720, 0.05), (72, None)):
                tr = []
                for s in names:
                    if s in TL: tr += [x + (s,) for x in run(TL[s], thr, out, maxh, stop)]
                show(f"{grp[:5]} bid{thr} sell{out} max{maxh}h stop{stop}", tr)
print("\n=== FIAT bid0.98 sell0.999 max720h no stop: every trade ===")
for s in FIAT:
    if s in TL:
        for x in run(TL[s], 0.98, 0.999, 720, None): print(f"{s:10s} {ts(x[0])} fill {x[5]:.4f} ret {x[1]*100:+.2f}% hold {x[2]:7.1f}h fill-bar vol ${x[3]:,.0f} {x[4]}")
print("\n=== per pair, bid0.98 sell0.999 max720h no stop ===")
for s in TL:
    tr = run(TL[s], 0.98, 0.999, 720, None)
    print(f"{s:10s} n={len(tr):3d} mean={np.mean([x[1] for x in tr])*100 if tr else 0:+.2f} worst={min([x[1] for x in tr])*100 if tr else 0:+.1f}")
# time-split out of sample: thresholds looked at on <=2022, report 2023+ separately
print("\n=== FIAT, split at 2023-01-01 ===")
for thr in (0.985, 0.98, 0.97):
    tr = []
    for s in FIAT:
        if s in TL: tr += run(TL[s], thr, 0.999, 720, None)
    a = [x for x in tr if x[0] < 1672531200000]; b = [x for x in tr if x[0] >= 1672531200000]
    show(f"FIAT bid{thr} <=2022", a); show(f"FIAT bid{thr} 2023-2026 (OOS)", b)

print("\n=== v2 extras ===")
def fiat(thr, out=0.999, maxh=720, stop=None):
    tr = []
    for s in FIAT:
        if s in TL: tr += [x + (s,) for x in run(TL[s], thr, out, maxh, stop)]
    return tr
for thr in (0.99, 0.985, 0.98, 0.97):
    tr = fiat(thr)
    # one trade per calendar day across all pairs (equal split of that day's fills) = independent events
    day = collections.defaultdict(list)
    for x in tr: day[x[0] // D].append(x[1])
    dd = [(d * D, float(np.mean(v))) for d, v in sorted(day.items())]
    show(f"FIAT bid{thr} per-DAY (independent events)", [(t, r, 0, 0, "limit", 0) for t, r in dd])
    r = np.array([x[1] for x in tr])
    print(f"   fee sensitivity bid{thr}: 0.15%/side {r.mean()*100:+.2f} | 0.075%/side {(r.mean()+0.0015)*100:+.2f} | 0 fee {(r.mean()+0.003)*100:+.2f} | trades per pair-year {len(tr)/sum((TL[s][-1,0]-TL[s][0,0])/(365*D) for s in FIAT if s in TL):.2f}")
# random-entry control: market buy at a random bar open on the same pairs, same exit (limit 0.999 / 720 h)
cnt = collections.Counter(x[-1] for x in fiat(0.985)); ms = []
for k in range(200):
    rng = np.random.default_rng(k); rr = []
    for s, c in cnt.items():
        a = TL[s]
        for i in rng.integers(100, len(a) - 2, c):
            e = a[i, 1]; t0 = a[i, 0]; px = None
            for q in range(int(i) + 1, len(a)):
                if a[q, 0] - t0 > 720 * H: px = a[q, 1]; break
                if a[q, 2] > 0.999: px = max(0.999, a[q, 1]); break
            if px is None: px = a[-1, 4]
            rr.append(px / e - 1 - 0.003)
    ms.append(np.mean(rr) * 100)
print(f"random-entry control (same pairs, random times, same exit): mean {np.mean(ms):+.3f}% sd {np.std(ms):.3f}  vs rule bid0.985 {np.mean([x[1] for x in fiat(0.985)])*100:+.2f}%  p={(np.array(ms) >= np.mean([x[1] for x in fiat(0.985)])*100).mean():.3f}")
print("worst fiat-backed moments (lowest 1m low per pair):")
for s in FIAT:
    if s in TL:
        a = TL[s]; i = int(np.argmin(a[:, 3])); print(f"   {s:10s} low {a[i,3]:.4f} at {ts(a[i,0])}")
print("non-fiat, bid0.985 no stop, every losing or delisted trade:")
for s in OTHER:
    if s in TL:
        for x in run(TL[s], 0.985, 0.999, 720, None):
            if x[1] < 0 or x[4] != "limit": print(f"   {s:10s} {ts(x[0])} ret {x[1]*100:+.1f}% {x[4]} hold {x[2]:.0f}h")
