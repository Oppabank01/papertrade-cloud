#!/usr/bin/env python3
"""Forward paper test of haralampije1/tiny-bot-entry "MACD + CCI" (GitHub, 26 Nov 2026, an AI-built entry for make.fun's
"Tiny Bot, Easy $2: Beat Buy-and-Hold on Solana" bounty on hourly bars of 7 Solana tokens) on the four of its tokens that
Binance spot lists: SOL, ETH (its WETH), WIF, RAY (opened 26 Nov 2026 by the scout; backtest in LABEL, opened at any p
because the user asked to try weak ideas too). Fake money only.

On closed 1h Binance bars, long only, as main.py: MACD from EMA8 and EMA21 (both seeded with the mean of the first 21
closes, the fast one with the last 8 of them), signal EMA5 seeded with the mean of the first 5 MACD values, CCI10 on the
typical price with the 0.015 constant. MACD above signal and CCI <= -40 -> long at the next open. Every later closed bar:
the close below the highest close since entry (or the fill price) x 0.97 (3% trailing stop), or MACD below signal, or
CCI >= 500 -> out at the next open. Indicators run over the bars this script is given.
One position per coin, one quarter of the start per coin, 0.35% per side.
  state_fwd_macdcci.json       SOL, ETH, WIF, RAY
  state_fwd_macdcci_twin.json  control: random entry bars (TWIN_P per free bar), same exits
  python3 fwd_macdcci.py"""
import random
import statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here (the bounty charges its own fee and slippage)
SYMS = ["SOLUSDT", "ETHUSDT", "WIFUSDT", "RAYUSDT"]   # my choice: the bounty's 7 tokens minus JITOSOL, POPCAT, FARTCOIN (not on Binance spot)
FAST, SLOW, SIG, CCI_N, CCI_K = 8, 21, 5, 10, 0.015   # main.py
CCI_BUY, CCI_SELL, TRAIL = -40.0, 500.0, 0.03          # main.py (its 5% initial stop is declared but never used)
TWIN_P = 1 / 55                # my choice: about the rule's entry rate (941 SOL entries in 55,139 1h bars, 1 in 59; RAY 1 in 50)
# also mine: fills at the next open (the bounty fills on its own engine), size one quarter of the start per coin in place of
# equity / 7, and bars with zero volume are not skipped (main.py skips them; Binance bars of these coins always trade)
LABEL = ("MACD + CCI ย่อ 1 ชม. (haralampije1/tiny-bot-entry บอทแข่ง make.fun) SOL ETH WIF RAY: MACD 8/21/5 อยู่เหนือเส้นสัญญาณ "
         "และ CCI10 ไม่เกิน -40 ซื้อ ออกเมื่อปิดต่ำกว่าจุดสูงสุดหลังเข้า 3% หรือ MACD ตัดลงใต้สัญญาณ หรือ CCI ถึง 500 "
         "(backtest Binance 1 ชม. ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง SOL 941 ไม้ -0.64% ต่อไม้ มัธยฐาน -1.19% ชนะ 24% "
         "ETH 1,210 ไม้ -0.62% WIF 476 ไม้ -0.89% RAY 922 ไม้ -0.58% ก่อนหัก +0.06/+0.08/-0.19/+0.12% ถือเฉลี่ย 8 ชม. "
         "ตัวแฝดเข้าสุ่ม -0.6 ถึง -0.8% permutation 200 รอบบน 20,000 แท่งล่าสุด กริด 4 แบบ (CCI -40/-100 x trail 3/5%) "
         "p 0.114/0.861/0.597/0.970)")
ACCOUNTS = {"state_fwd_macdcci.json": ("rule", LABEL),
            "state_fwd_macdcci_twin.json": ("random", "MACD + CCI ย่อ 1 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ออกด้วย trail 3% และ MACD ตัดลงแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def signals(b):
    """per bar 'up', 'down' or None, exactly as push_bar in main.py"""
    out, warm, f, s, macds, sg, typ = [], [], None, None, [], None, []
    for x in b:
        c = x["c"]
        if s is None:
            warm.append(c)
            if len(warm) == SLOW:
                s, f = st.fmean(warm), st.fmean(warm[SLOW - FAST:])
        else:
            f = (c - f) * (2 / (FAST + 1)) + f
            s = (c - s) * (2 / (SLOW + 1)) + s
        m = None
        if s is not None:
            m = f - s
            if sg is not None:
                sg = (m - sg) * (2 / (SIG + 1)) + sg
            else:
                macds.append(m)
                if len(macds) == SIG:
                    sg = st.fmean(macds)
        tp = (x["h"] + x["l"] + c) / 3
        typ.append(tp)
        if len(typ) > CCI_N:
            typ.pop(0)
        if m is None or sg is None:
            out.append(None)
            continue
        mu = st.fmean(typ)
        spread = sum(abs(v - mu) for v in typ)
        dev = tp - mu
        cci = 0 if dev == 0 or spread == 0 else dev / (CCI_K * (spread / CCI_N))
        out.append("up" if m > sg and cci <= CCI_BUY else "down" if m < sg or cci >= CCI_SELL else None)
    return out


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
    sg = signals(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["entry_t"]:
                continue
            p["hi"] = max(p["hi"], x["c"])
            why = ("ปิดต่ำกว่าจุดสูงสุด 3%" if x["c"] < p["hi"] * (1 - TRAIL) else
                   "MACD ตัดลงหรือ CCI ถึง 500" if sg[i] == "down" else None)
            if why:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
            continue
        if sg[i] is None:
            continue
        ok = sg[i] == "up" if mode == "rule" else rng.random() < TWIN_P
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "MACD เหนือสัญญาณ CCI ไม่เกิน -40" if mode == "rule" else "สุ่มแท่ง"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, hi=en, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_macdcci fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
