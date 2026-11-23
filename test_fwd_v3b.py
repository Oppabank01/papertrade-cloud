"""fwd_v3b.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_2325_v3b.py run(), copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_v3b as F, byttrade as B


def trades(b):   # the backtest
    I = F.ind(b); n = len(b); out = []; i = 100
    while i < n - 1:
        d = F.signal(b, i, I)
        if not d:
            i += 1; continue
        e, a = b[i + 1]["o"], I[3][i]
        stop, tgt = e - d * F.SL * a, e + d * F.TP * a
        px, j = None, i + 1
        while j < n:
            y = b[j]
            if d > 0:
                px = y["o"] if y["o"] <= stop else stop if y["l"] <= stop else max(tgt, y["o"]) if y["h"] >= tgt else None
            else:
                px = y["o"] if y["o"] >= stop else stop if y["h"] >= stop else min(tgt, y["o"]) if y["l"] <= tgt else None
            if px is None and j - i >= F.CAP:
                px = y["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((b[i + 1]["t"], round(e, 6), round(px, 6))); i = j + 1
    return out


b = [dict(x, closed=True) for x in mts.bars("binance", "BTCUSDT", "4h", max_age_h=24 * 7)[-1500:]]
start = 400
want = [(e, x) for t, e, x in trades(b) if t > b[start + 1]["t"]]
s = B.new_state("t"); s["seen"] = {"BTCUSDT": b[start]["t"]}
for k in range(start + 2, len(b) + 1):
    F.step(s, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 4
t = B.new_state("t"); t["seen"] = {"BTCUSDT": b[start]["t"]}
for k in range(start + 2, len(b) + 1):
    F.step(t, "BTCUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
