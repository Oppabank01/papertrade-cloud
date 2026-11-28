"""fwd_d3trail.py walking daily bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as its backtest fwd_d3trail.trades() on the full history (checked equal to the scout's
/tmp/scout_1614/d3.py run() on the 8 coins 2017-2026)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_d3trail as F, byttrade as B

total = 0
for sym in ("BTCUSDT", "ETHUSDT", "ADAUSDT", "LINKUSDT"):
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d", max_age_h=24 * 30)]
    tr = F.trades(full)
    idx = {x["t"]: k for k, x in enumerate(full)}
    t1 = next(t for t, _, _ in tr if idx[t] >= len(full) - 1600)
    start = idx[t1] - 2                # one bar before the signal bar: flat (no signal on or before the exit bar)
    want = [(round(e, 6), round(x, 6)) for t, e, x in tr if t >= t1]
    s = B.new_state("t"); s["seen"] = {sym: full[start]["t"]}
    for k in range(start + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, sym, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
    print(f"{sym}: {len(got)} trades match the backtest")
assert total >= 8, total

t = B.new_state("t"); t["seen"] = {"BTCUSDT": full[-800]["t"]}
for k in range(len(full) - 798, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "BTCUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "buy" for x in t["log"])
print("ok")
