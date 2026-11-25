"""fwd_mmom.py walking 30m bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as its backtest fwd_mmom.trades() (checked equal to the scout's /tmp/scout_1719/bt.py mmom with
thr 0 on both sides over 2020-2026 30m bars). This takes the last 45 days through mts.get."""
import random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_mmom as F, byttrade as B

for SYM in ("PAXGUSDT", "BTCUSDT"):
    start, raw = int((time.time() - 45 * 86400) * 1000), []
    while True:
        k = mts.get(f"https://api.binance.com/api/v3/klines?symbol={SYM}&interval=30m&limit=1000&startTime={start}")
        raw += k
        if len(k) < 1000:
            break
        start = k[-1][0] + 1
    full = [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), closed=True) for x in raw[:-1]]
    i0 = 1000
    want = [(d, round(e, 6), round(px, 6)) for t, d, e, px in F.trades(full) if t > full[i0]["t"]]
    s = B.new_state("t"); s["seen"] = {SYM: full[i0]["t"]}
    for k in range(i0 + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(s, SYM, w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
    buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(1 if b["side"] == "long" else -1, round(b["px"], 6), round(p, 6)) for b, p in zip(buys, sells)]
    assert got == want[:len(got)] and len(want) - len(got) <= 1, (SYM, len(got), len(want), got[:3], want[:3])
    assert len(got) >= 10, len(got)
    t = B.new_state("t"); t["seen"] = {SYM: full[i0]["t"]}
    for k in range(i0 + 2, len(full) + 1):
        w = full[max(0, k - 1000):k]
        F.step(t, SYM, w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
    assert any(x["kind"] == "sell" for x in t["log"])
    print(f"{SYM} {len(got)} trades match the backtest")
print("ok")
