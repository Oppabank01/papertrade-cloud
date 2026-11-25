#!/usr/bin/env python3
"""Forward paper test of the "Breakout" rule bot of AINotes Bot Wars (ainotes.us/crypto/bots, X @ainotesus: 6 AI models
vs 5 simple rules on 8 coins from 27 Sep 2026; day 59 Breakout leads at -7.8%, every AI model -29% to -38%). The site says
only "holds coins trading above their 30-day high", so the exit is my choice. Opened 25 Nov 2026 by the scout; backtest
in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1d Binance bars: close above the highest close of the 30 bars before -> long at the next open. Exit at the next
open after a close below the lowest close of the 30 bars before (my choice, the better of the 2 exits searched; the
other was a close below SMA30). No stop (the 30-day low exit is the stop). One position per coin, one eighth of the start
per coin, 0.35% per side.
  state_fwd_brk30.json       the site's 8 coins
  state_fwd_brk30_twin.json  control: random entry days (TWIN_P per flat day), the same 30-day low exit
  python3 fwd_brk30.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
N = 30                         # the site's 30-day high; the 30-day low exit is my choice
SYMS = [c + "USDT" for c in "BTC ETH SOL XRP DOGE LINK ADA BNB".split()]   # the site's 8 coins
TWIN_P = 1 / 15                # my choice: as the backtest twin
LABEL = ("Breakout 30 วัน (AINotes Bot Wars) รายวัน 8 เหรียญ: ปิดเหนือราคาปิดสูงสุด 30 วันก่อน ซื้อเปิดวันถัดไป "
         "ออกเมื่อปิดต่ำกว่าราคาปิดต่ำสุด 30 วันก่อน (backtest Binance รายวัน 2017-2026 หลังหัก 0.35%/ข้าง ต่อไม้ "
         "BTC 31 ไม้ +22.9% ETH 28 +31.6% SOL 22 +89.7% XRP 33 +8.0% DOGE 24 +457% LINK 31 +16.2% ADA 33 +21.4% BNB 32 +49.8% "
         "มัธยฐาน -12.7% ถึง +3.0% ชนะ 27-58% ตัวแฝดวันสุ่ม +4.6% ถึง +160% permutation ค้น 2 แบบออก p "
         "0.030/0.020/0.010/0.343/0.005/0.423/0.035/0.045 กำไรมาจากปีขาขึ้นใหญ่ ปี 2025-2026 ราว 0 ถึง -10% ต่อไม้)")
ACCOUNTS = {"state_fwd_brk30.json": ("rule", LABEL),
            "state_fwd_brk30_twin.json": ("random", "Breakout 30 วัน ตัวควบคุม: เข้าวันสุ่ม ออกเมื่อปิดต่ำกว่าต่ำสุด 30 วันแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def high(b, i):
    return b[i]["c"] > max(x["c"] for x in b[i - N:i])


def low(b, i):
    return b[i]["c"] < min(x["c"] for x in b[i - N:i])


def trades(b, first=N):
    """The backtest (scout /tmp/scout_0705/brk.py exit B): list of (entry_t, entry_px, exit_px), open trades left out."""
    out, pos = [], None
    for i in range(max(first, N), len(b) - 1):
        if pos:
            if low(b, i):
                out.append((pos[0], pos[1], b[i + 1]["o"]))
                pos = None
        elif high(b, i):
            pos = (b[i + 1]["t"], b[i + 1]["o"])
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < N:
            continue
        seen[sym] = x["t"]
        nx = bars[i + 1]
        if sym in s["pos"]:
            if low(bars, i):
                close(s, sym, nx["o"], nx["t"], "ปิดต่ำกว่าต่ำสุด 30 วัน")
            continue
        go = high(bars, i) if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / len(SYMS)
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd + usd * COST
        why = "ปิดเหนือสูงสุด 30 วัน" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_brk30 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
