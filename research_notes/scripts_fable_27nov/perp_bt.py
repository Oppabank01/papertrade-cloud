#!/usr/bin/env python3
"""Angle 2/3: memecoin perps (63 Binance USDT-M meme symbols incl. 12 delisted, 1h bars Jul 2025 - Nov 2026).
  python3 perp_bt.py <perp.pkl> [seeds=40]"""
import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import perplib as P
D = P.load(sys.argv[1]); SEEDS = int(sys.argv[2]) if len(sys.argv) > 2 else 40
ME = sorted(s for s in D if D[s]["kind"] == "meme"); ALT = sorted(s for s in D if D[s]["kind"] == "alt")
print("memes", len(ME), "alts", len(ALT)); N = 0
def roll_ret(c, k): r = np.full(len(c), np.nan); r[k:] = c[k:] / c[:-k] - 1; return r
def roll_sum(q, k):
    cs = np.r_[0, np.cumsum(q)]; r = np.full(len(q), np.nan)
    if len(q) >= k: r[k - 1:] = cs[k:] - cs[:-k]
    return r
def first_cross(mask):  # indices where mask turns True (signal bar) -> entry bar = +1
    m = mask.astype(bool); x = np.nonzero(m & ~np.r_[False, m[:-1]])[0]; return [int(i) + 1 for i in x]
def rule(name, fn, side, hold, stop, hedge=None, tp=None, univ=ME, pool=ME):
    global N; N += 1
    ev = {s: [i for i in fn(D[s]) if i >= 24 * 14] for s in univ}     # skip first 14 days after listing
    return P.report(name, D, ev, side, hold, stop, hedge, tp, pool, SEEDS)
print("\n== P0 drift: weekly short, every meme, Monday 00 UTC ==")
def weekly(d): return [i for i in range(len(d["t"])) if d["t"][i] % (7 * 86400000) == 4 * 86400000]   # epoch day 0 = Thursday -> +4d = Monday
rule("P0 short meme weekly h168 sl30", weekly, -1, 168, .30)
rule("P0h short meme / long BTC weekly h168 sl30", weekly, -1, 168, .30, hedge="BTCUSDT")
rule("P0a short ALT / long BTC weekly h168 sl30", weekly, -1, 168, .30, hedge="BTCUSDT", univ=ALT, pool=ALT)
print("\n== P1 7-day run-up fade ==")
for x in (.5, 1.0):
    for hold in (72, 168):
        rule(f"P1 short r7d>=+{x:.0%} h{hold} sl25", lambda d, x=x: first_cross(roll_ret(d["c"], 168) >= x), -1, hold, .25)
print("\n== P2 run-up then first crack (r7d>=+50% within last 3d peak, r24<=-15%) ==")
def crack(d, up=.5, dn=-.15):
    r7 = roll_ret(d["c"], 168); r1 = roll_ret(d["c"], 24); hot = np.zeros(len(r7), bool)
    idx = np.nonzero(r7 >= up)[0]
    for i in idx: hot[i:i + 72] = True
    return first_cross(hot & (r1 <= dn))
for hold in (72, 168):
    rule(f"P2 short crack after run-up h{hold} sl20", crack, -1, hold, .20)
print("\n== P3 funding spike (sum of last 8h funding >= x) ==")
def fspike(d, x):
    if not len(d["ft"]): return []
    out = []
    for ft, fr in zip(d["ft"], d["fr"]):
        if fr >= x: out.append(int(np.searchsorted(d["t"], ft)))
    return out
for x in (.0005, .001):
    for hold in (24, 72):
        rule(f"P3 short fund>={x:.2%} h{hold} sl15", lambda d, x=x: fspike(d, x), -1, hold, .15)
print("\n== P4 volume climax day (24h vol >= 5x 30d avg, r24>=+20%), short 24h later ==")
def climax(d):
    v24 = roll_sum(d["q"], 24); v30 = roll_sum(d["q"], 720) / 30
    return [i + 24 for i in first_cross((v24 >= 5 * v30) & (roll_ret(d["c"], 24) >= .2))]
for hold in (72, 168):
    rule(f"P4 short climax+24h h{hold} sl25", climax, -1, hold, .25)
print("\n== P5 breakdown: close < 20-day low -> short ==")
def brk(d, n=480):
    c = d["c"]; lo = np.full(len(c), np.nan)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    if len(c) > n + 1: lo[n:] = sw(d["l"], n).min(1)[:-1]
    return first_cross(c < lo)
for hold in (72, 168):
    rule(f"P5 short 20d-low break h{hold} sl15", brk, -1, hold, .15)
print("\n== P8 dip buy: r24 <= -20% -> long ==")
for hold in (24, 72):
    rule(f"P8 long r24<=-20% h{hold} sl15", lambda d: first_cross(roll_ret(d["c"], 24) <= -.2), 1, hold, .15)
print("\n== P9 momentum: r24 >= +20% on 3x volume -> long ==")
def mom(d):
    v24 = roll_sum(d["q"], 24); v30 = roll_sum(d["q"], 720) / 30
    return first_cross((v24 >= 3 * v30) & (roll_ret(d["c"], 24) >= .2))
for hold, st, tp in ((24, .10, None), (72, .10, None), (72, .10, .30)):
    rule(f"P9 long mom h{hold} sl{st:.0%} tp{tp}", mom, 1, hold, st, tp=tp)
print("\nsettings tried:", N)
