"""DR opening-auction mispricing, intraday check. Yahoo 1h bars (730 d) and 5m bars (60 d) for the DR, 1h bars with
pre/post-market for the US underlying, 1h USD/THB. fair = last US price before 10:00 Bangkok (post-market included) x FX.
dev = DR opening price / fair, divided by its trailing 20-session median, minus 1.
Rule: dev <= -x -> buy at the opening price (limit order in the pre-open auction), sell at the close of the first hour / the
day's close. Checks: entry one bar later (11:00 on 1h data, 10:05 on 5m data), traded value in the opening bar. Cost 0.17%/side."""
import os, json, time, numpy as np, r2lib as L
def yi(sym, interval, rng, prepost=False):
    fn = f"{L.R2}/yi_{sym.replace('=','_')}_{interval}_{rng}_{int(prepost)}.json"
    if os.path.exists(fn): j = json.load(open(fn))
    else:
        try: j = json.loads(L.raw(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={interval}&includePrePost={'true' if prepost else 'false'}", tries=3))
        except Exception as e: j = {"chart": {"result": None}}
        json.dump(j, open(fn, "w")); time.sleep(0.4)
    r = (j.get("chart") or {}).get("result")
    if not r or "timestamp" not in r[0]: return None
    q = r[0]["indicators"]["quote"][0]; f = lambda k: np.array([np.nan if x is None else x for x in q[k]], float)
    a = np.column_stack([np.array(r[0]["timestamp"], float), f("open"), f("high"), f("low"), f("close"), f("volume")])
    return a[np.isfinite(a[:, 4]) & np.isfinite(a[:, 1])]
PAIRS = {"AAPL80": "AAPL", "NVDA80": "NVDA", "TSLA80": "TSLA", "MSFT80": "MSFT", "GOOG80": "GOOG", "AMZN80": "AMZN", "META80": "META", "NFLX80": "NFLX",
         "AMD80": "AMD", "AVGO80": "AVGO", "NVDA01": "NVDA", "AAPL01": "AAPL", "TSLA01": "TSLA", "MSFT01": "MSFT", "AMZN01": "AMZN", "META01": "META", "NVDA19": "NVDA"}
C = 0.0017
def study(itv, rng):
    fx = yi("THB=X", "1h", "730d"); rows = []
    for dr, und in PAIRS.items():
        d = yi(dr + ".BK", itv, rng); u = yi(und, "1h", "730d", True)
        if d is None or u is None or len(d) < 50: continue
        day = ((d[:, 0] + 7 * 3600) // 86400).astype(np.int64); first = np.nonzero(np.concatenate([[True], np.diff(day) > 0]))[0]
        last = np.concatenate([first[1:] - 1, [len(d) - 1]]); prem = []; recs = []
        for a, z in zip(first, last):
            t0 = d[a, 0]
            if (t0 + 7 * 3600) % 86400 > 10.2 * 3600: prem.append(np.nan); recs.append(None); continue     # no bar at the 10:00 open
            ju = int(np.searchsorted(u[:, 0], t0)) - 1; jf = int(np.searchsorted(fx[:, 0], t0)) - 1
            if ju < 0 or jf < 0 or t0 - u[ju, 0] > 4 * 86400: prem.append(np.nan); recs.append(None); continue
            prem.append(d[a, 1] / (u[ju, 4] * fx[jf, 4])); recs.append((a, z))
        prem = np.array(prem)
        for k in range(20, len(prem)):
            if recs[k] is None or not np.isfinite(prem[k]): continue
            m = np.nanmedian(prem[k - 20:k])
            if not np.isfinite(m): continue
            a, z = recs[k]; o = d[a, 1]
            nxt = d[a + 1, 1] if a + 1 <= z else np.nan
            rows.append(dict(t=int(d[a, 0]) * 1000, dev=prem[k] / m - 1, r_bar=d[a, 4] / o - 1 - 2 * C, r_day=d[z, 4] / o - 1 - 2 * C,
                             r_day_late=(d[z, 4] / nxt - 1 - 2 * C) if np.isfinite(nxt) else np.nan, gap_late=(nxt / o - 1) if np.isfinite(nxt) else np.nan,
                             val=d[a, 5] * o, dr=dr, low_first=(d[a, 3] >= o * 0.9999)))
    print(f"\n=== {itv} bars, {rng}: {len(rows)} DR-days, {len(set(r['dr'] for r in rows))} DRs, {L.ts(min(r['t'] for r in rows))[:10]}..{L.ts(max(r['t'] for r in rows))[:10]} ===")
    dev = np.array([r["dev"] for r in rows]); print(f"dev sd {dev.std()*100:.2f}%  share dev<=-1% {np.mean(dev<=-0.01)*100:.1f}%  <=-2% {np.mean(dev<=-0.02)*100:.1f}%  | every day: open->close {np.mean([r['r_day'] for r in rows])*100:+.2f}% (after costs)")
    for x in (0.005, 0.01, 0.015, 0.02, 0.03):
        sel = [r for r in rows if r["dev"] <= -x]
        if len(sel) < 15: continue
        for lab, key in (("open -> end of first bar", "r_bar"), ("open -> day close", "r_day"), ("NEXT bar open -> day close", "r_day_late")):
            tr = [(r["t"], r[key]) for r in sel if np.isfinite(r[key])]
            print(L.fmt(f"dev<=-{x*100:.1f}% {lab}", L.stats(tr))[:250])
        v = np.array([r["val"] for r in sel]); g = np.array([r["gap_late"] for r in sel if np.isfinite(r["gap_late"])])
        print(f"      traded value in the opening bar, THB: median {np.median(v):,.0f}  p25 {np.percentile(v,25):,.0f}  share with zero volume {np.mean(v<=0)*100:.0f}% | move from the open to the next bar's open {g.mean()*100:+.2f}% | open was the bar's low {np.mean([r['low_first'] for r in sel])*100:.0f}%")
    return rows
r1 = study("1h", "730d")
r5 = study("5m", "60d")
# per-DR split on the hourly sample for the 1% rule
by = {}
for r in r1:
    if r["dev"] <= -0.01: by.setdefault(r["dr"], []).append(r["r_day"])
print("\nper DR, dev<=-1% open->close (1h sample): " + " ".join(f"{k}:n{len(v)} {np.mean(v)*100:+.2f}" for k, v in sorted(by.items())))
