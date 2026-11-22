"""poly_fav.py money math, filters and settlement on saved API samples (data/poly_fav_samples.json fetched 22 Nov 2026 19:1x UTC,
data/poly_samples.json for a resolved market).
  /usr/bin/python3 test_poly_fav.py          # offline checks
  /usr/bin/python3 test_poly_fav.py live     # plus one live run into a temp folder (real APIs, real state files untouched)"""
import json, os, random, sys, tempfile, time
from pathlib import Path
import polymarket as P
import poly_fav as F

HERE = Path(__file__).parent
S = json.load(open(HERE / "data/poly_fav_samples.json"))
R = json.load(open(HERE / "data/poly_samples.json"))
MK = {m["conditionId"]: m for m in S["markets"]}
BK = {b["asset_id"]: b for b in S["books"]}
close = lambda a, b, e=1e-9: abs(a - b) < e
USD = P.new_state("x")["start_usd"] * P.SIZE
REAL = [HERE / f"state_poly_{n}.json" for n in ("fav", "long", "fav_twin")]
REAL_BEFORE = [(p.exists(), p.stat().st_mtime if p.exists() else None) for p in REAL]


def hand_buy(asks, usd, rate):
    """Spend usd walking the asks; each share costs px x (1 + 0.5% slip) + rate x px x (1 - px). -> (shares, notional, fee)."""
    left, sh, no, fe = usd, 0.0, 0.0, 0.0
    for px, sz in asks:
        unit = px * 1.005 + rate * px * (1 - px)
        t = min(sz, left / unit)
        sh, no, fe, left = sh + t, no + t * px, fe + t * rate * px * (1 - px), left - t * unit
        if left <= 1e-12:
            return sh, no, fe
    return None


# --- the fee formula and the book walk on the saved real fav and long books
assert close(P.fee_of(10, 0.9, (0.05, 1.0)), 10 * 0.05 * 0.9 * 0.1) and close(P.fee_of(10, 0.05, (0.01, 1.0)), 10 * 0.01 * 0.05 * 0.95)
for key, lo, hi in (("fav_ok", F.FAV_LO, F.FAV_HI), ("long_ok", F.LONG_LO, F.LONG_HI)):
    m = MK[S["picks"][key]]
    rate = float(m["feeSchedule"]["rate"])
    tok, q = next((t, F.quote(BK.get(t), m, USD, lo, hi)) for t in json.loads(m["clobTokenIds"]) if isinstance(F.quote(BK.get(t), m, USD, lo, hi), dict))
    sh, no, fe = hand_buy(P.levels(BK[tok], "asks"), USD, rate)
    assert close(q["px"], no / sh, 1e-12) and close(q["cost"], USD / sh, 1e-12) and lo <= q["ask"] <= q["px"] <= hi
    assert close(no + fe + 0.005 * no, USD, 1e-9), "notional + fee + slip = the order size"
    print(f"quote ok: {key} {m['question'][:40]} ask {q['ask']} avg {q['px']:.4f} cost/share {q['cost']:.4f} ({(q['cost'] / q['px'] - 1):+.2%} over price)")
for key, lo, hi in (("fav_thin", F.FAV_LO, F.FAV_HI), ("long_thin", F.LONG_LO, F.LONG_HI)):
    m = MK[S["picks"][key]]
    qs = [F.quote(BK.get(t), m, USD, lo, hi) for t in json.loads(m["clobTokenIds"])]
    assert any(isinstance(x, str) for x in qs) and not any(isinstance(x, dict) for x in qs), qs
    print(f"thin ok: {key} -> {[x for x in qs if x]}")

