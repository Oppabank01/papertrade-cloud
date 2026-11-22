"""polymarket.py accounting on saved API samples (data/poly_samples.json, fetched 23 Nov 2026), no network.
  /usr/bin/python3 test_polymarket.py          # offline checks
  /usr/bin/python3 test_polymarket.py live     # plus one live run into a temp folder (real APIs, real state files untouched)"""
import json, random, sys, tempfile, time
from pathlib import Path
import polymarket as P

S = json.load(open(Path(__file__).parent / "data/poly_samples.json"))
M = {m["conditionId"].lower(): m for m in S["open_markets"]}
BK = {b["asset_id"]: b for b in S["books"]}
mkt = S["open_markets"][0]
tok = json.loads(mkt["clobTokenIds"])[0]
close = lambda a, b, e=1e-9: abs(a - b) < e

# --- buy: cash falls by exactly 5% of start; notional + taker fee + slip == that spend; fee follows the docs formula
s = P.new_state("t")
usd = s["start_usd"] * P.SIZE
assert P.buy(s, tok, mkt, 0, BK[tok], "test") is None
q = s["pos"][tok]
assert close(s["cash"], s["start_usd"] - usd) and close(q["usd"], usd)
asks = P.levels(BK[tok], "asks")
assert asks == sorted(asks) and asks[0][0] > 0, "best ask first"
rate, ex = q["fee"]
assert (rate, ex) == (float(mkt["feeSchedule"]["rate"]), float(mkt["feeSchedule"].get("exponent") or 1))
b = s["log"][-1]
notional = q["qty"] * q["entry"]
fee = q["qty"] * rate * (q["entry"] * (1 - q["entry"])) ** ex if q["qty"] <= asks[0][1] else b["fee_usd"]   # one level: exact formula
assert close(b["fee_usd"], fee, 1e-6), (b["fee_usd"], fee)
assert close(notional + b["fee_usd"] + P.SLIP * notional, usd, 1e-5), "spend = notional + fee + slip"
assert q["entry"] >= asks[0][0] - 1e-12, "never fill better than the best ask"
assert q["last"] == P.levels(BK[tok], "bids")[0][0], "marked at the best bid"
assert P.buy(s, tok, mkt, 0, BK[tok], "again") == "holding"
assert P.buy(s, tok, mkt, 0, dict(asks=[], bids=[]), "x") == "holding"
s2 = P.new_state("t"); assert P.buy(s2, tok, mkt, 0, dict(asks=[], bids=[]), "x") == "no asks / book too thin" and s2["cash"] == s2["start_usd"]
s3 = P.new_state("t"); assert P.buy(s3, tok, mkt, 0, dict(asks=[dict(price="0.99", size="1000")]), "x").startswith("price"), "0.99 is outside the band"
s4 = P.new_state("t"); s4["cash"] = usd / 2; assert P.buy(s4, tok, mkt, 0, BK[tok], "x") == "no cash"
print(f"buy ok: {q['qty']:.3f} shares at {q['entry']:.4f}, fee ${b['fee_usd']:.5f}, cost_side {b['cost_side']}")

# --- leader sell: proceeds = bids walked - taker fee - slip; pnl = proceeds - cost; cash conserved
v0 = P.value(s)
bids = P.levels(BK[tok], "bids")
assert P.sell(s, tok, BK[tok], "leader sold") is None and not s["pos"]
x = s["log"][-1]
gross = q["qty"] * bids[0][0] if q["qty"] <= bids[0][1] else None
if gross is not None:
    net = gross - q["qty"] * rate * (bids[0][0] * (1 - bids[0][0])) ** ex - P.SLIP * gross
    assert close(x["usd"], round(net, 5), 1e-5), (x["usd"], net)
    assert close(s["cash"], v0 - (q["qty"] * bids[0][0] - net), 1e-9), "selling at the marked bid only loses fee + slip"
