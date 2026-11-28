#!/usr/bin/env python3
"""Forward paper test of "D3" from rubenx1303/crypto-backtesting (GitHub, Nov 2026, backtest/mejora.py class D3: a daily
Donchian 100 breakout the author froze after comparing several families on Bitvavo EUR pairs). Opened 28 Nov 2026 by the
scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too. Fake money only.

On closed 1d Binance bars (the repo's numbers): flat and the close above 1.01 x the highest high of the 100 days before
and above SMA100 -> long at the next open. Stop = signal close - 4 * ATR14 (Wilder, seeded with the SMA of the first 14
true ranges of the bars fetched). After each closed day: if the highest close since entry is above entry + 1.5 * ATR14
of that day, stop = max(stop, highest close - 6 * ATR14). A low at or under the stop sells at the stop (at the open on a
gap). No target, no time limit. The repo caps the book at 2 positions and sizes by 1% risk (at most 45%); here one
position per coin and one eighth of the start per coin (my choice, so every signal is taken). "Highest close" for the
trail and USDT pairs instead of EUR are my choices. No signal while held or on the exit day. 0.35% per side.
  state_fwd_d3trail.json       the repo's CORE 8: BTC ETH SOL XRP ADA LINK DOT AVAX
  state_fwd_d3trail_twin.json  control: random entry days (TWIN_P per free day above SMA100), the same stop and trail
  python3 fwd_d3trail.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = [c + "USDT" for c in ("BTC", "ETH", "SOL", "XRP", "ADA", "LINK", "DOT", "AVAX")]
LOOK, BUF, SMA_N, AN, SL, ACT, TRAIL = 100, 1.01, 100, 14, 4.0, 1.5, 6.0   # the repo's numbers
WARM = 130                             # the repo's warm-up: no signal before bar 130 of the series
TWIN_P = 1 / 115                       # my choice: the backtest's random control rate (2.5 x the rule's entries per day)
LABEL = ("D3 Donchian 100 วัน (rubenx1303/crypto-backtesting) 8 เหรียญ: ปิดเหนือจุดสูงสุด 100 วันเกิน 1% และเหนือ SMA100 ซื้อ "
         "stop 4 ATR แล้ว trailing 6 ATR เมื่อกำไรเกิน 1.5 ATR (backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง รวม 80 ไม้ "
         "เฉลี่ย +37.2% ต่อไม้ มัธยฐาน -7.2% ชนะ 40% CI +13.9 ถึง +65.5% BTC 12 ไม้ +32.2% ETH 13 ไม้ +30.1% SOL 7 ไม้ +136.3% "
         "ปี 2025 -6.6% (8 ไม้) 2026 -13.6% (6 ไม้) ตัวแฝดเข้าสุ่มเหนือ SMA100 มัธยฐาน +19.1% permutation 200 รอบกริด 9 แบบ "
         "BTC p 0.070 ETH p 0.085 SOL p 0.045 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_d3trail.json": ("rule", LABEL),
            "state_fwd_d3trail_twin.json": ("random", "D3 ตัวควบคุม: เข้าวันสุ่มเหนือ SMA100 stop 4 ATR trailing 6 ATR แบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    """Highest high of the LOOK days before, SMA100, Wilder ATR14 (same as the scout's /tmp/scout_1614/d3.py)."""
    n = len(b)
    hi, sma, atr, a, s, hs = [None] * n, [None] * n, [None] * n, None, 0.0, [x["h"] for x in b]
    for i, x in enumerate(b):
        if i >= LOOK:
            hi[i] = max(hs[i - LOOK:i])
        s += x["c"]
        if i >= SMA_N:
            s -= b[i - SMA_N]["c"]
        if i >= SMA_N - 1:
            sma[i] = s / SMA_N
        if i >= 1:
            p = b[i - 1]["c"]
            tr = max(x["h"] - x["l"], abs(x["h"] - p), abs(x["l"] - p))
            a = (a or 0) + tr / AN if i <= AN else (a * (AN - 1) + tr) / AN
            if i >= AN:
                atr[i] = a
    return hi, sma, atr


def hit(x, stop):
    return x["o"] if x["o"] <= stop else stop if x["l"] <= stop else None


def trail(stop, peak, entry, a):
    return max(stop, peak - TRAIL * a) if a and peak > entry + ACT * a else stop


def trades(b):
    """The backtest (same trades as the scout's /tmp/scout_1614/d3.py run()): (entry_t, entry, exit), oldest first."""
    hi, sma, atr = ind(b)
    out, i, n = [], WARM, len(b)
    while i < n - 1:
        if not (hi[i] and sma[i] and atr[i] and b[i]["c"] > hi[i] * BUF and b[i]["c"] > sma[i]):
            i += 1
            continue
        ei = i + 1
        e, stop, peak = b[ei]["o"], b[i]["c"] - SL * atr[i], b[ei]["o"]
        px, j = None, ei
        while j < n:
            px = hit(b[j], stop)
            if px is not None:
                break
            peak = max(peak, b[j]["c"])
            stop = trail(stop, peak, e, atr[j])
            j += 1
        if px is None:
            break
        out.append((b[ei]["t"], e, px))
        i = j + 1
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
    hi, sma, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or i < WARM:
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px = hit(x, p["stop"])
            if px is not None:
                close(s, sym, px, x["t"] + B.DAY, "stop 4 ATR" if p["stop"] == p["stop0"] else "trailing 6 ATR")
                exited = True
            else:
                p["peak"] = max(p["peak"], x["c"])
                p["stop"] = trail(p["stop"], p["peak"], p["entry"], atr[i])
        if sym in s["pos"] or exited or not (hi[i] and sma[i] and atr[i]):
            continue
        if mode == "rule":
            go, why = x["c"] > hi[i] * BUF and x["c"] > sma[i], "ปิดเหนือจุดสูงสุด 100 วัน 1% และเหนือ SMA100"
        else:
            go, why = x["c"] > sma[i] and rng.random() < TWIN_P, "สุ่มวันเหนือ SMA100"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 8
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et, stop = bars[i + 1]["t"], x["c"] - SL * atr[i]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=stop, stop0=stop, peak=e,
                             entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_d3trail fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
