"""byttrade.py walking bars one at a time must give the same trades as the scout's backtest on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import byttrade as B


def backtest(b, cost, sides):   # the scout's trades() (scout_st4h.py, 22 Nov), entries only after index `start`
    atr, d, reg = B.wilder_atr(b, 14), B.supertrend_dir(b), B.daily_regime(b)
    out, i, n = [], START, len(b)
    while i < n - 1:
        s = d[i]
        if not (d[i] and d[i - 1] and d[i] != d[i - 1] and atr[i] and s in sides and reg[i] == s):
            i += 1; continue
        e, a = b[i + 1]["o"], atr[i]
        stop, take, best, j, x = e - s * 2 * a, e + s * 10 * a, e, i + 1, None
        while j < n:
            o, h, l = b[j]["o"], b[j]["h"], b[j]["l"]
            if s == 1:
                if l <= stop: x = min(o, stop) if j > i + 1 else stop; break
                if h >= take: x = max(o, take) if j > i + 1 else take; break
                best = max(best, h); stop = max(stop, best - 5 * a)
            else:
                if h >= stop: x = max(o, stop) if j > i + 1 else stop; break
                if l <= take: x = min(o, take) if j > i + 1 else take; break
                best = min(best, l); stop = min(stop, best + 5 * a)
            j += 1
        if x is None:
            break
        out.append(round(s * (x / e - 1), 5))
        i = j + 1
    return out


bars = [dict(x, closed=True) for x in mts.bars("binance", "SOLUSDT", "4h")[-1400:]]
START = 400
for sides in ((1, -1), (1,)):
    want = backtest(bars, B.COST, sides)
    s = B.new_state("t"); s["seen"] = bars[START - 1]["t"]
    for k in range(START + 1, len(bars) + 1):          # bars[k-1] is the forming bar at each tick
        view = bars[:k - 1] + [dict(bars[k - 1], closed=False)]
        B.process(s, view, sides, "flip", random.Random(1))
    got = [x["ret"] for x in s["log"] if x["kind"] == "sell"]
    assert got == want, (sides, got, want)
    assert all(x["side"] == "long" for x in s["log"]) or sides != (1,)
    print(f"sides {sides}: {len(got)} trades match the backtest, value {s['cash'] / s['start_usd'] - 1 + (0 if not s['pos'] else 0):+.1%}")

t = B.new_state("t"); B.process(t, bars[:-1] + [dict(bars[-1], closed=False)], (1, -1), "flip", random.Random(1))
assert t["seen"] == bars[-2]["t"] and not t["log"], "a new account must not trade on a stale signal"
tw = B.new_state("t"); tw["seen"] = bars[START - 1]["t"]
for k in range(START + 1, len(bars) + 1, 1):
    B.process(tw, bars[:k - 1] + [dict(bars[k - 1], closed=False)], (1, -1), "random", random.Random(k))
assert any(x["kind"] == "sell" for x in tw["log"]), "twin should trade"
print("ok")
