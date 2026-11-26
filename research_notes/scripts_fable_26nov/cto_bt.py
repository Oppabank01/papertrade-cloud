# Backtest "CTO after the dev rugs" (Hrundel75) on pump.fun graduates vs random-entry control.
# Inputs: ../grad.pkl (minute bars, post-graduation PumpSwap pool), dev*.pkl (creator token balance history from Solana RPC),
# ds.pkl (DexScreener paid orders), sol.pkl (SOLUSDT minute closes), creators.pkl.
import pickle, glob, random, statistics as st, math, sys, bisect
G = pickle.load(open("../grad.pkl", "rb")); CR = pickle.load(open("creators.pkl", "rb")); SOL = pickle.load(open("sol.pkl", "rb"))
DEV = {}
for f in glob.glob("dev[0-9].pkl"): DEV.update(pickle.load(open(f, "rb")))
try: DS = pickle.load(open("ds.pkl", "rb"))
except Exception: DS = {}
try: BC = pickle.load(open("bc.pkl", "rb"))
except Exception: BC = {}
USE_BC = "-nobc" not in sys.argv
try:
    for m, nb in pickle.load(open("fresh.pkl", "rb")).items():      # newer pool bars for coins whose CTO order came after grad.pkl was fetched
        last = G[m]["bars"][-1][0]; G[m]["bars"] = G[m]["bars"] + [b for b in nb if b[0] > last]
except Exception: pass
for m, v in G.items():                      # prepend bonding-curve minute bars (pre-graduation) when fetched
    if v and v.get("bars"):
        v["pool0"] = v["bars"][0][0]
        if USE_BC and BC.get(m): v["bars"] = [b for b in BC[m] if b[0] < v["pool0"]] + v["bars"]
FEED = set()
if "-nofeed" not in sys.argv:
    try:
        F1 = pickle.load(open("feed.pkl", "rb")); F2 = pickle.load(open("feed_dev.pkl", "rb"))
        for m, v in F1.items():
            if m in G or not v["bars"] or m not in F2 or not F2[m]["dev"] or not F2[m]["iscreate"]: continue
            bars = v["bars"] if USE_BC else [b for b in v["bars"] if b[0] >= v["pool0"]]
            if not bars: continue
            G[m] = dict(sym=v["sym"], bars=bars, pool0=v["pool0"]); DEV[m] = F2[m]["dev"]; DS[m] = v["orders"]; FEED.add(m)
    except Exception as e: print("feed not loaded", e)
COST, STOP, TRAIL = 0.02, 0.18, 0.15
MINVOL = float(next((a.split("=")[1] for a in sys.argv if a.startswith("-minvol=")), 500))   # USD volume required in the bar before entry
MINMC = float(next((a.split("=")[1] for a in sys.argv if a.startswith("-minmc=")), 0))    # min market cap (price * 1e9) at entry
def tradable(b, i):
    return i >= 1 and b[i - 1][5] >= MINVOL and b[i][1] * 1e9 >= MINMC and b[i][0] - b[i - 1][0] <= 600
solk = sorted(SOL)
def solusd(t):
    i = bisect.bisect_right(solk, t) - 1
    return SOL[solk[max(i, 0)]]

def dev_dump(m):
    """Dev dump = first creator SELL tx after which creator balance <= 10% of its running peak (peak >= 0.1% of supply).
    status: dump / hold / none (never held) / transfer (went to ~0 by transfer, not a sell) / nodata."""
    d = DEV.get(m)
    if d is None: return dict(status="nodata")
    if "-no200" in sys.argv and d["nsig"] >= 200: return dict(status="nodata")
    h = [x for x in d["hist"] if x["t"]]
    h.sort(key=lambda x: (x["t"], -x["pre"]))
    if not h: return dict(status="none")
    peak = 0.0; sold = 0.0; soldsol = 0.0
    for x in h:
        peak = max(peak, x["pre"], x["post"]); dec = x["pre"] - x["post"]
        if dec <= 0: continue
        is_sell = x["kind"] == "sell" or (x["sol"] is not None and x["sol"] > 0.001)
        if is_sell and x["sol"] and x["sol"] > 0: sold += dec; soldsol += x["sol"]
        if peak >= 1e6 and x["post"] <= 0.1 * peak:
            if not is_sell: return dict(status="transfer", peak=peak)
            px = (x["sol"] / dec) if (x["sol"] and x["sol"] > 0) else (soldsol / sold if sold else None)
            return dict(status="dump", T=x["t"], P_sol=px, P_vwap_sol=soldsol / sold if sold else None, peak=peak, nsig=d["nsig"], sampled="sampled" in d["note"])
    if peak < 1e6: return dict(status="none")
    return dict(status="hold", peak=peak, last=h[-1]["post"])

