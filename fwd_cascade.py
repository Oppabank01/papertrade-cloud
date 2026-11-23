#!/usr/bin/env python3
"""Forward paper test of "fade liquidation cascades, 2% filter, with a reversal check" (StacyOnChain on X, 17 Nov 2026,
an 8-month Hyperliquid study: plain fade +0.01% per trade after fees, 2% filter +0.22%, reversal check on top) on BTC,
ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas
too). Fake money only. We have no liquidation feed, so a cascade here is one closed 15m Binance bar that moves THR or more.

On closed 15m bars: a bar down THR or more -> wait for the next bar; if it closes green, long at the bar after's open.
A bar up THR or more -> the same for a short after a red bar. If the check fails, that next bar is itself checked as a
cascade. Out at the open HOLD bars after the entry. No stop (the post gives none). One position per coin, one third of
the start per coin, 0.35% per side.
  state_fwd_cascade.json       BTC, ETH, SOL
  state_fwd_cascade_twin.json  control: random entry bars (TWIN_P per free bar), random side, same HOLD-bar hold
  python3 fwd_cascade.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the post covers 7 Hyperliquid coins
M15 = 15 * 60 * 1000
THR = 0.02                         # the post's "2% filter"; read as a 2% move in one 15m bar (my reading)
HOLD = 4                           # my choice: 4 bars = 1 hour (the post's hold is not given)
TWIN_P = 1 / 400                   # my choice: about the rule's trade rate per coin-bar in the backtest
LABEL = ("เฟดการล้างพอร์ต 15 นาที BTC ETH SOL (StacyOnChain): แท่ง 15 นาทีขยับ 2% ขึ้นไป รอแท่งถัดไปกลับทิศแล้วสวน ถือ 1 ชม. "
         "(backtest Binance 2017-2026 หลังหัก 0.35%/ข้าง BTC 590 ไม้ -0.40% ETH 1,001 ไม้ -0.61% SOL 1,423 ไม้ -0.49% "
         "ก่อนหัก +0.30/+0.09/+0.21% ปี 2024+ -0.50/-0.77/-0.67% permutation 3 ปีล่าสุดทั้งกริด 4 แบบ BTC p 0.02 SOL p 0.005 "
         "แต่ติดลบหลังหักทุกแบบ ผ่านเพราะข้อมูลสลับแย่กว่า)")
ACCOUNTS = {"state_fwd_cascade.json": ("rule", LABEL),
            "state_fwd_cascade_twin.json": ("random", "เฟดการล้างพอร์ต ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม ถือ 1 ชม. แบบเดียวกัน")}


def fetch_iv(sym, iv="15m"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def cascade(x):
    r = x["c"] / x["o"] - 1
    return -1 if r >= THR else 1 if r <= -THR else 0


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, wait = s.setdefault("seen", {}), s.setdefault("wait", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p:
            if x["t"] < p["exit_t"]:
                continue
            close(s, sym, x["o"], x["t"], f"ครบ {HOLD} แท่ง")
        d, why = 0, ""
        if mode == "rule":
            w = wait.pop(sym, 0)
            if w and (x["c"] - x["o"]) * w > 0:
                d, why = w, "แท่งก่อนหน้าขยับเกิน 2% แท่งนี้กลับทิศ สวน"
            else:
                c = cascade(x)
                if c:
                    wait[sym] = c
        elif rng.random() < TWIN_P:
            d, why = rng.choice((1, -1)), "สุ่มแท่ง สุ่มฝั่ง"
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             entry_t=et, exit_t=et + HOLD * M15, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "15m")
        except Exception as e:
            print("fwd_cascade fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
