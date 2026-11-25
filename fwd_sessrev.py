#!/usr/bin/env python3
"""Forward paper test of the "two 12-hour sessions" reversal (MDPI J. Risk Financial Manag. 19(9) 692, 2026: BTC and ETH
hourly Kraken 2016-2025 split into two 12-hour sessions, BTC's best rule "mainly conditional reversal across the two
sessions"; the paper page refused the fetch, so the rule below is my closest version). Opened 25 Nov 2026 by the scout;
backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 12h Binance bars: when the 00:00-12:00 UTC bar moved more than THR (close vs open), take the other side on the
12:00-24:00 UTC bar: in at its open, out at its close. No stop (12 hours is the time stop). One position per coin, one
third of the start per coin, 0.35% per side.
  state_fwd_sessrev.json       BTC, ETH, SOL
  state_fwd_sessrev_twin.json  control: the same signal bars, random side
  python3 fwd_sessrev.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
DAY, H12 = 86400 * 1000, 12 * 3600 * 1000
THR = 0.02                     # my choice: the best of 6 settings searched (THR 0/1/2% x morning bar only or every bar), best only on SOL
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the three coins every scout test uses
LABEL = ("กลับทิศข้ามช่วง 12 ชม. (MDPI JRFM 2026) BTC ETH SOL: แท่ง 00-12 UTC ขยับเกิน 2% เล่นสวนทางในแท่ง 12-24 UTC "
         "เข้าเปิดออกปิดแท่ง (backtest Binance 12 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 772 ไม้ -0.83% ETH 1,104 ไม้ -0.93% "
         "SOL 1,032 ไม้ -0.47% ต่อไม้ ก่อนหัก -0.13/-0.23/+0.23% ตัวแฝดฝั่งสุ่ม -0.77/-0.73/-0.83% permutation ค้น 6 แบบ "
         "p 0.990/1.000/0.045 BTC ETH กลับเป็นไปทางเดียวกันเล็กน้อย คาดว่าติดลบ)")
ACCOUNTS = {"state_fwd_sessrev.json": ("rule", LABEL),
            "state_fwd_sessrev_twin.json": ("random", "กลับทิศข้ามช่วง 12 ชม. ตัวควบคุม: แท่งสัญญาณเดียวกัน ฝั่งสุ่ม")}


def fetch_iv(sym, iv="12h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def signal(x):
    """-1/1 side for the next 12h bar after the closed bar x, or 0."""
    if x["t"] % DAY != 0:
        return 0
    r = x["c"] / x["o"] - 1
    return 0 if abs(r) <= THR else (-1 if r > 0 else 1)


def trades(b):
    """The backtest (scout /tmp/scout_0705/sess.py, THR 2% morning bar): list of (entry_t, d, entry_px, exit_px)."""
    return [(b[i + 1]["t"], signal(b[i]), b[i + 1]["o"], b[i + 1]["c"]) for i in range(len(b) - 1) if signal(b[i])]


def close(s, sym, px, t, why):
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
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym]:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] == p["entry_t"]:
            close(s, sym, x["c"], x["t"] + H12, "ครบแท่ง 12 ชม.")
        if sym in s["pos"] or i + 1 >= len(bars):
            continue
        d = signal(x)
        if d and mode != "rule":
            d = 1 if rng.random() < 0.5 else -1
        usd = s["start_usd"] / 3
        if not d or (d > 0 and s["cash"] < usd * (1 + COST)):
            continue
        nx = bars[i + 1]
        e = nx["o"]
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "แท่ง 00-12 UTC ขยับเกิน 2% เล่นสวน" if mode == "rule" else "แท่งสัญญาณเดียวกัน ฝั่งสุ่ม"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "12h")
        except Exception as e:
            print("fwd_sessrev fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