def cto_time(m, T, mode):
    """mode: 'cto' = communityTakeover order paid after T ; 'profile' = any tokenProfile/communityTakeover order paid after T ; 'none'."""
    if mode == "none": return T
    o = (DS.get(m) or {}).get("orders") or []
    ts = [x["paymentTimestamp"] / 1000 for x in o if x.get("paymentTimestamp") and x["paymentTimestamp"] / 1000 > T
          and (x["type"] == "communityTakeover" or (mode == "profile" and x["type"] == "tokenProfile"))]
    return min(ts) if ts else None

def run_trade(bars, i, target):
    """Enter at open of bars[i]. Stop-first per bar. Returns net return incl. 2% per side."""
    e = bars[i][1]; stop = e * (1 - STOP); half_done = False; peak = None; legs = []
    if target and target <= e: legs.append((0.5, e)); half_done = True; peak = e      # already at/above dev level: half is sold at entry
    for j in range(i, len(bars)):
        t, o, h, l, c, v = bars[j]
        s = stop if not half_done else max(stop, peak * (1 - TRAIL))
        if l <= s:
            legs.append((1.0 - sum(w for w, _ in legs), min(o, s))); break
        if not half_done and target and h >= max(target, e):
            legs.append((0.5, max(target, e))); half_done = True; peak = max(h, target)
        elif half_done: peak = max(peak, h)
    else:
        legs.append((1.0 - sum(w for w, _ in legs), bars[-1][4]))
    return sum(w * (px * (1 - COST) / (e * (1 + COST)) - 1) for w, px in legs), half_done

def recovery_idx(bars, T, rec):
    """First bar index k (after T) whose close >= (1+rec) * post-dump low, low set in an earlier bar. Proxy for holder count +15%."""
    lo = None
    for k, b in enumerate(bars):
        if b[0] + 60 <= T: continue
        if lo is not None and b[4] >= lo * (1 + rec): return k
        lo = b[3] if lo is None else min(lo, b[3])
    return None

def stats(r):
    if not r: return dict(n=0)
    n = len(r); m = st.mean(r); s = st.stdev(r) if n > 1 else float("nan")
    srt = sorted(r, reverse=True)
    return dict(n=n, mean=m, med=st.median(r), win=sum(x > 0 for x in r) / n, t=(m / (s / math.sqrt(n)) if n > 1 and s > 0 else float("nan")),
                ex1=st.mean(srt[1:]) if n > 1 else float("nan"), ex5=st.mean(srt[5:]) if n > 5 else float("nan"))
def fmt(s):
    if not s.get("n"): return "n=0"
    return "n=%d mean=%+.1f%% med=%+.1f%% win=%.0f%% t=%.2f ex1=%+.1f%% ex5=%+.1f%%" % (s["n"], s["mean"] * 100, s["med"] * 100, s["win"] * 100, s["t"], s["ex1"] * 100, s["ex5"] * 100)

coins = [m for m in G if G[m] and G[m].get("bars")]
info = {m: dev_dump(m) for m in coins}
from collections import Counter
print("tradability filter for rule AND control: prev-bar volume >= $%.0f, entry mcap >= $%.0f, prev bar within 10 min" % (MINVOL, MINMC))
print("mode:", "pool bars + bonding-curve bars where fetched" if USE_BC else "pool (post-graduation) bars only", "| CTO-feed coins added:", len(FEED))
print("coins with bars", len(coins), "dev status", dict(Counter(v["status"] for v in info.values())))
dump = {}
for m, v in info.items():
    if v["status"] != "dump": continue
    b = G[m]["bars"]; ps = v["P_sol"] or v["P_vwap_sol"]
    if not ps: continue
    v["P"] = ps * solusd(v["T"]); v["pre_grad"] = v["T"] < G[m]["pool0"]; v["has_bc"] = (bool(BC.get(m)) or m in FEED) and USE_BC
    k = next((j for j, x in enumerate(b) if x[0] + 60 > v["T"]), None); v["bar_px"] = b[k][1] if k is not None and b[k][0] <= v["T"] else None
    dump[m] = v
