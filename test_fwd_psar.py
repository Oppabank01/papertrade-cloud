"""fwd_psar.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0504/sar.py psar_signals() and trades_from(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_psar as P, byttrade as B


def bt_signals(b, a0=0.02, step=0.02, amax=0.2):   # the backtest's Parabolic SAR, default settings
    out = [None, None]
    up = b[1]["c"] > b[0]["c"]
    sar = b[0]["l"] if up else b[0]["h"]
    ep = b[1]["h"] if up else b[1]["l"]
    af = a0
    for i in range(2, len(b)):
        h, l = b[i]["h"], b[i]["l"]
        sar = sar + af * (ep - sar)
        sig = None
        if up:
            sar = min(sar, b[i - 1]["l"], b[i - 2]["l"])
            if l < sar:
                up, sar, ep, af, sig = False, ep, l, a0, "sell"
            elif h > ep:
                ep, af = h, min(af + step, amax)
        else:
            sar = max(sar, b[i - 1]["h"], b[i - 2]["h"])
            if h > sar:
                up, sar, ep, af, sig = True, ep, h, a0, "buy"
            elif l < ep:
                ep, af = l, min(af + step, amax)
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
