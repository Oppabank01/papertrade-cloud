"""Memecoin-perp rule tester on Binance USDT-M 1h bars (perp.pkl from perp_extract.py).
Entry at the open of the bar after the signal bar. Stop checked first each bar: short fills max(open, stop)*1.001,
long fills min(open, stop)*0.999. Cost 0.15%/side. Funding paid/received is included. Optional BTC hedge leg."""
import pickle, math, collections, numpy as np
H = 3600000; SIDE_COST = 0.0015; SLIP = 0.001
def load(fn):
    D = {}
    for s, v in pickle.load(open(fn, "rb")).items():
        a = v["a"].astype(np.float64)
        if len(a) < 200: continue
        D[s] = dict(t=v["t"].astype(np.int64), o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3], q=a[:, 4], ft=v["ft"], fr=v["fr"], kind=v["kind"], st=v["st"])
    return D
def fund(d, t0, t1):
    if not len(d["ft"]): return 0.0
    a = np.searchsorted(d["ft"], t0, "right"); b = np.searchsorted(d["ft"], t1, "right"); return float(d["fr"][a:b].sum())
def sim(D, s, i, side, hold, stop, hedge=None, tp=None):
    """enter at open of bar i. returns (entry_time, net_ret) or None"""
    d = D[s]; n = len(d["t"])
    if i < 1 or i >= n - 1: return None
    e = d["o"][i]
    if not e > 0: return None
    j1 = min(n, i + hold); px = None; j = None
    for k in range(i, j1):
        if side > 0:
            lvl = e * (1 - stop)
            if d["l"][k] <= lvl: px = min(d["o"][k], lvl) * (1 - SLIP); j = k; break
            if tp and d["h"][k] >= e * (1 + tp): px = e * (1 + tp); j = k; break
        else:
            lvl = e * (1 + stop)
            if d["h"][k] >= lvl: px = max(d["o"][k], lvl) * (1 + SLIP); j = k; break
            if tp and d["l"][k] <= e * (1 - tp): px = e * (1 - tp); j = k; break
    if px is None: j = j1 - 1; px = d["c"][j]
    tex = d["t"][j] + H
    r = side * (px / e - 1) - side * fund(d, d["t"][i], tex) - 2 * SIDE_COST
    if hedge:
        b = D[hedge]; a = int(np.searchsorted(b["t"], d["t"][i])); z = int(np.searchsorted(b["t"], d["t"][j]))
        if a >= len(b["t"]) or z >= len(b["t"]): return None
        r += -side * (b["c"][z] / b["o"][a] - 1) + side * fund(b, b["t"][a], tex) - 2 * SIDE_COST
    return (int(d["t"][i]), r, int(tex))
def stats(tr):
    tr = sorted(tr); r = np.array([x[1] for x in tr]); n = len(r)
    if n < 8: return dict(n=n)
    day = collections.defaultdict(list)
    for x in tr: day[x[0] // 86400000].append(x[1])
    dm = np.array([np.mean(v) for v in day.values()]); s = np.sort(r); h = n // 2
    return dict(n=n, mean=r.mean() * 100, med=np.median(r) * 100, wr=(r > 0).mean() * 100, ex1=s[:-1].mean() * 100, ex5=s[:-5].mean() * 100,
                h1=r[:h].mean() * 100, h2=r[h:].mean() * 100, tday=dm.mean() / (dm.std() + 1e-12) * math.sqrt(len(dm)), days=len(dm), worst=s[0] * 100, best=s[-1] * 100)
def run(D, ev, side, hold, stop, hedge=None, tp=None):
    """ev: {sym: sorted bar indices}; cooldown = until the previous trade on that symbol has exited"""
    tr = []; meta = []
    for s, idx in ev.items():
        free = -1
        for i in idx:
            if D[s]["t"][min(i, len(D[s]["t"]) - 1)] < free: continue
            r = sim(D, s, i, side, hold, stop, hedge, tp)
            if r is None: continue
            tr.append(r); meta.append((s, i)); free = r[2]
    return tr, meta
def control(D, meta, pool, side, hold, stop, hedge, tp, mode, seeds=40):
    """mode 'sym': same symbol, random bar. mode 'time': same hour, random symbol from pool."""
    ms = []; md = []; e5 = []
    for k in range(seeds):
        rng = np.random.default_rng(1000 + k); c = []
        for s, i in meta:
            for _ in range(15):
                if mode == "sym": s2 = s; j = int(rng.integers(24 * 14, max(24 * 14 + 1, len(D[s]["t"]) - 2)))
                else:
                    s2 = pool[int(rng.integers(len(pool)))]; t = D[s]["t"][i]; j = int(np.searchsorted(D[s2]["t"], t))
                    if j >= len(D[s2]["t"]) - 1 or D[s2]["t"][j] != t or j < 24: continue
                r = sim(D, s2, j, side, hold, stop, hedge, tp)
                if r is not None: c.append(r[1]); break
        c = np.array(c)
        if len(c) > 5: ms.append(c.mean() * 100); md.append(np.median(c) * 100); e5.append(np.sort(c)[:-5].mean() * 100)
    return dict(mean=float(np.mean(ms)), med=float(np.mean(md)), ex5=float(np.mean(e5)), all=np.array(ms))
def report(name, D, ev, side, hold, stop, hedge=None, tp=None, pool=None, seeds=40):
    tr, meta = run(D, ev, side, hold, stop, hedge, tp); st = stats(tr)
    if st["n"] < 8: print(f"{name:46s} n={st['n']}"); return st
    line = (f"{name:46s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} "
            f"h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} tday={st['tday']:+5.1f}({st['days']}) worst={st['worst']:+5.0f} syms={len(set(m[0] for m in meta))}")
    for mode in ("sym", "time"):
        c = control(D, meta, pool, side, hold, stop, hedge, tp, mode, seeds)
        line += f" | ctl_{mode} mean={c['mean']:+6.2f} med={c['med']:+6.2f} p={float((c['all'] >= st['mean']).mean()):.2f}"
    print(line, flush=True); return st
