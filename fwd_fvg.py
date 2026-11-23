#!/usr/bin/env python3
"""Forward paper test of "FVG retest with 50 EMA filter" from WickCheck/pine-strategies (GitHub, Nov 2026, fvg_ema_filter.pine)
on BTC, ETH, SOL 4h bars (opened 23 Nov 2026 by the scout; backtest in LABEL, opened at any p because the user asked to
try weak ideas too). Fake money only.

On closed 4h Binance bars, as the Pine script: a bullish gap is low > high two bars back (zone high[2]..low), a bearish gap
the mirror; only the most recent gap of each kind is kept, forgotten after MAX_AGE bars, used up when it triggers an entry.
When flat: low <= gap top, close >= gap bottom, close > EMA50 and the gap is older than 1 bar -> long at the next open
(short is the mirror below EMA50). Stop AM x ATR14 (signal bar) from the fill, target RR x that distance. Exits on the bar
path from the entry bar on: stop first when one bar touches both, a gap through the stop or target fills at the open.
No time stop (the script has none). One position per coin, one third of the start per coin, 0.35% per side.
  state_fwd_fvg.json       BTC, ETH, SOL
  state_fwd_fvg_twin.json  control: random entry bars (TWIN_P per free bar) on the EMA50 side, same stop and target
  python3 fwd_fvg.py"""
import random
from byttrade import iso, load, save, fetch, wilder_atr, H4

COST = 0.0035                      # per side, as every account here
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]   # my choice; the repo tested GBP/USD, EUR/USD, gold on 1h
EMA_N, ATR_N, AM, MAX_AGE = 50, 14, 1.5, 50   # the script's defaults (ATR14 is ta.atr(14))
RR = 3.0                           # the script's default; 2R also tried (repo's blog compared both), 3R better on all three
TWIN_P = 1 / 40                    # my choice: the rule enters roughly once per 25 to 40 free bars
LABEL = ("FVG retest + EMA50 4 ชม. BTC ETH SOL (WickCheck/pine-strategies): ราคาย้อนแตะช่องว่าง 3 แท่งล่าสุดฝั่งเดียวกับ EMA50 "
         "stop 1.5 ATR เป้า 3R long+short (backtest 2017-2026 หลังหัก 0.35%/ข้าง BTC 703 ไม้ -0.50% ETH 744 ไม้ -0.28% SOL 498 ไม้ -0.18% "
         "มัธยฐาน -2.7 ถึง -4.2% ชนะ 27-29% ปี 2024+ -0.54/-0.21/-0.52% ตัวแฝดเข้าสุ่ม -0.50/-0.65/-0.57% permutation p 0.065/0.015/0.050)")
ACCOUNTS = {"state_fwd_fvg.json": ("rule", LABEL),
            "state_fwd_fvg_twin.json": ("random", "FVG ตัวควบคุม: เข้าแท่งสุ่ม ฝั่งตาม EMA50 stop 1.5 ATR เป้า 3R แบบเดียวกัน")}


def ema(b, n=EMA_N):
    c, out, k = [x["c"] for x in b], [None] * len(b), 2 / (n + 1)
    if len(c) < n:
        return out
    out[n - 1] = sum(c[:n]) / n
    for i in range(n, len(c)):
        out[i] = c[i] * k + out[i - 1] * (1 - k)
    return out


def book(g, b, i):
    """Gap bookkeeping at the close of bar i (g: dict bull, bear = [top, bot] or None, ba, ra = ages)."""
    if i >= 2 and b[i]["l"] > b[i - 2]["h"]:
        g["bull"], g["ba"] = [b[i]["l"], b[i - 2]["h"]], 0
    if i >= 2 and b[i]["h"] < b[i - 2]["l"]:
        g["bear"], g["ra"] = [b[i - 2]["l"], b[i]["h"]], 0
    g["ba"] += 1
    g["ra"] += 1


def gaps_upto(b, last):
    g = dict(bull=None, bear=None, ba=0, ra=0)
    for i in range(last + 1):
        book(g, b, i)
    return g


def signal(g, x, e):
    """Pine longSig / shortSig on closed bar x with EMA e; uses up the gap that fires."""
    if e is None:
        return 0
    u, d = g["bull"], g["bear"]
    if u and 1 < g["ba"] <= MAX_AGE and x["l"] <= u[0] and x["c"] >= u[1] and x["c"] > e:
        g["bull"] = None
        return 1
    if d and 1 < g["ra"] <= MAX_AGE and x["h"] >= d[1] and x["c"] <= d[0] and x["c"] < e:
        g["bear"] = None
        return -1
    return 0


