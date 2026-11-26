"""Out-of-sample universe for the pre-XD rule: 252 SET/mai common stocks that were NOT in the first list (picked by current
turnover from the TradingView scanner, before looking at any of their prices). Same code, same rules, nothing re-tuned."""
import os, json, time, collections, numpy as np
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_deep.py")).read()
head = src.split("# 1) day-by-day gross profile")[0]
import r2lib as L
OOS = json.load(open(f"{L.R2}/oos_tickers.json"))
head = head.replace("for s in SET:", "for s in OOS:")
exec(head); exec("def tr_pre" + src.split("def tr_pre")[1].split('print("\\n=== grid')[0])
src5 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "div_n5.py")).read()
exec("def tr_open" + src5.split("def tr_open")[1].split("for n in (5, 6):")[0])
prof = collections.defaultdict(list)
for s, i, amt in EV:
    c = S[s]["c"]
    if amt / c[i - 11] < 0.03: continue
    for k in range(-12, 4): prof[k].append((c[i + k] + (amt if k == 0 else 0)) / c[i + k - 1] - 1)
print("daily gross mean bp, y>=3%, offsets -12..+3: " + " ".join(f"{k:+d}:{np.mean(prof[k])*1e4:+.0f}" for k in range(-12, 4)))
for n in (5, 6):
    for ymin in (0.0, 0.03, 0.04, 0.05):
        for liq in (0, 5e6):
            e = ysel(EV, n, ymin, liq=liq); lab = f"OOS n={n} y>={ymin*100:.0f}% liq>={liq/1e6:.0f}M"
            report(f"{lab} close i-{n+1} -> close i-1", e, n, ctl=(liq == 0))
            rep2(f"{lab} OPEN i-{n} -> close i-1", e, lambda s, i, amt: tr_open(s, i, amt, n))
            rep2(f"{lab} OPEN i-{n} -> close i-1 stop 8%", e, lambda s, i, amt: tr_open(s, i, amt, n, stop=0.08))
            rep2(f"{lab} OPEN i-{n} -> close i-1 +0.25%/side", e, lambda s, i, amt: tr_open(s, i, amt, n, extra=0.0025))
