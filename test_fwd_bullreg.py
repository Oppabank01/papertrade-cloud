"""fwd_bullreg.py walking daily bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_0820/bt.py regime(), atr() and trades(), copied below) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_bullreg as P, byttrade as B


def bt_regime(b, ma=200, er_n=90, er_min=0.14, confirm=5):
    c = [x["c"] for x in b]
    out, state, run, cand = [None] * len(b), None, 0, None
    for i in range(len(b)):
        if i < max(ma, er_n):
            continue
        sma = sum(c[i - ma + 1:i + 1]) / ma
        vol = sum(abs(c[j] - c[j - 1]) for j in range(i - er_n + 1, i + 1))
        er = abs(c[i] - c[i - er_n]) / vol if vol else 0.0
        raw = "not" if c[i] <= sma else ("strong" if er > er_min else "weak")
        if state is None:
            state = raw
        elif raw != state:
            run = run + 1 if raw == cand else 1
            cand = raw
            if run >= confirm:
                state, run, cand = raw, 0, None
        else:
            run, cand = 0, None
        out[i] = state
    return out


def bt_atr(b, n=20):
    tr = [None] + [max(x["h"], p["c"]) - min(x["l"], p["c"]) for p, x in zip(b, b[1:])]
    return [None if i < n else sum(tr[i - n + 1:i + 1]) / n for i in range(len(b))]


def trades(b, reg, k=3, xlow=10):
    c, a = [x["c"] for x in b], bt_atr(b)
    pos, out = None, []
    for i in range(len(b) - 1):
        if pos:
            if b[i]["l"] <= pos["stop"]:
                out.append((round(pos["e"], 6), round(min(b[i]["o"], pos["stop"]), 6))); pos = None
                continue
            pos["hc"] = max(pos["hc"], c[i])
            pos["stop"] = max(pos["stop"], pos["hc"] - k * a[i])
            if c[i] < min(c[i - xlow:i]) or reg[i] not in ("strong", "weak"):
                out.append((round(pos["e"], 6), round(b[i + 1]["o"], 6))); pos = None
            continue
        if i < 21 or a[i] is None or reg[i] != "strong":
            continue
        if c[i] > max(c[i - 20:i]):
            e = b[i + 1]["o"]
            pos = dict(e=e, stop=e - k * a[i], hc=0.0)
    return out


btc = mts.bars("binance", "BTCUSDT", "1d")
full_reg = bt_regime(btc)
assert P.regime(btc) == full_reg
# the 1000-day window the live script sees settles on the same states as the full history after its first year
w = btc[-1000:]
assert P.regime(w)[-500:] == full_reg[-500:]
reg_by_t = {x["t"]: r for x, r in zip(btc, full_reg)}
total = 0
for sym in P.SYMS:
    full = mts.bars("binance", sym, "1d")
    b = [dict(x, closed=True) for x in full[-1200:]]
    want = trades(b, [reg_by_t.get(x["t"]) for x in b])
    s = B.new_state("t"); s["seen"] = {sym: b[0]["t"]}
    for k in range(2, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], reg_by_t, "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 25, total
t = B.new_state("t"); t["seen"] = {sym: b[0]["t"]}
for k in range(2, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], reg_by_t, "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over BTC ETH SOL BNB XRP match the backtest; ok")