# --- quote filters on synthetic books
fm = dict(conditionId="0x" + "f" * 64, question="synthetic", feesEnabled=True, feeSchedule=dict(rate=0.05, exponent=1))
bk = lambda asks, bids: dict(asks=[dict(price=str(p), size=str(s)) for p, s in asks], bids=[dict(price=str(p), size=str(s)) for p, s in bids])
assert F.quote(bk([(0.80, 100)], [(0.79, 100)]), fm, USD, 0.85, 0.97) is None, "best ask outside the range: not a candidate"
assert F.quote(bk([(0.90, 100)], []), fm, USD, 0.85, 0.97) == "thin: no bid"
assert F.quote(bk([(0.90, 100)], [(0.86, 100)]), fm, USD, 0.85, 0.97).startswith("thin: spread")
assert F.quote(bk([(0.90, 3), (0.95, 100)], [(0.89, 100)]), fm, USD, 0.85, 0.97) == "thin: depth", "only $2.7 within 2 cents"
assert F.quote(bk([(0.10, 1), (0.13, 100)], [(0.09, 100)]), fm, 2.0, 0.03, 0.10) == "thin: depth"
assert F.quote(bk([(0.10, 10), (0.11, 100)], [(0.09, 100)]), fm, 2.0, 0.03, 0.10).startswith("avg fill"), "walk leaves the range"
q = F.quote(bk([(0.90, 100)], [(0.89, 100)]), fm, USD, 0.85, 0.97)
unit = 0.9 * 1.005 + 0.05 * 0.9 * 0.1
assert close(q["px"], 0.9) and close(q["cost"], unit, 1e-12) and q["bid"] == 0.89

# --- buy then settle: a winner pays shares x 1, a loser 0, no fee at resolution
s = F.load(str(Path(tempfile.mkdtemp()) / "x.json"))
assert s["done"] == {} and s["ev_done"] == {} and close(s["start_usd"], 500 / 33.9)
fb = bk([(0.90, 100)], [(0.89, 100)])
assert P.buy(s, "tY", dict(fm, outcomes='["Yes", "No"]'), 0, fb, "test") is None
p = s["pos"]["tY"]
assert close(p["qty"], USD / unit, 1e-12) and close(s["cash"], s["start_usd"] - USD) and close(p["entry"], 0.9) and p["last"] == 0.89
assert close(s["log"][-1]["fee_usd"], p["qty"] * 0.05 * 0.09, 1e-5)
P.settle(s, "tY", 1.0, "won")
x = s["log"][-1]
assert close(s["cash"], s["start_usd"] - USD + USD / unit) and close(x["pnl"], USD / unit - USD, 1e-5)
assert close(x["pnl"] / USD, 1 / unit - 1, 1e-5), "a 0.90 favourite that wins returns 1/0.9090 - 1 = +10.0% after costs"
P.buy(s, "tN", dict(fm, outcomes='["Yes", "No"]'), 1, fb, "test")
P.settle(s, "tN", 0.0, "lost")
assert close(s["log"][-1]["pnl"], -USD, 1e-5) and close(P.value(s), s["cash"])
print(f"money ok: $0.7375 at 0.90 (rate 0.05) buys {USD / unit:.5f} shares, win {1 / unit - 1:+.2%}, loss -100%")
# break-even win rate for a 0.90 favourite after fee and slip = cost per share
print(f"  break-even win rate at ask 0.90: {unit:.4f}; at ask 0.05 (rate 0.05): {0.05 * 1.005 + 0.05 * 0.05 * 0.95:.4f}")

# --- resolution and market-state filters
ro = {r["status"] for r in S["open_resolutions"]}
assert ro == {"posed"} and all(F.res_ok(r) is None for r in S["open_resolutions"]), "open markets are 'posed'"
assert F.res_ok(None) is None and F.res_ok(dict(status="proposed")) == "resolution proposed"
assert F.res_ok(dict(status="posed", was_disputed=True)) == "disputed" and F.res_ok(R["resolution"][0]) == "resolution resolved"
now = time.time()
om = dict(fm, outcomes='["Yes", "No"]', clobTokenIds='["a", "b"]', enableOrderBook=True, acceptingOrders=True, closed=False,
          endDate=F.iso(now + 3 * 3600), umaResolutionStatus=None)
