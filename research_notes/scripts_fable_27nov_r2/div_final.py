"""Pre-XD run-up: headline table. Both universes (169 first-list tickers = in-sample, 252 fresh tickers = out-of-sample).
Rule: an XD with dividend / last close >= Y is known; buy the OPEN n trading days before XD (i-n), sell the CLOSE of the last
cum-dividend day (i-1). 0.17%/side. Stop 8% checked first on daily lows (fill min(open, stop)). No dividend is received."""
import os, json, time, collections, numpy as np, r2lib as L
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_deep.py")).read()
head = src.split("# 1) day-by-day gross profile")[0]; fn_src = "def tr_pre" + src.split("def tr_pre")[1].split('print("\\n=== grid')[0]
src5 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_n5.py")).read(); open_src = "def tr_open" + src5.split("def tr_open")[1].split("def rep2")[0]
OOS = json.load(open(f"{L.R2}/oos_tickers.json")); U = {}
for lab, repl in (("first list (in-sample)", None), ("fresh list (out-of-sample)", "for s in OOS:")):
    g = {"OOS": OOS, "__file__": os.path.abspath(__file__)}; exec(head if repl is None else head.replace("for s in SET:", repl), g); exec(fn_src, g); exec(open_src, g); U[lab] = g
def trades(g, n, ymin, stop, ctl_kind=None, seed=0):
    out = []
    rng = np.random.default_rng(seed)
    for s, i, amt in g["EV"]:
        d = g["S"][s]
        if amt / d["c"][i - 1 - n] < ymin: continue
        if ctl_kind == "rand":
            i = int(rng.integers(40, len(d["t"]) - 5))
            if d["t"][i] < 1262304000: continue
        t, r, a, b = g["tr_open"](s, i, amt, n, stop=stop); out.append((t, r))
    return out
for n, ymin, stop in ((6, 0.04, 0.08), (5, 0.04, 0.08), (6, 0.03, 0.08), (6, 0.05, 0.08), (6, 0.04, None)):
    print(f"\n### buy OPEN i-{n}, sell close i-1, yield >= {ymin*100:.0f}%, stop {stop} ###")
    allt = []
    for lab, g in U.items():
        tr = trades(g, n, ymin, stop); allt += tr; st = L.stats(tr)
        cm = np.array([np.mean([r for t, r in trades(g, n, ymin, stop, "rand", z)]) * 100 for z in range(60)])
        print(L.fmt(lab, st, dict(mean=float(cm.mean()), med=float(np.median(cm)), p=float((cm >= st["mean"]).mean())))[:300])
        by = collections.defaultdict(list)
        for t, r in tr: by[time.gmtime(t / 1000).tm_year].append(r)
        print("   year: " + " ".join(f"{str(y)[2:]}:{len(v)}/{np.mean(v)*100:+.1f}" for y, v in sorted(by.items())))
    st = L.stats(allt); print(L.fmt("both lists", st)[:260])
    r = np.array([x[1] for x in sorted(allt)]); q = len(r) // 4
    print("   quarters of the trade list in time order: " + " ".join(f"{r[k*q:(k+1)*q if k < 3 else len(r)].mean()*100:+.2f}" for k in range(4)) +
          f" | losing trades {np.mean(r<0)*100:.0f}% | 5th pct {np.percentile(r,5)*100:+.1f}% 95th {np.percentile(r,95)*100:+.1f}% | stop hit {np.mean(r<=-0.08)*100:.1f}%")
    bm = collections.Counter(time.gmtime(t / 1000).tm_mon for t, _ in allt if time.gmtime(t / 1000).tm_year >= 2023)
    yrs = 3.9; print("   trades per calendar month, 2023-26 average: " + " ".join(f"{m}:{bm.get(m,0)/yrs:.1f}" for m in range(1, 13)) + f" | per year {sum(bm.values())/yrs:.0f}")
# what the late dividend chaser gets: buy close i-1, sell close i+3, dividend net of 10% tax
print("\n### the other side: buy the last cum-dividend close, take the dividend (10% tax), sell close i+3; yield>=4% ###")
for lab, g in U.items():
    tr = []
    for s, i, amt in g["EV"]:
        c = g["S"][s]["c"]
        if amt / c[i - 1] < 0.04: continue
        tr.append((int(g["S"][s]["t"][i]) * 1000, (c[i + 3] + 0.9 * amt) / c[i - 1] - 1 - 2 * 0.0017))
    print(L.fmt(lab, L.stats(tr))[:230])

# tradable subset: 20-day median turnover >= 5M THB at entry (both lists pooled), with and without stop, with tick/spread stress
print("\n### pooled, turnover >= 5M THB/day (and >= 20M), buy OPEN i-n, sell close i-1 ###")
def pooled(n, ymin, stop, liqmin, extra=0.0):
    out = []
    for lab, g in U.items():
        for s, i, amt in g["EV"]:
            d = g["S"][s]
            if amt / d["c"][i - 1 - n] < ymin or d["liq"][i - 1 - n] < liqmin: continue
            t, r, a, b = g["tr_open"](s, i, amt, n, stop=stop, extra=extra); out.append((t, r))
    return out
for n in (6, 5):
    for ymin in (0.03, 0.04, 0.05):
        for liqmin in (5e6, 2e7):
            for stop, extra in ((None, 0), (0.08, 0), (None, 0.0025)):
                tr = pooled(n, ymin, stop, liqmin, extra); st = L.stats(tr)
                e = lambda a, b: [r for t, r in tr if a <= time.gmtime(t / 1000).tm_year < b]
                print(L.fmt(f"n={n} y>={ymin*100:.0f}% liq>={liqmin/1e6:.0f}M stop {stop} extra {extra*100:.2f}%", st)[:215] + f" | 2010-17 n{len(e(2010,2018))} {np.mean(e(2010,2018))*100:+.2f} 2018-22 n{len(e(2018,2023))} {np.mean(e(2018,2023))*100:+.2f} 2023-26 n{len(e(2023,2030))} {np.mean(e(2023,2030))*100:+.2f}")
