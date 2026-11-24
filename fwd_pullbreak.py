#!/usr/bin/env python3
"""Forward paper test of "pullback, then breakout" from itzalisha99/pump-fun-paper-sprint (Breakout Rider, a make.fun
bounty bot on pump.fun bonding curves), moved to Binance 4h bars of meme coins. Opened 24 Nov 2026 by the scout;
backtest in LABEL. Fake money only.

On closed 4h bars: the highest high of the last LOOK bars is the old peak; if the lowest low after that peak went at
least PULL below it and this bar closes more than LIFT above it -> long at the next open. Hard stop -STOP; once a high
reaches +TRAIL_ON the stop trails TRAIL below the highest high (only up); take all at +TP; out at the next open after
MAX_HOLD bars. Stops and the target are checked on closed bars (stop first), a gap fills at the open.
One position per coin, one sixth of the start per coin, 0.35% per side.
  state_fwd_pullbreak.json       DOGE, SHIB, PEPE, FLOKI, BONK, WIF
  state_fwd_pullbreak_twin.json  control: random entry bars (TWIN_P per flat bar), same exits
  python3 fwd_pullbreak.py"""
import random
import byttrade as B
from byttrade import iso, load, save, fetch

COST = 0.0035                          # per side, as every account here
SYMS = ["DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT", "WIFUSDT"]   # my choice: Binance spot meme coins
LOOK = 60                              # my choice: the repo's "early peak" since creation read as a 10-day (60 x 4h) peak
PULL = 0.15                            # my choice: the repo's 25% retrace gave 7 trades in 6 coins' whole 4h history
LIFT = 0.03                            # my choice: the repo's 7% lift scaled down with PULL; picked from 2 pairs x 3 lookbacks
                                       # (25/7 and 15/3, LOOK 48/60/120, 1h and 4h); the repo's "half the flow is buys" is dropped
STOP = 0.15                            # the repo's -15% hard stop
TRAIL_ON, TRAIL = 0.15, 0.20           # the repo's 20% trailing stop armed at +15%
TP = 1.0                               # the repo's +100% take-profit
MAX_HOLD = 30                          # my choice: 5 days; the repo's 1800 slots (12 min) has no meaning on 4h bars
TWIN_P = 1 / 1000                      # my choice: the rule fires about once per 1,300 bars per coin in the backtest
LABEL = ("Breakout Rider (itzalisha99) เหรียญมีม Binance 4 ชม. DOGE SHIB PEPE FLOKI BONK WIF: ย่อ 15% จากจุดสูงสุด 10 วัน "
         "แล้วปิดเหนือจุดสูงเดิม 3% ซื้อ stop -15% ถึง +15% trail 20% ขายหมด +100% ถือไม่เกิน 5 วัน "
         "(backtest Binance 4h ทั้งประวัติ หลังหัก 0.35%/ข้าง รวม 46 ไม้ +7.36% ต่อไม้ มัธยฐาน +0.72% ตัด 3 ไม้ดีสุด +2.01% "
         "DOGE 12 ไม้ +23.6% (9 ไม้ปี 2021) SHIB 9 +2.3% PEPE 11 +1.1% FLOKI 3 -10.0% BONK 5 +7.1% WIF 6 +3.0% "
         "permutation 200 รอบ p 0.005/0.214/0.428/0.940/0.080/0.199 เกณฑ์ 15/3 เลือกจาก 6 แบบ เกณฑ์เดิม 25/7 ได้แค่ 7 ไม้)")
ACCOUNTS = {"state_fwd_pullbreak.json": ("rule", LABEL),
            "state_fwd_pullbreak_twin.json": ("random", "Breakout Rider ตัวควบคุม: เข้าแท่งสุ่ม ทางออกแบบเดียวกัน")}


def signal(b, i):
    if i < LOOK:
        return False
    w = b[i - LOOK:i]
    j = max(range(LOOK), key=lambda k: (w[k]["h"], k))      # last bar holding the old peak
    if j == LOOK - 1:
        return False
    peak, low = w[j]["h"], min(x["l"] for x in w[j + 1:])
    return low <= peak * (1 - PULL) and b[i]["c"] > peak * (1 + LIFT)


def manage(p, x):
    """One closed bar for an open long p. Returns (price, why) to sell now, ("next", why) to sell at the next open, or None."""
    e = p["entry"]
    if x["o"] <= p["stop"]:
        return x["o"], "หลุด stop (เปิดกระโดด)"
    if x["l"] <= p["stop"]:
        return p["stop"], "หลุด stop" if p["stop"] < e else "trail"
    if x["o"] >= e * (1 + TP):
        return x["o"], "+100% (เปิดกระโดด)"
    if x["h"] >= e * (1 + TP):
        return e * (1 + TP), "+100%"
    p["hi"] = max(p["hi"], x["h"])
    if p["hi"] >= e * (1 + TRAIL_ON):
        p["stop"] = max(p["stop"], p["hi"] * (1 - TRAIL))
    p["held"] += 1
    if p["held"] >= MAX_HOLD:
        return "next", "ครบ 5 วัน"
    return None


def trades(b, go=None):
    """The backtest on a full history: (entry_t, entry, exit, t of the bar that triggered the exit) oldest first.
    go(i) replaces the rule's signal (twin)."""
    out, p = [], None
    for i in range(len(b) - 1):
        x = b[i]
        if p and x["t"] >= p["entry_t"]:
            r = manage(p, x)
            if r:
                out.append((p["entry_t"], p["entry"], b[i + 1]["o"] if r[0] == "next" else r[0], x["t"]))
                p = None
                continue
        if p:
            continue
        if go(i) if go else signal(b, i):
            e = b[i + 1]["o"]
            p = dict(entry=e, stop=e * (1 - STOP), hi=e, held=0, entry_t=b[i + 1]["t"])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = px / p["entry"] - 1
    s["cash"] += p["qty"] * px - p["qty"] * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side="long", px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - p["qty"] * px * COST, cost_side=COST,
                         stop_set=p["stop"], why=why))


def step(s, sym, bars, mode, rng):
    seen = s.setdefault("seen", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        return
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            r = manage(p, x)
            if r:
                if r[0] == "next":
                    close(s, sym, bars[i + 1]["o"], bars[i + 1]["t"], r[1])
                else:
                    close(s, sym, r[0], x["t"] + B.H4, r[1])
                continue
        if sym in s["pos"]:
            continue
        if mode == "rule":
            go, why = signal(bars, i), "ย่อ 25% แล้วปิดเหนือจุดสูงเดิม 7%"
        else:
            go, why = rng.random() < TWIN_P, "สุ่มแท่ง"
        if not go:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / len(SYMS)
        if s["cash"] < usd * (1 + COST):
            continue
        s["cash"] -= usd + usd * COST
        et = bars[i + 1]["t"]
        s["pos"][sym] = dict(side="long", d=1, qty=usd / e, entry=e, last=e, usd=usd, stop=e * (1 - STOP), hi=e, held=0,
                             entry_t=et, t=iso(et), why=why)
        s["log"].append(dict(kind="buy", t=iso(et), coin=sym[:-4], side="long", px=e, usd=usd,
                             stop_set=e * (1 - STOP), why=why))
    if sym in s["pos"]:
        s["pos"][sym]["last"] = bars[-1]["c"]


def main():
    rng, cache = random.Random(), {}
    for sym in SYMS:
        try:
            cache[sym] = fetch(sym)
        except Exception as e:
            print("fwd_pullbreak fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