assert F.tradable(om, now) is None
assert F.tradable(dict(om, endDate=F.iso(now - 60)), now) == "end passed" and F.tradable(dict(om, endDate=F.iso(now + 120)), now) == "end passed"
assert F.tradable(dict(om, endDate=F.iso(now + 49 * 3600)), now) == "ends beyond 48 h"
assert F.tradable(dict(om, umaResolutionStatus="proposed"), now) == "uma proposed"
assert F.tradable(dict(om, gameStartTime=F.iso(now - 600).replace("T", " ").replace("Z", "+00")), now) == "game started"
assert F.tradable(dict(om, gameStartTime=F.iso(now + 3600).replace("T", " ").replace("Z", "+00")), now) is None
assert F.tradable(dict(om, acceptingOrders=False), now) == "not accepting orders"
assert F.tradable(dict(om, clobTokenIds='["a", "b", "c"]'), now) == "not a 2-outcome book"
assert F.event_of(dict(om, events=[dict(id=7)])) == "7" and F.event_of(om) == om["conditionId"].lower()
print("filters ok: posed buys, proposed/disputed/resolved skip; end passed, > 48 h, uma proposed, closed books skip")

# --- history helpers on the saved prices-history sample
H = S["history"]
h, end = H["history"], P.ts_of(H["market"]["endDate"])
assert close(F.utc_ts("2026-11-16 01:01:54.232351+00"), P.ts_of("2026-11-16T01:01:54Z")) and F.utc_ts(None) is None
assert F.price_at(h, end - 3600) == float(max((x for x in h if x["t"] <= end - 3600), key=lambda x: x["t"])["p"])
assert F.price_at(h, h[0]["t"] - 10) is None, "no point within tol before the first one"
assert F.price_at([dict(t=100, p=0.3), dict(t=200, p=0.4)], 250, 100) == 0.4 and F.price_at([dict(t=100, p=0.3)], 250, 100) is None
rows = [dict(ev=str(i), y=1.0 if i < 9 else 0.0, rate=0.05, p={"6": 0.9}) for i in range(10)]
t = {(b[0], b[1]): b for b in F.table(rows, 6, [0.0, 0.5, 1.0001])}
lo_b, hi_b = t[(0.0, 0.5)], t[(0.5, 1.0)]
assert hi_b[2] == 10 and close(hi_b[4], 0.9) and close(hi_b[5], 0.9) and close(hi_b[6], 0.0), "price 0.9, won 9 of 10: calibrated"
assert lo_b[2] == 10 and close(lo_b[4], 0.1) and close(lo_b[5], 0.1), "token 1 side mirrors at 0.1"
assert close(hi_b[7], 0.9 / (0.9 * 1.005 + 0.05 * 0.09) - 1), "return per $ after fee and slip"
rows2 = [dict(ev="e", y=1.0, rate=0.0, p={"6": 0.9})] * 4
b = F.table(rows2, 6, [0.85, 0.97])[0]
assert b[2] == 4 and b[3] == 1 and close(b[5], 1.0) and close(b[6], 0.1 * 4 / (4 * 0.09) ** 0.5), "z = (won - price) n / sqrt(sum p(1-p))"
b = F.table([dict(ev="e1", y=1.0, rate=0.0, p={"6": 0.9}), dict(ev="e2", y=0.0, rate=0.0, p={"6": 0.9})], 6, [0.85, 0.97])[0]
assert close(b[8], -0.4 / ((0.5 ** 2 + 0.5 ** 2) / 4) ** 0.5), "event-clustered z"
print("calib helpers ok: price_at, utc_ts, both-sides table, z, clustered z and return per $")

# --- one full run with fake APIs
tmp = Path(tempfile.mkdtemp())
paths = [str(tmp / f) for f in ("fav.json", "long.json", "twin.json")]
lg = tmp / "log.jsonl"
now = time.time()


