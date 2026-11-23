"""fwd_dst.py walking 1h bars one at a time, each time on only the last 1000 bars like byttrade.fetch returns, gives the
same entries and exits as the scout's backtest on the full history (/tmp/scout_1949.py dst_trades(), copied below)."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_dst as F, byttrade as B


def trades(b):   # the backtest
    fd, sd = F.supertrend(b, F.FAST), F.supertrend(b, F.SLOW)
    out, pos = [], None
    for i in range(1, len(b) - 1):
        if fd[i] is None or sd[i] is None:
            continue
        both = fd[i] == -1 and sd[i] == -1
        prev = fd[i - 1] == -1 and sd[i - 1] == -1
        if pos is None and both and not prev:
            pos = (b[i + 1]["t"], b[i + 1]["o"])
        elif pos is not None and fd[i] == 1:
            out.append((pos[0], pos[1], b[i + 1]["o"]))
            pos = None
    return out


full = [dict(x, closed=True) for x in mts.bars("binance", "SOLUSDT", "1h", max_age_h=240)[-5000:]]
start = 2000                    # the walk starts here; the backtest sees all bars before it as warm-up
fd = F.supertrend(full, F.FAST)
while fd[start] != 1:           # start where the fast line points down, so the backtest is flat there too
    start += 1
want = [(round(e, 6), round(x, 6)) for t, e, x in trades(full) if t > full[start]["t"]]
s = B.new_state("t"); s["seen"] = {"SOLUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1):
    w = full[max(0, k - 1000):k]
    F.step(s, "SOLUSDT", w[:-1] + [dict(w[-1], closed=False)], "rule", random.Random(1))
buys = [x["px"] for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
got = [(round(e, 6), round(p, 6)) for e, p in zip(buys, sells)]
assert got == want[:len(got)] and len(want) - len(got) <= 1, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5
t = B.new_state("t"); t["seen"] = {"SOLUSDT": full[start]["t"]}
for k in range(start + 2, len(full) + 1, 1):
    w = full[max(0, k - 1000):k]
    F.step(t, "SOLUSDT", w[:-1] + [dict(w[-1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
