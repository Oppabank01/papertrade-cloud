#!/usr/bin/env python3
"""Daily odd signals on BTC/ETH (Binance spot daily bars). Entry at the open of day D+lag after signal day D (lag 2 = data surely published).
A) Bitcoin fee spikes and mempool size (api.blockchain.info charts, keyless)   B) hash-rate drops (miner capitulation)
C) geomagnetic storms (GFZ Potsdam Kp index, keyless)                           D) Fear & Greed level and CHANGE SPEED (alternative.me)
Hold 1/3/7/14 days, stop 15% checked first, cost 0.15%/side, cooldown = hold. Control: random days on the same coin, 300 seeds."""
import sys, calendar, numpy as np
from wlib import *
BT = klines("BTCUSDT", "1d", 0); ET = klines("ETHUSDT", "1d", 0)
IDX = {"BTC": {int(t): i for i, t in enumerate(BT[:, 0])}, "ETH": {int(t): i for i, t in enumerate(ET[:, 0])}}
BARS = {"BTC": BT, "ETH": ET}
NT = [0]
def test(name, days, coins=("BTC",), holds=(1, 3, 7, 14), lag=2, sides=(1, -1), stop=0.15):
    """days: list of signal-day timestamps (ms, 00:00 UTC)"""
    for coin in coins:
        a = BARS[coin]; ix = IDX[coin]
        for hold in holds:
            for side in sides:
                NT[0] += 1; tr = []; last = -1
                for d in sorted(days):
                    i = ix.get(int(d) + lag * D)
                    if i is None or i <= last: continue
                    x = sim(a, i, side, hold, stop)
                    if x: tr.append((x[0], x[1])); last = x[2]
                st = stats(tr)
                if st["n"] < 8: print(f"{name} {coin} hold{hold} side{side} n={st['n']}"); continue
                lo = ix.get(int(min(days)) + lag * D, 30)
                c = rand_ctl(a, st["n"], side, hold, stop, seeds=300, lo=max(30, lo), mean_obs=st["mean"])
                print(fmt(f"{name} {coin} hold{hold}d {'LONG' if side > 0 else 'SHORT'}", st, c), flush=True)
def zdays(series, win, Z, sign=1, use_log=True):
    """series: dict day_ms -> value. z of today's value vs prior `win` days"""
    out = []; ds = sorted(series)
    v = {d: (math.log(max(1e-9, series[d])) if use_log else series[d]) for d in ds}
    for d in ds:
        p = [v[d - k * D] for k in range(1, win + 1) if d - k * D in v]
        if len(p) < win * 0.8: continue
        z = (v[d] - np.mean(p)) / (np.std(p) + 1e-9)
        if sign * z >= Z: out.append(d)
    return out
def bc(chart):
    j = get(f"https://api.blockchain.info/charts/{chart}?timespan=all&format=json&sampled=false")
    s = {}
    for p in j["values"]:
        d = int(p["x"]) // 86400 * 86400 * 1000
        s[d] = max(s.get(d, 0), p["y"])
    return {d: y for d, y in s.items() if d >= 1483228800000 and y > 0}
print("=== A) bitcoin fees / mempool ===")
fee = bc("transaction-fees-usd"); print("fee days", len(fee))
for Z in (2, 3): test(f"fee_usd z>={Z} (30d)", zdays(fee, 30, Z), holds=(1, 3, 7))
test("fee_usd z<=-2 (30d, quiet chain)", zdays(fee, 30, 2, sign=-1), holds=(3, 7))
try:
    mp = bc("mempool-size"); print("mempool days", len(mp))
    for Z in (2, 3): test(f"mempool_size z>={Z} (30d)", zdays(mp, 30, Z), holds=(1, 3, 7))
except Exception as e: print("mempool-size failed", e)
print("=== B) hash-rate drop ===")
hr = bc("hash-rate"); ds = sorted(hr); cap = []
for d in ds:
    a7 = [hr[d - k * D] for k in range(7) if d - k * D in hr]; a30 = [hr[d - k * D] for k in range(30) if d - k * D in hr]
    if len(a7) >= 6 and len(a30) >= 25 and np.mean(a7) / np.mean(a30) < 0.92: cap.append(d)
print("hash-rate 7d/30d < 0.92 days", len(cap)); test("hashrate 7d/30d<0.92", cap, holds=(7, 14, 30))
print("=== C) geomagnetic storms (Kp) ===")
txt = raw("https://kp.gfz.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt").decode()
kp = {}
for ln in txt.splitlines():
    if ln.startswith("#") or not ln.strip(): continue
    p = ln.split()
    y, m, dd = int(p[0]), int(p[1]), int(p[2])
    if y < 2017: continue
    kp[calendar.timegm((y, m, dd, 0, 0, 0)) * 1000] = max(float(x) for x in p[7:15])
print("kp days", len(kp), "storm days Kp>=6:", sum(1 for v in kp.values() if v >= 6), "Kp>=7:", sum(1 for v in kp.values() if v >= 7))
for K in (6, 7): test(f"geomagnetic Kp>={K}", [d for d, v in kp.items() if v >= K], holds=(1, 3, 7), lag=1)
print("=== D) Fear & Greed level and speed ===")
fg = {int(x["timestamp"]) * 1000: int(x["value"]) for x in get("https://api.alternative.me/fng/?limit=0")["data"]}
print("fng days", len(fg))
def speed(n, chg):
    return [d for d in fg if d - n * D in fg and (fg[d] - fg[d - n * D] <= chg if chg < 0 else fg[d] - fg[d - n * D] >= chg)]
for coin in ("BTC", "ETH"):
    test("F&G <=10", [d for d, v in fg.items() if v <= 10], coins=(coin,), holds=(3, 7, 14), lag=1)
    test("F&G >=90", [d for d, v in fg.items() if v >= 90], coins=(coin,), holds=(3, 7, 14), lag=1)
    test("F&G drop >=20 in 3d", speed(3, -20), coins=(coin,), holds=(3, 7, 14), lag=1)
    test("F&G drop >=15 in 1d", speed(1, -15), coins=(coin,), holds=(3, 7, 14), lag=1)
    test("F&G rise >=20 in 3d", speed(3, 20), coins=(coin,), holds=(3, 7, 14), lag=1)
    test("F&G rise >=15 in 1d", speed(1, 15), coins=(coin,), holds=(3, 7, 14), lag=1)
print("settings tried:", NT[0])
