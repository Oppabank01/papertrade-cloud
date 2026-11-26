"""fwd_macdcci.py walking 1h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_2042/bt.py trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_macdcci as P, byttrade as B


def trades(b):   # the backtest, default settings
    sg = P.signals(b)
    pos, out = None, []
    for i in range(len(b) - 1):
        if pos:
            pos[1] = max(pos[1], b[i]["c"])
            if b[i]["c"] < pos[1] * (1 - P.TRAIL) or sg[i] == "down":
                out.append((round(pos[0], 6), round(b[i + 1]["o"], 6))); pos = None
            continue
        if sg[i] == "up":
            pos = [b[i + 1]["o"], b[i + 1]["o"]]
    return out


total = 0
for sym in P.SYMS:
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h")[-1500:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 40, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over SOL ETH WIF RAY match the backtest; ok")
