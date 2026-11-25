"""fwd_stbb.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_0216/bt_st.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_stbb as P, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "SOLUSDT", "15m", max_age_h=24 * 30)[-3000:]]
I = P.ind(b)
want, i, n = [], 401, len(b)
while i < n - 1:
    d = P.signal(b, i, I)
    if not d:
        i += 1; continue
    e, px, j = b[i + 1]["o"], None, i + 1
    while j < n - 1:                                   # the walk never sees the last bar closed
        px, _ = P.exit_px(b, j, I, d, e)
        if px is not None:
            break
        j += 1
    if px is None:
        break
    want.append((round(e, 6), round(px, 6))); i = j          # a fresh flip on the exit bar may open again
s = B.new_state("t"); s["seen"] = {"SOLUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(s, "SOLUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 5
t = B.new_state("t"); t["seen"] = {"SOLUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(t, "SOLUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
