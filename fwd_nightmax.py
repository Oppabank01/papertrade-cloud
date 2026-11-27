#!/usr/bin/env python3
"""Forward paper test of Quantpedia's "How To Profitably Trade Bitcoin's Overnight Sessions?" (Dujava, 12 Nov 2024,
Gemini BTC 2015-2024: MAX(10) held only Fri->Mon, Mon->Tue and Tue->Wed nights), opened 28 Nov 2026 by the scout
(backtest in LABEL; not a pass, opened because the user asked to try weak ideas too). Fake money only.

On 1h Binance bars: when the next bar opens at 16:00 New York (NYSE close) on a Friday, Monday or Tuesday and the
last closed price is at or above each of the 10 prices 24, 48, ... 240 bars back (my reading of "local 10-day max":
the article gives no exact definition), buy at that open; sell at the open of the next 10:00 New York bar on a weekday
(the article's session start). US daylight saving is computed here; NYSE holidays are ignored (my choice). Long only,
one position per coin, one third of the start per coin, 0.35% per side. No stop (the session is the time stop).
  state_fwd_nightmax.json       BTC, ETH, SOL
  state_fwd_nightmax_twin.json  control: same Fri/Mon/Tue 16:00 entries taken at random (TWIN_P), same exit
  python3 fwd_nightmax.py"""
import random
from datetime import datetime, timezone, timedelta
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the article used BTC only; ETH and SOL added by me
DAYS = (4, 0, 1)               # from the article: enter at Friday, Monday, Tuesday close
ENTRY_H, EXIT_H = 16, 10       # from the article: NYSE close 4 pm, session start 10 am New York
LOOK = 10                      # from the article: 10-day max
TWIN_P = 0.2                   # my choice: about the rule's hit rate on BTC (303 of 1447 windows in the backtest)
LABEL = ("BTC ข้ามคืนตลาดหุ้นสหรัฐ MAX(10) ตาม Quantpedia: ศุกร์ จันทร์ อังคาร 16:00 นิวยอร์ก ถ้าราคาสูงสุดใน 10 วันให้ซื้อ "
         "ขาย 10:00 นิวยอร์กวันทำการถัดไป BTC ETH SOL (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง BTC 303 ไม้ +0.05% "
         "ETH 278 ไม้ +0.17% SOL 180 ไม้ +0.57% ต่อไม้ ตัวแฝดสุ่ม -0.25 ถึง -0.33% แต่ปี 2025+ BTC -0.77% ETH -0.50% SOL +0.16% "
         "permutation p 0.418/0.289/0.114 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_nightmax.json": ("rule", LABEL),
            "state_fwd_nightmax_twin.json": ("random", "MAX(10) ข้ามคืนตัวควบคุม: เข้าสุ่มที่ศุกร์ จันทร์ อังคาร 16:00 นิวยอร์ก ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ny(t):
    """UTC ms -> New York wall clock (US DST: 2nd Sunday of March 07:00 UTC to 1st Sunday of November 06:00 UTC)."""
    u = datetime.fromtimestamp(t / 1000, timezone.utc)
    mar = datetime(u.year, 3, 8, 7, tzinfo=timezone.utc)
    mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(u.year, 11, 1, 6, tzinfo=timezone.utc)
    nov += timedelta(days=(6 - nov.weekday()) % 7)
    return u + timedelta(hours=-4 if mar <= u < nov else -5)


def is_entry(t):
    d = ny(t)
    return d.hour == ENTRY_H and d.weekday() in DAYS


def is_exit(t):
    d = ny(t)
    return d.hour == EXIT_H and d.weekday() < 5


def signal(b, i):
    return i >= 24 * LOOK and b[i]["c"] >= max(b[i - 24 * k]["c"] for k in range(1, LOOK + 1))


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
        if p and nx["t"] > p["entry_t"] and is_exit(nx["t"]):
            close(s, sym, nx["o"], nx["t"], "10:00 นิวยอร์ก")
        if sym in s["pos"] or not is_entry(nx["t"]):
            continue
        go = signal(bars, i) if mode == "rule" else rng.random() < TWIN_P
        usd = s["start_usd"] / 3
        if not go or s["cash"] < usd * (1 + COST):
            continue
        e = nx["o"]
        s["cash"] -= usd * (1 + COST)
        why = "สูงสุด 10 วันตอนตลาดหุ้นปิด" if mode == "rule" else "สุ่มตอนตลาดหุ้นปิด"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_nightmax fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
