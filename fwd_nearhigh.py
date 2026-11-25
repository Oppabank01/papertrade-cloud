#!/usr/bin/env python3
"""Forward paper test of the taker control of "SOL-LU-M25-H12" (kalambyryura/ai-trading-arena strategies/
sol-nc1-maker-pullback: the card says the same entry with a taker order and a 24 h hold earned more than its maker
recipe), opened 25 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas
too. Fake money only.

On closed 1h bars: close above the SMA of the last 20 completed UTC daily closes, close 0.05% to 0.30% below the highest
high of the last 7 completed UTC days, and the close at least 0.30% above the previous 1h close -> long at the next
open. Stop -15%, target +30% (protection only), out at the close of the 24th bar. A gap through the stop fills at the
open; both touched = stop. After an exit the next bar may not signal (card cooldown 3600 s). One position per coin, one
third of the start per coin, 0.35% per side.
  state_fwd_nearhigh.json       BTC, ETH, SOL
  state_fwd_nearhigh_twin.json  control: random entry times (1 in 200 free bars) when the close is above the SMA20, same exits
  python3 fwd_nearhigh.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                 # per side, as every account here
H1, DAY = 3600 * 1000, 86400 * 1000
TWIN_P = 1 / 200              # my choice: about as often as the rule fires in up regimes
SMA_D, HIGH_D = 20, 7         # from the card
GAP_LO, GAP_HI, PUSH = -0.0030, -0.0005, 0.0030   # from the card (-30..-5 bps from the 7-day high, 60-min return >= 30 bps)
SL, TP, MAXH = 0.15, 0.30, 24   # stop and target from the card; 24 h hold is the card's taker control (the recipe holds 12 h)
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice: the card trades SOL only; BTC and ETH added as every scout test does
# also mine: checks on closed 1h bars instead of every minute, and a taker entry at the next open instead of a post-only limit
LABEL = ("ใกล้จุดสูงสุด 7 วัน 1 ชม. (ai-trading-arena SOL-LU taker) BTC ETH SOL: เหนือ SMA20 วัน ต่ำกว่าสูงสุด 7 วัน 0.05-0.30% "
         "ขึ้น 1 ชม. 0.3%+ ซื้อแท่งถัดไป ถือ 24 ชม. stop -15% เป้า +30% (backtest Binance 1 ชม. 2017-2026 หลังหัก 0.35%/ข้าง "
         "BTC 192 ไม้ -0.31% ETH 155 ไม้ -1.01% SOL 90 ไม้ +0.33% ต่อไม้ มัธยฐาน SOL 0% ตัวแฝดเข้าสุ่ม -0.41/-0.18/-0.14% "
         "permutation 200 รอบ 3 ปีล่าสุด p 0.080/0.602/0.085 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_nearhigh.json": ("rule", LABEL),
            "state_fwd_nearhigh_twin.json": ("random", "ใกล้จุดสูงสุด 7 วัน ตัวควบคุม: เข้าสุ่มเวลาเมื่อเหนือ SMA20 วัน ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):   # same as the scout's /tmp/scout_1534/bt.py ind() (SMA20 and 7-day high of completed UTC days)
    n, days, cur, dh, dc = len(b), [], None, None, None
    sma, h7 = [None] * n, [None] * n
    for i, x in enumerate(b):
        d = x["t"] // DAY
        if d != cur:
            if cur is not None:
                days.append((dc, dh))
            cur, dh = d, x["h"]
        dh, dc = max(dh, x["h"]), x["c"]
        if len(days) >= SMA_D:
            sma[i] = sum(c for c, _ in days[-SMA_D:]) / SMA_D
            h7[i] = max(h for _, h in days[-HIGH_D:])
    return sma, h7


def signal(b, i, sma, h7):
    if sma[i] is None or i < 1:
        return 0
    c = b[i]["c"]
    return 1 if c > sma[i] and GAP_LO <= c / h7[i] - 1 <= GAP_HI and c / b[i - 1]["c"] - 1 >= PUSH else 0


def exit_px(p, x):
    o, h, l = x["o"], x["h"], x["l"]
    p["n"] += 1
    if o <= p["stop"]: return o, "stop"
    if l <= p["stop"]: return p["stop"], "stop"
    if h >= p["tgt"]: return max(p["tgt"], o), "ถึงเป้า 30%"
    return (x["c"], "ครบ 24 ชม.") if p["n"] >= MAXH else (None, None)


def close(s, sym, px, t, why):
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    cool = s.setdefault("cool", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    sma, h7 = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px, why = exit_px(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + H1, why)
                cool[sym] = x["t"] + H1          # the next bar may not signal
                continue
        if sym in s["pos"] or x["t"] <= cool.get(sym, 0):
            continue
        if mode == "rule":
            d = signal(bars, i, sma, h7)
        else:
            d = 1 if sma[i] and x["c"] > sma[i] and rng.random() < TWIN_P else 0
        usd = s["start_usd"] / 3
        if not d or s["cash"] < usd * (1 + COST):
            continue
        e = bars[i + 1]["o"]
        s["cash"] -= usd + usd * COST
        why = "ใกล้จุดสูงสุด 7 วัน เหนือ SMA20 ขึ้น 1 ชม. 0.3%+" if mode == "rule" else "สุ่มเวลา เหนือ SMA20 วัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, n=0, stop=e * (1 - SL), tgt=e * (1 + TP),
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1h")
        except Exception as e:
            print("fwd_nearhigh fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
