"""fwd_sto7.py walking 1h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0957/sto.py signals() and trades(long_only=True), copied below) on the same 4,000 bars, fed as
sliding 1,000-bar windows like the live fetch."""
import random, sys
from collections import deque
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_sto7 as P, byttrade as B

PER = (5, 8, 13, 21, 34, 55, 89)


def bt_rolling(vals, n, fn):
    out, dq = [None] * len(vals), deque()
    for i, v in enumerate(vals):
        while dq and fn(vals[dq[-1]], v):
            dq.pop()
        dq.append(i)
        if dq[0] <= i - n:
            dq.popleft()
        if i >= n - 1:
            out[i] = vals[dq[0]]
    return out


def bt_signals(b):   # the backtest's signals, the repo's settings
    n = len(b)
    c, h, l = [x["c"] for x in b], [x["h"] for x in b], [x["l"] for x in b]
    ob, os_ = [0] * n, [0] * n
    for p in PER:
        hh, ll = bt_rolling(h, p, lambda a, v: a <= v), bt_rolling(l, p, lambda a, v: a >= v)
        for i in range(n):
            if hh[i] is None:
                continue
            r = hh[i] - ll[i]
            k = 100 * (c[i] - ll[i]) / r if r else None
            if k is None:
                continue
            ob[i] += k >= 80
            os_[i] += k <= 20
    sig, lastob, lastos, ls_prev, ss_prev, s = [0] * n, -10**9, -10**9, False, False, 0.0
    for i in range(n):
        if ob[i] >= 7:
            lastob = i
        if os_[i] >= 7:
            lastos = i
        s += c[i]
        if i >= 6:
            s -= c[i - 6]
        sma = s / 6 if i >= 5 else None
        up = dn = False
        if i >= 6:
            up, dn = sma > prev_sma, sma < prev_sma
        prev_sma = sma
        ls = i - lastos <= 3 and up
        ss = i - lastob <= 3 and dn
        if ls and not ls_prev:
            sig[i] = 1
        elif ss and not ss_prev:
            sig[i] = -1
        ls_prev, ss_prev = ls, ss
    return sig


def trades(b):   # long only: buy on +1 when flat, sell on -1, both at the next open
    sg = bt_signals(b)
    pos, out = None, []
    for i in range(len(b) - 1):
        if pos is not None:
            if sg[i] == -1:
                out.append((round(pos, 6), round(b[i + 1]["o"], 6))); pos = None
        elif sg[i] == 1:
            pos = b[i + 1]["o"]
    return out


W = 1000   # bars per call, as byttrade.fetch returns live
total = 0
for sym in P.SYMS:
    full = mts.bars("binance", sym, "1h")
    assert P.signals(full) == bt_signals(full), sym
    b = [dict(x, closed=True) for x in full[-4000:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[max(0, k - W):k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 15, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[max(0, k - W):k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL BNB XRP match the backtest; ok")
