"""Bitkub payday / day-of-month. Bitkub 1h bars (round-1 cache) vs Binance spot 1h. Bangkok calendar days.
1) BTC and ETH premium on Bitkub (coin_THB / USDT_THB / coin_USDT on Binance - 1) by day of month.
2) USDT_THB vs Yahoo USD/THB daily close: premium by day of month.
3) Long-only drift on Bitkub itself: buy BTC_THB/ETH_THB/USDT_THB at the 00:00 Bangkok open of day A, sell at the open of day B
   (next month if B < A). Cost 0.25%/side. Control: the same holding length from every other start day; Binance same window."""
import time, glob, os, numpy as np, r2lib as L
SCRW = L.wlib.SCR; H = L.H; D = L.D
def bk(s):
    a = np.load(f"{SCRW}/bk_{s}.npy").copy(); a[:, 0] = (a[:, 0] // H) * H
    return a[np.concatenate([[True], np.diff(a[:, 0]) > 0])]
def bn(s):
    fs = glob.glob(f"{SCRW}/k_{s}USDT_1h_*.npy"); return np.load(max(fs, key=os.path.getsize))
U = bk("USDT")
def daily(a):
    """Bangkok-day open series: dict day -> (open of first bar at/after 00:00 Bangkok, close of the last bar)"""
    day = ((a[:, 0] + 7 * H) // D).astype(np.int64); out = {}
    first = np.concatenate([[True], np.diff(day) > 0]); last = np.concatenate([np.diff(day) > 0, [True]])
    for d, o, c in zip(day[first], a[first, 1], a[last, 4]): out[int(d)] = (o, c)
    return out
def dom(d): return time.gmtime(d * 86400).tm_mday
def ym(d): g = time.gmtime(d * 86400); return g.tm_year * 12 + g.tm_mon
Ud = daily(U)
print("USDT_THB bars", len(U), L.ts(U[0, 0]), L.ts(U[-1, 0]))
# 1) premium by day of month
for s in ("BTC", "ETH"):
    a = bk(s); b = bn(s); j = np.clip(np.searchsorted(b[:, 0], a[:, 0]), 0, len(b) - 1); has = b[j, 0] == a[:, 0]
    ui = np.clip(np.searchsorted(U[:, 0], a[:, 0], "right") - 1, 0, len(U) - 1); okU = (a[:, 0] - U[ui, 0]) <= 6 * H
    m = has & okU & (a[:, 0] >= U[0, 0])
    prem = (a[m, 4] / U[ui[m], 4]) / b[j[m], 4] - 1; day = ((a[m, 0] + 7 * H) // D).astype(np.int64)
    days = np.unique(day); pd_ = np.array([np.median(prem[day == d]) for d in days]); dm = np.array([dom(int(d)) for d in days])
    yr = np.array([time.gmtime(int(d) * 86400).tm_year for d in days])
    for lab, mk in (("all", yr > 0), ("2023+", yr >= 2023)):
        row = " ".join(f"{k}:{np.mean(pd_[mk & (dm == k)])*1e4:+.0f}" for k in range(1, 32))
        pay = mk & ((dm >= 25) | (dm <= 2)); rest = mk & ~((dm >= 25) | (dm <= 2))
        se = pd_[mk].std() / np.sqrt(pay.sum())
        print(f"{s} premium bp by day of month [{lab}] n_days {mk.sum()}: {row}\n   payday window 25..2: {pd_[pay].mean()*1e4:+.1f} bp vs rest {pd_[rest].mean()*1e4:+.1f} bp (se about {se*1e4:.1f})")
# 2) USDT_THB vs Yahoo USD/THB
y = L.yahoo("THB=X"); yday = (y["t"] // 86400).astype(np.int64); yc = dict(zip(yday.tolist(), y["c"].tolist()))
ds = sorted(d for d in Ud if d in yc and yc[d] > 20); pu = np.array([Ud[d][1] / yc[d] - 1 for d in ds]); dm = np.array([dom(d) for d in ds]); yr = np.array([time.gmtime(d * 86400).tm_year for d in ds])
pu_ok = np.abs(pu) < 0.1
for lab, mk in (("all", pu_ok), ("2023+", pu_ok & (yr >= 2023))):
    row = " ".join(f"{k}:{np.mean(pu[mk & (dm == k)])*1e4:+.0f}" for k in range(1, 32))
    pay = mk & ((dm >= 25) | (dm <= 2)); rest = mk & ~((dm >= 25) | (dm <= 2))
    print(f"USDT_THB premium over USD/THB bp by day of month [{lab}] n {mk.sum()}: {row}\n   payday window: {pu[pay].mean()*1e4:+.1f} vs rest {pu[rest].mean()*1e4:+.1f}")
# 3) long-only drift on Bitkub
def drift(s, A, B, cost=0.0025):
    dd = daily(bk(s)); bd = daily(bn(s)) if s != "USDT" else None; days = sorted(dd); tr = []; trb = []; idx = {d: k for k, d in enumerate(days)}
    for d in days:
        if dom(d) != A: continue
        e = d + 1
        while e in dd and dom(e) != B and e - d < 40: e += 1
        if e not in dd or dom(e) != B: continue
        r = dd[e][0] / dd[d][0] - 1 - 2 * cost; tr.append((d * D, r))
        if bd and d in bd and e in bd: trb.append(bd[e][0] / bd[d][0] - 1)
    if len(tr) < 8: return None
    hold = int(round(np.mean([1]))) ; L_ = int(np.median([(B - A) % 30 or 30]))
    allr = np.array([dd[days[k + L_]][0] / dd[days[k]][0] - 1 - 2 * cost for k in range(len(days) - L_)])
    st = L.stats(tr); ms = np.array([np.random.default_rng(z).choice(allr, st["n"]).mean() * 100 for z in range(300)])
    return L.fmt(f"{s}_THB buy day {A} sell day {B}", st, dict(mean=float(allr.mean() * 100), med=float(np.median(allr) * 100), p=float((ms >= st["mean"]).mean()))) + (f" | Binance same window {np.mean(trb)*100:+.2f}" if trb else "")
print()
for s in ("BTC", "ETH", "USDT"):
    for A, B in ((20, 25), (22, 28), (24, 1), (25, 1), (25, 28), (26, 2), (28, 3), (28, 5), (1, 5), (1, 10), (5, 20), (10, 20), (15, 25)):
        x = drift(s, A, B)
        if x: print(x)
