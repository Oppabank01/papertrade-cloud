"""fwd_zlemamart.py walking bars one at a time gives the same entries, exits and ladder levels as the scout's backtest
(/tmp/scout_0844/zl_bt.py run()) on the same bars."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_zlemamart as Z, byttrade as B

SYM = "LTCUSDT"                      # a coin with a 3-level ladder
b = [dict(x, closed=True) for x in mts.bars("binance", SYM, "4h")[-1300:]]
fast, slow, sl, rr, top = Z.CONFIG[SYM]
trend, atr = Z.ind(b, fast, slow)
want, pos, level, wd, n = [], None, 0, 0, len(b)
for i in range(401, n - 1):
    if trend[i] == 0:
        continue
    x = b[i]
    if pos and i >= pos["ei"]:
        if pos["d"] > 0:
            px = min(x["o"], pos["stop"]) if x["l"] <= pos["stop"] else pos["tgt"] if x["h"] >= pos["tgt"] else None
        else:
            px = max(x["o"], pos["stop"]) if x["h"] >= pos["stop"] else pos["tgt"] if x["l"] <= pos["tgt"] else None
        if px is not None:
            want.append((round(pos["entry"], 6), round(px, 6), level))
            stopped = (px - pos["entry"]) * pos["d"] < 0 or px == pos["stop"]
            level, wd = (level + 1, pos["d"]) if stopped and level < top else (0, 0)
            pos = None
            continue
    if pos:
        continue
    if wd:
        if trend[i] != wd:
            continue
        d, wd = wd, 0
    elif trend[i - 1] and trend[i] != trend[i - 1]:
        d, level = trend[i], 1
    else:
        continue
    e = b[i + 1]["o"]
    pos = dict(d=d, entry=e, ei=i + 1, stop=e - d * sl * atr[i], tgt=e + d * sl * rr * atr[i])

s = B.new_state("t"); s["seen"] = {SYM: b[400]["t"]}
for k in range(402, n + 1):
    Z.step(s, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x for x in s["log"] if x["kind"] == "sell"]
got = [(round(a["px"], 6), round(z["px"], 6), round(a["usd"] / (s["start_usd"] * Z.BASE))) for a, z in zip(buys, sells)]
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 5 and any(lv > 1 for *_, lv in got), got
t = B.new_state("t"); t["seen"] = {SYM: b[400]["t"]}
for k in range(402, n + 1):
    Z.step(t, SYM, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest ({sum(lv > 1 for *_, lv in got)} ladder re-entries); ok")
