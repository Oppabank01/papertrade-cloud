"""fwd_hull.py walking daily bars one day at a time, each time on only the last 1000 bars like byttrade.fetch returns,
gives the same entries and exits as its backtest fwd_hull.trades() (checked equal to the scout's /tmp/scout_0546/bt_hma.py
on Aug 2017 to Nov 2026 daily bars: BTC 107, ETH 99 trades). Data through mts.bars; the walk starts at a day when the
backtest holds nothing."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hull as F, byttrade as B

total = 0
for sym in F.SYMS:
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d")]
    all_tr = F.trades(full)
    assert len(all_tr) >= 50, (sym, len(all_tr))
    i0 = next(i for i in range(1000, len(full) - 1)
              if not any(et <= full[i + 1]["t"] and xt > full[i]["t"] for et, e, xt, x in all_tr))
    want = [(round(e, 8), round(x, 8)) for et, e, xt, x in all_tr if et > full[i0 + 1]["t"]]

    def walk(mode, seed):
        st = B.new_state("t"); st["seen"] = {sym: full[i0]["t"]}
        for k in range(i0 + 2, len(full) + 1):
            w = full[max(0, k - 1000):k]
            F.step(st, sym, w[:-1] + [dict(w[-1], closed=False)], mode, random.Random(seed + k))
        return st

    s = walk("rule", 1)
    got, last = [], None
    for x in s["log"]:
        if x["kind"] == "buy":
            last = x["px"]
        else:
            got.append((round(last, 8), round(x["px"], 8)))
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 20, (sym, len(got))
    t = walk("random", 99)
    assert any(x["kind"] == "sell" for x in t["log"])
    total += len(got)
print(f"{total} trades over BTC ETH match the backtest; ok")
