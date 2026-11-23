#!/usr/bin/env python3
"""Forward paper test of Boluwatifetade/crypto-trading-strategy "trend_pullback_1h" (GitHub, Nov 2026; the repo's
"Sweet Spot Gate Winner", BTC 1 year PF 1.215) on BTC, ETH, SOL (opened 24 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars: close above EMA200, close crosses above EMA50 (previous close at or below EMA50, this close
above), Wilder ADX14 above 20 and +DI above -DI -> long at the next open; mirrored -> short. Stop 2.5%, target 6% from
the entry, checked on bar high/low from the entry bar on (gap through -> open, both touched -> stop). No time stop, as
in the repo. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_tpull.json       BTC, ETH, SOL
  state_fwd_tpull_twin.json  control: random entry bars (TWIN_P per free bar), random side, same exits
  python3 fwd_tpull.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H1 = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo backtests BTC
ADX_TH, SL, TP = 20.0, 0.025, 0.06         # the repo's numbers
WARM = 201                     # my choice: warm-up bars for EMA200
TWIN_P = 1 / 150               # my choice: about the rule's signal rate (BTC 386 trades in 81k 1h bars, about 1 in 210)
LABEL = ("Trend pullback 1 ชม. (Boluwatifetade/Tadex) BTC ETH SOL: ปิดเหนือ EMA200 และตัดขึ้น EMA50 ADX14 เกิน 20 และ +DI "
         "เหนือ -DI long (short กลับกัน) stop 2.5% เป้า 6% ไม่มีเวลาถือสูงสุด (เลขของ repo) "
         "(backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 386 ไม้ -0.78% ETH 455 ไม้ -0.70% SOL 328 ไม้ -0.64% "
         "ต่อไม้ ก่อนหักราว 0% เข้าสุ่ม -0.57/-0.65/-0.63% permutation 200 รอบ p 0.682/0.463/0.234)")
ACCOUNTS = {"state_fwd_tpull.json": ("rule", LABEL),
            "state_fwd_tpull_twin.json": ("random", "Trend pullback ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 2.5% เป้า 6% แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    out, e, k = [None] * len(c), None, 2 / (n + 1)
    for i, v in enumerate(c):
        e = v if e is None else e + k * (v - e)
        out[i] = e
    return out


def wilder(b, n=14):   # same as the scout's /tmp/scout_0505/bt.py: ATR, +DI, -DI, ADX
    m = len(b)
    atr, pdi, mdi, adx = [None] * m, [None] * m, [None] * m, [None] * m
    tr_s = p_s = m_s = 0.0
    dxs, a = [], None
    for i in range(1, m):
        h, l, pc = b[i]["h"], b[i]["l"], b[i - 1]["c"]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        up, dn = h - b[i - 1]["h"], b[i - 1]["l"] - l
        pdm = up if up > dn and up > 0 else 0.0
        mdm = dn if dn > up and dn > 0 else 0.0
        if i <= n:
            tr_s += tr; p_s += pdm; m_s += mdm
            if i < n:
                continue
        else:
            tr_s = tr_s - tr_s / n + tr; p_s = p_s - p_s / n + pdm; m_s = m_s - m_s / n + mdm
        atr[i] = tr_s / n
        pdi[i] = 100 * p_s / tr_s if tr_s else 0.0
        mdi[i] = 100 * m_s / tr_s if tr_s else 0.0
        s = pdi[i] + mdi[i]
        dx = 100 * abs(pdi[i] - mdi[i]) / s if s else 0.0
        if a is None:
            dxs.append(dx)
            if len(dxs) == n:
                a = sum(dxs) / n
                adx[i] = a
        else:
            a = (a * (n - 1) + dx) / n
            adx[i] = a
    return atr, pdi, mdi, adx


def ind(b):   # same as bt.py sig_tp
    c = [x["c"] for x in b]
    e50, e200 = ema(c, 50), ema(c, 200)
    atr, pdi, mdi, adx = wilder(b)
    sig = [0] * len(b)
    for i in range(WARM, len(b)):
        if adx[i] is None or adx[i] <= ADX_TH:
            continue
        if c[i] > e200[i] and c[i - 1] <= e50[i - 1] and c[i] > e50[i] and pdi[i] > mdi[i]:
            sig[i] = 1
        elif c[i] < e200[i] and c[i - 1] >= e50[i - 1] and c[i] < e50[i] and mdi[i] > pdi[i]:
            sig[i] = -1
    return sig, atr


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sig, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            if hit is not None:
                close(s, sym, hit, x["t"] + H1, "stop 2.5%" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 6%")
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "rule":
            d = sig[i]
        else:
            d = rng.choice((1, -1)) if i >= WARM and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ย่อกลับข้าม EMA50 ตามเทรนด์ EMA200 ADX เกิน 20" if mode == "rule" else "สุ่มแท่ง ฝั่งสุ่ม"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e * (1 - d * SL), tgt=e * (1 + d * TP), entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_tpull fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
