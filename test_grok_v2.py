"""Self-check for v2 exits and entry gate (no network). Run: python3 test_grok_v2.py"""
import tempfile, json
from datetime import timedelta
from pathlib import Path
import grok

def run_with(price, liq, peak=None, held_h=1, tp_done=False):
    s = dict(start_usd=10, cash=9, pos={"M": dict(sym="T", qty=1, entry=1.0, cost=1, last=1, opened=(grok.now() - timedelta(hours=held_h)).isoformat(),
             tp_done=tp_done, liq0=100_000, peak=peak or 1.0)}, log=[], ended=False, day=grok.now().strftime("%Y-%m-%d"), day_start=10)
    grok.STATE = Path(tempfile.mkdtemp()) / "s.json"; grok.save(s)
    grok.pair = lambda m: None if price is None else {"priceUsd": str(price), "liquidity": {"usd": liq}}
    grok.usdthb = lambda: 33.0
    grok.cmd_run()
    s = grok.load()
    return [x["why"] for x in s["log"] if x["kind"] == "sell"], s["pos"]

assert "สภาพคล่องลด" in run_with(1.02, 60_000)[0][0]
assert "stop" in run_with(0.90, 100_000)[0][0]
assert "stop ทุน" in run_with(1.03, 100_000, peak=1.12)[0][0]
assert "trailing" in run_with(1.10, 100_000, peak=1.40, tp_done=True)[0][0]
assert "ไม่เคยถึง" in run_with(1.01, 100_000, held_h=7)[0][0]
assert "rug" in run_with(None, 0)[0][0]
why, pos = run_with(1.25, 100_000)
assert "ขายครึ่ง" in why[0] and pos["M"]["tp_done"]
assert run_with(1.03, 100_000, peak=1.06)[0] == []          # nothing triggers

ok = {"buy_volume_1h": 2, "sell_volume_1h": 1, "buy_volume_6h": 2, "sell_volume_6h": 1, "price": 1, "price_5m": 1}
p = {"priceChange": {"h1": 5, "h24": 0}, "volume": {"h24": 100_000, "h1": 5_000}, "liquidity": {"usd": 100_000}, "txns": {"h1": {"buys": 13, "sells": 10}}}
assert grok.entry_fails(p, ok) == []
assert grok.entry_fails(p, {**ok, "buy_volume_6h": 0})
assert grok.entry_fails({**p, "priceChange": {"h1": 40, "h24": 0}}, ok)
assert grok.entry_fails({**p, "txns": {"h1": {"buys": 12, "sells": 10}}}, ok)
assert grok.entry_fails(p, {**ok, "price": 0.9})
print("ok")

# shadow flags (log only)
grok.get = lambda url: {"pairs": [{"chainId": "solana", "baseToken": {"symbol": "T", "address": "OTHER"}, "marketCap": 900_000, "volume": {"h1": 10_000, "h6": 30_000}}]}
sp = {"txns": {"h1": {"buys": 500, "sells": 500}}, "volume": {"h1": 5_000}, "marketCap": 1_000_000, "liquidity": {"usd": 50_000}, "baseToken": {"symbol": "T"}}
fl = grok.shadow_flags(sp, "MINE")
assert any("avg_trade" in x for x in fl) and any("liq/mcap" in x for x in fl) and any("vamp" in x for x in fl), fl
grok.get = lambda url: {"pairs": []}
assert grok.shadow_flags({**sp, "volume": {"h1": 50_000}, "liquidity": {"usd": 300_000}}, "MINE") == []
print("shadow ok")

# ghost tracker: outcome per sampled price, and follow-up through a batched DexScreener reply
x = {"p0": 1.0}
assert grok.ghost_out(x, 0.91, 1) == "stop" and grok.ghost_out(x, 1.25, 1) == "tp"
assert grok.ghost_out(x, 1.05, 1) is None and grok.ghost_out(x, 1.05, 24) == "end" and grok.ghost_out(x, None, 1) == "rug"
assert abs(grok.ghost_score({"out": "tp"}) - (1.2 * 0.99 ** 4 - 1)) < 1e-9
import tempfile, pathlib
grok.GHOSTS = pathlib.Path(tempfile.mkdtemp()) / "g.json"
grok.ghost_add([("A", "A", 1.0, "entry", "x"), ("B", "B", 2.0, "judge", "y"), ("C", "C", None, "safety", "z")])
grok.ghost_add([("A", "A", 1.1, "entry", "x")])  # still open, not added twice
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "A"}, "priceUsd": "1.3", "liquidity": {"usd": 5}}]
grok.cmd_ghost_update()
assert not grok.ghost_load()[1]["out"]  # first miss is not a rug yet
grok.cmd_ghost_update()
g = {x["mint"]: x for x in grok.ghost_load()}
assert len(g) == 2 and g["A"]["out"] == "tp" and g["B"]["out"] == "rug" and g["B"]["ret"] == -1.0, g
grok.cmd_ghost_report()
print("ghost ok")
