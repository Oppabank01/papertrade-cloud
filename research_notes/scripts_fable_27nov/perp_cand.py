#!/usr/bin/env python3
"""Robustness for the two perp candidates from perp_bt.py: neighbours, out-of-sample half-year (Jan-Jun 2025),
non-meme alts, and funding/price decomposition.
  python3 perp_cand.py <perp.pkl> <perp_old.pkl> [seeds=20]"""
import sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent)); import perplib as P
SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 20; N = 0
def roll_ret(c, k): r = np.full(len(c), np.nan); r[k:] = c[k:] / c[:-k] - 1; return r
def first_cross(mask): m = mask.astype(bool); return [int(i) + 1 for i in np.nonzero(m & ~np.r_[False, m[:-1]])[0]]
def fspike(d, x): return [int(np.searchsorted(d["t"], ft)) for ft, fr in zip(d["ft"], d["fr"]) if fr >= x]
def line(name, D, univ, fn, side, hold, stop, ctl=True, skip=24 * 14):
    global N; N += 1
    ev = {s: [i for i in fn(D[s]) if i >= skip] for s in univ}
    if ctl: return P.report(name, D, ev, side, hold, stop, pool=univ, seeds=SEEDS)
    tr, meta = P.run(D, ev, side, hold, stop); st = P.stats(tr)
    if st["n"] < 8: print(f"{name:46s} n={st['n']}"); return st
    print(f"{name:46s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} "
          f"h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} tday={st['tday']:+5.1f}({st['days']}) worst={st['worst']:+5.0f} syms={len(set(m[0] for m in meta))}", flush=True); return st
for tag, fn_ in (("MAIN Jul25-Nov26", sys.argv[1]), ("OOS Jan-Jun25", sys.argv[2])):
    D = P.load(fn_); ME = sorted(s for s in D if D[s]["kind"] == "meme"); ALT = sorted(s for s in D if D[s]["kind"] == "alt")
    skip = 24 * 14 if tag.startswith("MAIN") else 24 * 8        # OOS file starts 1 Jan 2025: need 7d of history only
    print(f"\n######## {tag}: memes {len(ME)} alts {len(ALT)}")
    for un, U in (("meme", ME), ("alt", ALT)):
        print(f"-- C1 short after 7d run-up first crosses X ({un})")
        for x in (.75, 1.0, 1.5):
            for hold in (24, 72, 168):
                line(f"C1 {un} r7d>=+{x:.0%} h{hold} sl25", D, U, lambda d, x=x: first_cross(roll_ret(d["c"], 168) >= x), -1, hold, .25, ctl=(x == 1.0 and hold == 72), skip=skip)
        line(f"C1 {un} r7d>=+100% h72 sl40", D, U, lambda d: first_cross(roll_ret(d["c"], 168) >= 1.0), -1, 72, .40, ctl=False, skip=skip)
        print(f"-- C3 short after a funding print >= X ({un})")
        for x in (.00075, .001, .0015, .002):
            for hold in (24, 72):
                line(f"C3 {un} fund>={x:.3%} h{hold} sl15", D, U, lambda d, x=x: fspike(d, x), -1, hold, .15, ctl=(x == .001), skip=skip)
        line(f"C3 {un} fund>=0.100% h72 sl25", D, U, lambda d: fspike(d, .001), -1, 72, .25, ctl=False, skip=skip)
        line(f"C3 {un} fund>=0.100% h168 sl15", D, U, lambda d: fspike(d, .001), -1, 168, .15, ctl=False, skip=skip)
        keep = P.fund; P.fund = lambda d, a, b: 0.0
        line(f"C3 {un} fund>=0.100% h72 sl15 PRICE ONLY", D, U, lambda d: fspike(d, .001), -1, 72, .15, ctl=False, skip=skip)
        line(f"C1 {un} r7d>=+100% h72 sl25 PRICE ONLY", D, U, lambda d: first_cross(roll_ret(d["c"], 168) >= 1.0), -1, 72, .25, ctl=False, skip=skip)
        P.fund = keep
print("\nsettings tried:", N)
