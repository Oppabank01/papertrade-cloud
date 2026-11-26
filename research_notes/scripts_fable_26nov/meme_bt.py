# Memecoin (pump.fun graduates on PumpSwap) rule tests on GeckoTerminal minute bars.
# usage: python3 meme_bt.py <pkl> [grid|one <rulekey>]
import pickle, sys, random, math, statistics as st
COST = 0.02  # per side
def load(fn):
    g = pickle.load(open(fn, "rb")); out = []
    for m, v in g.items():
        b = v.get("bars")
        if not b or len(b) < 3: continue
        out.append(dict(mint=m, sym=v["sym"], t0=b[0][0], bars=b))
    out.sort(key=lambda c: c["t0"]); return out
def sim(b, i, kind):
    """enter at close of bar i (== open of bar i+1), need bar i+1. returns net return."""
    if i + 1 >= len(b): return None
    e = b[i][4]
    if e <= 0: return None
    tin = b[i][0]
    if kind == "X1": stop, tp, trail_arm, trail, hold = 0.75, None, 1.5, 0.30, 360
    elif kind == "X2": stop, tp, trail_arm, trail, hold = 0.75, 1.5, None, None, 120
    peak = e; px = None
    for j in range(i + 1, len(b)):
        t, o, h, l, c, v = b[j]
        if t - tin > hold * 60: px = b[j - 1][4]; break
        lvl = e * stop
        if trail_arm and peak >= e * trail_arm: lvl = max(lvl, peak * (1 - trail))
        if l <= lvl: px = min(o, lvl); break
        if tp and h >= e * tp: px = max(o, e * tp) if o >= e * tp else e * tp; break
        peak = max(peak, h)
    if px is None: px = b[-1][4]
    return px / e * (1 - COST) / (1 + COST) - 1
def entries(c, rule):
    b = c["bars"]; t0 = b[0][0]; kind = rule[0]
    if kind == "S":
        _, T, k, V = rule
        for i, x in enumerate(b):
            age = (x[0] - t0) / 60
            if age < T: continue
            if age > T + 10: return None      # no bar near T: skip coin
            vol = sum(y[5] for y in b[:i + 1] if y[0] > x[0] - 900)
            if x[4] >= k * b[0][1] and vol >= V: return i
            return None
    if kind == "D":
        _, d = rule; hi = 0
        for i, x in enumerate(b):
            age = (x[0] - t0) / 60
            if age > 180: return None
            if i >= 1: hi = max(hi, x[2])
            if age >= 5 and hi > 0 and x[4] <= (1 - d) * hi:
                vol = sum(y[5] for y in b[:i + 1] if y[0] > x[0] - 300)
                if vol >= 5000: return i
                return None
    return None
def stats(r):
    n = len(r)
    if n < 3: return dict(n=n)
    m = st.mean(r); sd = st.pstdev(r) or 1e-9; s = sorted(r)
    h = n // 2
    return dict(n=n, mean=m * 100, med=st.median(r) * 100, wr=sum(x > 0 for x in r) / n * 100, t=m / sd * math.sqrt(n),
                ex1=st.mean(s[:-1]) * 100, ex5=(st.mean(s[:-5]) * 100 if n > 8 else float("nan")),
                h1=st.mean(r[:h]) * 100, h2=st.mean(r[h:]) * 100)
def run(coins, rule, exitk, seeds=200):
    tr = []
    for c in coins:
        i = entries(c, rule)
        if i is None: continue
        r = sim(c["bars"], i, exitk)
        if r is None: continue
        tr.append((c["t0"], r, (c["bars"][i][0] - c["t0"]) / 60, c["sym"]))
    rs = [x[1] for x in tr]; ages = [x[2] for x in tr]
    ctl = []  # per-seed stats of age-matched random coin entries
    rng = random.Random(1)
    for s in range(seeds):
        rr = []
        for a in ages:
            for _ in range(30):
                c = rng.choice(coins); b = c["bars"]
                idx = [i for i, x in enumerate(b[:-1]) if max(2, a * 0.5) <= (x[0] - c["t0"]) / 60 <= max(4, a * 1.5)]
                if idx:
                    r = sim(b, rng.choice(idx), exitk)
                    if r is not None: rr.append(r); break
        if len(rr) > 5:
            ss = sorted(rr); ctl.append((st.mean(rr), st.median(rr), st.mean(ss[:-1]), st.mean(ss[:-5]) if len(ss) > 8 else float("nan")))
    return tr, stats(rs), ctl
def show(name, s, ctl):
    if s["n"] < 3 or not ctl: print(f"{name:22s} n={s['n']} (too few)"); return
    cm = [c[0] for c in ctl]; c1 = [c[2] for c in ctl]; c5 = [c[3] for c in ctl]; cmed = [c[1] for c in ctl]
    pm = sum(c >= s["mean"] / 100 for c in cm) / len(cm); p5 = sum(c >= s["ex5"] / 100 for c in c5) / len(c5)
    print(f"{name:22s} n={s['n']:3d} mean={s['mean']:+7.1f} med={s['med']:+6.1f} wr={s['wr']:4.0f} t={s['t']:+5.2f} ex1={s['ex1']:+6.1f} ex5={s['ex5']:+6.1f} h1={s['h1']:+6.1f} h2={s['h2']:+6.1f} | ctl mean={st.mean(cm)*100:+6.1f} med={st.mean(cmed)*100:+6.1f} ex1={st.mean(c1)*100:+6.1f} ex5={st.mean(c5)*100:+6.1f} p(ctl>=rule) mean={pm:.2f} ex5={p5:.2f}")
if __name__ == "__main__":
    coins = load(sys.argv[1]); print("coins", len(coins))
    grid = [("S", T, k, V) for T in (15, 60, 120) for k in (1, 2) for V in (10000, 50000)] + [("D", 0.5), ("D", 0.7)]
    if len(sys.argv) > 2 and sys.argv[2] == "one":
        grid = [eval(sys.argv[3])]; ex = [sys.argv[4]]
    else: ex = ["X1", "X2"]
    print("settings", len(grid) * len(ex))
    for rule in grid:
        for e in ex:
            tr, s, ctl = run(coins, rule, e, seeds=int(sys.argv[5]) if len(sys.argv) > 5 else 100)
            show(str(rule) + e, s, ctl)
