#!/usr/bin/env python3
"""Forward paper test of Orsonneri/crypto-trading-bots "01 candle-colour momentum" (GitHub, Nov 2026) in its core form,
on BTC, ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try
weak ideas too). Fake money only.

Yesterday's UTC day candle (built from 15m bars) closed green -> long at today's first 15m open, red -> short, doji ->
nothing. Stop 1% from the entry, checked on 15m CLOSES and filled at that close (the repo's default stop_mode
fixed_pct 0.01); otherwise out at the close of the day's last 15m bar. Left out (my simplification): the BREAKOUT
historical target, the BASE target at yesterday's extreme and the 50% partial take-profit.
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_cmom.json         BTC, ETH, SOL, 1% stop on closes
  state_fwd_cmom_nostop.json  same entries, no stop, hold the whole day
  state_fwd_cmom_twin.json    control: same entry times, random side, 1% stop
  python3 fwd_cmom.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo's default is ETHUSDT
M15, DAY = 15 * 60 * 1000, 86400 * 1000    # the repo's session_start_hour 0: UTC days
LABEL = ("candle-colour momentum (Orsonneri) BTC ETH SOL: แท่งวัน UTC เมื่อวานเขียวซื้อตอนเปิดวัน แดง short stop 1% ดูราคาปิด 15 นาที "
         "ไม่โดนปิดสิ้นวัน (backtest Binance 15 นาที 2017-2026 หลังหัก 0.35%/ข้าง BTC 3,318 ไม้ -0.65% ETH 3,318 ไม้ -0.64% "
         "SOL 2,269 ไม้ -0.74% ต่อไม้ ก่อนหักราว 0% ชนะ 21-24% เท่ากับฝั่งสุ่ม permutation 200 รอบบน 3 ปีล่าสุด p 0.17/0.35/0.15)")
ACCOUNTS = {"state_fwd_cmom.json": ("rule", 0.01, LABEL),
            "state_fwd_cmom_nostop.json": ("rule", 0, "candle-colour momentum ไม่มี stop: ทิศตามสีแท่งวันเมื่อวาน ถือทั้งวัน"),
            "state_fwd_cmom_twin.json": ("random", 0.01, "candle-colour momentum ตัวควบคุม: เข้าเวลาเดียวกัน ฝั่งสุ่ม stop 1% ปิดสิ้นวัน")}


def fetch_iv(sym, iv="15m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, stop, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        last = (x["t"] + M15) % DAY == 0          # the day's last 15m bar
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            if stop and (x["c"] - p["entry"]) * p["d"] <= -stop * p["entry"]:
                close(s, sym, x["c"], x["t"] + M15, "stop 1% ราคาปิด 15 นาที")
            elif last:
                close(s, sym, x["c"], x["t"] + M15, "ปิดสิ้นวัน")
        # the day just closed decides tomorrow; all 96 bars of it and the next bar must be there, as in the backtest
        if sym in s["pos"] or not last or i < 95 or bars[i - 95]["t"] != x["t"] + M15 - DAY or bars[i + 1]["t"] != x["t"] + M15:
            continue
        po, pc = bars[i - 95]["o"], x["c"]
        d = 1 if pc > po else -1 if pc < po else 0
        if mode == "random" and d:
            d = rng.choice((1, -1))
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("แท่งวันเมื่อวานเขียว" if d > 0 else "แท่งวันเมื่อวานแดง") if mode == "rule" else "เวลาเดียวกัน ฝั่งสุ่ม"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym)
        except Exception as e:
            print("fwd_cmom fetch failed", sym, type(e).__name__)
    for f, (mode, stop, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, stop, rng)
        save(f, s)


if __name__ == "__main__":
    main()
