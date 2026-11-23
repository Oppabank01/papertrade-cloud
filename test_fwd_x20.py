#!/usr/bin/env python3
"""fwd_x20 ladder on made-up bars: five +2% wins reach x28 and close; a bar touching both sides counts as a loss."""
import fwd_x20 as F
from byttrade import new_state

def bars(path):
    out, t = [], 0
    for o, h, l in path:
        out.append(dict(t=t, o=o, h=h, l=l, c=o, closed=True)); t += 3600000
    return out

flat = [(100, 100, 100)] * 25                                   # 24 warm-up bars, BTC flat -> trend side = short (-1)
s = new_state("t"); s["seen"] = 23 * 3600000
px, path = 100.0, list(flat[:24])
for _ in range(5):                                              # short wins: low reaches -2%
    path.append((px, px, px * 0.979)); px *= 0.979
F.step(s, bars(path), "trend", None)
sell = [x for x in s["log"] if x["kind"] == "sell"]
assert len(sell) == 1 and abs(sell[0]["ret"] - ((2 - F.FEE) ** 5 - 1)) < 1e-6, sell
s2 = new_state("t"); s2["seen"] = 23 * 3600000
F.step(s2, bars(flat[:24] + [(100, 102.5, 97.5)]), "trend", None)
assert s2["log"][-1]["ret"] == -1.0
print("x20 ladder ok: five wins pay x%.1f, a two-sided bar is a loss" % (2 - F.FEE) ** 5)
