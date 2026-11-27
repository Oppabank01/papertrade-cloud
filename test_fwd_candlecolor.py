"""fwd_candlecolor.py walking 15m bars one at a time (the last one still forming, a 1000-bar window like the live fetch)
gives the same trades as the scout's backtest (/tmp/scout_0436/cc.py, copied below) on mts.bars data."""
import bisect, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_candlecolor as F, byttrade as B

DAY = 86400000


def sessions(b):
    out = []
    for i, x in enumerate(b):
        key = x["t"] // DAY * DAY
        if out and out[-1]["ts"] == key:
            s = out[-1]
            s["h"], s["l"], s["c"], s["n"], s["j"] = max(s["h"], x["h"]), min(s["l"], x["l"]), x["c"], s["n"] + 1, i
        else:
            out.append(dict(ts=key, o=x["o"], h=x["h"], l=x["l"], c=x["c"], n=1, i=i, j=i))
    for s in out:
        s["ok"] = s["n"] == 96
    return out


def plan(ss, k, d):
    prev, cur = ss[k - 1], ss[k]
    e = cur["o"]
    peak = prev["h"] if d > 0 else prev["l"]
    if abs(e - peak) / e <= 0.01:
        th = max(peak, e) if d > 0 else min(peak, e)
        take = None
        for j in range(k - 2, -1, -1):
            s = ss[j]
            if s["ok"] and ((d > 0 and s["h"] > th) or (d < 0 and s["l"] < th)):
                take = s["h"] if d > 0 else s["l"]
                break
    else:
        take = prev["h"] if d > 0 else prev["l"]
    if take is not None and (take - e) * d <= 0:
        take = e * (1 + 0.002 * d)
    stop = e * (1 - 0.01 * d)
    return e, stop, take, (e + (take - e) * 0.5 if take is not None else None)


def run_day(b, s, d, e, stop, take, part):
    legs, size = [], 1.0
    for i in range(s["i"], s["j"] + 1):
        x = b[i]
        if part is not None and size == 1.0 and ((x["h"] >= part) if d > 0 else (x["l"] <= part)):
            legs.append((0.5, part)); size = 0.5; stop = e
        if take is not None and ((x["h"] >= take) if d > 0 else (x["l"] <= take)):
            legs.append((size, take)); return legs
        if (x["c"] < stop) if d > 0 else (x["c"] > stop):
            legs.append((size, x["c"])); return legs
        if i == s["j"]:
            legs.append((size, x["c"])); return legs


def trades(b):
    ss = sessions(b)
    out = []
    for k in range(1, len(ss)):
        prev, cur = ss[k - 1], ss[k]
        if not prev["ok"] or not cur["ok"]:
            continue
        d = 1 if prev["c"] > prev["o"] else -1 if prev["c"] < prev["o"] else 0
        if d == 0:
            continue
        e, stop, take, part = plan(ss, k, d)
        out.append((cur["ts"], d, e, run_day(b, cur, d, e, stop, take, part)))
    return out


SYM = "BTCUSDT"
full = mts.bars("binance", SYM, "15m", max_age_h=10 ** 6)
days = [dict(t=s["ts"], o=s["o"], h=s["h"], l=s["l"], c=s["c"], closed=True) for s in sessions(full) if s["ok"]]
dt = [x["t"] for x in days]
b = [dict(x, closed=True) for x in full]
n, S0 = len(b), len(b) - 4000
bt = [t for t in trades(full) if t[0] - 900000 > b[S0]["t"] and t[0] + DAY <= b[-1]["t"]]
want = [(d, round(e, 6), round(legs[0][1], 6) if len(legs) == 2 else None, round(legs[-1][1], 6)) for _, d, e, legs in bt]


def walk(mode, seed):
    s = B.new_state("t"); s["seen"] = {SYM: b[S0]["t"]}
    for k in range(S0 + 2, n + 1):
        now = b[k - 1]["t"]
        dd = days[max(0, bisect.bisect_right(dt, now - DAY) - 1000):bisect.bisect_right(dt, now - DAY)]
        F.step(s, SYM, b[max(0, k - 1000):k - 1] + [dict(b[k - 1], closed=False)], dd, mode, random.Random(seed + k))
    return s


s = walk("rule", 0)
buys = [x for x in s["log"] if x["kind"] == "buy"]
sells = [x for x in s["log"] if x["kind"] == "sell"]
got = [(1 if bu["side"] == "long" else -1, round(bu["px"], 6), round(se["part_px"], 6) if se.get("part_px") is not None else None,
        round(se["px"], 6)) for bu, se in zip(buys, sells)]
assert got == want, (len(got), len(want), [(g, w) for g, w in zip(got, want) if g != w][:3])
assert len(got) > 20 and any(g[2] is not None for g in got), len(got)
assert sum(x["kind"] == "sell" for x in s["log"]) == len(sells)
t = walk("random", 99)
assert any(x["kind"] == "sell" for x in t["log"]) and {x["side"] for x in t["log"] if x["kind"] == "buy"} == {"long", "short"}
print(f"{len(got)} trades match the backtest ({sum(g[2] is not None for g in got)} with a half exit); ok")
