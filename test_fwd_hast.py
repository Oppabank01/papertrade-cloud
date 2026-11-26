"""fwd_hast.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0146/hast.py signals() and trades_from(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hast as P, byttrade as B


def bt_signals(b, n=10, m=3.0):   # the backtest's Supertrend on Heikin Ashi, default settings
    k = P.ha(b)
    atr, fu, fl, pc, d = None, None, None, None, 0
    out = []
    for i, (o, h, l, c) in enumerate(k):
        tr = h - l if pc is None else max(h - l, abs(h - pc), abs(l - pc))
        atr = tr if atr is None else atr + (tr - atr) / n
        mid = (h + l) / 2
        up, lo = mid + m * atr, mid - m * atr
        if fu is None:
            nu, nl = up, lo
        else:
            nu = up if (up < fu or pc > fu) else fu
            nl = lo if (lo > fl or pc < fl) else fl
        sig = None
        if fu is not None and i >= n:
            prev = d
            if d != 1 and c > nu:
                d = 1
            elif d != -1 and c < nl:
                d = -1
            sig = "buy" if d == 1 and prev != 1 else "sell" if d == -1 and prev == 1 else None
        fu, fl, pc = nu, nl, c
        out.append(sig)
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
