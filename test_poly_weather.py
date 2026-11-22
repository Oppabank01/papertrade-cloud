"""poly_weather.py parsing and money math on saved API samples (data/poly_weather_samples.json, fetched 22 Nov 2026 18:4x UTC).
  /usr/bin/python3 test_poly_weather.py          # offline checks
  /usr/bin/python3 test_poly_weather.py live     # plus one live scan into a temp folder (real APIs, real state untouched)"""
import json, math, random, sys, tempfile, time
from datetime import datetime
from pathlib import Path
import polymarket as P
import poly_weather as W

HERE = Path(__file__).parent
S = json.load(open(HERE / "data/poly_weather_samples.json"))
EV = {e["title"]: e for e in S["events"]}
BK = {b["asset_id"]: b for b in S["books"]}
ENS, FCST = S["ensemble"], S["forecast"]
FC = {k: (FCST[k], ENS[k]) for k in FCST}
NOW = datetime.fromisoformat(S["fetched"].replace("Z", "+00:00")).timestamp()
close = lambda a, b, e=1e-9: abs(a - b) < e
tmp = Path(tempfile.mkdtemp())
W.STATIONS = tmp / "stations.json"

# --- bucket titles
pb = W.parse_bucket
assert pb("7°C", "C") == (7, 7) and pb("40-41°F", "F") == (40, 41) and pb("-6°C or below", "C") == (-math.inf, -6)
assert pb("58°F or higher", "F") == (58, math.inf) and pb("−2°C", "C") == (-2, -2) and pb("-2--1°F", "F") == (-2, -1)
assert pb("7°F", "C") is None and pb("41-40°F", "F") is None and pb("about 7°C", "C") is None and pb(None, "C") is None

# --- rules text of saved real events
nyc, _ = W.parse_event(EV["Highest temperature in NYC on November 24?"])
assert (nyc["kind"], nyc["icao"], nyc["date"], nyc["unit"]) == ("max", "KLGA", "2026-11-24", "F"), nyc
assert [b[:2] for b in nyc["buckets"]][:2] == [(-math.inf, 39), (40, 41)] and nyc["buckets"][-1][:2] == (58, math.inf) and len(nyc["buckets"]) == 11
lon, _ = W.parse_event(EV["Highest temperature in London on November 24?"])
assert (lon["kind"], lon["icao"], lon["date"], lon["unit"]) == ("max", "EGLC", "2026-11-24", "C")
mun, _ = W.parse_event(EV["Lowest temperature in Munich on November 24?"])
assert (mun["kind"], mun["icao"], mun["unit"]) == ("min", "EDDM", "C") and mun["buckets"][0][1] < 0, "negative buckets parse"
hk, why = W.parse_event(EV["Highest temperature in Hong Kong on November 24?"])
assert hk is None and why, "HKO rules have no ICAO station: skipped, not guessed"
e = EV["Highest temperature in NYC on November 24?"]
assert W.parse_event(dict(e, description=e["description"].replace("whole degrees Fahrenheit", "whole degrees Kelvin")))[0] is None
assert W.parse_event(dict(e, description=e["description"].replace("ids=KLGA", "ids=KJFK", 1)))[0] is None, "source station must match"
assert W.parse_event(dict(e, title="Highest temperature in NYC on November 25?"))[0] is None, "title date must match rules"
assert W.parse_event(dict(e, markets=e["markets"][:5] + e["markets"][6:]))[0] is None, "a missing bucket breaks the partition"
print(f"parse ok: NYC {nyc['icao']} {nyc['date']} {nyc['unit']}, London {lon['icao']}, Munich low {mun['icao']}, Hong Kong skipped ({why})")

