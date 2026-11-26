#!/usr/bin/env python3
"""Angle 4 (rough): be the liquidity provider instead of the buyer. Full-range constant-product LP in a Grok-mentioned pool
(data/grok_watch.csv), entered at first sight when liquidity >= $100k. LP value ~ sqrt(P1/P0) (SOL leg assumed flat),
fees = fee_share x sum of hourly volume/liquidity. Entry+exit cost 1% of the position (swap half in, half out).
This is an estimate only: the log does not record which DEX or fee tier each pool has.
  python3 lp_est.py"""
import csv, math, collections, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).parent)); from lib27 import stats, fmt
R = Path(__file__).resolve().parents[2]; f = lambda x: float(x) if x not in ("", None) else float("nan")
W = collections.defaultdict(list)
for r in csv.DictReader(open(R / "data/grok_watch.csv")):
    W[r["mint"]].append((int(r["t"]), f(r["price"]), f(r["liq"]), f(r["vol_h1"]), f(r["ch_h1"])))
for hold in (4, 12, 23):
    for fee in (0.0025, 0.0005):
        for sel in ("all big", "calm & hourly turnover >= 10%"):
            tr = []; turn = []
            for m, v in W.items():
                v.sort(); t0, p0, l0, v0, c0 = v[0]
                if not (p0 > 0 and l0 >= 1e5 and v0 == v0 and v0 >= 1000): continue
                if sel != "all big" and not (abs(c0 if c0 == c0 else 99) <= 10 and v0 / l0 >= 0.10): continue
                fees = 0.0; nxt = t0 + 3600; p1 = None; bad = False; prev = v[0]
                for x in v[1:]:
                    t, p, l, vh, _ = x
                    if not (p > 0 and l > 100): p1 = 0.0 if not (l > 100) else prev[1]; break           # pool gone: LP position gone too
                    if abs(math.log(p / prev[1])) > math.log(2.5) and abs(math.log(l / prev[2]) - math.log(p / prev[1]) / 2) > 0.7: bad = True; break   # pool switch in the log
                    if t >= nxt: fees += fee * (vh if vh == vh else 0) / l; nxt += 3600
                    prev = x
                    if t - t0 >= hold * 3600: p1 = p; break
                if bad or p1 is None: continue
                tr.append((t0, math.sqrt(min(p1 / p0, 16)) * (1 + fees) - 1 - 0.01)); turn.append(fees / fee)
            st = stats(tr)
            print(fmt(f"LP {hold}h fee {fee:.2%} {sel}", st) + (f" | median turnover over hold {np.median(turn):.2f}x" if turn else ""))
print("settings tried: 12")
