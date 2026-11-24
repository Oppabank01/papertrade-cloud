"""fwd_ema1226.py walking daily bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as its backtest fwd_ema1226.trades() on the full history (checked equal to the scout's
/tmp/scout_0834/bt.py pos_trades(ema_pos) on BTC, ETH, SOL 2017-2026)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_ema1226 as F, byttrade as B

for sym in ("BTCUSDT", "SOLUSDT"):
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d", max_age_h=24 * 30)]
    up = F.above(full)
    start = next(j for j in range(len(full) - 1500, len(full)) if not up[j])   # flat after this bar's close
    want = [(round(e, 6), round(x, 6)) for t, e, x in F.trades(full) if t > full[start]["t"]]
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
assert any(x["kind"] == "sell" and x["why"] == "ถือครบ 35 วัน" for x in t["log"])
print("ok")
