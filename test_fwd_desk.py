"""fwd_desk.py walking 1h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_1457/desk.py scores(use_vol=False) and walk(), copied below) on the last 4,000 bars, fed as
sliding 1,000-bar windows like the live fetch."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_desk as P, byttrade as B


def clip(x):
    return max(0.0, min(1.0, x))


def bt_scores(b):   # the backtest's score over the whole history, volume fixed at 0.5
    n = len(b)
    c = [x["c"] for x in b]
    e20, e50 = [c[0]] * n, [c[0]] * n
    for i in range(1, n):
        e20[i] = c[i] * (2 / 21) + e20[i - 1] * (1 - 2 / 21)
        e50[i] = c[i] * (2 / 51) + e50[i - 1] * (1 - 2 / 51)
    rsi, ag, al = [50.0] * n, 0.0, 0.0
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            rsi[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    out = [None] * n
    for i in range(264, n):
        r6, r24 = c[i] / c[i - 6] - 1, c[i] / c[i - 24] - 1
        mom = 0.5 * clip(0.5 + r6 / 0.08) + 0.5 * clip(0.5 + r24 / 0.20)
        if rsi[i] > 75:
            mom *= 0.8
        t1 = 1.0 if c[i] > e20[i] else 0.0
        t2 = 1.0 if e20[i] > e50[i] else 0.0
        t3 = clip(0.5 + (e50[i] / e50[i - 12] - 1) / 0.02)
        out[i] = 0.40 * mom + 0.35 * (0.35 * t1 + 0.35 * t2 + 0.30 * t3) + 0.25 * 0.5
    return out


def bt_walk(b, sig, start):   # flat at `start`; stop -8%, trail 5% from the peak once +10%, low checked first
    out, pos, cool = [], None, -1
    for j in range(start, len(b)):
        x = b[j]
        if pos:
            if j >= pos["j"]:
                if x["l"] <= pos["stop"]:
                    out.append((round(pos["e"], 6), round(min(pos["stop"], x["o"]), 6))); pos = None; cool = j + 1
                    continue
                pos["peak"] = max(pos["peak"], x["h"])
                if pos["peak"] >= pos["e"] * 1.10:
                    pos["stop"] = max(pos["stop"], pos["peak"] * 0.95)
            continue
        if j >= cool and j + 1 < len(b) and sig[j]:
            e = b[j + 1]["o"]
            pos = dict(e=e, j=j + 1, stop=e * 0.92, peak=e)
    return out


W, N = 1000, 4000   # bars per call as byttrade.fetch returns live; bars walked per coin
total = 0
for sym in P.SYMS:
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h", max_age_h=400)]
    S = len(full) - N
    sig = [v is not None and v >= 0.6 for v in bt_scores(full)]
    want = [t for t in bt_walk(full, sig, S)]
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
print(f"{total} trades over 10 coins match the backtest; ok")
