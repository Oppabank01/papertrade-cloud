#!/usr/bin/env python3
"""Offline: curve parsing rejects other account types, buy/sell math charges costs and never pays out more than the curve
holds, and a full run buys a fresh wallets.py skip then stops out on a price drop and treats a vanished curve as a rug."""
import base64, json, struct, sys, tempfile
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import curve as C

SOL = 100.0
def acct(vt, vs, rt, rs, done=0, owner=C.PUMP, disc=C.DISC):
    raw = disc + struct.pack("<5Q", vt, vs, rt, rs, 10**15) + bytes([done]) + bytes(117)
    return {"owner": owner, "data": [base64.b64encode(raw).decode(), "base64"]}

c = C.parse(acct(800 * 10**12, 30 * 10**9 + 20 * 10**9, 600 * 10**12, 20 * 10**9))
assert c and c["rs"] == 20 * 10**9 and not c["done"]
assert C.parse(acct(1, 30 * 10**9 + 5, 1, 5, owner="x")) is None
assert C.parse(acct(1, 30 * 10**9 + 5, 1, 5, disc=bytes(8))) is None
assert C.parse(acct(1, 5, 1, 9)) is None                                         # more real than virtual: not a curve
p = C.spot(c, SOL)
q = C.buy_qty(c, 3.0, SOL)
assert q < 3.0 / p * (1 - C.FEE) * (1 - C.SLIP)                                 # costs and price impact both charged
back = C.sell_usd(c, q, SOL)
assert 3.0 * 0.90 < back < 3.0 * (1 - C.FEE) ** 2 * (1 - C.SLIP) ** 2, back      # round trip loses about the costs
empty = dict(c, rs=10**5)                                                       # curve drained by the dumpers
assert C.sell_usd(empty, q, SOL) == 0.0
assert C.buy_qty(dict(c, rt=1), 3.0, SOL) is None

# full run with fake data
d = Path(tempfile.mkdtemp())
C.agents.STATE, C.SRC = d / "state_curve.json", d / "state_wallets.json"
C.grok.usdthb = lambda: 33.0
now = C.grok.now()
iso = lambda dt: dt.isoformat(timespec="seconds")
C.cmd_init(500)
s = C.agents.load(); s["seen_t"] = iso(now - timedelta(minutes=5)); C.agents.save(s)
M, OLD, THIN = "Mint1pump", "Old1pump", "Thin1pump"
skip = lambda m, ago: dict(t=iso(now - timedelta(minutes=ago)), kind="skip", mint=m, sym=m[:4], wallet="w1", usd=300, why="liq $0")
C.SRC.write_text(json.dumps({"log": [skip(OLD, 30), skip(M, 1), skip(THIN, 1)]}))
book = {"cM": acct(800 * 10**12, 30 * 10**9 + 20 * 10**9, 600 * 10**12, 20 * 10**9),
        "cT": acct(1000 * 10**12, 30 * 10**9 + 10**9, 790 * 10**12, 10**9)}
C.wallets.sol_usd = lambda: SOL
BTCQ = "Btcq1pump"                                                               # a curve quoted in BTC, not SOL
C.SRC.write_text(json.dumps({"log": [skip(OLD, 30), skip(M, 1), skip(THIN, 1), skip(BTCQ, 1)]}))
C.grok.get = lambda url: [{"dexId": "pumpfun", "baseToken": {"address": m}, "pairAddress": a, "quoteToken": {"address": qa}}
                          for m, a, qa in ((M, "cM", C.WSOL), (THIN, "cT", C.WSOL), (BTCQ, "cM", "BTCmint")) if m in url]
C.wallets.rpc = lambda method, params: {"value": [book.get(a) for a in params[0]]}
C.agents.jup_prices = lambda ms: {m: C.spot(C.parse(book["cM"]), SOL) for m in ms if m == M}
C.cmd_run()
s = C.agents.load()
assert list(s["pos"]) == [M], s["pos"]                                         # OLD too stale, THIN only 1 SOL in curve
assert any(x["kind"] == "skip" and x["mint"] == THIN and x["why"].startswith("curve 1.00") for x in s["log"])
assert any(x["kind"] == "skip" and x["mint"] == BTCQ and x["why"] == "not on a SOL pump.fun curve" for x in s["log"])
cost = s["pos"][M]["cost"]
C.cmd_run()                                                                     # no new skips: holds, nothing re-bought
assert len(C.agents.load()["pos"]) == 1
book["cM"] = acct(900 * 10**12, 30 * 10**9 + 10 * 10**9, 700 * 10**12, 10 * 10**9)   # price down ~29%
C.agents.jup_prices = lambda ms: {}
C.cmd_run()
s = C.agents.load()
sell = [x for x in s["log"] if x["kind"] == "sell"][-1]
assert not s["pos"] and sell["why"].startswith("stop") and sell["pnl"] < -cost * 0.3, sell
s["pos"]["Gone"] = dict(sym="Gone", qty=1.0, entry=1.0, last=1.0, peak=1.0, cost=1.0, curve="missing", opened=iso(now))
C.agents.save(s)
for _ in range(C.agents.MISS_N):
    C.cmd_run()
s = C.agents.load()
assert not s["pos"] and s["log"][-1]["why"].startswith("curve/pool หาย"), s["log"][-1]
print("curve ok")
