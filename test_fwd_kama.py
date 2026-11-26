"""fwd_kama.py walking daily bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0325/bt.py kama(), kama_sig() and trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_kama as P, byttrade as B


def bt_kama(c, er_n=10, fast=2, slow=30):
    fs, ss = 2 / (fast + 1), 2 / (slow + 1)
    out = [None] * len(c)
    if len(c) <= er_n:
        return out
    out[er_n] = c[er_n]
    for i in range(er_n + 1, len(c)):
        ch = abs(c[i] - c[i - er_n])
        vol = sum(abs(c[j] - c[j - 1]) for j in range(i - er_n + 1, i + 1))
        er = ch / vol if vol else 0.0
        sc = (er * (fs - ss) + ss) ** 2
        out[i] = out[i - 1] + sc * (c[i] - out[i - 1])
    return out


def bt_signals(b):
    c = [x["c"] for x in b]
    k = bt_kama(c)
    return [None if k[i] is None else ("buy" if c[i] > k[i] else "sell") for i in range(len(b))]


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
    full = mts.bars("binance", sym, "1d")
    assert P.signals(full) == bt_signals(full), sym
    b = [dict(x, closed=True) for x in full[-600:]]
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
