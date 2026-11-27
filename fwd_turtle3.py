#!/usr/bin/env python3
"""Forward paper test of negariank-gif/turtle-trading-bot (GitHub, 17 Nov 2026, a daily Telegram alert called "turtle
algorithm": buy when the daily close is above the highest high of the 20 days before, stop = close - 3 x ATR14, on gold,
silver, BTC, DOGE, XRP, SOL, ETH, AVAX; no exit is written, the alert just repeats with a new stop each breakout day).
Opened 27 Nov 2026 by the scout as the closest mechanical version; backtest in LABEL, opened at any p because the user
asked to try weak ideas too. Fake money only.

On closed 1d Binance bars: flat and the close above the highest high of the 20 bars before -> long at the next open,
stop = signal close - 3 x ATR14 (simple mean of 14 true ranges, as main.py). Each closed bar from the entry bar on: the
low through the stop -> out at the stop (a gap through it fills at the open, except on the entry bar); else, if that bar
is again a breakout day, the stop is raised to max(stop, close - 3 x ATR14) (my reading of the repeated alert). No
target and no time stop. Long only, as the repo. Gold and silver are left out (no Binance spot pair; my choice).
One position per coin, one sixth of the start per coin, 0.35% per side.
  state_fwd_turtle3.json       BTC, ETH, SOL, XRP, DOGE, AVAX
  state_fwd_turtle3_twin.json  control: random entry days (TWIN_P per flat day), the same stop and raises
  python3 fwd_turtle3.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "AVAXUSDT"]   # the repo's coins on Binance spot
N_HIGH, ATR_N, STOP_ATR = 20, 14, 3.0  # from main.py
TWIN_P = 1 / 25                        # my choice: gives about as many trades as the rule in the backtest
LABEL = ("turtle รายวัน (negariank-gif): ปิดเหนือ high 20 วันก่อน ซื้อ stop 3 ATR ยกขึ้นทุกวันที่ทะลุใหม่ ไม่มีเป้า long "
         "BTC ETH SOL XRP DOGE AVAX (backtest Binance รายวันตั้งแต่เหรียญเข้า ถึง 26 พ.ย. 69 หลังหัก 0.35%/ข้าง "
         "BTC 46 ไม้ +8.65% ETH 48 +7.38% SOL 24 +112% XRP 40 +7.91% DOGE 33 +10.3% AVAX 27 +39.3% ต่อไม้ "
         "แต่มัธยฐาน -1.7/-3.8/+1.4/-8.0/-3.8/-8.7% ชนะ 28-50% กำไรมาจากไม้ใหญ่ไม่กี่ไม้ ปี 2025+ -0.13/+0.74/+1.76/-4.35/-2.02/+3.48% "
         "ตัวแฝดเข้าวันสุ่มออกแบบเดียวกัน +6.1/+6.1/+61/+8.3/+14.7/+29.1% permutation 200 รอบ "
         "p 0.015/0.040/0.005/0.100/0.348/0.010)")
ACCOUNTS = {"state_fwd_turtle3.json": ("rule", LABEL),
            "state_fwd_turtle3_twin.json": ("random", "turtle รายวัน ตัวควบคุม: เข้าวันสุ่ม stop 3 ATR ยกขึ้นวันทะลุแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def sma_atr(b, n):
    tr = [b[0]["h"] - b[0]["l"]] + [max(x["h"] - x["l"], abs(x["h"] - p["c"]), abs(x["l"] - p["c"])) for p, x in zip(b, b[1:])]
    return [None if i < n else sum(tr[i - n + 1:i + 1]) / n for i in range(len(b))]


def breakout(b, i):
    return i >= N_HIGH and b[i]["c"] > max(x["h"] for x in b[i - N_HIGH:i])


def stop_out(p, x):
    """One closed bar against long position p (dict with stop, entry_t): fill price if the stop is hit, else None."""
    if x["l"] <= p["stop"]:
        return p["stop"] if x["t"] == p["entry_t"] else min(x["o"], p["stop"])
    return None


def trades(b, first=N_HIGH + 1, rng=None):
    """The backtest (the scout's /tmp/scout_2320/bt.py calls this): list of dict(t, d, e, x, why), oldest first.
    rng given: the twin's entries (random day) with the same stop and raises."""
    atr = sma_atr(b, ATR_N)
    out, p = [], None
    for i in range(first, len(b) - 1):
        if p and b[i]["t"] >= p["entry_t"]:
            px = stop_out(p, b[i])
            if px is not None:
                out.append(dict(t=p["entry_t"], d=1, e=p["e"], x=px, why="stop"))
                p = None
            elif breakout(b, i) and atr[i] is not None:
                p["stop"] = max(p["stop"], b[i]["c"] - STOP_ATR * atr[i])
        if p or atr[i] is None:
            continue
        if breakout(b, i) if rng is None else rng.random() < TWIN_P:
            e = b[i + 1]["o"]
            p = dict(entry_t=b[i + 1]["t"], e=e, stop=b[i]["c"] - STOP_ATR * atr[i])
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
    atr = sma_atr(bars, ATR_N)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = stop_out(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + B.DAY, f"หลุด stop {STOP_ATR:g} ATR")
            elif breakout(bars, i) and atr[i] is not None:
                p["stop"] = max(p["stop"], x["c"] - STOP_ATR * atr[i])
        if sym in s["pos"] or atr[i] is None:
            continue
        if not (breakout(bars, i) if mode == "rule" else rng.random() < TWIN_P):
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 6
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd * (1 + COST)
        why = f"ปิดเหนือ high {N_HIGH} วันก่อน" if mode == "rule" else "สุ่มวัน"
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=x["c"] - STOP_ATR * atr[i],
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_turtle3 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
