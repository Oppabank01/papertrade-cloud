"""Own idea: one-day crash in a SET large/mid cap that the index did not share -> buy the next open, hold a few days.
Signal day i: close/prev close - 1 <= -X (dividend added back on XD days), SET50 ETF (TDEX) that day >= -2%, price >= 1 THB,
20-day median turnover >= 20M THB. Entry next open; exit close after `hold` days; stop 10% checked first on daily lows
(fill min(open, stop)). Cost 0.17%/side. Control: random days, same stock. Survivorship: today's tickers only (flagged)."""
import os, time, numpy as np, r2lib as L, json, sys
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_yahoo.py")).read().split("ok = []")[0])
UNI = SET if len(sys.argv) < 2 else json.load(open(f"{L.R2}/oos_tickers.json"))
C = 0.0017; idx = L.yahoo("TDEX.BK"); iday = (idx["t"] + 7 * 3600) // 86400; ir = np.concatenate([[0], idx["c"][1:] / idx["c"][:-1] - 1]); imap = dict(zip(iday.tolist(), ir.tolist()))
S = {}
for s in UNI:
    d = L.yahoo(s + ".BK")
    if d is None or len(d["t"]) < 300: continue
    day = (d["t"] + 7 * 3600) // 86400; c = d["c"]; r = np.concatenate([[0], c[1:] / c[:-1] - 1])
    for ts_, amt in d["div"].items():
        i = int(np.searchsorted(day, (ts_ + 7 * 3600) // 86400))
        if 0 < i < len(c): r[i] = (c[i] + amt) / c[i - 1] - 1
    to = c * d["v"]; liq = np.array([np.median(to[max(0, k - 20):k]) if k >= 5 else 0 for k in range(len(to))])
    A = np.column_stack([d["t"] * 1000.0, d["o"], d["h"], d["l"], d["c"]]); S[s] = (A, r, liq, day)
print("universe", "first list" if len(sys.argv) < 2 else "fresh (out-of-sample) list", "tickers", len(S))
t0 = time.mktime((2010, 1, 1, 0, 0, 0, 0, 0, 0)) * 1000
def run(X, hold, stop, idio=True, side=1, up=False):
    tr = []; ctl = []
    for s, (A, r, liq, day) in S.items():
        cond = (r >= X) if up else (r <= -X)
        for i in np.nonzero(cond & (liq >= 2e7) & (A[:, 4] >= 1) & (A[:, 0] >= t0) & (np.abs(r) < 0.31))[0]:
            if idio and imap.get(int(day[i]), 0) < -0.02: continue
            x = L.sim(A, int(i) + 1, side, hold, stop, cost=C)
            if x: tr.append((x[0], x[1])); ctl.append(s)
    st = L.stats(tr)
    if st["n"] < 8: return f"X={X} n={st['n']}"
    ms = []
    lo = {s: int(np.searchsorted(S[s][0][:, 0], t0)) for s in set(ctl)}
    for z in range(100):
        rng = np.random.default_rng(z); rr = []
        for s in ctl:
            A = S[s][0]; x = L.sim(A, int(rng.integers(lo[s] + 1, len(A) - hold - 1)), side, hold, stop, cost=C)
            if x: rr.append(x[1])
        ms.append(np.mean(rr) * 100)
    ms = np.array(ms)
    y = lambda a, b: [q for t, q in tr if a <= time.gmtime(t / 1000).tm_year < b]
    return L.fmt(f"{'up' if up else 'drop'}>={X*100:.0f}% hold {hold}d stop {stop} idio={idio}", st, dict(mean=float(ms.mean()), med=float(np.median(ms)), p=float((ms >= st["mean"]).mean()))) + \
        f" | 2010-19 n{len(y(2010,2020))} {np.mean(y(2010,2020))*100:+.2f} 2020-26 n{len(y(2020,2030))} {np.mean(y(2020,2030))*100:+.2f}"
for X in (0.05, 0.07, 0.10, 0.15):
    for hold in (1, 3, 5, 10):
        print(run(X, hold, 0.10))
for X in (0.07, 0.10):
    print(run(X, 5, None)); print(run(X, 5, 0.10, idio=False))
print("--- the other side: long after a big up day (momentum) ---")
for X in (0.07, 0.10):
    for hold in (3, 10): print(run(X, hold, 0.10, up=True))
