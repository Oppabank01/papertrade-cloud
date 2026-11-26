# Binance USDT-M perp event rules on 1h bars, vs random controls. usage: python3 cex_bt.py [seeds]
import pickle, sys, math, numpy as np, bisect, collections
SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
RT = 0.003          # round-trip cost (taker 0.05% + slippage 0.10% per side)
STOPSLIP = 0.001
H = 3600000
K = {}
import os
for fn in os.environ.get("KFILES", "bn_k2_0.pkl,bn_k2_1.pkl").split(","): K.update(pickle.load(open(fn, "rb")))
F = pickle.load(open(os.environ.get("FFILE", "bn_f.pkl"), "rb"))
meta = {s: (ob, stt) for s, ob, stt in pickle.load(open("bn_syms.pkl", "rb"))}
D = {}
for s, (t, a) in K.items():
    if len(t) < 100: continue
    a = a.astype(np.float64); f = F.get(s) or []
    D[s] = dict(t=t.astype(np.float64), o=a[:, 0], h=a[:, 1], l=a[:, 2], c=a[:, 3], q=a[:, 4],
                ft=np.array([x[0] for x in f], dtype=float), fr=np.array([x[1] for x in f], dtype=float), ob=meta[s][0])
del K
SY = sorted(D); print("symbols", len(SY), "with funding", sum(1 for s in SY if len(D[s]["ft"])), flush=True)
def sim(d, i, side, hold, stop):
    """enter at open of bar i; side +1 long / -1 short; stop as fraction (e.g. 0.15); returns net ret or None"""
    n = len(d["t"])
    if i >= n - 1 or i < 0: return None
    e = d["o"][i]
    if e <= 0: return None
    j1 = min(n, i + hold)
    if side > 0:
        lvl = e * (1 - stop); hit = np.nonzero(d["l"][i:j1] <= lvl)[0]
        if len(hit): j = i + hit[0]; px = min(d["o"][j], lvl) * (1 - STOPSLIP); tex = d["t"][j] + H
        else: j = j1 - 1; px = d["c"][j]; tex = d["t"][j] + H
        r = px / e - 1
    else:
        lvl = e * (1 + stop); hit = np.nonzero(d["h"][i:j1] >= lvl)[0]
        if len(hit): j = i + hit[0]; px = max(d["o"][j], lvl) * (1 + STOPSLIP); tex = d["t"][j] + H
        else: j = j1 - 1; px = d["c"][j]; tex = d["t"][j] + H
        r = 1 - px / e
    ft = d["ft"]
    if len(ft):
        a = np.searchsorted(ft, d["t"][i], "right"); b = np.searchsorted(ft, tex, "right")
        r -= side * d["fr"][a:b].sum()
    return r - RT
def stats(tr):
    """tr: list of (time, ret). returns dict"""
    tr = sorted(tr); r = np.array([x[1] for x in tr]); n = len(r)
    if n < 8: return dict(n=n)
    day = collections.defaultdict(list)
    for t, x in tr: day[int(t // 86400000)].append(x)
    dm = np.array([np.mean(v) for v in day.values()])
    s = np.sort(r); h = n // 2
    return dict(n=n, mean=r.mean() * 100, med=np.median(r) * 100, wr=(r > 0).mean() * 100, t=r.mean() / (r.std() + 1e-12) * math.sqrt(n),
                tday=dm.mean() / (dm.std() + 1e-12) * math.sqrt(len(dm)), days=len(dm),
                ex1=s[:-1].mean() * 100, ex5=s[:-5].mean() * 100, h1=r[:h].mean() * 100, h2=r[h:].mean() * 100, worst=s[0] * 100)
def control(tr_meta, side, hold, stop, mode, rng):
    out = []
    for s, i, t in tr_meta:
        for _ in range(20):
            if mode == "sym":   # same symbol, random time
                d = D[s]; j = int(rng.integers(30, max(31, len(d["t"]) - 2))); 
            else:               # same time, random symbol
                s2 = SY[int(rng.integers(len(SY)))]; d = D[s2]; j = int(np.searchsorted(d["t"], t))
                if j >= len(d["t"]) - 1 or d["t"][j] != t or j < 30: continue
            r = sim(d, j, side, hold, stop)
            if r is not None: out.append((d["t"][j], r)); break
    return out
def evaluate(name, ev, side, hold, stop):
    """ev: dict sym -> sorted list of entry bar indices (signal already lagged). cooldown = hold."""
    tr = []; metaL = []
    for s, idxs in ev.items():
        d = D[s]; last = -10**9
        for i in idxs:
            if i < last: continue
            r = sim(d, i, side, hold, stop)
            if r is None: continue
            tr.append((d["t"][i], r)); metaL.append((s, i, d["t"][i])); last = i + hold
    st = stats(tr)
    if st["n"] < 8: print(f"{name:34s} n={st['n']}"); return st, None
    rng = np.random.default_rng(5); res = {}
    for mode in ("sym", "time"):
        ms = []; e5 = []; md = []
        for k in range(SEEDS):
            c = control(metaL, side, hold, stop, mode, rng); r = np.sort(np.array([x[1] for x in c]))
            ms.append(r.mean()); e5.append(r[:-5].mean()); md.append(np.median(r))
        ms = np.array(ms) * 100; e5 = np.array(e5) * 100
        res[mode] = (ms.mean(), np.mean(md) * 100, e5.mean(), (ms >= st["mean"]).mean(), (e5 >= st["ex5"]).mean())
    print(f"{name:34s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} t={st['t']:+5.1f} tday={st['tday']:+5.1f}({st['days']}) ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} worst={st['worst']:+5.0f}"
          f" | ctlSym mean={res['sym'][0]:+5.2f} med={res['sym'][1]:+5.2f} ex5={res['sym'][2]:+5.2f} p={res['sym'][3]:.2f}/{res['sym'][4]:.2f}"
          f" | ctlTime mean={res['time'][0]:+5.2f} med={res['time'][1]:+5.2f} ex5={res['time'][2]:+5.2f} p={res['time'][3]:.2f}/{res['time'][4]:.2f}", flush=True)
    return st, res
def bar_after(d, t):  # index of first bar with open time >= t
    return int(np.searchsorted(d["t"], t, "left"))
