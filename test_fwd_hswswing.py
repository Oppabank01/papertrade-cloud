"""fwd_hswswing.py walking daily bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as its backtest fwd_hswswing.trades() on the full history (checked equal to the scout's
/tmp/scout_1015/bt.py trades() on BTC, ETH, SOL, BNB, XRP 2017-2026)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hswswing as F, byttrade as B

total = 0
for sym in ("BTCUSDT", "ETHUSDT"):
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d", max_age_h=24 * 30)]
    tr = F.trades(full)
    idx = {x["t"]: i for i, x in enumerate(full)}
    entries = [idx[t] for t, *_ in tr]
    start = len(full) - 2000
    # a start bar outside every trade: no entry within the longest trade (entry bar to fill = HOLD + 1 bars) before it
    while any(start - F.HOLD - 3 < j <= start + 1 for j in entries):
        start += 1
    want = [(round(e, 6), round(x, 6)) for t, e, x, _ in tr if idx[t] > start + 1]
    s = B.new_state("t"); s["seen"] = {sym: full[start]["t"]}
    for k in range(start + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, sym, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 8, len(got)
    total += len(got)
    print(f"{sym}: {len(got)} trades match the backtest")

t = B.new_state("t"); t["seen"] = {"BTCUSDT": full[-1200]["t"]}
for k in range(len(full) - 1198, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "BTCUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print("ok", total)
