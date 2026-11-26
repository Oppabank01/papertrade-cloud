"""fwd_wt.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0325/bt.py ema(), wt(), wt_sig() and trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_wt as P, byttrade as B


def ema(v, n):
    a, e, out = 2 / (n + 1), v[0], []
    for x in v:
        e += a * (x - e); out.append(e)
    return out


def bt_signals(b, n1=10, n2=21, lo=-65, ex=65):
    ap = [(x["h"] + x["l"] + x["c"]) / 3 for x in b]
    esa = ema(ap, n1)
    d = ema([abs(a - e) for a, e in zip(ap, esa)], n1)
    ci = [(a - e) / (0.015 * dd) if dd else 0.0 for a, e, dd in zip(ap, esa, d)]
    w = ema(ci, n2)
    out = [None]
    for i in range(1, len(b)):
        s = None
        if w[i - 1] > lo >= w[i]:
            s = "buy"
        elif w[i - 1] < ex <= w[i]:
            s = "sell"
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
    b = [dict(x, closed=True) for x in full[-3000:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 15, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL BNB XRP match the backtest; ok")
