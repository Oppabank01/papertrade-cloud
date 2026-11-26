#!/usr/bin/env python3
"""Angle 1a: Grok-style 'big calm pool' entries on data/grok_watch.csv (5-min DexScreener snapshots, 308 Grok-mentioned
coins, 19-22 Nov 2026) with several exits, against random coins from the same snapshot (liq >= 100k, active).
Signal at snapshot i, entry at snapshot i+1 price, stop checked first on every later snapshot (fill = snapshot price,
which is <= stop), TP fills at the TP level. Cost/side 2% (0.5% if liquidity >= $1M).
  python3 gw_bt.py [seeds=200] [cost_small=0.02]"""
import csv, sys, math, random, collections
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent)); from lib27 import stats, fmt
R = Path(__file__).resolve().parents[2]
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
CS = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
f = lambda x: float(x) if x not in ("", None) else float("nan")
W = collections.defaultdict(list)
for r in csv.DictReader(open(R / "data/grok_watch.csv")):
    W[r["mint"]].append(dict(t=int(r["t"]), p=f(r["price"]), liq=f(r["liq"]), vm5=f(r["vol_m5"]), vh1=f(r["vol_h1"]), b=f(r["buys_m5"]), s=f(r["sells_m5"]),
                             c5=f(r["ch_m5"]), c1=f(r["ch_h1"]), sym=r["sym"]))
# clean: split each coin into segments at pool switches (price jump not explained by AMM mechanics) / dead pools
SEG = {}; nbreak = 0
for m, v in W.items():
    v.sort(key=lambda x: x["t"]); seg = 0
    for i, x in enumerate(v):
        ok = x["p"] == x["p"] and x["p"] > 0 and x["liq"] == x["liq"] and x["liq"] > 100
        if i and ok and v[i - 1]["ok"]:
            dlp = math.log(x["p"] / v[i - 1]["p"]); dlq = math.log(x["liq"] / v[i - 1]["liq"])
            if abs(dlp) > math.log(2.5) and abs(dlq - dlp / 2) > 0.7: seg += 1; nbreak += 1
        elif i and ok != v[i - 1]["ok"]: seg += 1
        x["ok"] = ok; x["seg"] = seg
print("coins", len(W), "pool-switch breaks", nbreak)
def cost(liq): return 0.005 if liq >= 1e6 else CS
def sim(v, i, ex):
    """signal at i, enter at i+1. ex = (hold_min, stop, tp, trail_arm, trail). returns (t, ret) or None"""
    if i + 2 >= len(v): return None
    a, e = v[i], v[i + 1]
    if not (a["ok"] and e["ok"]) or e["seg"] != a["seg"] or e["t"] - a["t"] > 600: return None
    hold, stop, tp, arm, trail = ex; pe = e["p"]; peak = pe; px = None; c = cost(a["liq"])
    for j in range(i + 2, len(v)):
        x = v[j]
        if x["seg"] != e["seg"] or not x["ok"]:
            # pool died or switched: if liquidity vanished take the collapsed price when lower (rug), else last good price
            last = v[j - 1]["p"]; px = min(last, x["p"]) if (x["p"] == x["p"] and x["p"] > 0 and not (x["liq"] > 100)) else last
            if not (x["liq"] > 100) and x["p"] == x["p"] and x["p"] > pe * 3: px = last
            break
        lvl = pe * (1 - stop)
        if arm and peak >= pe * (1 + arm): lvl = max(lvl, peak * (1 - trail))
        if x["p"] <= lvl: px = x["p"]; break
        if tp and x["p"] >= pe * (1 + tp): px = pe * (1 + tp); break
        peak = max(peak, x["p"])
        if x["t"] - e["t"] >= hold * 60: px = x["p"]; break
    if px is None: return None        # ran out of log before exit: drop (same for control)
    return (e["t"], min(px / pe, 4.0) * (1 - c) / (1 + c) - 1)
U = lambda x: x["ok"] and x["liq"] >= 1e5 and x["vh1"] == x["vh1"] and x["vh1"] >= 1000
nz = lambda v, d=0.0: v if v == v else d
SIG = {
 "G0 any big active (liq>=100k)": lambda x, v, i: U(x),
 "G1 calm |ch_h1|<=5": lambda x, v, i: U(x) and abs(nz(x["c1"], 99)) <= 5,
 "G2 calm + buys>=1.5x sells": lambda x, v, i: U(x) and abs(nz(x["c1"], 99)) <= 5 and nz(x["b"]) >= 5 and nz(x["b"]) >= 1.5 * max(nz(x["s"]), 1),
 "G3 dip ch_h1<=-15": lambda x, v, i: U(x) and nz(x["c1"]) <= -15,
 "G4 early move 3<=ch_m5<=12, ch_h1<=15": lambda x, v, i: U(x) and 3 <= nz(x["c5"]) <= 12 and nz(x["c1"], 99) <= 15,
 "G5 volume surge, flat price": lambda x, v, i: U(x) and abs(nz(x["c5"], 99)) <= 2 and nz(x["vm5"]) >= 1000 and nz(x["vm5"]) * 12 >= 3 * x["vh1"],
 "G6 first sight, liq>=100k, |ch_h1|<=10": lambda x, v, i: U(x) and i == 0 and abs(nz(x["c1"], 99)) <= 10,
 "G7 first sight, any big": lambda x, v, i: U(x) and i == 0,
}
EX = {"T15 sl15": (15, .15, None, None, None), "T60 sl15": (60, .15, None, None, None), "T240 sl15": (240, .15, None, None, None),
      "T240 tp20 sl10": (240, .10, .20, None, None), "T240 trail10@+10 sl10": (240, .10, None, .10, .10), "T720 sl25": (720, .25, None, None, None)}
# snapshot index for time-matched control: t-bucket -> [(mint, i)]
BUCK = collections.defaultdict(list)
for m, v in W.items():
    for i, x in enumerate(v):
        if U(x): BUCK[x["t"] // 300].append((m, i))
ntry = 0
for sn, sg in SIG.items():
    for en, ex in EX.items():
        ntry += 1; tr = []; meta = []
        for m, v in W.items():
            free = 0
            for i, x in enumerate(v):
                if x["t"] < free or not sg(x, v, i): continue
                r = sim(v, i, ex)
                if r is None: continue
                tr.append(r); meta.append((m, i, x["t"])); free = r[0] + ex[0] * 60   # no overlap inside the hold window
        st = stats(tr)
        if st["n"] < 6: print(fmt(f"{sn} | {en}", st)); continue
        cm = []; cmed = []
        for k in range(SEEDS):
            rng = random.Random(k); c = []
            for m, i, t in meta:
                cand = BUCK.get(t // 300) or []
                for _ in range(8):
                    if not cand: break
                    m2, i2 = rng.choice(cand); r = sim(W[m2], i2, ex)
                    if r is not None: c.append(r[1]); break
            if c: cm.append(np.mean(c)); cmed.append(np.median(c))
        ctl = dict(mean=np.mean(cm) * 100, med=np.mean(cmed) * 100, p=float(np.mean(np.array(cm) * 100 >= st["mean"])))
        print(fmt(f"{sn} | {en}", st, ctl) + f" coins={len(set(m for m, _, _ in meta))}", flush=True)
print("settings tried:", ntry)
