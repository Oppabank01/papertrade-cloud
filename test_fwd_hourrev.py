"""fwd_hourrev.py walking 1h bars one at a time (the last one still forming) gives the same bets and outcomes as its
backtest fwd_hourrev.trades(), the function the backtest numbers in its LABEL came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hourrev as F, byttrade as B

SYM = "BTCUSDT"
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "1h")[-1300:]]
S0, n = 400, len(b)
want = [(x["t"], x["d"], x["win"]) for x in F.trades(b, first=S0 + 1)]
s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
s["cash"] = 1e6   # a losing run would otherwise skip bets for want of cash; this test is about the walk
for k in range(S0 + 2, n + 1):
    F.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x for x in s["log"] if x["kind"] == "sell"]
got = [(want[j][0], 1 if e["side"] == "up" else -1, p["px"] == 1.0) for j, (e, p) in enumerate(zip(buys, sells))]
assert [g[1:] for g in got] == [w[1:] for w in want[:len(got)]] and len(want) - len(got) <= 1, (len(got), len(want))
assert [e["t"] for e in buys[:len(got)]] == [B.iso(w[0]) for w in want[:len(got)]]
assert len(got) > 50, len(got)
v = s["cash"] + sum(p["qty"] * p["last"] for p in s["pos"].values())
w = sum(1 for g in got if g[2])
assert abs(v - (1e6 + s["start_usd"] * F.STAKE * (w / F.PX - len(got)))) < 1e-6, v
t = B.new_state("t"); t["seen"] = {SYM: b[S0]["t"]}
for k in range(S0 + 2, n + 1):
    F.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} bets match the backtest; ok")
