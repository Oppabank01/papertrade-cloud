"""fwd_aroon.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0504/sar.py aroon_signals() and trades_from(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_aroon as P, byttrade as B


def bt_signals(b, n=14, hi=50, lo=-50):   # the backtest's Aroon, the repo's settings
    out, hold = [], False
    for i in range(len(b)):
        s = None
        if i >= n - 1:
            w = b[i - n + 1:i + 1]
            hs = [x["h"] for x in w]; ls = [x["l"] for x in w]
            ih = max(range(n), key=lambda j: (hs[j], -j))
            il = min(range(n), key=lambda j: (ls[j], j))
            osc = 100 * (n - (n - 1 - ih)) / n - 100 * (n - (n - 1 - il)) / n
            if not hold and osc > hi:
                s, hold = "buy", True
            elif hold and osc < lo:
                s, hold = "sell", False
        out.append(s)
    return out


def trades(b):
    sg = bt_signals(b)
    pos, out = None, []
    for i in range(len(b) - 1):
        if pos is not None:
            if sg[i] == "sell":
                out.append((round(pos, 6), round(b[i + 1]["o"], 6))); pos = None
        elif sg[i] == "buy":
            pos = b[i + 1]["o"]
    return out


total = 0
for sym in P.SYMS:
    full = mts.bars("binance", sym, "4h")
    assert P.signals(full) == bt_signals(full), sym
    b = [dict(x, closed=True) for x in full[-1000:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 25, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL BNB XRP match the backtest; ok")
