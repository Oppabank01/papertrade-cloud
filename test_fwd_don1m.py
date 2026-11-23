"""fwd_don1m.py walking 1m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as its backtest fwd_don1m.trades() (checked equal to the scout's /tmp/scout_0314/don.py run() on 90
days of ETH 1m bars). mts.bars would pull all 1m history since 2017, so this takes the last 6 days through mts.get."""
import random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_don1m as F, byttrade as B

SYM = "ETHUSDT"
start, raw = int((time.time() - 6 * 86400) * 1000), []
while True:
    k = mts.get(f"https://api.binance.com/api/v3/klines?symbol={SYM}&interval=1m&limit=1000&startTime={start}")
    raw += k
    if len(k) < 1000:
        break
    start = k[-1][0] + 1
full = [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), closed=True) for x in raw[:-1]]
want_all = F.trades(full)
# start the walk flat: the bar where the backtest closes a position without opening a new one
pos, ex = 0, None
for i in range(F.EN, len(full) - 1):
    w = F.want(full, i, pos)
    if w != pos:
        if pos and not w and i > 1500 and ex is None:
            ex = i
        pos = w
s = B.new_state("t"); s["seen"] = {SYM: full[ex]["t"]}
want = [(d, round(e, 6), round(x, 6)) for d, e, x in want_all]
k0 = next(j for j, (d, e, x) in enumerate(want_all) if round(x, 6) == round(full[ex + 1]["o"], 6)) + 1
want = want[k0:]
for k in range(ex + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, SYM, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(1 if e["side"] == "long" else -1, round(e["px"], 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) >= 8, len(got)
t = B.new_state("t"); t["seen"] = {SYM: full[-3000]["t"]}
for k in range(len(full) - 2998, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(t, SYM, w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
