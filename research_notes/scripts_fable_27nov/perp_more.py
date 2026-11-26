#!/usr/bin/env python3
"""More memecoin-perp checks: (a) quarter and symbol breakdown of the funding-spike short, (b) 'trapped longs' variant,
(c) 4h momentum / reversal, (d) weekly and daily cross-sectional momentum vs reversal inside the meme set.
  python3 perp_more.py <perp.pkl> <perp_old.pkl> [seeds=20]"""
import sys, collections, datetime as dt, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import perplib as P
SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 20; N = 0
def roll_ret(c, k): r = np.full(len(c), np.nan); r[k:] = c[k:] / c[:-k] - 1; return r
def first_cross(mask): m = mask.astype(bool); return [int(i) + 1 for i in np.nonzero(m & ~np.r_[False, m[:-1]])[0]]
def fspike(d, x, cond=None):
    out = []; r24 = roll_ret(d["c"], 24)
    for ft, fr in zip(d["ft"], d["fr"]):
        if fr < x: continue
        i = int(np.searchsorted(d["t"], ft))
        if i < 25 or i >= len(d["t"]): continue
        if cond == "down" and not r24[i - 1] <= 0: continue
        if cond == "up" and not r24[i - 1] > 0: continue
        out.append(i)
    return out
def go(name, D, U, fn, side, hold, stop, skip, ctl=False, hedge=None):
    global N; N += 1
    ev = {s: [i for i in fn(D[s]) if i >= skip] for s in U}
    if ctl: P.report(name, D, ev, side, hold, stop, hedge, pool=U, seeds=SEEDS); return P.run(D, ev, side, hold, stop, hedge)
    tr, meta = P.run(D, ev, side, hold, stop, hedge); st = P.stats(tr)
    if st["n"] < 8: print(f"{name:46s} n={st['n']}"); return tr, meta
    print(f"{name:46s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} "
          f"h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} tday={st['tday']:+5.1f}({st['days']}) worst={st['worst']:+5.0f} syms={len(set(m[0] for m in meta))}", flush=True)
    return tr, meta
for tag, fn_ in (("MAIN Jul25-Nov26", sys.argv[1]), ("OOS Jan-Jun25", sys.argv[2])):
    D = P.load(fn_); ME = sorted(s for s in D if D[s]["kind"] == "meme"); skip = 24 * 14 if tag.startswith("MAIN") else 24 * 8
    print(f"\n######## {tag}")
    tr, meta = go("C3 meme fund>=0.100% h72 sl15", D, ME, lambda d: fspike(d, .001), -1, 72, .15, skip)
    q = collections.defaultdict(list); sy = collections.defaultdict(list)
    for (t, r, _), (s, i) in zip(tr, meta):
        d_ = dt.datetime.fromtimestamp(t / 1000, dt.UTC); q[f"{d_.year}Q{(d_.month - 1) // 3 + 1}"].append(r); sy[s].append(r)
    print("   by quarter:", "  ".join(f"{k}:{np.mean(v) * 100:+.1f}({len(v)})" for k, v in sorted(q.items())))
    print("   by symbol :", "  ".join(f"{k[:-4]}:{np.mean(v) * 100:+.1f}({len(v)})" for k, v in sorted(sy.items(), key=lambda kv: -len(kv[1]))[:14]))
    print("   symbol-equal mean: %+.2f over %d symbols, %d%% of symbols positive" % (np.mean([np.mean(v) for v in sy.values()]) * 100, len(sy), 100 * np.mean([np.mean(v) > 0 for v in sy.values()])))
    go("C3b fund>=0.1% & r24<=0 (trapped longs) h72 sl15", D, ME, lambda d: fspike(d, .001, "down"), -1, 72, .15, skip, ctl=tag.startswith("MAIN"))
    go("C3c fund>=0.1% & r24>0 (still squeezing) h72 sl15", D, ME, lambda d: fspike(d, .001, "up"), -1, 72, .15, skip)
    go("C3h fund>=0.1% h72 sl15, long BTC hedge", D, ME, lambda d: fspike(d, .001), -1, 72, .15, skip, hedge="BTCUSDT")
    print("-- 4h momentum / reversal, memes")
    go("A1 long  r4h>=+8% h12 sl8", D, ME, lambda d: first_cross(roll_ret(d["c"], 4) >= .08), 1, 12, .08, skip, ctl=tag.startswith("MAIN"))
    go("A2 long  r4h<=-8% h12 sl8", D, ME, lambda d: first_cross(roll_ret(d["c"], 4) <= -.08), 1, 12, .08, skip, ctl=tag.startswith("MAIN"))
    go("A3 short r4h>=+8% h12 sl8", D, ME, lambda d: first_cross(roll_ret(d["c"], 4) >= .08), -1, 12, .08, skip)
    go("A4 short r4h<=-8% h12 sl8", D, ME, lambda d: first_cross(roll_ret(d["c"], 4) <= -.08), -1, 12, .08, skip)
    print("-- cross-sectional inside memes (top 5 vs bottom 5 by lookback return, equal weight, both legs cost 0.3% RT + funding)")
    t0 = min(D[s]["t"][0] for s in ME); t1 = max(D[s]["t"][-1] for s in ME)
    for lb, hold in ((168, 168), (24, 24)):
        mom = []; t = t0 + (skip + lb) * P.H
        t += (-t) % (hold * P.H)
        while t + hold * P.H <= t1:
            rk = []
            for s in ME:
                d = D[s]; i = int(np.searchsorted(d["t"], t))
                if i < max(lb, skip) or i >= len(d["t"]) - hold or d["t"][i] != t: continue
                rk.append((d["c"][i - 1] / d["c"][i - 1 - lb] - 1, s, i))
            rk.sort()
            if len(rk) >= 15:
                lo = [P.sim(D, s, i, 1, hold, 9.9) for _, s, i in rk[:5]]; hi = [P.sim(D, s, i, 1, hold, 9.9) for _, s, i in rk[-5:]]
                sl = [P.sim(D, s, i, -1, hold, 9.9) for _, s, i in rk[:5]]; sh = [P.sim(D, s, i, -1, hold, 9.9) for _, s, i in rk[-5:]]
                if all(lo + hi + sl + sh):
                    mom.append((t, (np.mean([x[1] for x in hi]) + np.mean([x[1] for x in sl])) / 2, (np.mean([x[1] for x in lo]) + np.mean([x[1] for x in sh])) / 2))
            t += hold * P.H
        N += 2
        for nm, k in (("momentum (long top5, short bottom5)", 1), ("reversal (long bottom5, short top5)", 2)):
            st = P.stats([(x[0], x[k], 0) for x in mom])
            if st["n"] >= 8: print(f"X lb{lb}h hold{hold}h {nm:38s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex5={st['ex5']:+6.2f} h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} tday={st['tday']:+5.1f}")
print("\nsettings tried:", N)
