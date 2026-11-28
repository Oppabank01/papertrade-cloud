"""fwd_xsrsi.py walking daily bars one at a time gives the same trades as the scout's backtest (/tmp/scout_0801/bt.py run())."""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_xsrsi as F, byttrade as B

DAY = F.DAY


def backtest(data):   # copy of bt.py run(), rule mode
    grid = sorted({t for d in data.values() for t in d})
    hist = {c: [] for c in data}
    pos, free, trades = {}, {}, []

    def out(c, t, px):
        p = pos.pop(c)
        trades.append((c, round(p["e"], 8), round(px, 8)))

    for k, t in enumerate(grid):
        sc = {}
        for c, d in data.items():
            if t in d and t - DAY in d and len(hist[c]) >= 15:
                v = F.rsi(hist[c])
                if v is not None:
                    sc[c] = v
        order = sorted(sc, key=lambda c: -sc[c]) if len(sc) >= F.MINU else []
        top, bot = order[:F.K], order[::-1][:F.K]
        for c in list(pos):
            p = pos[c]
            if t not in data[c]:
                continue
            age = k - p["k"]
            if age >= F.MAXH or (age >= F.HOLD and c not in (top if p["d"] > 0 else bot)):
                out(c, t, data[c][t]["o"]); free[c] = t + 2 * DAY
        if order:
            for side, lst in ((1, order), (-1, order[::-1])):
                n = sum(1 for p in pos.values() if p["d"] == side)
                for c in [c for c in lst if free.get(c, 0) <= t][:F.K]:
                    if n >= F.K:
                        break
                    if c in pos:
                        continue
                    pos[c] = dict(d=side, e=data[c][t]["o"], k=k, tp=F.tp_of(hist[c])); n += 1
        for c in list(pos):
            if t not in data[c]:
                continue
            x, p = data[c][t], pos[c]
            d, e = p["d"], p["e"]
            stop, tgt = e * (1 - d * F.STOP), (None if p["tp"] is None else e * (1 + d * p["tp"]))
            if d > 0:
                px = x["o"] if x["o"] <= stop else stop if x["l"] <= stop else (max(tgt, x["o"]) if tgt and x["h"] >= tgt else None)
            else:
                px = x["o"] if x["o"] >= stop else stop if x["h"] >= stop else (min(tgt, x["o"]) if tgt and x["l"] <= tgt else None)
            if px is not None:
                out(c, t, px); free[c] = t + 3 * DAY
        for c, d in data.items():
            if t in d:
                hist[c].append(d[t]["c"])
    return trades


raw = {c: mts.bars("binance", c + "USDT", "1d", max_age_h=48)[:-1] for c in F.COINS}
cut = raw["BTC"][-400]["t"]
raw = {c: [dict(x, closed=True) for x in b if x["t"] >= cut] for c, b in raw.items()}
want = backtest({c: {x["t"]: x for x in b} for c, b in raw.items()})
grid = sorted({x["t"] for b in raw.values() for x in b})


def walk(mode, seed):
    s = B.new_state("t"); s["free"] = {}; s["seen"] = s["opened"] = grid[0] - DAY
    rng = random.Random(seed)
    for k in range(1, len(grid) + 1):
        now = {c: [x for x in b if x["t"] < grid[k - 1]] + [dict(x, closed=False) for x in b if x["t"] == grid[k - 1]] for c, b in raw.items()}
        F.step(s, {c: b for c, b in now.items() if b}, mode, rng)
    F.step(s, raw, mode, rng)
    return s


s = walk("rule", 1)
buys = {}
got = []
for x in s["log"]:
    if x["kind"] == "buy":
        buys[x["coin"]] = x["px"]
    else:
        got.append((x["coin"], round(buys.pop(x["coin"]), 8), round(x["px"], 8)))
assert sorted(got) == sorted(want), (len(got), len(want), sorted(set(got) ^ set(want))[:4])
assert len(got) > 50
t = walk("random", 2)
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{len(got)} trades match the backtest; ok")
