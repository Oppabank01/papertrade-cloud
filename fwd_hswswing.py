#!/usr/bin/env python3
"""Forward paper test of the "Swing" strategy of bruce-quant/hsw-stock-bot (S&P 100 daily dips in strong uptrends, its
own report: 5.4% a year vs SPY 10.3%, random entry test p 0.40), moved to Binance daily coins. Opened 24 Nov 2026 by
the scout; backtest in LABEL. Fake money only.

On closed 1d Binance bars, every number from the repo's config.toml: close above SMA200 and SMA50 above SMA200, and
the close below SMA20 minus 2 population standard deviations of the last 20 closes -> long at the next open. Out at
the next open after the first close that is below the signal close minus 3 ATR14 (plain mean of true ranges), above
SMA20, or 20 bars after the entry bar. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_hswswing.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_hswswing_twin.json  control: random signal days (TWIN_P per flat day), same three exits
  python3 fwd_hswswing.py"""
import random, statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: 5 large coins = the repo's max_positions 5, so its ranking never binds
FAST, SLOW, BAND, K = 50, 200, 20, 2.0  # the repo's trend_fast/slow_days, band_days, band_std
ATRN, STOPK, HOLD = 14, 3.0, 20        # the repo's atr_days, stop_atr, max_hold_days (20 trading days -> 20 daily bars)
TWIN_P = 1 / 125                       # my choice: about the rule's entries per day in the backtest (112 trades on 14,000 coin days)
LABEL = ("HSW Swing รายวัน (bruce-quant/hsw-stock-bot ย้ายจากหุ้น S&P 100 มาเหรียญ) BTC ETH SOL BNB XRP: ราคาเหนือ SMA200 "
         "SMA50 เหนือ SMA200 และปิดใต้ Bollinger ล่าง 20/2 ซื้อเปิดวันถัดไป ออกเมื่อปิดใต้ราคาวันสัญญาณลบ 3 ATR14 ปิดเหนือ SMA20 "
         "หรือครบ 20 วัน (backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง รวม 112 ไม้ +1.40% ต่อไม้ มัธยฐาน +4.2% ชนะ 64% "
         "ก่อนหัก +2.1% BTC 26 ไม้ -0.08% ETH 30 ไม้ +3.27% SOL 18 ไม้ +1.41% BNB 21 ไม้ +0.84% XRP 17 ไม้ +1.06% "
         "ตัวแฝดเข้าวันสุ่ม -0.09 ถึง -0.42% permutation 200 รอบ p 0.622/0.318/0.547/0.701/0.478 ไม่ผ่าน)")
ACCOUNTS = {"state_fwd_hswswing.json": ("rule", LABEL),
            "state_fwd_hswswing_twin.json": ("random", "HSW Swing รายวัน ตัวควบคุม: เข้าวันสุ่ม ออกด้วยกฎ 3 ข้อเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def sma(c, n):
    out, s = [None] * len(c), 0.0
    for i, x in enumerate(c):
        s += x
        if i >= n:
            s -= c[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ind(b):
    """Per bar: close, SMA20, setup (dip in uptrend), stop level (close - 3 ATR14); None/False before warm-up."""
    c = [x["c"] for x in b]
    f, sl, mid = sma(c, FAST), sma(c, SLOW), sma(c, BAND)
    tr = [None] + [max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1])) for i in range(1, len(b))]
    setup, stop = [False] * len(b), [None] * len(b)
    for i in range(max(SLOW - 1, ATRN), len(b)):
        atr = sum(tr[i - ATRN + 1:i + 1]) / ATRN
        sd = st.pstdev(c[i - BAND + 1:i + 1])
        setup[i] = sd > 0 and c[i] > sl[i] and f[i] > sl[i] and c[i] < mid[i] - K * sd
        stop[i] = c[i] - STOPK * atr
    return c, mid, setup, stop


def trades(b):
    """The backtest (same as the scout's /tmp/scout_1015/bt.py trades()): (entry_t, entry, exit, why), oldest first."""
    c, mid, setup, stop = ind(b)
    out, i, n = [], 0, len(b)
    while i < n - 1:
        if not setup[i]:
            i += 1
            continue
        e, lv, why = b[i + 1]["o"], stop[i], None
        k = i + 1
        while k < n - 1:
            why = "stop" if c[k] < lv else "rebound" if c[k] > mid[k] else "time" if k - (i + 1) >= HOLD else None
            if why:
                break
            k += 1
        if not why:
            break
        out.append((b[i + 1]["t"], e, b[k + 1]["o"], why))
        i = k + 1
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
    c, mid, setup, stop = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars) or stop[i] is None:
            continue
        seen[sym] = x["t"]
        if sym in s["pos"]:
            p = s["pos"][sym]
            p["held"] = p.get("held", -1) + 1      # 0 on the entry bar's close, as k - (i + 1) in trades()
            why = ("ปิดใต้ stop 3 ATR" if c[i] < p["stop"] else "ปิดเหนือ SMA20" if c[i] > mid[i]
                   else "ครบ 20 วัน" if p["held"] >= HOLD else None)
            if why:
                close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], why)
            continue
        if mode == "rule":
            go, why = setup[i], "ปิดใต้ Bollinger ล่างในขาขึ้น"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มวัน"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 5
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, entry_t=et, t=iso(et), why=why,
                             stop=stop[i])
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd, why=why,
                             stop_set=round(stop[i], 8)))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_hswswing fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
