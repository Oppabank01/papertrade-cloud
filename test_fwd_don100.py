"""fwd_don100.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_0731/bt_don.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_don100 as P, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "ETHUSDT", "4h")[-2500:]]
atr, flip = P.ind(b)
want, i, n = [], 401, len(b)
while i < n - 1:
    if not flip[i] or not atr[i]:
        i += 1; continue
    e = b[i + 1]["o"]; stop = e - P.K * atr[i]; ext = e; px = None
    last, j = min(n - 1, i + P.MAXB), i + 1
    while j <= last:
        y = b[j]
        if y["l"] <= stop:
            px = min(stop, y["o"]); break
        ext = max(ext, y["h"])
        stop = max(stop, ext - P.K * atr[j])
        j += 1
    if px is None:
        if last - i < P.MAXB:
            break
        j, px = last, b[last]["c"]
    want.append((round(e, 6), round(px, 6))); i = j + 1
s = B.new_state("t"); s["seen"] = {"ETHUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(s, "ETHUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5
t = B.new_state("t"); t["seen"] = {"ETHUSDT": b[400]["t"]}
for k in range(402, n + 1):
    P.step(t, "ETHUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
