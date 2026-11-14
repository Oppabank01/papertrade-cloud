#!/usr/bin/env python3
"""Offline checks for agents.py seats and exits (no network)."""
import json, sys, tempfile, time
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import agents, grok

ok = dict(address="M", symbol="T", liquidity=50_000, open_timestamp=time.time() - 3600, smart_degen_count=3, renowned_count=1,
          buys=200, sells=100, price_change_percent5m=5, is_honeypot=0, renounced_mint=1, renounced_freeze_account=1,
          rug_ratio=0.1, top_10_holder_rate=0.2, sell_tax=0)
assert agents.seats(ok) == []
assert agents.seats({**ok, "smart_degen_count": 1})
assert agents.seats({**ok, "price_change_percent5m": -3})
assert agents.seats({**ok, "price_change_percent5m": 150})
assert agents.seats({**ok, "open_timestamp": time.time() - 60})
assert agents.seats({**ok, "rug_ratio": 0.9})

agents.STATE = Path(tempfile.mkdtemp()) / "s.json"
def state(entry, last_peak, opened_h):
    s = dict(start_usd=10, cash=0, log=[], pos={"M": dict(sym="T", qty=1, entry=entry, last=entry, peak=last_peak, cost=1,
             opened=(grok.now() - timedelta(hours=opened_h)).isoformat())})
    agents.save(s)
for price, peak, h, expect in [(0.91, 1.0, 0.1, "stop"), (1.10, 1.40, 0.1, "trailing"), (1.02, 1.05, 3.1, "ครบ"), (1.02, 1.05, 0.5, None)]:
    state(1.0, peak, h)
    agents._dex.clear()                     # each case is a new moment; the shared price pool would otherwise serve the last price
    grok.get = lambda url, p=price: [{"chainId": "solana", "baseToken": {"address": "M"}, "priceUsd": str(p), "liquidity": {"usd": 1}}]
    agents.cmd_run()
    s = agents.load()
    sold = [x for x in s["log"] if x["kind"] == "sell"]
    assert (expect is None and not sold) or (sold and expect in sold[0]["why"]), (price, sold)
print("agents ok")

# no re-buy within 24h of a sell
s = dict(start_usd=10, cash=10, pos={}, log=[dict(t=(grok.now() - timedelta(hours=1)).isoformat(timespec="seconds"), kind="sell", mint="M")])
assert agents.paper_buy(s, "M", "T") == "sold within 24h"
print("cooldown ok")
