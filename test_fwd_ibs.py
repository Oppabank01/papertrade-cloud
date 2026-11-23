#!/usr/bin/env python3
"""fwd_ibs's walk gives the same trades as the plain backtest over 5 years of Yahoo bars (network)."""
import fwd_overnight as O
import fwd_ibs as F
from byttrade import new_state

O.URL = O.URL.replace("range=3mo", "range=5y")
for sym in F.SYMS:
    bars = O.fetch(sym)
    want = [round(bars[i]["c"] / bars[i]["o"] - 1, 6) for i in range(2, len(bars)) if bars[i]["closed"] and F.ibs(bars[i - 1]) < F.TH]
    s = new_state("t"); s["seen"] = {sym: bars[1]["t"]}; s["sleeve"] = {sym: 1000.0}
    F.step(s, sym, bars, "rule", None)
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want and len(got) > 50, (sym, len(got), len(want))
    print(sym, len(got), "trades match, mean %+.3f%%" % (sum(got) / len(got) * 100))
