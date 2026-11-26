"""Binance 'Maintenance Updates' catalog (CMS 157), 619 notices Feb 2022 - Nov 2026.
upgrade: 'Binance Will Support the X (TICKER) Network Upgrade & Hard Fork - DATE' (364), maint: 'Wallet Maintenance for X
Network (TICKER)' (82), swap: token swap / rebrand / migration (43). Trade the ticker on Binance spot 1h bars.
Entry at the first 1h open after the notice (or at 00:00 UTC of the upgrade date for the 'event' rows). Stop 15% checked
first. Cost 0.15%/side. Control: random hours in the same coin within the fetched window (20 days before to 21 days after), 200 seeds."""
import json, re, os, time, calendar, numpy as np, r2lib as L
H = L.H; ns = json.load(open(f"{L.R2}/bn_maint.json"))
def kind(t):
    if "Completed" in t or "Completes" in t: return None
    if "Hard Fork" in t or "Network Upgrade" in t: return "upgrade"
    if "Wallet Maintenance for" in t: return "maint"
    if any(k in t for k in ("Token Swap", "Rebranding", "Redenomination", "Migration", "Merge")): return "swap"
    return None
def kl(sym, start):
    fn = f"{L.R2}/bm_{sym}_{start}.json"
    if os.path.exists(fn): return json.load(open(fn))
    try: k = json.loads(L.raw(f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval=1h&startTime={start}&limit=1000", tries=2))
    except Exception: k = []
    k = [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]; json.dump(k, open(fn, "w")); time.sleep(0.03); return k
EV = []
for x in ns:
    k = kind(x["title"])
    if not k: continue
    syms = [s for s in re.findall(r"\(([A-Z0-9]{2,10})\)", x["title"]) if s not in ("USDT", "USDC", "BUSD", "FDUSD")]
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})\s*$", x["title"]); ev_t = calendar.timegm((int(m.group(1)), int(m.group(2)), int(m.group(3)), 0, 0, 0)) * 1000 if m else None
    for s in syms[:1]: EV.append((k, s, (x["releaseDate"] // H + 1) * H, ev_t))
print("events", len(EV), {k: sum(1 for e in EV if e[0] == k) for k in ("upgrade", "maint", "swap")})
D = []
for k, s, t, et in EV:
    a = np.array(kl(s, t - 20 * 24 * H))     # 20 days before .. 21 days after (v1 used -40 d and ended 1.6 d after the notice)
    if len(a) < 990: continue
    D.append((k, s, t, et, a))
print("with Binance spot data", len(D), {k: sum(1 for e in D if e[0] == k) for k in ("upgrade", "maint", "swap")})
lead = np.array([(e[3] - e[2]) / 86400000 for e in D if e[0] == "upgrade" and e[3]]); print(f"upgrade notices: days from notice to the upgrade date: median {np.median(lead):.1f}, p10 {np.percentile(lead,10):.1f}, p90 {np.percentile(lead,90):.1f}")
def one(kd, side, mode, hold, stop=0.15, sub=None):
    tr = []; ctl = []
    for k, s, t, et, a in D:
        if k != kd or (sub and not sub(t)): continue
        if mode == "notice": t0 = t; h = hold
        elif mode == "runup":
            if not et or et - t < 24 * H: continue
            t0 = t; h = int((et - t) // H)
        else:
            if not et or et < t: continue
            t0 = et; h = hold
        i = int(np.searchsorted(a[:, 0], t0))
        if i >= len(a) or a[i, 0] != t0 or len(a) - i < h: continue
        x = L.sim(a, i, side, h, stop)
        if x: tr.append((x[0], x[1])); ctl.append((a, h))
    st = L.stats(tr)
    if st["n"] < 8: return f"{kd} {mode} n={st['n']}"
    ms = []
    for z in range(200):
        rng = np.random.default_rng(z); rr = [L.sim(a, int(rng.integers(0, len(a) - h - 1)), side, h, stop)[1] for a, h in ctl]; ms.append(np.mean(rr) * 100)
    ms = np.array(ms)
    return L.fmt(f"{kd} {'long' if side > 0 else 'short'} {mode} {hold if mode != 'runup' else 'to-date'}h", st, dict(mean=float(ms.mean()), med=float(np.median(ms)), p=float((ms >= st["mean"]).mean())))[:300]
for side in (1, -1):
    for hold in (24, 72, 168): print(one("upgrade", side, "notice", hold))
    print(one("upgrade", side, "runup", 0))
    for hold in (24, 72, 168): print(one("upgrade", side, "event", hold))
    for hold in (24, 72): print(one("maint", side, "notice", hold))
    for hold in (24, 72, 168): print(one("swap", side, "notice", hold))
    print()
