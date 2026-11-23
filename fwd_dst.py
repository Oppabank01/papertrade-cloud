#!/usr/bin/env python3
"""Forward paper test of the Double SuperTrend (Pine defaults as used by chellurikishore080-ans8260/
double-supertrend-binance-backtest, GitHub 2026: fast ATR 10 x 1.5, slow ATR 10 x 3.0, 1h, long only) on BTC, ETH, SOL
(opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On closed 1h Binance bars: long at the next open on the first bar where both SuperTrends point up; out at the next
open when the fast one flips down. No stop beyond that (the repo has none). One position per coin, one third of the
start per coin, 0.35% per side. The SuperTrends are computed on the 1000 bars byttrade.fetch returns.
  state_fwd_dst.json       BTC, ETH, SOL
  state_fwd_dst_twin.json  control: random entry bars (TWIN_P per free bar), same fast-flip exit
  python3 fwd_dst.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo scans the top 50 USDT pairs
PERIOD, FAST, SLOW = 10, 1.5, 3.0          # the repo's Pine defaults; no search here
TWIN_P = 1 / 60                # my choice: about the rule's trade rate per coin-bar in the backtest (1 in 53 on BTC)
LABEL = ("Double SuperTrend 1 ชม. long BTC ETH SOL (ATR10 x1.5 กับ x3.0 ค่าเริ่มต้นของ repo): เข้าเมื่อสองเส้นชี้ขึ้นพร้อมกันครั้งแรก "
         "ออกเมื่อเส้นเร็วกลับลง (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 1,537 ไม้ -0.54% ETH 1,569 ไม้ -0.49% "
         "SOL 1,161 ไม้ -0.54% ต่อไม้ ก่อนหัก +0.16/+0.21/+0.16% ชนะ 28-30% ติดลบเกือบทุกปี permutation 200 รอบ p 0.095/0.095/0.726)")
ACCOUNTS = {"state_fwd_dst.json": ("rule", LABEL),
            "state_fwd_dst_twin.json": ("random", "Double SuperTrend ตัวควบคุม: เข้าแท่งสุ่ม ออกเมื่อเส้นเร็วกลับลงแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def supertrend(b, factor, period=PERIOD):
    """Pine ta.supertrend direction: -1 up, +1 down, None during the ATR warm-up (Wilder RMA seeded with an SMA)."""
    n = len(b)
    tr = [b[0]["h"] - b[0]["l"]] + [max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
                                    for i in range(1, n)]
    atr = [None] * n
    if n >= period:
        atr[period - 1] = sum(tr[:period]) / period
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    up, lo, dr = [None] * n, [None] * n, [None] * n
    for i in range(n):
        if atr[i] is None:
            continue
        mid = (b[i]["h"] + b[i]["l"]) / 2
        bu, bl = mid + factor * atr[i], mid - factor * atr[i]
        if i == 0 or dr[i - 1] is None:
            up[i], lo[i], dr[i] = bu, bl, 1
            continue
        pc = b[i - 1]["c"]
        up[i] = bu if bu < up[i - 1] or pc > up[i - 1] else up[i - 1]
        lo[i] = bl if bl > lo[i - 1] or pc < lo[i - 1] else lo[i - 1]
        c = b[i]["c"]
        dr[i] = (-1 if c > up[i] else 1) if dr[i - 1] == 1 else (1 if c < lo[i] else -1)
    return dr


def close(s, sym, px, t, why):   # as pullback.close
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
    fd, sd = supertrend(bars, FAST), supertrend(bars, SLOW)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i == 0:
            continue
        seen[sym] = x["t"]
        if fd[i] is None or sd[i] is None or fd[i - 1] is None or sd[i - 1] is None:
            continue
        if sym in s["pos"]:
            if fd[i] == 1:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "SuperTrend เร็วกลับลง")
            continue
        if mode == "rule":
            go = fd[i] == -1 and sd[i] == -1 and not (fd[i - 1] == -1 and sd[i - 1] == -1)
            why = "SuperTrend สองเส้นชี้ขึ้นพร้อมกันครั้งแรก"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มแท่ง"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_dst fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
