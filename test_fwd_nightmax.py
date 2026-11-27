"""fwd_nightmax.py walking 1h bars one at a time (the last one still forming) gives the same trades as the scout's
backtest (/tmp/scout_0255/bt.py trades(filt="daily"), copied below with its own New York clock)."""
import random, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_nightmax as F, byttrade as B


def ny(t):
    u = datetime.fromtimestamp(t / 1000, timezone.utc)
    mar = datetime(u.year, 3, 8, 7, tzinfo=timezone.utc); mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(u.year, 11, 1, 6, tzinfo=timezone.utc); nov += timedelta(days=(6 - nov.weekday()) % 7)
    return u + timedelta(hours=-4 if mar <= u < nov else -5)


def trades(b, first):
    c = [x["c"] for x in b]
    out, i, n = [], first, len(b)
    while i < n - 1:
        d = ny(b[i + 1]["t"])
        if d.hour != 16 or d.weekday() not in (4, 0, 1) or not c[i] >= max(c[i - 24 * k] for k in range(1, 11)):
            i += 1; continue
        e_t, e, j = b[i + 1]["t"], b[i + 1]["o"], i + 1
        while j < n - 1:
            dj = ny(b[j + 1]["t"])
            if dj.hour == 10 and dj.weekday() < 5 and b[j + 1]["t"] > e_t:
                break
            j += 1
        if j >= n - 1:
            break
        out.append((e, b[j + 1]["o"], ny(e_t).weekday(), ny(b[j + 1]["t"]).weekday()))
        i = j
    return out


SYM = "BTCUSDT"
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1h")[-4000:]]
S0, n = 300, len(b)
bt = trades(b, S0 + 1)
assert all((ew, xw) in ((4, 0), (0, 1), (1, 2)) for _, _, ew, xw in bt), bt
want = [(round(e, 6), round(x, 6)) for e, x, _, _ in bt]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5, len(got)
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
