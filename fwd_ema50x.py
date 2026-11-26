#!/usr/bin/env python3
"""Forward paper test of "Close crosses EMA 50" (drakkB/pine-script-22-strategies-btc-benchmark, script
20-price-ema50.pine; on its sealed BTC 1d period 2024-12-17 to 2026-10-16 at 0.1%/side: 20 trades +16.98% vs holding
-23.25%, 3 of 4 judge steps, stopped at the test against chance). Opened 26 Nov 2026 by the scout; backtest in LABEL,
opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1d Binance bars (the script as written): the close crosses above EMA50 (this close above, the previous close at
or below the previous EMA50) -> long at the next open; the close crosses below EMA50 -> out at the next open. Long only,
no stop, no target. EMA50 as Pine's ta.ema (seeded with the SMA of the first 50 closes of the bars fetched). One position
per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_ema50x.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_ema50x_twin.json  control: random entry days (TWIN_P per flat day), out after HOLD days
  python3 fwd_ema50x.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the repo ran BTC only; the 5 large coins the scout uses
N = 50                                 # the script's number
TWIN_P = 1 / 15                        # my choice: about the rule's entry rate per flat day in the backtest (1/13 to 1/16)
HOLD = 14                              # my choice: the rule's mean hold in days in the backtest (10.5 to 15.5)
LABEL = ("ปิดตัด EMA50 รายวัน (drakkB 22 ท่า Pine) BTC ETH SOL BNB XRP: ปิดตัดขึ้น EMA50 ซื้อ ปิดตัดลงออก ไม่มี stop "
         "(backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง BTC 107 ไม้ +5.14% ต่อไม้ ETH 109 ไม้ +5.92% SOL 78 ไม้ +32.04% "
         "BNB 123 ไม้ +15.30% XRP 124 ไม้ +2.02% มัธยฐาน -2.4 ถึง -3.7% ชนะ 12-21% ตัด 1% ดีสุด -1.0 ถึง +9.3% "
         "ตัวแฝดเข้าสุ่ม +1.5/+2.0/+6.5/+4.1/+1.5% ตั้งแต่ 2025 -0.11/+1.16/-0.32/+0.53/-3.15% ต่อไม้ "
         "permutation 200 รอบ p 0.055/0.050/0.010/0.020/0.303 ไม่ผ่าน 0.01 ทุกเหรียญ กำไรเก่ามาจากขาขึ้นใหญ่ 2019-2021)")
ACCOUNTS = {"state_fwd_ema50x.json": ("rule", LABEL),
            "state_fwd_ema50x_twin.json": ("random", "ปิดตัด EMA50 ตัวควบคุม: เข้าวันสุ่ม ถือครบ 14 วันแล้วออก")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def pine_ema(c, n=N):
    """Pine ta.ema: None until bar n-1, seeded with the SMA of the first n closes (same as the scout's /tmp/scout_pine22.py)."""
    out, e, a = [None] * len(c), None, 2 / (n + 1)
    for i in range(len(c)):
        if i == n - 1:
            e = sum(c[:n]) / n
        elif i >= n:
            e = a * c[i] + (1 - a) * e
        out[i] = e
    return out


def cross(b):
    """Per bar: +1 close crosses above EMA50, -1 crosses below, 0 otherwise."""
    c = [x["c"] for x in b]
    e, out = pine_ema(c), [0] * len(c)
    for i in range(N, len(c)):
        if c[i] > e[i] and c[i - 1] <= e[i - 1]:
            out[i] = 1
        elif c[i] < e[i] and c[i - 1] >= e[i - 1]:
            out[i] = -1
    return out


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_pine22.py ema50_trades): (entry_t, entry, exit), oldest first."""
    x, out, ent = cross(b), [], None
    for i in range(len(b) - 1):
        if ent is None and x[i] > 0:
            ent = (b[i + 1]["t"], b[i + 1]["o"])
        elif ent is not None and x[i] < 0:
            out.append((ent[0], ent[1], b[i + 1]["o"]))
            ent = None
    return out


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
    xs = cross(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < N:
            continue
        seen[sym] = x["t"]
        if sym in s["pos"]:
            p = s["pos"][sym]
            p["held"] = p.get("held", 0) + 1      # closed bars since the entry bar
            if mode == "rule" and xs[i] < 0:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ปิดตัดลงใต้ EMA50")
            elif mode != "rule" and p["held"] >= HOLD:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "ถือครบ 14 วัน")
            continue
        if mode == "rule":
            go, why = xs[i] > 0, "ปิดตัดขึ้นเหนือ EMA50"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มวัน"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 5
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
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_ema50x fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