# --- probabilities: mean at a bucket centre, F conversion, sum to 1 with the saved forecast + ensemble spread
c_b = [(-math.inf, 6, None, ""), (7, 7, None, ""), (8, math.inf, None, "")]
p = W.bucket_probs(7.0, 1.0, c_b, "C")
assert close(p[1], W.phi(0.5) - W.phi(-0.5)) and close(sum(p), 1)
f_b = [(-math.inf, 49, None, ""), (50, 51, None, ""), (52, math.inf, None, "")]
p = W.bucket_probs(10.0, 1.0, f_b, "F")                     # 10 C = 50 F; 50-51 F is [49.5, 51.5) F = [9.722, 10.833) C
assert close(p[1], W.phi((51.5 - 32) * 5 / 9 - 10) - W.phi((49.5 - 32) * 5 / 9 - 10)) and close(sum(p), 1)
for name, info in (("KLGA", nyc), ("EGLC", lon), ("EDDM", mun)):
    ms = W.members(ENS[name], info["kind"], info["date"])
    assert ms and sorted(len(x) for x in ms) == [31, 51], [len(x) for x in ms]
    mean, sigma, n = W.model(*FC[name], info["kind"], info["date"])
    i = FCST[name]["daily"]["time"].index(info["date"])
    assert mean == FCST[name]["daily"][f"temperature_2m_{info['kind']}"][i] and n == 82
    pool = [v for m in ms for v in m]
    sd = (sum((v - sum(pool) / n) ** 2 for v in pool) / n) ** 0.5
    assert close(sigma, (sd ** 2 + W.SIGMA_C ** 2) ** 0.5) and sigma >= W.SIGMA_C
    pr = W.bucket_probs(mean, sigma, info["buckets"], info["unit"])
    assert close(sum(pr), 1, 1e-9) and all(0 <= x <= 1 for x in pr), sum(pr)
assert W.members(ENS["KLGA"], "max", "2030-01-01") is None and W.model(FCST["KLGA"], ENS["KLGA"], "max", "2030-01-01") is None
assert W.model(FCST["KLGA"], {}, "max", "2026-11-24") is None, "no ensemble spread -> no model"
m_, s_, _ = W.model(*FC["KLGA"], "max", "2026-11-24")
print(f"probabilities ok: NYC 24 Nov mean {m_ * 9 / 5 + 32:.1f} F sigma {s_:.2f} C, buckets sum "
      f"{sum(W.bucket_probs(m_, s_, nyc['buckets'], 'F')):.12f}")

# --- lead: the station's local day must not have started
off = FCST["KLGA"]["utc_offset_seconds"]
assert off == -5 * 3600
start = datetime.fromisoformat("2026-11-24T05:00:00+00:00").timestamp()      # midnight in New York
assert W.lead_ok(FCST["KLGA"], "2026-11-24", start - 1) and not W.lead_ok(FCST["KLGA"], "2026-11-24", start + 1)
assert not W.lead_ok(FCST["KLGA"], "2026-11-24", start - (W.MAX_LEAD_DAYS * 86400 + 10))

# --- edge = model p - all-in cost per share; quote matches polymarket.fill_buy
usd = 500 / 33.9 * P.SIZE
ev = W.evaluate(nyc, FC["KLGA"], BK, usd, NOW)
assert isinstance(ev, dict), ev
for r in ev["rows"]:
    f = P.fill_buy(P.levels(BK[r["tok"]], "asks"), usd, P.fee_info(r["m"]))
    assert close(r["cost"], usd / f[0]) and close(r["edge"], r["p"] - usd / f[0]) and P.PX_MIN <= r["px"] <= P.PX_MAX
    assert r["cost"] > P.levels(BK[r["tok"]], "asks")[0][0], "cost per share includes fee + slip"
assert ev["best"]["edge"] == max(r["edge"] for r in ev["rows"])
print(f"edge ok: NYC best {ev['best']['title']} p {ev['best']['p']:.3f} cost {ev['best']['cost']:.3f} edge {ev['best']['edge']:+.3f} (forecast {ev['mean']:.1f} F, sigma {ev['sigma']:.2f} C)")

# --- one full scan + settle with fake APIs on the saved samples: buy + twin same size same event; no rebuy; YES win pays 1
world = dict(res=[])
stinfo = S["stationinfo"]


def fake_get(url, params=None):
    p = params or {}
    if url.endswith("/events"):
        return S["events"] if p["offset"] == 0 else []
    if url.endswith("/stationinfo"):
        return [r for r in stinfo if r["icaoId"] in p["ids"].split(",")]
    if url in (W.OM, W.OME):
        by = {f"{r['lat']:.4f}": r["icaoId"] for r in stinfo}
        out = [(ENS if url == W.OME else FCST)[by[x]] for x in p["latitude"].split(",")]
        return out if len(out) > 1 else out[0]
    if url.endswith("/v2/resolutions"):
        return dict(data=world["res"])
    if url.endswith("/markets"):
        return [m for e in S["events"] for m in e["markets"] if m["conditionId"] in p["condition_ids"]]
    raise AssertionError(url)


