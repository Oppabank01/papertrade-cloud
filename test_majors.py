#!/usr/bin/env python3
"""Offline: sleeves go all in/out on SMA50, weekly accounts hit their target weights once a week, costs are charged."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import majors as M
M.HERE = Path(tempfile.mkdtemp())
M.get = lambda p: {"price": "32"}
M.cmd_init(3200)                                  # $100 each
up = [1.0] * 49 + [1.0 + i * 0.01 for i in range(11)]          # last close above SMA50
down = [2.0] * 50 + [1.0] * 10
c = {k: (up if k in ("BTC", "ETH") else down) for k in M.COINS}
px = {k: c[k][-1] for k in M.COINS}
for name in M.ACCOUNTS:
    s = json.loads(M.path(name).read_text())
    assert abs(M.equity(s, px) - 100) < 1e-9, name
    M.step(name, s, c, px, "2026-11-16")
    M.path(name).write_text(json.dumps(s))
b = json.loads(M.path("btc50").read_text()); assert b["sleeve"]["BTC"] == 0 and abs(M.equity(b, px) - 100 * (1 - M.COST)) < 1e-9
t = json.loads(M.path("trend6").read_text()); assert set(k for k, q in t["qty"].items() if q > 0) == {"BTC", "ETH"}
h = json.loads(M.path("hold6").read_text()); w = {k: h["qty"][k] * px[k] / M.equity(h, px) for k in M.COINS}
assert all(abs(x - 1 / 6) < 0.01 for x in w.values()) and h["cash"] >= -1e-9, (w, h["cash"])
v = json.loads(M.path("vt6").read_text()); assert set(k for k, q in v["qty"].items() if q > 0) == {"BTC", "ETH"} and v["cash"] > 50
n = len(h["log"]); M.step("hold6", h, c, px, "2026-11-17"); assert len(h["log"]) == n      # same week: no trades
print("majors ok")
