#!/usr/bin/env python3
"""Offline: each zoo rule picks its pattern, exits are set per account, rankings are used once and archived."""
import json, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import zoo, agents, grok
agents.jup_prices = lambda ms: {p["baseToken"]["address"]: float(p["priceUsd"]) for p in (agents.grok.get(agents.grok.DEX + ",".join(ms)) or []) if isinstance(p, dict) and p.get("priceUsd")} if ms else {}   # second source mirrors the mocked DexScreener
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
from datetime import datetime, timedelta
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
# agent rules: a second price source must agree within 1% to buy; disagreement prices exits at the lower source; long disagreement halts buys
zoo.use("bigliqF"); agents.STATE = d / "state_pricecheck.json"; agents.save(dict(start_usd=10, cash=10, pos={}, log=[])); s = agents.load()
grok.pair = lambda m: {"priceUsd": "1.0"}
agents.jup_prices = lambda ms: {m: 1.05 for m in ms}
assert agents.paper_buy(s, "Q", "Q").startswith("price mismatch") and "Q" not in s["pos"]
agents.jup_prices = lambda ms: {}
assert agents.paper_buy(s, "Q", "Q") == "price unverified"
agents.jup_prices = lambda ms: {m: 1.0 for m in ms}
assert agents.paper_buy(s, "Q", "Q") is None and s["log"][-1]["stop_set"] == agents.STOP; agents.save(s)
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "Q"}, "priceUsd": "1.0", "liquidity": {"usd": 1}}]
agents.jup_prices = lambda ms: {m: 0.90 for m in ms}       # sources disagree by 10%: exit check uses 0.90, which hits the -8% stop
agents.cmd_run(); s = agents.load()
assert "Q" not in s["pos"] and s["log"][-1]["why"].startswith("stop") and s["log"][-1]["price"] == 0.90, s["log"][-1]
s.update(pos={"Q": dict(sym="Q", qty=1, entry=1, last=1, peak=1, cost=1, opened=grok.now().isoformat())}); agents.save(s)
agents.STOP = -0.5; agents.jup_prices = lambda ms: {m: 0.98 for m in ms}
for _ in range(agents.GAP_HALT_N): agents.cmd_run()
s = agents.load(); assert s.get("halted") and agents.paper_buy(s, "Z", "Z") in ("account halted",), s.get("halted")
print("price check ok")
# halt fixes as new accounts: mode 1 bans only the gapped coin, mode 2 pauses all buys for PAUSE_H then resumes
held = lambda: {"Q": dict(sym="Q", qty=1, entry=1, last=1, peak=1, cost=1, opened=grok.now().isoformat())}
gap, ok_px = (lambda ms: {m: 0.98 for m in ms}), (lambda ms: {m: 1.0 for m in ms})
agents.HALT_MODE = 1; agents.save(dict(start_usd=10, cash=10, pos=held(), log=[])); agents.jup_prices = gap
for _ in range(agents.GAP_HALT_N): agents.cmd_run()
s = agents.load(); agents.jup_prices = ok_px
assert not s.get("halted") and s["banned"] == {"Q": "Q"} and s["log"][-1]["kind"] == "ban", s
assert agents.paper_buy(s, "Q", "Q") == "coin banned: price gap" and agents.paper_buy(s, "Z", "Z") is None
agents.HALT_MODE = 2; agents.save(dict(start_usd=10, cash=10, pos=held(), log=[])); agents.jup_prices = gap
for _ in range(agents.GAP_HALT_N): agents.cmd_run()
s = agents.load(); agents.jup_prices = ok_px
assert s.get("halted") and s["halted_until"] > grok.now().isoformat() and agents.paper_buy(s, "Z", "Z") == "account halted"
s["halted_until"] = (grok.now() - timedelta(minutes=1)).isoformat()
assert agents.paper_buy(s, "Z", "Z") is None and not s.get("halted") and any(x["kind"] == "resume" for x in s["log"]), s
agents.HALT_MODE = 0; agents.STOP = -0.08
zoo.use("w_ban_aged"); assert agents.HALT_MODE == 1 and agents.STOP == -0.08
zoo.use("agedF"); assert agents.HALT_MODE == 0                    # no leak back to the original accounts
print("halt modes ok")
# agent rules: death at 20+ sells below rand, pass at 50+ sells positive and above rand
st = lambda n, eq: dict(start_usd=10, cash=eq, pos={}, log=[{"kind": "sell", "pnl": 0}] * n)
a = st(20, 5); zoo.verdict("x", a, -0.3); assert a.get("dead")
b = st(19, 5); zoo.verdict("x", b, -0.3); assert not b.get("dead")
c = st(50, 11); zoo.verdict("x", c, -0.3); assert c.get("passed") and not c.get("dead")
r = st(30, 1); zoo.verdict("rand", r, 0.5); assert not r.get("dead")
print("verdict ok")
# null exits in a recipe mean "off", never None in the exit math; one crashing account does not stop the round
(d / "null.json").write_text(json.dumps([dict(name="x_null", label="t", horizon="week", exit={"TRAIL_ON": None, "TRAIL": None, "TP_ALL": None})]))
zoo.load_specs(d / "null.json"); zoo.use("x_null"); assert agents.TRAIL_ON == 9 and agents.TRAIL == 0.15 and agents.TP_ALL is None
calls = []
real = zoo.tick_one
zoo.tick_one = lambda n, *a: calls.append(n) or (_ for _ in ()).throw(RuntimeError("boom")) if n == list(zoo.ZOO)[0] else calls.append(n)
zoo.cmd_tick(); zoo.tick_one = real
assert len(calls) == len(zoo.ZOO), (len(calls), len(zoo.ZOO))
print("robust ok")
# market breadth: share of ranked coins up over 1h, attached to every coin each round, usable as a recipe gate
zoo.RANK.write_text(json.dumps(dict(t=1, rank=[dict(address=f"m{i}", price_change_percent1h=c) for i, c in enumerate([5, 2, 1, -3])])))
seen = []
zoo.tick_one = lambda n, dd, r: seen.append(dd)
zoo.cmd_tick(); zoo.tick_one = real
assert all(t["breadth"] == 0.75 for t in seen[0]["rank"])
assert zoo.spec_rule({"min": {"breadth": 0.74}})(seen[0]["rank"][0]) and not zoo.spec_rule({"max": {"breadth": 0.61}})(seen[0]["rank"][0])
print("breadth ok")
# 5-second accounts: rug/halt round counts scale to the same ~5 min, each watcher loop only touches its own speed, Jupiter cache stays younger than a check
(d / "f5.json").write_text(json.dumps([dict(name="w_f5_t", label="t", horizon="week", entry={"min": {"liquidity": 1}}, exit={"WATCH_S": 5})]))
zoo.load_specs(d / "f5.json"); zoo.use("w_f5_t"); assert agents.MISS_N == 60 and agents.GAP_HALT_N == 60 and agents.WATCH_S == 5
zoo.use("bigliqF"); assert agents.GAP_HALT_N == 15 and agents.WATCH_S == 20      # no leak back to 20 s accounts
touched = []
real_use = zoo.use
zoo.use = lambda n: touched.append(n) or real_use(n)
zoo.cmd_watch(0.05, every=0.01, ws=5); zoo.use = real_use
assert "w_f5_t" in touched and all(zoo.ZOO[n][2].get("WATCH_S") == 5 for n in touched), set(touched)
calls = []
grok.get = lambda url: calls.append(url) or {"J": {"usdPrice": 1.0}}
import importlib.util as iu
spec = iu.spec_from_file_location("agents_real", Path(__file__).parent / "agents.py"); ar = iu.module_from_spec(spec); spec.loader.exec_module(ar)
ar.WATCH_S = 5; ar.jup_prices(["J"]); time.sleep(4.1); ar.jup_prices(["J"]); assert len(calls) == 2      # 5 s checks: 4 s cache, fresh price each check
ar.WATCH_S = 20; ar.jup_prices(["J"]); assert len(calls) == 2                                           # 20 s accounts keep the 15 s cache
print("5s watch ok")
