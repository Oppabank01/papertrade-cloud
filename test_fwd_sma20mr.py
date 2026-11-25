"""fwd_sma20mr.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_0216/bt_mr.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_sma20mr as P, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "XRPUSDT", "1h", max_age_h=24 * 30)[-2000:]]
m = P.sma(b)
c = [x["c"] for x in b]
want, i, n = [], 401, len(b)
while i < n - 1:
    if not (m[i] is not None and c[i] <= m[i] * (1 - P.BAND)):
        i += 1; continue
    e = b[i + 1]["o"]; stop, tgt = e * (1 - P.SL), e * (1 + P.TP); px, j = None, i + 1
    while j < n - 1:                                   # the walk never sees the last bar closed
        y = b[j]
        if j > i + 1 and c[j - 1] >= m[j - 1] * (1 + P.BAND): px = y["o"]; break
        if y["o"] <= stop: px = y["o"]; break
        if y["l"] <= stop: px = stop; break
        if y["h"] >= tgt: px = max(tgt, y["o"]); break
        j += 1
    if px is None:
        break
    want.append((round(e, 6), round(px, 6))); i = j
s = B.new_state("t"); s["seen"] = {"XRPUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(s, "XRPUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 5
t = B.new_state("t"); t["seen"] = {"XRPUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(t, "XRPUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
