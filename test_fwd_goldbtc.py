"""fwd_goldbtc.py walking 4h bars one at a time (the last one still forming) gives the same entries and exits as its
backtest fwd_goldbtc.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_goldbtc as F, byttrade as B

raw = {s: {x["t"]: x for x in mts.bars("binance", s, "4h")} for s in F.SYMS}
ts = sorted(set(raw["BTCUSDT"]) & set(raw["PAXGUSDT"]))[-8000:]
b = {s: [dict(raw[s][t], closed=True) for t in ts] for s in F.SYMS}
S0, n = 400, len(ts)
s = B.new_state("t"); s["seen"] = {"DM": ts[S0]}
for k in range(S0 + 2, n + 1):
    F.step(s, {sy: v[:k - 1] + [dict(v[k - 1], closed=False)] for sy, v in b.items()}, "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(e["coin"] + "USDT", round(e["px"], 6), round(p, 6)) for e, p in zip(buys, sells)]
# the walk starts flat while the backtest may already hold that coin, so compare from the walk's second buy on
t1 = next(t for t in ts if B.iso(t) == buys[1]["t"])
got = got[1:]
want = [(x["sym"], round(x["e"], 6), round(x["x"], 6)) for x in F.trades(b) if x["t"] >= t1]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 8, len(got)
t = B.new_state("t"); t["seen"] = {"DM": ts[S0]}
for k in range(S0 + 2, n + 1):
    F.step(t, {sy: v[:k - 1] + [dict(v[k - 1], closed=False)] for sy, v in b.items()}, "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
