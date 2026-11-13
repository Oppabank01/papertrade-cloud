#!/usr/bin/env python3
"""Offline: each zoo rule picks its pattern, exits are set per account, rankings are used once and archived."""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import zoo, agents, grok
now = time.time()
base = dict(is_honeypot=0, renounced_mint=1, renounced_freeze_account=1, sell_tax=0, liquidity=50_000, buys=200, sells=100,
            price_change_percent5m=5, price_change_percent1h=0, smart_degen_count=0, renowned_count=0, top_10_holder_rate=0.3,
            dev_team_hold_rate=0.1, holder_count=100, open_timestamp=now - 7200)
fresh = {**base, "address": "F", "open_timestamp": now - 300}
safe = {**base, "address": "S", "top_10_holder_rate": 0.1, "dev_team_hold_rate": 0.0, "holder_count": 900}
dip = {**base, "address": "D", "price_change_percent5m": -20, "price_change_percent1h": 40, "buys": 10}
bad = {**safe, "address": "B", "is_honeypot": 1}
rank = [fresh, safe, dip, bad]
hit = lambda n: {t["address"] for t in zoo.picks(n, rank)}
assert hit("fresh") == {"F"} and hit("safe") == {"S"} and hit("dip") == {"D"}, (hit("fresh"), hit("safe"), hit("dip"))
assert hit("top1") == {"F"} and len(hit("rand")) == 1 and "B" not in hit("rand")
zoo.use("scalp"); assert agents.TP_ALL == 0.10 and agents.STOP == -0.05 and agents.MAX_HOLD_H == 0.5
zoo.use("safe"); assert agents.TP_ALL is None and agents.STOP == -0.08     # overrides never leak to the next account
d = Path(tempfile.mkdtemp()); zoo.HERE = d; zoo.HIST = d / "hist"; zoo.RANK = d / "rank.json"
zoo.RANK.write_text(json.dumps(dict(t=now, rank=rank)))
grok.pair = lambda m: {"priceUsd": "1.0"}; grok.usdthb = lambda: 32.0
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": m}, "priceUsd": "1.0", "liquidity": {"usd": 1}} for m in url.rsplit("/", 1)[1].split(",")]
zoo.ZOO = {k: zoo.ZOO[k] for k in ("safe", "fresh")}
zoo.cmd_init(500); zoo.cmd_tick(); zoo.cmd_tick()
zoo.use("safe"); s = agents.load()
assert list(s["pos"]) == ["S"] and sum(x["kind"] == "buy" for x in s["log"]) == 1
assert len(list((d / "hist").rglob("*.json.gz"))) == 1
print("zoo ok")
