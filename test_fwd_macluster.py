"""fwd_macluster.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_1207/bt.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_macluster as P, byttrade as B


def leg(b, j0, d):
    e = b[j0]["o"]; stop = e * (1 - d * P.SL); tgt = e * (1 + d * P.TP); peak = e
    for j in range(j0, len(b)):
        x = b[j]; o, h, l = x["o"], x["h"], x["l"]
        if d > 0:
            if o <= stop: return o, j
            if l <= stop: return stop, j
            if h >= tgt: return max(tgt, o), j
            peak = max(peak, h)
            if peak >= e * (1 + P.ACT): stop = max(stop, peak * (1 - P.DIST))
        else:
            if o >= stop: return o, j
            if h >= stop: return stop, j
            if l <= tgt: return min(tgt, o), j
            peak = min(peak, l)
            if peak <= e * (1 - P.ACT): stop = min(stop, peak * (1 + P.DIST))
        if j - j0 + 1 >= P.MAXH: return x["c"], j
    return None, None


b = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "4h")[-3000:]]
m, ss = P.ind(b)
want, i, n = [], 401, len(b)
while i < n - 1:
    d = P.signal(b, i, m, ss)
    if not d:
        i += 1; continue
    px, j = leg(b, i + 1, d)
    if px is None:
        break
    want.append((round(b[i + 1]["o"], 6), round(px, 6))); i = j + 1
s = B.new_state("t"); s["seen"] = {"BTCUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(s, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5
t = B.new_state("t"); t["seen"] = {"BTCUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(t, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
