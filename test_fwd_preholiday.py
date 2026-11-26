"""fwd_preholiday.py walking daily bars one day at a time, each time on only the last 1000 bars like byttrade.fetch
returns, gives the same entries and exits as its backtest fwd_preholiday.trades() (checked equal to the scout's
/tmp/scout_1902/bt.py on 2018 to Nov 2026 daily bars: BTC 93, ETH 93 trades). Data through mts.bars."""
import datetime as dt
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_preholiday as F, byttrade as B

assert F.nth_wd(2026, 11, 3, 4) == dt.date(2026, 11, 26)      # Thanksgiving
assert F.nth_wd(2026, 5, 0, -1) == dt.date(2026, 5, 25)       # Memorial Day
assert F.nth_wd(2026, 12, 0, -1) == dt.date(2026, 12, 28)
assert dt.date(2020, 6, 19) not in F.holidays(2020) and dt.date(2021, 6, 19) in F.holidays(2021)

total = 0
for sym in F.SYMS:
    full = [dict(x, closed=True) for x in mts.bars("binance", sym, "1d")]
    all_tr = F.trades(full)
    i0 = next(i for i in range(1000, len(full) - 1)
              if not any(et <= full[i + 1]["t"] <= et + 2 * F.DAY for et, e, x in all_tr) and not F.pre_holiday(full[i]["t"]))
    want = [(round(e, 8), round(x, 8)) for et, e, x in all_tr if et > full[i0 + 1]["t"]]

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
    assert len(got) >= 30, (sym, len(got))
    t = walk("random", 99)
    assert any(x["kind"] == "sell" for x in t["log"])
    total += len(got)
print(f"{total} trades over BTC ETH match the backtest; ok")
