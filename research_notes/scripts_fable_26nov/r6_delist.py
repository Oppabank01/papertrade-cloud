# R6: short a Binance USDT perp N minutes after Binance announces its delisting (spot "Binance Will Delist X" or
# futures "Binance Futures Will Delist XUSDT"). 1m bars. Stop fill = max(open, stop)*1.001. Funding from bn_f.pkl.
# usage: python3 r6_delist.py [list]
import pickle, numpy as np, math, time, sys, collections
import os
PFX = os.environ.get("EVPFX", "delist")
E = pickle.load(open(PFX + "_1m.pkl", "rb")); F = pickle.load(open("bn_f.pkl", "rb"))
if PFX in ("bybit", "delistold"): F = {}      # Bybit funding not fetched: results there exclude funding
EV = {}
for (ta, s), v in E.items():
    b = v["bars"]
    if not b or b[0][0] > ta: continue                      # no bars at announcement (e.g. relisted symbol)
    a = np.array(b, dtype=float)
    i0 = int(np.searchsorted(a[:, 0], ta))
    if a[i0:i0 + 30, 5].sum() <= 0: continue                # perp not trading any more
    f = F.get(s) or []
    EV[(ta, s)] = dict(kind=v["kind"], a=a, ft=np.array([x[0] for x in f], dtype=float), fr=np.array([x[1] for x in f], dtype=float), hasf=s in F)
print("usable events", len(EV), "of", len(E), "| announcements", len({k[0] for k in EV}), "| funding known", sum(v["hasf"] for v in EV.values()))
def trade(v, ta, lag, hold_min, stop, rt):
    a = v["a"]; t = a[:, 0]; o = a[:, 1]; h = a[:, 2]; c = a[:, 4]
    i = int(np.searchsorted(t, ta + lag * 60000))
    if i >= len(t) - 5 or i + hold_min > len(t) + 30: return None
    e = o[i]; j1 = min(len(t), i + hold_min)
    if stop:
        lvl = e * (1 + stop); hit = np.nonzero(h[i:j1] >= lvl)[0]
    else: hit = []
    if len(hit): j = i + hit[0]; px = max(o[j], lvl) * 1.001
    else: j = j1 - 1; px = c[j]
    r = 1 - px / e - rt
    fund = 0.0
    if len(v["ft"]):
        x = np.searchsorted(v["ft"], t[i], "right"); y = np.searchsorted(v["ft"], t[j] + 60000, "right")
        fund = v["fr"][x:y].sum()                          # short receives +rate, pays when negative
    return r + fund, fund, o[i] / o[max(0, int(np.searchsorted(t, ta)) - 1)] - 1
def stats(tr):
    tr = sorted(tr); r = np.array([x[1] for x in tr]); n = len(r); s = np.sort(r); h = n // 2
    g = collections.defaultdict(list)
    for t, x in tr: g[t].append(x)
    am = np.array([np.mean(v) for k, v in sorted(g.items())]); ha = len(am) // 2
    return (f"n={n:3d} mean={r.mean()*100:+6.2f} med={np.median(r)*100:+6.2f} wr={(r>0).mean()*100:3.0f} t={r.mean()/r.std()*math.sqrt(n):+5.1f} ex1={s[:-1].mean()*100:+6.2f} ex5={s[:-5].mean()*100:+6.2f} "
            f"h1={r[:h].mean()*100:+6.2f} h2={r[h:].mean()*100:+6.2f} worst={s[0]*100:+4.0f} | perAnn n={len(am)} mean={am.mean()*100:+6.2f} med={np.median(am)*100:+6.2f} wr={(am>0).mean()*100:3.0f} t={am.mean()/am.std()*math.sqrt(len(am)):+5.1f} h1={am[:ha].mean()*100:+6.2f} h2={am[ha:].mean()*100:+6.2f}")
ns = 0
def run(kind, lag, hold, stop, rt, show=True):
    global ns
    tr = []; fu = []
    for (ta, s), v in EV.items():
        if kind != "both" and v["kind"] != kind: continue
        x = trade(v, ta, lag, hold, stop, rt)
        if x: tr.append((ta, x[0])); fu.append(x[1])
    ns += 1
    if show: print(f"{kind:4s} lag{lag:2d}m hold{hold:3d}m stop{int(stop*100):2d} rt{rt*100:.1f}%  {stats(tr)}  fund_mean={np.mean(fu)*100:+.2f}")
    return tr
print("\n-- grid (cost 0.3% round trip, funding included) --")
for kind in (("spot", "fut", "both") if PFX.startswith("delist") else ("both",)):
    for lag in (5, 15, 30, 60):
        for hold in (240, 600):
            run(kind, lag, hold, 0.30, 0.003)
print("\n-- stop variants, both kinds, lag 15m --")
for stop in (0.15, 0.50, 0):
    for hold in (240, 600): run("both", 15, hold, stop, 0.003)
print("\n-- cost stress, both kinds, lag 15m hold 240m stop 30% --")
for rt in (0.01, 0.02, 0.04): run("both", 15, 240, 0.30, rt)
print("settings tried:", ns)
if len(sys.argv) > 1:
    for (ta, s), v in sorted(EV.items()):
        x = trade(v, ta, 15, 240, 0.30, 0.003)
        if x: print(time.strftime("%Y-%m-%d %H:%M", time.gmtime(ta / 1000)), v["kind"], f"{s:16s} premove={x[2]*100:+6.1f} fund={x[1]*100:+5.2f} net4h={x[0]*100:+6.1f}")
