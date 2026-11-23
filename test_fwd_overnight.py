#!/usr/bin/env python3
"""fwd_overnight's walk books close->open (and open->close for the twin) for every closed day, once each (network: Yahoo)."""
import fwd_overnight as F
from byttrade import new_state

for sym in F.SYMS:
    bars = F.fetch(sym)
    done = [x for x in bars if x["closed"]]
    for mode in ("night", "day"):
        s = new_state("t"); s["seen"] = {sym: bars[0]["t"]}; s["sleeve"] = {sym: 100.0}
        F.step(s, sym, bars, mode)
        F.step(s, sym, bars, mode)                      # second run books nothing new
        got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
        want = [round((bars[i]["o"] / bars[i - 1]["c"] if mode == "night" else bars[i]["c"] / bars[i]["o"]) - 1, 6)
                for i in range(1, len(bars)) if bars[i]["closed"]]
        assert got == want and len(got) == len(done) - 1, (sym, mode, len(got), len(want))
        assert abs(s["sleeve"][sym] - 100 - (s["cash"] - s["start_usd"])) < 1e-9
    print(sym, len(want), "days match; ok")
