#!/usr/bin/env python3
"""Offline checks for funding.py: accrual only while on, switch cost, the 7-day filter."""
import funding

H = 3600 * 1000
now = 1000 * H


def fresh():
    return dict(sleeve={k: 100.0 for k in funding.COINS}, on={k: False for k in funding.COINS}, last_t=now - 24 * H,
                log=[], history=[])


pos = {k: [(now - i * H, 0.0001) for i in range(24 * 8)][::-1] for k in funding.COINS}
neg = {k: [(t, -r) for t, r in pos[k]] for k in funding.COINS}

s = fresh()                                      # off -> filter turns it on: pays the switch, earns nothing yet
funding.step("fund7", s, pos, now, "d1")
assert all(s["on"].values()) and abs(s["sleeve"]["BTC"] - 100 * (1 - funding.COST)) < 1e-9, s

start = s["sleeve"]["BTC"]                       # next day on: earns 24 hours of funding, no new switch
s["last_t"] = now - 24 * H
funding.step("fund7", s, pos, now, "d2")
assert abs(s["sleeve"]["BTC"] - start * 1.0001 ** 24) < 1e-9 and len(s["log"]) == 3, s

s = fresh()                                      # negative week keeps fund7 out
funding.step("fund7", s, neg, now, "d1")
assert not any(s["on"].values()) and s["sleeve"]["ETH"] == 100.0

s = fresh()                                      # the control is always on, even through negative funding
funding.step("fundon", s, neg, now, "d1")
assert all(s["on"].values())
print("funding ok")

# pick accounts: top-3 by 7-day mean among the pool, drop a coin that fell out, pay COST each way
hist = {k: [(now - i * H, r) for i in range(24 * 8)][::-1] for k, r in (("A", 3e-5), ("B", 2e-5), ("C", 1e-5), ("D", -1e-5), ("E", 5e-6))}
s = dict(cash=300.0, sleeve={}, last_t=now - 24 * H, log=[], history=[])
funding.pick_step("fundtop3_500", s, hist, now, "d1", list(hist))
assert sorted(s["sleeve"]) == ["A", "B", "C"] and abs(s["sleeve"]["A"] - 100 * (1 - funding.COST)) < 1e-9, s
hist["C"] = [(t, -1e-4) for t, _ in hist["C"]]
s["last_t"] = now - 24 * H
funding.pick_step("fundtop3_500", s, hist, now, "d2", list(hist))
assert sorted(s["sleeve"]) == ["A", "B", "E"], s
s = dict(cash=500.0, sleeve={}, last_t=now, log=[], history=[])
funding.pick_step("fundhi_500", s, {k: hist[k] for k in "ABDE"}, now, "d1", list("ABDE"))
assert sorted(s["sleeve"]) == ["A", "B"], s                     # 10%/yr floor is ~1.14e-5 per hour: only A and B pass
print("funding picks ok")
