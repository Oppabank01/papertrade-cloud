"""fwd_ladder.py walking 4h bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same ladders (first fill, number of fills, exit) as the scout's backtest on the full history (/tmp/scout_2138.py ladder(),
copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_ladder as F, byttrade as B


def trades(b):   # the backtest
    c = [x["c"] for x in b]
    out, i, n = [], F.BB_N, len(b)
    while i < n - 1:
        if not c[i] < F.band(b, i)[0]:
            i += 1
            continue
        e0 = b[i + 1]["o"]
        fills, k = [e0], i + 1
        while k < n - 1:
            for d in F.LADDER[len(fills) - 1:]:
                if b[k]["l"] <= e0 * (1 - d):
                    fills.append(min(b[k]["o"], e0 * (1 - d)))
            if c[k] > F.band(b, k)[1]:
                break
            k += 1
        if k < n - 1:
            out.append((b[i + 1]["t"], e0, len(fills), b[k + 1]["o"]))
        i = k + 1
    return out


full = [dict(x, closed=True) for x in mts.bars("binance", "AVAXUSDT", "4h", max_age_h=240)[-4000:]]
start = 1500                    # the walk starts here; the backtest sees all bars before it as warm-up
c = [x["c"] for x in full]
while not c[start] > F.band(full, start)[1]:   # start on a close over the upper band, so the backtest is flat after it
    start += 1
want = [(round(e, 6), n, round(x, 6)) for t, e, n, x in trades(full) if t > full[start]["t"] + B.H4]
s = B.new_state("t"); s["seen"] = {"AVAXUSDT": full[start]["t"]}
s["cash"] = 1e12                # enough cash that no fill is skipped in a long walk
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, "AVAXUSDT", w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
got, cur = [], None
for x in s["log"]:
    if x["kind"] == "buy" and cur is None:
        cur = [x["px"], 1]
    elif x["kind"] == "buy":
        cur[1] += 1
    else:
        got.append((round(cur[0], 6), cur[1], round(x["px"], 6)))
        cur = None
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5 and any(n > 1 for _, n, _ in got)
t = B.new_state("t"); t["seen"] = {"AVAXUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "AVAXUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} ladders match the backtest; ok")
