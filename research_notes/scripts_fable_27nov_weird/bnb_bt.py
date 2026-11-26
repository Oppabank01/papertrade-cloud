#!/usr/bin/env python3
"""Own odd idea: Binance HODLer Airdrop / Launchpool / Megadrop announcements (bapi CMS catalog 48, cached list Mar 2025 - Nov 2026)
-> is BNB bid afterwards (people need BNB to farm)? Long BNB spot at the open of the hour after the announcement, 24/72/168 h, stop 10%.
Also a BTC-hedged version (long BNB, short BTC, 4 legs of cost). Control: random hours in the same window, 300 seeds."""
import pickle, sys, numpy as np
from wlib import *
arts = pickle.load(open(SCR + "/../binlist.pkl", "rb"))
ev = sorted((a["releaseDate"], a["title"]) for a in arts if any(k in a["title"] for k in ("HODLer", "Launchpool", "Megadrop")))
print("events", len(ev), ts(ev[0][0]), ts(ev[-1][0]))
B = klines("BNBUSDT", "1h", 1735689600000); T = klines("BTCUSDT", "1h", 1735689600000)
tb = {int(t): i for i, t in enumerate(T[:, 0])}
def hedged(i, hold):
    x = sim(B, i, 1, hold, 0.10); j = tb.get(int(B[i, 0]))
    if not x or j is None or j + hold >= len(T): return None
    k = tb.get(int(B[x[2], 0]))
    return (x[0], x[1] - (T[k, 4] / T[j, 1] - 1) - 0.003)
lo = int(np.searchsorted(B[:, 0], ev[0][0]))
for kind, sel in (("all", lambda t: True), ("HODLer only", lambda t: "HODLer" in t), ("Launchpool/Megadrop", lambda t: "HODLer" not in t)):
    for hold in (24, 72, 168):
        tr = []; th = []; free = -1
        for t, title in ev:
            if not sel(title): continue
            i = int(np.searchsorted(B[:, 0], t, "left"))
            if i <= free or i >= len(B) - hold: continue
            x = sim(B, i, 1, hold, 0.10)
            if x: tr.append((x[0], x[1])); free = x[2]
            h = hedged(i, hold)
            if h: th.append(h)
        st = stats(tr)
        if st["n"] < 8: print(kind, hold, "n", st["n"]); continue
        print(fmt(f"BNB long after {kind} hold{hold}h", st, rand_ctl(B, st["n"], 1, hold, 0.10, seeds=300, lo=lo, mean_obs=st["mean"])))
        sh = stats(th); cm = []
        for k in range(300):
            rng = np.random.default_rng(k); rr = [hedged(int(i), hold) for i in rng.integers(lo, len(B) - hold - 1, sh["n"])]
            cm.append(np.mean([r[1] for r in rr if r]) * 100)
        print(fmt(f"   BTC-hedged", sh, dict(mean=np.mean(cm), med=float('nan'), p=(np.array(cm) >= sh['mean']).mean())), flush=True)
