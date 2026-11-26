"""fwd_vortex.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0642/vk.py vortex_signals() and trades_from(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_vortex as P, byttrade as B


def bt_signals(b, n=14, th=0.15):   # the backtest's Vortex, the repo's settings
    a = 2 / (n + 1)
    out, hold = [None], False
    eu = ed = None
    trs, diff_prev = [], None
    for i in range(1, len(b)):
        ru, rd = abs(b[i]["h"] - b[i - 1]["l"]), abs(b[i]["l"] - b[i - 1]["h"])
        eu = ru if eu is None else a * ru + (1 - a) * eu
        ed = rd if ed is None else a * rd + (1 - a) * ed
        trs.append(max(b[i]["h"], b[i - 1]["c"]) - min(b[i]["l"], b[i - 1]["c"]))
        s = None
        if len(trs) >= n:
            atr = sum(trs[-n:]) / n
            d = (eu - ed) / atr if atr else 0.0
            if diff_prev is not None:
                if not hold and d > th and diff_prev <= th:
                    s, hold = "buy", True
                elif hold and d < -th and diff_prev >= -th:
                    s, hold = "sell", False
            diff_prev = d
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
