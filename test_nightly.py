#!/usr/bin/env python3
"""Offline: a night starts fresh, mirrors new source buys, halts at its target, settles at 09:00, starts again."""
import json, sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import nightly, agents, grok
agents.jup_prices = lambda ms: {p["baseToken"]["address"]: float(p["priceUsd"]) for p in (agents.grok.get(agents.grok.DEX + ",".join(ms)) or []) if isinstance(p, dict) and p.get("priceUsd")} if ms else {}   # second source mirrors the mocked DexScreener
TH = grok.TH
d = Path(tempfile.mkdtemp()); nightly.HERE = d
assert nightly.night_of(datetime(2026, 11, 13, 22, tzinfo=TH)) == "2026-11-13"
assert nightly.night_of(datetime(2026, 11, 14, 3, tzinfo=TH)) == "2026-11-13"
assert nightly.night_of(datetime(2026, 11, 14, 12, tzinfo=TH)) is None
grok.usdthb = lambda: 50.0                     # 500 THB = $10
price = {"v": 1.0}
grok.pair = lambda m: {"priceUsd": str(price["v"])}
grok.get = lambda url: [{"chainId": "solana", "baseToken": {"address": "M"}, "priceUsd": str(price["v"]), "liquidity": {"usd": 1}}]
src = d / "state_recipe_insider.json"
src.write_text(json.dumps({"log": [{"t": "2026-11-13T20:00:00+07:00", "kind": "buy", "mint": "OLD", "sym": "OLD"}]}))
t = lambda day, h, m=0: datetime(2026, 11, day, h, m, tzinfo=TH)
nightly.tick("runner", t(13, 21, 5))                            # session opens, OLD buy is ignored
s = json.loads((d / "state_night_runner.json").read_text())
assert abs(s["cash"] - 10) < 1e-9 and not s["pos"], s
src.write_text(json.dumps({"log": [{"t": "2026-11-13T20:00:00+07:00", "kind": "buy", "mint": "OLD", "sym": "OLD"},
                                   {"t": "2026-11-13T21:10:00+07:00", "kind": "buy", "mint": "M", "sym": "MOON"}]}))
nightly.tick("runner", t(13, 21, 12))                           # mirrors M with 40%
s = json.loads((d / "state_night_runner.json").read_text())
assert list(s["pos"]) == ["M"] and abs(s["pos"]["M"]["cost"] - 4.0) < 1e-9
nightly.agents._dex.clear()                                     # time has passed: drop the shared price pool
price["v"] = 3.0                                                # +200% on 40% => night ~ +70%: beats the +50% target
nightly.tick("runner", t(13, 23))
s = json.loads((d / "state_night_runner.json").read_text())
assert not s["pos"] and "ถึงเป้า" in s["session"]["halted"], s["session"]
nightly.tick("runner", t(14, 9, 5))                             # morning settles one night
s = json.loads((d / "state_night_runner.json").read_text())
n = s["nights"]; assert len(n) == 1 and n[0]["ret"] > 0.5 and n[0]["night"] == "2026-11-13", n
nightly.tick("runner", t(14, 21, 3))                            # next evening: fresh 500 THB again
s = json.loads((d / "state_night_runner.json").read_text())
assert abs(s["cash"] - 10) < 1e-9 and s["session"]["night"] == "2026-11-14"
print("nightly ok")
