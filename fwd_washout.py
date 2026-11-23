#!/usr/bin/env python3
"""Forward paper test of the "washout" leg of irwan11795/makefun-btc-race-24h-20261123-0511 (make.fun 24h BTC race
bot, GitHub 23 Nov 2026) on BTC, ETH, SOL (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because
the user asked to try weak ideas too). Fake money only.

The repo runs on 1-minute bars; here on closed 15m Binance bars with the same clock lengths: a close at least 4% under
the close 16 bars (240 minutes) earlier buys at the next open; out at the next open after a close 3% under the entry,
or after 33 bars held (about the repo's 500-bar cap). The repo's "range" leg is not here (backtest in the scout log).
One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_washout.json       BTC, ETH, SOL
  state_fwd_washout_twin.json  control: random entry bars (TWIN_P per free bar), same stop and time cap
  python3 fwd_washout.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the race trades cbBTC only
LOOK, DROP = 16, -0.04         # the repo's 240-bar return <= -400 bps, at 1m; 16 x 15m is my move to 15m bars
STOP, CAP = 0.03, 33           # the repo's -300 bps stop; 33 x 15m is my rounding of its 500 1m-bar cap
TWIN_P = 1 / 700               # my choice: about the rule's rate in the backtest (349 trades in 241,558 BTC bars)
LABEL = ("Washout ของบอทแข่ง make.fun (irwan11795) 15 นาที BTC ETH SOL: ปิดต่ำกว่าปิด 4 ชม. ก่อน 4% ขึ้นไป ซื้อแท่งถัดไป "
         "ออกเมื่อปิดต่ำกว่าทุน 3% หรือถือครบ 33 แท่ง (backtest Binance 15 นาที 2020-2026 หลังหัก 0.35%/ข้าง "
         "BTC 349 ไม้ -0.39% ETH 681 ไม้ -0.58% SOL 1,438 ไม้ -0.29% ต่อไม้ ก่อนหัก +0.31/+0.12/+0.41% ชนะ 41-42% "
         "permutation 200 รอบ p 0.045/0.254/0.005 แรงเด้งมีจริงบางเหรียญแต่เล็กกว่าต้นทุนไปกลับ)")
ACCOUNTS = {"state_fwd_washout.json": ("rule", LABEL),
            "state_fwd_washout_twin.json": ("random", "Washout ตัวควบคุม: เข้าแท่งสุ่ม stop 3% และถือไม่เกิน 33 แท่งแบบเดียวกัน")}


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
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < LOOK:
            continue
        seen[sym] = x["t"]
        if sym in s["pos"]:
            p = s["pos"][sym]
            p["held"] = p.get("held", 0) + 1      # closed bars since the entry bar, counted like the backtest
            if x["c"] <= p["entry"] * (1 - STOP):
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดต่ำกว่าทุน 3%")
            elif p["held"] >= CAP:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ถือครบ 33 แท่ง")
            continue
        if mode == "rule":
            go, why = x["c"] / bars[i - LOOK]["c"] - 1 <= DROP, "ร่วง 4% ใน 4 ชม."
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
            cache[sym] = fetch_iv(sym, "15m")
        except Exception as e:
            print("fwd_washout fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
