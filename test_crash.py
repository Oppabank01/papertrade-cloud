#!/usr/bin/env python3
"""Offline checks for crash.py: crash-day bounce entry/exit, night short booking, new-listing short and its stop."""
from datetime import datetime
import crash as c

H = c.H
st = lambda: dict(start_usd=100.0, cash=100.0, pos={}, cool={}, log=[], nights=[], pending={}, known=[], hour=0)
mk = {"BTC": (90.0, 0.0, 9e9), "AAA": (80.0, 0.0001, 5e8), "BBB": (100.0, 0.0, 4e8)}
down = lambda r: [100.0] * 6 + [100.0 * (1 + r)] * 24          # 30 closes, last 24 at the new level: 24h change = r
t0 = int(datetime(2026, 11, 19, 10, 0, tzinfo=c.TH).timestamp() * 1000)

# crash bounce: AAA -20% while BTC -10% -> long; BBB -5% ignored; BTC never bought
s = st()
c.step("c_crashbounce_24h_500", s, mk, {"BTC": down(-0.10), "AAA": down(-0.20), "BBB": down(-0.05)}, t0, True)
assert list(s["pos"]) == ["AAA"] and abs(s["cash"] - 80) < 1e-9 and s["pos"]["AAA"]["side"] == 1, s
# BTC filter: same coin drop but BTC only -2% -> no trade
s2 = st(); c.step("c_crashbounce_24h_500", s2, mk, {"BTC": down(-0.02), "AAA": down(-0.20)}, t0, True); assert not s2["pos"]
# hourly funding (longs pay), then sold 24h later at +10%
c.step("c_crashbounce_24h_500", s, {**mk, "AAA": (88.0, 0.0001, 5e8)}, {}, t0 + H, True)
c.step("c_crashbounce_24h_500", s, {**mk, "AAA": (88.0, 0.0001, 5e8)}, {}, t0 + 24 * H, False)
want = 80 + 20 * (1 - 0.0025) * (1 - 0.0001) * 1.1 * (1 - 0.0025)
assert not s["pos"] and abs(s["cash"] - want) < 1e-9 and s["log"][-1]["why"] == "ครบ 24 ชม.", (s["cash"], want)

# night short: at 21:00 short the -12% coin, price falls 10% overnight, covered and booked at 09:00
t21 = int(datetime(2026, 11, 19, 21, 0, tzinfo=c.TH).timestamp() * 1000)
s = st()
c.step("n_crashshort_500", s, mk, {"AAA": [100.0] * 24 + [88.0] * 6, "BBB": [100.0] * 30}, t21, True)
assert list(s["pos"]) == ["AAA"] and s["pos"]["AAA"]["side"] == -1 and s["night"] == "2026-11-19", s
c.step("n_crashshort_500", s, {**mk, "AAA": (72.0, 0.0, 5e8)}, {}, t21 + 12 * H, True)
r = s["nights"][0]["ret"]
assert not s["pos"] and r > 0 and abs(r - (20 * (1 - 0.0025) * 1.0001 * 1.1 * (1 - 0.0025) - 20) / 100) < 1e-4, s["nights"]

# new listing: first run only learns the list; a coin that appears is shorted the next UTC day; +50% stop
s = st()
c.step("l_newlist_short_500", s, mk, {}, t0, True); assert sorted(s["known"]) == sorted(mk) and not s["pending"]
c.step("l_newlist_short_500", s, {**mk, "NEW": (1.0, 0.0, 1e6)}, {}, t0 + H, True); assert s["pending"] and not s["pos"]
c.step("l_newlist_short_500", s, {**mk, "NEW": (2.0, 0.0, 1e6)}, {}, t0 + 22 * H, True)
assert s["pos"]["NEW"]["entry"] == 2.0 and abs(s["cash"] - 90) < 1e-9, s
c.step("l_newlist_short_500", s, {**mk, "NEW": (3.1, 0.0, 1e6)}, {}, t0 + 23 * H, False)
assert not s["pos"] and s["log"][-1]["why"] == "stop +50%" and s["log"][-1]["pnl"] < -5, s["log"]
print("crash ok")
