"""fwd_obsmc.py walking 4h bars one at a time (the last one still forming) gives the same entries and exits as its
backtest fwd_obsmc.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_obsmc as F, byttrade as B

SYM = "ETHUSDT"
full = [dict(x, closed=True) for x in mts.bars("binance", SYM, "4h")]
b = full[-3000:]
S0, n = 400, len(b)
want = [(round(e, 6), round(x, 6)) for _, e, _, x in F.trades(b, first=S0 + 1)]
s = B.new_state("t"); s["seen"] = {}
F.step(s, SYM, b[:S0 + 1] + [dict(b[S0 + 1], closed=False)], "rule", random.Random(1))   # first sight: seen = bar S0
assert s["seen"][SYM] == b[S0]["t"]
s["cash"] = 1e6   # a losing run would otherwise skip buys for want of cash; this test is about the walk
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 10, len(got)
# the 1000-bar window cron sees gives the same trades as full history once LOOK + a few bars have passed
w = F.trades(full[-1000:])
t0 = full[-1000 + F.LOOK + 20]["t"]
assert [x for x in w if x[0] >= t0] == [x for x in F.trades(full) if x[0] >= t0]
t = B.new_state("t"); t["seen"] = {}
F.step(t, SYM, b[:S0 + 1] + [dict(b[S0 + 1], closed=False)], "random", random.Random(0))
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
