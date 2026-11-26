#!/usr/bin/env python3
"""fwd_fgshort: finds 15-point Fear & Greed drops, queues a short at the next daily open, books it after 14 days (no network)."""
import random
import fwd_fgshort as F
from byttrade import new_state

D = F.D
d0 = 1_800_000_000_000 // D * D
fng = [dict(timestamp=str((d0 + i * D) // 1000), value=str(v)) for i, v in enumerate([50, 48, 30, 29])]
assert F.signals(fng) == {d0 + 2 * D: 18}
days = {d0 + i * D: F.signals(fng).get(d0 + i * D) for i in range(4)}
s = new_state("t"); s["mode"] = "rule"; s["seen"] = [d0, d0 + D]
fall = [[d0 + (3 + i) * D, "100", "105", "0", "90"] for i in range(14)]
kl = lambda u: fall
F.step(s, days, d0 + 3 * D, random.Random(1), kl)
assert len(s["queue"]) == 1 and s["queue"][0]["t0"] == d0 + 3 * D and not s["log"]
F.step(s, days, d0 + 18 * D, random.Random(1), kl)
sell = s["log"][-1]
assert sell["kind"] == "sell" and abs(sell["ret"] - 0.1) < 1e-9 and sell["why"] == "ครบ 14 วัน" and not s["queue"]
squeeze = [(0, 100.0, 104.0, 100.0)] + [(i, 100.0, 120.0 if i == 3 else 101.0, 100.0) for i in range(1, 14)]
px, why = F.trade(squeeze)
assert abs(px - 115.0 * 1.001) < 1e-9 and why == "stop +15%"
print("ok")