assert close(x["pnl"], x["usd"] - usd, 2e-5) and x["pnl"] < 0, "round trip across the spread loses"
assert close(P.value(s), s["cash"])
assert P.sell(P.new_state("t") | dict(pos={tok: dict(q)}), tok, dict(bids=[]), "x") == "no bids / book too thin"
print(f"leader sell ok: round trip pnl ${x['pnl']:+.4f} ({x['pnl'] / usd:+.1%})")

# --- resolution win and loss with the saved bosona trade (bought Down, payouts [0, 1e6])
tr, res, rm = S["trade"], S["resolution"][0], S["resolved_market"][0]
assert res["status"] == "resolved" and res["payouts"] == [0, 1000000] and tr["outcome"] == "Down" and tr["outcome_index"] == 1
for oi, want in ((1, 1.0), (0, 0.0)):
    pay, why = P.resolved_payout(res, rm, oi)
    assert pay == want, (oi, pay, why)
    assert P.resolved_payout(None, rm, oi)[0] == want, "gamma fallback agrees"
    assert P.resolved_payout(res, None, oi)[0] == want
assert P.resolved_payout(None, None, 1) == (None, None)
assert P.resolved_payout(dict(status="proposed", payouts=None), dict(rm, closed=False), 1) == (None, None), "not resolved yet"
assert P.resolved_payout(res, dict(rm, outcomePrices='["1", "0"]'), 1)[0] is None, "sources disagree: no settlement"
for oi, payout in ((1, 1.0), (0, 0.0)):
    s = P.new_state("t")
    rmk = dict(rm, closed=False, acceptingOrders=True)
    t = json.loads(rm["clobTokenIds"])[oi]
    assert P.buy(s, t, rmk, oi, dict(asks=[dict(price="0.40", size="100")], bids=[dict(price="0.38", size="100")]), "test") is None
    q = s["pos"][t]
    P.settle(s, t, P.resolved_payout(res, rm, oi)[0], "resolved")
    x = s["log"][-1]
    assert close(x["usd"], q["qty"] * payout, 2e-5) and close(x["pnl"], q["qty"] * payout - usd, 2e-5)
    assert close(s["cash"], s["start_usd"] - usd + q["qty"] * payout) and not s["pos"]
    assert (x["pnl"] > 0) == (payout == 1.0)
    if payout == 0:
        assert close(x["pnl"], -usd, 2e-5), "a loss costs exactly the stake"
    print(f"resolution {'win' if payout else 'loss'} ok: pnl ${x['pnl']:+.4f}")

# --- one full run with fake APIs: leader buy -> copy + twin buy; leader sell -> both sell; resolution -> settled
tmp = Path(tempfile.mkdtemp())
P.COPY, P.TWIN = str(tmp / "state_poly_copy.json"), str(tmp / "state_poly_twin.json")
W = "0x" + "a" * 40
P.wallets = lambda: [W]
now = time.time()
copied = dict(mkt, endDate=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 6 * 3600)))
others = [dict(m, endDate=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now + 8 * 3600))) for m in S["open_markets"][1:]]
lead = dict(S["trade"], proxy_wallet=W, side="BUY", token_id=tok, condition_id=mkt["conditionId"], outcome_index=0,
            price=P.levels(BK[tok], "asks")[0][0], size=100, timestamp=int(now) - 120, transaction_hash="0xfeed")
world = dict(buys=[lead], sells=[], res=[])


def fake_get(url, params=None):
    p = params or {}
    if url.endswith("/v2/trades"):
        return dict(data=world["sells"] if p.get("side") == "SELL" else [x for x in world["buys"] if x["timestamp"] >= p["start"]])
    if url.endswith("/v2/resolutions"):
        return dict(data=world["res"])
    if url.endswith("/markets") and "condition_ids" in p:
        return [m for m in [copied] + others if m["conditionId"] in p["condition_ids"]]
    if url.endswith("/markets"):
        return others if p.get("offset") == 0 else []
    raise AssertionError(url)


