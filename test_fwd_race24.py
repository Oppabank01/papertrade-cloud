"""fwd_race24.py walking 5m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as its backtest fwd_race24.trades() (checked equal to the scout's /tmp/scout_1719/bt2.py on 365 days
of 5m bars: BTC 371 legs, SOL 405 legs). mts.bars would pull all 5m history since 2017, so this takes the last 8 days
through mts.get."""
import random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_race24 as F, byttrade as B

SYM = "BTCUSDT"
start, raw = int((time.time() - 8 * 86400) * 1000), []
while True:
    k = mts.get(f"https://api.binance.com/api/v3/klines?symbol={SYM}&interval=5m&limit=1000&startTime={start}")
    raw += k
    if len(k) < 1000:
        break
    start = k[-1][0] + 1
full = [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), closed=True) for x in raw[:-1]]
all_tr = F.trades(full)
d0 = next(i for i, x in enumerate(full) if x["t"] % F.DAY == 0 and i >= 1000)   # start the walk flat at a race start
want = [(round(e, 6), round(px, 6)) for et, e, xt, px in all_tr if et > full[d0]["t"]]
s = B.new_state("t"); s["seen"] = {SYM: full[d0 - 1]["t"]}
for k in range(d0 + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, SYM, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got[:len(want)] == want and len(got) - len(want) <= 2, (len(got), len(want), got[:3], want[:3])
assert len(want) >= 3, len(want)
t = B.new_state("t"); t["seen"] = {SYM: full[-1500]["t"]}
for k in range(len(full) - 1498, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, SYM, w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(want)} trades match the backtest; ok")
