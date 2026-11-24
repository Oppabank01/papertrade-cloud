#!/usr/bin/env python3
"""Forward paper test of the Raschke/Connors "Holy Grail" trend pullback as coded in Jordan-Johnson90/quant-strategy-research
(holy_grail_strategy.py, GitHub, Nov 2026) on BTC, ETH, SOL 1h bars (opened 24 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars: ADX14 (Wilder, ewm 1/14) above 30 and rising arms the setup; after a winning trade it waits
until ADX turns down once. Armed, the first bar whose low touches a rising EMA20 (previous low above it) sets a buy stop at
that bar's high, stop at its low, target at the highest high of the 100 bars before; while later bars keep touching the
EMA the order rolls to the new bar's high and the stop to the lowest low. The order lives 5 bars and dies when ADX drops to
30 or below. Mirrored for shorts. Exits on bar high/low (gap through -> open, both touched -> stop), else at the close of
the 50th bar. One position per coin, one third of the start per coin, 0.35% per side.
Left out from the repo: its single re-entry after a stop and the daily loss limit (both in futures dollars).
  state_fwd_hgrail.json       BTC, ETH, SOL
  state_fwd_hgrail_twin.json  control: random bars (TWIN_P per free bar) set the same kind of stop order, random side,
                              no rolling, same stop/target/50-bar exits
  python3 fwd_hgrail.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H1 = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo trades index futures
ADX_TH, WIN, LOOK, MAXB = 30.0, 5, 100, 50   # the repo's numbers (ADX 30, entry window 5 bars, swing lookback 100, 50 bars max)
EN, AN = 20, 14                # the repo's EMA20 and ADX14
WARM = 300                     # my choice: warm-up bars before the first signal
TWIN_P = 1 / 60                # my choice: gives about as many control trades as the rule (BTC 815 vs 818 since 2017)
LABEL = ("Holy Grail 1 ชม. (Raschke/Connors, Jordan-Johnson90) BTC ETH SOL: ADX14 เกิน 30 และกำลังขึ้น ราคาย่อแตะ EMA20 "
         "ตั้ง buy stop ที่ high ของแท่งนั้น stop ที่ low เป้าที่จุดสูงสุด 100 แท่ง ถือไม่เกิน 50 แท่ง short กลับกัน (เลขของ repo "
         "ตัด re-entry กับเพดานขาดทุนรายวันออก) (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 818 ไม้ -0.81% "
         "ETH 786 ไม้ -0.67% SOL 540 ไม้ -0.81% ต่อไม้ ก่อนหัก -0.11/+0.03/-0.11% เข้าสุ่ม -0.81/-0.82/-0.93% "
         "permutation 200 รอบ 3 ปีล่าสุด p 0.637/0.090/0.284 ติดลบทุกปี)")
ACCOUNTS = {"state_fwd_hgrail.json": ("rule", LABEL),
            "state_fwd_hgrail_twin.json": ("random", "Holy Grail ตัวควบคุม: แท่งสุ่ม ฝั่งสุ่ม ตั้ง stop order แบบเดียวกัน stop/เป้า/50 แท่งเหมือนกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ewm(v, k):
    out, e = [0.0] * len(v), None
    for i, x in enumerate(v):
        e = x if e is None else e + k * (x - e)
        out[i] = e
    return out


def ind(b):   # the repo's compute_indicators: EMA20 (span) and ADX from ewm(alpha 1/14, adjust=False)
    tr, pdm, mdm = [b[0]["h"] - b[0]["l"]], [0.0], [0.0]
    for i in range(1, len(b)):
        h, l, pc = b[i]["h"], b[i]["l"], b[i - 1]["c"]
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
        up, dn = h - b[i - 1]["h"], b[i - 1]["l"] - l
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    atr, ps, ms = ewm(tr, 1 / AN), ewm(pdm, 1 / AN), ewm(mdm, 1 / AN)
    dx = []
    for a, p, m in zip(atr, ps, ms):
        p, m = (100 * p / a, 100 * m / a) if a else (0.0, 0.0)
        dx.append(100 * abs(p - m) / (p + m) if p + m else 0.0)
    return ewm([x["c"] for x in b], 2 / (EN + 1)), ewm(dx, 1 / AN)


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))
    return ret


def open_pos(s, sym, d, e, stop, tgt, t, mode):
    usd = s["start_usd"] / 3
    if d > 0 and s["cash"] < usd * (1 + COST):
        return False
    s["cash"] += (-usd if d > 0 else usd) - usd * COST
    why = "ย่อแตะ EMA20 ตอน ADX เกิน 30 ทะลุ stop order" if mode == "rule" else "สุ่มแท่ง ฝั่งสุ่ม ทะลุ stop order"
    s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, stop=stop, tgt=tgt,
                         held=0, entry_t=t, t=iso(t), why=why)
    s["log"].append(dict(kind="buy", t=iso(t), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, stop_set=stop, tgt=tgt, why=why))
    return True


def bar(s, g, sym, b, e, adx, i, mode, rng):
    """One closed bar of the Holy Grail state machine (same order as the repo's loop)."""
    x, pv = b[i], b[i - 1]
    if adx[i] <= ADX_TH:
        g["armed"] = g["wait"] = False
    elif g["wait"]:
        if adx[i] < adx[i - 1]:
            g["wait"] = False
    elif adx[i] > adx[i - 1]:
        g["armed"] = True
    p = s["pos"].get(sym)
    if p is not None:
        p["held"] += 1
        d, o, h, l = p["d"], x["o"], x["h"], x["l"]
        if d > 0:
            px = o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None
        else:
            px = o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None
        why = None if px is None else ("stop" if (px - p["entry"]) * d < 0 else "ถึงเป้าจุดสูงสุด 100 แท่ง")
        if px is None and p["held"] >= MAXB:
            px, why = x["c"], "ครบ 50 แท่ง"
        if px is not None and close(s, sym, px, x["t"] + H1, why) > 0:
            g["armed"], g["wait"] = False, True
        return
    q = g["pend"]
    if q is not None:
        d = q["d"]
        if (x["h"] >= q["entry"]) if d > 0 else (x["l"] <= q["entry"]):
            g["pend"] = None
            en = max(q["entry"], x["o"]) if d > 0 else min(q["entry"], x["o"])
            # my choice: the fill bar is checked for the stop too (the repo skips it); stop first
            if open_pos(s, sym, d, en, q["stop"], q["tgt"], x["t"], mode) and ((x["l"] <= q["stop"]) if d > 0 else (x["h"] >= q["stop"])):
                close(s, sym, q["stop"], x["t"] + H1, "stop แท่งที่เข้า")
            return
        if mode == "rule" and ((x["l"] <= e[i]) if d > 0 else (x["h"] >= e[i])):
            q["ext"] = min(q["ext"], x["l"]) if d > 0 else max(q["ext"], x["h"])
            q["stop"], q["entry"] = q["ext"], (x["h"] if d > 0 else x["l"])
        if x["t"] >= q["exp_t"] or (mode == "rule" and adx[i] <= ADX_TH):
            g["pend"] = None
        return
    if mode == "rule":
        if not (g["armed"] and adx[i] > ADX_TH):
            return
        lt = x["l"] <= e[i] and pv["l"] > e[i - 1] and e[i] >= e[i - 1]
        st = x["h"] >= e[i] and pv["h"] < e[i - 1] and e[i] <= e[i - 1]
        if lt == st:
            return
        d = 1 if lt else -1
    else:
        if rng.random() >= TWIN_P:
            return
        d = rng.choice((1, -1))
    lo = max(0, i - LOOK)
    pa = max(y["h"] for y in b[lo:i]) if d > 0 else min(y["l"] for y in b[lo:i])
    en, ext = (x["h"], x["l"]) if d > 0 else (x["l"], x["h"])
    if (pa - en) * d > 0:
        g["pend"] = dict(d=d, entry=en, stop=ext, tgt=pa, exp_t=x["t"] + WIN * H1, ext=ext)


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    e, adx = ind(bars)
    g = s.setdefault("hg", {}).setdefault(sym, dict(armed=False, wait=False, pend=None))
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i < WARM:
            continue
        seen[sym] = x["t"]
        bar(s, g, sym, bars, e, adx, i, mode, rng)
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_hgrail fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
