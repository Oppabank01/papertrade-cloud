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
zoo.use("savip"); assert agents.HALF_AT == 0.30 and agents.COOLDOWN_H == 0 and agents.STOP == -0.06
hot = {**safe, "address": "H", "smart_degen_count": 10, "renowned_count": 5, "buys": 400, "holder_count": 2000}
assert zoo.score(hot) == 100 and {t["address"] for t in zoo.picks("savip", rank + [hot])} == {"H"}
zoo.use("safe"); assert agents.TP_ALL is None and agents.HALF_AT is None and agents.COOLDOWN_H == 24 and agents.PER_TRADE == 0.20
assert agents.TP_ALL is None and agents.STOP == -0.08     # overrides never leak to the next account
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
# half take-profit: +30% sells half once, the rest stays and trails
zoo.use("safe"); agents.HALF_AT, agents.TRAIL_ON = 0.30, 0.30; s = agents.load(); s.update(cash=0, pos={"X": dict(sym="X", qty=10, entry=1, last=1, peak=1, cost=10, opened=grok.now().isoformat())}); agents.save(s)
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "X"}, "priceUsd": "1.3", "liquidity": {"usd": 1}}]
agents.cmd_run(); agents.cmd_run()
s = agents.load(); q = s["pos"]["X"]
assert q["half"] and abs(q["qty"] - 5) < 1e-9 and abs(q["cost"] - 5) < 1e-9 and sum(x["kind"] == "sell" for x in s["log"]) == 1
print("half ok")
# fast accounts: RugCheck filter, MISS_N per account, background watcher sells between ticks
import importlib; importlib.reload(zoo); zoo.HERE = d; zoo.HIST = d / "hist"; zoo.RANK = d / "rank.json"; zoo.LOCKS = d / "locks"; zoo.STOP_FILE = zoo.LOCKS / "watch.stop"
grok.get = lambda url: {"risks": [{"level": "danger", "name": "LP unlocked"}]} if "rugcheck" in url and "R" in url else {"risks": []}
big1 = {**base, "address": "G", "liquidity": 300_000, "market_cap": 3e6}
big2 = {**big1, "address": "R"}
assert {t["address"] for t in zoo.picks("bigliqRC", [big1, big2])} == {"G"} and {t["address"] for t in zoo.picks("bigliqF", [big1, big2])} == {"G", "R"}
zoo.use("bigliqF"); assert agents.MISS_N == 15
zoo.use("safe"); assert agents.MISS_N == 2
zoo.use("bigliqF"); agents.cmd_init(500); s = agents.load()
s.update(pos={"G": dict(sym="G", qty=1, entry=1, last=1, peak=1, cost=1, opened=grok.now().isoformat())}); agents.save(s)
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "G"}, "priceUsd": "0.9", "liquidity": {"usd": 1}}]
zoo.cmd_watch(0.3, every=0.1)
zoo.use("bigliqF"); s = agents.load()
assert not s["pos"] and s["log"][-1]["kind"] == "sell" and s["log"][-1]["why"].startswith("stop"), s["log"][-1]
zoo.cmd_stopwatch(); zoo.cmd_watch(5, every=0.1)        # a stale stop file is cleared at start (runs the full 5 s)
print("fast ok")
# X recipes from x_recipes.json: spec -> account, bad entries skipped, night accounts close at 09:00 and book the night
from datetime import datetime
spec = d / "x.json"
spec.write_text(json.dumps([
    dict(name="x_ok", label="t", horizon="night", entry=dict(min={"liquidity": 100_000}, safe=False, up=True), pick=dict(by="volume", take=1), exit={"STOP": -0.1}),
    dict(name="x_badkey", label="t", horizon="week", entry=dict(min={"nope": 1})),
    dict(name="x_badexit", label="t", horizon="week", exit={"EVAL": 1}),
    dict(name="x_badhz", label="t", horizon="year"),
    dict(name="rand", label="t", horizon="week"),
    dict(name="x_off", label="t", horizon="month", active=False)]))
zoo.load_specs(spec)
assert "x_ok" in zoo.ZOO and "x_off" in zoo.ZOO and "x_ok" in zoo.FAST and not any(k in zoo.ZOO for k in ("x_badkey", "x_badexit", "x_badhz"))
assert zoo.ZOO["rand"][0] != "t"
v1, v2 = {**big1, "volume": 5}, {**big1, "address": "V", "volume": 9}
assert [t["address"] for t in zoo.picks("x_ok", [v1, v2, {**base, "address": "L"}])] == ["V"]
zoo.use("x_ok"); assert agents.STOP == -0.1 and agents.MISS_N == 15
(d / "bad.json").write_text("{nope"); zoo.load_specs(d / "bad.json")      # unreadable file: message, no crash
zoo.RANK.write_text(json.dumps(dict(t=time.time() + 99, rank=[v2])))
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": m}, "priceUsd": "1.0", "liquidity": {"usd": 1}} for m in url.rsplit("/", 1)[1].split(",")]
zoo.use("x_ok"); agents.cmd_init(500); zoo.use("x_off"); agents.cmd_init(500)
grok.now = lambda: datetime(2026, 11, 14, 12, 0, tzinfo=grok.TH)   # daytime: night account does not buy
zoo.cmd_tick(); zoo.use("x_ok"); assert not agents.load()["pos"]
grok.now = lambda: datetime(2026, 11, 14, 22, 0, tzinfo=grok.TH)
zoo.RANK.write_text(json.dumps(dict(t=time.time() + 199, rank=[v2]))); zoo.cmd_tick()
zoo.use("x_ok"); assert list(agents.load()["pos"]) == ["V"]
zoo.use("x_off"); assert not agents.load()["pos"]          # inactive recipe never buys
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "V"}, "priceUsd": "1.05", "liquidity": {"usd": 1}}]
grok.now = lambda: datetime(2026, 11, 15, 9, 5, tzinfo=grok.TH); zoo.cmd_tick()
zoo.use("x_ok"); s = agents.load()
assert not s["pos"] and s["nights"][0]["night"] == "2026-11-14" and s["log"][-1]["why"] == "ปิดรอบเช้า", (s["pos"], s.get("nights"))
print("x recipes ok")
