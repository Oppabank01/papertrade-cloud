#!/usr/bin/env python3
"""Forward paper test of the baseline of yfwwwwww/hyperliquid-quant-bot (GitHub, 24 Nov 2026, a Hyperliquid perp bot
whose README says every smarter filter failed out of sample and only this plain baseline was kept): EMA20 / EMA100 cross
on 4h bars with an EMA200 trend filter and a 3 ATR stop, long and short, on BTC, ETH, SOL. Opened 27 Nov 2026 by the
scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h Binance bars (strategy.py, backtest.py and config.example.json of the repo):
  EMA20 crosses above EMA100 (previous bar at or below) and the close above EMA200 -> long at the next open;
  EMA20 crosses below EMA100 and the close below EMA200 -> short at the next open.
  Stop = entry -/+ 3 x ATR14 (fixed, no target). Each closed bar from the entry bar on: the low (high for a short)
  through the stop -> out at the stop (a gap through it fills at the open, except on the entry bar); else EMA20 crossing
  back against the position -> out at the next open (my choice: the repo fills at that bar's close; the next open is
  what a bar-by-bar walk can do). A cross exit and a new entry on the same bar flip the position.
EMAs seeded with the first close of the bars fetched (my choice; 1000 4h bars make the seed irrelevant for EMA200).
ATR14 Wilder from byttrade. One position per coin, one third of the start per coin, 0.35% per side, no leverage (the
repo runs 3x and risk-sizes 1% per trade; my choice: a fixed third, as every scout account).
  state_fwd_ema20x100.json       BTC, ETH, SOL
  state_fwd_ema20x100_twin.json  control: random entry bars (TWIN_P per flat bar), random side, the same stop and exits
  python3 fwd_ema20x100.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch, wilder_atr

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # the repo's three coins
FAST, SLOW, TREND, ATR_N, STOP_ATR = 20, 100, 200, 14, 3.0   # from the repo's config.example.json
TWIN_P = 1 / 55                        # my choice: gives about as many trades as the rule in the backtest
LABEL = ("EMA20 ตัด EMA100 4 ชม. กรองด้วย EMA200 long+short stop 3 ATR (yfwwwwww/hyperliquid-quant-bot) BTC ETH SOL "
         "(backtest Binance 4 ชม. 2017 ถึง 27 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 173 ไม้ +2.64% ETH 176 ไม้ +3.11% SOL 122 ไม้ "
         "+7.15% ต่อไม้ มัธยฐาน -3.0/-3.6/-4.8% ชนะ 27-35% ขา long พากำไร ขา short ราว 0% ปี 2025+ +0.71/+3.73/+2.49% "
         "ตัวแฝดเข้าสุ่มออกแบบเดียวกัน +0.57/+0.68/+6.74% permutation 200 รอบบน 6,000 แท่งล่าสุด p 0.055/0.045/0.090)")
ACCOUNTS = {"state_fwd_ema20x100.json": ("rule", LABEL),
            "state_fwd_ema20x100_twin.json": ("random", "EMA20x100 ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งสุ่ม stop 3 ATR และออกเมื่อ EMA ตัดสวนแบบเดียวกัน")}


def ema(c, n):
    k, out = 2 / (n + 1), [c[0]]
    for x in c[1:]:
        out.append(out[-1] + k * (x - out[-1]))
    return out


def lines(b):
    c = [x["c"] for x in b]
    return ema(c, FAST), ema(c, SLOW), ema(c, TREND), wilder_atr(b, ATR_N)


def cross(f, s, i):
    """+1 = EMA20 crossed above EMA100 on bar i, -1 = crossed below, 0 = no cross."""
    if f[i - 1] <= s[i - 1] and f[i] > s[i]:
        return 1
    if f[i - 1] >= s[i - 1] and f[i] < s[i]:
        return -1
    return 0


def signal(b, i, f, s, tr):
    d = cross(f, s, i)
    return d if d and (b[i]["c"] - tr[i]) * d > 0 else 0


def stop_out(p, x):
    """One closed bar against position p (dict with d, stop, entry_t): fill price if the stop is hit, else None."""
    first = x["t"] == p["entry_t"]
    if p["d"] > 0 and x["l"] <= p["stop"]:
        return p["stop"] if first else min(x["o"], p["stop"])
    if p["d"] < 0 and x["h"] >= p["stop"]:
        return p["stop"] if first else max(x["o"], p["stop"])
    return None


def trades(b, first=TREND + 1):
    """The backtest (the scout's /tmp/scout_2138/bt.py calls this): list of dict(t, d, e, x, why), oldest first."""
    f, s, tr, atr = lines(b)
    out, p = [], None
    for i in range(first, len(b) - 1):
        if p and b[i]["t"] >= p["entry_t"]:
            px = stop_out(p, b[i])
            if px is not None:
                out.append(dict(t=p["entry_t"], d=p["d"], e=p["e"], x=px, why="stop"))
                p = None
            elif cross(f, s, i) == -p["d"]:
                out.append(dict(t=p["entry_t"], d=p["d"], e=p["e"], x=b[i + 1]["o"], why="cross"))
                p = None
        if p or atr[i] is None:
            continue
        d = signal(b, i, f, s, tr)
        if d:
            e = b[i + 1]["o"]
            p = dict(entry_t=b[i + 1]["t"], d=d, e=e, stop=e - d * STOP_ATR * atr[i])
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
    f, sl, tr, atr = lines(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = stop_out(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + B.H4, f"หลุด stop {STOP_ATR:g} ATR")
            elif cross(f, sl, i) == -p["d"]:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "EMA20 ตัด EMA100 สวนทาง")
        if sym in s["pos"] or atr[i] is None:
            continue
        d = signal(bars, i, f, sl, tr) if mode == "rule" else (rng.choice((1, -1)) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = (f"EMA20 ตัด{'ขึ้น' if d > 0 else 'ลง'} EMA100 ปิด{'เหนือ' if d > 0 else 'ใต้'} EMA200" if mode == "rule"
               else "สุ่มแท่ง สุ่มฝั่ง")
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * STOP_ATR * atr[i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e,
                             usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_ema20x100 fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
