"""poly_arb.py money math on saved API samples (data/poly_arb_samples.json, data/poly_samples.json, fetched 23 Nov 2026).
  /usr/bin/python3 test_poly_arb.py          # offline checks
  /usr/bin/python3 test_poly_arb.py live     # plus one live run into a temp folder (real APIs, real state untouched)"""
import json, sys, tempfile, time
from pathlib import Path
import polymarket as P
import poly_arb as A

HERE = Path(__file__).parent
S = json.load(open(HERE / "data/poly_arb_samples.json"))
R = json.load(open(HERE / "data/poly_samples.json"))
BK = {b["asset_id"]: b for b in S["books"]}
close = lambda a, b, e=1e-9: abs(a - b) < e
n = A.PAIRS


def side_cost(asks, n, rate):
    """Hand walk: (notional, fee) for n shares."""
    left, no, fe = n, 0.0, 0.0
    for px, sz in asks:
        t = min(sz, left)
        no, fe, left = no + t * px, fe + t * rate * px * (1 - px), left - t
        if left <= 0:
            return no, fe
    return None


# --- pair cost on the two saved real markets: notional + both taker fees + 0.5% slip per side, per pair
for m in S["markets"]:
    ty, tn = json.loads(m["clobTokenIds"])
    pc = A.pair_cost(m, BK[ty], BK[tn])
    rate = float(m["feeSchedule"]["rate"])
    (ny, fy), (nn, fn) = side_cost(P.levels(BK[ty], "asks"), n, rate), side_cost(P.levels(BK[tn], "asks"), n, rate)
    want = (ny + nn + fy + fn + 0.005 * (ny + nn)) / n
    assert close(pc["per_pair"], want, 1e-12), (pc["per_pair"], want)
    assert close(pc["gap"], round(1 - want, 5), 1e-9)
    assert close(pc["raw"], round(1 - P.levels(BK[ty], "asks")[0][0] - P.levels(BK[tn], "asks")[0][0], 5))
    assert pc["per_pair"] >= 1, "real binary books: YES ask + NO ask is never below 1 (mirrored book)"
    print(f"pair cost ok: {m['question'][:45]} asks {pc['ask_yes']}+{pc['ask_no']} -> {pc['per_pair']:.5f} per pair (gap {pc['gap']:+.5f})")

# --- synthetic gap: 0.45 + 0.50 at rate 0.01 -> 0.95 + fees 0.01*(0.45*0.55 + 0.5*0.5) + slip 0.005*0.95
fm = dict(conditionId="0xabc", question="synthetic", feesEnabled=True, feeSchedule=dict(rate=0.01, exponent=1), endDate="2026-12-01T00:00:00Z")
by, bn = dict(asks=[dict(price="0.45", size="100")], bids=[dict(price="0.44", size="100")]), dict(asks=[dict(price="0.50", size="100")], bids=[dict(price="0.49", size="100")])
pc = A.pair_cost(fm, by, bn)
assert close(pc["per_pair"], 0.95 + 0.01 * (0.45 * 0.55 + 0.25) + 0.005 * 0.95, 1e-12) and close(pc["gap"], 0.04028, 1e-9)
# walking two levels: 3 at 0.45 and 2 at 0.47
by2 = dict(asks=[dict(price="0.47", size="10"), dict(price="0.45", size="3")])
pc2 = A.pair_cost(fm, by2, bn)
ny2 = 3 * 0.45 + 2 * 0.47
assert close(pc2["notional"], ny2 + 2.5, 1e-12) and close(pc2["fee_usd"], 0.01 * (3 * 0.45 * 0.55 + 2 * 0.47 * 0.53 + 5 * 0.25), 1e-12)
assert A.pair_cost(fm, dict(asks=[dict(price="0.45", size="4.9")]), bn) is None, "too thin for 5 shares"
assert A.pair_cost(fm, by, dict(asks=[])) is None
assert A.pair_cost(dict(fm, feesEnabled=False), by, bn)["fee_usd"] == 0
print(f"synthetic ok: 0.45+0.50 -> {pc['per_pair']:.6f} per pair, gap {pc['gap']:+.5f}")

# --- buy: cash falls by exactly the pair total; second buy of the same market is refused
s = A.new_state()
assert A.buy_pair(s, fm, ["y", "n"], pc, "test") is None
q = s["pos"]["0xabc"]
assert close(s["cash"], s["start_usd"] - pc["total"]) and close(q["usd"], pc["total"]) and q["qty"] == n
assert A.buy_pair(s, fm, ["y", "n"], pc, "again") == "holding"
s2 = A.new_state(); s2["cash"] = 1.0; assert A.buy_pair(s2, fm, ["y", "n"], pc, "x") == "no cash" and s2["cash"] == 1.0

