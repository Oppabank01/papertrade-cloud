#!/usr/bin/env python3
"""Forward paper test of the KAMA trend rule (giorgospoci532-cmd/Kama-Adaptive-Trading-Strategy, GitHub 15 Nov 2026: long
while the daily close is above Kaufman's Adaptive Moving Average, tested there on AAPL MSFT GOOG AMZN IBM 2008-2009) on
BTC, ETH, SOL, BNB, XRP (opened 27 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try
weak ideas too). Fake money only.

On closed 1d Binance bars, long only: KAMA as the repo's kama() (efficiency ratio over 10 bars, fast 2, slow 30, smoothing
constant squared, seeded with the close of bar 10 of the bars this script is given). BUY = flat and the close above KAMA,
SELL = in a position and the close at or below KAMA; both fill at the next open. One position per coin, one fifth of the
start per coin, 0.35% per side. The window byttrade.fetch returns (1000 days) moves each day, so KAMA can differ by a hair
from one seeded years earlier.
  state_fwd_kama.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_kama_twin.json  control: random entry bars (TWIN_P per free bar), same SELL exit
  python3 fwd_kama.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five majors the other scout accounts use
ER_N, FAST, SLOW = 10, 2, 30   # from the repo's "Slow KAMA (2, 30)"; I picked it over its "Fast KAMA (2, 10)" (2 tried)
TWIN_P = 1 / 7                 # my choice: the backtest twin's rate (2 x 240 BTC trades / about 3,390 daily bars)
# also mine: daily Binance bars instead of US stocks, fills at the next open, long only, size one fifth of the start
LABEL = ("KAMA รายวัน (giorgospoci532-cmd/Kama-Adaptive-Trading-Strategy) BTC ETH SOL BNB XRP: ถือเมื่อราคาปิดอยู่เหนือ "
         "KAMA 10/2/30 ขายเมื่อปิดต่ำกว่า (backtest Binance รายวัน 2017 ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 240 ไม้ "
         "+1.03% ต่อไม้ มัธยฐาน -2.32% ชนะ 23% ETH 222 ไม้ +1.49% SOL 153 ไม้ +4.55% BNB 240 ไม้ +3.12% XRP 215 ไม้ "
         "+1.32% ตัวแฝดเข้าสุ่ม +0.19 ถึง +2.46% แพ้ถือเฉยๆ ทุกเหรียญยกเว้น SOL ตั้งแต่ 2025 -1.69 ถึง +0.30% ต่อไม้ "
         "permutation 200 รอบ กริด 2 แบบ p 0.174/0.080/0.025/0.055/0.095)")
ACCOUNTS = {"state_fwd_kama.json": ("rule", LABEL),
            "state_fwd_kama_twin.json": ("random", "KAMA รายวัน ตัวควบคุม: เข้าวันสุ่ม ออกเมื่อปิดต่ำกว่า KAMA แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def kama(c):
    fs, ss = 2 / (FAST + 1), 2 / (SLOW + 1)
    out = [None] * len(c)
    if len(c) <= ER_N:
        return out
    out[ER_N] = c[ER_N]
    for i in range(ER_N + 1, len(c)):
        ch = abs(c[i] - c[i - ER_N])
        vol = sum(abs(c[j] - c[j - 1]) for j in range(i - ER_N + 1, i + 1))
        er = ch / vol if vol else 0.0
        out[i] = out[i - 1] + (er * (fs - ss) + ss) ** 2 * (c[i] - out[i - 1])
    return out


def signals(b):
    """per bar 'buy' (close above KAMA), 'sell' (at or below) or None before KAMA starts"""
    c = [x["c"] for x in b]
    k = kama(c)
    return [None if k[i] is None else ("buy" if c[i] > k[i] else "sell") for i in range(len(b))]


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
            if x["t"] >= p["entry_t"] and sg[i] == "sell":
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดต่ำกว่า KAMA")
            continue
        ok = sg[i] == "buy" if mode == "rule" else (sg[i] is not None and rng.random() < TWIN_P)
        if not ok:
            continue
        en, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        why = "ปิดเหนือ KAMA" if mode == "rule" else "สุ่มวัน"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / en, entry=en, last=en, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=en, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_kama fetch failed", sym, type(e).__name__)   # a failed fetch means no action for that coin
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
