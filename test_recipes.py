#!/usr/bin/env python3
"""Offline: each recipe picks only its pattern; a ranking is used once."""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import recipes, agents, grok
agents.jup_prices = lambda ms: {m: float(agents.grok.pair(m)["priceUsd"]) for m in ms}   # second source mirrors the mocked pair price
now = time.time()
base = dict(is_honeypot=0, renounced_mint=1, renounced_freeze_account=1, sell_tax=0, liquidity=50_000, buys=200, sells=100,
            price_change_percent5m=5, smart_degen_count=0, renowned_count=0, top_10_holder_rate=0.3, dev_team_hold_rate=0.1,
            launchpad_status="0", migrated_pool_exchange="", open_timestamp=now - 7200)
ins = {**base, "address": "I", "symbol": "INS", "open_timestamp": now - 600, "smart_degen_count": 6, "top_10_holder_rate": 0.1, "dev_team_hold_rate": 0.01}
grd = {**base, "address": "G", "symbol": "GRD", "open_timestamp": now - 600, "launchpad_status": "1", "migrated_pool_exchange": "pump_amm", "renowned_count": 1}
sm4 = {**base, "address": "S", "symbol": "SM4", "smart_degen_count": 4, "renowned_count": 1}
bad = {**sm4, "address": "B", "is_honeypot": 1}
pick = lambda n: {t["address"] for t in (ins, grd, sm4, bad) if recipes.base_guard(t) and recipes.RECIPES[n]["pick"](t)}
assert pick("insider") == {"I"}, pick("insider")
assert pick("grad") == {"G"}, pick("grad")
assert pick("smart4") == {"S"}, pick("smart4")
d = Path(tempfile.mkdtemp()); recipes.HERE = d; recipes.RANK = d / "rank.json"
recipes.RANK.write_text(json.dumps(dict(t=now, rank=[ins, grd, sm4, bad])))
grok.pair = lambda m: {"priceUsd": "1.0"}
recipes.setup("smart4"); agents.save(dict(start_usd=10, cash=10, pos={}, log=[]))
recipes.cmd_scan("smart4"); recipes.cmd_scan("smart4")
s = agents.load(); assert list(s["pos"]) == ["S"] and sum(x["kind"] == "buy" for x in s["log"]) == 1
recipes.setup("grad"); assert agents.TP_ALL == 0.35 and agents.STOP == -0.15
print("recipes ok")
