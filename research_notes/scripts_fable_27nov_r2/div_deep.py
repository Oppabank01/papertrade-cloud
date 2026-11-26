"""Pre-XD run-up on SET, robustness. Rule family: buy the close n trading days before XD, sell the close of the last
cum-dividend day (i-1), so no dividend and no withholding tax. Cost 0.17%/side (stress +0.25%/side).
Look-ahead guard: SET requires the record date to be announced >= 14 days ahead and XD = record date - 1 business day, so
entries n <= 7 trading days before XD are after the announcement. Yield filter uses the ENTRY price (known at entry).
Checks: day-by-day profile, random days same stock, same dates in other stocks with no XD nearby, month-clustered t,
years, liquid only, funds/REITs out, stop 8% checked first on daily lows, calendar-time portfolio."""
import sys, os, time, math, collections, numpy as np, r2lib as L
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_yahoo.py")).read().split("ok = []")[0])
C = 0.0017; Y0 = 2010
FUNDS = set("BTSGIF CPNREIT DIF EGATIF FTREIT KTBSTMR LHHOTEL TFFIF WHART".split())
idx = L.yahoo("TDEX.BK"); iday = (idx["t"] + 7 * 3600) // 86400; ic = idx["c"]
S = {}
for s in SET:
    d = L.yahoo(s + ".BK")
    if d is None or len(d["t"]) < 300: continue
    d["day"] = (d["t"] + 7 * 3600) // 86400
    to = d["c"] * d["v"]; d["liq"] = np.array([np.median(to[max(0, k - 20):k]) if k >= 5 else 0 for k in range(len(to))])
    d["xd"] = np.zeros(len(d["t"]), bool); S[s] = d
EV = []
for s, d in S.items():
    for ts_, amt in sorted(d["div"].items()):
        dd = (ts_ + 7 * 3600) // 86400; i = int(np.searchsorted(d["day"], dd))
        if i < 30 or i >= len(d["t"]) - 21 or d["day"][i] - dd > 4: continue
        d["xd"][i] = True
        if time.gmtime(d["t"][i]).tm_year < Y0 or d["v"][i - 1] <= 0: continue
        if not (0.001 < amt / d["c"][i - 1] < 0.25): continue
        EV.append((s, i, amt))
print("tickers", len(S), "events", len(EV))
# 1) day-by-day gross profile
prof = collections.defaultdict(list)
for s, i, amt in EV:
    d = S[s]; c = d["c"]; y = amt / c[i - 11]
    for k in range(-25, 11):
        r = (c[i + k] + (amt if k == 0 else 0)) / c[i + k - 1] - 1
        prof[("all", k)].append(r)
        if y >= 0.03: prof[("y>=3%", k)].append(r)
for lab in ("all", "y>=3%"):
    print(f"daily gross close-to-close mean, bp, offsets -25..+10 (0 = XD day incl. gross dividend) [{lab}] n={len(prof[(lab, 0)])}")
    print("  " + " ".join(f"{k:+d}:{np.mean(prof[(lab, k)])*1e4:+.0f}" for k in range(-25, 11)))
def tr_pre(s, i, amt, n, x=1, stop=None, extra=0.0):
    d = S[s]; a = i - x - n; b = i - x; c = d["c"]; e = c[a]
    px = c[b]
    if stop:
        for k in range(a + 1, b + 1):
            if d["l"][k] <= e * (1 - stop): px = min(d["o"][k], e * (1 - stop)); break
    return int(d["t"][a]) * 1000, px / e - 1 - 2 * (C + extra), a, b
def mclust_t(tr):
    m = collections.defaultdict(list)
    for t, r in tr: g = time.gmtime(t / 1000); m[(g.tm_year, g.tm_mon)].append(r)
    v = np.array([np.mean(x) for x in m.values()]); return v.mean() / (v.std() + 1e-12) * math.sqrt(len(v)), len(v)
def controls(evs, n, x=1, seeds=100):
    lo = {s: int(np.searchsorted(S[s]["t"], 1262304000)) for s in S}; names = list(S); m1 = []; m2 = []
    for z in range(seeds):
        rng = np.random.default_rng(z); r1 = []; r2 = []
        for s, i, amt in evs:
            d = S[s]; a = int(rng.integers(max(lo[s], 30), len(d["t"]) - n - 2)); r1.append(d["c"][a + n] / d["c"][a] - 1 - 2 * C)
            d0 = d["day"][i - x - n]; d1 = d["day"][i - x]
            for _ in range(6):                    # same dates, another stock with no XD within 30 bars either side
                o = S[names[int(rng.integers(len(names)))]]; a2 = int(np.searchsorted(o["day"], d0)); b2 = int(np.searchsorted(o["day"], d1))
                if a2 < 30 or b2 >= len(o["day"]) - 30 or o["day"][a2] != d0 or o["day"][b2] != d1 or o["xd"][a2 - 30:b2 + 30].any(): continue
                r2.append(o["c"][b2] / o["c"][a2] - 1 - 2 * C); break
        m1.append(np.mean(r1) * 100); m2.append(np.mean(r2) * 100)
    return np.array(m1), np.array(m2)
