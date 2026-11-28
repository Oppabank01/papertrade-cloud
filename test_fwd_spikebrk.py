"""fwd_spikebrk.py walking bars one at a time gives the same entries and exits as the scout's backtest (scout_0359/vb.py
trades() with the range proxy)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_spikebrk as F, byttrade as B


def backtest(b):   # copy of the scout's vb.trades(): stop 3%, target 6%, opposite signal out at the next open
    s, out, i, n = F.signals(b), [], 0, len(b)
    while i < n - 1:
        d = s[i]
        if not d:
            i += 1; continue
        e, j, px = b[i + 1]["o"], i + 1, None
        sp, tg = e * (1 - d * F.STOP), e * (1 + d * F.TGT)
        while j < n:
            x = b[j]
            if d > 0:
                px = x["o"] if x["o"] <= sp else sp if x["l"] <= sp else max(tg, x["o"]) if x["h"] >= tg else None
            else:
                px = x["o"] if x["o"] >= sp else sp if x["h"] >= sp else min(tg, x["o"]) if x["l"] <= tg else None
            if px is None and s[j] == -d and j + 1 < n:
                px = b[j + 1]["o"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((round(e, 10), round(px, 10)))
        i = j + 1
    return out


total = 0
for sym in ("WIFUSDT", "PEPEUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "4h")[-1300:]]
    start = 400
    want = [t for t in backtest(b[start:])]
    s = B.new_state("t"); s["seen"] = {sym: b[start - 1]["t"]}
    # the walk sees bars from start on; signals need 20 bars of history, so the backtest above starts at the same bar
    # and the walk gets the same history window by slicing from start
    for k in range(start + 2, len(b) + 1):
        F.step(s, sym, b[start:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 10), round(p, 10)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) > 5, (sym, len(got))
    total += len(got)
    t = B.new_state("t"); t["seen"] = {sym: b[start - 1]["t"]}
    for k in range(start + 2, len(b) + 1):
        F.step(t, sym, b[start:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
    assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades match the backtest; ok")
