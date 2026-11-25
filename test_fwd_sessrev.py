"""fwd_sessrev.py walking 12h bars one at a time (the last one still forming, a 200-bar window like a live fetch)
gives the same trades as its backtest fwd_sessrev.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_sessrev as F, byttrade as B

SYM, WIN = "SOLUSDT", 200
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "12h")]
S0, n = len(b) - 1500, len(b)
want = [(d, round(e, 6), round(x, 6)) for t, d, e, x in F.trades(b) if t > b[S0 + 1]["t"] and t < b[-1]["t"]]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[max(0, k - WIN):k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [(1 if x["side"] == "long" else -1, x["px"]) for x in s["log"] if x["kind"] == "buy"]
sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(d, round(e, 6), round(p, 6)) for (d, e), p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 100, len(got)
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[max(0, k - WIN):k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert sum(x["kind"] == "sell" for x in t["log"]) == len(got)
print(f"{len(got)} trades match the backtest; ok")
