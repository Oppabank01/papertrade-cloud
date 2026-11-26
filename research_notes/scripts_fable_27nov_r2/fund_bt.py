"""Funding settlement micro-drift on spot. Binance spot 5m bars 2020-2026 (BTC, ETH, SOL) around 00:00/08:00/16:00 UTC,
split by the funding rate paid at that settlement (round-1 cache of fapi fundingRate). Windows in minutes relative to T.
Gross mean in bp with t-stat; then the best-looking windows as trades with 0.15%/side."""
import pickle, numpy as np, r2lib as L
SCR0 = L.wlib.SCR.replace("/weird", ""); M5 = 300000
WIN = [(-60, -5), (-30, -5), (-15, 0), (-5, 0), (0, 5), (0, 15), (0, 30), (5, 60), (-30, 30), (0, 60), (0, 240)]
BK = [("<=-0.01%", -1, -0.0001), ("-0.01..0.005%", -0.0001, 0.00005), ("0.005..0.02%", 0.00005, 0.0002), ("0.02..0.05%", 0.0002, 0.0005), (">=0.05%", 0.0005, 1)]
best = []
for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
    A = L.klines(sym, "5m", 1577836800000); t = A[:, 0].astype(np.int64); o = A[:, 1]
    F = pickle.load(open(f"{SCR0}/fund_{sym}.pkl", "rb"))
    print(f"\n{sym}: 5m bars {len(A)} {L.ts(t[0])}..{L.ts(t[-1])}, settlements {len(F)}")
    def px(T, m):
        i = np.searchsorted(t, T + m * 60000)
        return o[i] if i < len(t) and t[i] == T + m * 60000 else np.nan
    rows = {b[0]: {w: [] for w in WIN} for b in BK}; ts_ = {b[0]: [] for b in BK}
    for T, r in F:
        T = (T // 3600000) * 3600000
        if T < t[0] + 3600000 or T > t[-1] - 5 * 3600000: continue
        b = next(x[0] for x in BK if x[1] <= r < x[2]); ts_[b].append(T)
        for w in WIN: rows[b][w].append(px(T, w[1]) / px(T, w[0]) - 1)
    print("  bucket            n   " + "  ".join(f"[{a:+d},{b:+d}]".rjust(11) for a, b in WIN))
    for b in BK:
        n = len(ts_[b[0]])
        if n < 20: continue
        cells = []
        for w in WIN:
            v = np.array(rows[b[0]][w]); v = v[np.isfinite(v)]; m = v.mean() * 1e4; tt = v.mean() / (v.std() + 1e-12) * np.sqrt(len(v)); cells.append(f"{m:+6.1f}({tt:+4.1f})")
            best.append((abs(tt), sym, b[0], w, m, tt, len(v), v, np.array(ts_[b[0]])[np.isfinite(np.array(rows[b[0]][w]))]))
        print(f"  {b[0]:15s} {n:5d}   " + "  ".join(cells))
print("\nlargest |t| cells as trades after 0.30% round trip (direction chosen after the fact, so this is the optimistic view):")
for at, sym, b, w, m, tt, n, v, T in sorted(best, key=lambda x: -x[0])[:8]:
    side = 1 if m > 0 else -1; tr = list(zip(T.tolist(), (side * v - 0.003).tolist())); st = L.stats(tr)
    print(L.fmt(f"{sym[:3]} {b} [{w[0]:+d},{w[1]:+d}] {'long' if side > 0 else 'short'}", st)[:250])
