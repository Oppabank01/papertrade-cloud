#!/usr/bin/env python3
"""Forward paper test of BTC-ETH pairs trading by z-score (Crypto.com Research "Pair trading" Sep 2024: daily, 30-day
moving z-score; tomeelow/pairs-trading on GitHub, Nov 2026, showed the stock version has no edge after costs) in its
closest single-series form: trade the ratio itself on Binance daily ETHBTC, SOLBTC, BNBBTC bars (opened 23 Nov 2026 by
the scout; backtest in LABEL, opened at any p because the user asked to try weak ideas too). Fake money only.

After the close of daily bar i: z = (log close - mean of the last W log closes) / their population SD.
Flat and z <= -Z_IN -> long the ratio (coin cheap against BTC) at the next open; z >= Z_IN -> short it.
Long exits at the next open once z >= 0, short once z <= 0, or after MAX_D days. After an exit the same open may start
the other side if z is beyond Z_IN. One position per pair, one third of the start per pair, 0.35% per side (one leg;
a real two-leg pair would pay twice).
  state_fwd_pairz.json       ETHBTC, SOLBTC, BNBBTC
  state_fwd_pairz_twin.json  control: random side on random days (TWIN_P per free day), same exits
  python3 fwd_pairz.py"""
import math
import random
import statistics as st
import byttrade as B
from byttrade import iso, load, save, fetch, DAY

COST = 0.0035                          # per side, as every account here
SYMS = ["ETHBTC", "SOLBTC", "BNBBTC"]   # ETHBTC from the research; SOLBTC and BNBBTC added by me
W = 30                                 # the research's 30-day window
Z_IN = 2.0                             # my choice (the research gives no number in its summary); set before the backtest
MAX_D = 20                             # my choice: time stop in days
TWIN_P = 1 / 25                        # my choice: about the rule's entry rate per free pair-day in the backtest
LABEL = ("pairs z-score รายวัน ETHBTC SOLBTC BNBBTC (Crypto.com Research 2024 หน้าต่าง 30 วัน ผมเลือกเข้า |z| 2 "
         "ออกเมื่อ z กลับ 0 หรือครบ 20 วัน) long+short (backtest Binance รายวัน 2017-2026 หลังหัก 0.35%/ข้าง "
         "ETHBTC 105 ไม้ -2.40% มัธยฐาน +1.12% SOLBTC 71 ไม้ -7.35% มัธยฐาน +1.19% BNBBTC 104 ไม้ -4.39% มัธยฐาน +2.35% "
         "ชนะ 54-62% แต่ไม้แพ้ใหญ่ permutation 200 รอบทั้งกริด 4 แบบ p 0.995/0.995/1.000 ตก "
         "ตัวแฝดสุ่มฝั่ง -1.28/-2.90/-1.91% ปี 2024+ -1.67/+1.11/+0.56%)")
ACCOUNTS = {"state_fwd_pairz.json": ("rule", LABEL),
            "state_fwd_pairz_twin.json": ("random", "pairs z-score ตัวควบคุม: เข้าวันสุ่มฝั่งสุ่ม ออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def zscore(b, i, w=W):
    """z of bar i's close against the last w closes (log), None before w bars of history."""
    if i < w - 1:
        return None
    c = [math.log(x["c"]) for x in b[i - w + 1:i + 1]]
    sd = st.pstdev(c)
    return (c[-1] - st.fmean(c)) / sd if sd else 0.0


def leave(d, z, entry_t, nx_t):
    return (z >= 0 if d > 0 else z <= 0) or nx_t >= entry_t + MAX_D * DAY


def trades(b, first=W, w=W, z_in=Z_IN):
    """The backtest (the scout's /tmp/scout_1441.py calls this): list of dict(t, d, e, x), oldest first."""
    out, p = [], None
    for i in range(first, len(b) - 1):
        z = zscore(b, i, w)
        if z is None:
            continue
        nx = b[i + 1]
        if p and leave(p["d"], z, p["t"], nx["t"]):
            out.append(dict(p, x=nx["o"]))
            p = None
        if not p and abs(z) >= z_in:
            p = dict(t=nx["t"], d=-1 if z > 0 else 1, e=nx["o"])
    return out


def close(s, sym, px, t, why):   # as fwd_regime.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym, side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        z = zscore(bars, i)
        if z is None:
            continue
        nx = bars[i + 1]
        p = s["pos"].get(sym)
        if p and leave(p["d"], z, p["entry_t"], nx["t"]):
            close(s, sym, nx["o"], nx["t"], f"z {z:.2f}" if nx["t"] < p["entry_t"] + MAX_D * DAY else f"ครบ {MAX_D} วัน")
        if sym in s["pos"]:
            continue
        if mode == "rule":
            want = (-1 if z > 0 else 1) if abs(z) >= Z_IN else 0
        else:
            want = rng.choice((1, -1)) if rng.random() < TWIN_P else 0
        usd = s["start_usd"] / 3
        if not want or (want > 0 and s["cash"] < usd * (1 + COST)):
            continue
        e = nx["o"]
        why = f"z {z:.2f} สวนกลับค่าเฉลี่ย {W} วัน" if mode == "rule" else "สุ่มฝั่ง"
        s["cash"] += (-usd if want > 0 else usd) - usd * COST
        s["pos"][sym] = dict(side="long" if want > 0 else "short", d=want, qty=want * usd / e, entry=e, last=e, usd=usd,
                             entry_t=nx["t"], t=iso(nx["t"]), why=why)
        s["log"].append(dict(kind="buy", t=iso(nx["t"]), coin=sym, side=s["pos"][sym]["side"], px=e, usd=usd, why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_pairz fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
