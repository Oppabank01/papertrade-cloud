#!/usr/bin/env python3
"""fwd_stable's bar-by-bar walk gives the same trades as the plain backtest (network: DefiLlama + Binance)."""
import sys
sys.path.insert(0, "/Users/oppabank/.claude/skills/market-timeseries/scripts")
import mts
import fwd_stable as F
from byttrade import new_state

sup = F.fetch_supply()
for sym in F.SYMS:
    bars = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d")]
    bars[-1]["closed"] = False
    px = {x["t"] // F.DAY: x for x in bars}
    want, nxt = [], -1
    for d in sorted(x for x in sup if x in px and x >= 18262):
        z = F.zscore(sup, d)
        a, c = px.get(d + 2), px.get(d + 2 + F.HOLD)
        if d < nxt or z is None or z <= F.Z or not a or not c or c is bars[-1]:
            continue
        want.append(round(c["o"] / a["o"] - 1, 5)); nxt = d + F.HOLD
    s = new_state("t"); s["cash"] = 1e9; s["seen"] = {sym: px[18262]["t"]}
    F.step(s, sym, bars, sup, "rule", None)
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want, (sym, len(got), len(want), got[:4], want[:4])
    print(sym, len(got), "trades match the backtest; ok")
