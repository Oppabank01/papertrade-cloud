"""Round-2 helpers (27 Nov 2026). Reuses wlib (klines cache of round 1), adds a Yahoo daily/hourly fetch with events.
New cache files go to the r2 scratch folder."""
import sys, os, json, time, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts_fable_27nov_weird"))
import wlib
from wlib import klines, sim, stats, fmt, rand_ctl, ts, raw, H, D
R2 = wlib.SCR.replace("/weird", "/r2"); os.makedirs(R2, exist_ok=True)
def yahoo(sym, interval="1d", rng=None, refresh=False):
    """returns dict(t=np.int64 sec, o,h,l,c,v arrays (raw, split-adjusted, not dividend-adjusted), adj, div={ts:amount}, meta)"""
    fn = f"{R2}/y_{sym.replace('^','_').replace('=','_')}_{interval}_{rng or 'max'}.json"
    if os.path.exists(fn) and not refresh: j = json.load(open(fn))
    else:
        q = f"range={rng}" if rng else f"period1=0&period2={int(time.time())}"
        try: j = json.loads(raw(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?{q}&interval={interval}&events=div,split", tries=3))
        except Exception as e: j = {"chart": {"result": None, "error": str(e)}}
        json.dump(j, open(fn, "w")); time.sleep(0.35)
    r = (j.get("chart") or {}).get("result")
    if not r or "timestamp" not in r[0]: return None
    r = r[0]; q = r["indicators"]["quote"][0]; t = np.array(r["timestamp"], dtype=np.int64)
    f = lambda k: np.array([np.nan if x is None else x for x in q[k]], dtype=float)
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    d = dict(t=t, o=f("open"), h=f("high"), l=f("low"), c=f("close"), v=f("volume"),
             adj=np.array([np.nan if x is None else x for x in adj], dtype=float) if adj else None,
             div={int(v["date"]): float(v["amount"]) for v in (r.get("events", {}).get("dividends") or {}).values()},
             split={int(v["date"]): (v["numerator"], v["denominator"]) for v in (r.get("events", {}).get("splits") or {}).values()},
             meta=r["meta"])
    ok = np.isfinite(d["c"]) & np.isfinite(d["o"]) & (d["c"] > 0)
    for k in "tohlcv": d[k] = d[k][ok]
    if d["adj"] is not None: d["adj"] = d["adj"][ok]
    return d
def line(name, tr, ctl=None):
    st = stats(tr); return fmt(name, st, ctl), st
