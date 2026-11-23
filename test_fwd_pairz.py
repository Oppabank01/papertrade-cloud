"""fwd_pairz.py walking daily bars one at a time (the last one still forming) gives the same entries and exits as its
backtest fwd_pairz.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_pairz as F, byttrade as B

SYM = "ETHBTC"
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1d")[-1500:]]
S0, n = 60, len(b)
want = [(x["d"], round(x["e"], 9), round(x["x"], 9)) for x in F.trades(b, first=S0 + 1)]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(1 if e["side"] == "long" else -1, round(e["px"], 9), round(p, 9)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 20, len(got)
assert any(x["side"] == "short" for x in buys) and any(x["side"] == "long" for x in buys)
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
