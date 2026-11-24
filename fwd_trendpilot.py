#!/usr/bin/env python3
"""Forward paper test of the exit engine of erikunterberger/trendpilot (an LLM picks US stocks, code sets every stop),
moved to Binance daily coins with a mechanical entry in place of the LLM pick. Opened 24 Nov 2026 by the scout;
backtest in LABEL. Fake money only.

On closed 1d bars: close above SMA50 above SMA200 and RSI14 below 75 -> long at the next open. Stop 2 ATR14 below the
entry (R); once a high reaches entry + 1R the stop moves to the entry and then trails 3 ATR14 below the highest high,
only moving up; still below entry + 0.5R after 14 bars -> out at the next open. Stops are checked on closed daily bars,
a gap through the stop fills at the open. One position per coin, one fifth of the start per coin, 0.35% per side.
  state_fwd_trendpilot.json       BTC, ETH, SOL, BNB, XRP
  state_fwd_trendpilot_twin.json  control: random entry days (TWIN_P per flat day), same exits
  python3 fwd_trendpilot.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]   # my choice: the five large coins fwd_hswswing uses
FAST, SLOW = 50, 200                   # the repo's 50/200-day averages; "trend" = close > SMA50 > SMA200 is my reading
RSI_MAX = 75                           # the repo's "overextended" RSI; above it the repo waits for a pullback, here: no entry
SL = 2.0                               # the repo's 2.0 ATR stop for short-term ideas (1.5 / 2.0 / 2.5 by category)
TRAIL = 3.0                            # my choice: middle of the repo's 2.5 to 3.5 ATR trail
FLAT_BARS, FLAT_R = 14, 0.5            # the repo's "two weeks in and still below +1/2 stop-width"; 14 daily bars
TWIN_P = 1 / 25                        # my choice: gives the twin about as many trades as the rule in the backtest
LABEL = ("TrendPilot ทางออก (erikunterberger) รายวัน BTC ETH SOL BNB XRP: ปิดเหนือ SMA50 เหนือ SMA200 RSI ต่ำกว่า 75 ซื้อ "
         "stop 2 ATR ถึง +1R ย้าย stop ไปทุน แล้ว trail 3 ATR ใต้จุดสูงสุด 14 วันยังไม่ถึง +0.5R ออก "
         "(backtest Binance 1d 2017-2026 หลังหัก 0.35%/ข้าง BTC 71 ไม้ +2.70% ETH 66 ไม้ +4.05% SOL 53 ไม้ +6.39% "
         "BNB 80 ไม้ +8.77% XRP 63 ไม้ +1.78% ต่อไม้ มัธยฐานติดลบเกือบทุกเหรียญ ตัวแฝดเข้าวันสุ่มทางออกเดียวกัน "
         "+1.06/+1.47/+6.02/+4.81/+1.31% permutation 200 รอบ p 0.040/0.020/0.065/0.010/0.259 ไม่ผ่าน 0.01 ยกเว้น BNB ที่เส้นพอดี "
         "ปี 2024-2026 อ่อนลง)")
ACCOUNTS = {"state_fwd_trendpilot.json": ("rule", LABEL),
            "state_fwd_trendpilot_twin.json": ("random", "TrendPilot ตัวควบคุม: เข้าวันสุ่ม ทางออกแบบเดียวกัน")}


def fetch_iv(sym, iv="1d"):
    """byttrade.fetch with another Binance interval (byttrade.URL is fixed at 4h); prices still only via byttrade.fetch."""
    old = B.URL
    B.URL = old.replace("interval=4h", "interval=" + iv)
    try:
        return fetch(sym)
    finally:
        B.URL = old


def ind(b):
    """Per bar: SMA50, SMA200, Wilder RSI14 and ATR14 (None until defined), as pullback.ind."""
    c, n = [x["c"] for x in b], len(b)
    f, s, rsi, atr = [None] * n, [None] * n, [None] * n, [None] * n
    sf = ss = ag = al = a = 0.0
    for i in range(n):
        sf += c[i]; ss += c[i]
        if i >= FAST:
            sf -= c[i - FAST]
        if i >= SLOW:
            ss -= c[i - SLOW]
        if i >= FAST - 1:
            f[i] = sf / FAST
        if i >= SLOW - 1:
            s[i] = ss / SLOW
    for i in range(1, n):
        d = c[i] - c[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= 14:
            ag += g / 14; al += l / 14
        else:
            ag = (ag * 13 + g) / 14; al = (al * 13 + l) / 14
        tr = max(b[i]["h"] - b[i]["l"], abs(b[i]["h"] - c[i - 1]), abs(b[i]["l"] - c[i - 1]))
        a = tr if i == 1 else (a * 13 + tr) / 14
        if i >= 14:
            rsi[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
            atr[i] = a
    return f, s, rsi, atr


def signal(x, f, s, rsi):
    return f is not None and s is not None and rsi is not None and x["c"] > f > s and rsi < RSI_MAX


def manage(p, x, atr):
    """One closed bar for an open long p. Returns (price, why) to sell now, ("next", why) to sell at the next open, or None."""
    if x["o"] <= p["stop"]:
        return x["o"], "หลุด stop (เปิดกระโดด)"
    if x["l"] <= p["stop"]:
        return p["stop"], "หลุด stop" if p["stop"] < p["entry"] else "trail / stop ที่ทุน"
    p["hi"] = max(p["hi"], x["h"])
    if p["hi"] >= p["entry"] + p["R"]:
        p["stop"] = max(p["stop"], p["entry"], p["hi"] - TRAIL * atr)
    p["held"] += 1
    if p["held"] >= FLAT_BARS and x["c"] < p["entry"] + FLAT_R * p["R"]:
        return "next", "14 วันยังไม่ถึง +0.5R"
    return None


def trades(b, go=None):
    """The backtest on a full history: (entry_t, entry, exit, t of the bar that triggered the exit) oldest first.
    go(i) replaces the rule's signal (twin)."""
    f, s, rsi, atr = ind(b)
    out, p = [], None
    for i in range(len(b) - 1):
        x = b[i]
        if p and x["t"] >= p["entry_t"]:
            r = manage(p, x, atr[i])
            if r:
                out.append((p["entry_t"], p["entry"], b[i + 1]["o"] if r[0] == "next" else r[0], x["t"]))
                p = None
                continue
        if p or not atr[i]:
            continue
        if go(i) if go else signal(x, f[i], s[i], rsi[i]):
            e = b[i + 1]["o"]
            p = dict(entry=e, R=SL * atr[i], stop=e - SL * atr[i], hi=e, held=0, entry_t=b[i + 1]["t"])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST,
                         stop_set=round(p["stop"], 8), why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    f, sm, rsi, atr = ind(bars)
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            r = manage(p, x, atr[i])
            if r:
                if r[0] == "next":
                    close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], r[1])
                else:
                    close(s, sym, r[0], x["t"] + B.DAY, r[1])
                continue
        if sym in s["pos"] or not atr[i]:
            continue
        if mode == "rule":
            go, why = signal(x, f[i], sm[i], rsi[i]), "เหนือ SMA50 เหนือ SMA200 RSI ต่ำกว่า 75"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มวัน"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 5
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, R=SL * atr[i], stop=e - SL * atr[i],
                             hi=e, held=0, entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd,
                             stop_set=round(e - SL * atr[i], 8), why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch_iv(sym, "1d")
        except Exception as e:
            print("fwd_trendpilot fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
