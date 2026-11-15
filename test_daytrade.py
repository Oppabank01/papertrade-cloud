#!/usr/bin/env python3
"""Offline checks for daytrade.py: grid fills and round trips, 09:00 booking, dip entry/exits, funding spike carry."""
from datetime import datetime
import daytrade as d

M = d.MIN
t0 = int(datetime(2026, 11, 16, 10, 0, tzinfo=d.TH).timestamp() * 1000)   # 10:00 Bangkok, day "2026-11-16"

# grid: price 100, dips to 99.4 (fills level 1 at 99.5), back to 100.1 (sells at 99.995) = one round trip
s = dict(cash=100.0, last_t=t0 - M, log=[], days=[], px=0, grid=[], center=0)
d.grid_step(s, [(t0, 100, 100, 100, 100), (t0 + M, 100, 100, 99.4, 99.6), (t0 + 2 * M, 99.6, 100.1, 99.6, 100)])
assert s["trips"] == 1 and not any(lv["qty"] for lv in s["grid"]), s
gain = 12.5 * (1 - d.FEE) / 99.5 * 99.5 * 1.005 * (1 - d.FEE) - 12.5
assert abs(s["cash"] - (100 + gain)) < 1e-9, (s["cash"], gain)
# a fill and its sell never happen in the same candle (unknown order inside the minute)
s2 = dict(cash=100.0, last_t=t0 - M, log=[], days=[], px=0, grid=[], center=0)
d.grid_step(s2, [(t0, 100, 100, 100, 100), (t0 + M, 100, 100.2, 99.4, 100)])
assert not s2.get("trips") and s2["grid"][0]["qty"] > 0
# 09:00 next day: holdings sold at the open, the day is booked, a new grid starts
t9 = int(datetime(2026, 11, 17, 9, 0, tzinfo=d.TH).timestamp() * 1000)
d.grid_step(s2, [(t9, 99, 99, 99, 99)])
assert s2["days"][0]["day"] == "2026-11-16" and s2["days"][0]["ret"] < 0 and s2["day"] == "2026-11-17" and s2["center"] == 99, s2

# dip: BTC falls 2.5% over 60 min -> buy; next candle hits +1.5% -> take profit
cs = [(t0 + i * M, 100 - i * 2.5 / 60, 100, 100 - i * 2.5 / 60, 100 - i * 2.5 / 60) for i in range(61)]
cs.append((t0 + 61 * M, 97.5, 99.1, 97.5, 98))
s = dict(cash=30.0, last_t=t0 + 59 * M, log=[], days=[], px={}, pos={}, cool={})
d.dip_step(s, {"BTC": cs, "ETH": [], "SOL": []})
kinds = [(x["kind"], x.get("why")) for x in s["log"]]
assert kinds[0][0] == "buy" and kinds[1] == ("sell", "tp") and not s["pos"], kinds
# stop is checked before take-profit when one candle touches both
s = dict(cash=30.0, last_t=t0 + 59 * M, log=[], days=[], px={}, pos={}, cool={})
cs[-1] = (t0 + 61 * M, 97.5, 99.5, 94, 98)
d.dip_step(s, {"BTC": cs, "ETH": [], "SOL": []})
assert s["log"][-1]["why"] == "stop" and s["log"][-1]["pnl"] < 0, s["log"]

# funding spike: enters above 0.01%/h, accrues the hourly rate, leaves when it falls under 0.002%
s = dict(cash=30.0, last_t=t0, log=[], days=[], px={}, sleeve={})
d.spike_step(s, {"AAA": 0.0002, "BBB": 0.00005}, {}, t0 + M)
assert list(s["sleeve"]) == ["AAA"] and abs(s["sleeve"]["AAA"] - 10 * (1 - d.SPIKE_COST / 2)) < 1e-9, s
d.spike_step(s, {"AAA": 0.00001}, {"AAA": [(t0 + 60 * M, 0.0002)]}, t0 + 61 * M)
assert not s["sleeve"] and s["log"][-1]["kind"] == "sell" and abs(s["cash"] - (20 + 10 * (1 - 0.003) * 1.0002 * (1 - 0.003))) < 1e-9, s
print("daytrade ok")
