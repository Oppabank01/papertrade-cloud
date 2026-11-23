#!/usr/bin/env python3
"""fwd_dvol's bar-by-bar walk gives the same trades as the plain backtest on full history (network: Binance + Deribit)."""
import json, sys, time, urllib.request
sys.path.insert(0, "/Users/oppabank/.claude/skills/market-timeseries/scripts")
import mts
import fwd_dvol as F
from byttrade import new_state


def dvol_all(cur):
    out, e = {}, int(time.time() * 1000)
    while True:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(F.DVOL.format(cur, 1600000000000, e), headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())["result"]
        out.update({d[0] // F.DAY: d[4] for d in r["data"]})
        if not r.get("continuation") or not r["data"]:
            return out
        e = r["continuation"]


for sym, cur in F.SYMS.items():
    dv = dvol_all(cur)
    bars = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d")]
    bars[-1]["closed"] = False
    px = {x["t"] // F.DAY: x for x in bars}
    want, nxt = [], -1   # plain backtest, as in the scout-style grid script
    for d in sorted(dv):
        if d < nxt or not F.spike(dv, d) or d + 1 not in px or d + 1 + F.HOLD not in px or px[d + 1 + F.HOLD] is bars[-1]:
            continue
        want.append(round(px[d + 1 + F.HOLD]["o"] / px[d + 1]["o"] - 1, 5)); nxt = d + F.HOLD
    s = new_state("t"); s["cash"] = 1e9; s["seen"] = {sym: bars[0]["t"]}
    F.step(s, sym, bars, dv, "rule", None)
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want, (sym, len(got), len(want), got[:5], want[:5])
    print(sym, len(got), "trades match the backtest; ok")
