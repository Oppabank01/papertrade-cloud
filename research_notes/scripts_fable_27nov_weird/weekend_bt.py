#!/usr/bin/env python3
"""Idea 7: 24/7 tokenised gold / equity perps move on the weekend while the real market is shut. Fade it or ride it into Monday?
A) PAXGUSDT on Binance spot, 1h, 2020-2026.   B) Hyperliquid HIP-3 'xyz' equity/commodity perps, 1h (API keeps only the last 5000 bars = since May 2026).
ref = Friday 21:00 UTC open (cash already shut), signal = price at Sunday 21:00 UTC open (1-2 h before futures reopen), M = signal/ref - 1.
Enter Sunday 21:00 UTC open if |M| >= thr; FADE = against M, RIDE = with M. Exit Monday 14:00 UTC (hold 17 bars) or Monday 21:00 (hold 24).
Stop 5% checked first. Cost 0.15%/side. Control: every weekend, random side, 200 seeds."""
import sys, datetime as dt, numpy as np
from wlib import *
def hl(coin):
    fn = f"{SCR}/hl_{coin.replace(':', '_')}.npy"
    if os.path.exists(fn): return np.load(fn)
    j = json.loads(raw("https://api.hyperliquid.xyz/info", json.dumps({"type": "candleSnapshot", "req": {"coin": coin, "interval": "1h", "startTime": 1750000000000, "endTime": int(time.time() * 1000)}}).encode(), tries=7))
    a = np.array([(x["t"], float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(x["v"]) * float(x["c"])) for x in j], dtype=np.float64) if j else np.zeros((0, 6))
    np.save(fn, a); time.sleep(2.5); return a
def weekends(a):
    """yield (i_fri, i_sun) bar indices"""
    idx = {int(t): i for i, t in enumerate(a[:, 0])}
    t0 = int(a[0, 0]); d = dt.datetime.utcfromtimestamp(t0 / 1000).replace(hour=21, minute=0, second=0, microsecond=0)
    while d.weekday() != 4: d += dt.timedelta(days=1)
    out = []
    while True:
        tf = int(d.replace(tzinfo=dt.timezone.utc).timestamp() * 1000); tsn = tf + 48 * H
        if tsn > a[-1, 0]: break
        if tf in idx and tsn in idx: out.append((idx[tf], idx[tsn]))
        d += dt.timedelta(days=7)
    return out
def test(name, series, thrs, holds, stop=0.05, entry_off=0):
    for thr in thrs:
        for hold in holds:
            for mode in ("FADE", "RIDE"):
                tr = []; allw = []
                for s, a in series.items():
                    for i_f, i_s in weekends(a):
                        i_e = i_s + entry_off
                        M = a[i_e, 1] / a[i_f, 1] - 1
                        allw.append((s, i_e))
                        if abs(M) < thr: continue
                        side = (-1 if M > 0 else 1) * (1 if mode == "FADE" else -1)
                        x = sim(a, i_e, side, hold, stop)
                        if x: tr.append((x[0], x[1]))
                st = stats(tr)
                if st["n"] < 8: print(f"{name} thr{thr} hold{hold} {mode} n={st['n']}"); continue
                cm = []
                for k in range(200):
                    rng = np.random.default_rng(k); rr = []
                    for q in rng.integers(0, len(allw), st["n"]):
                        s, i = allw[q]; x = sim(series[s], i, 1 if rng.random() < 0.5 else -1, hold, stop)
                        if x: rr.append(x[1])
                    cm.append(np.mean(rr) * 100)
                cm = np.array(cm)
                print(fmt(f"{name} |M|>={thr*100:.1f}% hold{hold}h {mode}", st, dict(mean=cm.mean(), med=float('nan'), p=(cm >= st['mean']).mean())), f"weekends_all={len(allw)}", flush=True)
pax = klines("PAXGUSDT", "1h", 0); print("PAXG bars", len(pax), ts(pax[0, 0]))
test("PAXG", {"PAXG": pax}, (0.003, 0.005, 0.01, 0.015), (17, 24, 72), stop=0.05)
test("PAXG sat-entry", {"PAXG": pax}, (0.005, 0.01), (41, 48), stop=0.05, entry_off=-24)
m, c = json.loads(raw("https://api.hyperliquid.xyz/info", json.dumps({"type": "metaAndAssetCtxs", "dex": "xyz"}).encode()))
rows = sorted(zip([u["name"] for u in m["universe"]], [float(x.get("dayNtlVlm") or 0) for x in c]), key=lambda x: -x[1])
top = [r[0] for r in rows[:60]]
S = {}
for coin in top:
    a = hl(coin)
    if len(a) > 24 * 60: S[coin] = a
print("HL xyz perps with >60 days of 1h bars:", len(S), "first bar", ts(min(a[0, 0] for a in S.values())))
COMM = {"xyz:GOLD", "xyz:SILVER", "xyz:CL", "xyz:BRENTOIL", "xyz:PLATINUM", "xyz:COPPER", "xyz:NATGAS", "xyz:ALUMINIUM", "xyz:PALLADIUM"}
test("HLxyz all", S, (0.005, 0.01, 0.02, 0.03), (17, 24), stop=0.05)
test("HLxyz equities", {k: v for k, v in S.items() if k not in COMM}, (0.01, 0.02), (17, 24), stop=0.05)
test("HLxyz commodities", {k: v for k, v in S.items() if k in COMM}, (0.005, 0.01), (17, 24), stop=0.05)
test("HLxyz sat-entry", S, (0.01, 0.02), (41,), stop=0.05, entry_off=-24)
