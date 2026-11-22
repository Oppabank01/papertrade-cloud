#!/usr/bin/env python3
"""Offline self-check: python3 test_mts.py"""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import mts  # noqa: E402
import stats as S  # noqa: E402

rng = random.Random(1)

# PSR: pure noise sits near 0.5, a strong drift near 1
noise = [rng.gauss(0, 0.01) for _ in range(2000)]
assert 0.2 < S.psr(noise) < 0.8, S.psr(noise)
assert S.psr([x + 0.002 for x in noise]) > 0.99

# the best of more tries is expected to look better by luck alone
assert S.expected_max_sharpe([0.1, -0.1, 0.05, -0.05] * 25) > S.expected_max_sharpe([0.1, -0.1, 0.05, -0.05])

# PBO: 10 noise strategies overfit (~0.5); one real edge among them does not
m = [[rng.gauss(0, 0.01) for _ in range(10)] for _ in range(800)]
p_noise, n = S.pbo(m)
assert n == 12870 and 0.3 < p_noise < 0.7, p_noise
m2 = [[x + (0.003 if j == 0 else 0) for j, x in enumerate(row)] for row in m]
assert S.pbo(m2)[0] < 0.05

# DM: a model with half the error beats the baseline
y = [rng.gauss(0, 1) for _ in range(500)]
good = [v + rng.gauss(0, 0.5) for v in y]
_, pv = S.dm_test([a - b for a, b in zip(y, good)], y)
assert pv < 0.01
_, pv = S.dm_test(y, y)
assert pv == 1.0

# trade summary exposes the fat tail
s = S.trade_summary([-0.08] * 99 + [30.0])
assert s["mean"] > 0 and s["median"] < 0 and s["mean_wo_top1pct"] < 0

# no lookahead: the return of bar t uses the position decided at bar t-1
c = [100, 100, 110, 121, 121]
pos = [0, 1, 1, 0, 0]
r = mts.strat_returns(c, pos, 0.0, 2)
assert r == [0.10000000000000009, 0.10000000000000009, 0.0], r
assert mts.strat_returns(c, pos, 0.01, 2)[0] == 0.10000000000000009 - 0.01   # cost when pos changed at bar 1

# bracket: a bar touching both stop and target counts as the stop; a gap fills at the open
bar = lambda o, h, l, c: dict(o=o, h=h, l=l, c=c)
b = [bar(1, 1, 1, 1), bar(1, 1.3, 0.9, 1)]
assert abs(mts.bracket_trade(b, 0, -0.08, 0.2, 5, 0) - (-0.08)) < 1e-12
b = [bar(1, 1, 1, 1), bar(0.5, 0.6, 0.4, 0.5)]
assert abs(mts.bracket_trade(b, 0, -0.08, 0.2, 5, 0) - (-0.5)) < 1e-12

# breakout enters above the prior high and exits below the prior low
c = [10, 10, 10, 10, 12, 13, 9, 9]
h = [x + 0.5 for x in c]
l = [x - 0.5 for x in c]
assert mts.positions(c, h, l, "breakout", 4) == [0, 0, 0, 0, 1, 1, 0, 0]
print("ok")

# permutation: same start and end, prefix untouched, valid bars, order destroyed
walk, px = [], 100.0
for i in range(400):
    o = px * math.exp(rng.gauss(0, 0.002)); c = o * math.exp(rng.gauss(0, 0.01))
    walk.append(dict(t=i, o=o, h=max(o, c) * 1.003, l=min(o, c) * 0.997, c=c)); px = c
pb = S.permute_bars(walk, 50, random.Random(3))
assert pb[:50] == walk[:50] and abs(pb[-1]["c"] - walk[-1]["c"]) < 1e-6 * walk[-1]["c"]
assert all(x["l"] <= min(x["o"], x["c"]) + 1e-12 and x["h"] >= max(x["o"], x["c"]) - 1e-12 for x in pb)
assert [x["c"] for x in pb[50:]] != [x["c"] for x in walk[50:]]
# a planted pattern (tomorrow repeats today's sign) is caught; the same score on a random walk is not
trendy, px, d = [], 100.0, 1
for i in range(400):
    d = d if rng.random() < 0.8 else -d
    o = px; c = o * math.exp(d * 0.01)
    trendy.append(dict(t=i, o=o, h=max(o, c), l=min(o, c), c=c)); px = c
follow = lambda b: S.sharpe([(1 if b[i - 1]["c"] > b[i - 2]["c"] else -1) * (b[i]["c"] / b[i - 1]["c"] - 1) for i in range(2, len(b))])
assert S.permutation_test(follow, trendy, 99)[1] < 0.05
assert S.permutation_test(follow, walk, 99)[1] > 0.05
print("permutation ok")
