#!/usr/bin/env python3
"""Forward paper test of Neeraj Joshi's "20 Candle Strategy" (YouTube, 21 Oct 2026; rules as locked by
strategyverdict/strategy-verdict-backtests, folder 20-candle-swing-neeraj-joshi: on Binance BTCUSDT perp 4h 2020 to Oct
2026 they got 346 trades, 38.2% win, +0.175R per trade after costs, PF 1.45, out-of-sample 2024+ PF 1.24). Opened
28 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 4h Binance bars: close above the highest high of the 20 bars before it and above EMA200 -> long at the next
open; close below the lowest low of the 20 bars before and below EMA200 -> short. Initial stop = entry -/+ 2.5 x ATR14
(Wilder) of the signal bar. Each closed bar from the entry bar on: the stop is checked first (a gap through it fills at
the open); if not hit, the trail becomes (highest high since entry - 3 x ATR14 of that bar) for longs, (lowest low +
3 ATR) for shorts, never loosened. No target, no time stop. The exit bar's own close may signal a new entry (my choice).
One position per coin, one third of the start per coin, 0.35% per side (the source used 0.05% + slippage on perps).
  state_fwd_c20swing.json       BTC, ETH, SOL
  state_fwd_c20swing_twin.json  control: random entry bars (TWIN_P per flat bar) on the EMA200 side, the same stop and trail
  python3 fwd_c20swing.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                                    # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]         # my choice: the source is BTC only; ETH and SOL as the other 4h accounts
N, EMA_N, ATR_N, STOP_ATR, TRAIL_ATR = 20, 200, 14, 2.5, 3.0   # from the video / the repo's RULES.md
TWIN_P = 1 / 30                                  # my choice: about as many trades as the rule in the backtest
LABEL = ("20 แท่ง 4 ชม. (Neeraj Joshi ทดสอบโดย strategyverdict): ปิดทะลุ high/low 20 แท่งก่อน ตามฝั่ง EMA200 "
         "stop 2.5 ATR แล้ว trail 3 ATR จากจุดสุดตั้งแต่เข้า ไม่มีเป้า long/short BTC ETH SOL "
         "(backtest Binance spot 4h ตั้งแต่เหรียญเข้า ถึง 28 พ.ย. 69 หลังหัก 0.35%/ข้าง BTC 468 ไม้ +0.19% ETH 483 +0.20% "
         "SOL 340 -0.11% ต่อไม้ มัธยฐาน -1.5/-2.3/-2.8% ชนะ 34-35% ปี 2024+ -0.29/-0.00/-0.57% "
         "ตัวแฝดเข้าสุ่มออกแบบเดียวกัน -0.00/+0.33/-0.17% permutation 200 รอบก่อนหัก p 0.005/0.005/0.075)")
ACCOUNTS = {"state_fwd_c20swing.json": ("rule", LABEL),
            "state_fwd_c20swing_twin.json": ("random", "20 แท่ง 4 ชม. ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งตาม EMA200 stop และ trail แบบเดียวกัน")}


def ind(b):
    """EMA200 of closes (seeded with the first close, used from bar EMA_N on) and Wilder ATR14."""
    n, k = len(b), 2 / (EMA_N + 1)
    ema, atr, e, a = [None] * n, [None] * n, b[0]["c"], 0.0
    for i in range(n):
        e = b[i]["c"] if i == 0 else e + k * (b[i]["c"] - e)
        if i >= EMA_N:
            ema[i] = e
        if i:
            tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
            a = tr if i == 1 else (a * (ATR_N - 1) + tr) / ATR_N
            if i >= ATR_N:
                atr[i] = a
    return ema, atr


def signal(b, i, ema):
    if i < N or ema[i] is None:
        return 0
    c = b[i]["c"]
    if c > ema[i] and c > max(x["h"] for x in b[i - N:i]):
        return 1
    if c < ema[i] and c < min(x["l"] for x in b[i - N:i]):
        return -1
    return 0


def bar_exit(p, x, atr_now):
    """One closed bar against position p (d, stop, ext): fill price if the stop is hit, else None and the trail moves."""
    d, st = p["d"], p["stop"]
    if d > 0:
        if x["o"] <= st or x["l"] <= st:
            return min(x["o"], st)
        p["ext"] = max(p["ext"], x["h"])
        if atr_now:
            p["stop"] = max(st, p["ext"] - TRAIL_ATR * atr_now)
    else:
        if x["o"] >= st or x["h"] >= st:
            return max(x["o"], st)
        p["ext"] = min(p["ext"], x["l"])
        if atr_now:
            p["stop"] = min(st, p["ext"] + TRAIL_ATR * atr_now)
    return None


def trades(b, first=EMA_N + 1, rng=None):
    """The backtest (the scout's /tmp/scout_1436/bt.py calls this): list of dict(t, d, e, x), oldest first.
    rng given: the twin's entries (random bar, side of EMA200) with the same stop and trail."""
    ema, atr = ind(b)
    out, p = [], None
    for i in range(first, len(b) - 1):
        if p and b[i]["t"] >= p["entry_t"]:
            px = bar_exit(p, b[i], atr[i])
            if px is not None:
                out.append(dict(t=p["entry_t"], d=p["d"], e=p["e"], x=px))
                p = None
        if p or atr[i] is None or ema[i] is None:
            continue
        if rng is None:
            d = signal(b, i, ema)
        else:
            d = (1 if b[i]["c"] > ema[i] else -1) if rng.random() < TWIN_P else 0
        if d:
            e = b[i + 1]["o"]
            p = dict(entry_t=b[i + 1]["t"], d=d, e=e, stop=e - d * STOP_ATR * atr[i], ext=e)
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
    ema, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < 1:
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = bar_exit(p, x, atr[i])
            if px is not None:
                close(s, sym, px, x["t"] + B.H4, "stop" if (px - p["entry"]) * p["d"] < 0 else "trail 3 ATR")
        if sym in s["pos"] or atr[i] is None or ema[i] is None:
            continue
        if mode == "rule":
            d = signal(bars, i, ema)
        else:
            d = (1 if x["c"] > ema[i] else -1) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = f"ปิดทะลุกรอบ {N} แท่ง ตามฝั่ง EMA{EMA_N}" if mode == "rule" else "สุ่มแท่ง ฝั่งตาม EMA200"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * STOP_ATR * atr[i], ext=e, entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_c20swing fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
