"""Thai DR mispricing vs the underlying (Yahoo daily). premium = DR price / (underlying close x FX); dev = premium / its
trailing 20-day median - 1 (the unknown DR ratio and fees cancel).
 OPEN rule (all DRs): at the Thai open the newest underlying close is known. dev_open <= -x -> buy the DR open, sell the DR
   close the same day (long only). Mirror shown as 'rich'. Cost 0.17%/side.
 CLOSE rule (HK/JP underlyings, their close is before the Thai close): dev_close <= -x -> buy the DR close, sell next open.
Control: every day (unconditional) and random days, same DR."""
import time, numpy as np, r2lib as L
PAIRS = {"AAPL80": ("AAPL", "US"), "NVDA80": ("NVDA", "US"), "TSLA80": ("TSLA", "US"), "MSFT80": ("MSFT", "US"), "GOOG80": ("GOOG", "US"), "AMZN80": ("AMZN", "US"),
         "META80": ("META", "US"), "NFLX80": ("NFLX", "US"), "AMD80": ("AMD", "US"), "AVGO80": ("AVGO", "US"), "NVDA01": ("NVDA", "US"), "AAPL01": ("AAPL", "US"),
         "TSLA01": ("TSLA", "US"), "MSFT01": ("MSFT", "US"), "AMZN01": ("AMZN", "US"), "META01": ("META", "US"), "NVDA19": ("NVDA", "US"), "BABA80": ("9988.HK", "HK"),
         "TENCENT80": ("0700.HK", "HK"), "BYDCOM80": ("1211.HK", "HK"), "PINGAN80": ("2318.HK", "HK"), "XIAOMI80": ("1810.HK", "HK"), "MEITUAN80": ("3690.HK", "HK"),
         "JD80": ("9618.HK", "HK"), "NDX01": ("3086.HK", "HK"), "TENCENT13": ("0700.HK", "HK"), "BABA13": ("9988.HK", "HK"), "TOYOTA80": ("7203.T", "JP"),
         "SONY80": ("6758.T", "JP"), "UNIQLO80": ("9983.T", "JP")}
