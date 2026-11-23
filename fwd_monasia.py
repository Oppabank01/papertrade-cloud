#!/usr/bin/env python3
"""Forward paper test of the "Monday Asia open effect" (Concretum Group blog, Bitcoin intraday trend 2018-2025: strong
from Sunday about 7 pm New York for about 24 hours, no rule given) in its closest mechanical form on BTC, ETH, SOL
(opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too).
Fake money only.

On daily Binance bars (00:00 UTC): when the next bar is a Monday, buy at its open (Monday 00:00 UTC = Sunday 7 pm New
York in winter); sell at the open of the next daily bar (Tuesday 00:00 UTC). Long only, one position per coin, one third
of the start per coin, 0.35% per side. No stop (one day is the time stop).
  state_fwd_monasia.json       BTC, ETH, SOL
  state_fwd_monasia_twin.json  control: random entry days (TWIN_P per free day), same one-day hold
  python3 fwd_monasia.py"""
import random
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save, fetch, DAY

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the blog used BTC only; ETH and SOL added by me
WEEKDAY, HOLD = 0, 1           # my reading of the blog: Monday 00:00 UTC for one day (long only, the blog's side)
TWIN_P = 1 / 7                 # my choice: one random day a week on average, like the rule
LABEL = ("Monday Asia open BTC ETH SOL (บล็อก Concretum ไม่มีกฎ ผมแปลงเป็นซื้อเปิดวันจันทร์ 00:00 UTC ขายเปิดวันอังคาร) "
         "(backtest Binance รายวัน 2017-2026 ก่อนหัก BTC +0.40% ETH +0.32% SOL +0.20% ต่อไม้ หลังหัก 0.35%/ข้าง "
         "BTC 483 ไม้ -0.30% มัธยฐาน -0.63% ETH 483 ไม้ -0.38% SOL 327 ไม้ -0.50% ซื้อทุกวัน -0.39 ถึง -0.56% "
         "permutation p 0.025/0.214/0.637 ตก ปี 2024+ BTC -0.22% ETH -0.20% SOL -0.53%)")
ACCOUNTS = {"state_fwd_monasia.json": ("rule", LABEL),
            "state_fwd_monasia_twin.json": ("random", "Monday Asia open ตัวควบคุม: เข้าวันสุ่ม ถือ 1 วันแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def weekday(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).weekday()


def trades(b, first=1):
    """The backtest: list of (entry_t, entry_px, exit_t, exit_px), oldest first."""
    out, i = [], first
    while i < len(b) - 1:
        if weekday(b[i + 1]["t"]) != WEEKDAY:
            i += 1
            continue
        e_t, e, j = b[i + 1]["t"], b[i + 1]["o"], i + 1
        while j < len(b) - 1 and b[j + 1]["t"] < e_t + HOLD * DAY:
            j += 1
        if j >= len(b) - 1:
            break
        out.append((e_t, e, b[j + 1]["t"], b[j + 1]["o"]))
        i = j
    return out


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px * (1 - COST)
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        nx = bars[i + 1]
        p = s["pos"].get(sym)
        if p and nx["t"] >= p["exit_t"]:
            close(s, sym, nx["o"], nx["t"], f"ครบ {HOLD} วัน")
        if sym in s["pos"]:
            continue
        go = weekday(nx["t"]) == WEEKDAY if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / 3
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd * (1 + COST)
        why = "เปิดวันจันทร์ 00:00 UTC" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"],
                             exit_t=nx["t"] + HOLD * DAY, t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_monasia fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
