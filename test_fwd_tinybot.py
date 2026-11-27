"""fwd_tinybot.py walking 1h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_1959/tiny.py walk(), copied below with its indicators run over the whole history) on the last 3,000 bars,
fed as sliding 1,000-bar windows like the live fetch."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_tinybot as P, byttrade as B


def bt_ind(b):   # the backtest's indicators over the whole history
    c = [x["c"] for x in b]
    n = len(c)

    def ema(span):
        out = [None] * n
        e = sum(c[:span]) / span
        out[span - 1] = e
        for i in range(span, n):
            e = c[i] * (2 / (span + 1)) + e * (1 - 2 / (span + 1))
            out[i] = e
        return out
    rsi, ag, al = [None] * n, 0.0, 0.0
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 10:
            ag += g / 10; al += l / 10
        else:
            ag = (ag * 9 + g) / 10; al = (al * 9 + l) / 10
        if i >= 10:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return ema(6), ema(24), rsi, c


def bt_walk(b, start):   # flat at `start`; signal on close i, fill at open i+1; exits read on closes from the entry bar
    e6, e24, rsi, c = bt_ind(b)
    n, i, out = len(b), start, []
    while i < n - 1:
        r12 = c[i] / c[i - 12] - 1
        ent = (rsi[i] < 32 and c[i] < e24[i] * 0.98 and r12 < -0.03) or (e6[i] > e24[i] and e6[i - 1] <= e24[i - 1] and r12 > 0.02)
        if not ent:
            i += 1; continue
        e, j, hit = b[i + 1]["o"], i + 1, False
        while j < n - 1:
            if rsi[j] > 65 or c[j] >= e * 1.10 or c[j] <= e * 0.88 or (e6[j] < e24[j] and e6[j - 1] >= e24[j - 1]):
                hit = True
                break
            j += 1
        if not hit:
            break
        out.append((round(e, 6), round(b[j + 1]["o"], 6)))
        i = j + 1
    return out


W, N = 1000, 3000   # bars per call as byttrade.fetch returns live; bars walked per coin
total = 0
for sym in P.SYMS:
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h", max_age_h=400)]
    S = len(full) - N
    want = bt_walk(full, S)
    s = B.new_state("t"); s["seen"] = {sym: full[S - 1]["t"]}
    for k in range(S + 1, len(full) + 1):
        P.step(s, sym, full[k - W:k - 1] + [dict(full[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(x, 6)) for e, x in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total >= 30, total
t = B.new_state("t"); t["seen"] = {sym: full[S - 1]["t"]}
for k in range(S + 1, len(full) + 1):
    P.step(t, sym, full[k - W:k - 1] + [dict(full[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades over {len(P.SYMS)} coins match the backtest; ok")
