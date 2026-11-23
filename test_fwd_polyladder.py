#!/usr/bin/env python3
"""fwd_polyladder on a made-up poly_fav state: wins compound by 1/cost, a loss ends the attempt, no reuse of an event or of a resolved buy."""
import fwd_polyladder as L
from byttrade import new_state

def buy(tok, t, px=0.87, ev=None, end_h=2):
    return dict(kind="buy", t=t, token=tok, px=px, usd=0.88, qty=1.0, event=ev or tok, end_h=end_h, coin=tok)
def sell(tok, t, won):
    return dict(kind="sell", t=t, token=tok, px=1.0 if won else 0.0)

s = new_state("t"); s["after"] = "2026-01-01T00"
fav = dict(log=[buy("a", "2026-01-01T01"), buy("x", "2026-01-01T01", px=0.95)], pos={"a": {}, "x": {}})
L.step(s, fav, "")
assert s["lad"]["token"] == "a" and len([x for x in s["log"] if x["kind"] == "buy"]) == 1
fav["log"] += [sell("a", "2026-01-01T02", True), buy("b", "2026-01-01T01b", ev="a"), buy("c", "2026-01-01T03")]
fav["pos"] = {"c": {}, "b": {}}
L.step(s, fav, "")
assert abs(s["lad"]["v"] - 1 / 0.88) < 1e-9 and s["lad"]["token"] == "c"    # b is older than the win and same event
fav["log"] += [sell("c", "2026-01-01T04", False)]
L.step(s, fav, "")
assert s["lad"] is None and s["log"][-1]["ret"] == -1.0
s2 = new_state("t"); s2["after"] = "2026-01-01T00"; s2["lad"] = dict(v=19.0, wins=24, unit=1.0, token="z", event="z", cost=0.88, coin="z", t="")
L.step(s2, dict(log=[sell("z", "2026-01-02", True)], pos={}), "")
assert s2["lad"] is None and s2["log"][-1]["ret"] > 19 and s2["cash"] > s2["start_usd"]
print("polyladder ok: compounding, loss, event and resolved-buy filters, x20 bank")