FX = {"US": L.yahoo("THB=X"), "HK": L.yahoo("HKDTHB=X"), "JP": L.yahoo("JPYTHB=X")}
C = 0.0017
def daynum(t, off): return ((t + off * 3600) // 86400).astype(np.int64)
ROWS = {"open": [], "close": []}
for dr, (und, mk) in PAIRS.items():
    d = L.yahoo(dr + ".BK"); u = L.yahoo(und); fx = FX[mk]
    if d is None or u is None: continue
    dd = daynum(d["t"], 7); ud = daynum(u["t"], {"US": -5, "HK": 8, "JP": 9}[mk]); fd = daynum(fx["t"], 0)
    ok = d["v"] > 0
    po = np.full(len(dd), np.nan); pc = np.full(len(dd), np.nan)
    for i in range(len(dd)):
        if not ok[i]: continue
        j = int(np.searchsorted(ud, dd[i])) - 1 if mk == "US" else int(np.searchsorted(ud, dd[i], "right")) - 1   # US: last session before the Thai day; HK/JP: same day
        jo = int(np.searchsorted(ud, dd[i])) - 1                                # for the open rule always the previous completed underlying session
        f = int(np.searchsorted(fd, dd[i])) - 1                                 # FX close of the previous day
        if jo < 0 or f < 0 or dd[i] - ud[jo] > 5: continue
        po[i] = d["o"][i] / (u["c"][jo] * fx["c"][f])
        if mk != "US" and j >= 0 and ud[j] == dd[i]:
            f2 = int(np.searchsorted(fd, dd[i], "right")) - 1; pc[i] = d["c"][i] / (u["c"][j] * fx["c"][f2])
    for i in range(25, len(dd) - 1):
        mo = np.nanmedian(po[i - 20:i]); mc = np.nanmedian(pc[i - 20:i])
        if np.isfinite(po[i]) and np.isfinite(mo): ROWS["open"].append((int(d["t"][i]) * 1000, po[i] / mo - 1, d["c"][i] / d["o"][i] - 1 - 2 * C, mk, dr))
        if np.isfinite(pc[i]) and np.isfinite(mc) and ok[i + 1]: ROWS["close"].append((int(d["t"][i]) * 1000, pc[i] / mc - 1, d["o"][i + 1] / d["c"][i] - 1 - 2 * C, mk, dr))
for rule in ("open", "close"):
    R = ROWS[rule]; dev = np.array([r[1] for r in R]); ret = np.array([r[2] for r in R])
    print(f"\n=== {rule} rule: {len(R)} DR-days, {len(set(r[4] for r in R))} DRs, {L.ts(min(r[0] for r in R))[:10]}..{L.ts(max(r[0] for r in R))[:10]} | dev sd {np.nanstd(dev)*100:.2f}% | every day mean {ret.mean()*100:+.3f}% | corr(dev, ret) {np.corrcoef(dev, ret)[0,1]:+.3f}")
    for mk in ("ALL", "US", "HK", "JP"):
        for x in (0.005, 0.01, 0.015, 0.02, 0.03):
            for side, lab in ((1, "cheap -> long"), (-1, "rich  -> (short, not possible; shown as info)")):
                sel = [(r[0], r[2] if side > 0 else -(r[2] + 2 * C) - 2 * C) for r in R if (mk == "ALL" or r[3] == mk) and (r[1] <= -x if side > 0 else r[1] >= x)]
                if len(sel) < 20: continue
                st = L.stats(sel); pool = np.array([r[2] for r in R if mk == "ALL" or r[3] == mk])
                ms = np.array([np.random.default_rng(z).choice(pool, st["n"]).mean() * 100 for z in range(200)])
                print(L.fmt(f"{mk} dev {'<=-' if side>0 else '>=+'}{x*100:.1f}% {lab[:13]}", st, dict(mean=float(pool.mean() * 100), med=float(np.median(pool) * 100), p=float((ms >= st["mean"]).mean())))[:300])

# ---- data check: Yahoo's DR 'open' equals the previous close on many days (no real opening print) ----
print("\n=== stale-open check (US-underlying DRs) ===")
tot = []
for dr, (und, mk) in PAIRS.items():
    if mk != "US": continue
    d = L.yahoo(dr + ".BK"); u = L.yahoo(und)
    if d is None: continue
    gap = d["o"][1:] / d["c"][:-1] - 1; stale = float((np.abs(gap) < 1e-9).mean())
    ud = daynum(u["t"], -5); dd = daynum(d["t"], 7); ur = np.concatenate([[0], u["c"][1:] / u["c"][:-1] - 1])
    j = np.searchsorted(ud, dd[1:]) - 1; usr = ur[np.clip(j, 0, len(ur) - 1)]
    b_gap = np.polyfit(usr, gap, 1)[0]; b_oc = np.polyfit(usr, d["c"][1:] / d["o"][1:] - 1, 1)[0]
    tot.append((dr, stale, b_gap, b_oc))
    print(f"  {dr:10s} open == previous close on {stale*100:4.0f}% of days | beta of DR gap to last US session return {b_gap:+.2f} | beta of DR open->close to the same US return {b_oc:+.2f}")
print("  A real opening price would carry the US move in the gap (beta near 1) and leave nothing for open->close (beta near 0).")
R = ROWS["open"]
print("\nopen rule again, US DRs, only days where the Yahoo open differs from the previous close AND the first-bar is not the day's low/high artefact:")
keep = {}
for dr, (und, mk) in PAIRS.items():
    if mk != "US": continue
    d = L.yahoo(dr + ".BK")
    if d is None: continue
    for i in range(1, len(d["t"])):
        keep[(dr, int(d["t"][i]) * 1000)] = abs(d["o"][i] / d["c"][i - 1] - 1) > 1e-9
for x in (0.01, 0.02, 0.03):
    sel = [(r[0], r[2]) for r in R if r[3] == "US" and r[1] <= -x and keep.get((r[4], r[0]), False)]
    if len(sel) >= 20: print(L.fmt(f"US dev<=-{x*100:.0f}% long, open moved", L.stats(sel))[:260])
