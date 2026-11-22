"""dxai.py walking 1h bars one at a time gives the same trades as the backtest (/private/tmp/claude-501/arxiv_dxai/analyse.py)."""
import random
import dxai as D, byttrade as B

cache = {m: [dict(x, closed=True) for x in D.fetch(m) if x["closed"]] for m in D.SYMS}
ts = sorted(set.intersection(*({x["t"] for x in b} for b in cache.values())))
tset = set(ts)
b = {m: [x for x in v if x["t"] in tset] for m, v in cache.items()}
n, START = len(ts), 30


def backtest(b, start):
    pos, out = {}, []
    for i in range(start, n - 1):
        ex = set()
        for m in list(pos):
            e, ei = pos[m]; x = b[m][i]
            if i < ei:
                continue
            st, tg = e * (1 - D.STOP), e * (1 + D.TGT)
            px = x["o"] if x["o"] <= st else st if x["l"] <= st else max(tg, x["o"]) if x["h"] >= tg else \
                x["c"] if i >= ei + D.HOLD - 1 else None
            if px is not None:
                out.append((m[:-4], round(e, 8), round(px, 8))); del pos[m]; ex.add(m)
        r = {m: b[m][i]["c"] / b[m][i - D.LOOK]["c"] - 1 for m in D.SYMS}
        for m in sorted(D.SYMS, key=lambda m: -r[m])[:D.TOP]:
            if m in pos or m in ex or b[m][i]["c"] / b[m][i - 1]["c"] - 1 <= D.CHASE:
                continue
            if len(pos) >= D.MAXPOS:
                break
            pos[m] = (b[m][i + 1]["o"], i + 1)
    return out


def walk(mode, seed):
    s = B.new_state("t"); s["seen"] = ts[START - 1]
    for k in range(START + 1, n + 1):          # bar k-1 is the forming bar at each tick
        D.step(s, {m: v[:k - 1] + [dict(v[k - 1], closed=False)] for m, v in b.items()}, mode, random.Random(seed + k))
    return s


want = backtest(b, START)
s = walk("rule", 0)
buys = {}
got = []
for x in s["log"]:
    if x["kind"] == "buy":
        buys[x["coin"]] = x["px"]
    else:
        got.append((x["coin"], round(buys[x["coin"]], 8), round(x["px"], 8)))
assert sorted(got) == sorted(want), (len(got), len(want), got[:3], want[:3])
assert len(got) >= 3, len(got)
assert all(x["side"] == "long" for x in s["log"])
t = B.new_state("t"); D.step(t, {m: v[:-1] + [dict(v[-1], closed=False)] for m, v in b.items()}, "rule", random.Random(1))
assert t["seen"] == ts[-2] and not t["log"], "a new account must not trade on a stale signal"
tw = walk("random", 100)
assert any(x["kind"] == "sell" for x in tw["log"]), "twin should trade"
print(f"{len(got)} rule trades match the backtest, twin {sum(x['kind'] == 'sell' for x in tw['log'])} trades; ok")
