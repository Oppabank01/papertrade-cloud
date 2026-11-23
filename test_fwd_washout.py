"""fwd_washout.py walking 15m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as the scout's backtest on the full history (/tmp/scout_2138.py washout(), copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_washout as F, byttrade as B


def trades(b):   # the backtest
    out, i, n = [], F.LOOK, len(b)
    while i < n - 1:
        if b[i]["c"] / b[i - F.LOOK]["c"] - 1 <= F.DROP:
            e, k = b[i + 1]["o"], i + 1
            while k < n - 1 and b[k]["c"] > e * (1 - F.STOP) and k - i < F.CAP:
                k += 1
            if k < n - 1:
                out.append((b[i + 1]["t"], e, b[k + 1]["o"]))
            i = k + 1
        else:
            i += 1
    return out


bars = mts.bars("binance", "SOLUSDT", "15m", max_age_h=24 * 30)
full = [dict(x, closed=True) for x in bars[-60000:]]
want_all = trades(full)
# walk only the stretch around the most recent backtest trades, so the test stays quick
first = want_all[-12][0]
start = next(j for j, x in enumerate(full) if x["t"] == first) - 1   # the signal bar of that trade
start -= 1                                                            # flat before it: the walk starts one bar earlier
want = [(round(e, 6), round(x, 6)) for t, e, x in want_all if t > full[start]["t"]]
s = B.new_state("t"); s["seen"] = {"SOLUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, "SOLUSDT", w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 10
t = B.new_state("t"); t["seen"] = {"SOLUSDT": full[-6000]["t"]}
for k in range(len(full) - 5998, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "SOLUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
