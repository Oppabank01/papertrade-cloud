"""Own idea: turn-of-month / payday flow on SET (provident-fund and salary money arrives at month end). TDEX (SET50 ETF)
and big caps, Yahoo daily. Buy the close `pre` trading days before the first trading day of a month, sell the close `post`
days after it. Cost 0.17%/side. Control: random start days, same holding length (300 draws). Also mid-month as placebo."""
import time, numpy as np, r2lib as L
C = 0.0017
def run(sym, pre, post, y0=2010, shift=0):
    d = L.yahoo(sym); t = d["t"]; c = d["c"]; g = [time.gmtime(int(x) + 7 * 3600) for x in t]
    first = [i for i in range(1, len(t)) if g[i].tm_mon != g[i - 1].tm_mon and g[i].tm_year >= y0]
    tr = []
    for f in first:
        a = f - pre + shift; z = f + post + shift
        if a < 1 or z >= len(t): continue
        tr.append((int(t[a]) * 1000, c[z] / c[a] - 1 - 2 * C))
    h = pre + post; lo = first[0]
    pool = np.array([c[i + h] / c[i] - 1 - 2 * C for i in range(lo, len(t) - h)])
    st = L.stats(tr); ms = np.array([np.random.default_rng(z).choice(pool, st["n"]).mean() * 100 for z in range(300)])
    y = lambda a, b: np.mean([r for tt, r in tr if a <= time.gmtime(tt / 1000).tm_year < b]) * 100
    return L.fmt(f"{sym} T-{pre}..T+{post}{' (placebo +10d)' if shift else ''}", st, dict(mean=float(pool.mean() * 100), med=float(np.median(pool) * 100), p=float((ms >= st["mean"]).mean()))) + f" | 2010-17 {y(2010,2018):+.2f} 2018-22 {y(2018,2023):+.2f} 2023-26 {y(2023,2030):+.2f}"
for sym in ("TDEX.BK", "PTT.BK", "CPALL.BK", "ADVANC.BK", "KBANK.BK", "AOT.BK", "SCC.BK", "BDMS.BK"):
    for pre, post in ((1, 3), (2, 3), (3, 1), (1, 1), (4, 0), (5, 5)):
        print(run(sym, pre, post)[:330])
    print(run(sym, 2, 3, shift=10)[:330])
