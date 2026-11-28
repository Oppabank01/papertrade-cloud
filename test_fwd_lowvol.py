"""fwd_lowvol.py walking daily bars one at a time gives the same weekly trades as the scout's backtest (/tmp/scout_1121/bt.py run())."""
import random, sys, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_lowvol as F, byttrade as B

DAY = F.DAY


def backtest(data, sig):   # copy of bt.py run(), rule mode: (monday, coin, side, open-to-open return)
    grid = sorted({t for d in data.values() for t in d})
    mondays = [t for t in grid if (t // DAY + 3) % 7 == 0]
    out = []
    for a, b in zip(mondays, mondays[1:]):
        el = {}
        for c, d in data.items():
            if a not in d or b not in d or not all(a - j * DAY in d for j in range(1, F.LOOK + 2)):
                continue
            el[c] = sig([d[a - j * DAY]["c"] for j in range(F.LOOK + 1, 0, -1)])
        if len(el) < F.MINU:
            continue
        k = len(el) // 3
        order = sorted(el, key=lambda c: el[c])
        for side, lst in ((1, order[:k]), (-1, order[-k:])):
            out += [(a, c, side, round(side * (data[c][b]["o"] / data[c][a]["o"] - 1), 6)) for c in lst]
    return out


def walk(raw, grid, mode, seed, sig):
    s = B.new_state("t"); s["seen"] = grid[0] - DAY
    rng = random.Random(seed)
    for t in grid:
        now = {c: [x for x in b if x["t"] < t] + [dict(x, closed=False) for x in b if x["t"] == t] for c, b in raw.items()}
        F.step(s, {c: b for c, b in now.items() if b}, mode, rng, sig)
    F.step(s, raw, mode, rng, sig)                     # a second pass books nothing new
    return s


def check(sig, name):
    raw = {c: mts.bars("binance", c + "USDT", "1d", max_age_h=48)[:-1] for c in F.COINS}
    cut = raw["BTC"][-400]["t"]
    raw = {c: [dict(x, closed=True) for x in b if x["t"] >= cut] for c, b in raw.items()}
    data = {c: {x["t"]: x for x in b} for c, b in raw.items()}
    want = backtest(data, sig)
    grid = sorted({x["t"] for b in raw.values() for x in b})
    s = walk(raw, grid, "rule", 1, sig)
    side = {"long": 1, "short": -1}
    got = []
    for x in s["log"]:
        if x["kind"] == "sell":
            a = round(B.datetime.fromisoformat(x["t"]).timestamp() * 1000) - 7 * DAY
            got.append((a, x["coin"], side[x["side"]], x["ret"]))
    first = min(t for t, *_ in want)
    assert sorted(got) == sorted(want), (len(got), len(want), sorted(set(got) ^ set(want))[:4])
    assert len(got) > 300, len(got)
    eq = s["cash"] + sum(p["qty"] * p["last"] for p in s["pos"].values())
    t = walk(raw, grid, "random", 2, sig)
    assert any(x["kind"] == "sell" for x in t["log"])
    assert all(abs(sum(p["qty"] * p["last"] for p in z["pos"].values())) < 0.25 * z["start_usd"] for z in (s, t)), "legs should roughly offset"
    print(f"{name}: {len(got)} weekly trades from {B.iso(first)[:10]} match the backtest; equity {eq / s['start_usd'] - 1:+.1%}, "
          f"mean trade {st.mean(r for *_, r in got) * 100:+.3f}%; ok")


if __name__ == "__main__":
    check(F.signal, "fwd_lowvol")
