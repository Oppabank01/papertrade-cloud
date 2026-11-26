#!/usr/bin/env python3
"""fwd_bitkubgap: premium from Bitkub ask/bid vs Binance, buy at ask on a 2% gap, sell at bid when it closes, twin mirrors (no network)."""
import random
import fwd_bitkubgap as G
from byttrade import new_state

bk = [dict(symbol="USDT_THB", highest_bid="33.0", lowest_ask="34.0", quote_volume="9e9"),
      dict(symbol="ETH_THB", highest_bid="96000", lowest_ask="96500", quote_volume="9e7"),      # Binance 3000 -> ask -3.5%
      dict(symbol="SOL_THB", highest_bid="6700", lowest_ask="6800", quote_volume="9e7"),        # Binance 200 -> ask +1.2%
      dict(symbol="DOGE_THB", highest_bid="1", lowest_ask="1", quote_volume="100")]             # too thin
bn = [dict(symbol="ETHUSDT", price="3000"), dict(symbol="SOLUSDT", price="200"), dict(symbol="DOGEUSDT", price="0.03")]
Q = G.quotes(bk, bn)
assert set(Q) == {"ETH", "SOL"} and abs(Q["ETH"][0] - (96500 / 33.5 / 3000 - 1)) < 1e-12
r, t = new_state("r"), new_state("t")
G.step(r, t, Q, 1_800_000_000_000, random.Random(1))
assert list(r["pos"]) == ["ETH"] and r["pos"]["ETH"]["entry"] == 96500 and list(t["pos"]) == ["SOL"]
Q2 = dict(ETH=(0.01, -0.004, 99000, 99000 * 0.999), SOL=(0.0, -0.01, 6900, 6850))
G.step(r, t, Q2, 1_800_000_300_000, random.Random(1))
sell = r["log"][-1]
assert sell["kind"] == "sell" and sell["px"] == 99000 * 0.999 and not r["pos"] and not t["pos"] and t["log"][-1]["px"] == 6850
usd = r["start_usd"] * G.SIZE
assert abs(r["cash"] - (r["start_usd"] - usd * (1 + G.COST) + usd / 96500 * 99000 * 0.999 * (1 - G.COST))) < 1e-9
r2, t2 = new_state("r"), new_state("t")
G.step(r2, t2, Q, 0, random.Random(1))
G.step(r2, t2, dict(ETH=(-0.03, -0.03, 1, 1)), G.HOLD, random.Random(1))
assert r2["log"][-1]["why"] == "ครบ 6 ชม." and not r2["pos"]
print("ok")
