"""fwd_pulsedip.py walking 1h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_1048/bt.py trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_pulsedip as P, byttrade as B


def trades(b):   # the backtest, default settings
    c = [x["c"] for x in b]; r, e = P.rsi(c), P.ema(c, P.EMA_N)
    pos, last, out = None, None, []
    for i in range(len(b) - 1):
        if pos:
            en, hi = pos[1], max(pos[2], c[i]); pos[2] = hi
            why = "stop" if c[i] <= en * (1 - P.SL) else "trail" if hi >= en * (1 + P.TP_ARM) and c[i] <= hi * (1 - P.TRAIL) \
                else "rsi" if r[i] >= P.RSI_SELL else None
            if why:
                out.append((round(en, 6), round(b[i + 1]["o"], 6))); pos, last = None, i
            continue
        if last is not None and i - last < P.COOL:
            continue
        if r[i] is None or e[i] is None:
            continue
        if r[i] <= P.RSI_BUY and c[i] >= e[i] * (1 - P.TOL):
            pos = [i + 1, b[i + 1]["o"], b[i + 1]["o"]]
    return out


total = 0
for sym in P.SYMS:
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h")[-3000:]]
    want = trades(b)
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 20, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL match the backtest; ok")