def hit(p, x):
    """Exit price on bar x's path for position p (d, e, sd), else None."""
    d, ep, sd = p["d"], p["e"], p["sd"]
    stop, tgt = ep - d * sd, ep + d * RR * sd
    if d > 0:
        return x["o"] if x["o"] <= stop else stop if x["l"] <= stop else max(tgt, x["o"]) if x["h"] >= tgt else None
    return x["o"] if x["o"] >= stop else stop if x["h"] >= stop else min(tgt, x["o"]) if x["l"] <= tgt else None


def trades(b, first=60, mode="rule", rng=None):
    """The backtest (the scout's /tmp/scout_0751.py numbers): list of dict(t, d, e, x), oldest first."""
    e50, atr = ema(b), wilder_atr(b, ATR_N)
    g, out, p = gaps_upto(b, first - 1), [], None
    for i in range(first, len(b) - 1):
        x = b[i]
        if p and x["t"] >= p["t"]:
            px = hit(p, x)
            if px is not None:
                out.append(dict(t=p["t"], d=p["d"], e=p["e"], x=px))
                p = None
        book(g, b, i)
        if p or atr[i] is None or e50[i] is None:
            continue
        d = signal(g, x, e50[i]) if mode == "rule" else ((1 if x["c"] > e50[i] else -1) if rng.random() < TWIN_P else 0)
        if d:
            p = dict(t=b[i + 1]["t"], d=d, e=b[i + 1]["o"], sd=AM * atr[i])
    return out


def close(s, sym, px, t, why):   # as pullback.close
    p = s["pos"].pop(sym)
    ret = (px / p["entry"] - 1) * p["d"]
    s["cash"] += p["qty"] * px - abs(p["qty"]) * px * COST
    s["log"].append(dict(kind="sell", t=iso(t), coin=sym[:-4], side=p["side"], px=px, usd=p["usd"], ret=round(ret, 5),
                         pnl=p["usd"] * ret - p["usd"] * COST - abs(p["qty"]) * px * COST, cost_side=COST, why=why))


def step(s, sym, bars, mode, rng):
    seen, gaps = s.setdefault("seen", {}), s.setdefault("gaps", {})
    closed = [i for i, x in enumerate(bars) if x["closed"]]
    if sym not in seen or sym not in gaps:
        seen[sym] = bars[closed[-1]]["t"]
        gaps[sym] = gaps_upto(bars, closed[-1])
        return
    e50, atr, g = ema(bars), wilder_atr(bars, ATR_N), gaps[sym]
    for i, x in enumerate(bars):
        if not x["closed"] or x["t"] <= seen[sym] or i + 1 >= len(bars):
            continue
        seen[sym] = x["t"]
        p = s["pos"].get(sym)
        if p and x["t"] >= p["entry_t"]:
            px = hit(dict(d=p["d"], e=p["entry"], sd=p["sd"]), x)
            if px is not None:
                why = "ถึงเป้า 3R" if (px - p["entry"]) * p["d"] > 0 else "หลุด stop 1.5 ATR"
                close(s, sym, px, x["t"], why)
        book(g, bars, i)
        if sym in s["pos"] or atr[i] is None or e50[i] is None:
            continue
        d = signal(g, x, e50[i]) if mode == "rule" else ((1 if x["c"] > e50[i] else -1) if rng.random() < TWIN_P else 0)
        if not d:
            continue
        e, usd = bars[i + 1]["o"], s["start_usd"] / 3
        if d > 0 and s["cash"] < usd * (1 + COST):
            continue
        s["cash"] += (-usd if d > 0 else usd) - usd * COST
        why = ("ย้อนแตะช่องว่างขาขึ้น เหนือ EMA50" if d > 0 else "ย้อนแตะช่องว่างขาลง ใต้ EMA50") if mode == "rule" else "สุ่มแท่ง ฝั่งตาม EMA50"
        s["pos"][sym] = dict(side="long" if d > 0 else "short", d=d, qty=d * usd / e, entry=e, last=e, usd=usd,
                             sd=AM * atr[i], stop=e - d * AM * atr[i], target=e + d * RR * AM * atr[i],
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
            print("fwd_fvg fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        if s.get("seen") is None:
            s["seen"] = {}
        for sym, bars in cache.items():
            step(s, sym, bars, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
