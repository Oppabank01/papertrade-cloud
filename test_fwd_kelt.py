"""fwd_kelt.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0642/vk.py keltner_lines() and keltner_trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_kelt as P, byttrade as B


def bt_lines(b, n=20, an=10):
    a = 2 / (n + 1)
    ema, atr, trs, E, A = None, None, [], [], []
    for i, x in enumerate(b):
        ema = x["c"] if ema is None else a * x["c"] + (1 - a) * ema
        tr = x["h"] - x["l"] if i == 0 else max(x["h"], b[i - 1]["c"]) - min(x["l"], b[i - 1]["c"])
        trs.append(tr)
        if atr is None and len(trs) == an:
            atr = sum(trs) / an
        elif atr is not None:
            atr = (atr * (an - 1) + tr) / an
        E.append(ema); A.append(atr)
    return E, A


def trades(b, k=2.5, sm=2.0, tm=3.0, warm=60):   # the backtest's Keltner breakout, the repo's set B
    E, A = bt_lines(b)
    out, pos = [], None
    for i in range(warm, len(b) - 1):
        x = b[i]
        if pos is not None:
            e, stp, tgt, j = pos
            if i >= j:
                if x["o"] <= stp or x["l"] <= stp:
                    out.append((round(e, 6), round(min(x["o"], stp), 6))); pos = None; continue
                if x["o"] >= tgt or x["h"] >= tgt:
                    out.append((round(e, 6), round(max(x["o"], tgt), 6))); pos = None; continue
                if x["c"] < E[i]:
                    out.append((round(e, 6), round(b[i + 1]["o"], 6))); pos = None
            continue
        if x["c"] > E[i] + k * A[i]:
            e = b[i + 1]["o"]
            pos = (e, e - sm * A[i], e + tm * A[i], i + 1)
    return out


total = 0
for sym in P.SYMS:
    full = mts.bars("binance", sym, "4h")
    assert P.lines(full) == bt_lines(full), sym
    b = [dict(x, closed=True) for x in full[-1000:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert any("stop" in x["why"] for x in s["log"] if x["kind"] == "sell") or sym != "BTCUSDT"
    total += len(got)
assert total >= 25, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL BNB XRP match the backtest; ok")
