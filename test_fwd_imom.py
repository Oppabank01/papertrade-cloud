"""fwd_imom.py walking 1h bars one at a time (the last one still forming) gives the same trades as its backtest
fwd_imom.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_imom as F, byttrade as B

SYM = "ETHUSDT"
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1h")[-3000:]]
S0, n = 400, len(b)
bt = F.trades(b, first=S0 + 1)
assert all(F.hour(e_t) == 23 for e_t, _, _, _ in bt)
want = [(round(e, 6), round(x, 6), d) for _, e, x, d in bt]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e["px"], 6), round(p, 6), 1 if e["side"] == "long" else -1) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5 and {d for _, _, d in got} == {1, -1}, got
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
