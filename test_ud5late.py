#!/usr/bin/env python3
"""ud5late buys the 0.50-0.90 side once per window in the last minute and settles from Gamma (no network: stubs)."""
import json, os, random, tempfile
os.environ["UD5_DIR"] = tempfile.mkdtemp()
import ud5late as U

ts = 1795495200
book = {"up": {"asks": [{"price": "0.72", "size": "100"}], "bids": []}, "dn": {"asks": [{"price": "0.30", "size": "100"}], "bids": []}}
def get(url, params=None):
    if params.get("closed") == "true":
        return [dict(outcomePrices=json.dumps(["1", "0"]))]
    return [dict(acceptingOrders=True, enableOrderBook=True, question="Bitcoin Up or Down", clobTokenIds=json.dumps(["up", "dn"]), outcomes=json.dumps(["Up", "Down"]))]
U.P.get, U.P.books = get, lambda toks: book
U.F.tokens = lambda m: ["up", "dn"]
U.P.levels = lambda b, side: [(float(x["price"]), float(x["size"])) for x in b[side]] if b else []
sr, st = U.load(U.RULE), U.load(U.TWIN)
U.step(sr, st, ts + 100, random.Random(1)); assert not sr["pos"]           # too early
U.step(sr, st, ts + 250, random.Random(1)); assert sr["pos"][str(ts)]["oi"] == 0 and sr["pos"][str(ts)]["entry"] == 0.72
U.step(sr, st, ts + 260, random.Random(1)); assert len(sr["log"]) == 1   # once per window
U.settle(sr, ts + 400)
sell = sr["log"][-1]
assert sell["kind"] == "sell" and sell["px"] == 1.0 and abs(sell["ret"] - (1 / (0.72 + 0.05 * 0.72 * 0.28) - 1)) < 1e-5
assert abs(sr["cash"] - (sr["start_usd"] + sell["pnl"])) < 1e-9
print("ok")
