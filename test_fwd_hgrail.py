"""fwd_hgrail.py walking bars one at a time (state saved between runs) gives the same trades as the scout's backtest
(/tmp/scout_0652/bt.py hg_run, copied below as ref_*)."""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / ".claude/skills/market-timeseries/scripts"))
import mts
import fwd_hgrail as P, byttrade as B


def ref_ema(c, n=None, alpha=None):
    k = alpha if alpha else 2 / (n + 1)
    out, e = [0.0] * len(c), None
    for i, v in enumerate(c):
        e = v if e is None else e + k * (v - e)
        out[i] = e
    return out


def ref_ind(b, n=14, en=20):
    m = len(b)
    tr, pdm, mdm = [b[0]["h"] - b[0]["l"]], [0.0], [0.0]
    for i in range(1, m):
        h, l, pc = b[i]["h"], b[i]["l"], b[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - b[i - 1]["h"], b[i - 1]["l"] - l
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    a = 1 / n
    atr, ps, ms = ref_ema(tr, alpha=a), ref_ema(pdm, alpha=a), ref_ema(mdm, alpha=a)
    dx = []
    for i in range(m):
        p = 100 * ps[i] / atr[i] if atr[i] else 0.0
        q = 100 * ms[i] / atr[i] if atr[i] else 0.0
        dx.append(100 * abs(p - q) / (p + q) if p + q else 0.0)
    return ref_ema([x["c"] for x in b], en), ref_ema(dx, alpha=a)


def ref_bar(st_, b, e, adx, i):
    x, pv = b[i], b[i - 1]
    if adx[i] <= P.ADX_TH:
        st_["armed"] = st_["wait"] = False
    elif st_["wait"]:
        if adx[i] < adx[i - 1]:
            st_["wait"] = False
    elif adx[i] > adx[i - 1]:
        st_["armed"] = True
    p = st_["pos"]
    if p is not None:
        p["held"] += 1
        d, o, h, l = p["d"], x["o"], x["h"], x["l"]
        if d > 0:
            px = o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None
        else:
            px = o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None
        if px is None and p["held"] >= P.MAXB:
            px = x["c"]
        if px is None:
            return None
        st_["pos"] = None
        if (px - p["entry"]) * d > 0:
            st_["armed"], st_["wait"] = False, True
        return (d, p["entry"], px)
    q = st_["pend"]
    if q is not None:
        d = q["d"]
        if (x["h"] >= q["entry"]) if d > 0 else (x["l"] <= q["entry"]):
            en = max(q["entry"], x["o"]) if d > 0 else min(q["entry"], x["o"])
            st_["pend"] = None
            st_["pos"] = dict(d=d, entry=en, stop=q["stop"], tgt=q["tgt"], held=0)
            if (x["l"] <= q["stop"]) if d > 0 else (x["h"] >= q["stop"]):
                st_["pos"] = None
                return (d, en, q["stop"])
            return None
        if (x["l"] <= e[i]) if d > 0 else (x["h"] >= e[i]):
            q["ext"] = min(q["ext"], x["l"]) if d > 0 else max(q["ext"], x["h"])
            q["stop"], q["entry"] = q["ext"], (x["h"] if d > 0 else x["l"])
        if i >= q["exp"] or adx[i] <= P.ADX_TH:
            st_["pend"] = None
        return None
    if not (st_["armed"] and adx[i] > P.ADX_TH):
        return None
    lt = x["l"] <= e[i] and pv["l"] > e[i - 1] and e[i] >= e[i - 1]
    stt = x["h"] >= e[i] and pv["h"] < e[i - 1] and e[i] <= e[i - 1]
    if lt == stt:
        return None
    d = 1 if lt else -1
    lo = max(0, i - P.LOOK)
    pa = max(y["h"] for y in b[lo:i]) if d > 0 else min(y["l"] for y in b[lo:i])
    en, ext = (x["h"], x["l"]) if d > 0 else (x["l"], x["h"])
    if (pa - en) * d > 0:
        st_["pend"] = dict(d=d, entry=en, stop=ext, tgt=pa, exp=i + P.WIN, ext=ext)
    return None


total = 0
for sym in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
    b = [dict(x, closed=True) for x in mts.bars("binance", sym, "1h")[-2500:]]
    assert all(y["t"] - x["t"] == P.H1 for x, y in zip(b, b[1:])), sym   # expiry by time equals expiry by bar count
    e, adx = ref_ind(b)
    st_, want = dict(armed=False, wait=False, pend=None, pos=None), []
    for i in range(301, len(b) - 1):        # the walk never sees the last bar closed
        t = ref_bar(st_, b, e, adx, i)
        if t:
            want.append((t[0], round(t[1], 6), round(t[2], 6)))
    s = B.new_state("t"); s["seen"] = {sym: b[300]["t"]}
    for k in range(302, len(b) + 1):
        P.step(s, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "rule", random.Random(1))
        s = json.loads(json.dumps(s))        # state goes through the json file between runs
    buys = [x for x in s["log"] if x["kind"] == "buy"]; sells = [x["px"] for x in s["log"] if x["kind"] == "sell"]
    got = [(1 if x["side"] == "long" else -1, round(x["px"], 6), round(p, 6)) for x, p in zip(buys, sells)]
    assert got == want, (sym, len(got), len(want), got[:3], want[:3])
    total += len(got)
assert total > 5, total
t = B.new_state("t"); t["seen"] = {sym: b[300]["t"]}
for k in range(302, len(b) + 1):
    P.step(t, sym, b[:k - 1] + [dict(b[k - 1], closed=False)], "random", random.Random(k))
assert any(x["kind"] == "sell" for x in t["log"])
print(f"{total} trades match the backtest; ok")
