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
