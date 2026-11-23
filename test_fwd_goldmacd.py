"""fwd_goldmacd.py walking bars one at a time gives the same entries and exits as the scout's backtest (bt.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_goldmacd as P, byttrade as B

sym = "PAXGUSDT"
b = [dict(x, closed=True) for x in mts.bars("binance", sym, "2h")[-1200:]]
sig, atr = P.ind(b)
want, i, n = [], 301, len(b)
while i < n - 1:
    d = sig[i]
    if not d or not atr[i]:
        i += 1; continue
    e = b[i + 1]["o"]; stop, tgt = e - d * P.SL * atr[i], e + d * P.TP * atr[i]
    px, j = None, i + 1
    while j < n:
        y = b[j]
        if d > 0:
            px = y["o"] if y["o"] <= stop else stop if y["l"] <= stop else max(tgt, y["o"]) if y["h"] >= tgt else None
        else:
            px = y["o"] if y["o"] >= stop else stop if y["h"] >= stop else min(tgt, y["o"]) if y["l"] <= tgt else None
        if px is None and j - i >= P.HOLD:
            px = y["c"]
        if px is not None:
            break
        j += 1
    if px is None or j >= n - 1:   # the walk never sees the last bar closed
        break
    want.append((d, round(e, 6), round(px, 6))); i = j + 1
s = B.new_state("t"); s["seen"] = {sym: b[300]["t"]}
for k in range(302, n + 1):
    P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(1 if x["side"] == "long" else -1, round(x["px"], 6), round(p, 6)) for x, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5, len(got)
t = B.new_state("t"); t["seen"] = {sym: b[300]["t"]}
for k in range(302, n + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
