"""fwd_nearhigh.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_1534/bt.py trades())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_nearhigh as P, byttrade as B


def leg(b, j0):
    e = b[j0]["o"]; stop = e * (1 - P.SL); tgt = e * (1 + P.TP)
    for j in range(j0, len(b)):
        x = b[j]; o, h, l = x["o"], x["h"], x["l"]
        if o <= stop: return o, j
        if l <= stop: return stop, j
        if h >= tgt: return max(tgt, o), j
        if j - j0 + 1 >= P.MAXH: return x["c"], j
    return None, None


b = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "1h")[-5000:]]   # SOL fires about once in 5000 bars
sma, h7 = P.ind(b)
want, i, n = [], 601, len(b)
while i < n - 1:
    if not P.signal(b, i, sma, h7):
        i += 1; continue
    px, j = leg(b, i + 1)
    if px is None:
        break
    want.append((round(b[i + 1]["o"], 6), round(px, 6))); i = j + 2
s = B.new_state("t"); s["seen"] = {"BTCUSDT": b[600]["t"]}
for k in range(602, n + 1):
    P.step(s, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 5
t = B.new_state("t"); t["seen"] = {"BTCUSDT": b[600]["t"]}
for k in range(602, n + 1):
    P.step(t, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
