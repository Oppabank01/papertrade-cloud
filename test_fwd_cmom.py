"""fwd_cmom.py walking 15m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as the scout's backtest (/tmp/scout_2325_cmom.py run(), copied below), with and without the stop."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_cmom as F, byttrade as B


def trades(b, stop):   # the backtest
    out, n, i, days = [], len(b), 0, []
    while i < n:
        k = b[i]["t"] // F.DAY; j = i
        while j < n and b[j]["t"] // F.DAY == k:
            j += 1
        if j - i == 96:
            days.append((i, j))
        i = j
    for (pa, pz), (a, z) in zip(days, days[1:]):
        if b[a]["t"] - b[pa]["t"] != F.DAY:
            continue
        po, pc = b[pa]["o"], b[pz - 1]["c"]
        d = 1 if pc > po else -1 if pc < po else 0
        if not d:
            continue
        e = b[a]["o"]; px = None
        for x in b[a:z]:
            if stop and (x["c"] - e) * d <= -stop * e:
                px = x["c"]; break
        if px is None:
            px = b[z - 1]["c"]
        out.append((b[a]["t"], round(e, 6), round(px, 6)))
    return out


bars = mts.bars("binance", "ETHUSDT", "15m", max_age_h=24 * 30)
full = [dict(x, closed=True) for x in bars[-4000:]]
start = next(j for j in range(1100, len(full)) if (full[j]["t"] + F.M15) % F.DAY == 0) - 96   # a day's last bar - 1 day
for stop in (0.01, 0):
    want = [(e, x) for t, e, x in trades(full, stop) if t > full[start]["t"] + F.M15]
    s = B.new_state("t"); s["seen"] = {"ETHUSDT": full[start]["t"]}
    for k in range(start + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, "ETHUSDT", w[:-1] + [dict(w[-1], closed=False)], "rule", stop, random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    m = min(len(got), len(want))   # the backtest drops the last, unfinished day; the walk may already have traded it
    assert got[:m] == want[:m] and abs(len(want) - len(got)) <= 1, (stop, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 15
t = B.new_state("t"); t["seen"] = {"ETHUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "ETHUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", 0.01, random.Random(k))
assert sum(x["kind"] == "sell" for x in t["log"]) >= 15
print(f"{len(got)} trades match the backtest; ok")
