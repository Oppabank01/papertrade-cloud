#!/usr/bin/env python3
"""v2: adds a WORST-PRICE fill (buy at the HIGH of the entry minute, sell at the LOW of the exit minute; short leg sells at the
entry minute LOW and covers at the exit minute HIGH) to kill bid-ask bounce, and splits by how much traded in the signal minute.
1-minute verification of the hedged Bitkub-discount trade (hourly bars can fake a discount when the two venues' last prints are not simultaneous).
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
                pos = (tn, K[i + 1, 1], B[jn, 1], prem, K[i + 1, 2], K[i, 5] * K[i, 4], K[i + 1, 5] * K[i + 1, 4], B[jn, 2])
        else:
            if t <= pos[0]: continue
            if prem >= exit_at or t - pos[0] >= maxh * H:
                tn = int(K[i + 1, 0]); jn = bi.get(tn)
                if jn is None: continue
                return (pos[0], K[i + 1, 1] / pos[1] - 1, B[jn, 1] / pos[2] - 1, pos[3], (tn - pos[0]) / 60000, sym, K[i + 1, 3] / pos[4] - 1, pos[5], pos[6], B[jn, 2] / B[bi[pos[0]], 3] - 1)
    if pos is None: return None
    jn = bi.get(int(K[-1, 0]))
    if jn is None: return None
    return (pos[0], K[-1, 4] / pos[1] - 1, B[jn, 4] / pos[2] - 1, pos[3], (K[-1, 0] - pos[0]) / 60000, sym, K[-1, 3] / pos[4] - 1, pos[5], pos[6], B[jn, 2] / B[bi[pos[0]], 3] - 1)

tk = get("https://api.bitkub.com/api/v3/market/ticker", cache=True)
spr = {}
for x in tk:
    try:
        b, a = float(x["highest_bid"]), float(x["lowest_ask"])
        if b > 0 and a > 0: spr[x["symbol"].replace("_THB", "")] = a / b - 1
    except Exception: pass
print("Bitkub quoted spread today (snapshot): median %.2f%%, p25 %.2f%%, p75 %.2f%%, n=%d" % (np.median(list(spr.values())) * 100, np.percentile(list(spr.values()), 25) * 100, np.percentile(list(spr.values()), 75) * 100, len(spr)))
def line(name, rows):
    st = stats(rows)
    if st["n"] < 8: print(f"{name:60s} n={st['n']}"); return
    yrs = collections.defaultdict(list)
    for t, r in rows: yrs[time.gmtime(t / 1000).tm_year].append(r)
    print(fmt(name, st), "yr " + " ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())), flush=True)
for thr in (0.02, 0.03, 0.05):
    tr = []; seen = set()
    for n, (sym, t0) in enumerate(ev):
        r = replay(sym, t0, thr)
        if r and (r[5], r[0]) not in seen: seen.add((r[5], r[0])); tr.append(r)
    print(f"\n--- thr {thr*100:.0f}% : {len(tr)} trades, median signal-minute volume {np.median([x[7] for x in tr]):,.0f} THB, median hold {np.median([x[4] for x in tr]):.0f} min, median Binance move while held {np.median([x[2] for x in tr])*100:+.2f}% ---")
    line(f"thr{thr*100:.0f}% unhedged, open fills (0.25%/side)", [(x[0], x[1] - 0.005) for x in tr])
    line(f"thr{thr*100:.0f}% unhedged, WORST-PRICE fills", [(x[0], x[6] - 0.005) for x in tr])
    line(f"thr{thr*100:.0f}% hedged, open fills", [(x[0], x[1] - x[2] - 0.008) for x in tr])
    line(f"thr{thr*100:.0f}% hedged, WORST-PRICE fills both legs", [(x[0], x[6] - x[9] - 0.008) for x in tr])
    for lo, hi, nm in ((0, 2e5, "signal minute < 200k THB"), (2e5, 1e6, "200k-1M THB"), (1e6, 1e12, ">= 1M THB")):
        sub = [x for x in tr if lo <= x[7] < hi]
        line(f"   {nm}: unhedged open fills", [(x[0], x[1] - 0.005) for x in sub]); line(f"   {nm}: unhedged WORST-PRICE", [(x[0], x[6] - 0.005) for x in sub])
    for lo, hi, nm in ((0, 0.004, "coins with today's spread < 0.4%"), (0.004, 0.015, "0.4-1.5%"), (0.015, 9, ">= 1.5% or unknown")):
        sub = [x for x in tr if lo <= spr.get(x[5], 1) < hi]
        line(f"   {nm}: unhedged open fills", [(x[0], x[1] - 0.005) for x in sub]); line(f"   {nm}: unhedged WORST-PRICE", [(x[0], x[6] - 0.005) for x in sub])
    if thr == 0.03:
        print("   sample of trades:")
        for x in sorted(tr, key=lambda x: -x[1])[:6] + sorted(tr, key=lambda x: x[1])[:6]: print(f"     {x[5]:7s} {ts(x[0])} prem {x[3]*100:+.1f}% open-fill {x[1]*100:+.1f}% worst-fill {x[6]*100:+.1f}% binance {x[2]*100:+.1f}% hold {x[4]:.0f}m sigvol {x[7]:,.0f} THB")
