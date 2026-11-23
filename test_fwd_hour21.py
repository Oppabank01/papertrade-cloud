"""fwd_hour21.py walking 1h bars one at a time (the last one still forming) gives the same trades as its backtest
fwd_hour21.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hour21 as F, byttrade as B

SYM = "BTCUSDT"
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1h")[-1300:]]
S0, n = 400, len(b)
bt = F.trades(b, first=S0 + 1)
assert all(F.hour(e_t) == 21 and F.hour(x_t) == 23 for e_t, _, x_t, _ in bt)
want = [(round(e, 6), round(x, 6)) for _, e, _, x in bt]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 20, len(got)
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
