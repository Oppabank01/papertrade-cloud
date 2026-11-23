"""fwd_cascade.py walking 15m bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_casc.py trades(), copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_cascade as F, byttrade as B


def trades(b, thr=F.THR, hold=F.HOLD):   # the backtest, reversal check on
    out, i, n = [], 1, len(b)
    while i < n - 1:
        r = b[i]["c"] / b[i]["o"] - 1
        d = -1 if r >= thr else 1 if r <= -thr else 0
        if not d:
            i += 1; continue
        k = i + 1
        if k >= n - 1 or (b[k]["c"] - b[k]["o"]) * d <= 0:
            i += 1; continue
        e, j = k + 1, k + 1 + hold
        if j >= n:
            break
        out.append((b[e]["o"], b[j]["o"]))
        i = j
    return out


b = [dict(x, closed=True) for x in mts.bars("binance", "SOLUSDT", "15m", max_age_h=240)[-6000:]]
start = 50
want = [(round(e, 6), round(x, 6)) for e, x in trades(b[start:])]
s = B.new_state("t"); s["seen"] = {"SOLUSDT": b[start]["t"]}
for k in range(start + 2, len(b) + 1):
    F.step(s, "SOLUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5
sides = {x["side"] for x in s["log"] if x["kind"] == "buy"}
t = B.new_state("t"); t["seen"] = {"SOLUSDT": b[start]["t"]}
for k in range(start + 2, len(b) + 1):
    F.step(t, "SOLUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest ({sorted(sides)}); ok")
