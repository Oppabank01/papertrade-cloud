"""fwd_tpull.py walking bars one at a time gives the same entries and exits as the scout's backtest (bt.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_tpull as P, byttrade as B

total = 0
for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h")[-2500:]]
    sig, atr = P.ind(b)
    want, i, n = [], 301, len(b)
    while i < n - 1:
        d = sig[i]
        if not d or not atr[i]:
            i += 1; continue
        e = b[i + 1]["o"]; stop, tgt = e * (1 - d * P.SL), e * (1 + d * P.TP)
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
        if px is None or j >= n - 1:   # the walk never sees the last bar closed
            break
        want.append((d, round(e, 6), round(px, 6))); i = j + 1
    s = B.new_state("t"); s["seen"] = {sym: b[300]["t"]}
    for k in range(302, n + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(1 if x["side"] == "long" else -1, round(x["px"], 6), round(p, 6)) for x, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total > 5, total
t = B.new_state("t"); t["seen"] = {sym: b[300]["t"]}
for k in range(302, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades match the backtest; ok")
