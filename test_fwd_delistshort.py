#!/usr/bin/env python3
"""fwd_delistshort: parses Binance delisting titles, books a 4 h short from 1 m bars, stop +30% (no network: stubs)."""
import random
import fwd_delistshort as D
from byttrade import new_state

assert D.coins("Binance Will Delist EPIC, QUICK on 2026-10-28") == ["EPIC", "QUICK"]
assert D.coins("Binance Will Delist USDP on 2026-09-24") == []
assert D.coins("Binance Futures Will Delist PTBUSDT and MITOUSDT USDⓈ-M Perpetual Contracts (2026-10-23)") == ["PTB", "MITO"]
assert D.coins("Binance Futures Will Delist Multiple USDⓈ-M Perpetual Contracts", "delist 1000XXUSDT, YYUSDT and XXUSDT") == ["XX", "YY"]
assert D.coins("Notice of Removal of Spot Trading Pairs - 2026-11-20") == []
assert D.coins("Binance Alpha Will Remove PTB, AA") == []

M = D.M
ts = 1_800_000_030_000
t0 = (ts // M + 1) * M + 14 * M
fall = [[t0 + i * M, "10", "10.5", "0", "9"] for i in range(240)]           # Binance kline rows
kl = lambda u, body=None: fall if "symbol=EPICUSDT" in u else []
s = new_state("t"); s["mode"] = "rule"
D.step(s, [("a", ["EPIC"], ts)], t0, random.Random(1), kl)
assert not s["log"] and len(s["queue"]) == 1                                  # waits for the 4 h window
D.step(s, [], t0 + 242 * M, random.Random(1), kl)
sell = s["log"][-1]
assert sell["kind"] == "sell" and abs(sell["ret"] - 0.1) < 1e-9 and sell["why"] == "ครบ 4 ชม."
usd = s["start_usd"] * D.SIZE
assert abs(s["cash"] - (s["start_usd"] + usd * 0.1 - usd * 0.9 * D.COST - usd * D.COST)) < 1e-9

squeeze = [[t0 + i * M, "10", "14" if i == 5 else "10.2", "0", "10"] for i in range(240)]
assert D.trade([(r[0], float(r[1]), float(r[2]), float(r[4])) for r in squeeze]) == (13.0 * 1.001, "stop +30%")

hl = lambda u, body=None: [] if "binance" in u else [dict(t=t0 + i * M, o="2", h="2", c="1.8") for i in range(240)]
s2 = new_state("t"); s2["mode"] = "rule"
D.step(s2, [("b", ["PTB"], ts)], t0 + 242 * M, random.Random(1), hl)
assert abs(s2["log"][-1]["ret"] - 0.1) < 1e-9                                 # Hyperliquid fallback
print("ok")
