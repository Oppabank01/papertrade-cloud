"""Pre-XD run-up, the look-ahead-safe versions only (n=5 and n=6 trading days before XD; the day-by-day profile in
div_deep.out shows the announcement bump at offsets -9..-7, so n>=7 is contaminated by announcement-day jumps).
Adds: realistic entry at the NEXT OPEN, exit at the open of the last cum day, stop 8%, cost stress, liquidity, year table,
out-of-sample split, calendar-time portfolio."""
import os, time, collections, numpy as np
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_deep.py")).read()
exec(src.split("# 1) day-by-day gross profile")[0]); exec("def tr_pre" + src.split("def tr_pre")[1].split('print("\\n=== grid')[0])
def tr_open(s, i, amt, n, stop=None, extra=0.0, exit_open=False):
    """decide after the close of i-1-n, buy the OPEN of i-n, sell close of i-1 (or its open)"""
    d = S[s]; a = i - n; b = i - 1; e = d["o"][a]; px = d["o"][b] if exit_open else d["c"][b]
    if stop:
        for k in range(a, b + 1):
            if d["l"][k] <= e * (1 - stop): px = min(d["o"][k], e * (1 - stop)); break
    return int(d["t"][a]) * 1000, px / e - 1 - 2 * (C + extra), a, b
def rep2(name, evs, f):
    tt = [f(s, i, amt)[:2] for s, i, amt in evs]; st = L.stats(tt)
    if st["n"] < 8: print(name, "n", st["n"]); return tt
    mt, nm = mclust_t(tt)
    A = [r for t, r in tt if time.gmtime(t / 1000).tm_year < 2018]; B = [r for t, r in tt if 2018 <= time.gmtime(t / 1000).tm_year < 2023]; Cc = [r for t, r in tt if time.gmtime(t / 1000).tm_year >= 2023]
    print(L.fmt(name, st) + f" | month-t {mt:+.1f}({nm}m) | 2010-17 n{len(A)} {np.mean(A)*100:+.2f} 2018-22 n{len(B)} {np.mean(B)*100:+.2f} 2023-26 n{len(Cc)} {np.mean(Cc)*100:+.2f}")
    return tt
for n in (5, 6):
    print(f"\n=== n={n}: decide after the close of day i-{n+1}, i = XD day ===")
    for ymin in (0.02, 0.03, 0.04, 0.05):
        e = ysel(EV, n, ymin); lab = f"n={n} y>={ymin*100:.0f}%"
        tt = report(f"{lab} buy close i-{n+1}, sell close i-1", e, n, ctl=True)
        by = collections.defaultdict(list)
        for t, r in tt: by[time.gmtime(t / 1000).tm_year].append(r)
        print("   by year: " + " ".join(f"{y}:n{len(v)} {np.mean(v)*100:+.2f}" for y, v in sorted(by.items())))
        rep2(f"{lab} buy OPEN i-{n}, sell close i-1", e, lambda s, i, amt: tr_open(s, i, amt, n))
        rep2(f"{lab} buy OPEN i-{n}, sell OPEN i-1", e, lambda s, i, amt: tr_open(s, i, amt, n, exit_open=True))
        rep2(f"{lab} buy OPEN i-{n}, sell close i-1, stop 8%", e, lambda s, i, amt: tr_open(s, i, amt, n, stop=0.08))
        rep2(f"{lab} buy OPEN i-{n}, sell close i-1, +0.25%/side", e, lambda s, i, amt: tr_open(s, i, amt, n, extra=0.0025))
        el = ysel(EV, n, ymin, liq=2e7, nofund=True)
        rep2(f"{lab} liquid>=20M THB/day no funds, buy OPEN i-{n}, sell close i-1", el, lambda s, i, amt: tr_open(s, i, amt, n))
        el2 = ysel(EV, n, ymin, liq=1e8, nofund=True)
        rep2(f"{lab} liquid>=100M THB/day no funds, buy OPEN i-{n}, sell close i-1", el2, lambda s, i, amt: tr_open(s, i, amt, n))
    print(f"  calendar-time portfolio n={n} (close-to-close, liquid>=20M):")
    for ymin in (0.03, 0.04):
        for K in (3, 5):
            evs = ysel(EV, n, ymin, liq=2e7)
            tk, cagr, dd, c1, c2 = portfolio(evs, n, K) if False else (None,) * 5
# top contributors and concentration by ticker for the headline rule
e = ysel(EV, 5, 0.04); tt = [(s, tr_pre(s, i, amt, 5)[1], S[s]["day"][i]) for s, i, amt in e]
bt = collections.defaultdict(list)
for s, r, d in tt: bt[s].append(r)
top = sorted(bt.items(), key=lambda kv: -sum(kv[1]))[:8]
print("\nheadline rule n=5 y>=4%: tickers", len(bt), "| biggest total contributors:", " ".join(f"{s}:n{len(v)} sum{sum(v)*100:+.0f}" for s, v in top))
tot = sum(sum(v) for v in bt.values()); print(f"   total {tot*100:+.0f} points; without the top 8 tickers mean {np.mean([r for s, v in bt.items() if s not in dict(top) for r in v])*100:+.2f}%")
ev_per_year = collections.Counter(time.gmtime(int(d) * 86400).tm_year for s, r, d in tt); print("   trades per year:", dict(sorted(ev_per_year.items())))