def mkt(c, ev, end_h, toks):
    return dict(om, conditionId="0x" + c * 64, question=f"market {c}", clobTokenIds=json.dumps(toks), endDate=F.iso(now + end_h * 3600),
                events=[dict(id=ev)])


W = dict(markets=[mkt("d", 4, 1, ["dy", "dn"]), mkt("a", 1, 2, ["ay", "an"]), mkt("e", 1, 2.5, ["ey", "en"]),
                  mkt("b", 2, 3, ["by", "bn"]), mkt("c", 3, 4, ["cy", "cn"]), mkt("g", 5, 60, ["gy", "gn"])],
         res={"0x" + "d" * 64: dict(condition_id="0x" + "d" * 64, status="posed", was_disputed=True)})
BKS = dict(ay=bk([(0.90, 100)], [(0.89, 100)]), an=bk([(0.11, 100)], [(0.10, 100)]),          # a: fav YES
           ey=bk([(0.92, 100)], [(0.91, 100)]), en=bk([(0.09, 100)], [(0.07, 100)]),          # e: same event as a; NO is a longshot
           by=bk([(0.05, 1000)], [(0.04, 1000)]), bn=bk([(0.96, 100)], [(0.95, 100)]),        # b: long YES, and its NO is a favourite
           cy=bk([(0.90, 100)], [(0.80, 100)]), cn=bk([(0.20, 100)], [(0.10, 100)]),          # c: thin (spread 0.10)
           dy=bk([(0.88, 100)], [(0.87, 100)]), dn=bk([(0.13, 100)], [(0.12, 100)]),          # d: disputed
           gy=bk([(0.90, 100)], [(0.89, 100)]), gn=bk([(0.11, 100)], [(0.10, 100)]))          # g: ends in 60 h
for k, v in BKS.items():
    v["asset_id"] = k


def fake_get(url, params=None):
    p = params or {}
    if url.endswith("/markets") and "condition_ids" in p:
        return [m for m in W["markets"] if m["conditionId"] in p["condition_ids"]]
    if url.endswith("/markets"):
        return list(W["markets"]) if p["offset"] == 0 else []
    if url.endswith("/v2/resolutions"):
        cs = p["condition"].split(",")
        return dict(data=[r for c, r in W["res"].items() if c in cs])
    raise AssertionError(url)


P.get, P.post = fake_get, lambda url, body: [BKS[x["token_id"]] for x in body if x["token_id"] in BKS]
F.cmd_run(*paths, str(lg), random.Random(1))
sf, sl, st = (json.load(open(f)) for f in paths)
assert sorted(sf["pos"]) == ["ay", "bn"], sf["pos"].keys()        # d disputed, e same event as a, c thin, g > 48 h
assert sorted(sl["pos"]) == ["by", "en"], sl["pos"].keys()        # e's NO at 0.09 is a longshot (event 1 is new to long)
assert set(st["done"]) == {"0x" + c * 64 for c in "abe"} and len(st["pos"]) == 3, "twin: one random side per market fav or long bought"
for s in (sf, sl, st):
    assert all(close(q["usd"], USD) for q in s["pos"].values()) and close(s["cash"], s["start_usd"] - USD * len(s["pos"]))
