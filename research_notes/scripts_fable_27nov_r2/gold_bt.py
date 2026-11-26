"""Thai gold price lag. Gold Traders Association bar SELL price, hourly buckets 2006-2026 (goldtraders.or.th/api/GoldPrices/ohlc),
last update of a day is before 18:00 Bangkok, shops in malls stay open to about 21:00 and sell at that stale price.
Rule: at decision hour (19/20/21 Bangkok) look at PAXG (Binance, trades 24/7) since the end of the association's last bucket.
If PAXG is up >= thr, buy a bar at the stale SELL price, sell at the association's first BUY price of the next session
(= first sell price - spread). Spread 100 THB (history) and 200 THB (what the API shows on 26 Nov 2026). Long only, no stop
(no market to stop in). Controls: every evening, and random evenings (200 seeds)."""
import json, time, calendar, numpy as np, r2lib as L
g = json.load(open(f"{L.R2}/gt_ohlc.json"))
def utc_ms(s): return (calendar.timegm(time.strptime(s, "%Y-%m-%dT%H:%M:%S")) - 7 * 3600) * 1000
G = np.array([(utc_ms(x["hour"]), x["open"], x["high"], x["low"], x["close"]) for x in g]); G = G[np.argsort(G[:, 0])]
P = L.klines("PAXGUSDT", "1h", 0); pt = P[:, 0].astype(np.int64)
print("gold buckets", len(G), L.ts(G[0, 0]), L.ts(G[-1, 0]), "| PAXG 1h", len(P), L.ts(P[0, 0]), L.ts(P[-1, 0]))
def paxg_open(t):
    i = np.searchsorted(pt, t)
    return P[i, 1] if i < len(pt) and pt[i] == t else None
H = L.H; DAY = L.D
# sessions: group buckets by Bangkok date
bkk_day = ((G[:, 0] + 7 * H) // DAY).astype(np.int64)
def build(dec_h, weekend=False):
    """returns list of (t_dec, signal, stale_ask, next_open, gap_days, dow)"""
    out = []
    days = np.unique(bkk_day)
    for d in days:
        idx = np.where(bkk_day == d)[0]; last = idx[-1]
        dow = time.gmtime(d * 86400).tm_wday          # 0=Mon .. 5=Sat
        if weekend != (dow == 5): continue
        t_last_end = int(G[last, 0]) + H               # end of the last bucket (conservative reference)
        t_dec = d * DAY - 7 * H + dec_h * H + (DAY if weekend else 0)   # weekend: decide on Sunday
        if last + 1 >= len(G) or G[last + 1, 0] <= t_dec: continue
        p0 = paxg_open(t_last_end); p1 = paxg_open(t_dec)
        if not p0 or not p1: continue
        out.append((t_dec, p1 / p0 - 1, G[last, 4], G[last + 1, 1], (G[last + 1, 0] - t_dec) / DAY, dow))
    return out
def run(ev, thr, spread, prem=0.0, lo=None, hi=None):
    tr = [(t, (nx - spread) / (ask + prem) - 1) for t, s, ask, nx, gd, dw in ev if (lo is None or s >= lo) and (hi is None or s < hi) and s >= thr]
    return tr
for weekend in (False, True):
    print("\n===", "Saturday price, decide Sunday" if weekend else "weekday evening", "===")
    for dec_h in ((19, 20, 21) if not weekend else (12, 20)):
        ev = build(dec_h, weekend)
        allr = np.array([(nx - 100) / ask - 1 for t, s, ask, nx, gd, dw in ev]); sig = np.array([e[1] for e in ev])
        print(f"\ndecision {dec_h}:00 Bangkok  sessions {len(ev)}  {L.ts(ev[0][0])} .. {L.ts(ev[-1][0])}  corr(signal, gap) {np.corrcoef(sig, allr)[0,1]:+.2f}"
              f"  every-evening mean (spread 100) {allr.mean()*100:+.3f}%  median PAXG signal {np.median(sig)*100:+.2f}%  sd {sig.std()*100:.2f}%")
        for thr in (0.002, 0.003, 0.005, 0.0075, 0.01, 0.015):
            for spread in (100, 200):
                tr = run(ev, thr, spread)
                if len(tr) < 8: continue
                st = L.stats(tr); rng_means = []
                for k in range(200):
                    rr = np.random.default_rng(k).choice(len(ev), len(tr), replace=False)
                    rng_means.append(np.mean([(ev[i][3] - spread) / ev[i][2] - 1 for i in rr]) * 100)
                rng_means = np.array(rng_means)
                ctl = dict(mean=float(rng_means.mean()), med=float(np.median(rng_means)), p=float((rng_means >= st["mean"]).mean()))
                print(L.fmt(f"  PAXG up>={thr*100:.2f}% spread {spread}", st, ctl))
        # yearly + premium scenario for the 0.5% rule
        tr = run(ev, 0.005, 100)
        by = {}
        for t, r in tr: by.setdefault(time.gmtime(t / 1000).tm_year, []).append(r)
        print("  yearly (thr 0.5%, spread 100):", " ".join(f"{y}:n{len(v)} {np.mean(v)*100:+.2f}" for y, v in sorted(by.items())))
        for prem in (100, 300):
            tr = run(ev, 0.005, 200, prem)
            if len(tr) >= 8: print(L.fmt(f"  thr 0.5% spread 200 + bar premium {prem} THB", L.stats(tr)))
        # the mirror: PAXG down -> the stale price is too high; nothing to do long-only (shops buy back at stale bid: sell signal)
        trs = [(t, (ask - spread_ - nx) / ask) for t, s, ask, nx, gd, dw in ev for spread_ in (100,) if s <= -0.005]
        if len(trs) >= 8: print(L.fmt("  holder's rule: PAXG down>=0.5%, sell tonight at stale bid, rebuy next first ask (gain vs holding)", L.stats(trs)))