P.get, P.post = fake_get, lambda url, body: [BK[x["token_id"]] for x in body if x["token_id"] in BK]
s, tw = W.load(str(tmp / "m.json")), W.load(str(tmp / "t.json"))
W.EDGE_MIN = -1.0                                   # force a buy in each parsed event so the accounting runs
W.scan(s, tw, NOW, random.Random(1), tmp / "log.jsonl")
assert len(s["pos"]) == 3 and len(tw["pos"]) == 3, (len(s["pos"]), len(tw["pos"]))
for t, q in s["pos"].items():
    tq = [x for x in tw["pos"].values() if x["pair"] == q["pair"]][0]
    assert close(q["usd"], usd) and close(tq["usd"], usd) and tq["event"] == q["event"] and q["oi"] == 0 == tq["oi"]
    assert close(q["usd"], q["qty"] * q["entry"] * (1 + P.SLIP) + P.fee_of(q["qty"], q["entry"], q["fee"]), 1e-3), "spend = notional + fee + slip"
assert close(s["cash"], s["start_usd"] - 3 * usd) and set(s["done"]) == {str(e["id"]) for e in S["events"] if W.parse_event(e)[0]}
rows = [json.loads(l) for l in open(tmp / "log.jsonl")]
assert len(rows) == 3 and all("edge" in r for r in rows)
W.scan(s, tw, NOW + 60, random.Random(1), tmp / "log.jsonl")
assert len([x for x in s["log"] if x["kind"] == "buy"]) == 3, "one buy per event"
t0, q0 = next(iter(s["pos"].items()))
world["res"] = [dict(condition_id=q0["cond"], status="resolved", payouts=[1000000, 0])]
W.settle_and_mark(s)
x = s["log"][-1]
assert x["kind"] == "sell" and close(x["pnl"], round(q0["qty"] - usd, 5), 2e-5) and t0 not in s["pos"]
world["res"] = [dict(condition_id=q["cond"], status="resolved", payouts=[0, 1000000]) for q in s["pos"].values()]
W.settle_and_mark(s)
assert not s["pos"] and all(close(y["pnl"], -usd, 2e-5) for y in s["log"][-2:]), "a losing bucket costs exactly the stake"
assert close(s["cash"], s["start_usd"] - 3 * usd + q0["qty"])
before = json.dumps(tw)
P.get = P.post = lambda *a, **k: (_ for _ in ()).throw(OSError("down"))
W.settle_and_mark(tw)
assert json.dumps(tw) == before, "no fetch, no change"
print(f"full run ok: 3 events bought with twins of the same size, no rebuy, win pnl ${x['pnl']:+.4f}, losses = stake, failed fetch did nothing")

if sys.argv[1:] == ["live"]:
    import importlib
    P2 = importlib.reload(P)
    W2 = importlib.reload(W)
    W2.STATIONS = tmp / "live_stations.json"
    t0 = time.time()
    W2.cmd_run(str(tmp / "live.json"), str(tmp / "live_twin.json"), str(tmp / "live.jsonl"), force=True)
    s = json.load(open(tmp / "live.json"))
    tw = json.load(open(tmp / "live_twin.json"))
    rows = [json.loads(l) for l in open(tmp / "live.jsonl")]
    priced = [r for r in rows if "edge" in r]
    assert priced and s["last_scan"] > 0 and len(s["pos"]) == len(tw["pos"]) + sum(x["kind"] == "skip" for x in tw["log"])
    print(f"live: {len(priced)} events priced in {time.time() - t0:.1f}s, edge >= {W2.EDGE_MIN}: "
          f"{sum(r['edge'] >= W2.EDGE_MIN for r in priced)}, bought {len(s['pos'])} (twin {len(tw['pos'])}), "
          f"median edge {sorted(r['edge'] for r in priced)[len(priced) // 2]:+.3f}")
print("ok")
