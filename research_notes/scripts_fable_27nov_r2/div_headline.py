"""Headline spec, strictest timing: buy the CLOSING auction 6 trading days before XD (close of i-6), sell the closing auction
of the last cum-dividend day (close of i-1). 5 trading days held. Stop 8% checked first on the lows of i-5..i-1.
Also: share of event-entry days where Yahoo's open equals the previous close (why the open-entry rows are less clean)."""
import os, json, time, collections, numpy as np, r2lib as L
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_deep.py")).read()
head = src.split("# 1) day-by-day gross profile")[0]; fn_src = "def tr_pre" + src.split("def tr_pre")[1].split('print("\\n=== grid')[0]
OOS = json.load(open(f"{L.R2}/oos_tickers.json")); U = {}
for lab, repl in (("first list", None), ("fresh list", "for s in OOS:")):
    g = {"OOS": OOS, "__file__": os.path.abspath(__file__)}; exec(head if repl is None else head.replace("for s in SET:", repl), g); exec(fn_src, g); U[lab] = g
def tr(g, n, ymin, stop, extra=0.0, liq=0):
    return [g["tr_pre"](s, i, amt, n, 1, stop, extra)[:2] for s, i, amt in g["EV"] if amt / g["S"][s]["c"][i - 1 - n] >= ymin and g["S"][s]["liq"][i - 1 - n] >= liq]
for ymin in (0.03, 0.04, 0.05):
    for stop, extra, liq in ((None, 0, 0), (0.08, 0, 0), (0.08, 0.0025, 0), (0.08, 0, 5e6), (0.08, 0, 2e7)):
        rows = []
        for lab, g in U.items(): rows.append((lab, tr(g, 5, ymin, stop, extra, liq)))
        rows.append(("pooled", rows[0][1] + rows[1][1]))
        for lab, t in rows:
            st = L.stats(t); e = lambda a, b: [r for tt, r in t if a <= time.gmtime(tt / 1000).tm_year < b]
            print(L.fmt(f"y>={ymin*100:.0f}% stop {stop} +{extra*100:.2f}% liq>={liq/1e6:.0f}M {lab}", st)[:222] + f" | 10-17 {np.mean(e(2010,2018))*100:+.2f} 18-22 {np.mean(e(2018,2023))*100:+.2f} 23-26 n{len(e(2023,2030))} {np.mean(e(2023,2030))*100:+.2f}")
for lab, g in U.items():
    a = b = c = d_ = 0
    for s, i, amt in g["EV"]:
        d = g["S"][s]; a += abs(d["o"][i - 6] / d["c"][i - 7] - 1) < 1e-9; b += 1
    for s, d in g["S"].items():
        c += int((np.abs(d["o"][1:] / d["c"][:-1] - 1) < 1e-9).sum()); d_ += len(d["o"]) - 1
    print(f"{lab}: Yahoo open == previous close on {a/b*100:.0f}% of entry days (all days {c/d_*100:.0f}%)")
