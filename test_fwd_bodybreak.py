"""fwd_bodybreak.py walking 1h bars one at a time (a 1000-bar window as byttrade.fetch returns, the last bar still
forming) gives the same entries and exits as its backtest fwd_bodybreak.trades(), the function the backtest numbers in its
LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_bodybreak as F, byttrade as B

SYM, W = "BTCUSDT", 1000
hb = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1h")]
n = len(hb)
S0 = n - 24 * 500
s = B.new_state("t"); s["seen"] = {}
F.step(s, SYM, hb[S0 - W:S0 - 1] + [dict(hb[S0 - 1], closed=False)], "rule", random.Random(1))
seen0 = s["seen"][SYM]
for k in range(S0 + 1, n + 1):
    F.step(s, SYM, hb[k - W:k - 1] + [dict(hb[k - 1], closed=False)], "rule", random.Random(1))
want = [(round(x["e"], 6), round(x["x"], 6)) for x in F.trades(hb) if x["t"] >= seen0 + B.DAY]
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e["px"], 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 5, len(got)
t = B.new_state("t"); t["seen"] = {}
F.step(t, SYM, hb[S0 - W:S0 - 1] + [dict(hb[S0 - 1], closed=False)], "random", random.Random(0))
for k in range(S0 + 1, n + 1, 1):
    F.step(t, SYM, hb[k - W:k - 1] + [dict(hb[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
