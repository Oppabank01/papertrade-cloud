"""fwd_trendpilot.py walking daily bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns,
gives the same entries and exits as its backtest fwd_trendpilot.trades() on the full history (the scout's
/tmp/scout_1343/bt.py runs that same function on BTC, ETH, SOL, BNB, XRP 2017-2026)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_trendpilot as F, byttrade as B

for sym in ("BTCUSDT", "ETHUSDT"):
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d", max_age_h=24 * 30)]
    tr = F.trades(full)
    busy = set()                      # bars where the backtest holds a position or exits
    for et, e, x, xt in tr:
        busy |= {y["t"] for y in full if et - B.DAY <= y["t"] <= xt}
    # first walked bar: flat in the backtest, so both start flat and judge the same signal there
    start = next(i for i in range(len(full) - 1500, len(full)) if full[i + 1]["t"] not in busy and full[i]["t"] not in busy)
    want = [(round(e, 6), round(x, 6)) for et, e, x, xt in tr if et > full[start + 1]["t"]]
    s = B.new_state("t"); s["seen"] = {sym: full[start]["t"]}
    for k in range(start + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, sym, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
    buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 15, len(got)
    print(f"{sym}: {len(got)} trades match the backtest")

t = B.new_state("t"); t["seen"] = {"BTCUSDT": full[-800]["t"]}
for k in range(len(full) - 798, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "BTCUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print("ok")
