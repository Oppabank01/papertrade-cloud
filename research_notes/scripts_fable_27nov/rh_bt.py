#!/usr/bin/env python3
"""Angle 1b: Grok-style selection on 14 days of GMGN top-50 snapshots (data/rank_hist, 13-26 Nov 2026) with exits scored
on full 5-min Jupiter bars (jup_fetch.py), so coins that leave the ranking or rug still count.
Signal at snapshot time t -> entry at the open of the first 5-min bar starting at/after t+60s. Stop checked first
(fill min(open, stop)), TP fills at the TP level. Cost/side 2% (0.5% when liquidity >= $1M and age > 30 d).
Control: same snapshot, random coin with liquidity >= CTL_LIQ, same exit.
  python3 rh_bt.py <rh.pkl> <jup5_dir> [seeds=100] [cost=0.02]"""
import sys, pickle, random, collections, bisect
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent)); from lib27 import stats, fmt
rows = pickle.load(open(sys.argv[1], "rb")); JD = Path(sys.argv[2])
SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 100; CS = float(sys.argv[4]) if len(sys.argv) > 4 else 0.02
COLS = "t mint sym price liq mc vol holders open buys sells ch5 ch1h smart top10 bundler lp_status exch hot rug wash".split()
B = {}
for p in JD.glob("*.npy"):
    a = np.load(p)
    if len(a) > 3: B[p.stem] = a
print("bars for", len(B), "mints")
snaps = collections.defaultdict(list); seen = collections.defaultdict(list)
for r in rows:
    x = dict(zip(COLS, r)); x["age_h"] = (x["t"] - x["open"]) / 3600 if x["open"] else 0
    snaps[x["t"]].append(x); seen[x["mint"]].append(x["t"])
T = sorted(snaps)
def sim(mint, t, ex, liq, age_h, ref=None):
    a = B.get(mint)
    if a is None: return None
    i = int(np.searchsorted(a[:, 0], t + 60))
    if i >= len(a) - 1 or a[i, 0] - t > 1800: return None       # no bar within 30 min: no trade (illiquid or missing data)
    pe = a[i, 1]
    if not pe > 0: return None
    if ref and not (0.7 < pe / ref < 1.43): return None         # Jupiter price disagrees with the GMGN snapshot: skip
    hold, stop, tp, arm, trail = ex; peak = pe; px = None; t0 = a[i, 0]
    c = 0.005 if (liq >= 1e6 and age_h > 720) else CS
    for j in range(i, len(a)):
        tt, o, h, l, cl = a[j, :5]
        if tt - t0 >= hold * 60: px = o; break
        lvl = pe * (1 - stop)
        if arm and peak >= pe * (1 + arm): lvl = max(lvl, peak * (1 - trail))
        if l <= lvl: px = min(o, lvl); break
        if tp and h >= pe * (1 + tp): px = pe * (1 + tp); break
        peak = max(peak, h)
    if px is None:
        if a[-1, 0] - t0 < hold * 60 * 0.5 and a[-1, 0] > 1795650000: return None   # data ends (26 Nov) before half the hold
        px = a[-1, 4]                                           # trading stopped: last print (dead coin)
    return (t0, min(px / pe, 4.0) * (1 - c) / (1 + c) - 1)
def absent(x, hrs=6):
    s = seen[x["mint"]]; k = bisect.bisect_left(s, x["t"]); return k == 0 or x["t"] - s[k - 1] >= hrs * 3600
big = lambda x: x["liq"] >= 1e5 and x["age_h"] >= 24
SIG = {
 "R0 any liq>=100k": lambda x: x["liq"] >= 1e5,
 "R1 big calm: liq>=100k age>=24h |ch1h|<=10": lambda x: big(x) and abs(x["ch1h"]) <= 10,
 "R2 R1 + buys>=1.5x sells": lambda x: big(x) and abs(x["ch1h"]) <= 10 and x["buys"] >= 1.5 * max(x["sells"], 1),
 "R3 big, back in top50 after 6h away": lambda x: big(x) and absent(x),
 "R4 big dip: ch1h<=-20": lambda x: big(x) and x["ch1h"] <= -20,
 "R5 big early move: 3<=ch5<=15, ch1h<=20": lambda x: big(x) and 3 <= x["ch5"] <= 15 and x["ch1h"] <= 20,
 "R6 mid calm: 30k<=liq<100k age>=6h |ch1h|<=10": lambda x: 3e4 <= x["liq"] < 1e5 and x["age_h"] >= 6 and abs(x["ch1h"]) <= 10,
 "R7 very big calm: liq>=300k age>=72h |ch1h|<=10": lambda x: x["liq"] >= 3e5 and x["age_h"] >= 72 and abs(x["ch1h"]) <= 10,
}
EX = {"T60 sl15": (60, .15, None, None, None), "T240 sl15": (240, .15, None, None, None), "T240 tp20 sl10": (240, .10, .20, None, None),
      "T240 trail10@+10 sl10": (240, .10, None, .10, .10), "T1440 sl25": (1440, .25, None, None, None)}
CTL_LIQ = 3e4; ntry = 0; cov = collections.Counter()
for sn, sg in SIG.items():
    for en, ex in EX.items():
        ntry += 1; tr = []; meta = []; free = {}
        for t in T:
            for x in snaps[t]:
                if not sg(x) or free.get(x["mint"], 0) > t: continue
                r = sim(x["mint"], t, ex, x["liq"], x["age_h"], x["price"])
                cov["sig"] += 1; cov["nobars"] += r is None
                if r is None: continue
                tr.append(r); meta.append((t, x["mint"])); free[x["mint"]] = r[0] + ex[0] * 60 + 3600
        st = stats(tr)
        if st["n"] < 6: print(fmt(f"{sn} | {en}", st)); continue
        cm = []; cmed = []
        for k in range(SEEDS):
            rng = random.Random(k); c = []
            for t, m in meta:
                cand = [y for y in snaps[t] if y["liq"] >= CTL_LIQ]
                for _ in range(8):
                    if not cand: break
                    y = rng.choice(cand); r = sim(y["mint"], t, ex, y["liq"], y["age_h"], y["price"])
                    if r is not None: c.append(r[1]); break
            if c: cm.append(np.mean(c)); cmed.append(np.median(c))
        ctl = dict(mean=np.mean(cm) * 100, med=np.mean(cmed) * 100, p=float(np.mean(np.array(cm) * 100 >= st["mean"])))
        days = len(set(int(t // 86400) for t, _ in meta))
        print(fmt(f"{sn} | {en}", st, ctl) + f" coins={len(set(m for _, m in meta))} days={days}", flush=True)
print("settings tried:", ntry, "| signals", cov["sig"], "dropped for missing/mismatched bars", cov["nobars"])