def report(name, evs, n, x=1, stop=None, extra=0.0, ctl=True):
    tr = [tr_pre(s, i, amt, n, x, stop, extra) for s, i, amt in evs]; tt = [(t, r) for t, r, a, b in tr]
    st = L.stats(tt)
    if st["n"] < 8: print(name, "n", st["n"]); return tt
    mt, nm = mclust_t(tt); s_ = L.fmt(name, st)
    ins = [r for t, r in tt if time.gmtime(t / 1000).tm_year < 2020]; oos = [r for t, r in tt if time.gmtime(t / 1000).tm_year >= 2020]
    s_ += f" | month-t {mt:+.1f}({nm}m) | 2010-19 n{len(ins)} {np.mean(ins)*100:+.2f} 2020-26 n{len(oos)} {np.mean(oos)*100:+.2f}"
    if ctl:
        m1, m2 = controls(evs, n, x)
        s_ += f" | ctl same stock random days {m1.mean():+.2f} (p {(m1 >= st['mean']).mean():.3f}) same dates other stock {m2.mean():+.2f} (p {(m2 >= st['mean']).mean():.3f})"
    print(s_); return tt
def ysel(evs, n, ymin, x=1, liq=0, nofund=False):
    return [(s, i, amt) for s, i, amt in evs if amt / S[s]["c"][i - x - n] >= ymin and S[s]["liq"][i - x - n] >= liq and not (nofund and s in FUNDS)]
print("\n=== grid: n days before XD, exit close i-1 (x=1) ===")
for n in (3, 4, 5, 6, 7, 8, 10):
    for ymin in (0, 0.02, 0.03, 0.04, 0.05):
        report(f"PRE n={n} yield@entry>={ymin*100:.0f}%", ysel(EV, n, ymin), n, ctl=(n in (5, 7) and ymin in (0, 0.03)))
print("\n=== variants at n=7 ===")
for ymin in (0, 0.03, 0.04):
    e = ysel(EV, 7, ymin)
    report(f"n=7 y>={ymin*100:.0f}% exit close i-2 (x=2)", ysel(EV, 7, ymin, x=2), 7, x=2, ctl=False)
    report(f"n=7 y>={ymin*100:.0f}% stop 8%", e, 7, stop=0.08, ctl=False)
    report(f"n=7 y>={ymin*100:.0f}% extra 0.25%/side (tick/spread stress)", e, 7, extra=0.0025, ctl=False)
    report(f"n=7 y>={ymin*100:.0f}% liquid (20d median turnover >= 20M THB)", ysel(EV, 7, ymin, liq=2e7), 7, ctl=False)
    report(f"n=7 y>={ymin*100:.0f}% liquid, no funds/REITs", ysel(EV, 7, ymin, liq=2e7, nofund=True), 7, ctl=(ymin == 0.03))
    tt = report(f"n=7 y>={ymin*100:.0f}% (again, for the year table)", e, 7, ctl=False)
    by = collections.defaultdict(list)
    for t, r in tt: by[time.gmtime(t / 1000).tm_year].append(r)
    print("   by year: " + " ".join(f"{y}:n{len(v)} {np.mean(v)*100:+.2f}" for y, v in sorted(by.items())))
    bm = collections.defaultdict(list)
    for t, r in tt: bm[time.gmtime(t / 1000).tm_mon].append(r)
    print("   by entry month: " + " ".join(f"{m}:n{len(v)} {np.mean(v)*100:+.2f}" for m, v in sorted(bm.items())))
# calendar-time portfolio: up to K equal slots, each trade takes one free slot (skip if none)
print("\n=== calendar-time portfolio (n=7, exit i-1, slots of 1/K of equity, skip when full) ===")
alld = np.unique(np.concatenate([d["day"] for d in S.values()])); alld = alld[alld >= 14610]
def portfolio(evs, n, K):
    trs = sorted((S[s]["day"][i - 1 - n], S[s]["day"][i - 1], S[s]["c"][i - 1] / S[s]["c"][i - 1 - n] - 1 - 2 * C) for s, i, amt in evs)
    eq = 1.0; open_ = []; curve = {}; k = 0; taken = 0
    for dday in alld:
        for e in [o for o in open_ if o[0] <= dday]:
            eq += e[1] * e[2]; open_.remove(e)
        while k < len(trs) and trs[k][0] <= dday:
            if trs[k][0] == dday and len(open_) < K: open_.append((trs[k][1], eq / K, trs[k][2])); taken += 1
            k += 1
        curve[int(dday)] = eq
    v = np.array(list(curve.values())); yrs = (alld[-1] - alld[0]) / 365.25; dd = (v / np.maximum.accumulate(v) - 1).min()
    half = len(v) // 2; c1 = (v[half] / v[0]) ** (1 / (yrs / 2)) - 1; c2 = (v[-1] / v[half]) ** (1 / (yrs / 2)) - 1
    return taken, (v[-1]) ** (1 / yrs) - 1, dd, c1, c2
a = np.searchsorted(iday, alld[0]); print(f"TDEX (SET50 ETF, price only) CAGR {((ic[-1]/ic[a]) ** (365.25/(iday[-1]-iday[a])) - 1)*100:+.1f}%/yr over the same years")
for ymin in (0, 0.02, 0.03, 0.04):
    for K in (5, 10):
        tk, cagr, dd, c1, c2 = portfolio(ysel(EV, 7, ymin, liq=2e7), 7, K)
        print(f"  yield>={ymin*100:.0f}% liquid, {K} slots: trades taken {tk}  CAGR {cagr*100:+.1f}%/yr  max drawdown {dd*100:.1f}%  first half {c1*100:+.1f}%/yr second half {c2*100:+.1f}%/yr (booked at exit, cash earns 0)")
