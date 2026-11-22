"""pullback.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_tpc.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import pullback as P, byttrade as B

b = [dict(x, closed=True) for x in mts.bars("binance", "ETHUSDT", "4h")[-1300:]]
sma, rsi, atr = P.ind(b)
want, i, n = [], 401, len(b)
while i < n - 1:
    d = P.signal(b[i], sma[i], rsi[i])
    if not d or not atr[i]:
        i += 1; continue
    e = b[i + 1]["o"]; stop, tgt = e - d * 2 * atr[i], e + d * 4 * atr[i]
    px, j = None, i + 1
    while j < n:
        y = b[j]
        if d > 0:
            px = y["o"] if y["o"] <= stop else stop if y["l"] <= stop else max(tgt, y["o"]) if y["h"] >= tgt else None
        else:
            px = y["o"] if y["o"] >= stop else stop if y["h"] >= stop else min(tgt, y["o"]) if y["l"] <= tgt else None
        if px is not None:
            break
        j += 1
    if px is None:
        break
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
