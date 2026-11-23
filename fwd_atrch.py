#!/usr/bin/env python3
"""Forward paper test of ATR_CHANNEL_2H (Dkpiec/freqtrade-atr-channel, GitHub 23 Nov 2026, "PF 3.70, 55% WR on 15-symbol
2H futures") on BTC, ETH, SOL (opened 24 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked
to try weak ideas too). Fake money only, no leverage (the repo uses 5x).

On closed 2h Binance bars: close above the highest high of the 40 bars before it + 1.5 ATR14 (Wilder) while the last
closed day has close > EMA20 and EMA10 > EMA20 -> long at the next open; close below the 40-bar low - 1.5 ATR while the
day is the other way round -> short. Stop 1 ATR, target 4 ATR (4R), both from the signal bar's ATR, checked on bar
high/low from the entry bar on (gap through -> open, both touched -> stop); else out at the close of the 120th bar.
All numbers are the repo's. One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_atrch.json       BTC, ETH, SOL
  state_fwd_atrch_twin.json  control: random entry bars (TWIN_P per free bar) on the daily-trend side, same exits
  python3 fwd_atrch.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                  # per side, as every account here
H2, DAY = 2 * 3600 * 1000, 86400 * 1000
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo trades 15 futures symbols it does not list
LB, MULT, SL, TP, HOLD = 40, 1.5, 1.0, 4.0, 120   # the repo's values
TWIN_P = 1 / 300               # my choice: about the rule's rate in the backtest (123 ETH trades in 40,574 bars)
LABEL = ("ATR channel 2 ชม. (Dkpiec) BTC ETH SOL: ทะลุกรอบ 40 แท่ง + 1.5 ATR ตามเทรนด์ EMA10/20 รายวัน long และ short "
         "stop 1 ATR เป้า 4 ATR ถือไม่เกิน 120 แท่ง (backtest Binance 2 ชม. 2017-2026 หลังหัก 0.35%/ข้าง "
         "BTC 135 ไม้ -0.05% ETH 123 ไม้ +0.57% SOL 74 ไม้ -1.23% ต่อไม้ ชนะ 18-36% เข้าสุ่มฝั่งเทรนด์ -0.76/-0.47/-0.72% "
         "permutation 200 รอบ p 0.025/0.005/0.726)")
ACCOUNTS = {"state_fwd_atrch.json": ("rule", LABEL),
            "state_fwd_atrch_twin.json": ("random", "ATR channel ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งตามเทรนด์รายวัน stop 1 ATR เป้า 4 ATR ถือไม่เกิน 120 แท่งแบบเดียวกัน")}


def fetch_iv(sym, iv="2h"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ema(c, n):
    out, e, k = [None] * len(c), None, 2 / (n + 1)
    for i, v in enumerate(c):
        e = v if e is None else e + k * (v - e)
        out[i] = e
    return out


def ind(b):   # same as the scout's /tmp/scout_s24/bt.py (watr, daily_trend, sig_atrch)
    n, a, atr = len(b), None, [None] * len(b)
    for i in range(1, n):
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - b[i - 1]["c"]), abs(b[i]["l"] - b[i - 1]["c"]))
        a = tr if a is None else a + (tr - a) / 14
        if i >= 14:
            atr[i] = a
    days, cur = [], None
    for x in b:
        k = x["t"] // DAY
        if k != cur:
            days.append([k, x["c"]]); cur = k
        else:
            days[-1][1] = x["c"]
    c = [d[1] for d in days]
    e10, e20, trd = ema(c, 10), ema(c, 20), {}
    for i in range(20, len(days)):   # a day's trend is used by the bars of the next day (last fully closed day)
        trd[days[i][0] + 1] = 1 if c[i] > e20[i] and e10[i] > e20[i] else -1 if c[i] < e20[i] and e10[i] < e20[i] else 0
    trend = [trd.get(x["t"] // DAY, 0) for x in b]
    sig = [0] * n
    for i in range(LB + 1, n):
        if atr[i] is None:
            continue
        hh, ll = max(x["h"] for x in b[i - LB:i]), min(x["l"] for x in b[i - LB:i])
        sig[i] = 1 if b[i]["c"] > hh + MULT * atr[i] and trend[i] == 1 else -1 if b[i]["c"] < ll - MULT * atr[i] and trend[i] == -1 else 0
    return sig, atr, trend


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
    sig, atr, trend = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p, exited = s["pos"].get(sym), False
        if p and x["t"] >= p["entry_t"]:
            o, h, l, d = x["o"], x["h"], x["l"], p["d"]
            hit = (o if o <= p["stop"] else p["stop"] if l <= p["stop"] else max(p["tgt"], o) if h >= p["tgt"] else None) if d > 0 else \
                  (o if o >= p["stop"] else p["stop"] if h >= p["stop"] else min(p["tgt"], o) if l <= p["tgt"] else None)
            p["held"] = p.get("held", 0) + 1      # closed bars from the entry bar on, counted like the backtest
            if hit is not None:
                close(s, sym, hit, x["t"] + H2, "stop" if (hit - p["entry"]) * d < 0 else "ถึงเป้า 4 ATR")
                exited = True
            elif p["held"] >= HOLD:
                close(s, sym, x["c"], x["t"] + H2, "ถือครบ 120 แท่ง")
                exited = True
        if sym in s["pos"] or exited or not atr[i]:
            continue
        if mode == "rule":
            d = sig[i]
        else:
            d = trend[i] if trend[i] and rng.random() < TWIN_P else 0
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = "ทะลุกรอบ 40 แท่ง + 1.5 ATR ตามเทรนด์รายวัน" if mode == "rule" else "สุ่มแท่ง ฝั่งตามเทรนด์รายวัน"
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             stop=e - d * SL * atr[i], tgt=e + d * TP * atr[i], entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "2h")
        except Exception as e:
            print("fwd_atrch fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