assert close(sf["pos"]["ay"]["qty"], USD / unit, 1e-12)
rows = [json.loads(l) for l in open(lg)]
why = {(r["side"], r["c"][:3]): r.get("why", "bought" if r.get("bought") else "?") for r in rows}
assert why[("fav", "0xd")] == "disputed" and why[("fav", "0xe")] == "already bought this market/event" and why[("fav", "0xc")].startswith("thin")
assert why[("fav", "0xa")] == why[("fav", "0xb")] == why[("long", "0xb")] == why[("long", "0xe")] == "bought" and ("fav", "0xg") not in why
print(f"run 1 ok: fav {sorted(sf['pos'])}, long {sorted(sl['pos'])}, twin {sorted(st['pos'])}, log {len(rows)} rows")
F.cmd_run(*paths, str(lg), random.Random(1))
sf2, sl2, st2 = (json.load(open(f)) for f in paths)
assert sorted(sf2["pos"]) == ["ay", "bn"] and sum(x["kind"] == "buy" for x in sf2["log"]) == 2, "no second buy of the same market/event"
assert st2["pos"] == st["pos"] and sl2["pos"] == sl["pos"]
# resolve a (YES wins) and b (NO wins): fav wins both, long loses, twin by its sides
W["res"].update({"0x" + "a" * 64: dict(condition_id="0x" + "a" * 64, status="resolved", payouts=[1000000, 0]),
                 "0x" + "b" * 64: dict(condition_id="0x" + "b" * 64, status="resolved", payouts=[0, 1000000])})
F.cmd_run(*paths, str(lg), random.Random(1))
sf3, sl3, st3 = (json.load(open(f)) for f in paths)
assert not sf3["pos"] and close(sf3["cash"], sf3["start_usd"] - 2 * USD + sf2["pos"]["ay"]["qty"] + sf2["pos"]["bn"]["qty"], 1e-9)
assert list(sl3["pos"]) == ["en"] and close(sl3["log"][[x["kind"] for x in sl3["log"]].index("sell")]["pnl"], -USD, 1e-5)
for t, q in st2["pos"].items():
    if q["cond"] in ("0x" + "a" * 64, "0x" + "b" * 64):
        win = (q["cond"].startswith("0xa") and q["oi"] == 0) or (q["cond"].startswith("0xb") and q["oi"] == 1)
        x = [y for y in st3["log"] if y["kind"] == "sell" and y["token"] == t][0]
        assert close(x["pnl"], (q["qty"] if win else 0) - USD, 1e-5)
print(f"settle ok: fav cash {sf3['cash']:.4f} (+{sf3['cash'] - sf3['start_usd']:.4f}), long lost {USD:.4f}")
before = [open(f).read() for f in paths]
P.get = P.post = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
F.cmd_run(*paths, str(lg), random.Random(1))
for f, b in zip(paths, before):
    a, b = json.load(open(f)), json.loads(b)
    assert a["pos"] == b["pos"] and a["cash"] == b["cash"] and a["log"] == b["log"], "failed fetch: no action"
F.LOG_KEEP = 3
F.trim_log(lg, 3)
assert len(lg.read_text().splitlines()) == 3
print("failed fetch did nothing, log trimmed")

if sys.argv[1:] == ["live"]:
    import importlib
    importlib.reload(P)
    import poly_arb
    importlib.reload(poly_arb)
    F2 = importlib.reload(F)
    lt = Path(tempfile.mkdtemp())
    lp = [str(lt / f) for f in ("fav.json", "long.json", "twin.json")]
    t0 = time.time()
    F2.cmd_run(*lp, str(lt / "log.jsonl"))
    took = time.time() - t0
    ss = [json.load(open(f)) for f in lp]
    rows = [json.loads(l) for l in open(lt / "log.jsonl")] if (lt / "log.jsonl").exists() else []
    assert rows, "live: no outcome in either range"
    assert all(F2.FAV_LO <= q["entry"] <= F2.FAV_HI for q in ss[0]["pos"].values())
    assert all(F2.LONG_LO <= q["entry"] <= F2.LONG_HI for q in ss[1]["pos"].values())
    assert len(ss[0]["pos"]) <= F2.MAX_NEW and len(ss[1]["pos"]) <= F2.MAX_NEW
    assert took < 30, took
    print(f"live: {len(rows)} outcomes in range, bought fav {len(ss[0]['pos'])} long {len(ss[1]['pos'])} twin {len(ss[2]['pos'])} in {took:.1f}s")
assert [(p.exists(), p.stat().st_mtime if p.exists() else None) for p in REAL] == REAL_BEFORE, "real state files touched"
print("ok")
