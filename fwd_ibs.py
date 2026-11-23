#!/usr/bin/env python3
"""Forward paper test of IBS (internal bar strength) dip buying on US index ETFs (SPY, QQQ, IWM), opened 23 Nov 2026. Fake money only.

IBS = (close - low) / (high - low) of the day. Rule on Yahoo daily bars: a session closes with IBS below 0.1 (closed near
the day's low) -> buy at the next open, sell at that session's close. A third of the start per ETF, each third compounds
on its own, 0.01% per side. Entry is at the next open, not the signal close, because the close is only known after it prints.
Backtest 2005-2026, next-open entry: SPY 550 trades +0.13%/trade vs all open-to-close days -0.01% (p 0.002), QQQ 554 +0.16%
(p < 0.002), IWM 588 +0.15% (p < 0.002); since 2020 SPY +0.13%, QQQ +0.17%, IWM +0.15%. Losing years 6-7 of 22 per ETF.
Buying at the signal close itself was about twice as good, so a good part of the edge is the overnight gap that this
version gives up. Overlaps with fwd_rsi2us (same dips), but holds one session instead of until a bounce.
Threshold 0.1 chosen by me from 2 tried (0.1, 0.2). About 26 trades a year per ETF.
  state_fwd_ibs.json        the rule
  state_fwd_ibs_twin.json   control: random sessions (1 in 10), same open-to-close hold
  python3 fwd_ibs.py"""
import random
import fwd_overnight as O
from byttrade import iso, load, save

COST, TH, TWIN_P = 0.0001, 0.1, 0.1
SYMS = O.SYMS
ACCOUNTS = {"state_fwd_ibs.json": ("rule", "หุ้นสหรัฐ IBS: วันที่ปิดใกล้จุดต่ำสุดของวัน (IBS ต่ำกว่า 0.1) ซื้อ SPY QQQ IWM ตอนเปิดวันถัดไป ขายตอนปิดวันนั้น (backtest ชนะวันสุ่ม p 0.002)"),
            "state_fwd_ibs_twin.json": ("random", "หุ้นสหรัฐ IBS ตัวควบคุม: ซื้อเปิดวันสุ่ม ขายตอนปิดวันเดียวกัน")}


def ibs(x):
    return (x["c"] - x["l"]) / (x["h"] - x["l"]) if x["h"] > x["l"] else 0.5


def step(s, sym, bars, mode, rng):
    if not isinstance(s.get("seen"), dict):
        s["seen"] = {}
    seen, sl = s["seen"], s.setdefault("sleeve", {})
    if sym not in seen:
        seen[sym] = [x for x in bars if x["closed"]][-1]["t"]
        sl[sym] = s["start_usd"] / len(SYMS)
        return
    for i in range(1, len(bars)):                     # book session i once it has closed: signal from session i-1
        x, prev = bars[i], bars[i - 1]
        if not x["closed"] or x["t"] <= seen[sym]:
            continue
        seen[sym] = x["t"]
        go = ibs(prev) < TH if mode == "rule" else rng.random() < TWIN_P
        if not go:
            continue
        usd = sl[sym]
        ret = x["c"] / x["o"] - 1
        pnl = usd * ret - usd * COST - usd * (1 + ret) * COST
        sl[sym] += pnl
        s["cash"] += pnl
        why = f"IBS {ibs(prev):.2f}" if mode == "rule" else "วันสุ่ม"
        s["log"].append(dict(kind="buy", t=iso(x["t"]), coin=sym, side="long", px=x["o"], usd=usd, why=why))
        s["log"].append(dict(kind="sell", t=iso(x["t"] + 6.5 * 3600 * 1000), coin=sym, side="long", px=x["c"], usd=usd,
                             ret=round(ret, 6), pnl=pnl, cost_side=COST, why=why))


def main():
    rng, bars = random.Random(), {}
    for sym in SYMS:
        try:
            bars[sym] = O.fetch(sym)
        except Exception as e:
            print("fwd_ibs fetch failed", sym, type(e).__name__)
    for f, (mode, label) in ACCOUNTS.items():
        s = load(f, label)
        for sym, b in bars.items():
            step(s, sym, b, mode, rng)
        save(f, s)


if __name__ == "__main__":
    main()
