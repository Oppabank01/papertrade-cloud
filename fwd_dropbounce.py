#!/usr/bin/env python3
"""Forward paper test of "daily big-drop bounce" on BTC, ETH, SOL (opened 23 Nov 2026 from a batch of simple bar ideas;
backtest in LABEL below, opened at any p because the user asked to try everything). Fake money only.

On closed daily Binance bars: a day that closes TRIG or worse -> long at the next daily open. Stop and target 1.5 ATR14
from the entry (given by the idea), checked on closed daily bars (gap through fills at the open, both touched = stop),
otherwise closed at the close of the HOLD-th day. Long only. One position per coin, one third of the start per coin,
0.35% per side.
  state_fwd_dropbounce.json       BTC, ETH, SOL
  state_fwd_dropbounce_twin.json  control: random entry days (TWIN_P per free day), same exits
  python3 fwd_dropbounce.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, DAY

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SL = TP = 1.5                      # ATR14 multiples, from the idea
# grid tried in-sample (bars before 2024, BTC+ETH+SOL pooled): drop 5/7/10% or 2 ATR x hold 1/2/3 days = 12 settings
GRID = [(k, h) for k in (("pct", 0.05), ("pct", 0.07), ("pct", 0.10), ("atr", 2.0)) for h in (1, 2, 3)]
TRIG, HOLD = ("pct", 0.10), 1      # chosen: best pooled in-sample (pre-2024) mean per trade after costs
TWIN_P = 1 / 60                    # the rule traded 144 times in ~9,000 coin-days, so the twin trades about as often
LABEL = ("ดีดหลังร่วงแรงรายวัน BTC ETH SOL: ปิดวันลบ 10% ขึ้นไป ซื้อเปิดวันถัดไป stop/เป้า 1.5 ATR ไม่โดนก็ปิดตอนปิดวันนั้น "
         "(backtest 2017-2026 หลังหัก 0.35%/ข้าง 144 ไม้ เฉลี่ย +1.02% มัธยฐาน +0.57% ชนะ 56% p 0.24 ไม่ผ่าน ปี 2024+ 19 ไม้ +0.79%)")
ACCOUNTS = {"state_fwd_dropbounce.json": ("rule", LABEL),
            "state_fwd_dropbounce_twin.json": ("random", "ดีดหลังร่วงแรง ตัวควบคุม: ซื้อวันสุ่ม ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def atr14(b):   # Wilder ATR14, same seeding as pullback.ind
    atr, a = [None] * len(b), 0.0
    for i in range(1, len(b)):
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
        a = tr if i == 1 else (a * 13 + tr) / 14
        if i >= 14:
            atr[i] = a
    return atr


def signal(b, i, atr, trig=TRIG):
    if i < 1 or atr[i] is None:
        return False
    if trig[0] == "pct":
        return b[i]["c"] / b[i - 1]["c"] - 1 <= -trig[1]
    return b[i]["c"] - b[i - 1]["c"] <= -trig[1] * atr[i]


def hit(x, stop, tgt, d):
    o, h, l = x["o"], x["h"], x["l"]
    if d > 0:
        return o if o <= stop else stop if l <= stop else max(tgt, o) if h >= tgt else None
    return o if o >= stop else stop if h >= stop else min(tgt, o) if l <= tgt else None


def trades(b, trig=TRIG, hold=HOLD, first=15, atr=None):
    """The backtest: list of dict(t, d, e, x) on closed bars, oldest first."""
    atr, out, i, n = atr or atr14(b), [], first, len(b)
    while i < n - 1:
        if not signal(b, i, atr, trig):
            i += 1
            continue
        e, t0 = b[i + 1]["o"], b[i + 1]["t"]
        stop, tgt, px, j = e - SL * atr[i], e + TP * atr[i], None, i + 1
        while j < n:
            px = hit(b[j], stop, tgt, 1)
            if px is None and b[j]["t"] >= t0 + (hold - 1) * DAY:
                px = b[j]["c"]
            if px is not None:
                break
            j += 1
        if px is None:
            break
        out.append(dict(t=t0, d=1, e=e, x=px))
        i = j + 1
    return out


def close(s, sym, px, t, why):   # as pullback.close
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
    atr = atr14(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px, why = hit(x, p["stop"], p["tgt"], 1), None
            if px is not None:
                why = "stop" if px < p["entry"] else "ถึงเป้า 1.5 ATR"
            elif x["t"] >= p["until"]:
                px, why = x["c"], f"ครบ {HOLD} วัน"
            if px is not None:
                close(s, sym, px, x["t"] + DAY, why)
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if not (signal(bars, i, atr) if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, t0, usd = bars[i + 1]["o"], bars[i + 1]["t"], s["start_usd"] / 3
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += -usd - usd * COST
        why = f"ปิดวันลบ {bars[i]['c'] / bars[i - 1]['c'] - 1:+.1%}" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=e - SL * atr[i],
                             tgt=e + TP * atr[i], until=t0 + (HOLD - 1) * DAY, entry_t=t0, t=iso(t0), why=why)
        s["log"].append(dict(kind="buy", t=iso(t0), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_dropbounce fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
