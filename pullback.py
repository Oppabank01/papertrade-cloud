#!/usr/bin/env python3
"""Forward paper test of "trend_pullback_champion" (Pyrochem/universal-quant-tournament-mcp), opened 23 Nov 2026 after
the scout's backtest (Binance 4h 2017-2026, 0.35%/side: BTC +0.46%/trade p 0.010, ETH +0.94% p 0.015, SOL +0.13%
p 0.498; not a pass, opened because the user asked to try weak ideas too). Fake money only.

On closed 4h bars: close above SMA200 and RSI14 <= 42 and a green bar -> long; close below SMA200 and RSI14 >= 58 and a
red bar -> short. Enter at the next open, stop 2 ATR14, target 4 ATR, checked on closed 4h bars; a gap through the stop
fills at the open; both touched = stop. One position per coin, one third of the start per coin, 0.35% per side.
  state_tpc.json       BTC, ETH, SOL
  state_tpc_twin.json  control: random entry times (1 in 40 free bars) on the SMA200 side, same exits
  python3 pullback.py"""
import random
from byttrade import iso, load, save, fetch, H4

COST, TWIN_P = 0.0035, 1 / 40
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
ACCOUNTS = {"state_tpc.json": ("rule", "trend pullback 4 ชม. BTC ETH SOL: เหนือ SMA200 RSI ย่อถึง 42 แท่งเขียว (short กลับกัน) stop 2 ATR เป้า 4 ATR"),
            "state_tpc_twin.json": ("random", "trend pullback ตัวควบคุม: เข้าสุ่มเวลา ฝั่งตาม SMA200 ออกแบบเดียวกัน")}


def ind(b):   # same as the scout's /tmp/scout_tpc.py
    c, n = [x["c"] for x in b], len(b)
    sma, rsi, atr, s, ag, al, a = [None] * n, [None] * n, [None] * n, 0.0, 0.0, 0.0, 0.0
    for i in range(n):
        s += c[i]
        if i >= 200:
            s -= c[i - 200]
        if i >= 199:
            sma[i] = s / 200
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        a = tr if i == 1 else (a * 13 + tr) / 14
        if i >= 14:
            atr[i] = a
    return sma, rsi, atr


def signal(x, sma, rsi):
    if sma is None or rsi is None:
        return 0
    if x["c"] > sma and rsi <= 42 and x["c"] > x["o"]:
        return 1
    if x["c"] < sma and rsi >= 58 and x["c"] < x["o"]:
        return -1
    return 0


def close(s, sym, px, t, why):
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
    sma, rsi, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            if hit is not None:
                close(s, sym, hit, x["t"] + H4, "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 4 ATR")
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "rule":
            d = signal(x, sma[i], rsi[i])
        else:
            d = (1 if x["c"] > sma[i] else -1) if sma[i] and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ย่อในเทรนด์ SMA200" if mode == "rule" else "สุ่มเวลา ฝั่งตาม SMA200"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * 2 * atr[i], tgt=e + d * 4 * atr[i], entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("pullback fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