# --- settlement: the pair pays exactly 1 whichever side wins, 0.5 + 0.5 on a 50-50, nothing if payouts do not sum to 1
res, rm = R["resolution"][0], R["resolved_market"][0]
assert A.pair_payout(res, rm)[0] == 1.0 and A.pair_payout(res, None)[0] == 1.0 and A.pair_payout(None, rm)[0] == 1.0
assert A.pair_payout(dict(res, payouts=[500000, 500000]), None)[0] == 1.0
assert A.pair_payout(dict(res, payouts=[1000000, 1000000]), None)[0] is None
assert A.pair_payout(None, None) == (None, None)
P.close(s, "0xabc", q["qty"] * 1.0, 1.0, "resolved", 0.0)
x = s["log"][-1]
assert close(x["pnl"], n - pc["total"], 1e-5) and close(s["cash"], s["start_usd"] - pc["total"] + n) and close(P.value(s), s["cash"])
assert close(x["pnl"] / pc["total"], pc["gap"] / pc["per_pair"], 1e-4), "return = gap / cost"
print(f"settle ok: pnl ${x['pnl']:+.4f} on ${pc['total']:.4f}")

# --- histogram buckets
assert A.bucket(-0.006) == "-0.01" and A.bucket(0.0) == "0.0" and A.bucket(0.003) == "0.0" and A.bucket(0.2) == "0.01" and A.bucket(-3) == "lt-1"

# --- one full run with fake APIs: the gap market is bought, the real one is logged only; resolution settles; no fetch -> no change
tmp = Path(tempfile.mkdtemp())
st, lg = str(tmp / "arb.json"), str(tmp / "arb.jsonl")
real = S["markets"][0]
gapm = dict(fm, conditionId="0x" + "b" * 64, question="gap market", outcomes='["Yes", "No"]', clobTokenIds='["ty", "tn"]',
            enableOrderBook=True, acceptingOrders=True, closed=False)
world = dict(res=[])
books_ = dict(BK, ty=dict(by, asset_id="ty"), tn=dict(bn, asset_id="tn"))


def fake_get(url, params=None):
    p = params or {}
    if url.endswith("/markets") and "condition_ids" in p:
        return [m for m in (real, gapm) if m["conditionId"] in p["condition_ids"]]
    if url.endswith("/markets"):
        return [real, gapm, dict(gapm, conditionId="0xthree", outcomes='["A", "B", "C"]')] if p["offset"] == 0 else []
    if url.endswith("/v2/resolutions"):
        return dict(data=world["res"])
    raise AssertionError(url)


P.get, P.post = fake_get, lambda url, body: [books_[x["token_id"]] for x in body if x["token_id"] in books_]
A.cmd_run(st, lg)
s = json.load(open(st))
assert list(s["pos"]) == [gapm["conditionId"].lower()] and s["stats"]["seen"] == 2, s["stats"]
rows = [json.loads(l) for l in open(lg)]
assert len(rows) == 2 and sum(r["b"] for r in rows) == 1 and s["scan_off"] == 0
A.cmd_run(st, lg)                                      # same gap again: no second buy
s = json.load(open(st))
assert sum(x["kind"] == "buy" for x in s["log"]) == 1 and s["stats"]["seen"] == 4
q = s["pos"][gapm["conditionId"].lower()]
assert close(q["last"], 0.44 + 0.49), "marked at the two best bids"
world["res"] = [dict(res, condition_id=gapm["conditionId"], payouts=[0, 1000000])]
A.cmd_run(st, lg)
s = json.load(open(st))
assert not s["pos"] and close(s["cash"], s["start_usd"] - q["usd"] + n, 1e-9) and s["log"][-1]["kind"] == "sell"
before = open(st).read()
P.get = P.post = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
A.cmd_run(st, lg)
after = json.load(open(st))
assert after["pos"] == json.loads(before)["pos"] and after["cash"] == json.loads(before)["cash"] and after["log"] == json.loads(before)["log"]
A.LOG_KEEP = 3
A.trim_log(Path(lg), 3)
assert len(open(lg).read().splitlines()) == 3
print("full run ok: gap bought once, real market logged only, settled at 1 per pair, failed fetch did nothing, log trimmed")

if sys.argv[1:] == ["live"]:
    import importlib
    P2 = importlib.reload(P)
    A2 = importlib.reload(A)
    t0 = time.time()
    A2.cmd_run(str(tmp / "live.json"), str(tmp / "live.jsonl"))
    took = time.time() - t0
    s = json.load(open(tmp / "live.json"))
    rows = [json.loads(l) for l in open(tmp / "live.jsonl")]
    assert rows and s["stats"]["seen"] == len(rows)
    print(f"live: {len(rows)} markets priced in {took:.1f}s, best raw {max(r['raw'] for r in rows):+.4f}, "
          f"best after costs {max(r['gap'] for r in rows):+.4f}, bought {sum(r['b'] for r in rows)}")
print("ok")
