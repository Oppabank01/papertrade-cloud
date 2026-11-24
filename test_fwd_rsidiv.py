"""fwd_rsidiv.py walking bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_1909/b_div.py div_signals() + /tmp/scout_1715/bt.py walk(), copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_rsidiv as P, byttrade as B


def wilder(vals, n):
    out, a = [None] * len(vals), None
    for i, v in enumerate(vals):
        if v is None:
            continue
        a = v if a is None else (a * (n - 1) + v) / n
        out[i] = a
    return out


def bt_signals(b, PR=3, GAP_MIN=5, GAP_MAX=40, OS=35, OB=65):
    n, c = len(b), [x["c"] for x in b]
    ag = wilder([None] + [max(c[i] - c[i - 1], 0) for i in range(1, n)], 14)
    al = wilder([None] + [max(c[i - 1] - c[i], 0) for i in range(1, n)], 14)
    rsi = [None if i < 14 else (100 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])) for i in range(n)]
    sig, stopd, lows, highs = [0] * n, [None] * n, [], []
    for i in range(2 * PR, n - 1):
        k = i - PR
        win = b[k - PR:k] + b[k + 1:k + PR + 1]
        if rsi[k] is None:
            continue
        if b[k]["l"] < min(x["l"] for x in win):
            for k1 in reversed(lows):
                if k - k1 > GAP_MAX:
                    break
                if k - k1 >= GAP_MIN:
                    if b[k]["l"] < b[k1]["l"] and rsi[k] > rsi[k1] and rsi[k1] <= OS:
                        e = b[i + 1]["o"]
                        if e > b[k]["l"]:
                            sig[i], stopd[i] = 1, e - b[k]["l"]
                    break
            lows.append(k)
        if b[k]["h"] > max(x["h"] for x in win):
            for k1 in reversed(highs):
                if k - k1 > GAP_MAX:
                    break
                if k - k1 >= GAP_MIN:
                    if b[k]["h"] > b[k1]["h"] and rsi[k] < rsi[k1] and rsi[k1] >= OB:
                        e = b[i + 1]["o"]
                        if e < b[k]["h"] and not sig[i]:
                            sig[i], stopd[i] = -1, b[k]["h"] - e
                    break
            highs.append(k)
    return sig, stopd


def bt_walk(b, sig, stopdist, rr, start):
    out, i, n = [], start, len(b)
    while i < n - 1:
        d = sig[i]
        if not d or not stopdist[i]:
            i += 1; continue
        e = b[i + 1]["o"]; sd = stopdist[i]
        stop, tgt = e - d * sd, e + d * rr * sd
        j, px = i + 1, None
        while j < n:
            y = b[j]
            if d > 0:
                px = y["o"] if y["o"] <= stop else stop if y["l"] <= stop else max(tgt, y["o"]) if y["h"] >= tgt else None
            else:
                px = y["o"] if y["o"] >= stop else stop if y["h"] >= stop else min(tgt, y["o"]) if y["l"] <= tgt else None
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((round(e, 6), round(px, 6))); i = j + 1
    return out


for sym in ("ETHUSDT", "BTCUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "4h")[-1300:]]
    sig, sd = bt_signals(b)
    want = bt_walk(b, sig, sd, 2.0, 401)
    s = B.new_state("t"); s["seen"] = {sym: b[400]["t"]}
    for k in range(402, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) > 3, (sym, len(got))
    print(f"{sym}: {len(got)} trades match the backtest")
t = B.new_state("t"); t["seen"] = {"ETHUSDT": b[400]["t"]}
for k in range(402, len(b) + 1):
    P.step(t, "ETHUSDT", b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print("ok")