P.get, P.post = fake_get, lambda url, body: [BK[x["token_id"]] for x in body if x["token_id"] in BK]
P.cmd_run()                                     # first run: cursor starts now, nothing copied
c = json.load(open(P.COPY)); assert not c["pos"] and c["cursor"][W] >= int(now)
c["cursor"][W] = int(now) - 600; json.dump(c, open(P.COPY, "w"))
P.cmd_run()
c, tw = json.load(open(P.COPY)), json.load(open(P.TWIN))
assert list(c["pos"]) == [tok] and len(tw["pos"]) == 1, (c["log"][-2:], tw["log"][-2:])
pair = c["pos"][tok]["pair"]
tq = list(tw["pos"].values())[0]
assert tq["pair"] == pair and tq["cond"] != mkt["conditionId"].lower() and close(tq["usd"], c["pos"][tok]["usd"])
P.cmd_run()                                     # same fill again: no second buy
assert len([x for x in json.load(open(P.COPY))["log"] if x["kind"] == "buy"]) == 1
world["sells"] = [dict(lead, side="SELL", timestamp=int(now) - 30)]
P.cmd_run()
c, tw = json.load(open(P.COPY)), json.load(open(P.TWIN))
assert not c["pos"] and not tw["pos"] and c["log"][-1]["kind"] == "sell" and tw["log"][-1]["why"] == "คู่ copy ขาย"
assert close(P.value(c), c["cash"]) and c["cash"] < c["start_usd"]
world.update(sells=[], buys=[])
# twin-only position left open, then resolved
tw["pos"][tok] = dict(qty=2.0, entry=0.4, last=0.4, usd=0.8, t="x", why="x", coin="x", cond=rm["conditionId"].lower(), oi=1, fee=[0.0, 1.0], pair="p")
tw["cash"] -= 0.8; json.dump(tw, open(P.TWIN, "w"))
world["res"] = [res]
P.get = lambda url, params=None: [rm] if url.endswith("/markets") else fake_get(url, params)
P.cmd_run()
tw = json.load(open(P.TWIN)); assert not tw["pos"] and tw["log"][-1]["pnl"] == round(2.0 - 0.8, 5)
# a failed fetch is no action
c = json.load(open(P.COPY))
c["pos"][tok] = dict(qty=2.0, entry=0.4, last=0.4, usd=0.8, t="x", why="x", coin="x", cond=mkt["conditionId"].lower(), oi=0,
                     fee=[0.05, 1.0], pair="p", wallet=W, leader_ts=int(now) - 60)
c["cash"] -= 0.8; json.dump(c, open(P.COPY, "w"))
before = json.load(open(P.COPY))
P.get = P.post = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
P.cmd_run()
after = json.load(open(P.COPY))
assert after["pos"] == before["pos"] and after["cash"] == before["cash"] and after["log"] == before["log"], "no fetch, no change"
print("full run ok: copy + twin bought together, sold together on the leader's sell, resolution settled, failed fetch did nothing")

if sys.argv[1:] == ["live"]:
    import importlib
    L = importlib.reload(P)
    L.COPY, L.TWIN = str(tmp / "live_copy.json"), str(tmp / "live_twin.json")
    L.cmd_run()                                 # first run sets cursors
    c = json.load(open(L.COPY))
    for w in c["cursor"]:
        c["cursor"][w] -= 15 * 60               # look back 15 minutes so the smoke run sees real fills
    json.dump(c, open(L.COPY, "w"))
    L.cmd_run()
    c, tw = json.load(open(L.COPY)), json.load(open(L.TWIN))
    print(f"live: {len(c['cursor'])} wallets polled, copy buys {sum(x['kind'] == 'buy' for x in c['log'])}, "
          f"skips {sum(x['kind'] == 'skip' for x in c['log'])}, twin buys {sum(x['kind'] == 'buy' for x in tw['log'])}")
    for x in c["log"][-8:]:
        print("  ", x["kind"], x.get("coin", "")[:50], x.get("px", ""), x.get("why", "")[:60])
print("ok")
