#!/usr/bin/env python3
"""fwd_xsmom's Monday walk holds the same coins and books the same weekly returns as a plain recomputation (network: Binance)."""
import fwd_xsmom as F
from byttrade import new_state

px = {c: {x["t"]: x["o"] for x in F.fetch_daily(c + "USDT")} for c in F.COINS}
start = min(px["BTC"]) + (F.LOOK + 1) * F.DAY
mons = F.mondays_after(start, px)
for mode in ("top", "all"):
    s = new_state("t"); s["seen"] = start
    F.step(s, px, mode)
    F.step(s, px, mode)                                # second run books nothing new
    want = []
    for a, b in zip(mons, mons[1:]):
        el = [c for c in px if a in px[c] and a - F.LOOK * F.DAY in px[c]]
        top = el if mode == "all" else sorted(el, key=lambda c: px[c][a] / px[c][a - F.LOOK * F.DAY], reverse=True)[:F.K]
        want += sorted((c, round(px[c][b] / px[c][a] - 1, 6)) for c in top if b in px[c])
    got, i = [], 0
    by_t = {}
    for x in s["log"]:
        if x["kind"] == "sell":
            by_t.setdefault(x["t"], []).append((x["coin"], x["ret"]))
    got = [y for t in sorted(by_t) for y in sorted(by_t[t])]
    assert got == want, (mode, len(got), len(want), got[:5], want[:5])
    assert sorted(s["pos"]) == sorted(F.pick(px, mons[-1], mode)), mode
    eq = s["cash"] + sum(p["qty"] * p["entry"] for p in s["pos"].values())
    print(mode, len(got), "weekly coin trades match;", f"equity {eq / s['start_usd'] - 1:+.0%} over {len(mons)} Mondays; ok")
