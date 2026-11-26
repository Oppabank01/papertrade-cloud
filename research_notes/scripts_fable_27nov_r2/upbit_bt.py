"""Upbit caution / delisting notices -> trade the coin on Binance spot (proxy for the perp; fapi is blocked on GitHub).
All 823 'trade' notices 2017-2026. Kinds: warn (거래 유의 종목 지정), urge (유의 촉구), ext (연장), rel (지정 해제), delist (거래지원 종료).
Entry: open of the 1m bar that starts >= 2 minutes after the notice time. Holds 1h/4h/12h on 1m bars, 24h/72h/168h on
1h bars (entry = first 1h open >= notice + 2 min). Stop 15% checked first (short fills max(open, stop)*1.001). Cost
0.15%/side. Short for warn/urge/ext/delist, long for rel (and both sides shown). Control: random 1h entries in the same
coin within +-120 days, 200 seeds."""
import json, re, os, time, numpy as np, r2lib as L
from datetime import datetime
ns = json.load(open(f"{L.R2}/upbit_notices.json")); H = L.H
def kind(t):
    if "유의" in t and "연장" in t: return "ext"
    if "유의" in t and "해제" in t: return "rel"
    if "유의 촉구" in t: return "urge"
    if "유의 종목 지정" in t or "유의종목 지정" in t: return "warn"
    if "종료" in t and "지원" in t: return "delist"
    return None
EV = []
for x in ns:
    k = kind(x["title"])
    if not k: continue
    ts = int(datetime.fromisoformat(x.get("first_listed_at") or x["listed_at"]).timestamp() * 1000)
    for sym in set(re.findall(r"\(([A-Z0-9]{2,10})\)", x["title"])): EV.append((k, sym, ts))
print("events", len(EV), {k: sum(1 for e in EV if e[0] == k) for k in ("warn", "urge", "ext", "rel", "delist")})
def kl(sym, itv, start, limit):
    fn = f"{L.R2}/ub_{sym}_{itv}_{start}_{limit}.json"
    if os.path.exists(fn): return json.load(open(fn))
    try: k = json.loads(L.raw(f"https://api.binance.com/api/v3/klines?symbol={sym}USDT&interval={itv}&startTime={start}&limit={limit}", tries=2))
    except Exception: k = []
    k = [(x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]; json.dump(k, open(fn, "w")); time.sleep(0.03); return k
D = []
for k, sym, ts in EV:
    m = np.array(kl(sym, "1m", ts + 2 * 60000, 1000))
    if len(m) < 100 or m[0][0] - ts > 10 * 60000: continue
    h = np.array(kl(sym, "1h", ts - 30 * 24 * H, 1000))          # 30 days before .. 11 days after the notice (v1 used -120 d and never reached the event: 24h+ rows were empty)
    h2 = np.array(kl(sym, "1h", int(h[-1][0]) + H, 1000)) if len(h) == 1000 else np.zeros((0, 5))
    hh = np.vstack([h, h2]) if len(h2) else h
    if len(hh) < 50: continue
    D.append((k, sym, ts, m, hh))
print("with Binance spot data at the time", len(D), {k: sum(1 for e in D if e[0] == k) for k in ("warn", "urge", "ext", "rel", "delist")})
def one(kd, side, hold_h, stop=0.15):
    tr = []; ctl = []
    for k, sym, ts, m, hh in D:
        if k != kd: continue
        if hold_h <= 12: a = m; i = 0; hold = hold_h * 60
        else:
            a = hh; i = int(np.searchsorted(hh[:, 0], ts + 2 * 60000)); hold = hold_h
        if i >= len(a) or len(a) - i < hold * 0.9: continue
        x = L.sim(a, i, side, hold, stop)
        if x: tr.append((x[0], x[1]))
        hi = len(hh) - max(hold_h, 1) - 1
        if hi > 30: ctl.append((hh, hi))
    st = L.stats(tr)
    if st["n"] < 8: return f"{kd:6s} {'short' if side < 0 else 'long '} {hold_h:3d}h n={st['n']}"
    ms = []
    for z in range(200):
        rng = np.random.default_rng(z); rr = []
        for hh, hi in ctl:
            x = L.sim(hh, int(rng.integers(0, hi)), side, max(hold_h, 1), stop)
            if x: rr.append(x[1])
        ms.append(np.mean(rr) * 100)
    ms = np.array(ms)
    return L.fmt(f"{kd:6s} {'short' if side < 0 else 'long '} {hold_h:3d}h stop {stop}", st, dict(mean=float(ms.mean()), med=float(np.median(ms)), p=float((ms >= st["mean"]).mean())))
for kd in ("warn", "urge", "ext", "rel", "delist"):
    for side in (-1, 1):
        for hold in (1, 4, 12, 24, 72, 168):
            print(one(kd, side, hold))
    print()
for kd, side in (("warn", -1), ("delist", -1), ("rel", 1), ("urge", -1)):
    for hold in (4, 24):
        print(one(kd, side, hold, stop=None) + "  [no stop]")
# era split for the warn short
for kd, side, hold in (("warn", -1, 24), ("warn", -1, 4), ("delist", -1, 24), ("rel", 1, 24)):
    for lab, lo, hi in (("<=2022", 0, 1672531200000), ("2023-24", 1672531200000, 1735689600000), ("2025-26", 1735689600000, 9e15)):
        Dsave = D; D = [e for e in Dsave if lo <= e[2] < hi]; print(f"   {lab}: " + one(kd, side, hold)[:230]); D = Dsave
