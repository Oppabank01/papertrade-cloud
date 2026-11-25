"""fwd_rvwap.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_0405/bt_rv.py trades())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_rvwap as P, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "4h", max_age_h=24 * 30)[-1500:]]
L = P.line(b)
want, i, n = [], 401, len(b)
while i + P.HOLD + 1 < n - 1:                          # the walk never sees the last bar closed
    d = P.signal(b, i, L)
    if not d:
        i += 1; continue
    want.append((round(b[i + 1]["o"], 6), round(b[i + 1 + P.HOLD]["o"], 6))); i += P.HOLD + 1
s = B.new_state("t"); s["seen"] = {"BTCUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(s, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 5
# the line matches an independent rolling mean of hlc3
h = [(x["h"] + x["l"] + x["c"]) / 3 for x in b]
assert all(abs(L[j] - sum(h[j - 17:j + 1]) / 18) < 1e-6 * h[j] for j in range(17, n, 97))
t = B.new_state("t"); t["seen"] = {"BTCUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(t, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
