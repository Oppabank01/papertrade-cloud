#!/usr/bin/env python3
"""Forward paper test of ShuWayne/crypto-trading-intelligence-terminal strategy v3-B "Range Mean-Reversion" (GitHub,
pre-registered 19 Nov 2026, the repo's own forward test started the same day), opened 23 Nov 2026 by the scout. The
backtest (LABEL) loses before costs and does worse than random entries; opened anyway because the user asked to try
weak ideas too. Fake money only.

On closed 4h bars (the repo's docs/strategy.md): |SMA20 - SMA50| <= 1% of close and the 20-bar swing range (highs and
lows of the 20 bars before) >= 4 ATR14; the bar's true range <= 2.5 ATR. Long: the low of this or the previous bar
<= swing low + 0.5 ATR, min RSI14 of the two < 32, green bar closing in its upper half, RSI <= 40. Short mirrored
(swing high - 0.5 ATR, max RSI > 68, red bar in the lower half, RSI >= 60). Enter at the next open (the repo fills at
the signal close), stop 1.5 ATR, target 3 ATR, out at the close of the 24th bar held; a gap through the stop fills at
the open, both touched = stop. Left out: the optional move of the stop to breakeven and the 2-entries-a-day cap.
One position per coin, one half of the start per coin, 0.35% per side.
  state_fwd_v3b.json       BTC, SOL (the repo's two symbols)
  state_fwd_v3b_twin.json  control: random entry bars (TWIN_P per free bar), random side, same exits
  python3 fwd_v3b.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "SOLUSDT"]  # the repo trades only these two
SL, TP, CAP = 1.5, 3.0, 24     # the repo's stop, target (ATR) and 96 h time cap in 4h bars
TWIN_P = 1 / 120               # my choice: about the rule's rate in the backtest (171 BTC trades in 20,290 bars)
LABEL = ("v3-B range mean-reversion (ShuWayne) 4 ชม. BTC SOL: SMA20 กับ SMA50 ห่างไม่เกิน 1% กรอบ 20 แท่งกว้าง 4 ATR ขึ้นไป "
         "แตะขอบล่างใน 0.5 ATR RSI ต่ำกว่า 32 แท่งเขียวปิดครึ่งบน ซื้อ (short กลับกัน) stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 24 แท่ง "
         "(backtest Binance 4 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 171 ไม้ -1.17% SOL 64 ไม้ -1.78% ETH 127 ไม้ -1.34% ต่อไม้ "
         "ก่อนหัก -0.47/-1.08/-0.64% ชนะ 28-31% permutation 200 รอบ p 0.92/0.85/0.89 แย่กว่าตัวเข้าสุ่มทุกเหรียญ)")
ACCOUNTS = {"state_fwd_v3b.json": ("rule", LABEL),
            "state_fwd_v3b_twin.json": ("random", "v3-B ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 1.5 ATR เป้า 3 ATR ถือไม่เกิน 24 แท่งแบบเดียวกัน")}


def ind(b):   # same as the scout's /tmp/scout_2325_v3b.py
    n, c = len(b), [x["c"] for x in b]
    sma20, sma50, rsi, atr, sh, sl = [None] * n, [None] * n, [None] * n, [None] * n, [None] * n, [None] * n
    s20 = s50 = ag = al = a = 0.0
    for i in range(n):
        s20 += c[i]; s50 += c[i]
        if i >= 20:
            s20 -= c[i - 20]
            sh[i] = max(x["h"] for x in b[i - 20:i]); sl[i] = min(x["l"] for x in b[i - 20:i])
        if i >= 50:
            s50 -= c[i - 50]
        if i >= 19:
            sma20[i] = s20 / 20
        if i >= 49:
            sma50[i] = s50 / 50
        if i == 0:
            continue
        d = c[i] - c[i - 1]; g, l = max(d, 0), max(-d, 0)
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        if i <= 14:
            ag += g / 14; al += l / 14; a += tr / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14; a = (a * 13 + tr) / 14
        if i >= 14:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al); atr[i] = a
    return sma20, sma50, rsi, atr, sh, sl


def signal(b, i, I):
    sma20, sma50, rsi, atr, sh, sl = I
    if i < 100 or None in (sma50[i], atr[i], sh[i], rsi[i - 1]):   # the repo's 100-bar warm-up
        return 0
    x, p = b[i], b[i - 1]
    if abs(sma20[i] - sma50[i]) > 0.01 * x["c"] or sh[i] - sl[i] < 4 * atr[i]:
        return 0
    if max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) > 2.5 * atr[i]:
        return 0
    mid = (x["h"] + x["l"]) / 2
    if min(x["l"], p["l"]) <= sl[i] + 0.5 * atr[i] and min(rsi[i], rsi[i - 1]) < 32 and x["c"] > x["o"] and x["c"] > mid and rsi[i] <= 40:
        return 1
    if max(x["h"], p["h"]) >= sh[i] - 0.5 * atr[i] and max(rsi[i], rsi[i - 1]) > 68 and x["c"] < x["o"] and x["c"] < mid and rsi[i] >= 60:
        return -1
    return 0


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
    I = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            p["held"] = p.get("held", 0) + 1      # closed bars since the entry bar, counted like the backtest
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            why = None if hit is None else "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 3 ATR"
            if hit is None and p["held"] >= CAP:
                hit, why = x["c"], "ถือครบ 24 แท่ง"
            if hit is not None:
                close(s, sym, hit, x["t"] + H4, why)
                exited = True
        if sym in s["pos"] or exited or not I[3][i]:
            continue
        if mode == "rule":
            d = signal(bars, i, I)
        else:
            d = rng.choice((1, -1)) if i >= 100 and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 2
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "แตะขอบกรอบ RSI สุด แท่งกลับตัว" if mode == "rule" else "สุ่มแท่ง สุ่มฝั่ง"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, held=0,
                             stop=e - d * SL * I[3][i], tgt=e + d * TP * I[3][i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_v3b fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
