"""fwd_memeregime.py walking 15m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives
the same entries and exits as its backtest fwd_memeregime.trades() on the full history (the function the backtest numbers in
its LABEL came from)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_memeregime as F, byttrade as B

SYM = "WIFUSDT"
full = [dict(x, closed=True) for x in mts.bars("binance", SYM, "15m", max_age_h=24 * 30)[-20000:]]
want_all = F.trades(full)
# walk only the last 3000 bars, so the test stays quick; start flat right after a backtest exit
start = len(full) - 3000
ex = next(k for k in range(start, len(full)) if F.signal(full, k) == 0 and F.signal(full, k - 1) != 0)
s = B.new_state("t"); s["seen"] = {SYM: full[ex]["t"]}
s["cash"] = 1e9   # hundreds of losing trades would drain the cash and skip longs; the backtest has no cash limit
want = [(x["d"], round(x["e"], 6), round(x["x"], 6)) for x in want_all if x["t"] > full[ex + 1]["t"]]
for k in range(ex + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, SYM, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(1 if e["side"] == "long" else -1, round(e["px"], 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 50, len(got)
assert any(x["side"] == "short" for x in buys)
t = B.new_state("t"); t["seen"] = {SYM: full[-2000]["t"]}
for k in range(len(full) - 1998, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, SYM, w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
