#!/usr/bin/env python3
"""Follow-up on the only F&G row that looked alive: SHORT after the Fear & Greed index collapses (panic continuation).
F&G value for day D is published just after 00:00 UTC of D; entry = open of D+1 (24 h later). Stop checked first, cost 0.15%/side, no funding.
Checks: neighbours (drop size, window, hold, stop), replication on 10 alts never looked at, year by year, and a PRICE-ONLY matched control
(short after an equally rare 1-day BTC price drop, no F&G needed) to see whether F&G adds anything beyond 'big red day'."""
import sys, numpy as np
from wlib import *
fg = {int(x["timestamp"]) * 1000: int(x["value"]) for x in get("https://api.alternative.me/fng/?limit=0")["data"]}
COINS = "BTC ETH SOL BNB XRP DOGE ADA LTC LINK AVAX TRX BCH".split()
K = {c: klines(c + "USDT", "1d", 0) for c in COINS}
IX = {c: {int(t): i for i, t in enumerate(K[c][:, 0])} for c in COINS}
def drops(n, chg): return sorted(d for d in fg if d - n * D in fg and fg[d] - fg[d - n * D] <= -chg)
def run(c, days, hold, stop, side=-1, lag=1):
    tr = []; free = -1
    for d in days:
        i = IX[c].get(d + lag * D)
        if i is None or i <= free: continue
        x = sim(K[c], i, side, hold, stop)
        if x: tr.append((x[0], x[1])); free = x[2]
    return tr
def line(name, c, days, hold, stop, side=-1):
    tr = run(c, days, hold, stop, side); st = stats(tr)
    if st["n"] < 8: print(f"{name} n={st['n']}"); return None
    lo = IX[c].get(min(fg) + D, 30) or 30
    ctl = rand_ctl(K[c], st["n"], side, hold, stop, seeds=300, lo=max(30, lo), mean_obs=st["mean"])
    print(fmt(name, st, ctl), flush=True); return tr
print("=== neighbours, ETH and BTC, SHORT ===")
for c in ("ETH", "BTC"):
    for n, chg in ((1, 10), (1, 15), (1, 20), (2, 15), (2, 20), (3, 15), (3, 20), (3, 25)):
        for hold in (7, 14, 21):
            line(f"{c} F&G -{chg} in {n}d short hold{hold}d sl15", c, drops(n, chg), hold, 0.15)
    for stop in (0.08, 0.10, 0.25):
        line(f"{c} F&G -15 in 1d short hold14d sl{int(stop*100)}", c, drops(1, 15), 14, stop)
print("\n=== replication on alts (same rule, untouched assets): F&G -15 in 1d, short 14d, sl15 ===")
pool = []
for c in COINS:
    tr = line(f"{c} F&G -15 in 1d short hold14d sl15", c, drops(1, 15), 14, 0.15)
    if tr and c not in ("BTC", "ETH"): pool += tr
print(fmt("POOLED 10 alts", stats(pool)))
pool = []
for c in COINS:
    tr = run(c, drops(3, 20), 14, 0.15)
    if c not in ("BTC", "ETH"): pool += tr
print(fmt("POOLED 10 alts, F&G -20 in 3d short 14d", stats(pool)))
print("\n=== year by year, ETH F&G -15 in 1d short 14d sl15 ===")
tr = run("ETH", drops(1, 15), 14, 0.15); yrs = collections.defaultdict(list)
for t, r in tr: yrs[time.gmtime(t / 1000).tm_year].append(r)
print(" ".join(f"{y}:{np.mean(v)*100:+.1f}/{len(v)}" for y, v in sorted(yrs.items())))
for t, r in tr: print("  ", ts(t)[:10], f"{r*100:+.1f}%", end="")
print()
print("\n=== price-only matched control: short ETH 14d after BTC 1-day close-to-close drop <= -X% (same lag) ===")
B = K["BTC"]; t0 = min(fg)
for X in (0.04, 0.05, 0.06, 0.08):
    days = [int(B[i, 0]) + D for i in range(1, len(B)) if B[i, 0] >= t0 and B[i, 4] / B[i - 1, 4] - 1 <= -X]   # +D: known at next 00:00, like F&G
    line(f"ETH after BTC day <= -{X*100:.0f}% short 14d sl15", "ETH", days, 14, 0.15)
    line(f"BTC after BTC day <= -{X*100:.0f}% short 14d sl15", "BTC", days, 14, 0.15)
print("\n=== overlap: how many F&G -15 days are also BTC <= -5% days ===")
fd = set(drops(1, 15)); pd_ = set(int(B[i, 0]) + D for i in range(1, len(B)) if B[i, 4] / B[i - 1, 4] - 1 <= -0.05)
print("F&G days", len(fd), "price days", len(pd_), "both", len(fd & pd_))
only_fg = sorted(fd - pd_); line("ETH F&G -15 in 1d but BTC day > -5% short 14d", "ETH", only_fg, 14, 0.15)
