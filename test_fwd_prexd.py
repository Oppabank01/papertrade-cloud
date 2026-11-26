#!/usr/bin/env python3
"""fwd_prexd: books a 4%+ dividend stock from 6 days before XD to the day before, needs the XD seen before entry, twin same days (no network)."""
import random
import fwd_prexd as P
from byttrade import new_state

BASE = 1793612400000
days = [f"2026-11-{d:02d}" for d in range(2, 14)]                          # 12 trading days, XD on the 11th = index 9
mk = lambda px, low=None: [(d, BASE + i * 86_400_000, px[i], (low or px)[i], px[i]) for i, d in enumerate(days)]
up = mk([10.0] * 3 + [10.0, 10.1, 10.2, 10.3, 10.4, 10.5, 9.9, 9.9, 9.9])
other = mk([20.0] * 12)
bars = {"AAA": up, "BBB": other}
dl = lambda s: bars[s]
e, rest = P.window(up, days[9])
assert e[0] == days[3] and [x[0] for x in rest] == days[4:9]
r, t = new_state("r"), new_state("t")
cal = [("AAA", days[9], 0.5, 9e6), ("CCC", days[9], 0.1, 9e6)]               # AAA 5% yield, CCC has no bars
P.step(r, t, cal, ["AAA", "BBB"], e[1] - 1, random.Random(1), dl)             # seen before the entry close, XD in the future
assert not r["log"] and r["cal"]["AAA|" + days[9]]["seen"] == e[1] - 1
bars["CCC"] = other
P.step(r, t, [], [], up[9][1], random.Random(1), dl)                         # XD day: book
sell = r["log"][-1]
assert sell["kind"] == "sell" and abs(sell["ret"] - 0.05) < 1e-6 and sell["why"] == "ขายวันก่อน XD"
assert len([x for x in r["log"] if x["kind"] == "sell"]) == 1                 # CCC yield 0.5% skipped
assert t["log"][-1]["coin"] == "BBB" and abs(t["log"][-1]["ret"]) < 1e-9
r2, t2 = new_state("r"), new_state("t")
P.step(r2, t2, cal[:1], ["BBB"], e[1] + 1, random.Random(1), dl)            # seen after the entry close: no trade
P.step(r2, t2, [], [], up[9][1], random.Random(1), dl)
assert not r2["log"]
bars["AAA"] = mk([10.0] * 12, [10.0] * 5 + [9.0] + [10.0] * 6)              # low 9.0 under the 9.2 stop on day 6
r3, t3 = new_state("r"), new_state("t")
P.step(r3, t3, cal[:1], ["BBB"], 0, random.Random(1), dl)
P.step(r3, t3, [], [], up[9][1], random.Random(1), dl)
assert r3["log"][-1]["why"] == "stop -8%" and abs(r3["log"][-1]["px"] - 9.2) < 1e-9
print("ok")