print("dev peak holding among dumps (%% of 1e9 supply) median: %.1f%% | dumps with >=200 ATA signatures (history truncated): %d | sampled histories: %d" % (st.median([v["peak"] / 1e7 for v in dump.values()]) if dump else 0, sum(v["nsig"] >= 200 for v in dump.values()), sum(v["sampled"] for v in dump.values())))
print("dev dumps with price", len(dump), "| before first pool bar (bonding curve):", sum(v["pre_grad"] for v in dump.values()), "| after:", sum(not v["pre_grad"] for v in dump.values()))
if "-ppre" in sys.argv:                     # alternative "dev sell level": open of the minute bar in which the dev crossed 90% sold (pre-dump level)
    for v in dump.values():
        if v["bar_px"]: v["P"] = max(v["P"], v["bar_px"])
print("dev sell level used as target:", "max(dev execution price, open of dump minute bar)" if "-ppre" in sys.argv else "dev execution price of the sell that crossed 90% (SOL received / tokens * SOLUSD)")
rat = sorted(v["P_sol"] * solusd(v["T"]) / v["bar_px"] if v["P_sol"] else v["P"] / v["bar_px"] for v in dump.values() if v["bar_px"])
if rat: print("sanity dev sell price / open of that minute bar: n=%d median=%.2f p10=%.2f p90=%.2f" % (len(rat), rat[len(rat)//2], rat[len(rat)//10], rat[len(rat)*9//10]))
print("dump coins with bonding-curve bars merged:", sum(v["has_bc"] for v in dump.values()), "| dump coins whose bars cover the dump minute:", len(rat))
print("DexScreener orders fetched", len(DS), "| dump coins with CTO order after dump:", sum(cto_time(m, v["T"], "cto") is not None for m, v in dump.items()),
      "| with any profile/CTO order after dump:", sum(cto_time(m, v["T"], "profile") is not None for m, v in dump.items()))

def rule_trades(mode, rec, need_below=True, delay=0):
    tr = {}; skip = Counter()
    for m, v in dump.items():
        b = G[m]["bars"]; tc = cto_time(m, v["T"], mode)
        if tc is None: skip["no_cto"] += 1; continue
        k = recovery_idx(b, v["T"], rec) if rec is not None else next((k for k, x in enumerate(b) if x[0] + 60 > v["T"]), None)
        if k is None: skip["no_recovery"] += 1; continue
        sig_t = max(b[k][0] + 60, tc + (delay if mode != "none" else 0))                       # signal known at close of bar k / at CTO payment time
        i = next((j for j in range(len(b)) if b[j][0] >= sig_t), None)
        if i is None or i >= len(b) - 1: skip["no_bar_after_signal"] += 1; continue
        if need_below and b[i][1] >= v["P"]: skip["already_above_dev_level"] += 1; continue
        if not tradable(b, i): skip["illiquid_at_signal"] += 1; continue
        r, half = run_trade(b, i, v["P"])
        tr[m] = dict(r=r, half=half, i=i, sym=G[m]["sym"], ratio=v["P"] / b[i][1], pre=v["pre_grad"], curve=b[i][0] < G[m]["pool0"], feed=m in FEED, wait=(b[i][0] - v["T"]) / 60)
    return tr, skip

def control(coinset, seeds=2000, need_below=True):
    elig = {}
    for m in coinset:
        v = dump[m]; b = G[m]["bars"]
        e = [j for j in range(len(b) - 1) if b[j][0] > v["T"] and (not need_below or b[j][1] < v["P"]) and tradable(b, j)]
        if e: elig[m] = e
    cache = {}; means = []; agg = Counter(); allr = []
    for s in range(seeds):
        rnd = random.Random(s); rs = []
        for m, e in elig.items():
            j = rnd.choice(e)
            if (m, j) not in cache: cache[(m, j)] = run_trade(G[m]["bars"], j, dump[m]["P"])[0]
            rs.append(cache[(m, j)])
        S = stats(rs); means.append(S["mean"])
        for k in ("mean", "med", "win", "t", "ex1", "ex5"):
            if not math.isnan(S[k]): agg[k] += S[k]; agg["c_" + k] += 1
        allr += rs
    avg = {k: agg[k] / agg["c_" + k] if agg["c_" + k] else float("nan") for k in ("mean", "med", "win", "t", "ex1", "ex5")}
    avg["n"] = len(elig)
    return avg, means

ALLR = {}
for name, mode, rec, nb in [("A strict: dev dump + CTO order + recovery15, entry below dev level", "cto", 0.15, True), ("A2: same as A but entry allowed above dev level (half sold at once)", "cto", 0.15, False),
                        ("B: dev dump + new DexScreener profile/CTO order + recovery15, entry below dev level", "profile", 0.15, True), ("B2: same as B but entry allowed above dev level (half sold at once)", "profile", 0.15, False),
                        ("C: dev dump + recovery15 (no CTO filter)", "none", 0.15, True), ("D: dev dump + recovery30 (no CTO filter)", "none", 0.30, True), ("E: dev dump only, first bar after dump", "none", None, True)]:
    tr, skip = rule_trades(mode, rec, nb, 300 if "-delay5" in sys.argv else 0)
    rs = [x["r"] for x in tr.values()]; S = stats(rs)
    print("\n==", name); print("  skipped:", dict(skip))
    print("  RULE   ", fmt(S), "| half-target hit: %d | entries on bonding curve: %d | from CTO feed: %d | median wait after dump: %s min" % (sum(x["half"] for x in tr.values()), sum(x["curve"] for x in tr.values()), sum(x["feed"] for x in tr.values()), ("%.0f" % st.median([x["wait"] for x in tr.values()])) if tr else "-"))
    for lab, sub in (("post-graduation entries only", [x["r"] for x in tr.values() if not x["curve"]]), ("bonding-curve entries only", [x["r"] for x in tr.values() if x["curve"]])):
        if sub and len(sub) != len(rs): print("     ", lab, fmt(stats(sub)))
    ALLR[name] = tr
    if len(rs) >= 2:
        avg, means = control(list(tr), need_below=nb); p = sum(x >= S["mean"] for x in means) / len(means)
        print("  CONTROL same coins, random bar after dump (avg of 2000 seeds):", fmt(avg), "| seed-mean 5/50/95 pct: %+.1f%% / %+.1f%% / %+.1f%%" % tuple(sorted(means)[int(len(means) * q)] * 100 for q in (0.05, 0.5, 0.95)))
        print("  share of control seeds with mean >= rule mean: %.3f   rule minus control mean: %+.1f pp" % (p, (S["mean"] - avg["mean"]) * 100))
    if "-v" in sys.argv:
        for m, x in sorted(tr.items(), key=lambda kv: -kv[1]["r"]): print("   ", x["sym"][:12].ljust(12), m[:6], "r=%+.1f%%" % (x["r"] * 100), "target/entry=%.2f" % x["ratio"], "half" if x["half"] else "", "devDumpOnCurve" if x["pre"] else "devDumpAfterGrad", "entryOnCurve" if x["curve"] else "", "FEED" if x["feed"] else "", "wait=%.0fm" % x["wait"])
avg, means = control(list(dump))
print("\n== CONTROL all dump coins, random bar after dump below dev level:", fmt(avg))
ratios = [x["ratio"] for x in ALLR.get("C: dev dump + recovery15 (no CTO filter)", {}).values()]
nod = [m for m, v in info.items() if v["status"] in ("hold", "none", "transfer") and len(G[m]["bars"]) >= 3]
if ratios and nod:
    agg = Counter(); means = []; ELIG = {}
    for sd in range(1000):
        rnd = random.Random(10_000 + sd); rs = []
        for m in nod:
            b = G[m]["bars"]; e = ELIG.get(m)
            if e is None: e = ELIG[m] = [j for j in range(len(b) - 1) if tradable(b, j)]
            if not e: continue
            j = rnd.choice(e); rs.append(run_trade(b, j, b[j][1] * rnd.choice(ratios))[0])
        S = stats(rs); means.append(S["mean"])
        for k in ("mean", "med", "win", "t", "ex1", "ex5"): agg[k] += S[k]
    avg = {k: agg[k] / 1000 for k in ("mean", "med", "win", "t", "ex1", "ex5")}; avg["n"] = sum(1 for e in ELIG.values() if e)
    print("== CONTROL coins WITHOUT dev dump (hold/none/transfer), random bar, target ratio sampled from rule C trades:", fmt(avg))
pickle.dump(dict(info=info, trades=ALLR), open("bt_info.pkl", "wb"))
if "-dbg" in sys.argv:
    pre = sys.argv[sys.argv.index("-dbg") + 1]; nm = sys.argv[sys.argv.index("-dbg") + 2]
    m = [k for k in G if k.startswith(pre)][0]; t = ALLR[[k for k in ALLR if k.startswith(nm)][0]].get(m); b = G[m]["bars"]; v = dump[m]
    print(G[m]["sym"], "T", v["T"], "P", v["P"], "trade", t, "nbars", len(b), "orders", (DS.get(m) or {}).get("orders"))
    if t:
        for x in b[max(0, t["i"] - 3):t["i"] + 12]: print("   ", x[0], ["%.3g" % y for y in x[1:5]], round(x[5]))
