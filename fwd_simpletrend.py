#!/usr/bin/env python3
"""Forward paper test of "SimpleTrendOpt" (iralekseev-hub/freqtrade-bybit-bot, hyperopt numbers from SimpleTrendOpt.json),
opened 24 Nov 2026 by the scout. Backtest numbers are in ACCOUNTS labels below. Fake money only.

On closed 4h bars: EMA9 > EMA21, Supertrend(10, 3) up, RSI14 < 59, MACD(12, 26, 9) above its signal and close above the
Bollinger mid (SMA20) -> long; the mirror (EMA9 < EMA21, Supertrend down, RSI14 > 24, MACD below signal, close below SMA20)
-> short. Enter at the next open. Exits, all from the repo: stop -15.2%, ROI table 62.7% / 9.2% after 834 min / 5.1% after
2450 min / 0% after 7110 min, trailing 2% once 5.8% up, exit signal (EMA9 back across EMA21 and Supertrend flipped and
MACD across its signal) at the next open. The bot runs 3x leverage and freqtrade measures these on the leveraged profit, so
in price terms every one is divided by 3 (my choice: no leverage here, same price levels as the bot).
Checked on closed 4h bars: a gap through the stop fills at the open; stop and target in one bar = stop; the trailing
level uses the best price of the bars before the current one (my choice, no look-ahead inside a bar).
One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_simpletrend.json       BTC ETH SOL DOGE XRP (first five Binance spot coins of the repo's whitelist)
  state_fwd_simpletrend_twin.json  control: random entry times (1 in 30 free bars, my choice) on the EMA9/EMA21 side, same exits
  python3 fwd_simpletrend.py"""
import random
from byttrade import iso, load, save, fetch, H4, supertrend_dir

COST, TWIN_P, LEV = 0.0035, 1 / 30, 3
SL, TR_POS, TR_OFF = 0.152 / LEV, 0.02 / LEV, 0.058 / LEV
ROI = [(7110, 0.0), (2450, 0.051 / LEV), (834, 0.092 / LEV), (0, 0.627 / LEV)]   # minutes in trade -> price gain to take
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT"]
ACCOUNTS = {"state_fwd_simpletrend.json": ("rule", "SimpleTrendOpt 4 ชม. 5 เหรียญ long+short: EMA9/21 Supertrend RSI MACD BB กลาง ออกตามตาราง ROI ของ repo (backtest 2017-2026 หลังหัก 0.35%/ข้าง: BTC 1,253 ไม้ -0.64% ETH 1,452 ไม้ -0.64% SOL 1,262 ไม้ -0.62% DOGE 1,288 ไม้ -0.70% XRP 1,437 ไม้ -0.74% ต่อไม้ ก่อนหักราว 0% ตัวแฝดสุ่ม -0.60 ถึง -0.69% p 0.040/0.129/0.040/0.189/0.507)"),
            "state_fwd_simpletrend_twin.json": ("random", "SimpleTrendOpt ตัวควบคุม: เข้าสุ่มเวลา ฝั่งตาม EMA9/21 ออกแบบเดียวกัน")}


def ema(v, n):   # seeded with the SMA of the first n values, like talib
    out, k, e, seen = [None] * len(v), 2 / (n + 1), None, []
    for i, x in enumerate(v):
        if x is None:
            continue
        if e is None:
            seen.append(x)
            if len(seen) == n:
                e = sum(seen) / n; out[i] = e
            continue
        e = x * k + e * (1 - k); out[i] = e
    return out


def ind(b):
    c, n = [x["c"] for x in b], len(b)
    e9, e21, e12, e26 = ema(c, 9), ema(c, 21), ema(c, 12), ema(c, 26)
    macd = [a - b_ if a is not None and b_ is not None else None for a, b_ in zip(e12, e26)]
    sig = ema(macd, 9)
    rsi, ag, al = [None] * n, 0.0, 0.0
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        if i >= 14:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    mid, s = [None] * n, 0.0
    for i in range(n):
        s += c[i] - (c[i - 20] if i >= 20 else 0)
        if i >= 19:
            mid[i] = s / 20
    st = supertrend_dir(b)
    return [None if i < 60 or None in (e9[i], e21[i], macd[i], sig[i], rsi[i], mid[i]) else
            (e9[i] - e21[i], st[i], rsi[i], macd[i] - sig[i], c[i] - mid[i]) for i in range(n)]   # 60 = repo's startup candles


def signal(k):
    if k is None:
        return 0
    tr, st, rsi, md, bb = k
    if tr > 0 and st == 1 and rsi < 59 and md > 0 and bb > 0:
        return 1
    if tr < 0 and st == -1 and rsi > 24 and md < 0 and bb < 0:
        return -1
    return 0


def exit_signal(k, d):
    return k is not None and k[0] * d < 0 and k[1] == -d and k[3] * d < 0


def bar_exit(p, x):
    """Price this closed bar exits at (stop, trailing or ROI), or None; updates the best price after checking."""
    d, e, o, h, l = p["d"], p["entry"], x["o"], x["h"], x["l"]
    mins = (x["t"] - p["entry_t"]) / 60000
    roi = next(r for m, r in ROI if mins >= m)
    stop, tgt = e * (1 - d * SL), e * (1 + d * roi)
    if (p["best"] - e) * d >= e * TR_OFF:
        tr = p["best"] * (1 - d * TR_POS)
        stop = max(stop, tr) if d > 0 else min(stop, tr)
    p["best"] = max(p["best"], h) if d > 0 else min(p["best"], l)
    if d > 0:
        return (o, "stop") if o <= stop else (stop, "stop") if l <= stop else (max(tgt, o), "ROI") if h >= tgt else (None, "")
    return (o, "stop") if o >= stop else (stop, "stop") if h >= stop else (min(tgt, o), "ROI") if l <= tgt else (None, "")


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
    k = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            px, why = bar_exit(p, x)
            if px is not None:
                close(s, sym, px, x["t"] + H4, why)
                exited = True
            elif exit_signal(k[i], p["d"]):
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], "สัญญาณออก EMA Supertrend MACD")
                exited = True
        if sym in s["pos"] or exited or k[i] is None:
            continue
        if mode == "rule":
            d = signal(k[i])
        else:
            d = (1 if k[i][0] > 0 else -1) if rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "EMA9/21 Supertrend RSI MACD BB ตรงกัน" if mode == "rule" else "สุ่มเวลา ฝั่งตาม EMA9/21"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd, best=e,
                             entry_t=bars[i + 1]["t"], t=iso(bars[i + 1]["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(bars[i + 1]["t"]), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("simpletrend fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
