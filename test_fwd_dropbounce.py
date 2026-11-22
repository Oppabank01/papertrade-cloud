"""fwd_dropbounce.py walking daily bars one at a time (the last one still forming) gives the same entries and exits as its
backtest fwd_dropbounce.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_dropbounce as F, byttrade as B

SYM, S0 = "ETHUSDT", 400
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1d")]
n = len(b)
want = [(round(x["e"], 6), round(x["x"], 6)) for x in F.trades(b, first=S0 + 1)]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
s["cash"] = 1e6   # a losing run would otherwise skip longs for want of cash; this test is about the walk
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5, len(got)
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
