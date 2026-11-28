"""fwd_rot5.py walking daily bars one day at a time gives the same holding segments (coin, side, entry, exit) as its
backtest fwd_rot5.segments(), the function the backtest numbers in the scout's feed came from."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_rot5 as F, byttrade as B

px = {c: {x["t"]: x["o"] for x in mts.bars("binance", c + "USDT", "1d")[-1000:]} for c in F.COINS}
days = sorted(px["BTC"])
start = days[F.LOOK + 5]
want = sorted((c, d, round(px[c][a], 8), round(px[c][b], 8)) for c, d, a, b in F.segments(px, start))
s = B.new_state("t"); s["seen"] = start
for k in range(F.LOOK + 6, len(days) + 1):
    cut = set(days[:k])
    F.step(s, {c: {t: v for t, v in p.items() if t in cut} for c, p in px.items()}, "rule", random.Random(1))
F.step(s, px, "rule", random.Random(1))                 # running again books nothing new
buys = {}
got = []
for x in s["log"]:
    if x["kind"] == "buy":
        buys[x["coin"]] = x
    else:
        e = buys.pop(x["coin"])
        got.append((x["coin"], 1 if x["side"] == "long" else -1, round(e["px"], 8), round(x["px"], 8)))
got.sort()
assert got == want, (len(got), len(want), got[:3], want[:3])
assert len(got) > 50 and {d for _, d, _, _ in got} == {1, -1}, len(got)
assert {c: p["d"] for c, p in s["pos"].items()} == F.pick(px, F.reviews_after(start, px)[-1]), s["pos"].keys()
t = B.new_state("t"); t["seen"] = start
F.step(t, px, "random", random.Random(3))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} segments match the backtest; ok")
