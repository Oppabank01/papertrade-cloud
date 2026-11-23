#!/usr/bin/env python3
"""Forward paper test of the "Seasonality of Bitcoin" hour window (Quantpedia summary of Vojtko & Javorska 2023, Gemini
BTC 2015-2023: long 21:00 to 23:00 UTC every day, 40.6% a year before costs) on BTC, ETH, SOL (opened 23 Nov 2026 by
the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

On 1h Binance bars: when the next bar opens at START_H UTC, buy at its open; sell at the open of the bar HOLD hours later
(23:00 UTC). Long only, one position per coin, one third of the start per coin, 0.35% per side. No stop (the window is
the time stop).
  state_fwd_hour21.json       BTC, ETH, SOL
  state_fwd_hour21_twin.json  control: random entry hours (TWIN_P per free hour), same 2h hold
  python3 fwd_hour21.py"""
import random
from datetime import datetime, timezone
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H = 3600 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the paper used BTC only; ETH and SOL added by me
START_H, HOLD = 21, 2          # from the paper (21:00 to 23:00 UTC); no search here
TWIN_P = 1 / 24                # my choice: one random 2h window a day on average, like the rule
LABEL = ("ช่วงเวลา 21:00-23:00 UTC (04:00-06:00 ไทย) BTC ETH SOL ตาม Quantpedia/Vojtko 2023 ซื้อทุกวันถือ 2 ชม. "
         "(backtest Binance 1 ชม. 2017-2026 ก่อนหัก BTC +0.085% ETH +0.097% SOL +0.049% ต่อไม้ หลังหัก 0.35%/ข้าง "
         "BTC 3,382 ไม้ -0.62% ETH 3,382 ไม้ -0.60% SOL 2,294 ไม้ -0.65% ตัวแฝดชั่วโมงสุ่ม -0.70% permutation p 0.005/0.005/0.303 "
         "แพทเทิร์นมีจริงแต่ต้นทุนไปกลับ 0.7% ใหญ่กว่า 7 เท่า)")
ACCOUNTS = {"state_fwd_hour21.json": ("rule", LABEL),
            "state_fwd_hour21_twin.json": ("random", "ช่วง 21-23 UTC ตัวควบคุม: เข้าชั่วโมงสุ่ม ถือ 2 ชม. แบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def hour(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).hour


def trades(b, first=1):
    """The backtest: list of (entry_t, entry_px, exit_t, exit_px), oldest first."""
    out, i = [], first
    while i < len(b) - 1:
        if hour(b[i + 1]["t"]) != START_H:
            i += 1
            continue
        e_t, e, j = b[i + 1]["t"], b[i + 1]["o"], i + 1
        while j < len(b) - 1 and b[j + 1]["t"] < e_t + HOLD * H:
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
            close(s, sym, nx["o"], nx["t"], f"ครบ {HOLD} ชม.")
        if sym in s["pos"]:
            continue
        go = hour(nx["t"]) == START_H if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / 3
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd * (1 + COST)
        why = "เปิดแท่ง 21:00 UTC" if mode == "rule" else "สุ่มชั่วโมง"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"],
                             exit_t=nx["t"] + HOLD * H, t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_hour21 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
