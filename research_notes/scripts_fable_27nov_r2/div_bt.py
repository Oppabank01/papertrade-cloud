"""SET dividend capture and neighbours. Yahoo daily bars (raw close, split-adjusted) + dividend events for ~170 SET tickers.
i = XD day (first bar on/after the event date). Cost 0.17%/side, dividend net of 10% withholding. No stop (stated).
  CAP k : buy close i-1, sell close i+k, keep the dividend
  CAPo  : buy close i-1, sell XD open
  PRE n : buy close i-1-n, sell close i-1 (no dividend, no tax)
  POST k: buy XD close (or XD open), sell close i+k
Controls: (a) random days in the same stock, same horizon, 200 seeds; (b) SET index over the same window (excess)."""
import sys, glob, os, time, numpy as np, r2lib as L
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_yahoo.py")).read().split("ok = []")[0])
C = 0.0017; TAX = 0.10; Y0 = 2010
# SET50 ETF (TDEX) as the market proxy: Yahoo has no usable ^SET.BK history
idx = L.yahoo("TDEX.BK"); iday = (idx["t"] + 7 * 3600) // 86400; ic = idx["c"]
def idx_ret(d0, d1):
    a = np.searchsorted(iday, d0); b = np.searchsorted(iday, d1)
    if a >= len(iday) or b >= len(iday) or iday[a] != d0 or iday[b] != d1: return np.nan
    return ic[b] / ic[a] - 1
S = {}
for s in SET:
    d = L.yahoo(s + ".BK")
    if d is None or len(d["t"]) < 300: continue
    d["day"] = (d["t"] + 7 * 3600) // 86400; S[s] = d
print("tickers", len(S), "with dividends", sum(1 for d in S.values() if d["div"]))
EV = []   # (sym, i, div, yield)
gap = []
for s, d in S.items():
    for ts_, amt in sorted(d["div"].items()):
        dd = (ts_ + 7 * 3600) // 86400; i = int(np.searchsorted(d["day"], dd))
        if i < 25 or i >= len(d["t"]) - 21 or d["day"][i] - dd > 4: continue
        if time.gmtime(d["t"][i]).tm_year < Y0: continue
        y = amt / d["c"][i - 1]
        if not (0.001 < y < 0.25) or d["v"][i] <= 0 or d["v"][i - 1] <= 0: continue
        EV.append((s, i, amt, y)); gap.append((d["o"][i] / d["c"][i - 1] - 1, y))
gap = np.array(gap)
print(f"events {len(EV)}  mean yield {gap[:,1].mean()*100:.2f}%  mean XD open gap {gap[:,0].mean()*100:+.2f}%  (sanity: gap should be about -yield)  drop ratio {(-gap[:,0]).mean()/gap[:,1].mean():.2f}")
def trade(kind, k, e):
    s, i, amt, y = e; d = S[s]; c = d["c"]; o = d["o"]
    if kind == "CAP": a, b, pa, pb, dv = i - 1, i + k, c[i - 1], c[i + k], amt * (1 - TAX)
    elif kind == "CAPo": a, b, pa, pb, dv = i - 1, i, c[i - 1], o[i], amt * (1 - TAX)
    elif kind == "PRE": a, b, pa, pb, dv = i - 1 - k, i - 1, c[i - 1 - k], c[i - 1], 0.0
    elif kind == "POST": a, b, pa, pb, dv = i, i + k, c[i], c[i + k], 0.0
    elif kind == "POSTo": a, b, pa, pb, dv = i, i + k, o[i], c[i + k], 0.0
    r = (pb + dv) / pa - 1 - 2 * C
    return int(d["t"][a]) * 1000, r, r - idx_ret(d["day"][a], d["day"][b]) if kind not in ("CAPo", "POSTo") else np.nan, (a, b)
def ctl(kind, k, evs, seeds=200):
    hold = {"CAP": k + 1, "PRE": k, "POST": k, "POSTo": k, "CAPo": 1}[kind]; ms = []
    lo = {s: int(np.searchsorted(S[s]["t"], time.mktime((Y0, 1, 1, 0, 0, 0, 0, 0, 0)))) for s in S}
    for z in range(seeds):
        rng = np.random.default_rng(z); rr = []
        for s, i, amt, y in evs:
            d = S[s]; a = int(rng.integers(max(lo[s], 1), len(d["t"]) - hold - 1))
            if kind == "CAPo": rr.append(d["o"][a + 1] / d["c"][a] - 1 - 2 * C)
            elif kind == "POSTo": rr.append(d["c"][a + hold] / d["o"][a] - 1 - 2 * C)
            else: rr.append(d["c"][a + hold] / d["c"][a] - 1 - 2 * C)
        ms.append(np.mean(rr) * 100)
    return np.array(ms)
def report(name, kind, k, evs, split=2021):
    tr = [trade(kind, k, e) for e in evs]
    tt = [(t, r) for t, r, x, ab in tr if np.isfinite(r)]
    st = L.stats(tt)
    if st["n"] < 8: return
    cm = ctl(kind, k, evs, 100 if len(evs) > 2000 else 200)
    ex = np.nanmean([x for t, r, x, ab in tr]) * 100
    oos = [r for t, r in tt if time.gmtime(t / 1000).tm_year >= split]; ins = [r for t, r in tt if time.gmtime(t / 1000).tm_year < split]
    print(L.fmt(name, st, dict(mean=float(cm.mean()), med=float(np.median(cm)), p=float((cm >= st["mean"]).mean()))) +
          f" | vsSET {ex:+.2f} | <{split} n{len(ins)} {np.mean(ins)*100:+.2f} >={split} n{len(oos)} {np.mean(oos)*100:+.2f}")
for lab, evs in (("all", EV), ("yield>=2%", [e for e in EV if e[3] >= 0.02]), ("yield>=3%", [e for e in EV if e[3] >= 0.03]), ("yield>=4%", [e for e in EV if e[3] >= 0.04])):
    print(f"\n--- {lab}: {len(evs)} events ---")
    report("CAPo buy close i-1, sell XD open", "CAPo", 0, evs)
    for k in (0, 1, 3, 5, 10, 20): report(f"CAP buy close i-1, sell close i+{k}", "CAP", k, evs)
    for n in (3, 5, 10, 20): report(f"PRE buy close i-1-{n}, sell close i-1", "PRE", n, evs)
    for k in (3, 5, 10, 20): report(f"POST buy XD close, sell close i+{k}", "POST", k, evs)
    for k in (0, 5, 10): report(f"POSTo buy XD open, sell close i+{k}", "POSTo", k, evs) if k else None
