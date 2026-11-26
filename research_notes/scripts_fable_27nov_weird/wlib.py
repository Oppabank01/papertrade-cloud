"""Shared helpers for the 27 Nov 'weird ideas' hunt. Standard library + numpy only, small memory.
- get(url): JSON GET with on-disk cache in the scratch folder
- klines(sym, interval, start_ms): Binance spot bars from data-api.binance.vision (reachable from GitHub US runners), cached as .npy
- sim(): one trade on OHLC arrays, stop checked first on every bar (long fills min(open, stop), short max(open, stop)*1.001)
- stats()/fmt(): n, mean, median, win rate, ex-best-1, ex-best-5, halves, t on day-clustered means
- rand_ctl(): random-entry control on the same asset, many seeds
"""
import json, os, time, hashlib, math, collections, urllib.request, numpy as np
SCR = "/private/tmp/claude-501/-Volumes-Drive-D-Code-Working-Space/ff910ff4-d0e5-4b35-9b50-810c88be183a/scratchpad/bt/weird"
os.makedirs(SCR, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
H = 3600000; D = 86400000
def raw(url, data=None, tries=4, timeout=30):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **({"Content-Type": "application/json"} if data else {})), data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
        except Exception as e:
            err = e; time.sleep(1.5 * (k + 1))
    raise err
def get(url, data=None, cache=True, tries=4):
    key = hashlib.md5((url + (data.decode() if data else "")).encode()).hexdigest()
    fn = f"{SCR}/c_{key}.json"
    if cache and os.path.exists(fn): return json.load(open(fn))
    j = json.loads(raw(url, data, tries))
    if cache: json.dump(j, open(fn, "w"))
    return j
def klines(sym, interval="1h", start=0, end=None, base="https://api.binance.com/api/v3"):
    # research fetch uses api.binance.com (4x faster from this Mac); data-api.binance.vision serves the same bars for cloud use
    """returns float64 array [t, o, h, l, c, quote_vol] of closed bars, cached"""
    fn = f"{SCR}/k_{sym}_{interval}_{start}.npy"
    if os.path.exists(fn): return np.load(fn)
    out = []; s = start; now = int(time.time() * 1000) if end is None else end
    while True:
        try: k = json.loads(raw(f"{base}/klines?symbol={sym}&interval={interval}&limit=1000&startTime={s}", tries=3))
        except Exception as e:
            if not out: return np.zeros((0, 6))
            raise
        if not k: break
        out += [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[7])) for x in k if x[6] < now]
        if len(k) < 1000 or k[-1][0] >= now: break
        s = k[-1][0] + 1; time.sleep(0.05)
    a = np.array(out, dtype=np.float64) if out else np.zeros((0, 6))
    np.save(fn, a); return a
def sim(a, i, side, hold, stop=None, tp=None, cost=0.0015, slip=0.001):
    """a: [t,o,h,l,c,...]; enter at open of bar i, exit at close of bar i+hold-1 unless stop/tp. returns (t_entry, net_ret, exit_idx) or None"""
    n = len(a)
    if i < 0 or i >= n: return None
    e = a[i, 1]
    if not e > 0: return None
    j1 = min(n, i + hold); px = None; j = None
    for k in range(i, j1):
        o, h, l = a[k, 1], a[k, 2], a[k, 3]
        if side > 0:
            if stop is not None and l <= e * (1 - stop): px = min(o, e * (1 - stop)); j = k; break
            if tp is not None and h >= e * (1 + tp): px = max(o, e * (1 + tp)) if k > i else e * (1 + tp); j = k; break
        else:
            if stop is not None and h >= e * (1 + stop): px = max(o, e * (1 + stop)) * (1 + slip); j = k; break
            if tp is not None and l <= e * (1 - tp): px = min(o, e * (1 - tp)) if k > i else e * (1 - tp); j = k; break
    if px is None: j = j1 - 1; px = a[j, 4]
    return (int(a[i, 0]), side * (px / e - 1) - 2 * cost, j)
def stats(tr):
    """tr: list of (t_ms, ret)"""
    tr = sorted(tr); r = np.array([x[1] for x in tr], dtype=float); n = len(r)
    if n < 8: return dict(n=n)
    day = collections.defaultdict(list)
    for x in tr: day[x[0] // D].append(x[1])
    dm = np.array([np.mean(v) for v in day.values()]); s = np.sort(r); h = n // 2
    return dict(n=n, mean=r.mean() * 100, med=np.median(r) * 100, wr=(r > 0).mean() * 100, ex1=s[:-1].mean() * 100,
                ex5=(s[:-5].mean() * 100 if n > 10 else float("nan")), h1=r[:h].mean() * 100, h2=r[h:].mean() * 100,
                t=dm.mean() / (dm.std() + 1e-12) * math.sqrt(len(dm)), days=len(dm), worst=s[0] * 100, best=s[-1] * 100,
                tmid=tr[h][0])
def fmt(name, st, ctl=None):
    if st["n"] < 8: return f"{name:50s} n={st['n']}"
    s = (f"{name:50s} n={st['n']:4d} mean={st['mean']:+6.2f} med={st['med']:+6.2f} wr={st['wr']:3.0f} ex1={st['ex1']:+6.2f} ex5={st['ex5']:+6.2f} "
         f"h1={st['h1']:+6.2f} h2={st['h2']:+6.2f} t={st['t']:+5.1f}({st['days']}d) worst={st['worst']:+5.0f} best={st['best']:+5.0f}")
    if ctl: s += f" | ctl mean={ctl['mean']:+6.2f} med={ctl['med']:+6.2f} p={ctl['p']:.3f}"
    return s
def rand_ctl(a, n, side, hold, stop=None, tp=None, cost=0.0015, seeds=200, lo=0, hi=None, mean_obs=None):
    """n random entries on the same asset between bar lo and hi, repeated for many seeds"""
    hi = (len(a) - hold - 1) if hi is None else hi; ms = []; md = []
    for k in range(seeds):
        rng = np.random.default_rng(100 + k); rr = []
        for i in rng.integers(lo, max(lo + 1, hi), n):
            x = sim(a, int(i), side, hold, stop, tp, cost)
            if x: rr.append(x[1])
        ms.append(np.mean(rr) * 100); md.append(np.median(rr) * 100)
    ms = np.array(ms)
    return dict(mean=float(ms.mean()), med=float(np.mean(md)), p=float((ms >= mean_obs).mean()) if mean_obs is not None else float("nan"), all=ms)
def ts(ms):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(ms / 1000))
