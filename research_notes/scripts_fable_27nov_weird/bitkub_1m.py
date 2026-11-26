#!/usr/bin/env python3
"""1-minute verification of the hedged Bitkub-discount trade (hourly bars can fake a discount when the two venues' last prints are not simultaneous).
For every hourly signal (discount >= 2%, signal hour >= 1M THB traded) we pull 1m bars from Bitkub (coin_THB and USDT_THB) and Binance for
[signal hour start, +8 h] and replay minute by minute:
  premium_m = (coin_THB close / last USDT_THB close) / Binance close - 1, only on minutes where Bitkub actually traded (>= 20k THB that minute)
  entry: first minute with premium <= -thr -> buy Bitkub at the NEXT minute's open (must trade within 2 min), short Binance at that minute's open
  exit: first later minute with premium >= -0.5% -> both legs at the next minute's open; else after 6 h at the last close
Costs: Bitkub 0.25%/side, Binance 0.15%/side (0.8% round trip both legs), plus a 0.5%/side Bitkub spread stress line."""
import pickle, sys, numpy as np
from wlib import *
TR = pickle.load(open(f"{SCR}/a1_trades_2pct_1m.pkl", "rb"))
ev = sorted(set((x[5], int(x[0]) - H) for x in TR if x[6] >= 5e6 or x[3] <= -0.03))
print("hourly signals to replay:", len(ev), flush=True)
def bk1m(sym, a, b):
    try: j = get(f"https://api.bitkub.com/tradingview/history?symbol={sym}_THB&resolution=1&from={a}&to={b}", tries=3)
    except Exception as e: return np.zeros((0, 6))
    if j.get("s") != "ok": return np.zeros((0, 6))
    return np.array([(t * 1000, o, h, l, c, v) for t, o, h, l, c, v in zip(j["t"], j["o"], j["h"], j["l"], j["c"], j["v"])], dtype=np.float64)
def bn1m(sym, a_ms):
    try: k = get(f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1m&limit=600&startTime={a_ms}", tries=3)
    except Exception as e: return np.zeros((0, 6))
    return np.array([(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])) for x in k], dtype=np.float64) if k else np.zeros((0, 6))
def replay(sym, t0, thr, exit_at=-0.005, minthb=2e4, maxh=6):
    a = t0 // 1000; b = a + 8 * 3600
    K = bk1m(sym, a, b); U = bk1m("USDT", a, b); B = bn1m(sym, t0)
    if len(K) < 5 or len(U) < 5 or len(B) < 100: return None
    bi = {int(t): i for i, t in enumerate(B[:, 0])}
    def usdt(t):
        i = int(np.searchsorted(U[:, 0], t, "right")) - 1
        return U[i, 4] if i >= 0 and t - U[i, 0] <= 10 * 60000 else None
    pos = None
    for i in range(len(K) - 1):
        t = int(K[i, 0]); j = bi.get(t); u = usdt(t)
        if j is None or u is None: continue
        prem = (K[i, 4] / u) / B[j, 4] - 1
        if pos is None:
            if t - t0 > 120 * 60000: return None                      # no signal within 2 h of the hourly signal bar -> hourly discount was a print artefact
            if prem <= -thr and prem > -0.5 and K[i, 5] * K[i, 4] >= minthb:
                tn = int(K[i + 1, 0]); jn = bi.get(tn)
                if tn - t > 2 * 60000 or jn is None: continue
                pos = (tn, K[i + 1, 1], B[jn, 1], prem)
        else:
            if t <= pos[0]: continue
            if prem >= exit_at or t - pos[0] >= maxh * H:
                tn = int(K[i + 1, 0]); jn = bi.get(tn)
                if jn is None: continue
                return (pos[0], K[i + 1, 1] / pos[1] - 1, B[jn, 1] / pos[2] - 1, pos[3], (tn - pos[0]) / 60000, sym)
    if pos is None: return None
    jn = bi.get(int(K[-1, 0]))
    if jn is None: return None
    return (pos[0], K[-1, 4] / pos[1] - 1, B[jn, 4] / pos[2] - 1, pos[3], (K[-1, 0] - pos[0]) / 60000, sym)
res = {0.02: [], 0.03: [], 0.05: []}; noarte = 0
for n, (sym, t0) in enumerate(ev):
    got = False
    for thr in res:
        r = replay(sym, t0, thr)
        if r: res[thr].append(r); got = True
    noarte += (not got)
    if n % 50 == 0: print(n, len(ev), {k: len(v) for k, v in res.items()}, flush=True)
    time.sleep(0.05)
print("hourly signals with no 1m discount at all (artefacts or no data):", noarte, "of", len(ev))
for thr, tr in res.items():
    # de-duplicate: overlapping hourly signals can replay the same minute entry
    seen = set(); tr2 = []
    for x in tr:
        if (x[5], x[0]) in seen: continue
        seen.add((x[5], x[0])); tr2.append(x)
    for nm, f in (("Bitkub leg only (unhedged, 0.25%/side)", lambda x: x[1] - 0.005), ("HEDGED (0.8% round trip)", lambda x: x[1] - x[2] - 0.008), ("HEDGED +0.5%/side Bitkub spread stress", lambda x: x[1] - x[2] - 0.018)):
        st = stats([(x[0], f(x)) for x in tr2])
        if st["n"] < 8: print(thr, nm, "n", st["n"]); continue
        yrs = collections.defaultdict(list)
        for x in tr2: yrs[time.gmtime(x[0] / 1000).tm_year].append(f(x))
        print(fmt(f"1m thr{thr*100:.0f}% {nm}", st), f"| medhold={np.median([x[4] for x in tr2]):.0f}min coins={len(set(x[5] for x in tr2))}", "yr " + " ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
pickle.dump(res, open(f"{SCR}/a1_1m_res.pkl", "wb"))
