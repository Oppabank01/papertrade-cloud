"""fwd_vwapbuf.py walking 15m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as the scout's backtest (/tmp/scout_1949.py vwap_trades() with TWAP, copied below)."""
import random, sys
import statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_vwapbuf as F, byttrade as B

D = F.DAY


def trades(b, k=F.K):   # the backtest, TWAP
    dclose = {}
    for x in b:
        dclose[x["t"] // D] = x["c"]
    days = sorted(dclose)
    dret = {}
    for i in range(15, len(days)):
        rs = [dclose[days[j]] / dclose[days[j - 1]] - 1 for j in range(i - 14, i)]
        dret[days[i]] = k * st.pstdev(rs)
    out, pos, cur, pv, vv = [], None, None, 0.0, 0.0
    for i in range(1, len(b) - 1):
        x, nx = b[i], b[i + 1]
        day = x["t"] // D
        if day != cur:
            cur, pv, vv = day, 0.0, 0.0
        pv += (x["h"] + x["l"] + x["c"]) / 3
        vv += 1
        nday = nx["t"] // D
        if pos and nday != day:
            out.append((pos[2], pos[1], nx["o"]))
            pos = None
            continue
        if nday != day or day not in dret or x["t"] % D < F.M15:
            continue
        ref, buf = pv / vv, dret[day]
        sig = 1 if x["c"] > ref * (1 + buf) else -1 if x["c"] < ref * (1 - buf) else 0
        if sig and (not pos or pos[0] != sig):
            if pos:
                out.append((pos[2], pos[1], nx["o"]))
            pos = (sig, nx["o"], nx["t"])
    return out


full = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "15m", max_age_h=240)[-96 * 60:]]
full = full[next(i for i, x in enumerate(full) if x["t"] % D == 0):]          # start on a day boundary
daily = []
for x in full:
    if not daily or daily[-1]["t"] != x["t"] // D * D:
        daily.append(dict(t=x["t"] // D * D, c=x["c"], closed=True))
    daily[-1]["c"] = x["c"]
start = next(i for i in range(96 * 25, len(full)) if full[i + 1]["t"] % D == 0)  # the last bar of a day: backtest is flat
want = [(round(e, 6), round(x, 6)) for t, e, x in trades(full) if t > full[start]["t"]]
s = B.new_state("t"); s["seen"] = {"BTCUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, "BTCUSDT", w[:-1] + [dict(w[-1], closed=False)], daily, "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 20
sides = {x["side"] for x in s["log"] if x["kind"] == "buy"}
t = B.new_state("t"); t["seen"] = {"BTCUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "BTCUSDT", w[:-1] + [dict(w[-1], closed=False)], daily, "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest ({sorted(sides)}); ok")
