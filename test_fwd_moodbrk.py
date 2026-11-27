"""fwd_moodbrk.py walking 4h bars one at a time gives the same entries and exits as the scout's backtest
(/tmp/scout_1144/bt.py moods(), atr() and trades(), copied below) on the same bars, and the mood computed from the
1000 daily bars byttrade.fetch returns equals the full-history mood on recent days."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_moodbrk as P, byttrade as B

H4, DAY = 4 * 3600 * 1000, 86400 * 1000


def bt_ema_above(d, n=20):
    out, e, a = {}, None, 2 / (n + 1)
    for i, x in enumerate(d):
        if i < n - 1:
            continue
        e = sum(y["c"] for y in d[:n]) / n if i == n - 1 else e + a * (x["c"] - e)
        out[x["t"]] = x["c"] > e
    return out


def bt_moods(daily):
    ab = {s: bt_ema_above(d) for s, d in daily.items()}
    days = sorted(set().union(*[set(v) for v in ab.values()]))
    out = {}
    for t in days:
        v = [ab[s][t] for s in ab if t in ab[s]]
        if "BTCUSDT" not in daily or t not in ab["BTCUSDT"] or len(v) < 3:
            continue
        br, btc = sum(v) / len(v), ab["BTCUSDT"][t]
        out[t] = "weak" if br < 0.35 and not btc else "hot" if br > 0.65 and btc else "neutral"
    return out


def bt_mood_of(mood, t):
    return mood.get(((t + H4) // DAY) * DAY - DAY)


def bt_atr(b, n=14):
    out, a = [None] * len(b), 0.0
    for i in range(1, len(b)):
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
        a = tr if i == 1 else (a * (n - 1) + tr) / n
        if i >= n:
            out[i] = a
    return out


def bt_trades(b, mood, k=2.0, start=0):
    a, out, i, n = bt_atr(b), [], max(start, 34), len(b)
    while i < n - 1:
        x = b[i]
        if bt_mood_of(mood, x["t"]) != "neutral" or not a[i] or not x["c"] > max(y["h"] for y in b[i - 20:i]):
            i += 1; continue
        e = b[i + 1]["o"]; stop = e - k * a[i]; tgt = e + 6 * k * a[i]
        px, j = None, i + 1
        while j < n:
            y = b[j]
            px = y["o"] if y["o"] <= stop else stop if y["l"] <= stop else max(tgt, y["o"]) if y["h"] >= tgt else None
            if px is None and j - (i + 1) == 59:
                px = y["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append((round(e, 6), round(px, 6))); i = j + 1
    return out


daily = {s: mts.bars("binance", s, "1d") for s in P.SYMS}
full = bt_moods(daily)
win = P.moods({s: d[-1000:] for s, d in daily.items()})
recent = sorted(full)[-500:]
assert all(win.get(t) == full[t] for t in recent), sum(win.get(t) != full[t] for t in recent)
assert P.moods({s: d for s, d in daily.items()}) == full

total = 0
for sym in ("ETHUSDT", "LINKUSDT", "BTCUSDT"):
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "4h")[-2400:]]
    want, n = bt_trades(b, full, start=401), len(b)
    s = B.new_state("t"); s["seen"] = {sym: b[400]["t"]}
    for k in range(402, n + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], full, "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
    t = B.new_state("t"); t["seen"] = {sym: b[400]["t"]}
    for k in range(402, n + 1):
        P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], full, "random", random.Random(k))
    assert any(x["kind"] == "sell" for x in t["log"])
assert total > 5
print(f"{total} trades match the backtest; mood from 1000 days matches on {len(recent)} days; ok")
