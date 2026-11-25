"""fwd_emarot.py walking 1h bars of all 7 coins one hour at a time, each time on only the last 1000 bars like
byttrade.fetch returns, gives the same entries and exits as its backtest fwd_emarot.trades() (checked equal to the
scout's /tmp/scout_0546/bt_ema.py on Mar 2024 to Nov 2026 1h bars: 2,338 trades). This takes the last 75 days through mts.get
and starts the walk at an hour when the backtest holds nothing."""
import random, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_emarot as F, byttrade as B

raw = {}
for sym in F.SYMS:
    start, k_all = int((time.time() - 75 * 86400) * 1000), []
    while True:
        k = mts.get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&limit=1000&startTime={start}")
        k_all += k
        if len(k) < 1000:
            break
        start = k[-1][0] + 1
    raw[sym] = [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]), c=float(x[4]), closed=True) for x in k_all[:-1]]
full = F.align(raw)
ref = full[F.SYMS[0]]
all_tr = F.trades(full)
i0 = next(i for i in range(1000, len(ref) - 1)
          if not any(et <= ref[i + 1]["t"] and xt > ref[i]["t"] for s, et, e, xt, x in all_tr))
want = sorted((s[:-4], et, round(e, 8), round(x, 8)) for s, et, e, xt, x in all_tr if et > ref[i0 + 1]["t"])


def walk(mode, seed):
    st = B.new_state("t"); st["seen"] = ref[i0]["t"]
    for k in range(i0 + 2, len(ref) + 1):
        w = {s: b[max(0, k - 1000):k] for s, b in full.items()}
        w = {s: b[:-1] + [dict(b[-1], closed=False)] for s, b in w.items()}
        F.step(st, w, mode, random.Random(seed + k))
    return st


s = walk("rule", 1)
pairs, open_ = [], {}
for x in s["log"]:
    if x["kind"] == "buy":
        open_[x["coin"]] = x["px"]
    else:
        pairs.append((x["coin"], round(open_.pop(x["coin"]), 8), round(x["px"], 8)))
assert sorted(p for p in pairs) == sorted((c, e, x) for c, et, e, x in want), (len(pairs), len(want), pairs[:3], want[:3])
assert len(pairs) >= 30, len(pairs)
t = walk("random", 99)
assert any(x["kind"] == "sell" for x in t["log"])
assert all(len([1 for x in t["log"][:k + 1] if x["kind"] == "buy"]) - len([1 for x in t["log"][:k + 1] if x["kind"] == "sell"]) <= F.NAMES
           for k in range(len(t["log"])))
print(f"{len(pairs)} trades over 7 coins match the backtest; ok")
